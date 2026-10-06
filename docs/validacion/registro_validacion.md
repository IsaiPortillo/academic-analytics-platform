# Registro de validación de datos y procesos — Fases 3.3, 4.1 y 4.2

Generado automáticamente por `python -m etl.validar_dw`. No editar a mano: se regenera en cada corrida, y el historial de corridas queda en git.

- **Fecha:** 2026-10-05 14:25
- **Commit:** `14073fd`
- **Última carga del DW:** 2026-10-05 20:25 UTC, fecha de corte 2026-10-02
- **Volumen:** 36,704 hechos de inscripción, 1,500 estudiantes
- **Resultado:** 66 de 66 verificaciones correctas ✅

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
| Cruce relacional-grafo | Área de cada materia en Neo4j |
| Seguridad / Anonimización / Integridad | Permisos reales de PostgreSQL y catálogo del DW |

## Resultados

| Grupo | Verificación | Esperado | Obtenido | Estado |
|---|---|---|---|---|
| Completitud | Inscripciones → fact_inscripcion | 36704 | 36704 | ✅ OK |
| Completitud | Estudiantes → dim_estudiante | 1500 | 1500 | ✅ OK |
| Completitud | Materias → dim_materia | 16 | 16 | ✅ OK |
| Completitud | Períodos → dim_periodo | 8 | 8 | ✅ OK |
| Completitud | Docentes → dim_docente | 20 | 20 | ✅ OK |
| Completitud | Secciones → dim_seccion | 194 | 194 | ✅ OK |
| Costo | Inscripciones reprobadas (OLTP independiente vs DW) | 8020 | 8020 | ✅ OK |
| Costo | Costo de reprobación total en USD (OLTP independiente vs DW) | 802,000.00 | 802,000.00 | ✅ OK |
| Costo | Inscripciones con costo de matrícula (OLTP independiente vs DW) | 36704 | 36704 | ✅ OK |
| Costo | Costo de matrícula total en USD (OLTP independiente vs DW) | 3,670,400.00 | 3,670,400.00 | ✅ OK |
| Costo | Inscripciones con costo de repetición (OLTP independiente vs DW) | 5511 | 5511 | ✅ OK |
| Costo | Costo de repetición total en USD (OLTP independiente vs DW) | 551,100.00 | 551,100.00 | ✅ OK |
| Costo | Costo de repetición nunca supera el costo de la inscripción (filas que lo violan) | 0 | 0 | ✅ OK |
| Data mart | Suma por departamento = total (costo_matricula_materia) | 3,670,400.00 | 3,670,400.00 | ✅ OK |
| Data mart | Suma por departamento = total (costo_reprobacion) | 802,000.00 | 802,000.00 | ✅ OK |
| Data mart | Suma por departamento = total (costo_repeticion) | 551,100.00 | 551,100.00 | ✅ OK |
| Data mart | Filas del mart sin departamento | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2022-I (reporte de notas vs DW) | 989/4122 | 989/4122 | ✅ OK |
| Patrón de riesgo | 2022-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 140 | 140 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2022-II (reporte de notas vs DW) | 1015/4044 | 1015/4044 | ✅ OK |
| Patrón de riesgo | 2022-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 173 | 173 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2023-I (reporte de notas vs DW) | 1046/4160 | 1046/4160 | ✅ OK |
| Patrón de riesgo | 2023-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 168 | 168 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2023-II (reporte de notas vs DW) | 995/4092 | 995/4092 | ✅ OK |
| Patrón de riesgo | 2023-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2024-I (reporte de notas vs DW) | 1005/4153 | 1005/4153 | ✅ OK |
| Patrón de riesgo | 2024-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2024-II (reporte de notas vs DW) | 986/4175 | 986/4175 | ✅ OK |
| Patrón de riesgo | 2024-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2025-I (reporte de notas vs DW) | 977/4096 | 977/4096 | ✅ OK |
| Patrón de riesgo | 2025-I: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Sistema transaccional | Reprobadas/cerradas 2025-II (reporte de notas vs DW) | 1007/4124 | 1007/4124 | ✅ OK |
| Patrón de riesgo | 2025-II: inscripciones con nota < 6.00 y ≥ 3 ausencias (reportes vs DW, caso por caso) | 0 | 0 | ✅ OK |
| Umbrales | Reporte de asistencia y calculos.py usan el mismo umbral de faltas | mismo objeto | mismo objeto | ✅ OK |
| Umbrales | ETL usa el umbral de faltas del sistema transaccional | 3 | 3 | ✅ OK |
| Umbrales | ETL usa el umbral de aprobación del sistema transaccional | 6.0 | 6.0 | ✅ OK |
| Correlaciones | r(asistencia, nota) PostgreSQL vs pandas | +0.014623 (n=12,000) | +0.014623 (n=12,000) | ✅ OK |
| Correlaciones | r(asistencia, intento) PostgreSQL vs pandas | +0.025905 (n=12,000) | +0.025905 (n=12,000) | ✅ OK |
| Correlaciones | r(asistencia, costo) PostgreSQL vs pandas | -0.008968 (n=12,000) | -0.008968 (n=12,000) | ✅ OK |
| Correlaciones | r(nota, intento) PostgreSQL vs pandas | -0.144880 (n=32,966) | -0.144880 (n=32,966) | ✅ OK |
| Correlaciones | r(nota, costo) PostgreSQL vs pandas | -0.738186 (n=32,966) | -0.738186 (n=32,966) | ✅ OK |
| Correlaciones | r(intento, costo) PostgreSQL vs pandas | +0.111674 (n=32,966) | +0.111674 (n=32,966) | ✅ OK |
| Particiones | Suma de cohortes = total (reprobadas/cerradas) | 8020/32966 | 8020/32966 | ✅ OK |
| Particiones | Suma por turno = total | 8020/32966 | 8020/32966 | ✅ OK |
| Particiones | Turno: grupos sin valor (nulos) | 0 | 0 | ✅ OK |
| Particiones | Suma por área de la materia = total | 8020/32966 | 8020/32966 | ✅ OK |
| Particiones | Área de la materia: grupos sin valor (nulos) | 0 | 0 | ✅ OK |
| Particiones | Suma por ciclo del plan = total | 8020/32966 | 8020/32966 | ✅ OK |
| Particiones | Ciclo del plan: grupos sin valor (nulos) | 0 | 0 | ✅ OK |
| Particiones | Suma por condición laboral = total | 8020/32966 | 8020/32966 | ✅ OK |
| Particiones | Condición laboral: grupos sin valor (nulos) | 0 | 0 | ✅ OK |
| Cruce relacional-grafo | Materias del DW con el área que registra Neo4j | 16 | 16 | ✅ OK |
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

- **Cobertura de asistencia.** Solo 3 de 8 períodos tienen asistencia registrada (2022-I, 2022-II, 2023-I): 12,000 de 32,966 inscripciones cerradas. El generador sintético (scripts/generator, `LIMIT 12000`) solo creó asistencia para 12,000 inscripciones. El patrón de riesgo y las correlaciones con asistencia solo pueden observarse en esos períodos.
- **Calidad de datos del OLTP: doble inscripción.** 1,901 veces un estudiante (1,052 estudiantes distintos) quedó inscrito en dos secciones de la misma materia en el mismo período. El esquema solo impide repetir la misma sección (`uq_estudiante_seccion`), y el generador sintético elige secciones al azar. El DW trata cada inscripción por separado, que es lo correcto; esta validación compara contra los reportes por estudiante + materia + sección para no mezclarlas. Con datos reales, una restricción por (estudiante, materia, período) en el OLTP lo evitaría.
- **Asistencia y nota no se relacionan en estos datos** (r = +0.015). El generador crea la asistencia al azar, sin depender de la nota: el dashboard lo reporta correctamente como relación despreciable. Con datos reales esta relación podría aparecer; no es un error del análisis sino una propiedad de los datos sintéticos.
- **Número de intento y nota** (r = -0.145): relación débil y negativa, coherente con el generador, que resta 0.4 puntos de media a quien repite.
- **Costo y nota** (r = -0.738) es una relación por construcción: el costo de reprobación solo existe con nota < 6.00. Se usa costo_reprobacion porque costo_inscripcion es constante (todas las materias tienen 4 UV y el costo por UV es el mismo supuesto de $25.00 en todos los períodos) y su correlación no está definida.
- **La condición laboral es la variable que más separa la reprobación** (trabaja 42.3 % vs no trabaja 19.8 %), coherente con el generador, que resta 0.6 puntos de media a quien trabaja. Turno, área, ciclo del plan y cohorte no se modelan en el generador y sus diferencias son pequeñas o indistinguibles del azar.

## Cómo reproducir

```bash
python -m etl.carga        # recarga el DW desde el OLTP y Neo4j
python -m etl.validar_dw   # vuelve a validar y regenera este registro
```
