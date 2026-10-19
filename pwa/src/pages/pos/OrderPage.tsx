import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { ErrorApi } from "@/api/cliente"
import type { Comando, Resultado } from "@/api/comandos"
import { abrirPedido, agregarItem, enviarTanda, modificarItem, pedido as pedirPedido, precuenta, quitarItem, reabrir } from "@/api/pedidos"
import type { RespuestaEnviar, RespuestaPrecuenta } from "@/api/pedidos"
import type { Categoria, Item, Modificador, Pedido, Producto } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import { useNotificar } from "@/components/comun/avisos"
import CatalogoProductos from "@/components/pos/CatalogoProductos"
import ComandaMesa from "@/components/pos/ComandaMesa"
import ModalProducto from "@/components/pos/ModalProducto"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { mensajeDeError, useComando } from "@/hooks/useComando"
import { useCarta } from "@/hooks/useCarta"
import { useComandosPendientes } from "@/hooks/usePendientes"
import { usePlano } from "@/hooks/usePlano"
import { useSondeo } from "@/hooks/useSondeo"
import { guardarCache, leerCache } from "@/offline/cache"
import { iraALaCola } from "@/offline/destino"
import { estacionActiva } from "@/offline/estacion"
import { aplicar, estadoMesa } from "@/offline/pedidoLocal"
import { useSesion } from "@/sesion/useSesion"

export default function OrderPage() {
  const { local, sesion } = useSesion()
  const localId = local!.local_id
  const mesaId = useParams().mesaId!
  const navigate = useNavigate()
  const notificar = useNotificar()
  const correr = useComando()
  const hayToken = sesion.token !== null

  const { plano, error: errorPlano } = usePlano(localId)
  const { productos, cargada, error: errorCarta } = useCarta(localId)
  const pendientes = useComandosPendientes(localId)
  const comandosMesa = useMemo(() => pendientes.filter((c) => c.mesaId === mesaId), [pendientes, mesaId])

  const [pedidoId, setPedidoId] = useState<string | null>(null)
  const [servidor, setServidor] = useState<Pedido | null>(null)
  const [errorPedido, setErrorPedido] = useState<string | null>(null)
  const [categoria, setCategoria] = useState<Categoria>("Entradas")
  const [elegido, setElegido] = useState<Producto | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [confirmandoReabrir, setConfirmandoReabrir] = useState(false)
  const iniciado = useRef(false)

  const mesa = plano?.mesas.find((m) => m.mesa_id === mesaId)

  // Lo que se muestra: el pedido del servidor (o de la caché) con los comandos todavía no confirmados encima.
  const vista = useMemo(
    () => comandosMesa.reduce<Pedido | null>((p, c) => aplicar(p, c, "superponer"), servidor),
    [servidor, comandosMesa],
  )
  const itemsPendientes = useMemo(
    () => new Set(comandosMesa.filter((c) => c.operacion === "pedido.agregar_item").map((c) => String(c.cuerpo.item_id))),
    [comandosMesa],
  )

  const cargarPedido = useCallback(
    async (id: string) => {
      try {
        const datos = await pedirPedido(localId, id)
        setServidor(datos)
        setErrorPedido(null)
        await guardarCache(`pedido:${localId}:${id}`, datos)
      } catch (e) {
        if (e instanceof ErrorApi && e.http === 404) {
          setServidor(null) // todavía no existe en el servidor: se ve solo lo pendiente
          return
        }
        if (estacionActiva(localId) !== null) {
          const guardado = await leerCache<Pedido>(`pedido:${localId}:${id}`)
          if (guardado) {
            setServidor(guardado)
            return
          }
        }
        setErrorPedido(mensajeDeError(e))
      }
    },
    [localId],
  )

  // Ejecuta un comando de la comanda. Antes de guardar en la cola local valida con las reglas del servidor.
  const lanzar = useCallback(
    async <T,>(c: Comando, fin?: (r: Resultado<T>) => void | Promise<void>) => {
      setOcupado(true)
      try {
        if (await iraALaCola(localId)) {
          try {
            aplicar(vista, c, "validar")
          } catch (e) {
            notificar(mensajeDeError(e), "error")
            return null
          }
        }
        const resultado = await correr<T>(c, fin)
        // Tras un rechazo (por ejemplo PEDIDO_EN_PRECUENTA) o un éxito normal, se vuelve a leer el pedido.
        const id = typeof c.cuerpo.pedido_id === "string" ? c.cuerpo.pedido_id : null
        if (id && (resultado === null || resultado.via === "normal")) await cargarPedido(id)
        return resultado
      } finally {
        setOcupado(false)
      }
    },
    [localId, vista, notificar, correr, cargarPedido],
  )

  // Entrar a la mesa: si tiene pedido se carga; si está libre se abre uno (P19).
  useEffect(() => {
    if (iniciado.current || !mesa) return
    iniciado.current = true
    if (mesa.estado === "bloqueada") {
      notificar("La mesa está bloqueada", "info")
      navigate(`/l/${localId}/salon`, { replace: true })
      return
    }
    const existente = estadoMesa(mesa, comandosMesa).pedido_id
    if (existente) {
      setPedidoId(existente)
      void cargarPedido(existente)
      return
    }
    if (mesa.estado !== "libre") {
      setErrorPedido("No se encontró el pedido de la mesa. Vuelve al salón e intenta de nuevo.")
      return
    }
    const comando = abrirPedido(localId, mesaId)
    void lanzar<Pedido>(comando, (r) => {
      if (r.via === "normal") {
        setPedidoId(r.respuesta.datos.pedido_id) // 200 con el pedido que ya tenía la mesa: se usa ese
        setServidor(r.respuesta.datos)
      } else {
        setPedidoId(String(comando.cuerpo.pedido_id))
      }
    })
  }, [mesa, comandosMesa, localId, mesaId, navigate, notificar, cargarPedido, lanzar])

  useSondeo(() => (pedidoId ? cargarPedido(pedidoId) : undefined), 15_000, pedidoId !== null && hayToken)

  const productosDeCategoria = useMemo(() => productos.filter((p) => p.categoria === categoria), [productos, categoria])

  function agregar(datos: { modificador: Modificador | null; observacion: string }) {
    const producto = elegido
    if (!producto || !pedidoId) return
    setElegido(null)
    void lanzar(
      agregarItem(localId, pedidoId, mesaId,
        { productoId: producto.producto_id, modificadorId: datos.modificador?.modificador_id, observacion: datos.observacion || undefined },
        {
          nombre: producto.nombre, categoria: producto.categoria, cuarto_id: producto.cuarto_id,
          precio_unitario: producto.precio + (datos.modificador?.precio_adicional ?? 0),
          modificador_nombre: datos.modificador?.nombre ?? null,
        }),
    )
  }

  const cambiarCantidad = (item: Item, cantidad: number) =>
    pedidoId && void lanzar(modificarItem(localId, pedidoId, mesaId, item.item_id, { cantidad }))
  const cambiarObservacion = (item: Item, observacion: string) =>
    pedidoId && void lanzar(modificarItem(localId, pedidoId, mesaId, item.item_id, { observacion }))
  const quitar = (item: Item) => pedidoId && void lanzar(quitarItem(localId, pedidoId, mesaId, item.item_id))

  function enviar() {
    if (!pedidoId) return
    void lanzar<RespuestaEnviar>(enviarTanda(localId, pedidoId, mesaId), (r) => {
      if (r.via !== "normal") return
      for (const imp of r.respuesta.datos.impresion) {
        if (imp.estado === "encolada") notificar(`Enviada a ${imp.cuarto}`, "ok")
        else if (imp.estado === "sin_impresora") notificar(`${imp.cuarto}: sin impresora configurada`, "info")
      }
    })
  }

  function pedirPrecuenta() {
    if (!pedidoId) return
    void lanzar<RespuestaPrecuenta>(precuenta(localId, pedidoId, mesaId), (r) => {
      if (r.via === "normal" && r.respuesta.datos.items_en_espera > 0) {
        notificar(`Hay ${r.respuesta.datos.items_en_espera} ítems que no se enviaron a cocina`, "info")
      }
      navigate(`/l/${localId}/salon`)
    })
  }

  function confirmarReabrir() {
    setConfirmandoReabrir(false)
    if (pedidoId) void lanzar(reabrir(localId, pedidoId, mesaId))
  }

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <Button type="button" variant="outline" onClick={() => navigate(`/l/${localId}/salon`)}>← Salón</Button>
      </div>
      {(errorPedido ?? errorPlano ?? errorCarta) && <Aviso tipo="error" className="mb-4">{errorPedido ?? errorPlano ?? errorCarta}</Aviso>}
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <CatalogoProductos
          categoria={categoria}
          productos={productosDeCategoria}
          cargada={cargada}
          onCategoria={setCategoria}
          onProducto={(p) => (pedidoId ? setElegido(p) : notificar("Espera: se está abriendo la mesa", "info"))}
        />
        <ComandaMesa
          numeroMesa={mesa?.numero ?? null}
          pedido={vista}
          pendientes={itemsPendientes}
          ocupado={ocupado || pedidoId === null}
          onCantidad={cambiarCantidad}
          onObservacion={cambiarObservacion}
          onQuitar={quitar}
          onEnviar={enviar}
          onPrecuenta={pedirPrecuenta}
          onReabrir={() => setConfirmandoReabrir(true)}
        />
      </div>

      <ModalProducto producto={elegido} onCerrar={() => setElegido(null)} onConfirmar={agregar} />

      <Dialog open={confirmandoReabrir} onOpenChange={setConfirmandoReabrir}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reabrir mesa</DialogTitle>
            <DialogDescription>Reabrir la mesa deja sin efecto la precuenta. ¿Confirmas?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setConfirmandoReabrir(false)}>Cancelar</Button>
            <Button type="button" onClick={confirmarReabrir}>Reabrir</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
