# Alcance por carrera y rol admin — registro de validación

Fecha: 1 de noviembre de 2026. Base: volumen FMO (53 683 inscripciones, 2 303 estudiantes,
12 carreras, 523 materias). Scripts 23, 24 y 25 aplicados.

Todo se comprobó contra la aplicación en ejecución, con los tres roles, y contra PostgreSQL
directamente para lo que la pantalla no muestra. Los cambios de prueba se revirtieron.

## Resumen

| Bloque | Comprobaciones | Resultado |
|---|---|---|
| Acceso a las 26 rutas con los tres roles | 78 | ✅ 78/78 |
| Alcance de los datos y de las escrituras | 7 | ✅ 7/7 |
| Operación del coordinador en su carrera | 8 | ✅ 8/8 |
| Pruebas automatizadas nuevas (`test_rol_admin_carrera.py`) | 25 | ✅ |
| Pruebas automatizadas totales | 513 | ✅ |
| Validación del almacén (`etl.validar_dw`) | 99 | ✅ 99/99 |

## 1. Acceso por rol (78 de 78)

Se pidieron las 26 rutas con cada rol. Lo esperado y lo obtenido coinciden en las 78.

| Rutas | `rol_admin` | `rol_coordinador` | `rol_docente` |
|---|---|---|---|
| Inicio, Mi cuenta | 200 | 200 | 200 |
| Calificaciones, Asistencia | 200 | 200 | 200 |
| Matrícula, Reportes, Reporte personalizado | 200 | 200 | **403** |
| Vista ejecutiva, Diagnóstico, Red curricular, Dashboard, Cubo OLAP | 200 | 200 | **403** |
| Auditoría | 200 | 200 | **403** |
| Catálogos: índice, materias, secciones, estudiantes, malla | 200 | 200 | **403** |
| Catálogos: períodos, carreras, departamentos, docentes | 200 | **403** | **403** |
| Usuarios, Costos, Metas, Almacén | 200 | **403** | **403** |

## 2. Alcance de los datos (7 de 7)

| Comprobación | Resultado |
|---|---|
| Materias que ve el admin | 523 |
| Materias que ve el coordinador de Ingeniería de Sistemas | **45** |
| La exportación a CSV también viene recortada | 523 frente a **45** filas |
| El índice de catálogos no le ofrece lo que daría 403 | solo materias, secciones y estudiantes |
| Crear una materia en **otra** carrera | **rechazado** por el motor: 422, y el total sigue en 523 |
| Mensaje que ve el usuario | «Esa materia pertenece a otra carrera. Solo puedes administrar las de la tuya.» |
| Abrir una sección de otra carrera en Calificaciones | no dibuja la matriz de notas |

## 3. El coordinador opera su carrera (8 de 8)

Lo acotado no le impide trabajar: ve los 12 ciclos, **56 secciones** de su carrera en el ciclo
vigente, abre la matriz de notas, tiene el buscador por carnet, entra a Matrícula y genera un
reporte personalizado.

## 4. El recorte en el almacén

Los tableros no leen el OLTP, así que se comprobó aparte. La misma pantalla, con los dos roles:

| | admin | coordinador de carrera |
|---|---|---|
| Costo de reprobación (vista ejecutiva) | 143 325 | **38 525** |
| Hechos visibles en `fact_inscripcion` | 53 683 | **12 884** |
| Carreras visibles en `dim_carrera` | 12 | **1** |

Y con `rol_dw_carrera` adoptado **sin declarar la carrera**: **0 filas**.

## 5. Falla cerrado

Con `SET LOCAL ROLE rol_coordinador` y sin declarar `app.carrera_id`, el coordinador ve **0
filas** en las ocho tablas con seguridad por fila: `carreras`, `materias`, `estudiantes`,
`secciones`, `inscripciones`, `evaluaciones`, `calificaciones` y `asistencias`. Lo mismo en el
almacén y en la bitácora.

## 6. La bitácora

| Quién | Ve |
|---|---|
| Admin | todas las filas |
| Coordinador de la carrera del cambio | **la fila de su carrera** |
| Coordinador de otra carrera | **0** |
| Coordinador sin carrera declarada | **0** |

Y **nadie escribe**: las políticas nuevas son `FOR SELECT`, así que agregarlas no abrió la
escritura. `DELETE` y `UPDATE` sobre `auditoria.log_cambios_notas` siguen devolviendo
«permission denied» para los dos roles, **incluido el admin**.

## 7. Rendimiento

El riesgo conocido era que las políticas se ejecutaran por fila (el script 16 dejó anotado un
conteo que pasó de 4 ms a 26 s con una política escrita como función). Escritas en línea:

| Consulta | admin | coordinador |
|---|---|---|
| `count(*)` sobre 131 000 calificaciones | 32 ms | **49 ms** |

El planificador convierte la política en *hash joins*. Y medido por pantalla, el coordinador es
**más rápido** que el admin en las 14 rutas analíticas (menos datos): ninguna pasa de 0,25 s.

## 8. Lo que no se rompió

- **`etl.carga`** sigue cargando el almacén completo (53 683 hechos).
- **`etl.validar_dw`**: 99 de 99.
- **`rol_dashboard` sin adoptar el rol acotado** sigue viendo todo: Streamlit y la validación no
  cambian.
- **Las cuentas que ya existían** migraron a `rol_admin` solas. Un coordinador sin carrera no
  vería nada, y nadie podría volver a administrar.

## Decisiones y límites declarados

- **El departamento no se guarda.** Las carreras ya pertenecen a uno, así que asignar la carrera
  lo determina; guardar los dos permitiría que se contradijeran.
- **Las vistas de indicadores siguen institucionales.** Las metas lo son
  (`academico_oltp.metas_indicador`), así que el semáforo también: un coordinador ve el valor de
  su carrera frente a la meta institucional. Compararla contra una meta de toda la institución
  sería engañoso, y resolverlo bien exige metas por carrera.
- **`v_mart_departamento` se marcó `security_invoker`.** Una vista normal se evalúa con los
  permisos de su dueño, así que el recorte se podía esquivar consultándola.
- **Alcance honesto.** Protege contra errores de la aplicación. No protege contra quien controle
  la credencial de `rol_app`, que puede declarar cualquier carrera; esa credencial ya equivale a
  la aplicación entera y vive solo en el `.env`.
- **El docente no cambió.** Sus políticas son las del script 16; en las cinco tablas nuevas
  recibió `USING (true)` a propósito, para que este cambio no le altere el comportamiento.

## Defectos encontrados y corregidos durante esta validación

1. **`cerrar_acta()` rechazaba a `rol_admin`.** La comprobación de rol vive dentro de la función
   y su lista no conocía el rol nuevo: dar `EXECUTE` no alcanzaba. Lo cazaron las pruebas.
2. **La bitácora no estaba acotada.** El recorte servía para los datos y se podía esquivar
   leyendo su rastro. Corregido en el script 25.
3. **El índice de catálogos ofrecía tarjetas que devolvían 403.**
4. **El rechazo mostraba el texto crudo de PostgreSQL** («new row violates row-level security
   policy…»). Ahora se traduce, y concuerda en género con el catálogo.

## Cómo reproducirlo

```bash
./scripts/aplicar_ddl_pendiente.sh            # aplica 23, 24 y 25 si faltan
python backend/scripts/crear_usuario.py --demo --password demo1234
cd backend && python -m unittest tests.test_rol_admin_carrera -v
python -m pytest backend/tests dashboard etl -q # 513
python -m etl.validar_dw                       # 99 de 99
```
