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
│   ├── app/red_curricular.py   # Fase 4.3: la malla como grafo (NetworkX), cruce costo × posición y su lectura
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
- [x] **1.2:** Generador de datos sintéticos con Python que se parecen a la FMO-UES: 8 departamentos, 12 carreras con su
  plan de estudios (523 asignaturas), 105 docentes, ~2 300 estudiantes que avanzan por su plan con prerrequisitos,
  dos ciclos al año de cuatro módulos cada uno, evaluaciones por módulo (cada docente arma las suyas), notas y
  asistencia (~0.5 M de filas). Todo es inventado: ver `scripts/generator/catalogo_ues.py` para lo que es público y lo
  que no.
- [x] **1.3:** Modelado y carga del grafo de la malla curricular en Neo4j (Cypher: asignaturas y relaciones de prerrequisitos).
- [x] **1.4:** Pruebas de rendimiento y optimización con `EXPLAIN ANALYZE` (documentación comparativa antes/después de índices).

### Fase 2: Sistema Transaccional de Gestión (CRUD Operacional)
- [x] **2.1:** Backend y frontend liviano transaccional (FastAPI + Jinja2 + Tailwind CSS).
- **2.2:** Módulos operacionales:
  - [x] Matrícula (SCRUM-7) — inscribir y retirar estudiantes de secciones.
  - [x] Registro de calificaciones (SCRUM-8) — evaluaciones ponderadas y notas por sección.
  - [x] Control de asistencia (SCRUM-9) — asistencia por sesión y resumen de faltas.
  - [x] Reportes operacionales (SCRUM-10) — notas finales, asistencia acumulada, rendimiento por
    materia, desempeño por docente, ocupación de secciones y notas pendientes de registro. Todos
    se descargan en CSV, Excel y PDF (`backend/app/exportar.py`).
  - [x] Reporte personalizado (`/reportes/personalizado`) — el coordinador elige tema (asistencia,
    calificaciones, matrícula), agrupación (período, mes, semana, día, carrera, materia, docente,
    turno, motivo de retiro…), desglose, rango de fechas y gráfica (líneas, columnas o barras).
    La gráfica sale en la página (SVG), en el PDF y como gráfico nativo en el Excel.
  - [x] Carga masiva desde Excel — notas, asistencia y matrícula: plantilla con la lista de la
    sección, vista previa con errores y cambios fila por fila, y confirmación explícita antes de
    sobrescribir.
  - [x] Filtros en las listas de Catálogos — además de buscar, cada lista se filtra por lo que le corresponde
    (departamento, carrera, ciclo del plan, turno, docente, condición, año de ingreso, activo…), se ordena
    por cualquier columna, elige cuántas filas mostrar (25 a 200), muestra los filtros activos como fichas
    que se quitan de una en una y descarga en CSV exactamente la lista filtrada (no solo la página).
  - [x] Carga masiva de catálogos — períodos, secciones, materias, docentes, estudiantes, carreras y
    departamentos (Catálogos > cada uno > «Carga masiva»). La plantilla trae la cabecera del
    catálogo, una fila amarilla de ejemplo (arriba de la cabecera: nunca se importa), listas
    desplegables, una hoja «Guía» (qué escribir en cada campo, con ejemplo) y una hoja
    «Referencia» con los códigos válidos: en el archivo se escribe el código (`MAT101`, `SIS`),
    nunca el número interno. Si el registro ya existe (mismo código; en estudiantes, mismo carnet)
    se actualiza, si no se crea. Hasta 1 000 filas por archivo; con un solo error no se aplica
    nada y la confirmación aplica todo o nada. El carnet no viaja ni se guarda: solo su hash.
  - [x] Cierre de acta — el docente cierra la sección cuando las evaluaciones suman 100 % y no
    falta ninguna nota; desde ahí el motor bloquea cambios. Solo el coordinador la reabre, con motivo.
  - [x] Administración (solo coordinador) — períodos, secciones, materias, docentes, estudiantes,
    carreras y departamentos; malla curricular (escribe en Neo4j y rechaza ciclos); usuarios
    (alta, rol, desactivar, contraseña temporal); metas de los indicadores; auditoría de cambios
    de notas y actas; estado del almacén (historial de cargas y última validación).
  - [x] Cuenta propia — cada usuario cambia su contraseña; la temporal obliga a cambiarla al entrar.

  Validación de estas funciones, decisiones y limitaciones:
  [`docs/validacion/funcionalidades_lista_d.md`](docs/validacion/funcionalidades_lista_d.md).

### Fase 3: Ingeniería de Datos (ETL y Data Warehouse)
- [x] **3.1:** Conexión y extracción híbrida (SQLAlchemy para PostgreSQL y driver oficial Neo4j).
- [x] **3.2:** Pipeline de extracción, anonimización (SHA-256), limpieza de datos y cálculo de métricas de grafo.
- [x] **3.3:** Diseño del modelo dimensional estrella (`dw_academico`) y carga incremental/controlada a hechos y dimensiones.

### Fase 4: Dashboard Analítico e Inteligencia de Negocios
- [x] **4.1:** Vista ejecutiva con los KPIs de costo y rendimiento, filtrados por período, carrera y departamento.
- [x] **4.2:** Matriz de correlaciones, análisis por cohorte e identificación de los estudiantes que presentan el patrón de riesgo observado.
- [x] **4.3:** Visualización interactiva de la red curricular (NetworkX, desde el grafo de Neo4j vía el ETL) y reporte de asignaturas críticas/cuellos de botella, cruzado con el costo.

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

- **Python** >= 3.11 (en Ubuntu 20.04 el del sistema es 3.8: ver [Despliegue en un servidor](#️-despliegue-en-un-servidor-ubuntu))
- **Docker & Docker Compose** — esta guía asume Docker para levantar PostgreSQL y Neo4j; sin él tendrías que instalar y configurar ambos motores a mano y ejecutar los scripts de `database/oltp/` manualmente, un camino que este README no cubre.

> **Todos los comandos de esta guía son de bash.** En Windows usa **Git Bash** (o WSL), no
> PowerShell ni `cmd`: ahí no existen `source`, `./script.sh`, `$VARIABLE` ni la redirección
> `< archivo`, y los pasos fallan con errores que no tienen que ver con el proyecto.
> En Git Bash el entorno virtual se activa con `source .venv/Scripts/activate` (en Linux/macOS,
> `source .venv/bin/activate`); ver el paso 3.

> **Siempre desde la raíz del repositorio.** Todos los comandos asumen que estás en la raíz
> (donde está este README). Los pocos que necesitan estar en `backend/` van entre paréntesis,
> `( cd backend && … )`, para que tu terminal no se quede allí.

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

> ⚠️ Si ya tenías un `.env` de una versión anterior, **no basta con conservarlo**: la plantilla
> ganó variables nuevas (`ETL_DB_*`, `DASHBOARD_DB_*`, `DW_CARGA_DB_*`). Compara con
> `.env.example` y agrega las que falten. Si falta alguna, `docker compose` lo avisa con
> `The "…" variable is not set. Defaulting to a blank string` y los scripts de inicialización
> (`07`, `11`, `14`) se niegan a crear ese rol. Ver [Solución de problemas](#solución-de-problemas).

### 2. Despliegue de los motores de base de datos

```bash
# Levanta PostgreSQL 17 y Neo4j en segundo plano y ESPERA a que estén listos
docker compose up -d --wait
```

`--wait` importa: el primer arranque ejecuta todos los scripts de `database/oltp/` y tarda
unas decenas de segundos. Sin él, `up -d` vuelve de inmediato y el generador del paso 4
falla con `connection refused` o con tablas que aún no existen. (Los contenedores declaran un
`healthcheck`; puedes ver su estado con `docker compose ps`, debe decir `healthy`.)

En el **primer arranque sobre un volumen vacío**, PostgreSQL ejecuta automáticamente los
scripts de `database/oltp/` en orden alfabético (`01_init...` → `05_usuarios_auth` →
`06_bootstrap_rol_app` → `07_bootstrap_rol_etl` → `08_costos_institucionales` → … →
`10_dw_academico` → `11_bootstrap_rol_dashboard` → `12_dw_diagnostico` →
`13_dw_cierre_scrum35` → `14_bootstrap_rol_dw_carga` → `15_dw_red_curricular`): crea el esquema operacional, la tabla de
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
python -m venv .venv
source .venv/Scripts/activate      # Git Bash en Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r backend/requirements.txt -r scripts/generator/requirements.txt \
            -r etl/requirements.txt
```

Comprueba que el entorno quedó activo: `which python` debe apuntar a `.venv/`. Si apunta a
tu Python global, `pip` instalará allí y comandos como `uvicorn` no se encontrarán (por eso
esta guía los invoca como `python -m …`).

### 4. Poblar con datos sintéticos (Fase 1.2)

```bash
python scripts/generator/02_generador_datos_sinteticos.py   # con --reiniciar reemplaza lo transaccional anterior
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
python -m uvicorn --app-dir backend app.main:app --reload
```

Disponible en `http://localhost:8000` (documentación de la API en `/api/docs`). El servidor
**ocupa esa terminal**: déjalo corriendo y abre **otra** (también en la raíz, con el entorno
virtual activado) para los pasos siguientes.

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
# http://localhost:8000/vista-ejecutiva  (con el servidor del paso 7 corriendo)
( cd backend && python -m app.verificar_dw )                  # la vista ejecutiva NO puede leer el OLTP
( cd backend && python -m unittest discover -s tests -v )     # definición de los KPIs
```

Pantalla **Vista ejecutiva** de la misma aplicación web (menú *Inteligencia institucional*,
solo coordinador): costo de reprobación, costo por estudiante, tasa de reprobación y proporción
del costo atribuible a repetición, con filtros por período, carrera y departamento, ranking de
materias por costo y la interpretación en texto de cada indicador. A diferencia del resto de la
app, no usa la sesión con `SET LOCAL ROLE`: lee el DW con su propia conexión como
`rol_dashboard`, que solo tiene `SELECT` sobre `dw_academico` — PostgreSQL le niega
`academico_oltp`. Detalle y guía de pruebas en
[`docs/FASE-4.1_vista_ejecutiva.txt`](docs/FASE-4.1_vista_ejecutiva.txt).

**Dashboard interactivo en Streamlit (SCRUM-44).** App independiente en `dashboard/` con la misma identidad
de Sistema Minerva (marca, paleta, tipografía, modo claro y oscuro, barra lateral y barra superior), para que se
vea como parte de la app. Tiene la versión interactiva de las pantallas de inteligencia, con sus mismas
secciones: **Vista ejecutiva**, **Dashboard estratégico**, **Red curricular** (la red dibujada, eligiendo una
materia se resalta lo que bloquea), **Cubo OLAP** (ROLLUP/CUBE con subtotales y CSV) y **Patrón de riesgo
observado** (el equivalente descriptivo de las antiguas «alertas»). Comparte con la app web las consultas de
`backend/app/dw.py` y las definiciones y lecturas en texto de `backend/app/`, así que ambas muestran las mismas
cifras. El marco visual está en `dashboard/tema.py` y `dashboard/shell.py`: si cambia un token de `DESIGN.md`,
cámbialo ahí también.

```bash
pip install -r dashboard/requirements.txt      # una sola vez (dentro del .venv)
streamlit run dashboard/app.py                 # desde la raíz del repo → http://127.0.0.1:8501
python -m unittest discover -s dashboard/tests -v
```

Solo necesita `POSTGRES_*` y `DASHBOARD_DB_PASSWORD` en el `.env` (ver `.env.example`); no lee
`APP_*` ni ninguna credencial del backend. Se conecta como `rol_dashboard`, que PostgreSQL
limita a `SELECT` sobre `dw_academico`.

> **Seguridad:** esta app **no tiene inicio de sesión propio** (la vista `/vista-ejecutiva` sí exige
> un coordinador). Por eso `.streamlit/config.toml` la deja escuchando solo en `127.0.0.1`. Para
> abrirla con un enlace sin túnel, publícala detrás de nginx con la sesión de la app web: ver
> «Dashboard de Streamlit con enlace y login» en la sección de despliegue. No la expongas a una red ni
> a internet de ninguna otra forma.

### 12. Análisis diagnóstico y validación de datos (Fase 4.2)

```bash
python -m etl.carga                 # el DW necesita database/oltp/12_dw_diagnostico.sql
python -m etl.validar_dw            # 99 verificaciones entre capas + registro para la memoria
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

### 13. Red curricular y materias cuello de botella (Fase 4.3)

```bash
python -m etl.carga                 # lleva las relaciones de la malla de Neo4j al DW (database/oltp/15)
( cd backend && python -m unittest discover -s tests -v )   # 34 pruebas de la red, sin base de datos
```

Pantalla **Red curricular** (`/red-curricular`, mismo menú, solo coordinador): las 45 materias del plan de Sistemas Informáticos (la única carrera con malla en el grafo) y sus
relaciones de prerrequisito como red interactiva (elegir una materia resalta lo que bloquea y lo que
hay que aprobar antes), el reporte de materias cuello de botella y el cruce del costo de reprobación
con la posición de cada materia en la malla, con la lectura en texto de cada pieza. La malla se
origina en Neo4j pero la pantalla la lee del Data Warehouse, con `rol_dashboard`: no necesita
credenciales del grafo. Neo4j recién creado arranca vacío: carga primero la malla
(`python database/nosql/03_cargar_grafo_neo4j.py`). Detalle, método y guía de pruebas en
[`docs/FASE-4.3_red_curricular.txt`](docs/FASE-4.3_red_curricular.txt).

### 14. Dashboard estratégico y cubo OLAP (datos reales)

Dos pantallas del menú «Inteligencia institucional» (solo coordinador) que antes eran maquetas con cifras de
ejemplo y ahora leen el Data Warehouse con `rol_dashboard`, sin consultar el sistema transaccional ni Neo4j:

- **Dashboard estratégico** (`/dashboard`): estudiantes evaluados, tasa de aprobación y costo de reprobación con su
  variación contra el período anterior, aprobación por ciclo del plan, reprobación por período y las materias que
  más frenan la malla, con la lectura en texto de cada pieza.
- **Cubo OLAP** (`/analitica-olap`): eliges hasta tres dimensiones (período, departamento, carrera, ciclo del plan,
  área, materia, turno, cohorte) y PostgreSQL calcula con `GROUP BY ROLLUP` o `CUBE` las medidas de cada
  combinación, los subtotales y el total. El usuario nunca escribe SQL: elige claves de un catálogo fijo. Se
  descarga en CSV y `etl/validar_dw.py` concilia sus totales contra los hechos del DW.

Quedaron fuera a propósito las «alertas de deserción» de la maqueta: son predictivas y el proyecto se limita a los
niveles descriptivo y diagnóstico. Su equivalente descriptivo, los estudiantes que **ya presentan** el patrón de
riesgo observado, está en Análisis diagnóstico. Detalle en
[`docs/FASE-4.4_dashboard_y_cubo.txt`](docs/FASE-4.4_dashboard_y_cubo.txt).

---

## 🖥️ Despliegue en un servidor (Ubuntu)

Probado en Ubuntu 20.04 (x86_64) con nginx delante y Cloudflare apuntando al dominio. Los
pasos 1 a 12 de arriba siguen siendo válidos; esto es lo que cambia en un servidor.

**1. Python 3.11 o superior.** Ubuntu 20.04 trae 3.8 y las dependencias no instalan. Sin tocar el
Python del sistema, con [`uv`](https://docs.astral.sh/uv/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r backend/requirements.txt -r scripts/generator/requirements.txt                -r etl/requirements.txt -r dashboard/requirements.txt
```

**2. Docker Engine con el plugin `docker compose` v2** (2.1.1 o superior, por `--wait`), desde el
repositorio oficial de Docker, no el `docker.io` de Ubuntu. Si tu usuario no está en el grupo
`docker`, los comandos llevan `sudo`, y **`sudo` borra las variables de entorno**: en los
scripts `07`, `11` y `14` pasa los valores explícitos, `sudo docker exec -i -e VAR="$VAR" …`
(un `-e VAR` a secas llega vacío y el script se niega a correr).

**3. Bases de datos solo en loopback.** `docker-compose.yml` publica PostgreSQL y Neo4j en
`127.0.0.1`. Docker se salta `ufw`/`iptables` cuando publica en `0.0.0.0`, así que no confíes en
el firewall del host. Para llegar desde tu equipo, túnel SSH:
`ssh -L 7474:127.0.0.1:7474 usuario@servidor`.

**4. La web como servicio de systemd**, escuchando solo en `127.0.0.1:8000` (nginx publica el
puerto 80/443 y hace `proxy_pass http://127.0.0.1:8000`). Sin `--reload` en servidor:

```ini
# /etc/systemd/system/academico-web.service
[Service]
User=ubuntu
WorkingDirectory=/var/www/academic-analytics-platform
ExecStart=/var/www/academic-analytics-platform/.venv/bin/python -m uvicorn --app-dir backend     app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure
[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now academico-web
```

**5. Dashboard de Streamlit con enlace y login.** `dashboard/` no tiene login propio y escucha solo en
`127.0.0.1:8501`. Para abrirlo con un enlace (sin túnel SSH) se publica en `/analitica/` y nginx
**exige antes la sesión de la app web**: la misma cookie y los mismos usuarios, sin otra contraseña
ni otra lista de usuarios. Solo entra el coordinador (igual que `/vista-ejecutiva`).

```
visitante ─> nginx ─ auth_request ─> app web  GET /auth/verificar   204 coordinador · 401 sin sesión · 403 otro rol
                 └── si pasa ──────> Streamlit 127.0.0.1:8501 (bajo /analitica/)
                 └── si no (401) ──> redirige a /login?siguiente=/analitica/   (vuelve al dashboard al entrar)
```

Pasos (todo en `deploy/`; comandos como root, los de Python como `ubuntu`):
1. Servicio: `cp deploy/academico-streamlit.service /etc/systemd/system/ && systemctl daemon-reload &&
   systemctl enable --now academico-streamlit` (usa el venv, el `.env` y `STREAMLIT_SERVER_BASE_URL_PATH=analitica`).
2. nginx: incorpora a tu vhost los bloques `location = /_auth_coordinador`, `location /analitica/` y los
   dos `@…` de `deploy/nginx-edumetrics.conf` (ese archivo es el vhost completo de referencia), y el `map`
   `$esquema_publico` en `conf.d/`. Valida y recarga: `nginx -t && systemctl reload nginx`. Requiere
   `ngx_http_auth_request_module`, que trae `nginx-light`, `nginx-core` y `nginx-full`
   (`nginx -V 2>&1 | grep auth_request`).
3. `.env`: `DASHBOARD_STREAMLIT_URL=/analitica/` (agrega «Dashboard interactivo» al menú) y reinicia `academico-web`.
   El servicio ya define `DASHBOARD_APP_URL=/` para los enlaces «Volver al sistema» y «Salir» del dashboard. Con las
   líneas `auth_request_set` / `proxy_set_header X-Minerva-Usuario` de `deploy/nginx-edumetrics.conf`, la barra
   superior del dashboard muestra quién inició sesión (solo informativo: nginx reemplaza lo que mande el navegador
   y nada se autoriza por esa cabecera).

Comprobación: sin sesión, `/analitica/` redirige al login; con un docente responde 403; con un coordinador
carga el dashboard. Cerrar sesión en la app corta el acceso a las páginas nuevas; una pestaña de Streamlit ya
abierta sigue viva hasta que se cierre o recargue.

**6. Lista de seguridad antes de abrirlo a internet**
- `MODO_DEMO=false` en `.env` (es el valor por defecto).
- `COOKIE_SECURE=true` en `.env` cuando el sitio se sirva por HTTPS (también si el TLS termina en
  nginx o Cloudflare): la cookie de sesión lleva la marca `Secure` y el navegador solo la envía por
  HTTPS. Con `true` no se puede iniciar sesión por `http://<IP>` directo, solo por el dominio con
  HTTPS; en local déjalo en `false`. Reinicia el servicio tras cambiarlo.
- **No dejes los usuarios de `--demo` con la contraseña `demo1234`**: es pública en este README.
  En un servidor crea usuarios con contraseña propia (`crear_usuario.py` sin `--demo`) o
  cámbiales la contraseña a los demo.
- `.env` con permisos `600` y contraseñas generadas (`openssl rand -base64 24`).
- Comprueba desde fuera que solo responde el 80/443: `5432`, `7474`, `7687`, `8000` y `8501`
  deben estar cerrados.

---

## 🆘 Solución de problemas

**`The "DASHBOARD_DB_PASSWORD" variable is not set. Defaulting to a blank string` (o `ETL_DB_*`, `DW_CARGA_DB_*`) al usar `docker compose`**
Tu `.env` es de una versión anterior y le faltan variables. Cópialas de `.env.example` y
ponles valor. Si el contenedor de PostgreSQL ya existía, los roles nuevos no se crean solos:
aplica las secciones de abajo que correspondan (`rol_etl`, `rol_dashboard`, `rol_dw_carga`).

**`ValidationError … etl_db_password` (o `dashboard_db_password`, `dw_carga_db_password`) `Field required`, incluso al correr las pruebas**
Mismo origen: a tu `.env` le falta esa variable. Los módulos del ETL y del dashboard leen su
configuración al importarse, así que hasta las pruebas "sin base de datos" necesitan el `.env`
completo (aunque no se conecten a nada). Agrega `ETL_DB_USER`/`ETL_DB_PASSWORD`,
`DASHBOARD_DB_USER`/`DASHBOARD_DB_PASSWORD` y `DW_CARGA_DB_USER`/`DW_CARGA_DB_PASSWORD` desde
`.env.example`. Si tu contenedor de PostgreSQL ya existía, además hay que crear esos roles en
la base (siguientes entradas).

**`uvicorn: command not found` / `No module named 'etl'` / `No module named 'app'`**
Casi siempre es una de dos cosas: el entorno virtual no está activo (`which python` debe
apuntar a `.venv/`; en Git Bash se activa con `source .venv/Scripts/activate`), o estás en el
directorio equivocado. Los comandos de `etl.*` y `dashboard/` van desde la **raíz**; solo
`app.verificar_dw` y las pruebas del backend van desde `backend/` (`( cd backend && … )`).

**`connection refused` o `relation "…" does not exist` justo después de `docker compose up -d`**
Los scripts del primer arranque aún no terminaron. Usa `docker compose up -d --wait` o espera
a que `docker compose ps` muestre `healthy` en los dos contenedores.

**`relation "…" does not exist` en una pantalla que a un compañero sí le funciona**
Tu contenedor se creó antes de que alguien agregara un script DDL nuevo, y los scripts de
`database/oltp/` **solo se ejecutan en el primer arranque** sobre un volumen vacío. No hace falta
borrar nada ni averiguar cuál falta:

```bash
./scripts/aplicar_ddl_pendiente.sh --revisar   # qué falta, sin tocar nada
./scripts/aplicar_ddl_pendiente.sh             # aplicar lo que falte
```

Si aplicó algo del Data Warehouse, recárgalo después con `python -m etl.carga`. Conviene correrlo
cada vez que traigas cambios de `develop`. Ejemplo: los scripts 17 a 20 (actas, cuentas, motivo de
retiro, metas) son necesarios para Administración, cierre de acta y semáforo de metas, y el 20 toca
el Data Warehouse, así que después hay que correr `python -m etl.carga`.

**`-bash: source: .venv/bin/activate: No such file` o `The term 'source' is not recognized`**
En Windows el entorno virtual vive en `.venv/Scripts/`, no en `.venv/bin/`, y `source` solo
existe en Git Bash/WSL. Abre **Git Bash** y usa `source .venv/Scripts/activate`.

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

**`relation "dw_academico.bridge_prerrequisito" does not exist` al cargar el DW o al abrir la red curricular**
Tu DW se creó antes de la Fase 4.3. Aplica la migración (idempotente), instala la dependencia nueva y recarga:
```bash
pip install -r backend/requirements.txt
docker exec -i academico_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1     < database/oltp/15_dw_red_curricular.sql
python -m etl.carga
```
Si `etl.carga` falla con la malla vacía, Neo4j arrancó sin datos: `python database/nosql/03_cargar_grafo_neo4j.py`.

**`ModuleNotFoundError: No module named 'networkx'`**
Falta la dependencia de la Fase 4.3: `pip install -r backend/requirements.txt` (con el entorno virtual activo).

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
- **Cada docente solo ve y escribe sus propias secciones**, y también lo impone el motor:
  `evaluaciones`, `calificaciones` y `asistencias` tienen seguridad por fila
  (`database/oltp/16_rls_docente.sql`). Junto al `SET LOCAL ROLE`, la aplicación declara el
  docente de la sesión con `set_config('app.docente_id', …, true)`. Si no lo declara, el docente
  no ve ninguna fila: también falla cerrado. El coordinador y `rol_etl` tienen políticas de
  acceso completo. Límite honesto: protege de errores de la aplicación, no de quien tenga la
  credencial de `rol_app`, que puede declarar cualquier docente.
- **Actas cerradas:** un trigger (`database/oltp/17_auditoria_y_actas.sql`) rechaza cualquier
  cambio de evaluaciones, notas o asistencia de una sección con el acta cerrada, venga de la
  aplicación o de SQL directo, incluso al coordinador. Cerrar y reabrir son funciones
  `SECURITY DEFINER` que validan rol, propiedad de la sección, ponderación y notas completas, y
  dejan constancia en `auditoria.log_actas`.
- **Auditoría de notas:** cada alta, cambio o borrado de una nota queda en
  `auditoria.log_cambios_notas` con el usuario de la aplicación (no solo el rol), que la
  aplicación declara con `set_config('app.usuario', …, true)`.
- **Contraseña y perfil propios:** el docente no tiene permiso sobre `usuarios`; cambia su
  contraseña con `cambiar_password_propio()` (`18_usuarios_cuenta.sql`) y su nombre con
  `actualizar_perfil_propio()` (`21_perfil_propio.sql`). Ambas solo tocan su fila y solo esas
  columnas; la contraseña solo acepta hashes bcrypt. Se usan desde **Mi cuenta** (`/cuenta`,
  el avatar de la barra superior), que además muestra el último acceso y deja elegir
  Automático / Claro / Oscuro.

En la capa web:

- **CSRF:** todo `POST` exige el token de la sesión (`app/csrf.py`), que va oculto en cada
  formulario (`{{ csrf_campo() }}`). Cerrar sesión también es un `POST`.
- **Intentos de login:** 5 fallos por IP y usuario (o 20 por IP) bloquean 15 minutos
  (`app/limite_login.py`). En el servidor, nginx limita además los `POST /login`.
- **Sesión:** dura 8 horas, se cierra tras 30 minutos sin actividad y se corta en el siguiente
  clic si la cuenta se desactiva o le cambian el rol (`app/dependencies.py`).
- **Mensajes:** los avisos de éxito o error viajan en la sesión, no en la URL (`app/avisos.py`).
  Nadie puede fabricar un enlace al sistema real con un mensaje falso.

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

Seguridad por fila: un docente que intenta registrar asistencia en la sección de otro.

```bash
docker exec -i -e PGPASSWORD="$APP_DB_PASSWORD" academico_postgres     psql -U "$APP_DB_USER" -d "$POSTGRES_DB" <<'SQL'
BEGIN;
SET LOCAL ROLE rol_docente;
SELECT set_config('app.docente_id', '1', true);
SELECT count(*) FROM academico_oltp.calificaciones;           -- solo las de sus secciones
INSERT INTO academico_oltp.asistencias (inscripcion_id, fecha_sesion, estado_asistencia)
SELECT i.inscripcion_id, DATE '2099-01-01', 'PRESENTE'
FROM academico_oltp.inscripciones i JOIN academico_oltp.secciones s USING (seccion_id)
WHERE s.docente_id <> 1 LIMIT 1;
ROLLBACK;
SQL
```

| Operación | Resultado |
|---|---|
| `SELECT` de notas como el docente 1 | solo las de sus secciones (4 964 de 131 872) |
| `INSERT` en la sección de otro docente | `ERROR: new row violates row-level security policy` |

Las pruebas `backend/tests/test_rls_docente.py` repiten estos intentos y otros (mover una
evaluación a otra sección, cruzar una evaluación propia con un estudiante ajeno) contra la base
real. `backend/tests/test_actas_db.py` recorre el ciclo del acta (cerrar, intentar modificar,
reabrir) y las funciones de cuenta. Las dos suites corren en transacciones que se revierten y se
omiten si PostgreSQL no está levantado.

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
> Streamlit no tiene login propio, escucha solo en `127.0.0.1` y, publicada, queda detrás de nginx con la
> sesión de la app web (ver «Despliegue en un servidor»).

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

