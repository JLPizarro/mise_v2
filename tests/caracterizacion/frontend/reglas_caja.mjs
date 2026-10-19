// Transcripción literal de las reglas de caja que hoy viven dentro de componentes React del
// frontend (mise-frontend, commit e084510 más cambios sin commitear, leído el 2026-10-14).
//
// Las funciones están definidas dentro de los componentes y no se exportan, así que no se pueden
// importar. Se copiaron sin cambiar la lógica; solo se convirtieron en funciones puras que reciben
// por parámetro lo que en el componente sale del estado de React. Cada una cita su origen.
//
// Uso:   node tests/caracterizacion/frontend/reglas_caja.mjs > tests/caracterizacion/frontend/golden.json
// La prueba test_frontend_golden.py compara el dominio nuevo contra golden.json y, si hay Node,
// verifica que golden.json siga coincidiendo con esta transcripción.

// PendientesCaja.tsx, crearDivisionIgual
export function crearDivisionIgual(total, cantidadPersonas) {
  const montoBase = Math.floor(total / cantidadPersonas)
  const resto = total % cantidadPersonas
  return Array.from({ length: cantidadPersonas }, (_, index) => montoBase + (index < resto ? 1 : 0))
}

// pagos.service.ts, calcularCantidadesPagadasPorItem
export function calcularCantidadesPagadasPorItem(pagos) {
  const cantidades = {}
  for (const pago of pagos) {
    if (pago.tipo_division !== "items") continue
    for (const itemCobrado of pago.items_cobrados) {
      cantidades[itemCobrado.item_id] = (cantidades[itemCobrado.item_id] ?? 0) + itemCobrado.cantidad
    }
  }
  return cantidades
}

// PendientesCaja.tsx, cobrarSeleccionItems (usa item.precio_unitario, el precio congelado)
export function cobrarSeleccionItems(items, pagos, seleccion, saldoPendiente) {
  const cantidadesPagadasPorItem = calcularCantidadesPagadasPorItem(pagos)
  let totalSeleccionado = 0
  const seleccionValida = []
  for (const seleccionado of seleccion) {
    const item = items.find((actual) => actual.item_id === seleccionado.item_id)
    if (!item) continue
    const yaPagadas = cantidadesPagadasPorItem[item.item_id] ?? 0
    const disponibles = Math.max(item.cantidad - yaPagadas, 0)
    const cantidad = Math.max(0, Math.min(seleccionado.cantidad, disponibles))
    if (cantidad <= 0) continue
    totalSeleccionado += item.precio_unitario * cantidad
    seleccionValida.push({ item_id: item.item_id, cantidad })
  }
  if (seleccionValida.length === 0 || totalSeleccionado <= 0) return null
  const montoACobrar = Math.min(totalSeleccionado, saldoPendiente)
  return { seleccion: seleccionValida, monto: montoACobrar }
}

// DivisionPorItems.tsx, getPrecioUnitario: la vista previa usa el precio ACTUAL del catálogo
export function precioVistaPreviaItems(item) {
  return item.producto.precio + (item.modificador?.precio_adicional ?? 0)
}

// MontoLibre.tsx, montoNumerico y montoValido
export function montoLibre(texto, saldoPendiente) {
  const valor = Number(texto || 0)
  const montoNumerico = !Number.isFinite(valor) ? 0 : Math.max(0, Math.floor(valor))
  return { monto: montoNumerico, valido: montoNumerico > 0 && montoNumerico <= saldoPendiente }
}

// PendientesCaja.tsx, prepararPropina
export function propinaSugerida(monto, propinaSugeridaPct) {
  return Math.round((monto * propinaSugeridaPct) / 100)
}

// FormularioPago.tsx, usarPropinaSugerida (10 % fijo)
export function botonPropinaSugerida(totalCuenta) {
  return Math.round(totalCuenta * 0.1)
}

// FormularioPago.tsx: obtenerMontoConsumo, obtenerPropinaMedio, obtenerTotalMedio,
// obtenerVuelto, formularioValido y confirmarPago
export function formularioPago(totalCuenta, propinaNumerica, pagoMixto, medios) {
  const obtenerConsumoAnterior = (index) =>
    medios.slice(0, index).reduce((total, medio) => total + Number(medio.monto || 0), 0)

  const obtenerMontoConsumo = (medio, index) => {
    if (!pagoMixto && medios.length === 1) return totalCuenta
    const esUltimo = index === medios.length - 1
    if (pagoMixto && medios.length === 1) return Number(medio.monto || 0)
    if (esUltimo) return Math.max(totalCuenta - obtenerConsumoAnterior(index), 0)
    return Number(medio.monto || 0)
  }

  const obtenerPropinaMedio = (index) => (index === medios.length - 1 ? propinaNumerica : 0)
  const obtenerTotalMedio = (medio, index) => obtenerMontoConsumo(medio, index) + obtenerPropinaMedio(index)

  const obtenerVuelto = (medio, index) => {
    if (medio.metodo !== "efectivo") return 0
    const recibido = Number(medio.efectivo_recibido || 0)
    return Math.max(recibido - obtenerTotalMedio(medio, index), 0)
  }

  const formularioValido = (() => {
    if (medios.length === 0) return false
    if (pagoMixto && medios.length !== 2) return false
    let consumoAcumulado = 0
    for (let index = 0; index < medios.length; index++) {
      const medio = medios[index]
      if (!medio.metodo) return false
      const montoConsumo = obtenerMontoConsumo(medio, index)
      if (montoConsumo <= 0) return false
      consumoAcumulado += montoConsumo
      if (consumoAcumulado > totalCuenta) return false
      if (medio.metodo === "debito" || medio.metodo === "credito") {
        if (!medio.codigo_autorizacion_pos.trim()) return false
      }
      if (medio.metodo === "efectivo") {
        const recibido = Number(medio.efectivo_recibido || 0)
        if (recibido < obtenerTotalMedio(medio, index)) return false
      }
    }
    return consumoAcumulado === totalCuenta
  })()

  return {
    valido: formularioValido,
    pagos: medios.map((medio, index) => ({
      metodo: medio.metodo,
      monto: obtenerMontoConsumo(medio, index),
      propina: obtenerPropinaMedio(index),
      vuelto: obtenerVuelto(medio, index),
    })),
  }
}

// ---------------------------------------------------------------------------
// Casos. Al agregar uno, regenerar golden.json.
// ---------------------------------------------------------------------------

const medio = (metodo, monto = "", codigo = "", recibido = "") => ({
  metodo, monto: String(monto), codigo_autorizacion_pos: codigo, efectivo_recibido: String(recibido),
})

const itemsEjemplo = [
  { item_id: "a", cantidad: 3, precio_unitario: 1500, producto: { precio: 1700 }, modificador: null },
  { item_id: "b", cantidad: 1, precio_unitario: 10000, producto: { precio: 8000 }, modificador: { precio_adicional: 2000 } },
  { item_id: "c", cantidad: 2, precio_unitario: 999, producto: { precio: 999 }, modificador: null },
]

const casos = {
  division_igual: [
    [10000, 3], [10000, 2], [100, 7], [1, 2], [5, 5], [0, 3], [12345, 20], [7, 20], [99999, 4],
  ].map(([total, n]) => ({ total, n, partes: crearDivisionIgual(total, n) })),

  seleccion_items: [
    { seleccion: [{ item_id: "a", cantidad: 2 }], pagos: [], saldo: 99999 },
    { seleccion: [{ item_id: "a", cantidad: 5 }], pagos: [], saldo: 99999 },
    { seleccion: [{ item_id: "a", cantidad: 2 }, { item_id: "b", cantidad: 1 }], pagos: [], saldo: 5000 },
    { seleccion: [{ item_id: "a", cantidad: 2 }],
      pagos: [{ tipo_division: "items", items_cobrados: [{ item_id: "a", cantidad: 2 }] }], saldo: 99999 },
    { seleccion: [{ item_id: "a", cantidad: 2 }],
      pagos: [{ tipo_division: "monto_libre", items_cobrados: [{ item_id: "a", cantidad: 3 }] }], saldo: 99999 },
    { seleccion: [{ item_id: "x", cantidad: 1 }], pagos: [], saldo: 99999 },
    { seleccion: [{ item_id: "a", cantidad: 0 }], pagos: [], saldo: 99999 },
    { seleccion: [{ item_id: "a", cantidad: 1 }, { item_id: "a", cantidad: 3 }], pagos: [], saldo: 99999 },
  ].map((c) => ({ ...c, resultado: cobrarSeleccionItems(itemsEjemplo, c.pagos, c.seleccion, c.saldo) })),

  vista_previa_items: itemsEjemplo.map((item) => ({
    item_id: item.item_id, precio_congelado: item.precio_unitario, precio_vista_previa: precioVistaPreviaItems(item),
  })),

  monto_libre: [
    ["5000", 8000], ["8000", 8000], ["8001", 8000], ["0", 8000], ["", 8000], ["12.9", 8000], ["abc", 8000], ["-3", 8000],
  ].map(([texto, saldo]) => ({ texto, saldo, ...montoLibre(texto, saldo) })),

  propina_sugerida: [
    [10000, 10], [1005, 10], [1015, 10], [1025, 10], [999, 10], [3333, 10], [10000, 0], [7, 15], [12345, 12],
    [250025, 2], [5, 10], [15, 10], [25, 10],
  ].map(([monto, pct]) => ({ monto, pct, propina: propinaSugerida(monto, pct) })),

  boton_propina: [10000, 1005, 15, 25, 3333].map((total) => ({ total, propina: botonPropinaSugerida(total) })),

  formulario_pago: [
    { total: 10000, propina: 1000, mixto: false, medios: [medio("efectivo", "", "", 11000)] },
    { total: 10000, propina: 1000, mixto: false, medios: [medio("efectivo", "", "", 10999)] },
    { total: 10000, propina: 1000, mixto: false, medios: [medio("efectivo", "", "", 20000)] },
    { total: 10000, propina: 1000, mixto: false, medios: [medio("debito", "", "")] },
    { total: 10000, propina: 1000, mixto: false, medios: [medio("debito", "", "  ")] },
    { total: 10000, propina: 1000, mixto: false, medios: [medio("credito", "", "A1")] },
    { total: 10000, propina: 1000, mixto: false, medios: [medio("transferencia")] },
    { total: 10000, propina: 1000, mixto: false, medios: [medio(null)] },
    { total: 10000, propina: 1000, mixto: true, medios: [medio("debito", 6000, "A1")] },
    { total: 10000, propina: 1000, mixto: true, medios: [medio("debito", 6000, "A1"), medio("efectivo", "", "", 5000)] },
    { total: 10000, propina: 1000, mixto: true, medios: [medio("debito", 6000, "A1"), medio("efectivo", "", "", 4999)] },
    { total: 10000, propina: 1000, mixto: true, medios: [medio("efectivo", 6000, "", 6000), medio("credito", "", "B2")] },
    { total: 10000, propina: 1000, mixto: true, medios: [medio("efectivo", 6000, "", 5999), medio("credito", "", "B2")] },
    { total: 10000, propina: 0, mixto: true, medios: [medio("debito", 10000, "A1"), medio("efectivo", "", "", 0)] },
    { total: 10000, propina: 0, mixto: true, medios: [medio("debito", 12000, "A1"), medio("efectivo", "", "", 0)] },
    { total: 10000, propina: 0, mixto: true, medios: [medio("debito", 4000, "A1"), medio("debito", "", "B")] },
    { total: 10000, propina: 0, mixto: true, medios: [medio("debito", 1, "A"), medio("debito", 1, "B"), medio("debito", "", "C")] },
  ].map((c) => ({ ...c, resultado: formularioPago(c.total, c.propina, c.mixto, c.medios) })),
}

console.log(JSON.stringify(casos, null, 2))
