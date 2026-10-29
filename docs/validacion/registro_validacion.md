# Registro de validación de datos y procesos — Fases 3.3, 4.1 y 4.2

Generado automáticamente por `python -m etl.validar_dw`. No editar a mano: se regenera en cada corrida, y el historial de corridas queda en git.

- **Fecha:** 2026-10-29 21:50
- **Commit:** `1e344c9`
- **Última carga del DW:** 2026-10-29 21:48 UTC, fecha de corte 2026-10-29
- **Volumen:** 53,683 hechos de inscripción, 2,303 estudiantes
- **Resultado:** 99 de 99 verificaciones correctas ✅

## Qué se verifica y contra qué

| Grupo | Fuente de comparación |
|---|---|
| Completitud | Conteos del esquema operacional (`academico_oltp`) |
| Costo | SQL independiente sobre el OLTP, escrito en este script (no reutiliza el ETL): reprobación, matrícula y repetición |
| Data mart | El corte por departamento reparte exactamente cada medida de costo |
| Sistema transaccional | Las mismas funciones de los reportes del coordinador (SCRUM-10) |
| Patrón de riesgo | Intersección de los reportes de notas (SCRUM-10) y asistencia (SCRUM-25), caso por caso |
| Umbrales | Identidad de las constantes en `backend/app/calculos.py`, el reporte y el ETL |
| Correlaciones | `corr()` de PostgreSQL (lo que muestra el dashboard) contra pandas |
| Particiones | Cada segmentación del dashboard debe repartir exactamente el total |
| Indicadores | La vista de cálculo del DW contra `app/indicadores.py`, y lo guardado por el MERGE contra la vista |
| Cruce relacional-grafo | Área de cada materia en Neo4j |
| Seguridad / Anonimización / Integridad | Permisos reales de PostgreSQL y catálogo del DW |

## Resultados

| Grupo | Verificación | Esperado | Obtenido | Estado |
|---|---|---|---|---|
| Completitud | Inscripciones → fact_inscripcion | 53683 | 53683 | ✅ OK |
| Completitud | Estudiantes → dim_estudiante | 2303 | 2303 | ✅ OK |
| Completitud | Materias → dim_materia | 523 | 523 | ✅ OK |
| Completitud | Períodos → dim_periodo | 12 | 12 | ✅ OK |
| Completitud | Docentes → dim_docente | 105 | 105 | ✅ OK |
| Completitud | Secciones → dim_seccion | 4482 | 4482 | ✅ OK |
| Costo | Inscripciones reprobadas (OLTP independiente vs DW) | 11006 | 11006 | ✅ OK |
| Costo | Costo de reprobación total en USD (OLTP independiente vs DW) | 1,096,900.00 | 1,096,900.00 | ✅ OK |
| Costo | Inscripciones con costo de matrícula (OLTP independiente vs DW) | 53683 | 53683 | ✅ OK |
| Costo | Costo de matrícula total en USD (OLTP independiente vs DW) | 5,375,975.00 | 5,375,975.00 | ✅ OK |
| Costo | Inscripciones con costo de repetición (OLTP independiente vs DW) | 8605 | 8605 | ✅ OK |
| Costo | Costo de repetición total en USD (OLTP independiente vs DW) | 857,775.00 | 857,775.00 | ✅ OK |
| Costo | Costo de repetición nunca supera el costo de la inscripción (filas que lo violan) | 0 | 0 | ✅ OK |
| Data mart | Suma por departamento = total (costo_matricula_materia) | 5,375,975.00 | 5,375,975.00 | ✅ OK |
| Data mart | Suma por departamento = total (costo_reprobacion) | 1,096,900.00 | 1,096,900.00 | ✅ OK |
| Data mart | Suma por departamento = total (costo_repeticion) | 857,775.00 | 857,775.00 | ✅ OK |
| Data mart | Filas del mart sin departamento | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2021-I (reporte de notas vs DW) | 400/1697 | 400/1697 | ✅ OK |
| Patrón de riesgo | 2021-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2021-II (reporte de notas vs DW) | 421/1565 | 421/1565 | ✅ OK |
| Patrón de riesgo | 2021-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2022-I (reporte de notas vs DW) | 767/3112 | 767/3112 | ✅ OK |
| Patrón de riesgo | 2022-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2022-II (reporte de notas vs DW) | 766/2872 | 766/2872 | ✅ OK |
| Patrón de riesgo | 2022-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2023-I (reporte de notas vs DW) | 1115/4312 | 1115/4312 | ✅ OK |
| Patrón de riesgo | 2023-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2023-II (reporte de notas vs DW) | 1059/4023 | 1059/4023 | ✅ OK |
| Patrón de riesgo | 2023-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2024-I (reporte de notas vs DW) | 1281/5262 | 1281/5262 | ✅ OK |
| Patrón de riesgo | 2024-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2024-II (reporte de notas vs DW) | 1189/4915 | 1189/4915 | ✅ OK |
| Patrón de riesgo | 2024-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2025-I (reporte de notas vs DW) | 1358/6027 | 1358/6027 | ✅ OK |
| Patrón de riesgo | 2025-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 236 | 236 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2025-II (reporte de notas vs DW) | 1208/5518 | 1208/5518 | ✅ OK |
| Patrón de riesgo | 2025-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 214 | 214 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2026-I (reporte de notas vs DW) | 1442/6480 | 1442/6480 | ✅ OK |
| Patrón de riesgo | 2026-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 278 | 278 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2026-II (reporte de notas vs DW) | 0/0 | 0/0 | ✅ OK |
| Patrón de riesgo | 2026-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Umbrales | Reporte de asistencia y calculos.py usan el mismo umbral de faltas | mismo objeto | mismo objeto | ✅ OK |
| Umbrales | ETL usa el umbral de faltas del sistema transaccional | 3 | 3 | ✅ OK |
| Umbrales | ETL usa el umbral de aprobación del sistema transaccional | 6.0 | 6.0 | ✅ OK |
| Correlaciones | r(asistencia, nota) PostgreSQL vs pandas | +0.300873 (n=18,025) | +0.300873 (n=18,025) | ✅ OK |
| Correlaciones | r(asistencia, intento) PostgreSQL vs pandas | -0.170107 (n=18,025) | -0.170107 (n=18,025) | ✅ OK |
| Correlaciones | r(asistencia, costo) PostgreSQL vs pandas | -0.217408 (n=18,025) | -0.217408 (n=18,025) | ✅ OK |
| Correlaciones | r(nota, intento) PostgreSQL vs pandas | -0.478121 (n=45,783) | -0.478121 (n=45,783) | ✅ OK |
| Correlaciones | r(nota, costo) PostgreSQL vs pandas | -0.747707 (n=45,783) | -0.747707 (n=45,783) | ✅ OK |
| Correlaciones | r(intento, costo) PostgreSQL vs pandas | +0.456534 (n=45,783) | +0.456534 (n=45,783) | ✅ OK |
| Particiones | Suma de cohortes = total (reprobadas/cerradas) | 11006/45783 | 11006/45783 | ✅ OK |
| Particiones | Suma por turno = total | 11006/45783 | 11006/45783 | ✅ OK |
| Particiones | Turno: grupos sin valor (nulos) | 0 | 0 | ✅ OK |
| Particiones | Suma por área de la materia = total | 11006/45783 | 11006/45783 | ✅ OK |
| Particiones | Área de la materia: grupos sin valor (nulos) | 0 | 0 | ✅ OK |
| Particiones | Suma por ciclo del plan = total | 11006/45783 | 11006/45783 | ✅ OK |
| Particiones | Ciclo del plan: grupos sin valor (nulos) | 0 | 0 | ✅ OK |
| Particiones | Suma por condición laboral = total | 11006/45783 | 11006/45783 | ✅ OK |
| Particiones | Condición laboral: grupos sin valor (nulos) | 0 | 0 | ✅ OK |
| Indicadores | Vista de cálculo del DW = fórmulas de la app (KPI × período) | 60 | 60 | ✅ OK |
| Indicadores | Resultados guardados por el MERGE = vista de cálculo | 0 | 0 | ✅ OK |
| Cruce relacional-grafo | Materias de la malla con el área que registra Neo4j | 45 | 45 | ✅ OK |
| Cruce relacional-grafo | Materias sin nodo en el grafo rotuladas «Sin área en la malla» | 478 | 478 | ✅ OK |
| Red curricular | Relaciones de prerrequisito en el DW frente a las de Neo4j | 39 | 39 | ✅ OK |
| Red curricular | Relaciones que están en un lado y no en el otro (diferencia simétrica) | 0 | 0 | ✅ OK |
| Red curricular | La malla del DW es un grafo sin ciclos | True | True | ✅ OK |
| Red curricular | Materias que se exigen a sí mismas | 0 | 0 | ✅ OK |
| Red curricular | Métricas de dim_materia (Neo4j) distintas de las recalculadas desde bridge_prerrequisito | [] | [] | ✅ OK |
| Red curricular | Umbral de cuello de botella: pantalla frente al ETL | 0.25 | 0.25 | ✅ OK |
| Red curricular | Materias cuyo es_cuello_botella no corresponde a su índice de bloqueo | 0 | 0 | ✅ OK |
| Red curricular | Costo de reprobación del cruce por materia frente al total de los hechos | 1096900.0 | 1096900.0 | ✅ OK |
| Red curricular | Materias del cruce frente a materias de la malla | 523 | 523 | ✅ OK |
| Red curricular | rol_dashboard lee las relaciones de la malla (lo que ve la pantalla) | 39 | 39 | ✅ OK |
| Cubo OLAP | ROLLUP periodo × ciclo: una sola fila de total general | 1 | 1 | ✅ OK |
| Cubo OLAP | ROLLUP periodo × ciclo: inscripciones con nota final del total frente a los hechos | 45783 | 45783 | ✅ OK |
| Cubo OLAP | ROLLUP periodo × ciclo: reprobados del total frente a los hechos | 11006 | 11006 | ✅ OK |
| Cubo OLAP | ROLLUP periodo × ciclo: costo de reprobación del total frente a los hechos | 1096900.0 | 1096900.0 | ✅ OK |
| Cubo OLAP | ROLLUP periodo × ciclo: la suma del detalle es el total (no se pierde ninguna fila) | 45783 | 45783 | ✅ OK |
| Cubo OLAP | CUBE area × turno × cohorte: una sola fila de total general | 1 | 1 | ✅ OK |
| Cubo OLAP | CUBE area × turno × cohorte: inscripciones con nota final del total frente a los hechos | 45783 | 45783 | ✅ OK |
| Cubo OLAP | CUBE area × turno × cohorte: reprobados del total frente a los hechos | 11006 | 11006 | ✅ OK |
| Cubo OLAP | CUBE area × turno × cohorte: costo de reprobación del total frente a los hechos | 1096900.0 | 1096900.0 | ✅ OK |
| Cubo OLAP | CUBE area × turno × cohorte: la suma del detalle es el total (no se pierde ninguna fila) | 45783 | 45783 | ✅ OK |
| Dashboard estratégico | Inscripciones con nota final sumadas por ciclo del plan frente a los hechos | 45783 | 45783 | ✅ OK |
| Dashboard estratégico | Reprobados sumados por ciclo del plan frente a los hechos | 11006 | 11006 | ✅ OK |
| Seguridad | rol_dashboard NO puede leer academico_oltp | permiso denegado | permiso denegado | ✅ OK |
| Seguridad | rol_dashboard NO puede escribir en dw_academico | permiso denegado | permiso denegado | ✅ OK |
| Anonimización | carnet_hash con formato distinto de SHA-256 en el DW | 0 | 0 | ✅ OK |
| Anonimización | Columnas con datos personales en dim_estudiante | [] | [] | ✅ OK |
| Integridad | CHECK del patrón de riesgo activo en el DW | 1 | 1 | ✅ OK |
| Integridad | CHECK de costo_repeticion activo en el DW | 1 | 1 | ✅ OK |
| Integridad | Hechos sin sección o sin docente (llaves nulas) | 0 | 0 | ✅ OK |
| Integridad | Llaves de sección y docente exigidas NOT NULL por el DDL | 2 | 2 | ✅ OK |
| Integridad | Hechos cuya sección o docente difiere del OLTP | 0 | 0 | ✅ OK |
| Anonimización | Columnas con datos personales o código institucional en dim_docente | [] | [] | ✅ OK |
| Seguridad | Tablas de dw_academico que rol_etl puede escribir (privilegios del catálogo) | [] | [] | ✅ OK |
| Seguridad | Privilegios de rol_dw_carga sobre academico_oltp (esquema + tablas, catálogo) | 0 | 0 | ✅ OK |
| Seguridad | rol_etl (lee el OLTP) NO puede escribir en dw_academico | permiso denegado | permiso denegado | ✅ OK |
| Seguridad | rol_dw_carga (escribe el DW) NO puede leer academico_oltp | permiso denegado | permiso denegado | ✅ OK |

## Observaciones sobre los datos

No son fallas: son propiedades de los datos que la memoria debe declarar al interpretar los resultados.

- **Cobertura de asistencia.** Solo 3 de 12 períodos tienen asistencia registrada (2025-I, 2025-II, 2026-I): 18,025 de 45,783 inscripciones cerradas. El generador sintético (scripts/generator, `LIMIT 12000`) solo creó asistencia para 12,000 inscripciones. El patrón de riesgo y las correlaciones con asistencia solo pueden observarse en esos períodos.
- **Calidad de datos del OLTP: doble inscripción.** 0 veces un estudiante (0 estudiantes distintos) quedó inscrito en dos secciones de la misma materia en el mismo período. El esquema solo impide repetir la misma sección (`uq_estudiante_seccion`), y el generador sintético elige secciones al azar. El DW trata cada inscripción por separado, que es lo correcto; esta validación compara contra los reportes por estudiante + materia + sección para no mezclarlas. Con datos reales, una restricción por (estudiante, materia, período) en el OLTP lo evitaría.
- **Asistencia y nota no se relacionan en estos datos** (r = +0.301). El generador crea la asistencia al azar, sin depender de la nota: el dashboard lo reporta correctamente como relación despreciable. Con datos reales esta relación podría aparecer; no es un error del análisis sino una propiedad de los datos sintéticos.
- **Número de intento y nota** (r = -0.478): relación débil y negativa, coherente con el generador, que resta 0.4 puntos de media a quien repite.
- **Costo y nota** (r = -0.748) es una relación por construcción: el costo de reprobación solo existe con nota < 6.00. Se usa costo_reprobacion porque costo_inscripcion es constante (todas las materias tienen 4 UV y el costo por UV es el mismo supuesto de $25.00 en todos los períodos) y su correlación no está definida.
- **La condición laboral es la variable que más separa la reprobación** (trabaja 33.3 % vs no trabaja 21.1 %), coherente con el generador, que resta 0.6 puntos de media a quien trabaja. Turno, área, ciclo del plan y cohorte no se modelan en el generador y sus diferencias son pequeñas o indistinguibles del azar.

## Cómo reproducir

```bash
python -m etl.carga        # recarga el DW desde el OLTP y Neo4j
python -m etl.validar_dw   # vuelve a validar y regenera este registro
```
