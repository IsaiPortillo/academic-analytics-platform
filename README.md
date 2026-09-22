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
├── docs/                      # Documentación académica, diagramas y memorias
│   ├── diagramas/              # (pendiente — Fase 5)
│   └── memoria/                 # (pendiente — Fase 5)
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
`06_bootstrap_rol_app`): crea el esquema operacional, la tabla de usuarios de la aplicación y
el rol de servicio. No hay que ejecutar ningún `.sql` a mano.

> ⚠️ Esos scripts **solo corren la primera vez**. Si ya tenías el contenedor creado desde
> antes (por ejemplo, de un clone anterior) y cambias algo en `.env`, el cambio **no** se
> aplica solo. Para reinicializar desde cero (⚠️ borra todos los datos):
> `docker compose down -v && docker compose up -d`. Si no quieres perder datos, ver
> [Solución de problemas](#solución-de-problemas) más abajo.

### 3. Dependencias de Python

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r scripts/generator/requirements.txt
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
