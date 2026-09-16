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
```

---

## 🚀 Estado del Desarrollo (Fases)

### Fase 1: Base de Datos Operacional y Scripts de Datos
- [x] **1.1:** Definición del DDL operacional OLTP (PostgreSQL 17), esquemas, PK/FK, checks, roles y disparadores de integridad.
- [x] **1.2:** Generador de datos sintéticos realistas con Python (`Faker` + inserción por lotes masiva ~100k+ registros).
- [ ] **1.3:** Modelado y carga del grafo de la malla curricular en Neo4j (Cypher: asignaturas y relaciones de prerrequisitos).
- [ ] **1.4:** Pruebas de rendimiento y optimización con `EXPLAIN ANALYZE` (documentación comparativa antes/después de índices).

### Fase 2: Sistema Transaccional de Gestión (CRUD Operacional)
- [ ] **2.1:** Backend y frontend liviano transaccional (FastAPI + Bootstrap o Streamlit Admin).
- [ ] **2.2:** Módulos de matrícula, registro de calificaciones, control de asistencia y reportes operacionales.

### Fase 3: Ingeniería de Datos (ETL y Data Warehouse)
- [ ] **3.1:** Conexión y extracción híbrida (SQLAlchemy para PostgreSQL y driver oficial Neo4j).
- [ ] **3.2:** Pipeline de extracción, anonimización (SHA-256), limpieza de datos y cálculo de métricas de grafo.
- [ ] **3.3:** Diseño del modelo dimensional estrella (`dw_academico`) y carga incremental/controlada a hechos y dimensiones.

### Fase 4: Dashboard Analítico e Inteligencia de Negocios (Streamlit)
- [ ] **4.1:** Vista ejecutiva con métricas y KPIs clave interactivos filtrados por ciclo y cátedra.
- [ ] **4.2:** Matriz de correlaciones, análisis de rendimiento por cohorte y módulo de alerta temprana de deserción.
- [ ] **4.3:** Visualización interactiva de la red curricular (PyVis / NetworkX) y reporte de asignaturas críticas/cuellos de botella.

### Fase 5: Memoria Académica y Preparación de la Defensa
- [ ] **5.1:** Redacción del informe final estructurado bajo los 21 capítulos exigidos por los lineamientos de la UES (FMO).
- [ ] **5.2:** Batería de consultas analíticas y justificación técnica de arquitectura para la defensa ante jurado.
- [ ] **5.3:** Estandarización final del repositorio Git (README, diagramas de arquitectura, contenedores Docker y manual de despliegue).

---

## ⚙️ Requisitos Previos e Instalación

- **PostgreSQL** 17
- **Python** >= 3.11
- **Neo4j** Community / Enterprise

### Ejecución del Generador Sintético (Fase 1.2)

```bash
# 1. Instalar dependencias requeridas
pip install -r requirements.txt

# 2. Configurar credenciales en scripts/generator/02_generador_datos_sinteticos.py
# 3. Poblar la base de datos operacional
python scripts/generator/02_generador_datos_sinteticos.py
