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

## 9. Metas por carrera (scripts 26 y 27) — 14 de 14 en vivo

Añadido el 2 de noviembre de 2026, con su propia auditoría contra la aplicación corriendo.

| Comprobación | Resultado |
|---|---|
| El admin entra a Metas y elige el alcance (institución o una de las 12 carreras) | ✅ |
| En alcance de carrera avisa «hereda la institucional» y muestra cuál | ✅ |
| La perspectiva del CMI y el cargo responsable solo se editan en la meta general | ✅ |
| Guardar una meta propia redirige al alcance de esa carrera y deja la general intacta | ✅ |
| «Volver a la meta institucional» quita la propia y la carrera vuelve a heredar | ✅ |
| El coordinador **no** entra a Metas (403) | ✅ |
| El coordinador ve en la base su meta y la general, **nunca la de otra carrera** | ✅ |
| El coordinador no puede escribir metas | ✅ permission denied |

**El semáforo, con una meta propia puesta a Ingeniería de Sistemas (40 000 y 15 %):**

| Alcance | Costo de reprobación | Tasa de reprobación |
|---|---|---|
| Institucional | Meta ≤ $90 000 · Desfavorable | Meta ≤ 22 % · En observación |
| Ing. Sistemas (meta propia) | Meta ≤ **$40 000** · Favorable | Meta ≤ **15 %** · Desfavorable |
| Ing. Civil (hereda) | Meta ≤ $90 000 · **sin estado** | Meta ≤ 22 % · En observación |
| Coordinador de Ing. Sistemas | Meta ≤ **$40 000** · Favorable | Meta ≤ **15 %** · Desfavorable |

Las dos filas del medio son la prueba de la regla: la carrera con meta propia **sí** evalúa el
total —la meta ya está a su escala—; la que hereda la institucional **no**, porque un subtotal no
se compara con un total institucional.

**Defecto encontrado y corregido en esta auditoría:** el coordinador de carrera veía sus propios
valores contra las metas **institucionales**, con un falso «Favorable» de 393 contra 90 000. Su
recorte viene de las políticas de fila, no del filtro de la URL, así que la vista ejecutiva no
sabía su alcance. Ahora lo deriva de su cuenta (`carrera_del_usuario`), con prueba de regresión.

**En el almacén:** 60 filas institucionales y 720 por carrera en `fact_indicador_periodo`, y el
`MERGE` sigue siendo **idempotente** (0 filas tocadas al repetirlo). Con `=` en vez de
`IS NOT DISTINCT FROM`, las filas institucionales no habrían emparejado nunca y el `MERGE` las
habría borrado e insertado en cada carga, para siempre.

**La validación del almacén pasó de 99 a 100 verificaciones**, con una nueva que comprueba lo que
sí es aditivo: que los numeradores y denominadores de las carreras sumen exactamente los
institucionales. Es la confirmación independiente de que `GROUPING SETS` calcula bien el grano.

## Decisiones y límites declarados

- **El departamento no se guarda.** Las carreras ya pertenecen a uno, así que asignar la carrera
  lo determina; guardar los dos permitiría que se contradijeran.
- **Resuelto el 2 de noviembre:** las metas pasaron a ser por carrera con la institucional de
  respaldo (sección 9). Lo que **no** se hace es derivar la institucional promediando las de las
  carreras: cuatro de los cinco indicadores son razones, y promediar razones es un promedio de
  promedios. Solo el costo de reprobación es aditivo.
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
