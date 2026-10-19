# Copia congelada del backend local (solo lectura)

Copia exacta, sin modificar, de los archivos puros de `mise-backend/app/` tal como estaban en el
árbol de trabajo el 2026-10-14 (commit `bb22c60` más los cambios sin commitear de la versión
anterior, que quedó deprecada).

Sirve únicamente para las pruebas de caracterización: fijan el comportamiento del POS local para
que la migración no cambie resultados sin reportarlo. **No editar estos archivos.** Si una prueba de
caracterización falla, el error está en la prueba o en los dobles de `dobles.py`, nunca aquí.

Solo se copiaron los módulos que no dependen de FastAPI, Pydantic ni Postgres: entidades,
excepciones, puertos y los casos de uso de pedidos, pagos y caja.
