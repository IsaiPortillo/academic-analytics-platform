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
   - **Dashboard:** dentro de la misma aplicación web (FastAPI + Jinja2 + Tailwind), leyendo solo el Data Warehouse con un rol propio: KPIs ejecutivos, patrones de abandono observados y visualización de la red curricular.

Backend transaccional (Fase 2): **FastAPI + Jinja2 + Tailwind CSS**, con autorización resuelta en PostgreSQL — ver [Modelo de seguridad](#modelo-de-seguridad-de-la-aplicación) más abajo.

---

## 📂 Estructura del Repositorio

```text
academic-analytics-platform/
├── PRODUCT.md                 # Contexto de producto (usuarios, propósito, alcance)
├── DESIGN.md                  # Sistema de diseño de la interfaz (tokens, componentes)
├── docker-compose.yml         # PostgreSQL 17 + Neo4j, con init automático de database/oltp
├── .env.example                # Plantilla de variables de entorno (copiar a .env)
├── docs/                      # Documentación académica (ver docs/README.md)
│   ├── diagramas/              # Modelo operacional, arquitectura y esquema dimensional
│   └── memoria/                 # Los 21 capítulos y el calendario de entregas
├── database/                  # Definición de persistencia y migraciones
│   ├── oltp/                  # Scripts de inicialización (se auto-ejecutan): OLTP, roles,
│   │                           #   costos y el DW (10 a 14: esquema estrella, roles dashboard y carga)
│   │                           #   (el DW va aquí y no en database/dw/: ver nota del script 10)
│   └── nosql/                 # Script de carga (Python) y consultas Cypher del grafo
├── scripts/                   # Utilidades de datos y de desarrollo
│   ├── generator/              # Generador de datos sintéticos (Fase 1.2)
│   ├── benchmark/               # Benchmarks EXPLAIN ANALYZE (Fase 1.4)
│   └── setup-tailwind.sh       # Descarga el CLI de Tailwind y compila los estilos
├── backend/                   # Sistema transaccional operacional (FastAPI)
│   ├── app/                   # Configuración, modelos, routers y plantillas
│   │   ├── routers/            # matricula, calificaciones, asistencia, reportes, auth
│   │   ├── templates/          # Jinja2 (base.html + un template por módulo)
│   │   └── static/src/         # input.css (tokens Tailwind) -> se compila a static/app.css
│   ├── app/dw.py               # Fase 4: consultas al DW con rol_dashboard (sin acceso al OLTP)
│   ├── app/indicadores.py      # Fase 4: definición de los KPIs y su interpretación en texto
│   ├── app/indicadores_diagnostico.py  # Fase 4.2: lecturas diagnósticas y pruebas estadísticas
│   ├── app/verificar_dw.py     # Demuestra que la vista ejecutiva no puede leer el OLTP
│   ├── tests/                  # Pruebas de los KPIs (sin base de datos)
│   └── scripts/                # Utilidades de administración (alta de usuarios)
├── etl/                       # Pipelines de extracción, transformación y carga — Fase 3
│   ├── config.py               # Credenciales del ETL (rol_etl lee; rol_dw_carga escribe el DW)
│   ├── conexiones.py           # Conexión híbrida PostgreSQL + Neo4j (punto único)
│   ├── verificar_conexiones.py # Comprobación de conectividad y de solo-lectura
│   ├── extraccion.py           # Extracción de entidades OLTP (columnas explícitas)
│   ├── grafo.py                # Métricas de grafo y cuellos de botella (Cypher)
│   ├── transformacion.py       # Reglas de limpieza y enriquecimiento
│   ├── anonimizacion.py        # Verificación de que nada identificable sale al DW
│   ├── pipeline.py             # Orquestador: python -m etl.pipeline
│   ├── verificar_pipeline.py   # Nota = SCRUM-10 y bloqueo de fugas, en vivo
│   ├── carga.py                # Carga del DW dw_academico: python -m etl.carga
│   ├── validar_dw.py           # Validación entre capas → docs/validacion/registro_validacion.md
│   ├── tests/                  # Pruebas de las reglas (unittest, sin base de datos)
│   └── staging/                # Salida del pipeline (no versionada)
├── dashboard/                 # Vista ejecutiva en Streamlit — SCRUM-44 (solo lee dw_academico)
│   ├── app.py                  # streamlit run dashboard/app.py
│   ├── config.py               # DASHBOARD_DB_* desde .env (rol_dashboard, sin credenciales del backend)
│   ├── requirements.txt        # streamlit, pandas, sqlalchemy, psycopg2, pydantic-settings
│   └── tests/                  # Pruebas de la configuración
└── .streamlit/config.toml     # Streamlit: solo 127.0.0.1, tema carmesí, sin telemetría
```

---

## 📚 Documentación adicional

- **[Recorrido del sistema](docs/recorrido_del_sistema.md)** — cómo probar el proyecto
  completo de punta a punta, con la salida real de cada comando, lo que hoy no funciona y
  un guion de defensa de 10 minutos. Es el mejor punto de partida para entender el
  proyecto o para incorporarse a él.
- **[`PRODUCT.md`](PRODUCT.md)** — quiénes son los usuarios, qué resuelve el producto, y qué principios no deben romperse al agregar una funcionalidad (p. ej. "la autorización nunca se mueve a Python").
- **[`DESIGN.md`](DESIGN.md)** — el sistema de diseño de la interfaz: paleta, tipografía, y el catálogo de componentes Tailwind (`.btn-save`, `.badge-danger`, `.card`, …) usados en todas las plantillas.

---

## 🚀 Estado del Desarrollo (Fases)

### Fase 1: Base de Datos Operacional y Scripts de Datos
- [x] **1.1:** Definición del DDL operacional OLTP (PostgreSQL 17), esquemas, PK/FK, checks, roles y disparadores de integridad.
- [x] **1.2:** Generador de datos sintéticos realistas con Python (`Faker` + inserción por lotes masiva ~100k+ registros).
- [x] **1.3:** Modelado y carga del grafo de la malla curricular en Neo4j (Cypher: asignaturas y relaciones de prerrequisitos).
- [x] **1.4:** Pruebas de rendimiento y optimización con `EXPLAIN ANALYZE` (documentación comparativa antes/después de índices).

### Fase 2: Sistema Transaccional de Gestión (CRUD Operacional)
- [x] **2.1:** Backend y frontend liviano transaccional (FastAPI + Jinja2 + Tailwind CSS).
- **2.2:** Módulos operacionales:
  - [x] Matrícula (SCRUM-7) — inscribir y retirar estudiantes de secciones.
  - [x] Registro de calificaciones (SCRUM-8) — evaluaciones ponderadas y notas por sección.
  - [x] Control de asistencia (SCRUM-9) — asistencia por sesión y resumen de faltas.
  - [ ] Reportes operacionales (SCRUM-10) — notas finales y asistencia acumulada.

### Fase 3: Ingeniería de Datos (ETL y Data Warehouse)
- [x] **3.1:** Conexión y extracción híbrida (SQLAlchemy para PostgreSQL y driver oficial Neo4j).
- [x] **3.2:** Pipeline de extracción, anonimización (SHA-256), limpieza de datos y cálculo de métricas de grafo.
- [x] **3.3:** Diseño del modelo dimensional estrella (`dw_academico`) y carga incremental/controlada a hechos y dimensiones.

### Fase 4: Dashboard Analítico e Inteligencia de Negocios
- [x] **4.1:** Vista ejecutiva con los KPIs de costo y rendimiento, filtrados por período, carrera y departamento.
- [x] **4.2:** Matriz de correlaciones, análisis por cohorte e identificación de los estudiantes que presentan el patrón de riesgo observado.
- [ ] **4.3:** Visualización interactiva de la red curricular (PyVis / NetworkX) y reporte de asignaturas críticas/cuellos de botella, cruzado con el costo.

> **Alcance analítico:** el proyecto se limita a los niveles **descriptivo** («¿qué ocurrió?») y
> **diagnóstico** («¿por qué ocurrió?»). Predictivo y prescriptivo quedan fuera. Por eso el punto
> 4.2 identifica patrones de riesgo ya observados en datos históricos y no pronostica quién va a
> desertar: son cosas distintas, y solo la primera es inteligencia de negocios.

### Fase 5: Memoria Académica y Preparación de la Defensa
- [ ] **5.1:** Redacción del informe final estructurado bajo los 21 capítulos exigidos por los lineamientos de la UES (FMO).
- [ ] **5.2:** Batería de consultas analíticas y justificación técnica de arquitectura para la defensa ante jurado.
- [ ] **5.3:** Estandarización final del repositorio Git (README, diagramas de arquitectura, contenedores Docker y manual de despliegue).

---

## ⚙️ Puesta en marcha

### Requisitos previos

- **Python** >= 3.11
- **Docker & Docker Compose** — esta guía asume Docker para levantar PostgreSQL y Neo4j; sin él tendrías que instalar y configurar ambos motores a mano y ejecutar los scripts de `database/oltp/` manualmente, un camino que este README no cubre.

> Nota: varios comandos de esta guía (verificación del modelo de seguridad, solución de problemas) usan variables como `$APP_DB_PASSWORD` directamente en la terminal. Para que existan en tu shell, expórtalas primero desde `.env`:
> ```bash
> set -a && source .env && set +a
> ```

### 1. Configuración de credenciales

Todas las credenciales del proyecto viven en un único archivo `.env` en la raíz
(no versionado). Nunca se escriben dentro del código.

```bash
cp .env.example .env
```

Edita `.env` y reemplaza los valores marcados como `cambiar_...`. Para la clave de sesión:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Despliegue de los motores de base de datos

```bash
# Levanta PostgreSQL 17 y Neo4j en segundo plano
docker compose up -d
```

En el **primer arranque sobre un volumen vacío**, PostgreSQL ejecuta automáticamente los
scripts de `database/oltp/` en orden alfabético (`01_init...` → `05_usuarios_auth` →
`06_bootstrap_rol_app` → `07_bootstrap_rol_etl` → `08_costos_institucionales` → … →
`10_dw_academico` → `11_bootstrap_rol_dashboard` → `12_dw_diagnostico` →
`13_dw_cierre_scrum35` → `14_bootstrap_rol_dw_carga`): crea el esquema operacional, la tabla de
usuarios de la aplicación, el rol de servicio de la app, el rol de solo lectura del ETL, el
catálogo de costos institucionales, el Data Warehouse, el rol de solo lectura del dashboard y
el rol que escribe el DW.
No hay que ejecutar ningún `.sql` a mano.

> ⚠️ Esos scripts **solo corren la primera vez**. Si ya tenías el contenedor creado desde
> antes (por ejemplo, de un clone anterior) y cambias algo en `.env`, el cambio **no** se
> aplica solo. Para reinicializar desde cero (⚠️ borra todos los datos):
> `docker compose down -v && docker compose up -d`. Si no quieres perder datos, ver
> [Solución de problemas](#solución-de-problemas) más abajo.

### 3. Dependencias de Python

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r scripts/generator/requirements.txt \
            -r etl/requirements.txt
```

### 4. Poblar con datos sintéticos (Fase 1.2)

```bash
python scripts/generator/02_generador_datos_sinteticos.py
python database/nosql/03_cargar_grafo_neo4j.py   # grafo curricular en Neo4j
```

Ambos scripts toman las credenciales del `.env`; ya no hay que editarlos.

> ⚠️ **Siembra los costos después de poblar.** `08_costos_institucionales.sql` corre al crear el
> contenedor, cuando todavía no hay períodos, así que no siembra nada. Sin costos, el DW carga
> `costo_inscripcion`/`costo_reprobacion`/`costo_repeticion` vacíos y la medida central del
> proyecto queda en cero sin ningún error. Tras el generador, ejecuta (idempotente):
> ```bash
> docker exec -i academico_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
>   "INSERT INTO academico_oltp.costos_uv (periodo_id, costo_por_uv, moneda, fuente)
>    SELECT periodo_id, 25.00, 'USD', 'SUPUESTO PARAMETRICO - pendiente de sustituir por cifra presupuestaria oficial'
>    FROM academico_oltp.periodos_academicos ON CONFLICT (periodo_id) DO NOTHING;"
> ```
> El valor de $25.00 por UV es un **supuesto paramétrico**, no una cifra oficial (ver la nota del
> script 08): sustitúyelo por el costo real, o decláralo como supuesto en la memoria.

### 5. Crear los usuarios de la aplicación

```bash
python backend/scripts/crear_usuario.py --demo --password demo1234
```

Crea dos usuarios de prueba para entorno local: `coordinador` y `docente` (este último
requiere que el generador de datos se haya ejecutado antes — paso 4). Para dar de alta
usuarios reales, sin el flag `--demo`:

```bash
python backend/scripts/crear_usuario.py --username jperez \
    --nombre "Jose Perez" --rol rol_docente --docente-id 3
```

### 6. Compilar los estilos (Tailwind CSS)

```bash
./scripts/setup-tailwind.sh
```

Descarga el binario standalone de Tailwind CSS (no requiere Node.js) en `.tools/` la primera
vez, y compila `backend/app/static/src/input.css` a `backend/app/static/app.css`. `app.css`
sí está versionado, así que un clone limpio ya tiene una versión compilada funcionando —
este paso solo hace falta si vas a tocar clases de Tailwind en `backend/app/templates/` o en
`input.css`.

### 7. Levantar el sistema transaccional (Fase 2)

```bash
cd backend
uvicorn app.main:app --reload
```

Disponible en `http://localhost:8000` (documentación de la API en `/api/docs`).

### 8. Verificar las conexiones del ETL (Fase 3)

```bash
python -m etl.verificar_conexiones
```

Desde la raíz del repositorio (el `-m` importa `etl` como paquete). Comprueba tres cosas y
devuelve código de salida distinto de cero si alguna falla:

1. Que se puede **leer** el esquema operacional con `rol_etl`.
2. Que se puede **leer** el grafo curricular en Neo4j.
3. Que el ETL **no puede escribir** en el esquema operacional — intenta un `UPDATE` a
   propósito y lo correcto es que PostgreSQL lo rechace.

La tercera es la que importa: el ETL es de solo lectura por los `GRANT` del motor, no por
disciplina de quien escriba el pipeline. Requiere que los pasos 4 (datos y grafo) y 2 (rol
`rol_etl`) se hayan completado.

### 9. Ejecutar el pipeline de extracción y limpieza (Fase 3.2)

```bash
python -m etl.pipeline                            # escribe en etl/staging/
python -m etl.pipeline --fecha-corte 2025-12-31   # corrida reproducible
python -m unittest discover -s etl/tests -v       # reglas de limpieza (sin base de datos)
python -m etl.verificar_pipeline                  # nota = SCRUM-10 y bloqueo de fugas, en vivo
```

Extrae estudiantes, inscripciones, calificaciones, asistencias, secciones, materias y periodos,
calcula la nota final ponderada con **la misma expresión SQL que el reporte de SCRUM-10**
(`backend/app/calculos.py`), aplica las reglas de limpieza, cruza con las métricas de grafo de
Neo4j (dependientes directos e indirectos por asignatura) y verifica que ningún dato
identificable salga hacia el DW. Si la verificación falla, no escribe ningún archivo. El
detalle de cada regla y cómo probarlas está en [`etl/SCRUM-34_pipeline.txt`](etl/SCRUM-34_pipeline.txt).

### 10. Cargar el Data Warehouse (Fase 3.3)

```bash
python -m etl.carga
```

Corre el pipeline completo y, solo si la verificación de anonimización pasa, recarga el
esquema estrella `dw_academico` (hechos por inscripción + dimensiones de período, carrera,
materia, estudiante, docente y sección) en **una sola transacción**: si algo falla, el DW queda
como estaba. Es **idempotente**: re-ejecutarla reemplaza el contenido, nunca duplica filas.

**Lectura y escritura son roles distintos.** El pipeline lee el OLTP con `rol_etl` (solo
lectura); la carga escribe el DW con `rol_dw_carga`, que **no** puede leer el OLTP. Define
`DW_CARGA_DB_USER` y `DW_CARGA_DB_PASSWORD` en tu `.env` (ver `.env.example`); sin ellas la
carga se detiene antes de tocar nada.

**Medidas de costo** en `fact_inscripcion` (costo institucional por UV × unidades valorativas,
SCRUM-36): `costo_inscripcion` (la matrícula de la materia), `costo_reprobacion` (lo anterior
solo si termina reprobada; la medida central del proyecto) y `costo_repeticion` (lo anterior
solo si `numero_intento > 1`). Las dos últimas **no son excluyentes** — una repetición reprobada
cuenta en ambas — así que no se suman entre sí. El corte por departamento ya viene resuelto en
la vista `dw_academico.v_mart_departamento`.

### 11. Abrir la vista ejecutiva (Fase 4.1)

```bash
cd backend
uvicorn app.main:app --reload                  # http://localhost:8000/vista-ejecutiva
python -m app.verificar_dw                     # la vista ejecutiva NO puede leer el OLTP
python -m unittest discover -s tests -v        # definición de los KPIs
```

Pantalla **Vista ejecutiva** de la misma aplicación web (menú *Inteligencia institucional*,
solo coordinador): costo de reprobación, costo por estudiante, tasa de reprobación y proporción
del costo atribuible a repetición, con filtros por período, carrera y departamento, ranking de
materias por costo y la interpretación en texto de cada indicador. A diferencia del resto de la
app, no usa la sesión con `SET LOCAL ROLE`: lee el DW con su propia conexión como
`rol_dashboard`, que solo tiene `SELECT` sobre `dw_academico` — PostgreSQL le niega
`academico_oltp`. Detalle y guía de pruebas en
[`docs/FASE-4.1_vista_ejecutiva.txt`](docs/FASE-4.1_vista_ejecutiva.txt).

**Versión Streamlit (SCRUM-44).** Los mismos cuatro KPIs, filtros, ranking e interpretaciones
existen también como app independiente en `dashboard/`. Comparte con la vista web las
definiciones de `backend/app/indicadores.py` y las consultas de `backend/app/dw.py`, así que
ambas muestran las mismas cifras.

```bash
pip install -r dashboard/requirements.txt      # una sola vez (dentro del .venv)
streamlit run dashboard/app.py                 # desde la raíz del repo → http://127.0.0.1:8501
python -m unittest discover -s dashboard/tests -v
```

Solo necesita `POSTGRES_*` y `DASHBOARD_DB_PASSWORD` en el `.env` (ver `.env.example`); no lee
`APP_*` ni ninguna credencial del backend. Se conecta como `rol_dashboard`, que PostgreSQL
limita a `SELECT` sobre `dw_academico`.

> **Seguridad:** esta app **no tiene inicio de sesión** (la vista `/vista-ejecutiva` sí exige un
> coordinador). Por eso `.streamlit/config.toml` la deja escuchando solo en `127.0.0.1`. No la
> expongas a una red ni a internet sin poner antes un proxy con autenticación.

### 12. Análisis diagnóstico y validación de datos (Fase 4.2)

```bash
python -m etl.carga                 # el DW necesita database/oltp/12_dw_diagnostico.sql
python -m etl.validar_dw            # 46 verificaciones entre capas + registro para la memoria
```

Pantalla **Análisis diagnóstico** (mismo menú, solo coordinador): matriz de correlaciones,
análisis por cohorte, segmentación por turno, área y ciclo del plan, y los estudiantes que
**ya presentan** el patrón de riesgo (nota < 6.00 y 3+ ausencias, los mismos umbrales del
sistema transaccional, definidos una sola vez en `backend/app/calculos.py`). Describe patrones
observados; no predice. `etl/validar_dw.py` reconcilia el DW contra el OLTP y contra los
reportes del coordinador caso por caso, y escribe
[`docs/validacion/registro_validacion.md`](docs/validacion/registro_validacion.md). Detalle,
hallazgos y guía de pruebas en
[`docs/FASE-4.2_analisis_diagnostico.txt`](docs/FASE-4.2_analisis_diagnostico.txt).

---

## 🆘 Solución de problemas

**`password authentication failed for user "rol_app"` (o similar) al iniciar sesión o abrir el sitio**
Editaste `.env` después de que el contenedor de PostgreSQL ya se había inicializado una vez;
los scripts de `docker-entrypoint-initdb.d/` no se vuelven a ejecutar sobre un volumen
existente, así que el rol sigue con la contraseña anterior. Dos opciones:
- Sin perder datos, sincroniza la contraseña del rol a mano:
  ```bash
  docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
      psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      -c "ALTER ROLE $APP_DB_USER WITH PASSWORD '$APP_DB_PASSWORD';"
  ```
- O reinicializa desde cero (⚠️ borra todos los datos): `docker compose down -v && docker compose up -d`.

**`role "rol_app" does not exist`**
El contenedor de PostgreSQL ya existía de antes de que `.env` tuviera `APP_DB_PASSWORD`
definida — `06_bootstrap_rol_app.sh` se niega a correr sin esa variable, y al ser un script
de primer-arranque no se reintenta solo. Ejecútalo manualmente contra el contenedor ya
corriendo:
```bash
docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" -e POSTGRES_USER -e POSTGRES_DB \
    -e APP_DB_USER -e APP_DB_PASSWORD \
    academico_postgres bash -s < database/oltp/06_bootstrap_rol_app.sh
```

**`set: pipefail: invalid option name` al correr el script anterior (Windows)**
Tu copia local de `06_bootstrap_rol_app.sh` tiene saltos de línea CRLF — el `.gitattributes`
del repo fuerza LF para `*.sh`, así que un clone limpio no debería tener este problema, pero
si tu checkout es antiguo o algún editor reescribió el archivo, corrígelo con
`git checkout -- database/oltp/06_bootstrap_rol_app.sh` (o `dos2unix`) y vuelve a intentar.

**`relation "academico_oltp.costos_uv" does not exist`**
Tu contenedor se creó antes de que existiera `08_costos_institucionales.sql`, y los scripts de
primer arranque no se reejecutan sobre un volumen existente. Aplícalo a mano sin perder datos
(el script es idempotente, se puede correr más de una vez):
```bash
set -a && . ./.env && set +a
docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
    < database/oltp/08_costos_institucionales.sql
```

**`column "patron_riesgo" ... does not exist` al cargar el DW**
Tu DW se creó antes de la Fase 4.2. Aplica la migración (idempotente) y recarga:
```bash
docker exec -i academico_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1     < database/oltp/12_dw_diagnostico.sql
python -m etl.carga
```

**`schema "dw_academico" does not exist` o `password authentication failed for user "rol_dashboard"`**
Tu contenedor se creó antes del Data Warehouse. Agrega `DASHBOARD_DB_USER` y
`DASHBOARD_DB_PASSWORD` a tu `.env` (ver `.env.example`) y aplica los dos scripts sin perder datos:
```bash
set -a && . ./.env && set +a
docker exec -i academico_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1     < database/oltp/10_dw_academico.sql
docker exec -i -e POSTGRES_USER -e POSTGRES_DB -e DASHBOARD_DB_USER -e DASHBOARD_DB_PASSWORD     academico_postgres bash -s < database/oltp/11_bootstrap_rol_dashboard.sh
python -m etl.carga
```

**`password authentication failed for user "rol_dw_carga"`, `DW_CARGA_DB_PASSWORD` faltante o `column "seccion_key" does not exist` al cargar el DW**
Tu DW se creó antes del cierre de SCRUM-35 (dimensiones de docente y sección, `costo_repeticion` y
el rol de escritura propio). Agrega `DW_CARGA_DB_USER` y `DW_CARGA_DB_PASSWORD` a tu `.env`,
aplica la migración y el bootstrap (idempotentes, sin perder datos), recarga y vuelve a aplicar
la migración para que las llaves nuevas queden `NOT NULL`:
```bash
set -a && . ./.env && set +a
docker exec -i academico_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1     < database/oltp/13_dw_cierre_scrum35.sql
docker exec -i -e POSTGRES_USER -e POSTGRES_DB -e DW_CARGA_DB_USER -e DW_CARGA_DB_PASSWORD     academico_postgres bash -s < database/oltp/14_bootstrap_rol_dw_carga.sh
python -m etl.carga
docker exec -i academico_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1     < database/oltp/13_dw_cierre_scrum35.sql
```
> La migración también le **quita** a `rol_etl` los permisos de escritura sobre el DW que le
> había dado el script 10: `rol_etl` queda de solo lectura, como dice el criterio de SCRUM-35.

**`password authentication failed for user "rol_etl"` al correr el ETL**
Mismo caso que con `rol_app`: `07_bootstrap_rol_etl.sh` es un script de primer arranque y no
se reejecuta sobre un volumen existente. Córrelo contra el contenedor ya levantado:
```bash
docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" -e POSTGRES_USER -e POSTGRES_DB \
    -e ETL_DB_USER -e ETL_DB_PASSWORD \
    academico_postgres bash -s < database/oltp/07_bootstrap_rol_etl.sh
```

**El contenedor `academico_neo4j` no arranca, o el ETL falla con `Neo.ClientError.Security.Unauthorized`**
Algo más en la máquina ya está ocupando los puertos 7474/7687 — otra instancia de Neo4j
(Docker o Neo4j Desktop). Docker no puede publicar un puerto tomado, así que el contenedor
del proyecto nunca se crea y el driver acaba hablándole a la instancia ajena, que tiene otra
contraseña. Comprueba con `docker ps` y `ss -ltn | grep -E '7474|7687'`; libera el puerto
(`docker stop <contenedor>`, sin `-v` para no perder sus datos) y vuelve a correr
`docker compose up -d neo4j_db`. Un Neo4j recién creado arranca **vacío**: hay que volver a
ejecutar `python database/nosql/03_cargar_grafo_neo4j.py` (paso 4).

**`No hay docentes en la base: omito el usuario docente` al crear los usuarios demo**
Ejecutaste el paso 5 antes que el paso 4. Corre primero el generador de datos sintéticos y
vuelve a correr `crear_usuario.py --demo`.

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

### Comprobación del modelo (demostrable ante el jurado)

```bash
docker exec -i -e PGPASSWORD="$APP_DB_PASSWORD" academico_postgres \
    psql -U "$APP_DB_USER" -d "$POSTGRES_DB" <<'SQL'
-- Sin SET ROLE: el rol de servicio no puede leer nada (falla cerrado)
SELECT count(*) FROM academico_oltp.inscripciones;

-- Como docente: leer sí, borrar no
BEGIN;
SET LOCAL ROLE rol_docente;
SELECT count(*) FROM academico_oltp.inscripciones;
DELETE FROM academico_oltp.inscripciones WHERE inscripcion_id = 1;
ROLLBACK;
SQL
```

Resultado esperado:

| Operación | Resultado |
|---|---|
| `SELECT` sin `SET ROLE` | `ERROR: permission denied for table inscripciones` |
| `SELECT` como `rol_docente` | 36 704 filas |
| `DELETE` como `rol_docente` | `ERROR: permission denied for table inscripciones` |
| `DELETE` como `rol_coordinador` | `DELETE 1` |
| Leer `auditoria` como `rol_docente` | `ERROR: permission denied for schema auditoria` |

---

## 🧱 Decisiones de stack

### Backend y frontend (Fase 2.1)

Se optó por **FastAPI + Jinja2 + Bootstrap** sobre la alternativa de Streamlit Admin:

| Criterio | FastAPI + Bootstrap | Streamlit Admin |
|---|---|---|
| Separación backend/frontend | Sí, con capa de rutas y plantillas | No, todo en un script |
| Control de sesión y roles | Middleware y dependencias propias | Limitado |
| Manejo de formularios y validación | Completo | Restringido a widgets |
| Representatividad de un OLTP real | Alta | Baja |

Streamlit se había reservado para la **Fase 4 (dashboard analítico)**.

> **Actualización (octubre 2026):** la Fase 4 tiene **dos** frontends sobre el mismo DW. La
> vista ejecutiva vive dentro de esta aplicación (`/vista-ejecutiva`, con su menú, su sesión y su
> sistema de diseño) para que el coordinador vea operación y analítica en un solo lugar; y, por
> el requisito SCRUM-44, existe además una app Streamlit en `dashboard/`. Ambas comparten las
> definiciones de los KPIs y las consultas, y cumplen lo que el requisito pedía de fondo: leen
> **solo** `dw_academico`, con un rol de solo lectura propio (`rol_dashboard`) y credenciales
> desde `.env`. La diferencia es de acceso: la vista web exige sesión de coordinador; la app
> Streamlit no tiene login y solo escucha en `127.0.0.1`.

> **Actualización (septiembre 2026):** la capa visual migró de Bootstrap 5.3 (CDN) a
> **Tailwind CSS v4**, compilado con el binario standalone (`scripts/setup-tailwind.sh`, sin
> Node.js) hacia `backend/app/static/app.css`. La decisión de FastAPI + Jinja2 sigue vigente
> sin cambios; solo se reemplazó el framework de CSS. El sistema de diseño resultante está
> documentado en [`DESIGN.md`](DESIGN.md).

### Base NoSQL: Neo4j frente a MongoDB (Fase 1.3)

El curso exige una base NoSQL y justificar cuál conviene. Se eligió **Neo4j**.

La estructura que el proyecto necesita modelar fuera del relacional es una sola: la malla
curricular, es decir, qué materia exige haber aprobado cuál. Eso es un grafo dirigido acíclico,
y las preguntas que el proyecto le hace son **transitivas**, no de un solo salto:

- ¿Cuántas materias quedan bloqueadas en cascada si un estudiante reprueba esta? (profundidad variable)
- ¿Cuál es la cadena de prerrequisitos más larga hacia la materia final de la carrera?

En Cypher esas dos preguntas son una línea cada una, y están en
[`database/nosql/cypher_queries.cql`](database/nosql/cypher_queries.cql):

```cypher
MATCH (base:Materia)<-[:REQUIERE_APROBADA*1..5]-(bloqueadas:Materia)
RETURN base.codigo, count(DISTINCT bloqueadas) AS MateriasBloqueadasEnCascada
ORDER BY MateriasBloqueadasEnCascada DESC;
```

| Criterio | Neo4j | MongoDB |
|---|---|---|
| Modelado de la dependencia | Relación de primera clase | Arreglo de referencias dentro del documento |
| Recorrido transitivo | Nativo (`*1..5`, `*`) | Posible con `$graphLookup` |
| El **camino** como resultado | Sí: `p = (...)-[...*]->(...)`, `length(p)`, `nodes(p)` | No: devuelve los documentos alcanzados, aplanados y sin la ruta |
| Ruta crítica hacia la graduación | Una consulta | Reconstruir la cadena en la aplicación |
| Algoritmos de grafos (centralidad) | APOC, ya instalado en el contenedor | Fuera de alcance del motor |

El punto que decide no es que MongoDB no pueda: `$graphLookup` hace recorridos recursivos. Es que
devuelve el **conjunto** de documentos alcanzados y no el **camino** que los une, y el camino es
justamente la respuesta que necesita el reporte de asignaturas críticas de la Fase 4.3. En MongoDB
habría que reconstruirlo en código de aplicación; en Neo4j es el resultado de la consulta.

> **La pregunta incómoda, por si la hace el jurado:** ¿y por qué no un `WITH RECURSIVE` en
> PostgreSQL, que ya está en el proyecto? Se puede, y para el caso de bloqueo en cascada daría el
> mismo resultado. La respuesta honesta tiene dos partes: el curso exige incorporar un motor NoSQL,
> y dado ese requisito, la malla curricular es la única estructura del dominio que es genuinamente
> no relacional, así que es donde un motor de grafos aporta algo real en vez de ser decorativo. Los
> datos transaccionales se quedan en PostgreSQL precisamente porque ahí sí son tabulares.

