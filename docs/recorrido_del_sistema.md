# Recorrido del sistema

Guía para probar el proyecto completo de punta a punta y entender qué hace cada pieza. Cada comando
viene con la salida real que produjo el 30 de septiembre de 2026; si lo que te sale difiere mucho,
algo está distinto en tu entorno y vale la pena averiguar qué.

Se recorre en capas, de abajo hacia arriba: base de datos → seguridad → aplicación → grafo → ETL.
Al final hay un guion de defensa y la lista honesta de lo que todavía no funciona.

> Todos los comandos se ejecutan desde la raíz del repositorio. Los que consultan la base cargan las
> credenciales del `.env` con `set -a && . ./.env && set +a`, así no se escriben contraseñas a mano.

---

## 0. Levantar el entorno

```bash
docker compose up -d
docker compose ps
```

Deben quedar los dos contenedores arriba:

```
academico_neo4j      Up   0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp
academico_postgres   Up   0.0.0.0:5433->5432/tcp
```

Si alguno no aparece, lo más probable es un conflicto de puertos con otro proyecto de Docker. Mira
la sección «Solución de problemas» del [README](../README.md).

---

## 1. La base operacional

El sistema transaccional vive en el esquema `academico_oltp`. Esto cuenta lo que hay dentro:

```bash
set -a && . ./.env && set +a
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT 'calificaciones' t, count(*) FROM academico_oltp.calificaciones
UNION ALL SELECT 'asistencias', count(*) FROM academico_oltp.asistencias
UNION ALL SELECT 'inscripciones', count(*) FROM academico_oltp.inscripciones
UNION ALL SELECT 'estudiantes', count(*) FROM academico_oltp.estudiantes
ORDER BY 2 DESC;"
```

| Tabla | Filas |
|---|---|
| calificaciones | 131,864 |
| asistencias | 120,000 |
| inscripciones | 36,704 |
| estudiantes | 1,500 |

Son unas 290,000 filas en total, todas sintéticas (Faker). Nunca entra información real de un
estudiante.

> **Cuidado con una trampa**: si consultas `pg_stat_user_tables` para ver el conteo, te va a dar
> cero después de recrear el contenedor. Eso son estadísticas del planificador, no datos. Cuenta
> siempre con `count(*)`.

---

## 2. El modelo de seguridad

Esta es la parte más defendible del proyecto y la que conviene tener dominada: **la autorización no
se resuelve en Python, la resuelve PostgreSQL**. La aplicación se conecta siempre como `rol_app`,
que es `NOINHERIT`, y cada transacción hace `SET LOCAL ROLE` al rol del usuario que inició sesión.
A partir de ahí mandan los `GRANT` del motor.

### 2.1 Los roles

```bash
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT rolname, rolcanlogin AS puede_entrar, rolinherit AS hereda
FROM pg_roles WHERE rolname LIKE 'rol_%' ORDER BY rolname;"
```

```
     rolname     | puede_entrar | hereda
-----------------+--------------+--------
 rol_app         | t            | f
 rol_coordinador | f            | t
 rol_docente     | f            | t
 rol_etl         | t            | t
```

Lo que hay que entender de esta tabla:

- `rol_app` **puede entrar pero no hereda** (`NOINHERIT`). Es el usuario de servicio de la web. Al
  no heredar, si el código olvidara hacer `SET LOCAL ROLE`, la consulta falla en vez de correr con
  permisos de más. Falla cerrado por construcción.
- `rol_coordinador` y `rol_docente` **no pueden entrar**: no son personas, son perfiles de permisos.
  Se llega a ellos solo con `SET ROLE`.
- `rol_etl` entra por su cuenta porque el pipeline se conecta directo, y solo tiene `SELECT`.

### 2.2 La demostración: un docente no puede borrar una matrícula

```bash
printf "SET ROLE rol_docente;\nDELETE FROM academico_oltp.inscripciones WHERE inscripcion_id = 1;\n" \
| docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

```
ERROR:  permission denied for table inscripciones
```

Ese error lo produce el motor, no la aplicación. Es la diferencia entre «el sistema valida permisos»
y «el sistema **no puede** saltarse los permisos». Un sistema que solo comprueba roles en código no
puede afirmar lo mismo con honestidad.

### 2.3 El ETL no puede escribir

```bash
.venv/bin/python -m etl.verificar_conexiones
```

```
  [OK] Lectura OLTP como 'rol_etl': 1,500 estudiantes, 36,704 inscripciones
  [OK] Lectura Neo4j: 16 materias, 16 relaciones de prerrequisito
  [OK] Escritura rechazada por PostgreSQL: permission denied for table estudiantes
```

La tercera línea es la importante: el script **intenta escribir a propósito** y lo correcto es que
falle. Que el ETL sea de solo lectura no depende de que quien escriba el pipeline se porte bien.

---

## 3. La aplicación web

```bash
.venv/bin/python -m uvicorn --app-dir backend app.main:app --reload   # en Git Bash: .venv/Scripts/python
```

Queda en `http://localhost:8000`, con la documentación de la API en `/api/docs`. Se lanza
desde la raíz y ocupa esa terminal: los comandos siguientes van en otra.

Usuarios de prueba (contraseña `demo1234` en ambos):

| Usuario | Rol | Qué ve |
|---|---|---|
| `coordinador` | `rol_coordinador` | Los cuatro módulos |
| `docente` | `rol_docente` | Calificaciones y asistencia |

### 3.1 Comprobar que los roles se respetan

Entra como `docente` e intenta abrir `http://localhost:8000/matricula`. Debe responder **403**, no
una página vacía ni un error feo. Lo mismo con `/reportes`.

Comprobado por ruta:

| Ruta | coordinador | docente | sin sesión |
|---|---|---|---|
| `/` | 200 | 200 | 303 → `/login` |
| `/matricula` | 200 | **403** | 303 |
| `/calificaciones` | 200 | 200 | 303 |
| `/asistencia` | 200 | 200 | 303 |
| `/reportes` | 200 | **403** | 303 |

### 3.2 Los reportes

`/reportes/asistencia` y `/reportes/notas-finales`, cada uno con su exportación a CSV.

> **Importante para probarlos**: por defecto abren el período más reciente (2025-II), que **no tiene
> asistencias registradas**, así que se ven vacíos y parecen rotos. No lo están: el generador de
> datos solo creó asistencias para los tres primeros períodos. Usa `?periodo_id=1` (2022-I) para ver
> el reporte con datos reales.

```bash
curl -s -b cookies.txt "http://localhost:8000/reportes/asistencia/csv?periodo_id=1" | head -3
```

```
estudiante_id,codigo_materia,materia,seccion,estado_inscripcion,sesiones,presentes,ausentes,justificados,porcentaje_asistencia
624,PRG315,Programación III,1,FINALIZADO,10,2,7,1,20
405,ACA115,Álgebra Vectorial y Matrices,2,FINALIZADO,10,4,6,0,40
```

El CSV empieza con un BOM UTF-8 para que Excel no rompa las tildes, y se transmite en streaming: no
se arma entero en memoria.

Con `&solo_riesgo=true` el mismo reporte baja de 4,354 filas a **644 estudiantes en riesgo** (3 o más
ausencias). Ese umbral está en `backend/app/routers/reportes.py` como `UMBRAL_FALTAS_RIESGO`, y es el
mismo que debe usar el dashboard de la Fase 4.

---

## 4. El grafo curricular

Las dos consultas del proyecto están en
[`database/nosql/cypher_queries.cql`](../database/nosql/cypher_queries.cql) y se pueden pegar tal
cual en el Neo4j Browser (`http://localhost:7474`).

### 4.1 Materias cuello de botella

```cypher
MATCH (base:Materia)<-[:REQUIERE_APROBADA*1..5]-(bloqueadas:Materia)
RETURN base.codigo, count(DISTINCT bloqueadas) AS MateriasBloqueadasEnCascada
ORDER BY MateriasBloqueadasEnCascada DESC;
```

| Materia | Bloquea en cascada |
|---|---|
| Programación I | **10** de 16 |
| Programación II | 7 |
| Matemática I | 3 |

**Programación I bloquea 10 de las 16 materias del plan.** Ese es el hallazgo que justifica haber
metido una base de grafos: reprobarla no cuesta una materia, cuesta el avance de media carrera.

### 4.2 Ruta crítica hacia la graduación

La cadena más larga de prerrequisitos hasta Inteligencia de Negocios:

```
PRG115 → PRG215 → ADS115 → SIF115 → BIN115   (profundidad 4)
```

Fíjate que el resultado es el **camino**, no solo el conjunto de materias. Esa es exactamente la
razón por la que se eligió Neo4j sobre MongoDB, y está argumentada en el README.

---

## 5. La pregunta de negocio, de punta a punta

Aquí se junta todo: notas del OLTP, ponderación de evaluaciones y costo institucional. Responde
«¿cuánto le costó a la institución la reprobación en 2022-I, materia por materia?».

El script está en [`scripts/analisis/costo_reprobacion.sql`](../scripts/analisis/costo_reprobacion.sql):

```bash
docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < scripts/analisis/costo_reprobacion.sql
```

| Materia | Reprobados | Costo unitario | Costo total |
|---|---|---|---|
| MAT315 | 126 | $100.00 | **$12,600.00** |
| BAD215 | 120 | $100.00 | $12,000.00 |
| ARC115 | 83 | $100.00 | $8,300.00 |
| ACA115 | 81 | $100.00 | $8,100.00 |

Con una tasa de reprobación del **24.0%** en ese período (989 de 4,122 inscripciones finalizadas).

> El costo por unidad valorativa sembrado son **USD 25.00 y es un supuesto paramétrico**, no una
> cifra oficial de la UES. Está declarado así en la columna `fuente` de `academico_oltp.costos_uv`.
> Si aparece el dato oficial, se sustituye y todos los números se recalculan solos.

---

## 6. Lo que hoy NO funciona

Ser honesto con esto vale más que fingir que todo está perfecto, sobre todo si el jurado pregunta.

| Problema | Impacto | Estado |
|---|---|---|
| Solo hay asistencias en los 3 primeros períodos de 8 | Los reportes del período actual salen vacíos y parecen rotos | Sin arreglar |
| Ningún período está marcado como `activo` | La app tiene que deducir el período vigente | Sin arreglar |
| El dashboard (Fase 4) no existe | Es el entregable del 23 de octubre | En curso |
| El data warehouse (Fase 3.3) no existe | Bloquea al dashboard | En curso |

### Corregido: la auditoría de notas

Si tu contenedor es anterior a octubre de 2026, corregir una nota fallaba con
`permission denied for schema auditoria`. La causa era que el trigger de auditoría escribía en la
bitácora con los permisos de quien hacía el `UPDATE`, y los roles de la aplicación no los tienen.

Ya está resuelto con `SECURITY DEFINER` en
[`09_fix_auditoria_security_definer.sql`](../database/oltp/09_fix_auditoria_security_definer.sql):
la función se ejecuta con los permisos de su dueño, así que escribe el rastro aunque el rol auditado
no pueda tocarlo. Aplícalo si tu base es anterior; es idempotente.

Esto además dejó una demostración muy buena para la defensa: cambia una nota como `rol_docente`,
revíértela como `rol_coordinador`, y consulta la bitácora.

```
 log_id | nota_anterior | nota_nueva |   usuario_db
--------+---------------+------------+-----------------
      1 |          7.64 |       9.10 | rol_docente
      2 |          9.10 |       7.64 | rol_coordinador
```

Cada cambio queda atribuido a su rol, y ninguno de los dos puede insertar, modificar ni borrar
entradas de esa bitácora: si `rol_docente` lo intenta, obtiene `permission denied for schema
auditoria`. El rastro solo lo escribe el trigger.

---

## 7. Guion de defensa, 10 minutos

Un orden que cuenta la historia completa sin perderse en detalles:

1. **El problema** (1 min). Programación I bloquea 10 de 16 materias; la reprobación en 2022-I costó
   $98,900 en una sola carrera. Abre con el número, no con la arquitectura.
2. **El sistema transaccional** (2 min). Entra como coordinador, muestra matrícula y reportes. Entra
   como docente y muestra que matrícula le da 403.
3. **La seguridad está en el motor** (2 min). En `psql`: `SET ROLE rol_docente` + `DELETE` →
   `permission denied`. Explica el `NOINHERIT` de `rol_app` y el `SET LOCAL ROLE` por transacción.
   Es el punto más fuerte que tiene el proyecto.
4. **El grafo** (2 min). Neo4j Browser, la consulta de cuellos de botella, y por qué un documental no
   habría dado el camino.
5. **El ETL** (2 min). `python -m etl.verificar_conexiones`, señalando la tercera línea: el ETL no
   puede escribir, y lo garantiza PostgreSQL.
6. **La pregunta de negocio** (1 min). El costo de reprobación por materia, aclarando que el costo
   por UV es un supuesto documentado.

**Las tres preguntas que conviene llevar preparadas:**

- *¿Por qué Neo4j y no MongoDB?* — `$graphLookup` devuelve los documentos alcanzados, no el camino
  que los une, y el camino es lo que necesita el reporte de materias críticas.
- *¿Por qué no un `WITH RECURSIVE` en PostgreSQL?* — Se podría, y para el bloqueo en cascada daría lo
  mismo. El curso exige un motor NoSQL, y la malla es la única estructura del dominio que es
  genuinamente no relacional.
- *¿De dónde sale el costo por unidad valorativa?* — Es un supuesto paramétrico declarado como tal.
  No inventamos una cifra presentándola como oficial.
