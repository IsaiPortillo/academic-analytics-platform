# Funcionalidades de la lista D — registro de validación

Fecha: 29 de octubre de 2026. Base: volumen local con los datos sintéticos (36 704 inscripciones,
131 872 calificaciones). Todo se comprobó contra la aplicación en ejecución, con usuarios reales de
cada rol, y las cifras se contrastaron con SQL independiente. Los cambios de prueba se revirtieron.

## Resumen

| Bloque | Qué se agregó | Comprobaciones en vivo | Pruebas automatizadas |
|---|---|---|---|
| Auditoría y confirmaciones | Pantalla `/auditoria` (notas y actas, filtros, descargas); la bitácora guarda usuario, operación y evaluación; confirmar antes de sobrescribir notas y de recargar el DW | 17/17 | `test_funcionalidades.py`, `test_actas_db.py` |
| Calificaciones y asistencia | Editar y eliminar evaluaciones; plantilla Excel con la lista; importar con vista previa; cerrar y reabrir acta; «Marcar todos presentes»; corregir o eliminar una sesión; importar asistencia | 43/43 | `test_funcionalidades.py`, `test_actas_db.py` |
| Usuarios y cuenta | Alta con contraseña temporal, cambio de rol, desactivar, restablecer; «Mi cuenta» (nombre, contraseña, apariencia); cambio obligatorio de la temporal; último acceso | 31/31 | `test_seguridad.py`, `test_actas_db.py` |
| Administración y malla | CRUD de períodos, secciones, materias, docentes, estudiantes, carreras y departamentos; malla curricular que escribe en Neo4j y rechaza ciclos | 34/34 | `test_funcionalidades.py` |
| Matrícula | Carga masiva con vista previa (cupo, estudiante inactivo, sección inexistente, duplicados); motivo, detalle y fecha de retiro | 16/16 | `test_funcionalidades.py` |
| Metas y almacén | Metas editables con justificación y responsable; estado frente a la meta en la vista ejecutiva y por período; historial de cargas y última validación del DW | 20/20 | `test_funcionalidades.py`, `etl.validar_dw` (90/90) |
| Reporte personalizado | Tema, agrupación, desglose, rango de fechas y gráfica (líneas, columnas, barras) en pantalla, PDF y Excel | 21/21 | `test_funcionalidades.py` |
| Seguridad (repaso) | CSRF en todas las rutas nuevas, sesiones que se cortan al cambiar rol o contraseña | 22/22 | `test_seguridad.py`, `test_rls_docente.py` |

**Total:** 204 comprobaciones en vivo y 308 pruebas automatizadas (237 del backend, 24 del
dashboard, 47 del ETL), todas correctas.

## Decisiones

- **Las reglas viven en el motor.** El cierre de acta lo impone un trigger, y cerrar o reabrir son
  funciones `SECURITY DEFINER` que validan rol, propiedad de la sección, ponderación 100 % y notas
  completas (`17_auditoria_y_actas.sql`). La prueba en vivo lo demuestra: con el acta cerrada, ni
  el superusuario cambia una nota. El docente cambia su contraseña con `cambiar_password_propio()`
  (`18_usuarios_cuenta.sql`) sin tener permiso sobre la tabla `usuarios`, así que no puede
  ascenderse.
- **Importar nunca escribe en la vista previa.** La confirmación reenvía los cambios y el servidor
  los vuelve a validar. Un cambio manipulado en el formulario de confirmación se rechaza.
- **Reporte personalizado con listas blancas.** Tema, agrupación, métrica, desglose y gráfica solo
  aceptan valores conocidos, y las fechas van como parámetros. Seis intentos de inyección
  devolvieron la página normal, sin error de SQL.
- **Metas en el OLTP, estado en el DW.** El coordinador edita la meta; el ETL la lleva a
  `dim_indicador` y `fact_indicador_periodo` (MERGE idempotente), y `v_semaforo_indicador` da el
  estado. La meta nueva se ve en el tablero después de recargar el DW, no antes.
- **Carnet.** Al dar de alta un estudiante, el carnet se guarda solo como hash (HMAC si hay
  `CARNET_CLAVE`). No se muestra ni se puede editar después.

## Limitaciones conocidas

- **Fechas sintéticas escasas.** Las evaluaciones caen en 4 fechas (2023), las inscripciones en 1
  y la asistencia en 12. Los reportes por día, semana o mes funcionan, pero muestran pocos puntos.
- **Las metas son propuestas.** 90 000 ± 10 000, 130 ± 15, 22 % ± 3, 5 % ± 1 y 20 % ± 3 son
  valores razonables para los datos sintéticos. Hay que reemplazarlos por los de la memoria.
- **Neo4j Community no tiene roles finos.** La aplicación escribe con el mismo usuario que el ETL.
  La regla de que solo el coordinador edita la malla la impone la aplicación, no Neo4j.
- **El límite de intentos de login vive en memoria.** Se reinicia con el proceso y no se comparte
  entre varios workers. En el servidor lo complementa el `limit_req` de nginx.
- **El dashboard de Streamlit** tiene su propia sesión, sin el corte por inactividad de la
  aplicación web.

## Para quien trae estos cambios

```bash
./scripts/aplicar_ddl_pendiente.sh   # aplica 17, 18, 19 y 20 si faltan
python -m etl.carga                  # el 20 toca el Data Warehouse
python -m etl.validar_dw             # 90 de 90
```
