# Dossier del proyecto

**Plataforma de Gestión Académica y Analítica de Rendimiento Estudiantil**
Grupo Adilman · Universidad de El Salvador, Facultad Multidisciplinaria Oriental
Curso de Especialización en Administración de Bases de Datos e Inteligencia de Negocios

> Documento de referencia completo, escrito para ser leído sin tener el repositorio delante.
> Estado al **10 de octubre de 2026**. Defensa: **28 y 29 de octubre de 2026**.

---

## 0. Cómo usar este documento

Está pensado para estudiar el proyecto a fondo y para discutirlo en voz alta. Dos cosas que
conviene saber antes de empezar:

- **Todas las cifras están verificadas ejecutando el sistema**, no estimadas. La última corrida
  completa de validación fue el 10 de octubre de 2026 sobre el commit `b05136c`.
- **Los datos son sintéticos**, generados con Faker. Reproducen la estructura de una carrera real
  pero no son datos de la UES. Esto importa cada vez que aparece una cifra: el proyecto demuestra
  un *método* de cálculo, no un hallazgo institucional.

La sección 15 reúne las preguntas abiertas y los puntos débiles. Si el objetivo es encontrar qué
falta, empezar por ahí y volver después al detalle.

---

## 1. Qué es el proyecto

Un sistema que integra el registro académico operacional de una carrera universitaria con una capa
analítica, para responder tres preguntas que hoy una institución no puede responder con sus propios
datos:

1. ¿Qué asignaturas concentran la reprobación?
2. ¿Qué factores la acompañan?
3. ¿Cuánto le cuesta a la institución?

Es un proyecto de graduación con dos criterios de éxito simultáneos: aprobar la defensa ante
jurado, y quedar en un estado razonablemente adoptable después.

### El contexto del curso, que condiciona el diseño

El docente aprobó el tema con una condición explícita: por sí solo «es más analítica que
inteligencia de negocios y no es un negocio». Por eso el **componente de costos** no es un extra,
es lo que hace que el proyecto califique.

Además fijó el **alcance analítico en los dos primeros niveles de Gartner**:

| Nivel | Pregunta | ¿Dentro del alcance? |
|---|---|---|
| Descriptivo | ¿Qué ocurrió? | Sí |
| Diagnóstico | ¿Por qué ocurrió? | Sí |
| Predictivo | ¿Qué ocurrirá? | **No** |
| Prescriptivo | ¿Qué conviene hacer? | **No** |

Esto tiene una consecuencia práctica de redacción: identificar estudiantes en riesgo **sí** entra
(se reconocen patrones ya observados en datos históricos), pero decir «alerta temprana» o
«predicción» describe trabajo que el proyecto no puede entregar.

### Requisitos mínimos que impuso el curso

- Sistema transaccional funcional (lenguaje libre)
- PostgreSQL obligatorio
- Una base NoSQL obligatoria, con justificación de cuál
- Separación OLTP / OLAP, y data marts si aplica
- Proceso ETL, sugerido en Python
- KPIs, métricas y preguntas de negocio definidos
- Dashboard
- Interpretación y recomendaciones

Y tres cosas que **no se aceptan**: solo un CRUD sin analítica; un dashboard construido sobre un
CSV; y un dashboard que consulte directamente las tablas transaccionales.

### El equipo

Tres personas: **Eliseo** (base de datos, seguridad, costos, memoria), **Isai** (frontend,
calificaciones, asistencia, reportes, dashboard) y **Edras** (matrícula, pipeline ETL, modelo
dimensional, análisis diagnóstico). Todos deben poder defender cualquier parte: el docente pregunta
a cualquiera del grupo y puede pedir demostraciones en vivo.

---

## 2. El problema, con números

Sobre el conjunto sintético de 8 períodos académicos (2022-I a 2025-II):

| Indicador | Valor |
|---|---|
| Inscripciones totales | 36.704 |
| Inscripciones cerradas (con resultado definitivo) | 32.966 |
| Reprobadas | 8.020 |
| **Tasa de reprobación** | **24,3 %** |
| Costo de matrícula total | USD 3.670.400 |
| **Costo de la reprobación** | **USD 802.000** |
| De ese costo, atribuible a repeticiones | 5.511 inscripciones |

El costo se calcula así: `unidades valorativas × costo por unidad valorativa del período`. El costo
por unidad valorativa está fijado en **USD 25, declarado como supuesto paramétrico**, no como cifra
oficial de la UES. Está escrito así dentro de la propia base de datos, en la columna `fuente` de la
tabla de costos.

### El hallazgo que distingue al proyecto

Las asignaturas no son independientes: forman una red de prerrequisitos. Modelada como grafo:

- **Programación I condiciona 10 de las 16 asignaturas** del plan.
- Programación II condiciona 7.
- La cadena de dependencias más larga es `PRG115 → PRG215 → ADS115 → SIF115 → BIN115`.

Reprobar Programación I no retrasa una materia: interrumpe la ruta hacia la mayor parte de la
carrera. Ese efecto en cascada es lo que un dashboard académico corriente no puede mostrar, y es la
justificación de haber incorporado una base de datos de grafos.

---

## 3. Arquitectura: cuatro capas

```
┌─ Capa 4 · Analítica ────────────────────────────────────────────┐
│  Streamlit (dashboard/) + vistas analíticas en el backend       │
│  Lee dw_academico. NUNCA el esquema operacional.                │
└──────────────────────────▲──────────────────────────────────────┘
┌─ Capa 3 · Integración (ETL) ─────────────────────────────────────┐
│  Python: extracción → transformación → verificación →  carga     │
│  Lee el OLTP con rol_etl. Escribe el DW con rol_dw_carga.        │
└──────────────────────────▲──────────────────────────────────────┘
┌─ Capa 2 · Sistema transaccional ─────────────────────────────────┐
│  FastAPI + Jinja2 + Tailwind. Matrícula, notas, asistencia,      │
│  reportes. La autorización la resuelve el motor, no este código. │
└──────────────────────────▲──────────────────────────────────────┘
┌─ Capa 1 · Persistencia ──────────────────────────────────────────┐
│  PostgreSQL 17: academico_oltp · auditoria · dw_academico        │
│  Neo4j 5: malla curricular como grafo dirigido                   │
└──────────────────────────────────────────────────────────────────┘
```

**Por qué dos motores**: el dominio tiene dos estructuras de naturaleza distinta. Los registros
académicos son tabulares y exigen integridad referencial. La malla curricular es un grafo dirigido
acíclico, y las preguntas que se le hacen son de recorrido transitivo, no de un salto.

---

## 4. Stack tecnológico

| Componente | Tecnología | Por qué |
|---|---|---|
| Motor relacional | PostgreSQL 17 | Integridad referencial estricta, disparadores, y un modelo de roles que permite resolver la autorización en el motor |
| Motor de grafos | Neo4j 5.20 Community (+ APOC) | Recorridos transitivos nativos; devuelve el camino, no solo los nodos alcanzados |
| Backend | FastAPI + Jinja2 | Separación de capas, control de sesión y roles, formularios reales |
| Frontend | Tailwind CSS v4 (binario standalone, sin Node.js) | Migrado desde Bootstrap en septiembre de 2026 |
| ORM | SQLAlchemy 2.0 (tipado, `Mapped`) | Mapea el esquema existente; **nunca** crea tablas |
| Contraseñas | bcrypt directo | Evita la incompatibilidad conocida entre passlib y bcrypt ≥ 4 |
| ETL | Python + pandas + SQLAlchemy + driver oficial de Neo4j | — |
| Dashboard | Streamlit + pandas | Orientado a exploración de datos, que es donde sí encaja |
| Infraestructura | Docker Compose | Reproducibilidad desde el repositorio, que es un entregable exigido |
| Datos de prueba | Faker | ~290.000 registros sintéticos |

---

## 5. Capa 1 — Persistencia

### 5.1 Esquema operacional: `academico_oltp`

Trece tablas en grupos funcionales:

| Grupo | Tablas |
|---|---|
| Estructura académica | `departamentos`, `carreras`, `materias` |
| Actores | `estudiantes`, `docentes`, `usuarios` |
| Tiempo y oferta | `periodos_academicos`, `secciones` |
| Hechos académicos | `inscripciones`, `evaluaciones`, `calificaciones`, `asistencias` |
| Costos | `costos_uv` |

Más el esquema `auditoria` con `log_cambios_notas`.

La cadena central:

```
estudiante ──> inscripcion ──> seccion ──> materia
                   │              └──> docente, periodo
                   ├──> calificacion ──> evaluacion (con su porcentaje)
                   └──> asistencia
```

### 5.2 Reglas de negocio que viven en el motor

Criterio de diseño constante: **si una regla debe cumplirse siempre, se impone en la base de datos,
no en la aplicación.** Una regla en Python se evade conectándose con `psql`; una restricción del
motor no.

| Regla | Mecanismo |
|---|---|
| La ponderación de evaluaciones de una sección no puede exceder 100 % | Disparador `BEFORE INSERT OR UPDATE` |
| Todo cambio de nota queda registrado con su autor | Disparador `AFTER UPDATE` |
| Un estudiante no se inscribe dos veces en la misma sección | `UNIQUE (estudiante_id, seccion_id)` |
| Una nota está entre 0 y 10 | `CHECK` |
| El escalafón docente es uno de cuatro valores | `CHECK` |

### 5.3 El modelo de seguridad — lo más defendible del proyecto

**El problema que resuelve**: en la mayoría de sistemas la autorización es código (`if rol ==
'docente'`). Si el programador olvida la comprobación en una ruta, no hay red; y cualquiera con las
credenciales de la aplicación puede conectarse por fuera, porque para la base de datos todo es el
mismo usuario.

**La solución, en tres piezas:**

1. **Los roles son del motor, no de la aplicación.** `rol_coordinador` y `rol_docente` existen en
   PostgreSQL con sus `GRANT`, y **no pueden iniciar sesión**: no son personas, son perfiles de
   permisos.

2. **La aplicación se conecta siempre como `rol_app`, creado `NOINHERIT`.** Aunque sea miembro de
   los dos roles, no hereda sus permisos: tiene que pedirlos. Si el código olvidara hacerlo, la
   consulta falla en vez de correr con permisos de más. **Falla cerrado por construcción.**

3. **Cada transacción cambia de rol** según quién inició sesión:

```python
ROLES_VALIDOS = frozenset({"rol_coordinador", "rol_docente"})

def get_db(request):
    db = SessionLocal()
    try:
        rol = (request.session.get("usuario") or {}).get("rol_db")
        if rol is not None:
            if rol not in ROLES_VALIDOS:
                raise HTTPException(status_code=403, ...)
            db.execute(text(f"SET LOCAL ROLE {rol}"))
        yield db
        db.commit()
    except Exception:
        db.rollback(); raise
    finally:
        db.close()
```

**Dos detalles por los que preguntan:**

- **¿Por qué `SET LOCAL ROLE` y no `SET ROLE`?** `LOCAL` acota el cambio a la transacción. Sin él,
  el rol queda pegado a la conexión física, y como las conexiones se reutilizan desde un *pool*, la
  siguiente petición heredaría el rol del usuario anterior. Fuga de privilegios silenciosa.
- **¿Por qué la lista blanca, si el rol ya viene de la base?** Porque `SET ROLE` **no admite
  parámetros vinculados**: el nombre hay que interpolarlo en el texto de la consulta, que es la
  forma de una inyección SQL. La lista blanca garantiza que solo dos cadenas literales lleguen ahí.

**Cómo se demuestra en vivo:**

```sql
SET ROLE rol_docente;
DELETE FROM academico_oltp.inscripciones WHERE inscripcion_id = 1;
-- ERROR:  permission denied for table inscripciones
```

El error lo produce el motor, no la aplicación.

### 5.4 La bitácora de auditoría

Cada cambio de nota se registra en `auditoria.log_cambios_notas`. El requisito es que sea
**inescribible para los roles auditados**: una bitácora que el auditado puede modificar no es
evidencia.

Eso choca con cómo funciona un disparador, que por omisión corre con los permisos de quien provoca
el cambio — y esos roles no tienen escritura sobre la bitácora. Una versión anterior del proyecto lo
resolvió concediéndoles `INSERT`, lo que funcionaba pero permitía fabricar entradas.

**La solución correcta es `SECURITY DEFINER`**: la función del disparador se ejecuta con los
permisos de su dueño. El rastro se escribe siempre y nadie más puede tocarlo.

**Detalle fino**: dentro de una función `SECURITY DEFINER`, `CURRENT_USER` es el *dueño* de la
función. Como la columna tenía `DEFAULT CURRENT_USER`, la bitácora habría registrado `postgres` en
todas las filas. Por eso el rol se escribe explícitamente leyendo el parámetro `role`, que conserva
el `SET ROLE` que hizo la aplicación. Además la función fija su `search_path`, obligatorio en toda
función `SECURITY DEFINER` para que quien llama no pueda anteponer un esquema propio.

Resultado demostrable:

```
 log_id | nota_anterior | nota_nueva |   usuario_db
--------+---------------+------------+-----------------
      1 |          7.64 |       9.10 | rol_docente
      2 |          9.10 |       7.64 | rol_coordinador
```

### 5.5 El catálogo de costos

Tabla `academico_oltp.costos_uv`: costo por unidad valorativa **por período**, porque el presupuesto
cambia cada año. Vive en el esquema operacional y no en el *warehouse* porque es dato institucional
de referencia que alguien mantiene en el tiempo, y el OLTP es la fuente de la que el ETL lee todo lo
demás.

Incluye una columna `fuente` que documenta de dónde sale la cifra. Hoy dice que es un supuesto
paramétrico pendiente de sustituir por el dato presupuestario oficial.

### 5.6 El grafo curricular

16 nodos `:Materia` unidos por relaciones `:REQUIERE_APROBADA`. Es un grafo dirigido acíclico.

Las dos consultas del proyecto:

```cypher
-- Materias cuello de botella: bloqueo en cascada
MATCH (base:Materia)<-[:REQUIERE_APROBADA*1..5]-(bloqueadas:Materia)
RETURN base.codigo, count(DISTINCT bloqueadas) AS MateriasBloqueadasEnCascada
ORDER BY MateriasBloqueadasEnCascada DESC;

-- Ruta crítica hacia la graduación
MATCH p = (meta:Materia {codigo:'BIN115'})-[:REQUIERE_APROBADA*]->(raiz:Materia)
WHERE NOT (raiz)-[:REQUIERE_APROBADA]->()
RETURN [n in nodes(p) | n.codigo], length(p) ORDER BY length(p) DESC;
```

El `*1..5` es el corazón: «sigue la relación entre uno y cinco saltos».

**Neo4j frente a MongoDB.** La respuesta débil es «porque es un grafo». La fuerte reconoce que
MongoDB también puede recorrer con `$graphLookup`; la diferencia es que devuelve el **conjunto** de
documentos alcanzados y no el **camino** que los une — y el camino es la respuesta que necesita el
reporte de materias críticas.

**Y la pregunta incómoda**: ¿por qué no un `WITH RECURSIVE` en PostgreSQL, que ya está? Se podría, y
para el bloqueo en cascada daría lo mismo. El curso exige un motor NoSQL y, dado ese requisito, la
malla es la única estructura del dominio genuinamente no relacional: es donde un motor de grafos
aporta algo real en vez de ser decorativo.

---

## 6. Capa 2 — Sistema transaccional

FastAPI servido con uvicorn en el puerto 8000, documentación de API en `/api/docs`.

| Módulo | Responsabilidad |
|---|---|
| `main.py` | Aplicación, middleware de sesión, montaje de routers |
| `config.py` | Credenciales desde el `.env`, nunca en código |
| `database.py` | Engine, sesión y el `SET LOCAL ROLE` por transacción |
| `models.py` | Mapeo de todo el esquema. **Nunca** `create_all()` |
| `security.py` | Hash y verificación de contraseñas con bcrypt |
| `dependencies.py` | `usuario_actual()`, `requiere_rol()` |
| `calculos.py` | Umbrales y fórmulas compartidas |
| `routers/` | `auth`, `matricula`, `calificaciones`, `asistencia`, `reportes`, `vista_ejecutiva`, `analisis_diagnostico` |

**Roles en la interfaz**: el coordinador ve los cuatro módulos; el docente no ve matrícula ni
reportes (devuelven 403, no una página vacía).

### El error más instructivo del proyecto

Durante la Fase 2 todos los usuarios se creaban inactivos y el inicio de sesión fallaba siempre. La
causa: las columnas con `DEFAULT` en el DDL no estaban declaradas con `server_default` en el modelo,
así que SQLAlchemy las incluía en el `INSERT` con un **NULL explícito** — y un NULL explícito
*anula* el `DEFAULT` de PostgreSQL.

La lección que el proyecto adoptó como norma: **el error no se encontró leyendo el código, se
encontró ejecutando la aplicación.** De ahí que todo se verifique contra el sistema corriendo.

### Los reportes

Dos decisiones que conviene saber justificar:

- **La agregación ocurre en SQL**, con `GROUP BY`, `HAVING` y `COUNT(CASE WHEN ...)`. Traer 36.000
  filas a memoria para contarlas en un bucle sería más lento y no escalaría.
- **El CSV se transmite en flujo** con `StreamingResponse`, así que nunca se arma entero en memoria,
  y lleva un BOM UTF-8 para que Excel no rompa las tildes.

Las funciones de consulta son compartidas entre la vista web y la exportación, de modo que no pueden
divergir.

---

## 7. Capa 3 — El proceso ETL

```
  extracción OLTP  ─┐
                    ├─> transformación ─> verificación de ─> staging ─> carga al
  métricas Neo4j   ─┘                      anonimización                modelo dimensional
   (rol_etl, solo lectura)                                         (rol_dw_carga, escritura)
```

| Módulo | Responsabilidad |
|---|---|
| `conexiones.py` | Punto único de acceso a ambos motores |
| `extraccion.py` | Extrae del OLTP; agrega con `GROUP BY` en el motor |
| `grafo.py` | Métricas de dependencia curricular desde Neo4j |
| `transformacion.py` | Limpieza, clasificación y enriquecimiento |
| `anonimizacion.py` | Verificación en tres barreras |
| `pipeline.py` | Orquesta extracción, transformación y verificación |
| `carga.py` | Escribe el modelo dimensional en una transacción |
| `validar_dw.py` | 66 verificaciones contra fuentes independientes |
| `verificar_conexiones.py` | Comprobación de conectividad y de solo-lectura |

### Anonimización: lista blanca, no lista negra

El carné llega ya hasheado con SHA-256 desde el generador, así que el ETL **no anonimiza: verifica**
que la anonimización se cumple. Tres barreras:

1. **Lista blanca de columnas.** Solo pueden salir las columnas enumeradas; cualquier otra detiene
   el pipeline. Es lista blanca y no negra a propósito: una lista negra solo atrapa lo que alguien
   previó, mientras que una blanca obliga a editar el control al agregar un atributo, y ese *diff*
   es el que se revisa.
2. **Validación de contenido.** El `carnet_hash` debe tener forma de SHA-256 y ser único.
3. **Aislamiento de credenciales** respecto del conjunto analítico.

### Limpieza: clasificar, nunca imputar

Ante un dato que no permite calcular un resultado, el ETL deja el resultado nulo y **clasifica el
caso**, en lugar de inventar un cero. Un cero imputado a un retiro contaminaría todas las medias.

| Clasificación | Inscripciones | Significado |
|---|---|---|
| APROBADO | 24.946 | Cerrada con nota ≥ 6,00 |
| REPROBADO | 8.020 | Cerrada por debajo del mínimo |
| RETIRADO | 1.842 | No computa como reprobación |
| SIN_CIERRE | 1.896 | Aún en curso a la fecha de corte |

Las retiradas y las sin cierre quedan **fuera del denominador** de la tasa de reprobación, que se
calcula sobre las 32.966 cerradas.

### Trazabilidad de la carga

Cada ejecución deja una fila en `dw_academico.carga_control` con métricas en JSON:

| Métrica | Última corrida (10 oct) |
|---|---|
| Duración | 3,35 segundos |
| Filas de hechos | 36.704 |
| Inscripciones sin costo asignado | 0 |
| Inscripciones cerradas con nota incompleta | 0 |
| Materias sin nodo en el grafo | ninguna |
| Nodos del grafo sin materia en el OLTP | ninguno |
| Cuellos de botella detectados | PRG115, PRG215 |
| Inscripciones no retiradas sin asistencia | 22.862 |

Esa última cifra es una **limitación del conjunto de datos**, no un defecto del proceso: el
generador solo produjo asistencia para 3 de los 8 períodos. El ETL la detecta, la cuantifica y la
registra en lugar de rellenarla.

### Separación de privilegios

Dos roles mutuamente excluyentes: `rol_etl` solo lee el OLTP; `rol_dw_carga` escribe el DW pero no
puede leer el OLTP. Ninguno puede hacer lo del otro, y ambas restricciones están verificadas con
intentos deliberados que el motor rechaza.

---

## 8. Capa 4 — Data warehouse y analítica

### El modelo dimensional: `dw_academico`

**Grano del hecho: una inscripción** (un estudiante cursando una sección en un período).

| Tabla | Filas | Papel |
|---|---|---|
| `fact_inscripcion` | 36.704 | Hecho; 24 columnas |
| `dim_estudiante` | 1.500 | Anonimizada: solo el resumen del carné |
| `dim_seccion` | 194 | Turno, cupo, número |
| `dim_materia` | 16 | Enriquecida con métricas del grafo |
| `dim_docente` | 20 | Escalafón y departamento, sin datos personales |
| `dim_periodo` | 8 | Incluye el costo por UV vigente |
| `dim_carrera` | 1 | Con su departamento, habilita el data mart |
| `carga_control` | — | Metadatos y calidad de cada ejecución |

**Las medidas:**

| Medida | Definición |
|---|---|
| `costo_inscripcion` | UV × costo por UV del período |
| `costo_reprobacion` | Lo anterior cuando resulta reprobada |
| `costo_repeticion` | Lo anterior cuando el intento es el segundo o posterior |
| `nota_final` | Promedio ponderado por el porcentaje de cada evaluación |
| `porcentaje_asistencia` | Sesiones presente sobre sesiones registradas |

**Dos decisiones de modelado que no son obvias:**

- El costo por UV vive en `dim_periodo`, no en una dimensión propia: es un atributo del período, y
  una dimensión de un solo atributo añadiría una unión sin aportar análisis.
- `dim_materia` incorpora `dependientes_totales`, `indice_bloqueo` y `es_cuello_botella`. Ahí se
  materializa la integración de los dos motores: una propiedad calculada en Neo4j queda disponible
  para segmentar hechos relacionales.

### Estrategia de carga

**Recarga completa dentro de una sola transacción.** Si falla a mitad, el `ROLLBACK` deja el DW
intacto, y mientras dura la carga el dashboard sigue viendo la versión anterior completa, nunca una
mezcla. Con 36.704 hechos en 3,35 segundos, el costo de recargar todo es despreciable frente a la
complejidad de una carga incremental. **Debería revisarse si el volumen creciera uno o dos órdenes
de magnitud.**

### Estrella frente a las alternativas

| Enfoque | Qué aporta | Por qué no |
|---|---|---|
| **Estrella** | Dimensiones desnormalizadas, menos uniones | **Elegido** |
| Copo de nieve | Menos redundancia | Añade uniones para ahorrar un espacio irrelevante a esta escala |
| Data Vault | Trazabilidad histórica y múltiples fuentes heterogéneas | Dos fuentes controladas, sin requisito de historiar: la complejidad no se paga |

### La validación: 66 verificaciones

Lo más sólido que tiene el proyecto. Se contrastan contra **fuentes independientes**, no contra el
propio proceso:

| Grupo | Contra qué |
|---|---|
| Completitud | Conteos del esquema operacional |
| Costo | SQL independiente escrito en el validador, que **no** reutiliza el ETL |
| Sistema transaccional | Las mismas funciones de los reportes del coordinador |
| Correlaciones | `corr()` de PostgreSQL contra pandas |
| Particiones | Cada segmentación debe repartir exactamente el total |
| Seguridad y anonimización | Privilegios reales del motor y catálogo del DW |
| Cruce relacional-grafo | Área de cada materia en Neo4j |

Que el costo se recalcule con SQL propio es lo que convierte la validación en evidencia: si ambos
caminos compartieran código, coincidirían aunque los dos estuvieran mal.

La corrida del 10 de octubre dio los **mismos 66 resultados** que la del 5 de octubre, en otra
máquina y con el DW reconstruido desde cero. El pipeline es reproducible.

### El dashboard

Streamlit en `dashboard/app.py`, con rol de solo lectura `rol_dashboard` que **no puede leer el
OLTP** (verificado). Muestra KPIs de costo, ranking de materias por costo de reprobación, evolución
por período, y filtros por período, carrera y departamento.

El análisis diagnóstico vive en el backend (`indicadores_diagnostico.py`,
`routers/analisis_diagnostico.py`): correlaciones, cohortes, segmentación por turno, área y ciclo, e
identificación del patrón de riesgo.

**Un resultado que hay que saber explicar**: la correlación entre asistencia y nota es despreciable
(r = +0,015). No es un fallo del análisis — el generador crea la asistencia al azar, sin dependencia
de la nota. Con datos reales podría aparecer. Está documentado.

---

## 9. Qué trae el repositorio

```
academic-analytics-platform/
├── README.md                  # Puesta en marcha, 12 pasos, y decisiones de stack
├── PRODUCT.md                 # Contexto de producto y principios
├── DESIGN.md                  # Sistema de diseño de la interfaz
├── docker-compose.yml         # PostgreSQL 17 + Neo4j 5
├── database/
│   ├── oltp/                  # 14 scripts: DDL, roles, costos, DW
│   └── nosql/                 # Carga del grafo y consultas Cypher
├── backend/                   # FastAPI: 13 módulos, 7 routers, 4 suites de prueba
├── etl/                       # 10 módulos del pipeline + pruebas
├── dashboard/                 # Streamlit
├── scripts/
│   ├── generator/             # Generador de datos sintéticos (Faker)
│   ├── benchmark/             # EXPLAIN ANALYZE
│   └── analisis/              # costo_reprobacion.sql
└── docs/
    ├── recorrido_del_sistema.md   # Cómo probar todo y guion de defensa
    ├── validacion/                # Registro de las 66 verificaciones
    ├── diagramas/                 # Modelo dimensional (SVG y PNG)
    └── memoria/                   # Los 21 capítulos y guías de redacción
```

**Scripts de base de datos**, en orden de ejecución:

| Script | Qué hace |
|---|---|
| `01_init_oltp_academico.sql` | Esquema operacional, disparadores, roles RBAC |
| `05_usuarios_auth.sql` | Tabla de usuarios de la aplicación |
| `06_bootstrap_rol_app.sh` | Crea `rol_app` LOGIN NOINHERIT |
| `07_bootstrap_rol_etl.sh` | Habilita el login de `rol_etl` |
| `08_costos_institucionales.sql` | Catálogo de costos y vista de costo por materia |
| `09_fix_auditoria_security_definer.sql` | Corrige la auditoría para que no sea falsificable |
| `10_dw_academico.sql` | Esquema estrella |
| `11_bootstrap_rol_dashboard.sh` | Rol de solo lectura del dashboard |
| `12_dw_diagnostico.sql` | Estructuras del análisis diagnóstico |
| `13_dw_cierre_scrum35.sql` | Dimensiones de docente y sección |
| `14_bootstrap_rol_dw_carga.sh` | Rol de escritura del DW |

> **Trampa importante**: estos scripts se ejecutan **solo en el primer arranque** sobre un volumen
> vacío. Si tu contenedor es anterior a un script nuevo, hay que aplicarlo a mano. Está documentado
> en la sección de solución de problemas del README.

---

## 10. Números del proyecto

| Dato | Valor |
|---|---|
| Registros académicos totales | ~290.000 |
| Estudiantes / docentes | 1.500 / 20 |
| Inscripciones / calificaciones / asistencias | 36.704 / 131.864 / 120.000 |
| Materias / secciones / períodos | 16 / 194 / 8 |
| Relaciones de prerrequisito | 16 |
| Tasa de reprobación global | 24,3 % (8.020 de 32.966) |
| Costo de reprobación | USD 802.000 |
| Materias que bloquea Programación I | 10 de 16 |
| Umbrales del sistema | Aprobación 6,00 · Riesgo 3 ausencias |
| Duración de la carga del DW | 3,35 segundos |
| Verificaciones de validación | 66 de 66 correctas |

---

## 11. Las decisiones y su porqué

Resumen de todo lo anterior, para repasar rápido:

| Decisión | Razón en una línea |
|---|---|
| Autorización en el motor | Una regla en código se evade conectándose por fuera |
| `rol_app` NOINHERIT | Falla cerrado si el código olvida cambiar de rol |
| `SET LOCAL ROLE` | Sin `LOCAL`, el rol se queda pegado a la conexión del *pool* |
| Lista blanca de roles | `SET ROLE` no admite parámetros vinculados |
| Auditoría `SECURITY DEFINER` | El auditado no debe poder escribir su propio expediente |
| Neo4j para la malla | Devuelve el camino, no solo los nodos alcanzados |
| Costo en `dim_periodo` | Es un atributo del período, no una dimensión |
| Costo en el OLTP y no en el DW | Es dato institucional de referencia; el OLTP es la fuente |
| Recarga completa | Atomicidad frente al consumidor, a un costo despreciable |
| Esquema estrella | Dos fuentes controladas; Data Vault no se paga |
| Clasificar y no imputar | Un cero inventado contamina todas las medias |
| Lista blanca en anonimización | Una lista negra solo atrapa lo que alguien previó |
| Agregación en SQL | El motor está optimizado para eso |
| `server_default` en los modelos | Un NULL explícito anula el `DEFAULT` de PostgreSQL |
| Nunca `create_all()` | La fuente de verdad son los scripts versionados |

---

## 12. Estado actual

### Terminado y verificado

- **Fase 1** — Base de datos operacional, datos sintéticos, grafo curricular, benchmarks.
- **Fase 2** — Sistema transaccional completo con RBAC en el motor.
- **Fase 3** — Conexión híbrida, modelo de costos, pipeline ETL, modelo dimensional y carga.
- **Fase 4, parcial** — Vista ejecutiva y análisis diagnóstico.

### Pendiente

| Qué | Ticket | Estado |
|---|---|---|
| Visualización interactiva de la red curricular | SCRUM-46 | Los datos están calculados; falta dibujarla (no hay PyVis ni NetworkX) |
| Memoria: entrega 2 (12 oct) | SCRUM-40 | Por hacer |
| Memoria: entrega 3 (19 oct) | SCRUM-41 | Solo el diagrama; los capítulos 12, 13 y 14 sin escribir |
| Memoria: entrega 4 (23 oct) | SCRUM-42 | Por hacer |
| Preparación de la defensa | SCRUM-43 | Por hacer |

**El riesgo real del proyecto no es técnico: es que el sistema va muy por delante del documento.**
La calificación se reparte entre ambos.

---

## 13. Defectos conocidos y limitaciones

Conviene reconocerlos antes de que los encuentre el jurado:

1. **Asistencia solo en 3 de los 8 períodos.** El generador no la produjo para el resto, así que los
   reportes del período más reciente salen vacíos y parecen rotos. Hay que usar `?periodo_id=1`.
2. **Ningún período está marcado como activo.** La aplicación deduce el vigente.
3. **La correlación asistencia-nota es nula** porque el generador las crea independientes. Es una
   propiedad de los datos sintéticos, no un hallazgo.
4. **El costo por UV es un supuesto**, no una cifra oficial.
5. **El DDL del DW está en `database/oltp/`** y `database/dw/` sigue vacío pese a estar declarado en
   el README. Inconsistencia visible en el repositorio.
6. **Falta el diagrama entidad-relación** del modelo operacional.
7. **Los scripts de primer arranque no se reejecutan**, lo que obliga a aplicarlos a mano en
   entornos existentes. Es una fricción real para el equipo.

---

## 14. Cómo probarlo todo

```bash
docker compose up -d                              # PostgreSQL + Neo4j
python scripts/generator/02_generador_datos_sinteticos.py
python database/nosql/03_cargar_grafo_neo4j.py    # el grafo arranca vacío
python backend/scripts/crear_usuario.py --demo --password demo1234
cd backend && uvicorn app.main:app --reload       # http://localhost:8000
python -m etl.verificar_conexiones                # 3 comprobaciones
python -m etl.carga                               # recarga el DW
python -m etl.validar_dw                          # 66 verificaciones
streamlit run dashboard/app.py                    # vista ejecutiva
```

Usuarios de prueba: `coordinador` y `docente`, contraseña `demo1234`.

---

## 15. Preguntas abiertas y puntos para discutir

Esto es lo que conviene examinar con ojo crítico:

### Sobre el alcance y el encuadre

1. ¿El componente de costos está suficientemente desarrollado, o sigue siendo una multiplicación
   simple adherida a un proyecto académico? ¿Qué más haría falta para que sea genuinamente
   inteligencia de negocios?
2. ¿Hay algún punto donde el proyecto todavía suene predictivo y se nos haya escapado?
3. El docente pidió «profundizar con descubrimiento y minería de datos hasta llegar a un análisis
   específico» en el nivel diagnóstico. ¿El análisis actual llega a esa profundidad o se queda en
   correlaciones y segmentaciones?

### Sobre el diseño técnico

4. ¿La recarga completa del DW es defendible, o un jurado esperaría carga incremental con
   dimensiones de cambio lento (SCD)? El modelo actual no historiza cambios en las dimensiones.
5. `dim_carrera` tiene **una sola fila**. ¿Una dimensión de un solo valor tiene sentido, o es un
   artefacto del conjunto de datos?
6. ¿Falta una dimensión de tiempo propiamente dicha (fecha, mes, trimestre)? Hoy el tiempo se
   modela solo como período académico.
7. El hecho mezcla medidas de costo, académicas y de asistencia con banderas booleanas. ¿Conviene
   separarlo en más de un hecho, o el grano único es correcto?

### Sobre lo que falta

8. ¿Cuánto pesa realmente la visualización de la red curricular (SCRUM-46) en la nota, dado que el
   análisis de cuellos de botella ya existe en texto y tabla?
9. ¿Es obligatorio Power BI además de Streamlit? El docente dijo «la idea es llegar también a Power
   BI» y nunca se aclaró.
10. ¿Cómo se declara el uso de IA en la memoria? El docente iba a enviar el formato y no llegó.

### Sobre la defensa

11. ¿Qué pregunta del jurado dejaría al proyecto peor parado, y está preparada la respuesta?
12. Los datos son sintéticos: ¿cómo se presenta eso sin que parezca una debilidad del trabajo?

---

## 16. Glosario

| Término | En una frase |
|---|---|
| OLTP | Sistema transaccional: registra las operaciones del día a día |
| OLAP | Procesamiento analítico: consultas agregadas sobre datos históricos |
| ETL | Extracción, transformación y carga del operacional al analítico |
| Esquema estrella | Una tabla de hechos rodeada de dimensiones desnormalizadas |
| Tabla de hechos | Los sucesos medibles, con sus medidas numéricas |
| Dimensión | El contexto por el que se filtra o agrupa un hecho |
| Grano | Qué representa exactamente una fila del hecho |
| Data mart | Subconjunto del warehouse orientado a un área o departamento |
| RBAC | Control de acceso basado en roles |
| `NOINHERIT` | Rol que no hereda los permisos de los roles a los que pertenece |
| `SECURITY DEFINER` | Función que se ejecuta con los permisos de su dueño |
| Unidad valorativa | Unidad de medida académica; base del cálculo de costo |
| Materia cuello de botella | Aquella de la que dependen muchas otras en la malla |
| Supuesto paramétrico | Valor adoptado y declarado como tal, no obtenido de una fuente oficial |
