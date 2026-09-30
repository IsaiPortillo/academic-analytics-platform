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
│   ├── oltp/                  # Scripts DDL, triggers y roles operacionales (se auto-ejecutan)
│   ├── nosql/                 # Script de carga (Python) y consultas Cypher del grafo
│   └── dw/                    # DDL del modelo dimensional (Data Mart) — Fase 3
├── scripts/                   # Utilidades de datos y de desarrollo
│   ├── generator/              # Generador de datos sintéticos (Fase 1.2)
│   ├── benchmark/               # Benchmarks EXPLAIN ANALYZE (Fase 1.4)
│   └── setup-tailwind.sh       # Descarga el CLI de Tailwind y compila los estilos
├── backend/                   # Sistema transaccional operacional (FastAPI)
│   ├── app/                   # Configuración, modelos, routers y plantillas
│   │   ├── routers/            # matricula, calificaciones, asistencia, reportes, auth
│   │   ├── templates/          # Jinja2 (base.html + un template por módulo)
│   │   └── static/src/         # input.css (tokens Tailwind) -> se compila a static/app.css
│   └── scripts/                # Utilidades de administración (alta de usuarios)
├── etl/                       # Pipelines de extracción, transformación y carga — Fase 3
│   ├── config.py               # Credenciales del ETL (rol_etl, solo lectura)
│   ├── conexiones.py           # Conexión híbrida PostgreSQL + Neo4j (punto único)
│   ├── verificar_conexiones.py # Comprobación de conectividad y de solo-lectura
│   ├── extraccion.py           # Extracción de entidades OLTP (columnas explícitas)
│   ├── grafo.py                # Métricas de grafo y cuellos de botella (Cypher)
│   ├── transformacion.py       # Reglas de limpieza y enriquecimiento
│   ├── anonimizacion.py        # Verificación de que nada identificable sale al DW
│   ├── pipeline.py             # Orquestador: python -m etl.pipeline
│   ├── verificar_pipeline.py   # Nota = SCRUM-10 y bloqueo de fugas, en vivo
│   ├── tests/                  # Pruebas de las reglas (unittest, sin base de datos)
│   └── staging/                # Salida del pipeline (no versionada)
└── dashboard/                  # Interfaz interactiva de analítica en Streamlit — Fase 4
```

---

## 📚 Documentación adicional

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
- [ ] **3.3:** Diseño del modelo dimensional estrella (`dw_academico`) y carga incremental/controlada a hechos y dimensiones.

### Fase 4: Dashboard Analítico e Inteligencia de Negocios (Streamlit)
- [ ] **4.1:** Vista ejecutiva con los KPIs de costo y rendimiento, filtrados por período, carrera y departamento.
- [ ] **4.2:** Matriz de correlaciones, análisis por cohorte e identificación de los estudiantes que presentan el patrón de riesgo observado.
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
`06_bootstrap_rol_app` → `07_bootstrap_rol_etl` → `08_costos_institucionales`): crea el
esquema operacional, la tabla de usuarios de la aplicación, el rol de servicio de la app,
el rol de solo lectura del ETL y el catálogo de costos institucionales. No hay que
ejecutar ningún `.sql` a mano.

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

Streamlit se reserva para la **Fase 4 (dashboard analítico)**, donde su orientación a la
exploración de datos sí es la herramienta adecuada.

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

