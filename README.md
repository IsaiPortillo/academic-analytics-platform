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

---

## 🚀 Estado del Desarrollo (Fases)

- [x] **Fase 1.1:** Definición del DDL operacional OLTP (PostgreSQL 17), RBAC y disparadores de negocio.
- [x] **Fase 1.2:** Generador de datos sintéticos realistas con Faker y carga masiva (~100k+ registros).
- [ ] **Fase 1.3:** Modelado y carga de la red curricular en Neo4j (Cypher).
- [ ] **Fase 1.4:** Pruebas de rendimiento y optimización con `EXPLAIN ANALYZE`.
- [ ] **Fase 2:** Sistema transaccional liviano de gestión académica.
- [ ] **Fase 3:** Pipeline ETL y construcción del Data Warehouse.
- [ ] **Fase 4:** Dashboard analítico de toma de decisiones (Streamlit).
- [ ] **Fase 5:** Memoria técnica final y preparación de defensa.

---

## ⚙️ Requisitos Previos e Instalación

- **PostgreSQL** 17
- **Python** >= 3.11
- **Neo4j** Community / Enterprise

### Ejecución del Generador Sintético (Fase 1.2):
```bash
# 1. Instalar dependencias requeridas
pip install -r requirements.txt

# 2. Configurar credenciales en scripts/generator/02_generador_datos_sinteticos.py
# 3. Poblar la base de datos operacional
python scripts/generator/02_generador_datos_sinteticos.py