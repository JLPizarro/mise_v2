"""Genera las figuras del informe EP3 (SVG) en esta carpeta: python docs/informe/figuras/generar_figuras.py

PNG para Word (2x), con Chrome: chrome --headless=new --force-device-scale-factor=2 --window-size=1600,1090
--screenshot=figura-1-arquitectura.png figura-1-arquitectura.svg (figura 2: 1400x600; figura 3: 1400x560).
"""

from html import escape
from pathlib import Path

DESTINO = Path(__file__).parent
FUENTE = "Segoe UI, Arial, Helvetica, sans-serif"

ESTILOS = {
    # relleno, borde
    "lambda": ("#FFFFFF", "#C2812A"),
    "dato": ("#FCE4C4", "#C2812A"),
    "cola": ("#FFF1DC", "#C2812A"),
    "local": ("#FFFFFF", "#3F7FBF"),
    "actor": ("#FFFFFF", "#8A70C2"),
    "ok": ("#E7F5EC", "#2E8B57"),
    "no": ("#FBEAEA", "#C0392B"),
    "neutro": ("#FFFFFF", "#6B7280"),
    "aviso": ("#FFF8E1", "#C9A227"),
}
GRUPOS = {
    "aws": ("#FFF8EF", "#E3A247"),
    "local": ("#EEF5FB", "#6A9FD0"),
    "actor": ("#F5F1FB", "#9B86C9"),
    "sub": ("#FFFDF9", "#EBC48A"),
    "gris": ("#F7F7F8", "#C7CAD1"),
}
FLECHAS = {
    "peticion": ("#374151", ""),
    "identidad": ("#7B5FBF", "6 4"),
    "async": ("#D9822B", "7 4"),
    "ok": ("#2E8B57", ""),
    "no": ("#C0392B", "6 4"),
    "azul": ("#2F6FB0", ""),
    "verde": ("#2E8B57", ""),
    "manual": ("#6B7280", ""),
}


class Figura:
    def __init__(self, ancho: int, alto: int, titulo: str):
        self.ancho, self.alto, self.titulo = ancho, alto, titulo
        self.partes: list[str] = []

    def grupo(self, x, y, w, h, etiqueta, estilo, *, abajo=False):
        relleno, borde = GRUPOS[estilo]
        self.partes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{relleno}" stroke="{borde}" stroke-width="1.5"/>')
        ty = y + h - 12 if abajo else y + 22
        self.partes.append(f'<text x="{x + 14}" y="{ty}" class="grupo" fill="{borde}">{escape(etiqueta)}</text>')

    def caja(self, x, y, w, h, titulo, subs=(), estilo="lambda", *, titulo_tam=15):
        relleno, borde = ESTILOS[estilo]
        self.partes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{relleno}" stroke="{borde}" stroke-width="1.6"/>')
        lineas = 1 + len(subs)
        alto_texto = 18 + 16 * (lineas - 1)
        cy = y + (h - alto_texto) / 2 + 14
        self.partes.append(f'<text x="{x + w / 2}" y="{cy}" class="t" font-size="{titulo_tam}" text-anchor="middle">{escape(titulo)}</text>')
        for i, s in enumerate(subs):
            self.partes.append(f'<text x="{x + w / 2}" y="{cy + 18 + 16 * i}" class="s" text-anchor="middle">{escape(s)}</text>')

    def flecha(self, d, estilo="peticion", *, punta=True, doble=False):
        color, guion = FLECHAS[estilo]
        extra = f' stroke-dasharray="{guion}"' if guion else ""
        fin = f' marker-end="url(#m-{estilo})"' if punta else ""
        ini = f' marker-start="url(#i-{estilo})"' if doble else ""
        self.partes.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8"{extra}{fin}{ini}/>')

    def texto(self, x, y, contenido, *, clase="e", anchor="start", color=None, peso=None):
        attrs = f' fill="{color}"' if color else ""
        attrs += f' font-weight="{peso}"' if peso else ""
        self.partes.append(f'<text x="{x}" y="{y}" class="{clase}" text-anchor="{anchor}"{attrs}>{escape(contenido)}</text>')

    def svg(self) -> str:
        marcas = "".join(
            f'<marker id="m-{n}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
            f'<marker id="i-{n}" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
            for n, (c, _) in FLECHAS.items())
        estilo = (f"text{{font-family:{FUENTE};}} .t{{font-weight:600;fill:#1F2937;}} .s{{font-size:12.5px;fill:#4B5563;}}"
                  f" .grupo{{font-size:13px;font-weight:700;letter-spacing:.06em;}} .e{{font-size:12.5px;fill:#374151;}}"
                  f" .eb{{font-size:12.5px;fill:#374151;font-weight:600;}}"
                  f" .lbl{{font-size:12.5px;fill:#1F2937;paint-order:stroke;stroke:#FFFFFF;stroke-width:4px;stroke-linejoin:round;}}")
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.ancho} {self.alto}" width="{self.ancho}" height="{self.alto}" role="img" aria-label="{escape(self.titulo)}">'
                f'<title>{escape(self.titulo)}</title><defs>{marcas}<style>{estilo}</style></defs>'
                f'<rect width="100%" height="100%" fill="#FFFFFF"/>' + "".join(self.partes) + "</svg>")


def leyenda(f: Figura, x, y, w, entradas):
    f.grupo(x, y, w, 30 + 24 * len(entradas), "LEYENDA", "gris")
    for i, (estilo, texto) in enumerate(entradas):
        yy = y + 46 + 24 * i
        f.flecha(f"M{x + 16},{yy - 4} H{x + 66}", estilo)
        f.texto(x + 76, yy, texto)


# --- Figura 1: arquitectura --------------------------------------------------------------------------

def figura_1() -> Figura:
    f = Figura(1600, 1090, "Figura 1. Arquitectura de MISE v2: PWA en los dispositivos del local y servicios administrados de AWS")

    # Identidad
    f.grupo(20, 20, 310, 112, "IDENTIDAD", "actor")
    f.caja(40, 48, 270, 70, "Google", ["inicio de sesión (OAuth 2.0 / OpenID)"], "actor")

    # Restaurante
    f.grupo(20, 150, 310, 530, "RESTAURANTE", "local")
    f.caja(40, 190, 260, 70, "Celular del garzón", ["PWA instalable", "no guarda datos del negocio"], "local")
    f.caja(40, 280, 260, 84, "PC de caja (estación)", ["PWA con cola local:", "sigue tomando comandas", "si se corta internet"], "local")
    f.caja(40, 590, 260, 72, "Impresoras térmicas", ["cocina, barra y caja", "protocolo CloudPRNT"], "local")
    f.texto(170, 404, "Red del local con respaldo celular", anchor="middle", clase="s")
    f.texto(170, 420, "(router e impresoras con energía de respaldo)", anchor="middle", clase="s")

    f.grupo(20, 700, 310, 128, "FUERA DEL LOCAL", "actor")
    f.caja(40, 738, 260, 72, "Dueño y administración", ["la misma PWA, desde", "cualquier lugar"], "actor")

    leyenda(f, 20, 850, 310, [("peticion", "petición de la PWA o la impresora"),
                              ("identidad", "identidad (token de Google)"),
                              ("async", "evento o mensaje en segundo plano")])

    # AWS
    f.grupo(360, 20, 1222, 1052, "AWS · US-EAST-1 · SERVICIOS ADMINISTRADOS, SIN SERVIDORES PROPIOS", "aws", abajo=True)
    f.caja(460, 70, 220, 70, "Amazon S3 · sitio", ["PWA por HTTPS"], "dato")
    f.caja(720, 70, 440, 70, "Amazon API Gateway (HTTP API, stage prod)", ["autorizador JWT de Google · CORS · límites por ruta"], "lambda")
    f.caja(1220, 70, 330, 70, "Amazon CloudWatch", ["registros (7 días) y 9 alarmas"], "neutro")

    f.grupo(400, 185, 1150, 180, "FUNCIONES DE LA API · AWS LAMBDA (ALIAS «VIVO»)", "sub")
    xs = (415, 695, 975, 1255)
    fila1 = (("salon", "plano y carta"), ("pedidos", "comanda y tandas"), ("caja", "cobro, turno, retiros"),
             ("administracion", "catálogo, mesas, personal"))
    fila2 = (("reportes", "turnos e indicadores"), ("impresion", "trabajos CloudPRNT"),
             ("contingencia", "comandas durante una falla"), ("mensajeria", "destinos, reglas y fallidos"))
    for x, (n, s) in zip(xs, fila1):
        f.caja(x, 218, 265, 54, n, [s], "lambda", titulo_tam=14)
    for x, (n, s) in zip(xs, fila2):
        f.caja(x, 284, 265, 54, n, [s], "lambda", titulo_tam=14)
    f.texto(415, 357, "+ reservas y pedidos-externos (base para versiones siguientes)", clase="s")

    f.caja(415, 400, 400, 66, "Amazon DynamoDB · configuracion", ["catálogo, mesas, personal, destinos"], "dato")
    f.caja(860, 400, 420, 66, "Amazon DynamoDB · operacion", ["pedidos, caja y eventos (misma transacción)"], "dato")
    f.caja(1310, 400, 240, 66, "Amazon S3 + Athena", ["archivo histórico consultable"], "dato")

    f.grupo(400, 500, 1150, 330, "PROCESAMIENTO EN SEGUNDO PLANO", "sub")
    f.caja(415, 540, 300, 62, "procesador-eventos", ["efectos de cada evento"], "lambda")
    f.caja(760, 540, 230, 62, "Amazon SQS · dte-emision", ["cola de documentos"], "cola", titulo_tam=14)
    f.caja(1030, 540, 230, 62, "emision-dte", ["emite boleta o factura"], "lambda")
    f.caja(760, 630, 230, 62, "Amazon SQS · contingencia", ["FIFO: en orden por mesa"], "cola", titulo_tam=14)
    f.caja(1030, 630, 230, 62, "drenador-contingencia", ["reaplica las comandas"], "lambda")
    f.caja(415, 720, 300, 62, "Amazon EventBridge", ["regla cada 5 minutos"], "cola")
    f.caja(760, 720, 230, 62, "tareas-programadas", ["reencola y vigila"], "lambda")
    f.caja(1305, 580, 230, 112, "Colas de fallidos (3)", ["mensajes apartados 14 días", "con el error registrado", "reproceso desde Mensajería"], "cola")

    f.grupo(400, 860, 1150, 180, "DISTRIBUCIÓN DE AVISOS", "sub")
    f.caja(415, 900, 330, 66, "Amazon SNS · avisos del negocio", ["atributos: tipo de aviso y local"], "cola", titulo_tam=14)
    f.caja(790, 892, 400, 82, "Destinos con reglas de distribución", ["correo o cola SQS propia", "solo los avisos elegidos y de su local"], "ok")
    f.caja(1305, 893, 230, 80, "SNS · alertas técnicas", ["documento fallido,", "impresoras y alarmas"], "cola", titulo_tam=14)

    # Flechas de identidad
    f.flecha("M285,118 V190", "identidad")
    f.texto(278, 170, "inicio de sesión", clase="s", anchor="end")
    f.flecha("M310,60 H940 V70", "identidad")
    f.texto(680, 54, "claves públicas de Google para validar el token", anchor="middle", clase="s")

    # Bus de dispositivos
    for y in (225, 322, 626, 774):
        f.flecha(f"M300,{y} H342", "peticion", punta=False)
    f.flecha("M342,774 V105 H460", "peticion")
    f.texto(347, 98, "descarga la PWA", clase="s")
    f.flecha("M342,162 H900 V140", "peticion")
    f.texto(560, 178, "HTTPS: token de Google (personal) o clave (impresoras)", anchor="middle", clase="s")
    f.flecha("M1060,140 V185", "peticion")
    f.texto(1068, 168, "invoca la función de cada ruta", clase="s")

    # Datos
    f.flecha("M615,365 V400", "peticion")
    f.flecha("M1070,365 V400", "peticion")
    f.texto(1078, 390, "dato y evento en una transacción", clase="s")

    # Asíncrono
    f.flecha("M900,466 V484 H700 V540", "async")
    f.texto(692, 497, "flujo de eventos (Streams)", clase="s", anchor="end")
    f.flecha("M715,571 H760", "async")
    f.flecha("M990,571 H1030", "async")
    f.flecha("M837,365 V520 H737 V661 H760", "async")
    f.texto(730, 652, "comandas", clase="s", anchor="end")
    f.texto(730, 667, "en falla", clase="s", anchor="end")
    f.flecha("M990,661 H1030", "async")
    f.flecha("M715,751 H760", "async")
    f.flecha("M1260,596 H1305", "async")
    f.flecha("M1260,661 H1305", "async")
    f.flecha("M415,571 H407 V933 H415", "async")
    f.texto(412, 846, "avisos", clase="s")
    f.flecha("M745,933 H790", "async")
    f.flecha("M1550,105 H1566 V933 H1535", "async")
    f.texto(1560, 520, "alarmas", clase="s", anchor="end")
    f.flecha("M1290,338 V1010 H1000 V974", "async")
    f.texto(1015, 1024, "Mensajería: crea y elimina destinos y reglas; reprocesa o descarta fallidos", clase="s")
    return f


# --- Figura 2: destinos y reglas -------------------------------------------------------------------------

def ejemplo(f: Figura, texto: list[str]):
    """Franja superior común a las figuras de un solo ejemplo."""
    f.grupo(20, 20, f.ancho - 40, 34 + 18 * len(texto), "EJEMPLO", "gris")
    for i, linea in enumerate(texto):
        f.texto(118, 39 + 18 * i, linea, clase="e")


def figura_2() -> Figura:
    f = Figura(1400, 690, "Figura 2. Distribución de avisos por reglas: cada aviso se publica una vez y llega solo a los destinos cuya regla coincide")
    ejemplo(f, ["En MISE Centro el proveedor rechaza una boleta y una comanda tomada durante una caída queda en conflicto. Cada aviso",
                "se publica una sola vez; SNS entrega una copia a cada destino cuya regla incluye ese aviso y ese local, y a nadie más."])

    f.texto(40, 112, "AVISOS DEL LOCAL", clase="grupo", color="#6B7280")
    f.caja(40, 140, 300, 96, "Boleta rechazada", ["origen: emisión del documento", "aviso: documento rechazado · MISE Centro"], "neutro")
    f.caja(40, 390, 300, 96, "Comanda en conflicto", ["origen: reaplicación tras una caída", "aviso: comanda en conflicto · MISE Centro"], "neutro")

    f.texto(420, 112, "DISTRIBUCIÓN", clase="grupo", color="#6B7280")
    f.caja(420, 230, 290, 150, "Amazon SNS · tema de avisos", ["recibe cada aviso una vez", "y compara sus atributos (aviso", "y local) con la regla de cada", "destino: entrega una copia", "solo donde coinciden"], "cola", titulo_tam=14)

    f.texto(800, 112, "DESTINOS Y SUS REGLAS", clase="grupo", color="#6B7280")
    destinos = [
        (125, "Contabilidad · cola", ["local: MISE Centro", "reglas: documento rechazado"], "ok"),
        (235, "Jefe de turno · correo", ["local: MISE Centro", "reglas: comanda en conflicto"], "ok"),
        (345, "Dueño · correo", ["local: MISE Centro", "reglas: documento rechazado, comanda en conflicto"], "ok"),
        (455, "Contabilidad Norte · cola", ["local: Sucursal Norte", "reglas: documento rechazado"], "no"),
    ]
    for y, titulo, subs, estilo in destinos:
        f.caja(800, y, 330, 84, titulo, subs, estilo, titulo_tam=14)

    f.texto(1160, 112, "QUÉ RECIBE", clase="grupo", color="#6B7280")
    verde, azul, gris = "#2E8B57", "#2F6FB0", "#8A8F98"
    resultados = [
        (125, [("✔ documento rechazado", verde), ("✕ comanda en conflicto: no es su regla", gris)]),
        (235, [("✕ documento rechazado: no es su regla", gris), ("✔ comanda en conflicto", azul)]),
        (345, [("✔ documento rechazado", verde), ("✔ comanda en conflicto", azul)]),
        (455, [("✕ documento rechazado: otro local", gris), ("✕ comanda en conflicto: otro local", gris)]),
    ]
    for y, lineas in resultados:
        for i, (texto, color) in enumerate(lineas):
            f.texto(1160, y + 36 + 22 * i, texto, clase="eb", color=color)

    # Recorridos: cada aviso entra a SNS y sale solo hacia los destinos cuya regla coincide.
    f.flecha("M340,188 H380 V285 H420", "verde")
    f.flecha("M340,438 H380 V325 H420", "azul")
    f.flecha("M710,285 H740 V167 H800", "verde")
    f.flecha("M740,285 V377 H800", "verde")
    f.flecha("M710,325 H765 V277 H800", "azul")
    f.flecha("M765,325 V397 H800", "azul")
    f.flecha("M565,380 V497 H776", "no", punta=False)
    f.texto(786, 502, "✕", anchor="middle", clase="eb", color="#C0392B")
    f.texto(575, 490, "local distinto: no pasa", clase="s")

    f.grupo(40, 575, 700, 100, "LEYENDA", "gris")
    f.flecha("M60,619 H110", "verde")
    f.texto(120, 623, "copia del aviso «documento rechazado»")
    f.flecha("M60,645 H110", "azul")
    f.texto(120, 649, "copia del aviso «comanda en conflicto»")
    f.flecha("M400,619 H450", "no", punta=False)
    f.texto(460, 623, "la regla no coincide: no se entrega")
    f.caja(800, 575, 570, 100, "Administración → Mensajería (dueño o admin)",
           ["crea y elimina estos destinos y sus reglas; valida antes de aplicar", "los destinos de tipo cola se revisan con «Ver mensajes»"], "neutro", titulo_tam=14)
    return f


def figura_3() -> Figura:
    f = Figura(1400, 1110, "Figura 3. Secuencia de un mensaje fallido: qué hace cada componente y dónde se decide")
    ejemplo(f, ["El proveedor de documentos tributarios no responde y una boleta no se puede emitir. Cada columna es un componente;",
                "cada fila numerada, una interacción en orden. Los rombos ◆ marcan dónde se toma una decisión (detalle abajo)."])

    vidas = [  # x, título, subtítulo, estilo
        (100, "procesador-eventos", "Lambda", "lambda"),
        (270, "dte-emision", "cola SQS", "cola"),
        (440, "emision-dte", "Lambda", "lambda"),
        (610, "Proveedor de DTE", "simulado", "neutro"),
        (780, "DynamoDB", "operacion", "dato"),
        (950, "dte-emision-fallidos", "cola SQS", "cola"),
        (1120, "CloudWatch + SNS", "alarma y alertas", "aviso"),
        (1290, "Mensajería", "PWA + función", "neutro"),
    ]
    alto_vida = 950
    for x, titulo, sub, estilo in vidas:
        f.caja(x - 75, 100, 150, 56, titulo, [sub], estilo, titulo_tam=12)
        f.partes.append(f'<path d="M{x},156 V{alto_vida}" stroke="#B8BCC4" stroke-width="1.2" stroke-dasharray="3 4"/>')

    def fase(y, h, texto):
        f.partes.append(f'<rect x="20" y="{y}" width="1360" height="{h}" rx="8" fill="#FFF8EF" fill-opacity="0.55" stroke="#EBC48A" stroke-width="1"/>')
        f.texto(30, y + 16, texto, clase="grupo", color="#C2812A")

    fase(168, 400, "1 · LA MÁQUINA REINTENTA SOLA")
    fase(576, 128, "2 · SE APARTA Y SE AVISA")
    fase(712, 238, "3 · UNA PERSONA DECIDE, SOLO PORQUE LA MÁQUINA NO PUDO")

    def msg(x1, x2, y, texto, estilo="async"):
        f.flecha(f"M{x1},{y} H{x2}", estilo)
        izq = min(x1, x2)
        f.partes.append(f'<text x="{izq + 8}" y="{y - 6}" class="lbl">{escape(texto)}</text>')

    def rombo(x, y, letra):
        f.partes.append(f'<path d="M{x},{y - 9} L{x + 9},{y} L{x},{y + 9} L{x - 9},{y} z" fill="#C9A227"/>')
        f.partes.append(f'<text x="{x}" y="{y + 4}" font-size="10" font-weight="700" fill="#FFFFFF" text-anchor="middle">{letra}</text>')

    msg(100, 270, 205, "1. venta cerrada: emitir boleta")
    msg(270, 440, 245, "2. entrega el mensaje (recepción 1)")
    msg(440, 610, 285, "3. emitir boleta")
    msg(610, 440, 320, "no responde (error 5xx)", "no")
    rombo(424, 320, "A")
    msg(440, 780, 360, "4. registra el error y el intento (diagnóstico)")
    msg(440, 270, 400, "5. lo devuelve: visible otra vez en ~30 s")
    rombo(254, 400, "B")
    f.partes.append('<rect x="250" y="420" width="420" height="58" rx="6" fill="#FFFFFF" fill-opacity="0.85" stroke="#C9A227" stroke-dasharray="4 3"/>')
    f.texto(262, 440, "se repite (pasos 2 a 5) en las recepciones 2, 3 y 4,", clase="e")
    f.texto(262, 458, "con esperas de ~1, ~2 y ~4 minutos entre una y otra", clase="e")
    msg(270, 440, 508, "6. recepción 5: falla otra vez")
    msg(440, 780, 548, "7. estado «fallido» + evento «documento fallido»")

    msg(270, 950, 612, "8. superó 5 recepciones: SQS lo mueve a la cola de fallidos (redrive)")
    rombo(270, 612, "B")
    msg(950, 1120, 652, "9. alarma: hay un fallido")
    f.texto(1158, 688, "correo al equipo técnico", clase="s")

    msg(1290, 950, 750, "10. lee el mensaje apartado")
    msg(1290, 780, 790, "11. lee su diagnóstico: intento 5, error 5xx")
    rombo(1290, 830, "C")
    f.texto(1290, 860, "proveedor de vuelta:", clase="s", anchor="end")
    f.texto(1290, 876, "Reprocesar", clase="eb", anchor="end")
    msg(1290, 270, 900, "12. Reprocesar: lo reenvía a su cola y lo borra de fallidos", "manual")
    msg(270, 440, 932, "13. entrega", "verde")
    msg(440, 780, 932, "14. emitida con el mismo folio", "verde")
    rombo(440, 950, "D")

    f.grupo(20, 968, 1360, 130, "DECISIONES", "gris")
    decisiones = [
        ("A", "emision-dte: ¿el proveedor respondió? No respondió → es recuperable: no se marca final y se reintenta.",
         "(Si hubiera respondido «rechazado», sería definitivo: sin reintentos y con aviso al dueño.)"),
        ("B", "SQS: ¿superó las 5 recepciones? No → el mensaje vuelve tras la espera. Sí → pasa solo a la cola de fallidos."),
        ("C", "Persona: ¿se arregló la causa? Sí → Reprocesar. Si la venta no corresponde → Descartar (se borra)."),
        ("D", "emision-dte: el folio ya estaba asignado → se reutiliza; reprocesar nunca crea una segunda boleta."),
    ]
    y = 1008
    for letra, texto, *extra in decisiones:
        rombo(46, y - 4, letra)
        f.texto(64, y, texto + (" " + extra[0] if extra else ""), clase="e")
        y += 22
    return f


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre, figura in (("figura-1-arquitectura", figura_1()), ("figura-2-distribucion-avisos", figura_2()),
                           ("figura-3-manejo-de-fallos", figura_3())):
        (DESTINO / f"{nombre}.svg").write_text(figura.svg(), encoding="utf-8")
        print(nombre)
