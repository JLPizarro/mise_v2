"""Operaciones sobre los recursos de mensajería de AWS (SNS y SQS), en un solo lugar.

La función `mensajeria` decide QUÉ hacer (validación, reglas, permisos); este módulo sabe CÓMO se
hace en AWS. Nadie más crea, modifica ni elimina colas o suscripciones en tiempo de ejecución.

Recursos que administra:
- Destinos de tipo «cola»: una cola SQS propia (`pos-destino-<id>`) suscrita al tema de avisos.
- Destinos de tipo «correo»: una suscripción de correo al tema de avisos (requiere confirmación).
- Reglas de distribución: la política de filtro de cada suscripción (avisos y local).
- Mensajes fallidos: lectura, reenvío a su cola de origen y descarte en las colas de fallidos.

Todas las operaciones son repetibles con el mismo resultado: crear una cola o suscripción que ya
existe con los mismos datos devuelve la existente. Eso hace seguro reintentar un comando.
"""

import json
import time

from pos_dominio.errores import ErrorDominio, ErrorInfraestructura
from pos_dominio.infra import aws

_PERMISO_DENEGADO = {"AccessDenied", "AccessDeniedException", "AuthorizationError"}
_NO_EXISTE = {"NotFound", "AWS.SimpleQueueService.NonExistentQueue", "QueueDoesNotExist", "ResourceNotFoundException"}
RETENCION_DESTINO = 4 * 24 * 3600  # los mensajes de un destino de tipo cola duran 4 días


class PermisoAwsDenegado(ErrorDominio):
    """El rol de ejecución no tiene permiso sobre el recurso. Es un problema de configuración, no del usuario."""

    http = 503
    codigo = "PERMISO_AWS_DENEGADO"


class SuscripcionPendiente(ErrorDominio):
    http = 409
    codigo = "SUSCRIPCION_PENDIENTE"


def _llamar(servicio: str, metodo: str, **parametros):
    try:
        return aws._llamar(servicio, metodo, **parametros)
    except ErrorInfraestructura as error:
        if error.causa in _PERMISO_DENEGADO:
            raise PermisoAwsDenegado(
                f"El rol del laboratorio no permite {servicio}:{metodo}. Revisa los permisos de LabRole.",
                detalle={"operacion": f"{servicio}.{metodo}"}) from error
        raise


class GestorMensajeria:
    def __init__(self, tema_avisos_arn: str, *, espera_lectura: int = 1):
        self.tema = tema_avisos_arn
        # arn:aws:sns:<region>:<cuenta>:<nombre>
        _, _, _, self.region, self.cuenta, _ = tema_avisos_arn.split(":", 5)
        self.espera_lectura = espera_lectura
        self._urls: dict[str, str] = {}

    # --- colas -------------------------------------------------------------------------------------------

    def url_cola(self, nombre: str) -> str:
        if nombre not in self._urls:
            self._urls[nombre] = _llamar("sqs", "get_queue_url", QueueName=nombre)["QueueUrl"]
        return self._urls[nombre]

    def arn_cola(self, nombre: str) -> str:
        return f"arn:aws:sqs:{self.region}:{self.cuenta}:{nombre}"

    def estado_cola(self, nombre: str) -> dict | None:
        """{visibles, en_proceso} o None si la cola no existe."""
        try:
            atributos = _llamar("sqs", "get_queue_attributes", QueueUrl=self.url_cola(nombre), AttributeNames=[
                "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
        except ErrorInfraestructura as error:
            if error.causa in _NO_EXISTE:
                return None
            raise
        return {"visibles": int(atributos.get("ApproximateNumberOfMessages", 0)),
                "en_proceso": int(atributos.get("ApproximateNumberOfMessagesNotVisible", 0))}

    def crear_cola_destino(self, nombre: str) -> tuple[str, str]:
        """Cola que solo el tema de avisos puede escribir. Devuelve (url, arn)."""
        arn = self.arn_cola(nombre)
        politica = {"Version": "2012-10-17", "Statement": [{
            "Sid": "AvisosDesdeElTema", "Effect": "Allow", "Principal": {"Service": "sns.amazonaws.com"},
            "Action": "sqs:SendMessage", "Resource": arn, "Condition": {"ArnEquals": {"aws:SourceArn": self.tema}}}]}
        url = _llamar("sqs", "create_queue", QueueName=nombre, Attributes={
            "MessageRetentionPeriod": str(RETENCION_DESTINO), "Policy": json.dumps(politica)})["QueueUrl"]
        self._urls[nombre] = url
        return url, arn

    def eliminar_cola(self, nombre: str) -> None:
        try:
            _llamar("sqs", "delete_queue", QueueUrl=self.url_cola(nombre))
        except ErrorInfraestructura as error:
            if error.causa not in _NO_EXISTE:
                raise
        self._urls.pop(nombre, None)

    def ver_mensajes(self, nombre: str, maximo: int = 10) -> list[dict]:
        """Mira los mensajes de una cola sin consumirlos (vuelven a estar visibles de inmediato)."""
        respuesta = _llamar("sqs", "receive_message", QueueUrl=self.url_cola(nombre), MaxNumberOfMessages=min(maximo, 10),
                            VisibilityTimeout=0, WaitTimeSeconds=self.espera_lectura,
                            AttributeNames=["SentTimestamp"], MessageAttributeNames=["All"])
        return [{"mensaje_id": m["MessageId"], "texto": m.get("Body", ""),
                 "atributos": {k: v.get("StringValue") for k, v in (m.get("MessageAttributes") or {}).items()},
                 "enviado_en": _fecha(m.get("Attributes", {}).get("SentTimestamp"))}
                for m in respuesta.get("Messages", [])]

    # --- suscripciones (destinos y reglas) ---------------------------------------------------------------

    def suscribir(self, protocolo: str, extremo: str, politica: dict) -> str:
        atributos = {"FilterPolicy": json.dumps(politica), "FilterPolicyScope": "MessageAttributes"}
        if protocolo == "sqs":
            atributos["RawMessageDelivery"] = "true"  # la cola recibe el texto del aviso tal cual
        return _llamar("sns", "subscribe", TopicArn=self.tema, Protocol=protocolo, Endpoint=extremo,
                       Attributes=atributos, ReturnSubscriptionArn=True)["SubscriptionArn"]

    def estado_suscripcion(self, arn: str) -> str:
        """"activa", "pendiente_confirmacion" o "no_existe"."""
        try:
            atributos = _llamar("sns", "get_subscription_attributes", SubscriptionArn=arn)["Attributes"]
        except ErrorInfraestructura as error:
            if error.causa in _NO_EXISTE:
                return "no_existe"
            raise
        return "pendiente_confirmacion" if atributos.get("PendingConfirmation") == "true" else "activa"

    def cambiar_filtro(self, arn: str, politica: dict) -> None:
        try:
            _llamar("sns", "set_subscription_attributes", SubscriptionArn=arn, AttributeName="FilterPolicy",
                    AttributeValue=json.dumps(politica))
        except ErrorInfraestructura as error:
            if error.causa == "InvalidParameter" and self.estado_suscripcion(arn) == "pendiente_confirmacion":
                raise SuscripcionPendiente("El correo aún no confirma la suscripción. Pulsa «Confirm subscription» "
                                           "en el correo de AWS y vuelve a intentarlo.") from error
            raise

    def desuscribir(self, arn: str) -> None:
        try:
            _llamar("sns", "unsubscribe", SubscriptionArn=arn)
        except ErrorInfraestructura as error:
            if error.causa in _NO_EXISTE:
                return
            if error.causa == "InvalidParameter" and self.estado_suscripcion(arn) == "pendiente_confirmacion":
                raise SuscripcionPendiente("El correo aún no confirma la suscripción y AWS no permite borrarla todavía. "
                                           "Confírmala desde el correo (o espera 3 días a que venza) y vuelve a "
                                           "intentarlo.") from error
            raise

    def publicar(self, asunto: str, mensaje: str, atributos: dict[str, str]) -> str:
        return aws.publicar(self.tema, asunto, mensaje, atributos=atributos)

    # --- mensajes fallidos -------------------------------------------------------------------------------

    def mensajes_fallidos(self, nombre: str, maximo: int = 30) -> list[dict]:
        """Lee hasta `maximo` mensajes de una cola de fallidos sin borrarlos y los deja visibles otra vez."""
        url = self.url_cola(nombre)
        vistos: dict[str, dict] = {}
        recibos: list[str] = []
        for _ in range(3):
            lote = _llamar("sqs", "receive_message", QueueUrl=url, MaxNumberOfMessages=10, VisibilityTimeout=15,
                           WaitTimeSeconds=self.espera_lectura, AttributeNames=["All"]).get("Messages", [])
            if not lote:
                break
            for m in lote:
                recibos.append(m["ReceiptHandle"])
                vistos.setdefault(m["MessageId"], _vista_fallido(m))
            if len(vistos) >= maximo:
                break
        for recibo in recibos:
            self._soltar(url, recibo)
        return list(vistos.values())[:maximo]

    def tomar(self, nombre: str, mensaje_id: str) -> dict | None:
        """Busca un mensaje por su id y lo retiene 60 s para actuar sobre él. Los demás quedan libres."""
        url = self.url_cola(nombre)
        encontrado = None
        otros: list[str] = []
        for _ in range(5):
            lote = _llamar("sqs", "receive_message", QueueUrl=url, MaxNumberOfMessages=10, VisibilityTimeout=60,
                           WaitTimeSeconds=self.espera_lectura, AttributeNames=["All"]).get("Messages", [])
            if not lote:
                break
            for m in lote:
                if m["MessageId"] == mensaje_id and encontrado is None:
                    encontrado = {**_vista_fallido(m), "recibo": m["ReceiptHandle"], "cuerpo_texto": m.get("Body", "")}
                else:
                    otros.append(m["ReceiptHandle"])
            if encontrado:
                break
        for recibo in otros:
            self._soltar(url, recibo)
        return encontrado

    def soltar(self, nombre: str, recibo: str) -> None:
        self._soltar(self.url_cola(nombre), recibo)

    def reenviar(self, origen: str, mensaje: dict, *, fifo: bool) -> str:
        """Devuelve el mensaje a su cola de origen (con su mismo grupo si es FIFO). Devuelve el nuevo id."""
        parametros = {"QueueUrl": self.url_cola(origen), "MessageBody": mensaje["cuerpo_texto"]}
        if fifo:
            parametros["MessageGroupId"] = mensaje["grupo"] or "reproceso"
            parametros["MessageDeduplicationId"] = f"{mensaje['mensaje_id']}-r{int(time.time())}"[:128]
        return _llamar("sqs", "send_message", **parametros)["MessageId"]

    def borrar(self, nombre: str, recibo: str) -> None:
        _llamar("sqs", "delete_message", QueueUrl=self.url_cola(nombre), ReceiptHandle=recibo)

    @staticmethod
    def _soltar(url: str, recibo: str) -> None:
        try:
            _llamar("sqs", "change_message_visibility", QueueUrl=url, ReceiptHandle=recibo, VisibilityTimeout=0)
        except ErrorInfraestructura:
            pass  # volverá a estar visible al vencer su visibilidad


def _fecha(milisegundos) -> str | None:
    if not milisegundos:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(milisegundos) / 1000))


def _vista_fallido(m: dict) -> dict:
    atributos = m.get("Attributes", {})
    try:
        cuerpo = json.loads(m.get("Body", ""))
    except ValueError:
        cuerpo = m.get("Body", "")
    return {"mensaje_id": m["MessageId"], "cuerpo": cuerpo,
            "recepciones": int(atributos.get("ApproximateReceiveCount", 0)),
            "enviado_en": _fecha(atributos.get("SentTimestamp")), "grupo": atributos.get("MessageGroupId")}
