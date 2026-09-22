# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: two authenticated staff roles — `rol_coordinador` (academic coordinator/administrator) and `rol_docente` (teaching staff) — who log into a FastAPI/Jinja2 web app whose authorization is enforced at the PostgreSQL level via `SET LOCAL ROLE`. A student-facing surface (e.g. students viewing their own grades/attendance) is a confirmed future audience, not yet built or designed.

## Product Purpose

Academic analytics and business-intelligence platform built as a graduation capstone (Curso de Especialización en Administración de Bases de Datos e Inteligencia de Negocios, Universidad de El Salvador — Facultad Multidisciplinaria Oriental) that closes the gap between operational transactional data (OLTP) and strategic/curricular analytics: early dropout-risk detection and curriculum impact analysis, by combining a relational OLTP core, a Neo4j curriculum-dependency graph, an ETL pipeline, and an OLAP/BI dashboard.

Success spans two horizons that must both be satisfied, not traded off against each other: (1) passing the thesis defense (jurado) with a fully demonstrable system across the five README-defined phases, and (2) remaining viable for real institutional adoption afterward. Durability, maintainability, and real data volumes matter beyond the one-off demo.

## Positioning

Authorization is resolved in the database, not in application code: the app always connects as a `NOINHERIT` service role (`rol_app`) that can only read the users table; every transaction runs `SET LOCAL ROLE <rol>` so PostgreSQL's own `GRANT`s (defined in `01_init_oltp_academico.sql`) accept or reject each operation. This fails closed by construction — a competing system that merely checks permissions in application code could not truthfully make the same guarantee. The four-layer architecture (OLTP/Postgres, curriculum graph/Neo4j, ETL, OLAP-BI/Streamlit) is a deliberate mechanism for turning transactional academic records into curricular-bottleneck detection and dropout early-warning that a purely relational or purely dashboard-only system would not provide.

## Operating Context

- Deployed via Docker Compose: PostgreSQL 17 (`academico_postgres`) and Neo4j 5.x (`academico_neo4j`); first boot auto-runs `database/oltp/*.sql` in alphabetical order.
- Backend: FastAPI + Jinja2 + Bootstrap, run with `uvicorn app.main:app --reload`, served at `http://localhost:8000` (API docs at `/api/docs`).
- Session middleware authenticates users; every DB transaction executes `SET LOCAL ROLE` before touching data.
- Synthetic data generated with Faker (`scripts/generator/02_generador_datos_sinteticos.py`, ~100k+ rows) and loaded into the Neo4j curriculum graph (`database/nosql/03_cargar_grafo_neo4j.py`).
- ETL (`etl/`) and the Streamlit analytics dashboard (`dashboard/`) exist as early-stage scaffolding (Fases 3–4 of the roadmap) and are not yet functionally complete.
- Five-phase roadmap: (1) operational DB + synthetic data + curriculum graph — done; (2) transactional CRUD system (matrícula, calificaciones, asistencia, reportes) — in progress, matrícula module furthest along; (3) ETL + data warehouse — pending; (4) Streamlit BI dashboard (KPIs, dropout alerts, curriculum network viz) — pending; (5) academic memoir/thesis writeup + defense prep — pending.
- The final deliverable must also satisfy the university's 21-chapter thesis-report format (UES-FMO guidelines) and a live jury defense demonstrating the security model documented in the README.

## Capabilities and Constraints

- Confirmed: matrícula, calificaciones, asistencia, and reportes modules (Fase 2.2) are scaffolded as routers but largely placeholder (`placeholder.html`) pending full CRUD implementation.
- Confirmed: DB-enforced RBAC is the security mechanism — authorization logic must never move into application code.
- Confirmed: all data is synthetic (Faker-generated) — real student PII must never enter the system.
- Open/undecided: exact scope and UI of the future student-facing surface (read-only grades/attendance access has been raised, not designed).
- Open/undecided: production hosting/infrastructure target for real institutional use beyond local Docker Compose.

## Brand Commitments

Project name: "Plataforma de Gestión Académica y Analítica de Rendimiento Estudiantil," produced for Universidad de El Salvador, Facultad Multidisciplinaria Oriental (UES-FMO). No logo or visual-identity assets confirmed yet.

## Evidence on Hand

No real user data, testimonials, or case studies exist and none should be fabricated — all current data is synthetic (Faker-generated academic records, ~100k+ rows). No production deployment history yet.

## Product Principles

1. Authorization lives in the database, never in application code — every feature must preserve fail-closed RBAC via `SET LOCAL ROLE`.
2. Treat the thesis defense and real institutional adoption as two success criteria to satisfy simultaneously — avoid throwaway demo-only shortcuts.
3. Never use or fabricate real student data; all seed/demo data stays synthetic.
4. Curriculum and performance analytics (dropout risk, curricular bottlenecks) are the differentiating value, not CRUD alone — features should trace back to that analytic purpose.
5. Spanish is the working language throughout the UI; do not introduce English copy without an explicit decision.

## Accessibility & Inclusion

No formal accessibility standard has been mandated by the university; none confirmed at this time.
