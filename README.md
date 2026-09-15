# Plataforma de Gestión Académica y Analítica de Rendimiento Estudiantil

Sistema integral de analítica de datos e inteligencia de negocios orientado a la optimización de procesos académicos, detección temprana de deserción y análisis de impacto curricular en educación superior.

---

## 📌 Contexto del Proyecto
Proyecto de graduación desarrollado en el marco del Curso de Especialización en **Administración de Bases de Datos e Inteligencia de Negocios** de la Universidad de El Salvador (Facultad Multidisciplinaria Oriental).

El proyecto aborda la brecha entre los sistemas operacionales transaccionales y la analítica estratégica, integrando modelos relacionales (OLTP), modelado en grafos (NoSQL) para mallas curriculares, bodegas de datos (OLAP) y visualización interactiva.

---

## 🏛️ Arquitectura Técnica

El sistema se compone de cuatro capas fundamentales:

1. **Capa Operacional (OLTP):**
   - **Motor:** PostgreSQL 17.
   - **Alcance:** Control de planes de estudio, matrículas, secciones, evaluaciones, calificaciones y asistencias, bajo esquemas dedicados (`academico_oltp`, `auditoria`), políticas RBAC y triggers de integridad.
2. **Capa NoSQL (Grafo Curricular):**
   - **Motor:** Neo4j.
   - **Alcance:** Modelado de dependencias, prerrequisitos y cálculo de asignaturas críticas / cuello de botella mediante algoritmos de grafos.
3. **Capa de Integración y Procesamiento (ETL):**
   - **Tecnología:** Python (Pandas, SQLAlchemy, Neo4j Driver).
   - **Alcance:** Extracción, anonimización (SHA-256), transformación, cruce relacional-grafo y carga en el Data Warehouse.
4. **Capa Analítica y Visualización (OLAP / BI):**
   - **Almacenamiento:** Modelo estrella en esquema dimensional (`dw_academico`).
   - **Dashboard:** Streamlit (KPIs ejecutivos, matrices de correlación, alertas de deserción y visualización de redes curriculares).

---

## 📂 Estructura del Repositorio

```text
academic-analytics-platform/
├── docs/                      # Documentación académica, diagramas y memorias
│   ├── diagramas/
│   └── memoria/
├── database/                  # Definición de persistencia y migraciones
│   ├── oltp/                  # Scripts DDL, triggers y roles operacionales
│   ├── nosql/                 # Scripts Cypher y esquemas de grafo
│   └── dw/                    # DDL del modelo dimensional (Data Mart)
├── scripts/                   # Generación de datos sintéticos y benchmarking
│   ├── generator/
│   └── benchmark/
├── etl/                       # Pipelines de extracción, transformación y carga
└── dashboard/                 # Interfaz interactiva de analítica en Streamlit