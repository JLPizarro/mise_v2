"""Casos de uso del módulo de caja: turnos, arqueo y retiros de efectivo."""

from dataclasses import dataclass

from app.application.ports import (
    ConfiguracionRepository,
    PagoRepository,
    RetiroCajaRepository,
    TurnoCajaRepository,
    UsuarioRepository,
)
from app.domain.entities import RetiroCaja, TurnoCaja
from app.domain.exceptions import NotFoundError, UnauthorizedError, ValidationError


def calcular_umbral_diferencia(
    efectivo_esperado: int, umbral_pct: float, umbral_minimo: int
) -> int:
    """Diferencia máxima tolerada antes de exigir un segundo conteo ciego.

    umbral_pct/umbral_minimo vienen de configuracion_restaurante (editables
    desde el dashboard) — antes estaban hardcodeados acá (2% / $5.000)."""
    return max(round(efectivo_esperado * umbral_pct / 100), umbral_minimo)


def _sum_metodo(pagos, metodo: str, incluir_propina: bool = True) -> int:
    return sum(
        p.monto + (p.propina if incluir_propina else 0)
        for p in pagos
        if p.metodo == metodo
    )


def _sum_efectivo(pagos, incluir_propina: bool = True) -> int:
    return _sum_metodo(pagos, "efectivo", incluir_propina)


class AbrirTurnoUseCase:
    def __init__(self, turnos: TurnoCajaRepository):
        self._turnos = turnos

    def execute(self, usuario_id: str, monto_apertura: int) -> TurnoCaja:
        if monto_apertura < 0:
            raise ValidationError("monto_apertura no puede ser negativo")

        if self._turnos.find_abierto() is not None:
            raise ValidationError("Ya hay un turno de caja abierto")

        return self._turnos.abrir(usuario_id, monto_apertura)


class ObtenerTurnoActualUseCase:
    def __init__(self, turnos: TurnoCajaRepository):
        self._turnos = turnos

    def execute(self) -> TurnoCaja:
        turno = self._turnos.find_abierto()

        if turno is None:
            raise NotFoundError("No hay un turno de caja abierto")

        return turno


@dataclass
class ResultadoConteo:
    turno: TurnoCaja
    requiere_segundo_conteo: bool
    conteo_completado: bool


class RegistrarConteoEfectivoUseCase:
    """Conteo ciego: el cajero declara cuánto efectivo hay sin conocer el
    efectivo esperado. Si la diferencia contra lo esperado supera el
    umbral, se exige un segundo conteo independiente."""

    def __init__(
        self,
        turnos: TurnoCajaRepository,
        pagos: PagoRepository,
        retiros: RetiroCajaRepository,
        configuracion: ConfiguracionRepository,
    ):
        self._turnos = turnos
        self._pagos = pagos
        self._retiros = retiros
        self._configuracion = configuracion

    def execute(self, turno_id: str, monto: int) -> ResultadoConteo:
        if monto < 0:
            raise ValidationError("El conteo no puede ser negativo")

        turno = self._turnos.find_by_id(turno_id)

        if turno is None:
            raise NotFoundError("Turno no encontrado")

        if turno.estado != "abierto":
            raise ValidationError("El turno ya está cerrado")

        es_segundo_conteo = turno.requiere_segundo_conteo and turno.segundo_conteo is None

        if not es_segundo_conteo and turno.primer_conteo is not None:
            raise ValidationError("El primer conteo ya fue registrado")

        pagos_turno = self._pagos.list_by_turno(turno_id)
        total_retiros = sum(r.monto for r in self._retiros.list_by_turno(turno_id))

        # Antes esto no restaba los retiros, a diferencia de CerrarTurnoUseCase
        # (mismo cálculo más abajo): un retiro entre medio inflaba el
        # esperado y podía exigir un segundo conteo sin necesidad.
        efectivo_esperado = (
            turno.monto_apertura + _sum_efectivo(pagos_turno) - total_retiros
        )

        turno_actualizado = self._turnos.registrar_conteo(
            turno_id, monto, es_segundo_conteo
        )

        if es_segundo_conteo:
            return ResultadoConteo(
                turno=turno_actualizado,
                requiere_segundo_conteo=False,
                conteo_completado=True,
            )

        config = self._configuracion.obtener()

        diferencia = abs(monto - efectivo_esperado)
        umbral = calcular_umbral_diferencia(
            efectivo_esperado,
            config.umbral_diferencia_pct,
            config.umbral_diferencia_minimo,
        )

        if diferencia > umbral:
            self._turnos.marcar_requiere_segundo_conteo(turno_id)

            turno_actualizado = self._turnos.find_by_id(turno_id)

            return ResultadoConteo(
                turno=turno_actualizado,
                requiere_segundo_conteo=True,
                conteo_completado=False,
            )

        return ResultadoConteo(
            turno=turno_actualizado,
            requiere_segundo_conteo=False,
            conteo_completado=True,
        )


class RegistrarConciliacionTerminalUseCase:
    def __init__(self, turnos: TurnoCajaRepository):
        self._turnos = turnos

    def execute(
        self,
        turno_id: str,
        total_debito_pos: int,
        total_credito_pos: int,
        total_notas_credito_pos: int,
    ) -> TurnoCaja:
        for valor in (total_debito_pos, total_credito_pos, total_notas_credito_pos):
            if valor < 0:
                raise ValidationError("Los totales del terminal no pueden ser negativos")

        turno = self._turnos.find_by_id(turno_id)

        if turno is None:
            raise NotFoundError("Turno no encontrado")

        if turno.estado != "abierto":
            raise ValidationError("El turno ya está cerrado")

        return self._turnos.registrar_conciliacion_terminal(
            turno_id, total_debito_pos, total_credito_pos, total_notas_credito_pos
        )


@dataclass
class ResultadoCierre:
    turno: TurnoCaja
    efectivo_esperado: int
    conteo_definitivo: int
    diferencia_efectivo: int
    total_debito_mise: int
    total_credito_mise: int
    total_efectivo_mise: int


class CerrarTurnoUseCase:
    def __init__(
        self,
        turnos: TurnoCajaRepository,
        pagos: PagoRepository,
        retiros: RetiroCajaRepository,
    ):
        self._turnos = turnos
        self._pagos = pagos
        self._retiros = retiros

    def execute(self, turno_id: str, usuario_cierre_id: str) -> ResultadoCierre:
        turno = self._turnos.find_by_id(turno_id)

        if turno is None:
            raise NotFoundError("Turno no encontrado")

        if turno.estado != "abierto":
            raise ValidationError("El turno ya está cerrado")

        if turno.primer_conteo is None:
            raise ValidationError("Falta registrar el conteo de efectivo")

        if turno.requiere_segundo_conteo and turno.segundo_conteo is None:
            raise ValidationError("Falta registrar el segundo conteo de efectivo")

        if turno.total_debito_pos is None:
            raise ValidationError("Falta registrar la conciliación del terminal")

        pagos_turno = self._pagos.list_by_turno(turno_id)
        retiros_turno = self._retiros.list_by_turno(turno_id)

        total_efectivo_mise = _sum_efectivo(pagos_turno)
        total_retiros = sum(r.monto for r in retiros_turno)

        efectivo_esperado = (
            turno.monto_apertura + total_efectivo_mise - total_retiros
        )

        conteo_definitivo = (
            turno.segundo_conteo
            if turno.segundo_conteo is not None
            else turno.primer_conteo
        )

        turno_cerrado = self._turnos.cerrar(turno_id, usuario_cierre_id)

        return ResultadoCierre(
            turno=turno_cerrado,
            efectivo_esperado=efectivo_esperado,
            conteo_definitivo=conteo_definitivo,
            diferencia_efectivo=conteo_definitivo - efectivo_esperado,
            total_debito_mise=_sum_metodo(pagos_turno, "debito"),
            total_credito_mise=_sum_metodo(pagos_turno, "credito"),
            total_efectivo_mise=total_efectivo_mise,
        )


class RegistrarRetiroUseCase:
    """Retiro de efectivo del turno, autorizado con el PIN de un admin/dueño."""

    def __init__(
        self,
        retiros: RetiroCajaRepository,
        turnos: TurnoCajaRepository,
        usuarios: UsuarioRepository,
    ):
        self._retiros = retiros
        self._turnos = turnos
        self._usuarios = usuarios

    def execute(
        self,
        turno_id: str,
        usuario_id: str,
        monto: int,
        motivo: str,
        codigo_autorizacion: str,
    ) -> RetiroCaja:
        if monto <= 0:
            raise ValidationError("El monto del retiro debe ser mayor a 0")

        if not motivo.strip():
            raise ValidationError("Ingresa el motivo del retiro")

        turno = self._turnos.find_by_id(turno_id)

        if turno is None or turno.estado != "abierto":
            raise ValidationError("No hay un turno de caja abierto")

        autorizador = self._usuarios.find_autorizador_por_pin(codigo_autorizacion)

        if autorizador is None:
            raise UnauthorizedError("Código de autorización inválido")

        return self._retiros.create(
            turno_id, usuario_id, autorizador.usuario_id, monto, motivo.strip()
        )


class ListarRetirosUseCase:
    def __init__(self, retiros: RetiroCajaRepository):
        self._retiros = retiros

    def execute(self, turno_id: str) -> list[RetiroCaja]:
        return self._retiros.list_by_turno(turno_id)
