# Diagramas

Los diagramas son un entregable del producto tecnológico, no un adorno del documento.

| Diagrama | Qué debe mostrar | Entrega | Ticket |
|---|---|---|---|
| Modelo operacional (entidad-relación) | Las 13 tablas de `academico_oltp` y `auditoria`, con sus claves foráneas | 12 oct | SCRUM-40 |
| Arquitectura de datos | Las cuatro capas: OLTP, grafo curricular, ETL y capa analítica | 12 oct | SCRUM-40 |
| Modelo dimensional (esquema estrella) | Tabla de hechos con sus medidas, incluidas las de costo, y las dimensiones | 19 oct | SCRUM-41 |
| Malla curricular | El grafo de 16 materias y sus relaciones `:REQUIERE_APROBADA` | 19 oct | SCRUM-41 |

## De dónde sacar cada uno sin dibujarlo a mano

- **Modelo operacional**: se puede generar desde la base ya creada con pgAdmin (ERD para la base de
  datos) o con SchemaSpy, en vez de redibujar las 13 tablas. La fuente de verdad es
  `database/oltp/01_init_oltp_academico.sql`.
- **Malla curricular**: el Neo4j Browser en `http://localhost:7474` ya la dibuja; basta un
  `MATCH (m:Materia)-[r:REQUIERE_APROBADA]->(n) RETURN m, r, n` y exportar la imagen. El mismo grafo
  que consume la Fase 4.3.
- **Modelo dimensional y arquitectura**: estos sí se diseñan, porque comunican decisiones y no solo
  estructura.

Guardar en PNG o SVG, con el nombre del diagrama y sin espacios (`modelo_operacional.png`).
