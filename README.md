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
├── backend/                   # Sistema transaccional operacional (FastAPI)
│   ├── app/                   # Configuración, modelos, routers y plantillas
│   └── scripts/               # Utilidades de administración (alta de usuarios)
├── etl/                       # Pipelines de extracción, transformación y carga
└── dashboard/                 # Interfaz interactiva de analítica en Streamlit
```

---

## 🚀 Estado del Desarrollo (Fases)

### Fase 1: Base de Datos Operacional y Scripts de Datos
- [x] **1.1:** Definición del DDL operacional OLTP (PostgreSQL 17), esquemas, PK/FK, checks, roles y disparadores de integridad.
- [x] **1.2:** Generador de datos sintéticos realistas con Python (`Faker` + inserción por lotes masiva ~100k+ registros).
- [x] **1.3:** Modelado y carga del grafo de la malla curricular en Neo4j (Cypher: asignaturas y relaciones de prerrequisitos).
- [x] **1.4:** Pruebas de rendimiento y optimización con `EXPLAIN ANALYZE` (documentación comparativa antes/después de índices).

### Fase 2: Sistema Transaccional de Gestión (CRUD Operacional)
- [x] **2.1:** Backend y frontend liviano transaccional (FastAPI + Jinja2 + Bootstrap).
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

---

## ⚙️ Requisitos Previos e Instalación

- **Python** >= 3.11
- **PostgreSQL** 17
- **Neo4j** >= 5.x (Community, Enterprise o Neo4j Desktop)
- **Docker & Docker Compose** (Opcional, pero recomendado para levantar servicios)

---

### 🔑 1. Configuración de credenciales

Todas las credenciales del proyecto viven en un único archivo `.env` en la raíz
(no versionado). Nunca se escriben dentro del código.

```bash
cp .env.example .env
```

Edita `.env` y reemplaza los valores marcados como `cambiar_...`. Para la clave de sesión:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 📦 2. Despliegue de los motores de base de datos

```bash
# Levanta PostgreSQL 17 y Neo4j en segundo plano
docker compose up -d
```

En el **primer arranque**, PostgreSQL ejecuta automáticamente los scripts de `database/oltp/`
en orden alfabético: crea el esquema operacional, la tabla de usuarios de la aplicación y el
rol de servicio. No hay que ejecutar ningún `.sql` a mano.

> Si ya tenías el contenedor creado desde antes, los scripts de inicialización **no** se
> vuelven a ejecutar. Para reinicializar desde cero (⚠️ borra todos los datos):
> `docker compose down -v && docker compose up -d`

### 🐍 3. Dependencias de Python

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r scripts/generator/requirements.txt
```

### 🎲 4. Poblar con datos sintéticos (Fase 1.2)

```bash
python scripts/generator/02_generador_datos_sinteticos.py
python database/nosql/03_cargar_grafo_neo4j.py   # grafo curricular en Neo4j
```

Ambos scripts toman las credenciales del `.env`; ya no hay que editarlos.

### 👤 5. Crear los usuarios de la aplicación

```bash
python backend/scripts/crear_usuario.py --demo --password demo1234
```

Crea dos usuarios de prueba para entorno local: `coordinador` y `docente` (este último
requiere que el generador de datos se haya ejecutado antes). Para dar de alta usuarios
reales, sin el flag `--demo`:

```bash
python backend/scripts/crear_usuario.py --username jperez \
    --nombre "Jose Perez" --rol rol_docente --docente-id 3
```

### 🚀 6. Levantar el sistema transaccional (Fase 2)

```bash
cd backend
uvicorn app.main:app --reload
```

Disponible en `http://localhost:8000` (documentación de la API en `/api/docs`).

---

## 🔐 Modelo de seguridad de la aplicación

La autorización **no se resuelve en Python, sino en el motor de base de datos**:

1. La aplicación se conecta siempre con un rol de servicio (`rol_app`) creado con `NOINHERIT`,
   que por sí solo únicamente puede leer la tabla de usuarios.
2. Al autenticar, se recupera el rol asignado al usuario (`rol_coordinador` o `rol_docente`).
3. En cada transacción se ejecuta `SET LOCAL ROLE <rol>`, de modo que los `GRANT` definidos en
   `01_init_oltp_academico.sql` son los que autorizan o rechazan cada operación.

Consecuencias del diseño:

- Si un docente intenta una operación fuera de sus permisos, quien la rechaza es PostgreSQL
  (`permission denied`), no una validación de la interfaz.
- `NOINHERIT` hace que el sistema falle **cerrado**: si la aplicación omitiera el `SET ROLE`,
  la sesión se queda sin privilegios en lugar de acumular los de todos los roles.
- `SET LOCAL` (y no `SET`) limita el cambio a la transacción, evitando que una conexión
  reutilizada del pool arrastre el rol del usuario anterior.

---

## 🧱 Decisión de stack (Fase 2.1)

Se optó por **FastAPI + Jinja2 + Bootstrap** sobre la alternativa de Streamlit Admin:

| Criterio | FastAPI + Bootstrap | Streamlit Admin |
|---|---|---|
| Separación backend/frontend | Sí, con capa de rutas y plantillas | No, todo en un script |
| Control de sesión y roles | Middleware y dependencias propias | Limitado |
| Manejo de formularios y validación | Completo | Restringido a widgets |
| Representatividad de un OLTP real | Alta | Baja |

Streamlit se reserva para la **Fase 4 (dashboard analítico)**, donde su orientación a la
exploración de datos sí es la herramienta adecuada.
