# Memoria académica

Los 21 capítulos exigidos, y en qué entrega va cada uno.

| # | Capítulo | Entrega |
|---|---|---|
| 1 | Portada | 23 oct |
| 2 | Resumen y palabras clave (abstract y keywords) | 23 oct |
| 3 | Glosario | 23 oct |
| 4 | Introducción | 5 oct |
| 5 | Planteamiento del problema | 5 oct |
| 6 | Objetivos | 5 oct |
| 7 | Marco conceptual y tecnológico | 5 oct |
| 8 | Metodología | 12 oct |
| 9 | Análisis y diseño de la solución | 12 oct |
| 10 | Arquitectura de datos | 12 oct |
| 11 | Diseño e implementación del sistema operacional | 12 oct |
| 12 | Diseño e implementación de la base de datos | 19 oct |
| 13 | Procesos ETL e integración de datos | 19 oct |
| 14 | Modelo dimensional y data warehouse | 19 oct |
| 15 | Indicadores y análisis de los dashboards | 23 oct |
| 16 | Análisis: evaluación de rendimiento y optimización | 23 oct |
| 17 | Resultados y discusión | 23 oct |
| 18 | Conclusiones | 23 oct |
| 19 | Recomendaciones | 23 oct |
| 20 | Referencias bibliográficas | continuo |
| 21 | Anexos | continuo |

## Material del repositorio que alimenta cada capítulo

No hay que redactar desde cero: buena parte ya está construida, verificada y documentada.

| Capítulo | De dónde sale |
|---|---|
| 7. Marco tecnológico | Sección «Decisiones de stack» del [README](../../README.md): FastAPI frente a Streamlit, y Neo4j frente a MongoDB |
| 10. Arquitectura de datos | `docker-compose.yml` y la estructura del repositorio |
| 11. Sistema operacional | `database/oltp/01_init_oltp_academico.sql`, el modelo de seguridad del README y `backend/` |
| 12. Base de datos | Los scripts de `database/oltp/`, incluido el catálogo de costos (`08_`) |
| 13. Procesos ETL | `etl/` y la comprobación ejecutable `python -m etl.verificar_conexiones` |
| 14. Modelo dimensional | `database/dw/` (Fase 3.3) |
| 16. Rendimiento y optimización | `scripts/benchmark/04_explain_analyze_benchmarks.sql`, con los `EXPLAIN ANALYZE` de la Fase 1.4 |

## Dos cosas que conviene tener listas para la defensa

1. **El modelo de seguridad es demostrable en vivo**: `SET ROLE rol_docente` seguido de un `DELETE`
   que PostgreSQL rechaza. La autorización la resuelve el motor, no el código de la aplicación.
2. **El costo por unidad valorativa sembrado es un supuesto paramétrico**, no una cifra oficial de
   la UES. Está declarado como tal en la columna `fuente` de `academico_oltp.costos_uv`. Antes de la
   defensa hay que sustituirlo por el dato oficial o declararlo como supuesto en la memoria,
   explicando el criterio. Presentarlo como dato institucional no es defendible.
