-- Tabla de Athena sobre el archivo histórico de eventos (JSON comprimido en S3).
-- Particionado por cliente y fecha con proyección de particiones: no hace falta MSCK REPAIR ni
-- crear particiones a mano.
--
-- Antes de ejecutar: reemplaza <BUCKET_ARCHIVO> por el nombre real del bucket (pos-archivo-<cuenta>).
-- Consola de Athena -> Editor de consultas -> pega todo -> Ejecutar.
--
-- Clave de cada objeto (la escribe procesador-eventos):
--   s3://<BUCKET_ARCHIVO>/eventos/tenant=<tenant_id>/fecha=<AAAA-MM-DD>/<event_id>.json.gz
-- `datos` viene como texto JSON: se lee con json_extract_scalar (ver consultas de ejemplo abajo).

CREATE DATABASE IF NOT EXISTS pos;

CREATE EXTERNAL TABLE IF NOT EXISTS pos.eventos (
  event_id      string,
  tipo          string,
  v             int,
  tenant_id     string,
  local_id      string,
  ocurrido_en   string,
  registrado_en string,
  usuario_id    string,
  command_id    string,
  origen        string,
  datos         string
)
PARTITIONED BY (tenant string, fecha date)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://<BUCKET_ARCHIVO>/eventos/'
TBLPROPERTIES (
  'projection.enabled'          = 'true',
  'projection.tenant.type'      = 'injected',
  'projection.fecha.type'       = 'date',
  'projection.fecha.format'     = 'yyyy-MM-dd',
  'projection.fecha.range'      = '2026-01-01,NOW',
  'projection.fecha.interval'   = '1',
  'projection.fecha.interval.unit' = 'DAYS',
  'storage.location.template'   = 's3://<BUCKET_ARCHIVO>/eventos/tenant=${tenant}/fecha=${fecha}/'
);

-- Con 'injected', toda consulta DEBE filtrar por tenant (protege de mezclar clientes).

-- Ventas del día por local:
-- SELECT local_id,
--        count(*) AS ventas,
--        sum(cast(json_extract_scalar(datos, '$.total') AS bigint)) AS total
-- FROM pos.eventos
-- WHERE tenant = 'demo' AND fecha = date '2026-10-15' AND tipo = 'venta.cerrada'
-- GROUP BY local_id;

-- Auditoría de autorizaciones de un mes:
-- SELECT ocurrido_en, tipo, usuario_id, json_extract_scalar(datos, '$.autorizador_id') AS autorizador
-- FROM pos.eventos
-- WHERE tenant = 'demo' AND fecha BETWEEN date '2026-10-01' AND date '2026-10-31'
--   AND tipo IN ('autorizacion.concedida', 'autorizacion.rechazada')
-- ORDER BY ocurrido_en;
