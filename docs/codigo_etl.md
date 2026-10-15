# Código fuente del proceso ETL

**Plataforma de Gestión Académica y Analítica de Rendimiento Estudiantil** · Grupo Adilman · UES-FMO

Volcado completo del paquete `etl/`, tal como está en `develop` (commit `a019ec7`) al 11 de octubre de 2026.
Los archivos van en orden de ejecución del pipeline, no alfabético.

> Los bloques usan delimitadores de cuatro tildes invertidas porque `validar_dw.py` genera
> Markdown y contiene bloques de tres dentro de sus cadenas.

## Flujo

````
  extracción OLTP  ─┐
                    ├─> transformación ─> verificación de ─> staging ─> carga al
  métricas Neo4j   ─┘                      anonimización                modelo dimensional
   (rol_etl, solo lectura)                                         (rol_dw_carga, escritura)
````

## Índice

| # | Archivo | Líneas | Qué hace |
|---|---|---|---|
| 1 | [`etl/__init__.py`](#1-init) | 5 | Marca `etl/` como paquete. Por eso todo se ejecuta con `python -m etl.<modulo>`. |
| 2 | [`etl/config.py`](#2-config) | 69 | Credenciales desde el `.env`. Define los dos roles: `rol_etl` (lee el OLTP) y `rol_dw_carga` (escribe el DW). |
| 3 | [`etl/conexiones.py`](#3-conexiones) | 98 | Punto único de acceso a PostgreSQL y Neo4j. Reutiliza los modelos del backend en vez de duplicarlos. |
| 4 | [`etl/extraccion.py`](#4-extraccion) | 223 | Extrae del esquema operacional. Agrega con `GROUP BY` en el motor, no en pandas. |
| 5 | [`etl/grafo.py`](#5-grafo) | 87 | Métricas de dependencia curricular desde Neo4j: dependientes directos, en cascada e índice de bloqueo. |
| 6 | [`etl/transformacion.py`](#6-transformacion) | 350 | Limpieza y enriquecimiento. Principio: ante un dato que no permite calcular un resultado, clasifica el caso y lo deja nulo, nunca lo imputa. |
| 7 | [`etl/anonimizacion.py`](#7-anonimizacion) | 168 | Verifica (no anonimiza) en tres barreras. Lista blanca de columnas, no lista negra. |
| 8 | [`etl/pipeline.py`](#8-pipeline) | 118 | Orquesta extracción, transformación y verificación. Escribe staging solo si la anonimización pasó. |
| 9 | [`etl/carga.py`](#9-carga) | 213 | Carga al modelo dimensional. Recarga completa dentro de una sola transacción. |
| 10 | [`etl/validar_dw.py`](#10-validar-dw) | 581 | 66 verificaciones contra fuentes independientes. Regenera `docs/validacion/registro_validacion.md`. |
| 11 | [`etl/verificar_conexiones.py`](#11-verificar-conexiones) | 95 | Comprobación de conectividad y de que el ETL NO puede escribir en el OLTP. |
| 12 | [`etl/verificar_pipeline.py`](#12-verificar-pipeline) | 107 | Comprobación del pipeline de extracción y transformación. |
| 13 | [`etl/tests/__init__.py`](#13-tests-init) | 0 | Paquete de pruebas. |
| 14 | [`etl/tests/test_pipeline.py`](#14-tests-test-pipeline) | 419 | Pruebas del pipeline. |

**Total: 2533 líneas en 14 archivos.**

---

## 1. __init__

**`etl/__init__.py`** — Marca `etl/` como paquete. Por eso todo se ejecuta con `python -m etl.<modulo>`.

````python
"""Pipeline ETL — Fase 3.

Extracción híbrida desde PostgreSQL (OLTP) y Neo4j (grafo curricular),
transformación y carga al modelo dimensional.
"""
````

---

## 2. config

**`etl/config.py`** — Credenciales desde el `.env`. Define los dos roles: `rol_etl` (lee el OLTP) y `rol_dw_carga` (escribe el DW).

````python
"""Configuración del pipeline ETL — SCRUM-33.

Mismo patrón que backend/app/config.py: las credenciales salen del .env de la
raíz, nunca del código. La diferencia es el rol de PostgreSQL que se usa —
aquí rol_etl, que solo tiene SELECT — porque el ETL jamás debe escribir en el
esquema operacional.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]


class ErrorConfiguracion(Exception):
    """Falta una credencial que la operación pedida necesita."""


class SettingsETL(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "academico_db"

    # Rol de solo lectura. Que el ETL no pueda escribir no depende de que este
    # código se porte bien, sino de los GRANT del motor.
    etl_db_user: str = "rol_etl"
    etl_db_password: str

    # Rol de ESCRITURA del Data Warehouse (SCRUM-35). Es otro rol, a propósito:
    # rol_etl lee el OLTP y no puede escribir el DW; rol_dw_carga escribe el DW
    # y no puede leer el OLTP. Opcional aquí para que los comandos que solo leen
    # (pipeline, verificaciones) no exijan una credencial que no usan; la carga
    # sí la exige y falla con un mensaje claro si falta.
    dw_carga_db_user: str = "rol_dw_carga"
    dw_carga_db_password: str | None = None

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.etl_db_user}:{self.etl_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_carga(self) -> str:
        if not self.dw_carga_db_password:
            raise ErrorConfiguracion(
                "Falta DW_CARGA_DB_PASSWORD en el .env: la carga del DW escribe con "
                "rol_dw_carga, no con rol_etl (que es de solo lectura). Ver "
                "database/oltp/14_bootstrap_rol_dw_carga.sh."
            )
        return (
            f"postgresql+psycopg2://{self.dw_carga_db_user}:{self.dw_carga_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = SettingsETL()
````

---

## 3. conexiones

**`etl/conexiones.py`** — Punto único de acceso a PostgreSQL y Neo4j. Reutiliza los modelos del backend en vez de duplicarlos.

````python
"""Capa de conexión híbrida a PostgreSQL y Neo4j — SCRUM-33.

Punto único de entrada a ambos motores para todo el pipeline, de modo que
SCRUM-34 (extracción) y SCRUM-35 (carga) no repitan configuración ni abran
conexiones por su cuenta.

Sobre los modelos: el esquema operacional ya está mapeado en
backend/app/models.py y no se duplica aquí — dos mapeos del mismo esquema se
desincronizan tarde o temprano. Como `backend/` no es un paquete instalable,
se agrega al sys.path para poder importarlo (ver `modelos_oltp`). Lo correcto a
futuro sería extraer los modelos a un paquete compartido, pero eso toca código
de toda la Fase 2 y queda fuera del alcance de este ticket.
"""

import sys
from contextlib import contextmanager
from pathlib import Path

from neo4j import Driver, GraphDatabase
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import RAIZ_PROYECTO, settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SesionOLTP = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def engine_carga():
    """Conexión de ESCRITURA al Data Warehouse (SCRUM-35), como rol_dw_carga.

    Distinta de `engine` a propósito: ese lee el OLTP con rol_etl y no puede
    escribir el DW; este escribe el DW y no puede leer el OLTP. Se crea al
    pedirla (no al importar) para que quien solo lee no necesite la credencial.
    """
    return create_engine(settings.database_url_carga, pool_pre_ping=True, future=True)


def _backend_en_path() -> None:
    ruta_backend = str(RAIZ_PROYECTO / "backend")
    if ruta_backend not in sys.path:
        sys.path.insert(0, ruta_backend)


def modelos_oltp():
    """Devuelve el módulo de modelos SQLAlchemy del backend.

    Import perezoso y con ajuste de sys.path: así el ETL reutiliza el mapeo del
    esquema sin que importar este módulo obligue a tener el backend disponible.
    """
    _backend_en_path()
    from app import models  # noqa: PLC0415  (import diferido a propósito)

    return models


def calculos_oltp():
    """Devuelve backend/app/calculos.py: la nota final ponderada y los umbrales
    académicos que también usa el reporte de SCRUM-10. Mismo mecanismo que
    `modelos_oltp`, por la misma razón: una regla de negocio, una sola copia.
    """
    _backend_en_path()
    from app import calculos  # noqa: PLC0415

    return calculos


@contextmanager
def sesion_oltp() -> Session:
    """Sesión de solo lectura sobre el esquema operacional.

    No se expone commit: si algo intentara escribir, PostgreSQL lo rechazaría
    de todos modos por los permisos de rol_etl. El rollback al salir deja la
    conexión limpia para el pool.
    """
    sesion = SesionOLTP()
    try:
        yield sesion
    finally:
        sesion.rollback()
        sesion.close()


def crear_driver_neo4j() -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


@contextmanager
def sesion_grafo():
    """Sesión contra el grafo curricular de Neo4j."""
    driver = crear_driver_neo4j()
    try:
        with driver.session() as sesion:
            yield sesion
    finally:
        driver.close()
````

---

## 4. extraccion

**`etl/extraccion.py`** — Extrae del esquema operacional. Agrega con `GROUP BY` en el motor, no en pandas.

````python
"""Extracción de las entidades operacionales — SCRUM-34.

Dos decisiones atraviesan todo el módulo:

1. Columnas explícitas, nunca SELECT *. Qué sale del OLTP es una decisión
   consciente columna por columna: si mañana alguien agrega una columna
   `nombre` a estudiantes, el ETL no la arrastra al Data Warehouse sin que
   nadie lo note. (La validación de anonimización lo vuelve a comprobar al
   final, pero la primera barrera es no pedirla.)

2. Las calificaciones y asistencias se extraen ya agregadas por inscripción,
   haciendo el GROUP BY en PostgreSQL. El grano del modelo dimensional es la
   inscripción (un estudiante cursando una sección), y traer ~130k notas y
   ~120k sesiones a Python para agregarlas aquí sería mover datos para nada —
   el mismo criterio que ya sigue el reporte de SCRUM-10. La nota final usa
   literalmente la misma expresión SQL que ese reporte (backend/app/calculos.py).
"""

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .conexiones import calculos_oltp, modelos_oltp


def _leer(sesion: Session, consulta) -> pd.DataFrame:
    # coerce_float convierte los NUMERIC (Decimal) a float: el análisis
    # posterior es estadístico, no contable.
    return pd.read_sql(consulta, sesion.connection(), coerce_float=True)


def extraer_estudiantes(sesion: Session) -> pd.DataFrame:
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Estudiante.estudiante_id,
        m.Estudiante.carnet_hash,
        m.Estudiante.anio_ingreso,
        m.Estudiante.carrera_id,
        m.Estudiante.trabaja,
        m.Estudiante.condicion_academica,
        m.Estudiante.activo,
    ))


def extraer_materias(sesion: Session) -> pd.DataFrame:
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Materia.materia_id,
        m.Materia.codigo_materia,
        m.Materia.nombre,
        m.Materia.unidades_valorativas,
        m.Materia.ciclo_plan,
        m.Materia.carrera_id,
        m.Materia.activo,
    ))


def extraer_periodos(sesion: Session) -> pd.DataFrame:
    m = modelos_oltp()
    return _leer(sesion, select(
        m.PeriodoAcademico.periodo_id,
        m.PeriodoAcademico.codigo_periodo,
        m.PeriodoAcademico.anio,
        m.PeriodoAcademico.ciclo_romano,
        m.PeriodoAcademico.fecha_inicio,
        m.PeriodoAcademico.fecha_fin,
    ))


def extraer_secciones(sesion: Session) -> pd.DataFrame:
    # Sin `aula`: no es insumo de ningún análisis. docente_id es una llave
    # sustituta interna, no un dato personal; codigo_docente no se extrae.
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Seccion.seccion_id,
        m.Seccion.materia_id,
        m.Seccion.docente_id,
        m.Seccion.periodo_id,
        m.Seccion.numero_seccion,
        m.Seccion.turno,
        m.Seccion.cupo_maximo,
    ))


def extraer_inscripciones(sesion: Session) -> pd.DataFrame:
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Inscripcion.inscripcion_id,
        m.Inscripcion.estudiante_id,
        m.Inscripcion.seccion_id,
        m.Inscripcion.fecha_inscripcion,
        m.Inscripcion.numero_intento,
        m.Inscripcion.estado_inscripcion,
    ))


def extraer_notas_por_inscripcion(sesion: Session) -> pd.DataFrame:
    """Nota final ponderada por inscripción, para todas las inscripciones.

    A diferencia del reporte de SCRUM-10, aquí no se filtran los RETIRADO ni se
    limita a un periodo: el ETL extrae todo y las reglas de limpieza deciden
    qué hacer con cada caso (ver transformacion.py). Agrega además cuántas
    evaluaciones de la sección quedaron sin nota, que el reporte no necesita.
    """
    m = modelos_oltp()
    nf = calculos_oltp().expresiones_nota_final()
    consulta = calculos_oltp().unir_evaluaciones_y_calificaciones(
        select(
            m.Inscripcion.inscripcion_id,
            func.count(m.Evaluacion.evaluacion_id).label("evaluaciones"),
            func.count(m.Calificacion.calificacion_id).label("evaluaciones_calificadas"),
            nf.ponderacion_evaluada.label("ponderacion_evaluada"),
            nf.ponderacion_calificada.label("ponderacion_calificada"),
            nf.nota_final.label("nota_final"),
        )
        .select_from(m.Inscripcion)
        .join(m.Seccion, m.Inscripcion.seccion_id == m.Seccion.seccion_id)
    ).group_by(m.Inscripcion.inscripcion_id)
    return _leer(sesion, consulta)


def extraer_asistencia_por_inscripcion(sesion: Session) -> pd.DataFrame:
    """Sesiones de asistencia agregadas por inscripción.

    INNER sobre asistencias a propósito: solo devuelve inscripciones con al
    menos una sesión registrada. Las que no tienen ninguna se distinguen en la
    transformación (porcentaje de asistencia desconocido, no 0 %).
    """
    m = modelos_oltp()
    conteo = calculos_oltp().conteo_asistencia
    return _leer(sesion, select(
        m.Asistencia.inscripcion_id,
        func.count(m.Asistencia.asistencia_id).label("sesiones"),
        conteo("PRESENTE").label("presentes"),
        conteo("AUSENTE").label("ausentes"),
        conteo("JUSTIFICADO").label("justificados"),
    ).group_by(m.Asistencia.inscripcion_id))


def extraer_carreras(sesion: Session) -> pd.DataFrame:
    """Carreras con su departamento ya resuelto, para la dimensión de carrera."""
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Carrera.carrera_id,
        m.Carrera.codigo_carrera,
        m.Carrera.nombre.label("nombre_carrera"),
        m.Departamento.departamento_id,
        m.Departamento.codigo_departamento,
        m.Departamento.nombre.label("nombre_departamento"),
    ).join(m.Departamento, m.Carrera.departamento_id == m.Departamento.departamento_id))


def extraer_docentes(sesion: Session) -> pd.DataFrame:
    """Docentes con su departamento ya resuelto, para la dimensión de docente.

    Sin codigo_docente: es un identificador institucional y no es insumo de
    ningún análisis (la sección ya lleva docente_id, la llave sustituta interna).
    El OLTP no guarda nombres de docentes; lo que sale es escalafón y departamento.
    """
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Docente.docente_id,
        m.Docente.escalafon,
        m.Departamento.departamento_id,
        m.Departamento.codigo_departamento,
        m.Departamento.nombre.label("nombre_departamento"),
        m.Docente.activo,
    ).join(m.Departamento, m.Docente.departamento_id == m.Departamento.departamento_id))


def extraer_costos_periodo(sesion: Session) -> pd.DataFrame:
    """Costo por UV de cada período, con su fuente (SCRUM-36).

    La fuente viaja hasta el DW para que el dashboard pueda advertir cuando la
    cifra es un supuesto paramétrico y no un dato presupuestario oficial.
    """
    m = modelos_oltp()
    return _leer(sesion, select(
        m.CostoUV.periodo_id,
        m.CostoUV.costo_por_uv,
        m.CostoUV.moneda,
        m.CostoUV.fuente.label("fuente_costo"),
    ))


def extraer_costo_materia_periodo(sesion: Session) -> pd.DataFrame:
    """Costo de impartir cada materia en cada período.

    Se lee de la vista v_costo_materia_periodo (database/oltp/08) y no se
    recalcula aquí: la multiplicación UV × costo por UV vive en un solo lugar,
    igual que la nota final vive en backend/app/calculos.py.
    """
    return _leer(sesion, text(
        "SELECT materia_id, periodo_id, costo_materia "
        "FROM academico_oltp.v_costo_materia_periodo"
    ))


EXTRACTORES = {
    "estudiantes": extraer_estudiantes,
    "materias": extraer_materias,
    "periodos": extraer_periodos,
    "secciones": extraer_secciones,
    "inscripciones": extraer_inscripciones,
    "notas": extraer_notas_por_inscripcion,
    "asistencia": extraer_asistencia_por_inscripcion,
    "carreras": extraer_carreras,
    "docentes": extraer_docentes,
    "costos_periodo": extraer_costos_periodo,
    "costos_materia": extraer_costo_materia_periodo,
}


def extraer_oltp(sesion: Session) -> dict[str, pd.DataFrame]:
    """Ejecuta todos los extractores en una misma transacción REPEATABLE READ.

    Con el aislamiento por defecto (READ COMMITTED) cada SELECT vería su propia
    foto de la base: si un docente registra una nota entre la extracción de
    inscripciones y la de notas, los dos DataFrames no cuadrarían. En REPEATABLE
    READ todas las consultas leen el mismo instante, sin bloquear al OLTP.
    """
    sesion.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    return {nombre: extractor(sesion) for nombre, extractor in EXTRACTORES.items()}
````

---

## 5. grafo

**`etl/grafo.py`** — Métricas de dependencia curricular desde Neo4j: dependientes directos, en cascada e índice de bloqueo.

````python
"""Métricas de grafo de la malla curricular — SCRUM-34.

Alimentan el análisis de asignaturas cuello de botella de la Fase 4.3.

Semántica de la relación (ver database/nosql/03_malla_curricular.cql):
    (A)-[:REQUIERE_APROBADA]->(B)   "para cursar A hay que haber aprobado B"

Por lo tanto los *dependientes* de una materia B son las materias que apuntan
hacia ella: reprobar B las bloquea. Se calculan en Cypher y no en Python
porque el recorrido de caminos de longitud variable es justamente lo que un
motor de grafos resuelve de forma nativa, y es el argumento de por qué la
malla vive en Neo4j y no en una tabla de prerrequisitos en PostgreSQL (donde
el mismo cálculo exigiría un WITH RECURSIVE por materia).
"""

import pandas as pd
from neo4j import Session

# Una materia es cuello de botella si reprobarla bloquea, directa o
# indirectamente, al menos a un cuarto del resto del pensum. Se usa una
# proporción y no un número absoluto para que el criterio siga teniendo sentido
# si la malla crece más allá de las 16 materias del tronco actual.
UMBRAL_CUELLO_BOTELLA = 0.25

# Un solo recorrido por materia para cada métrica. Los caminos de longitud
# variable en Cypher no repiten relaciones, así que la consulta termina aunque
# alguien introdujera por error un ciclo en la malla.
CONSULTA_METRICAS = """
MATCH (m:Materia)
OPTIONAL MATCH (m)<-[:REQUIERE_APROBADA]-(directo:Materia)
WITH m, count(DISTINCT directo) AS dependientes_directos
OPTIONAL MATCH (m)<-[:REQUIERE_APROBADA*1..]-(cascada:Materia)
WITH m, dependientes_directos, count(DISTINCT cascada) AS dependientes_totales
OPTIONAL MATCH (m)-[:REQUIERE_APROBADA]->(requisito:Materia)
WITH m, dependientes_directos, dependientes_totales,
     count(DISTINCT requisito) AS prerrequisitos_directos
OPTIONAL MATCH abajo = (m)<-[:REQUIERE_APROBADA*1..]-(:Materia)
WITH m, dependientes_directos, dependientes_totales, prerrequisitos_directos,
     coalesce(max(length(abajo)), 0) AS longitud_cascada
OPTIONAL MATCH arriba = (m)-[:REQUIERE_APROBADA*1..]->(:Materia)
RETURN m.codigo AS codigo_materia,
       m.area AS area,
       dependientes_directos,
       dependientes_totales - dependientes_directos AS dependientes_indirectos,
       dependientes_totales,
       prerrequisitos_directos,
       longitud_cascada,
       coalesce(max(length(arriba)), 0) AS profundidad_prerrequisitos
ORDER BY dependientes_totales DESC, codigo_materia
"""

COLUMNAS_METRICAS = [
    "codigo_materia",
    "area",
    "dependientes_directos",
    "dependientes_indirectos",
    "dependientes_totales",
    "prerrequisitos_directos",
    "longitud_cascada",
    "profundidad_prerrequisitos",
]


def extraer_metricas_grafo(sesion: Session) -> pd.DataFrame:
    """Métricas estructurales de cada materia de la malla.

    - dependientes_directos: materias que la tienen como prerrequisito inmediato.
    - dependientes_indirectos: materias bloqueadas en cascada, sin contar las directas.
    - longitud_cascada: cuántos ciclos de la cadena posterior se retrasan si se reprueba.
    - profundidad_prerrequisitos: cuántas materias encadenadas hay que aprobar antes.

    También trae el área de conocimiento de la materia (Ciencias Básicas,
    Desarrollo de Software, ...), que solo existe en el grafo: el OLTP no la
    registra. Es una de las variables cualitativas del análisis diagnóstico.
    """
    registros = [dict(r) for r in sesion.run(CONSULTA_METRICAS)]
    return pd.DataFrame(registros, columns=COLUMNAS_METRICAS)


def clasificar_cuellos_de_botella(metricas: pd.DataFrame) -> pd.DataFrame:
    """Agrega indice_bloqueo (fracción del resto del pensum que la materia
    bloquea) y la marca es_cuello_botella según UMBRAL_CUELLO_BOTELLA."""
    resultado = metricas.copy()
    otras_materias = max(len(resultado) - 1, 1)
    resultado["indice_bloqueo"] = (resultado["dependientes_totales"] / otras_materias).round(4)
    resultado["es_cuello_botella"] = resultado["indice_bloqueo"] >= UMBRAL_CUELLO_BOTELLA
    return resultado
````

---

## 6. transformacion

**`etl/transformacion.py`** — Limpieza y enriquecimiento. Principio: ante un dato que no permite calcular un resultado, clasifica el caso y lo deja nulo, nunca lo imputa.

````python
"""Limpieza y enriquecimiento de los datos académicos — SCRUM-34.

Recibe lo que produjeron extraccion.py y grafo.py y devuelve los conjuntos
listos para el modelo dimensional (SCRUM-35):

    hechos_inscripcion   grano: una inscripción (estudiante cursando una sección)
    estudiante_periodo   grano: un estudiante en un periodo en que se inscribió
    estudiantes          dimensión, con marcas de actividad
    materias             dimensión, enriquecida con métricas de grafo y rendimiento
    periodos, secciones  dimensiones, tal como salen del OLTP

Principio general de la limpieza: ante un dato que no permite calcular un
resultado académico, el ETL deja el resultado en NULO y lo clasifica, nunca
lo imputa. Un 0 inventado para un retiro o para una sección sin evaluaciones
arrastraría hacia abajo cualquier promedio del dashboard y se confundiría con
un reprobado real. Cada caso queda contado en el reporte de calidad.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .conexiones import calculos_oltp
from .grafo import clasificar_cuellos_de_botella

_calculos = calculos_oltp()
ESTADO_RETIRADO = _calculos.ESTADO_RETIRADO
ESTADO_INSCRITO = "INSCRITO"
# Mismo umbral que el reporte de notas finales de SCRUM-10.
UMBRAL_APROBACION = float(_calculos.UMBRAL_NOTA_APROBACION)
# Mismo umbral que el reporte de asistencia acumulada de SCRUM-25.
UMBRAL_FALTAS_RIESGO = int(_calculos.UMBRAL_FALTAS_RIESGO)

# Resultado de una inscripción. Solo APROBADO y REPROBADO llevan nota final.
APROBADO = "APROBADO"
REPROBADO = "REPROBADO"
RETIRADO = "RETIRADO"                  # el estudiante se retiró de la materia
EN_CURSO = "EN_CURSO"                  # INSCRITO en un periodo que aún no termina
SIN_CIERRE = "SIN_CIERRE"              # INSCRITO en un periodo ya terminado: nadie cerró la nota
SIN_EVALUACIONES = "SIN_EVALUACIONES"  # la sección no tiene evaluaciones creadas
SIN_CALIFICAR = "SIN_CALIFICAR"        # FINALIZADO pero sin ninguna nota registrada

RESULTADOS_CERRADOS = (APROBADO, REPROBADO)


class ErrorIntegridad(Exception):
    """Los datos extraídos no cuadran entre sí; no se debe cargar nada."""


@dataclass
class ResultadoTransformacion:
    datasets: dict[str, pd.DataFrame]
    calidad: dict = field(default_factory=dict)


def _exigir_sin_nulos(df: pd.DataFrame, columnas: list[str], contexto: str) -> None:
    faltantes = df[columnas].isna().any(axis=1)
    if faltantes.any():
        raise ErrorIntegridad(
            f"{contexto}: {int(faltantes.sum())} fila(s) sin {', '.join(columnas)}"
        )


def _clasificar_resultado(h: pd.DataFrame, fecha_corte: date) -> pd.Series:
    """Asigna el resultado de cada inscripción. El orden de las condiciones es
    la prioridad: la primera que se cumple gana."""
    inscrito = h["estado_inscripcion"] == ESTADO_INSCRITO
    periodo_vigente = h["fecha_fin"] >= pd.Timestamp(fecha_corte)
    condiciones = [
        # Retiro: no es un resultado académico, se conserva como señal de
        # deserción para la Fase 4.2 pero sin nota.
        h["estado_inscripcion"] == ESTADO_RETIRADO,
        inscrito & periodo_vigente,
        h["ponderacion_evaluada"] == 0,
        inscrito,
        # Evaluaciones sin nota registrada, caso extremo: ninguna. No hay
        # evidencia de desempeño, así que no hay nota que reportar.
        h["ponderacion_calificada"] == 0,
        # Evaluaciones sin nota registrada, caso parcial: la nota faltante
        # cuenta como 0, igual que en el reporte de SCRUM-10 (el estudiante no
        # se presentó). Se marca con nota_completa = False.
        h["nota_final"] >= UMBRAL_APROBACION,
    ]
    opciones = [RETIRADO, EN_CURSO, SIN_EVALUACIONES, SIN_CIERRE, SIN_CALIFICAR, APROBADO]
    return pd.Series(np.select(condiciones, opciones, default=REPROBADO), index=h.index)


def construir_hechos_inscripcion(datos: dict[str, pd.DataFrame], fecha_corte: date) -> pd.DataFrame:
    secciones = datos["secciones"][["seccion_id", "materia_id", "docente_id", "periodo_id", "turno"]]
    periodos = datos["periodos"][["periodo_id", "fecha_fin"]].assign(
        fecha_fin=lambda df: pd.to_datetime(df["fecha_fin"])
    )

    h = (
        datos["inscripciones"]
        .merge(secciones, on="seccion_id", how="left", validate="many_to_one")
        .merge(periodos, on="periodo_id", how="left", validate="many_to_one")
        .merge(datos["notas"], on="inscripcion_id", how="left", validate="one_to_one")
        .merge(datos["asistencia"], on="inscripcion_id", how="left", validate="one_to_one")
        .merge(datos["costos_materia"], on=["materia_id", "periodo_id"], how="left",
               validate="many_to_one")
    )
    _exigir_sin_nulos(h, ["materia_id", "periodo_id", "fecha_fin", "ponderacion_evaluada"],
                      "hechos_inscripcion")

    # Sin sesiones registradas no es lo mismo que 0 % de asistencia: el
    # porcentaje queda nulo y los conteos en 0.
    conteos = ["sesiones", "presentes", "ausentes", "justificados"]
    h[conteos] = h[conteos].fillna(0).astype("int64")
    # Mismo cálculo que el CSV de asistencia de SCRUM-26: presentes / sesiones.
    h["porcentaje_asistencia"] = (
        (h["presentes"] / h["sesiones"].where(h["sesiones"] > 0) * 100).round(2)
    )

    h["resultado"] = _clasificar_resultado(h, fecha_corte)
    cerrada = h["resultado"].isin(RESULTADOS_CERRADOS)

    h["evaluaciones_sin_nota"] = (h["evaluaciones"] - h["evaluaciones_calificadas"]).astype("int64")
    h["nota_final"] = h["nota_final"].where(cerrada)
    h["aprobado"] = pd.Series(pd.NA, index=h.index, dtype="boolean")
    h.loc[cerrada, "aprobado"] = h.loc[cerrada, "resultado"] == APROBADO
    h["nota_completa"] = pd.Series(pd.NA, index=h.index, dtype="boolean")
    h.loc[cerrada, "nota_completa"] = (
        h.loc[cerrada, "ponderacion_calificada"] >= h.loc[cerrada, "ponderacion_evaluada"]
    )

    # Costo (SCRUM-36). costo_inscripcion es lo que la institución invirtió en
    # que el estudiante cursara la materia; costo_reprobacion es esa misma
    # inversión cuando terminó en REPROBADO, y 0 en cualquier otro caso. Un
    # retiro no cuenta como reprobación, igual que en el resto del pipeline.
    # Un período sin costo registrado deja el costo nulo (no 0) y se cuenta en
    # el reporte de calidad.
    h["costo_inscripcion"] = h["costo_materia"]
    h["costo_reprobacion"] = h["costo_inscripcion"].where(h["resultado"] == REPROBADO, 0.0).fillna(0.0)
    h["es_repeticion"] = h["numero_intento"] > 1
    # costo_repeticion (SCRUM-35): la misma inversión cuando es un reintento
    # (numero_intento > 1), sin importar cómo termine. No excluye a
    # costo_reprobacion: una repetición reprobada cuenta en las dos medidas, así
    # que no deben sumarse entre sí.
    h["costo_repeticion"] = h["costo_inscripcion"].where(h["es_repeticion"], 0.0).fillna(0.0)

    # Patrón de riesgo (Fase 4.2): inscripción cerrada con nota final < 6.00 Y
    # 3 o más ausencias. Son los dos umbrales que ya usa el sistema
    # transaccional (reportes de SCRUM-10 y SCRUM-25), tomados de
    # backend/app/calculos.py: el dashboard y el reporte miden lo mismo. Es un
    # patrón OBSERVADO en datos históricos, no una predicción.
    h["patron_riesgo"] = (h["resultado"] == REPROBADO) & (h["ausentes"] >= UMBRAL_FALTAS_RIESGO)

    return h[[
        "inscripcion_id", "estudiante_id", "seccion_id", "materia_id", "periodo_id",
        "docente_id", "fecha_inscripcion", "numero_intento", "estado_inscripcion",
        "resultado", "nota_final", "aprobado", "nota_completa",
        "ponderacion_evaluada", "ponderacion_calificada", "evaluaciones_sin_nota",
        "sesiones", "presentes", "ausentes", "justificados", "porcentaje_asistencia",
        "es_repeticion", "costo_inscripcion", "costo_reprobacion", "costo_repeticion",
        "turno", "patron_riesgo",
    ]].sort_values("inscripcion_id", ignore_index=True)


def construir_estudiante_periodo(hechos: pd.DataFrame, materias: pd.DataFrame) -> pd.DataFrame:
    """Resumen por estudiante y periodo, base del análisis de patrones de abandono (4.2).

    Estudiantes sin actividad en el periodo: solo existe fila para los periodos
    en que el estudiante se inscribió a algo — no se fabrican filas para cada
    combinación estudiante × periodo. Si se inscribió pero no muestra actividad
    (retiró todo, o no tiene ni notas ni asistencia), la fila se conserva con
    con_actividad = False y promedio nulo: es exactamente el patrón de abandono
    que la Fase 4.2 debe identificar, y un promedio de 0 lo confundiría con un
    estudiante que reprobó todo.
    """
    h = hechos.merge(materias[["materia_id", "unidades_valorativas"]], on="materia_id",
                     how="left", validate="many_to_one")
    cerrada = h["resultado"].isin(RESULTADOS_CERRADOS)
    no_retirada = h["resultado"] != RETIRADO

    h = h.assign(
        retirada=~no_retirada,
        aprobada=h["resultado"] == APROBADO,
        reprobada=h["resultado"] == REPROBADO,
        uv_vigentes=h["unidades_valorativas"].where(no_retirada, 0),
        uv_aprobadas=h["unidades_valorativas"].where(h["resultado"] == APROBADO, 0),
        uv_cerradas=h["unidades_valorativas"].where(cerrada, 0),
        nota_por_uv=(h["nota_final"] * h["unidades_valorativas"]).where(cerrada, 0),
        con_actividad=no_retirada & (
            (h["ponderacion_calificada"] > 0)
            | (h["sesiones"] > 0)
            | (h["resultado"] == EN_CURSO)
        ),
    )

    ep = h.groupby(["estudiante_id", "periodo_id"], as_index=False).agg(
        materias_inscritas=("inscripcion_id", "count"),
        materias_retiradas=("retirada", "sum"),
        materias_aprobadas=("aprobada", "sum"),
        materias_reprobadas=("reprobada", "sum"),
        uv_inscritas=("uv_vigentes", "sum"),
        uv_aprobadas=("uv_aprobadas", "sum"),
        uv_cerradas=("uv_cerradas", "sum"),
        nota_por_uv=("nota_por_uv", "sum"),
        sesiones=("sesiones", "sum"),
        presentes=("presentes", "sum"),
        con_actividad=("con_actividad", "any"),
    )
    # Promedio del periodo ponderado por unidades valorativas (como el CUM),
    # solo sobre materias con resultado cerrado.
    ep["promedio_periodo"] = (ep["nota_por_uv"] / ep["uv_cerradas"].where(ep["uv_cerradas"] > 0)).round(2)
    ep["porcentaje_asistencia"] = (ep["presentes"] / ep["sesiones"].where(ep["sesiones"] > 0) * 100).round(2)
    return ep.drop(columns=["nota_por_uv", "uv_cerradas", "sesiones", "presentes"])


def construir_periodos(periodos: pd.DataFrame, costos_periodo: pd.DataFrame) -> pd.DataFrame:
    """Dimensión de períodos con su orden cronológico y su costo por UV."""
    p = periodos.merge(costos_periodo, on="periodo_id", how="left", validate="one_to_one")
    p = p.sort_values("fecha_inicio", ignore_index=True)
    p["orden"] = range(1, len(p) + 1)
    return p


def construir_estudiantes(estudiantes: pd.DataFrame, estudiante_periodo: pd.DataFrame,
                          periodos: pd.DataFrame) -> pd.DataFrame:
    """Dimensión de estudiantes. Se conservan todos, incluso los que nunca
    tuvieron actividad (sin_actividad = True): la dimensión describe a la
    población, y descartarlos haría invisibles a los que abandonaron antes de
    empezar."""
    orden = periodos[["periodo_id", "codigo_periodo", "fecha_inicio"]]
    activos = (
        estudiante_periodo[estudiante_periodo["con_actividad"]]
        .merge(orden, on="periodo_id")
        .sort_values("fecha_inicio")
        .groupby("estudiante_id")
        .agg(periodos_con_actividad=("periodo_id", "count"),
             ultimo_periodo_activo=("codigo_periodo", "last"))
    )
    inscritos = estudiante_periodo.groupby("estudiante_id").agg(
        periodos_inscritos=("periodo_id", "count")
    )

    e = estudiantes.merge(inscritos, on="estudiante_id", how="left").merge(
        activos, on="estudiante_id", how="left"
    )
    e[["periodos_inscritos", "periodos_con_actividad"]] = (
        e[["periodos_inscritos", "periodos_con_actividad"]].fillna(0).astype("int64")
    )
    e["sin_actividad"] = e["periodos_con_actividad"] == 0
    return e.sort_values("estudiante_id", ignore_index=True)


def construir_materias(materias: pd.DataFrame, metricas_grafo: pd.DataFrame,
                       hechos: pd.DataFrame) -> pd.DataFrame:
    """Dimensión de materias con el cruce relacional-grafo.

    Además de las métricas estructurales de Neo4j, agrega el rendimiento real
    de cada materia y el indice_impacto = tasa_reprobacion × dependientes_totales:
    cuántas materias quedan bloqueadas, en promedio, por cada estudiante que la
    cursa. Una materia con muchos dependientes pero que casi nadie reprueba no
    es un cuello de botella en la práctica; este índice combina ambas cosas.
    """
    grafo = clasificar_cuellos_de_botella(metricas_grafo)
    m = materias.merge(grafo, on="codigo_materia", how="left", indicator=True)
    m["en_grafo"] = m.pop("_merge") == "both"

    metricas_conteo = [
        "dependientes_directos", "dependientes_indirectos", "dependientes_totales",
        "prerrequisitos_directos", "longitud_cascada", "profundidad_prerrequisitos",
    ]
    m[metricas_conteo] = m[metricas_conteo].fillna(0).astype("int64")
    m["indice_bloqueo"] = m["indice_bloqueo"].fillna(0.0)
    m["es_cuello_botella"] = m["es_cuello_botella"].fillna(False).astype(bool)
    # Una materia del OLTP que no está en la malla no tiene área: se rotula en
    # vez de quedar nula, para que aparezca como su propio segmento.
    m["area"] = m["area"].fillna("Sin área en la malla")

    rendimiento = hechos.groupby("materia_id").agg(
        inscripciones=("inscripcion_id", "count"),
        retiros=("resultado", lambda r: (r == RETIRADO).sum()),
        inscripciones_cerradas=("resultado", lambda r: r.isin(RESULTADOS_CERRADOS).sum()),
        reprobados=("resultado", lambda r: (r == REPROBADO).sum()),
        nota_promedio=("nota_final", "mean"),
    )
    m = m.merge(rendimiento, on="materia_id", how="left")
    conteos = ["inscripciones", "retiros", "inscripciones_cerradas", "reprobados"]
    m[conteos] = m[conteos].fillna(0).astype("int64")
    m["nota_promedio"] = m["nota_promedio"].round(2)
    m["tasa_reprobacion"] = (
        m["reprobados"] / m["inscripciones_cerradas"].where(m["inscripciones_cerradas"] > 0)
    ).round(4)
    m["tasa_retiro"] = (m["retiros"] / m["inscripciones"].where(m["inscripciones"] > 0)).round(4)
    m["indice_impacto"] = (m["tasa_reprobacion"] * m["dependientes_totales"]).round(4)
    return m.sort_values("codigo_materia", ignore_index=True)


def _reporte_calidad(datos, hechos, estudiante_periodo, estudiantes, materias, metricas_grafo):
    cerradas = hechos["resultado"].isin(RESULTADOS_CERRADOS)
    no_retiradas = hechos["resultado"] != RETIRADO
    return {
        "extraidos": {nombre: len(df) for nombre, df in datos.items()},
        "inscripciones_por_resultado": {
            k: int(v) for k, v in hechos["resultado"].value_counts().sort_index().items()
        },
        "inscripciones_cerradas_con_nota_incompleta": int(
            (cerradas & ~hechos["nota_completa"].fillna(True)).sum()
        ),
        "evaluaciones_sin_nota_en_inscripciones_cerradas": int(
            hechos.loc[cerradas, "evaluaciones_sin_nota"].sum()
        ),
        "inscripciones_no_retiradas_sin_asistencia": int(
            (no_retiradas & (hechos["sesiones"] == 0)).sum()
        ),
        "estudiante_periodo_sin_actividad": int((~estudiante_periodo["con_actividad"]).sum()),
        "estudiantes_sin_actividad": int(estudiantes["sin_actividad"].sum()),
        "materias_sin_nodo_en_grafo": sorted(
            materias.loc[~materias["en_grafo"], "codigo_materia"].tolist()
        ),
        "nodos_de_grafo_sin_materia_en_oltp": sorted(
            set(metricas_grafo["codigo_materia"]) - set(materias["codigo_materia"])
        ),
        "inscripciones_sin_costo": int(hechos["costo_inscripcion"].isna().sum()),
        "cuellos_de_botella": materias.loc[
            materias["es_cuello_botella"], "codigo_materia"
        ].tolist(),
    }


def transformar(datos: dict[str, pd.DataFrame], metricas_grafo: pd.DataFrame,
                fecha_corte: date | None = None) -> ResultadoTransformacion:
    """fecha_corte decide qué periodos siguen vigentes (EN_CURSO vs SIN_CIERRE).
    Por defecto es hoy; se puede fijar para reproducir una corrida."""
    fecha_corte = fecha_corte or date.today()

    hechos = construir_hechos_inscripcion(datos, fecha_corte)
    estudiante_periodo = construir_estudiante_periodo(hechos, datos["materias"])
    estudiantes = construir_estudiantes(datos["estudiantes"], estudiante_periodo, datos["periodos"])
    materias = construir_materias(datos["materias"], metricas_grafo, hechos)

    datasets = {
        "hechos_inscripcion": hechos,
        "estudiante_periodo": estudiante_periodo,
        "estudiantes": estudiantes,
        "materias": materias,
        "periodos": construir_periodos(datos["periodos"], datos["costos_periodo"]),
        "carreras": datos["carreras"].sort_values("carrera_id", ignore_index=True),
        "docentes": datos["docentes"].sort_values("docente_id", ignore_index=True),
        "secciones": datos["secciones"].sort_values("seccion_id", ignore_index=True),
    }
    calidad = _reporte_calidad(datos, hechos, estudiante_periodo, estudiantes,
                               materias, metricas_grafo)
    calidad["fecha_corte"] = fecha_corte.isoformat()
    return ResultadoTransformacion(datasets=datasets, calidad=calidad)
````

---

## 7. anonimizacion

**`etl/anonimizacion.py`** — Verifica (no anonimiza) en tres barreras. Lista blanca de columnas, no lista negra.

````python
"""Verificación de anonimización antes de que algo salga hacia el DW — SCRUM-34.

El carnet ya llega hasheado con SHA-256 desde el generador (Fase 1.2), así que
el ETL no anonimiza: *verifica* que la anonimización se cumple. Tres barreras,
de la más estructural a la más empírica:

1. Lista blanca de columnas por conjunto de salida. Solo pueden salir las
   columnas enumeradas aquí; cualquier otra hace fallar el pipeline. Es lista
   blanca y no lista negra a propósito: una lista negra ("nombre", "email",
   ...) solo atrapa lo que alguien pensó de antemano. Con lista blanca, agregar
   una columna al DW exige editar este archivo, y ese diff es el que se revisa.

2. Validación de contenido: carnet_hash debe tener forma de SHA-256 (64
   caracteres hexadecimales) y ser único, y ninguna columna de texto puede
   contener algo con forma de carnet sin hashear, correo o DUI. Esto atrapa
   el caso en que la columna es legítima pero el dato no lo es — p. ej. un
   generador o una migración que dejara el carnet en claro dentro de
   carnet_hash.

3. Aislamiento de credenciales: rol_etl no puede leer academico_oltp.usuarios
   (nombres completos, hashes de contraseña). Se comprueba en vivo contra
   PostgreSQL, igual que verificar_conexiones.py comprueba el solo-lectura.

Si cualquiera falla, el pipeline se detiene antes de escribir nada.
"""

import re

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .conexiones import sesion_oltp

COLUMNAS_PERMITIDAS: dict[str, set[str]] = {
    "hechos_inscripcion": {
        "inscripcion_id", "estudiante_id", "seccion_id", "materia_id", "periodo_id",
        "docente_id", "fecha_inscripcion", "numero_intento", "estado_inscripcion",
        "resultado", "nota_final", "aprobado", "nota_completa",
        "ponderacion_evaluada", "ponderacion_calificada", "evaluaciones_sin_nota",
        "sesiones", "presentes", "ausentes", "justificados", "porcentaje_asistencia",
        "es_repeticion", "costo_inscripcion", "costo_reprobacion", "costo_repeticion",
        "turno", "patron_riesgo",
    },
    "estudiante_periodo": {
        "estudiante_id", "periodo_id", "materias_inscritas", "materias_retiradas",
        "materias_aprobadas", "materias_reprobadas", "uv_inscritas", "uv_aprobadas",
        "con_actividad", "promedio_periodo", "porcentaje_asistencia",
    },
    # Única dimensión sobre personas. Sin nombre, sin carnet en claro, sin
    # fecha de nacimiento ni datos de contacto: el OLTP tampoco los tiene.
    "estudiantes": {
        "estudiante_id", "carnet_hash", "anio_ingreso", "carrera_id", "trabaja",
        "condicion_academica", "activo", "periodos_inscritos",
        "periodos_con_actividad", "ultimo_periodo_activo", "sin_actividad",
    },
    "materias": {
        "materia_id", "codigo_materia", "nombre", "unidades_valorativas", "ciclo_plan",
        "carrera_id", "activo", "en_grafo", "area", "dependientes_directos",
        "dependientes_indirectos", "dependientes_totales", "prerrequisitos_directos",
        "longitud_cascada", "profundidad_prerrequisitos", "indice_bloqueo",
        "es_cuello_botella", "inscripciones", "retiros", "inscripciones_cerradas",
        "reprobados", "nota_promedio", "tasa_reprobacion", "tasa_retiro", "indice_impacto",
    },
    "periodos": {
        "periodo_id", "codigo_periodo", "anio", "ciclo_romano", "fecha_inicio", "fecha_fin",
        "orden", "costo_por_uv", "moneda", "fuente_costo",
    },
    "carreras": {
        "carrera_id", "codigo_carrera", "nombre_carrera", "departamento_id",
        "codigo_departamento", "nombre_departamento",
    },
    "secciones": {
        "seccion_id", "materia_id", "docente_id", "periodo_id", "numero_seccion",
        "turno", "cupo_maximo",
    },
    # Sin codigo_docente ni nombre: el OLTP no guarda nombres y el código es un
    # identificador institucional que ningún análisis necesita.
    "docentes": {
        "docente_id", "escalafon", "departamento_id", "codigo_departamento",
        "nombre_departamento", "activo",
    },
}

PATRON_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Formas de datos identificables que nunca deberían aparecer en un valor de
# texto. El carnet sigue el formato del generador (p. ej. US2300042); se busca
# como palabra completa para no confundirlo con un fragmento de un hash.
PATRONES_IDENTIFICABLES = {
    "carnet sin hashear": re.compile(r"\b[A-Z]{2}\d{5,7}\b"),
    "correo electrónico": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "DUI": re.compile(r"\b\d{8}-\d\b"),
}


class ErrorAnonimizacion(Exception):
    """Algún dato identificable saldría del OLTP. No se debe cargar nada."""


def validar_columnas(datasets: dict[str, pd.DataFrame]) -> list[str]:
    errores = []
    for nombre, df in datasets.items():
        permitidas = COLUMNAS_PERMITIDAS.get(nombre)
        if permitidas is None:
            errores.append(f"'{nombre}': conjunto sin lista blanca declarada")
            continue
        sobrantes = sorted(set(df.columns) - permitidas)
        if sobrantes:
            errores.append(f"'{nombre}': columnas no autorizadas {sobrantes}")
    return errores


def validar_carnet_hash(estudiantes: pd.DataFrame) -> list[str]:
    errores = []
    hashes = estudiantes["carnet_hash"].astype("string")
    invalidos = ~hashes.str.fullmatch(PATRON_SHA256).fillna(False)
    if invalidos.any():
        errores.append(
            f"'estudiantes': {int(invalidos.sum())} carnet_hash sin forma de SHA-256 "
            "(¿carnet en claro?)"
        )
    if hashes.duplicated().any():
        errores.append("'estudiantes': carnet_hash duplicado")
    return errores


def escanear_contenido(datasets: dict[str, pd.DataFrame]) -> list[str]:
    errores = []
    for nombre, df in datasets.items():
        for columna in df.select_dtypes(include=["object", "string"]).columns:
            valores = df[columna].dropna().astype("string").drop_duplicates()
            for descripcion, patron in PATRONES_IDENTIFICABLES.items():
                coincidencias = valores[valores.str.contains(patron, regex=True)]
                if not coincidencias.empty:
                    errores.append(
                        f"'{nombre}.{columna}': {len(coincidencias)} valor(es) con forma "
                        f"de {descripcion}"
                    )
    return errores


def verificar_aislamiento_credenciales() -> list[str]:
    """Lo correcto es que PostgreSQL rechace la lectura de usuarios. Solo un
    rechazo por permisos (SQLSTATE 42501) cuenta: cualquier otro error, como
    una base apagada, no demuestra nada y se propaga."""
    with sesion_oltp() as sesion:
        try:
            sesion.execute(text("SELECT 1 FROM academico_oltp.usuarios LIMIT 1"))
        except DBAPIError as exc:
            if getattr(exc.orig, "pgcode", None) != "42501":
                raise
            return []
    return ["rol_etl puede leer academico_oltp.usuarios: revisa sus GRANT"]


def verificar_anonimizacion(datasets: dict[str, pd.DataFrame],
                            comprobar_permisos: bool = True) -> None:
    errores = validar_columnas(datasets)
    errores += validar_carnet_hash(datasets["estudiantes"])
    errores += escanear_contenido(datasets)
    if comprobar_permisos:
        errores += verificar_aislamiento_credenciales()
    if errores:
        raise ErrorAnonimizacion(
            "La salida del ETL contiene datos potencialmente identificables:\n  - "
            + "\n  - ".join(errores)
        )
````

---

## 8. pipeline

**`etl/pipeline.py`** — Orquesta extracción, transformación y verificación. Escribe staging solo si la anonimización pasó.

````python
"""Pipeline de extracción, limpieza y enriquecimiento — SCRUM-34 (Fase 3.2).

    extracción OLTP ─┐
                     ├─> transformación ─> verificación de anonimización ─> staging
    métricas Neo4j ──┘

La carga al modelo dimensional (SCRUM-35) puede llamar a `ejecutar_pipeline()`
y recibir los DataFrames en memoria, o leer los CSV de staging que deja la
ejecución por línea de comandos:

    python -m etl.pipeline
    python -m etl.pipeline --salida etl/staging --fecha-corte 2025-12-31

La salida a disco ocurre solo si la verificación de anonimización pasó: un
error ahí detiene el proceso sin escribir un solo archivo.
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

from .anonimizacion import ErrorAnonimizacion, verificar_anonimizacion
from .conexiones import sesion_grafo, sesion_oltp
from .config import RAIZ_PROYECTO
from .extraccion import extraer_oltp
from .grafo import extraer_metricas_grafo
from .transformacion import ErrorIntegridad, ResultadoTransformacion, transformar

SALIDA_POR_DEFECTO = RAIZ_PROYECTO / "etl" / "staging"


def ejecutar_pipeline(fecha_corte: date | None = None) -> ResultadoTransformacion:
    inicio = time.perf_counter()

    print("[1/4] Extrayendo entidades operacionales de PostgreSQL...")
    with sesion_oltp() as sesion:
        datos = extraer_oltp(sesion)
    for nombre, df in datos.items():
        print(f"      {nombre:<14} {len(df):>8,} filas")

    print("[2/4] Calculando métricas de grafo en Neo4j...")
    with sesion_grafo() as sesion:
        metricas = extraer_metricas_grafo(sesion)
    print(f"      {len(metricas)} materias en la malla curricular")

    print("[3/4] Limpiando y enriqueciendo...")
    resultado = transformar(datos, metricas, fecha_corte)

    print("[4/4] Verificando anonimización de la salida...")
    verificar_anonimizacion(resultado.datasets)
    print("      Ningún dato identificable en la salida.")

    resultado.calidad["duracion_segundos"] = round(time.perf_counter() - inicio, 2)
    return resultado


def escribir_staging(resultado: ResultadoTransformacion, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, df in resultado.datasets.items():
        df.to_csv(salida / f"{nombre}.csv", index=False, encoding="utf-8")
    (salida / "calidad.json").write_text(
        json.dumps(resultado.calidad, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _imprimir_resumen(resultado: ResultadoTransformacion) -> None:
    c = resultado.calidad
    print("\nResultados por inscripción:")
    for estado, n in c["inscripciones_por_resultado"].items():
        print(f"  {estado:<18} {n:>8,}")
    print(f"\nCerradas con nota incompleta:        {c['inscripciones_cerradas_con_nota_incompleta']:,}")
    print(f"No retiradas sin asistencia:         {c['inscripciones_no_retiradas_sin_asistencia']:,}")
    print(f"Estudiante-periodo sin actividad:    {c['estudiante_periodo_sin_actividad']:,}")
    print(f"Estudiantes sin ninguna actividad:   {c['estudiantes_sin_actividad']:,}")

    materias = resultado.datasets["materias"].sort_values(
        ["dependientes_totales", "indice_impacto"], ascending=False
    )
    print("\nAsignaturas con más dependientes (cuello de botella = *):")
    print(f"  {'materia':<8} {'dir':>4} {'indir':>6} {'reprob.':>8} {'impacto':>8}")
    for _, m in materias.head(6).iterrows():
        marca = "*" if m["es_cuello_botella"] else " "
        print(f"{marca} {m['codigo_materia']:<8} {m['dependientes_directos']:>4} "
              f"{m['dependientes_indirectos']:>6} {m['tasa_reprobacion']:>8.1%} "
              f"{m['indice_impacto']:>8.2f}")

    for aviso in ("materias_sin_nodo_en_grafo", "nodos_de_grafo_sin_materia_en_oltp"):
        if c[aviso]:
            print(f"\nAVISO {aviso}: {', '.join(c[aviso])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO,
                        help="directorio de staging (por defecto etl/staging)")
    parser.add_argument("--fecha-corte", type=date.fromisoformat, default=None,
                        help="YYYY-MM-DD; periodos que terminan después siguen EN_CURSO")
    args = parser.parse_args(argv)

    print("Pipeline ETL — SCRUM-34\n")
    try:
        resultado = ejecutar_pipeline(args.fecha_corte)
    except (ErrorAnonimizacion, ErrorIntegridad) as exc:
        print(f"\n[DETENIDO] {exc}\nNo se escribió ningún archivo.", file=sys.stderr)
        return 1

    escribir_staging(resultado, args.salida)
    _imprimir_resumen(resultado)
    print(f"\nStaging escrito en {args.salida} "
          f"({resultado.calidad['duracion_segundos']} s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

---

## 9. carga

**`etl/carga.py`** — Carga al modelo dimensional. Recarga completa dentro de una sola transacción.

````python
"""Carga al modelo dimensional dw_academico — SCRUM-35 (Fase 3.3).

Toma lo que produce el pipeline de SCRUM-34 (ya limpio, enriquecido y con la
anonimización verificada) y lo escribe en el esquema estrella definido en
database/oltp/10_dw_academico.sql.

Escribe con rol_dw_carga, no con rol_etl: el pipeline LEE el OLTP con un rol de
solo lectura, y la carga ESCRIBE el DW con otro que no puede leer el OLTP.

Estrategia: recarga completa dentro de UNA transacción. Se vacían hechos y
dimensiones y se vuelven a llenar; si algo falla a mitad, el ROLLBACK deja el
DW exactamente como estaba. Mientras dura la carga, el dashboard sigue viendo
la versión anterior completa, nunca una mezcla. Con el volumen actual (~37k
hechos) la recarga tarda segundos, así que la complejidad de una carga
incremental no se justifica todavía; si el volumen creciera, el grano por
inscripción y las llaves naturales guardadas en las dimensiones permiten
pasar a incremental sin rediseñar el modelo.

    python -m etl.carga
    python -m etl.carga --fecha-corte 2025-12-31
"""

import argparse
import json
import sys
from datetime import date

import pandas as pd
from sqlalchemy import text

from .anonimizacion import ErrorAnonimizacion
from .conexiones import engine_carga
from .config import ErrorConfiguracion
from .pipeline import ejecutar_pipeline
from .transformacion import (
    REPROBADO,
    RESULTADOS_CERRADOS,
    RETIRADO,
    ErrorIntegridad,
    ResultadoTransformacion,
)

ESQUEMA_DW = "dw_academico"

# Orden de inserción: dimensiones antes que hechos, por las llaves foráneas.
TABLAS_DW = [
    "dim_periodo", "dim_carrera", "dim_materia", "dim_estudiante",
    "dim_docente", "dim_seccion", "fact_inscripcion",
]


def _asignar_llave(df: pd.DataFrame, columna_id: str, columna_llave: str) -> pd.DataFrame:
    """Llave sustituta 1..n, determinista: ordenada por la llave natural."""
    resultado = df.sort_values(columna_id, ignore_index=True)
    resultado.insert(0, columna_llave, range(1, len(resultado) + 1))
    return resultado


def _mapa(df: pd.DataFrame, columna_id: str, columna_llave: str) -> pd.Series:
    return df.set_index(columna_id)[columna_llave]


def preparar_tablas(resultado: ResultadoTransformacion) -> dict[str, pd.DataFrame]:
    """Traduce los conjuntos del pipeline a las tablas del modelo estrella."""
    ds = resultado.datasets

    dim_periodo = _asignar_llave(ds["periodos"], "periodo_id", "periodo_key")[[
        "periodo_key", "periodo_id", "codigo_periodo", "anio", "ciclo_romano",
        "fecha_inicio", "fecha_fin", "orden", "costo_por_uv", "moneda", "fuente_costo",
    ]]

    dim_carrera = _asignar_llave(ds["carreras"], "carrera_id", "carrera_key")[[
        "carrera_key", "carrera_id", "codigo_carrera", "nombre_carrera",
        "departamento_id", "codigo_departamento", "nombre_departamento",
    ]]
    llave_carrera = _mapa(dim_carrera, "carrera_id", "carrera_key")

    dim_materia = _asignar_llave(ds["materias"], "materia_id", "materia_key")
    dim_materia["carrera_key"] = dim_materia["carrera_id"].map(llave_carrera)
    dim_materia = dim_materia.rename(columns={"nombre": "nombre_materia"})[[
        "materia_key", "materia_id", "codigo_materia", "nombre_materia",
        "unidades_valorativas", "ciclo_plan", "area", "carrera_key", "en_grafo",
        "dependientes_directos", "dependientes_indirectos", "dependientes_totales",
        "longitud_cascada", "indice_bloqueo", "es_cuello_botella",
    ]]

    dim_estudiante = _asignar_llave(ds["estudiantes"], "estudiante_id", "estudiante_key")
    dim_estudiante["carrera_key"] = dim_estudiante["carrera_id"].map(llave_carrera)
    dim_estudiante = dim_estudiante[[
        "estudiante_key", "estudiante_id", "carnet_hash", "anio_ingreso",
        "carrera_key", "trabaja", "condicion_academica",
    ]]

    dim_docente = _asignar_llave(ds["docentes"], "docente_id", "docente_key")[[
        "docente_key", "docente_id", "escalafon", "departamento_id",
        "codigo_departamento", "nombre_departamento", "activo",
    ]]

    # Los códigos de materia y período viajan como texto para que una sección
    # sea legible por sí sola; la dimensión no encadena llaves a otras dimensiones.
    dim_seccion = _asignar_llave(ds["secciones"], "seccion_id", "seccion_key")
    dim_seccion["codigo_materia"] = dim_seccion["materia_id"].map(
        dim_materia.set_index("materia_id")["codigo_materia"])
    dim_seccion["codigo_periodo"] = dim_seccion["periodo_id"].map(
        dim_periodo.set_index("periodo_id")["codigo_periodo"])
    sin_contexto = dim_seccion[["codigo_materia", "codigo_periodo"]].isna().any(axis=1)
    if sin_contexto.any():
        raise ErrorIntegridad(
            f"dim_seccion: {int(sin_contexto.sum())} sección(es) con materia o período inexistente"
        )
    dim_seccion = dim_seccion[[
        "seccion_key", "seccion_id", "numero_seccion", "turno", "cupo_maximo",
        "codigo_materia", "codigo_periodo",
    ]]

    h = ds["hechos_inscripcion"]
    materia = dim_materia.set_index("materia_id")
    fact = pd.DataFrame({
        "inscripcion_id": h["inscripcion_id"],
        "periodo_key": h["periodo_id"].map(_mapa(dim_periodo, "periodo_id", "periodo_key")),
        "materia_key": h["materia_id"].map(materia["materia_key"]),
        "estudiante_key": h["estudiante_id"].map(_mapa(dim_estudiante, "estudiante_id", "estudiante_key")),
        # La carrera que oferta la materia: es la que asume su costo.
        "carrera_key": h["materia_id"].map(materia["carrera_key"]),
        "seccion_key": h["seccion_id"].map(_mapa(dim_seccion, "seccion_id", "seccion_key")),
        "docente_key": h["docente_id"].map(_mapa(dim_docente, "docente_id", "docente_key")),
        "numero_intento": h["numero_intento"],
        "es_repeticion": h["es_repeticion"],
        "resultado": h["resultado"],
        "cerrada": h["resultado"].isin(RESULTADOS_CERRADOS),
        "reprobado": h["resultado"] == REPROBADO,
        "retirado": h["resultado"] == RETIRADO,
        "nota_final": h["nota_final"],
        "unidades_valorativas": h["materia_id"].map(materia["unidades_valorativas"]),
        "costo_inscripcion": h["costo_inscripcion"],
        "costo_reprobacion": h["costo_reprobacion"],
        "costo_repeticion": h["costo_repeticion"],
        "sesiones": h["sesiones"],
        "presentes": h["presentes"],
        "ausentes": h["ausentes"],
        "porcentaje_asistencia": h["porcentaje_asistencia"],
        "turno": h["turno"],
        "patron_riesgo": h["patron_riesgo"],
    })

    llaves = ["periodo_key", "materia_key", "estudiante_key", "carrera_key", "seccion_key", "docente_key"]
    huerfanos = fact[llaves].isna().any(axis=1)
    if huerfanos.any():
        raise ErrorIntegridad(
            f"fact_inscripcion: {int(huerfanos.sum())} hecho(s) sin dimensión correspondiente"
        )
    fact[llaves] = fact[llaves].astype("int64")

    return {
        "dim_periodo": dim_periodo,
        "dim_carrera": dim_carrera,
        "dim_materia": dim_materia,
        "dim_estudiante": dim_estudiante,
        "dim_docente": dim_docente,
        "dim_seccion": dim_seccion,
        "fact_inscripcion": fact,
    }


def cargar_dw(resultado: ResultadoTransformacion) -> dict[str, int]:
    """Recarga completa y atómica del DW. Devuelve filas cargadas por tabla."""
    # Se prepara todo ANTES de abrir la conexión de escritura: si los datos no
    # cuadran, ni siquiera se intenta tocar el DW.
    tablas = preparar_tablas(resultado)
    with engine_carga().begin() as conexion:
        # Un solo TRUNCATE para todas: PostgreSQL resuelve las llaves foráneas
        # entre ellas. carga_control no se vacía: es el historial de cargas.
        conexion.execute(text(
            "TRUNCATE " + ", ".join(f"{ESQUEMA_DW}.{t}" for t in reversed(TABLAS_DW))
        ))
        for nombre in TABLAS_DW:
            tablas[nombre].to_sql(nombre, conexion, schema=ESQUEMA_DW, if_exists="append",
                                  index=False, method="multi", chunksize=2000)
        conexion.execute(
            text(f"INSERT INTO {ESQUEMA_DW}.carga_control (fecha_corte, filas_hechos, calidad) "
                 "VALUES (:fecha_corte, :filas, CAST(:calidad AS JSONB))"),
            {
                "fecha_corte": resultado.calidad["fecha_corte"],
                "filas": len(tablas["fact_inscripcion"]),
                "calidad": json.dumps(resultado.calidad, ensure_ascii=False),
            },
        )
    return {nombre: len(df) for nombre, df in tablas.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga del Data Warehouse — SCRUM-35")
    parser.add_argument("--fecha-corte", type=date.fromisoformat, default=None,
                        help="YYYY-MM-DD; periodos que terminan después siguen EN_CURSO")
    args = parser.parse_args(argv)

    print("Carga del Data Warehouse dw_academico — SCRUM-35\n")
    try:
        resultado = ejecutar_pipeline(args.fecha_corte)
        print("[DW] Cargando el modelo dimensional (una sola transacción)...")
        filas = cargar_dw(resultado)
    except (ErrorAnonimizacion, ErrorIntegridad, ErrorConfiguracion) as exc:
        print(f"\n[DETENIDO] {exc}\nEl DW no se modificó.", file=sys.stderr)
        return 1

    for nombre, n in filas.items():
        print(f"      {nombre:<18} {n:>8,} filas")
    print("\nDW cargado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

---

## 10. validar_dw

**`etl/validar_dw.py`** — 66 verificaciones contra fuentes independientes. Regenera `docs/validacion/registro_validacion.md`.

````python
"""Validación de datos y procesos del Data Warehouse — Fases 3.3, 4.1 y 4.2.

Reconcilia lo que muestra el dashboard contra fuentes independientes, y deja
un registro fechado para la memoria (docs/validacion/registro_validacion.md):

  - Contra el OLTP, con SQL escrito aquí y no con el código del ETL: conteos,
    costo de reprobación.
  - Contra los reportes del sistema transaccional (SCRUM-10/25), llamando a sus
    mismas funciones: tasa de reprobación y patrón de riesgo, inscripción por
    inscripción. Es lo que exige el criterio "el dashboard y el sistema
    transaccional deben medir lo mismo con los mismos números".
  - Contra un segundo cálculo: la correlación de PostgreSQL contra pandas.
  - Consistencia interna: cada segmentación reparte exactamente el total.
  - Seguridad: aislamiento de rol_dashboard y anonimización del DW.

Además registra observaciones sobre los datos (cobertura de asistencia,
relaciones que el generador sintético no modela) que la memoria debe declarar.

    python -m etl.validar_dw

Sale con código distinto de cero si alguna verificación falla.
"""

import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from sqlalchemy.exc import DBAPIError

from .conexiones import _backend_en_path, engine_carga, sesion_grafo, sesion_oltp
from .config import RAIZ_PROYECTO, ErrorConfiguracion

REGISTRO = RAIZ_PROYECTO / "docs" / "validacion" / "registro_validacion.md"
TOLERANCIA = 1e-9

_backend_en_path()
from app import calculos, dw  # noqa: E402
from app.routers import reportes  # noqa: E402
from app.verificar_dw import verificar_sin_acceso_oltp, verificar_solo_lectura_dw  # noqa: E402


@dataclass
class Resultado:
    grupo: str
    nombre: str
    esperado: str
    obtenido: str
    ok: bool


resultados: list[Resultado] = []
observaciones: list[str] = []


def registrar(grupo, nombre, esperado, obtenido, ok=None):
    ok = (esperado == obtenido) if ok is None else ok
    resultados.append(Resultado(grupo, nombre, str(esperado), str(obtenido), bool(ok)))
    marca = "OK   " if ok else "FALLO"
    print(f"  [{marca}] {grupo} · {nombre}: esperado {esperado} · obtenido {obtenido}")


def _escalar(sesion, sql, **params):
    return sesion.execute(text(sql), params).scalar()


def _df(sesion, sql, **params):
    return pd.read_sql(text(sql), sesion.connection(), params=params)


# ---------------------------------------------------------------------------
# 1. Completitud del DW frente al OLTP
# ---------------------------------------------------------------------------

def validar_completitud(s):
    pares = [
        ("Inscripciones → fact_inscripcion", "academico_oltp.inscripciones", "dw_academico.fact_inscripcion"),
        ("Estudiantes → dim_estudiante", "academico_oltp.estudiantes", "dw_academico.dim_estudiante"),
        ("Materias → dim_materia", "academico_oltp.materias", "dw_academico.dim_materia"),
        ("Períodos → dim_periodo", "academico_oltp.periodos_academicos", "dw_academico.dim_periodo"),
        ("Docentes → dim_docente", "academico_oltp.docentes", "dw_academico.dim_docente"),
        ("Secciones → dim_seccion", "academico_oltp.secciones", "dw_academico.dim_seccion"),
    ]
    for nombre, origen, destino in pares:
        registrar("Completitud", nombre,
                  _escalar(s, f"SELECT count(*) FROM {origen}"),
                  _escalar(s, f"SELECT count(*) FROM {destino}"))


# ---------------------------------------------------------------------------
# 2. Costo de reprobación contra un cálculo independiente sobre el OLTP
# ---------------------------------------------------------------------------

COSTO_OLTP = """
WITH nota AS (
    SELECT i.inscripcion_id, s.materia_id, s.periodo_id,
           ROUND(COALESCE(SUM(c.nota * e.porcentaje / 100), 0), 2) AS nota,
           COALESCE(SUM(e.porcentaje), 0) AS ponderacion
    FROM academico_oltp.inscripciones i
    JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
    LEFT JOIN academico_oltp.evaluaciones e ON e.seccion_id = s.seccion_id
    LEFT JOIN academico_oltp.calificaciones c
           ON c.inscripcion_id = i.inscripcion_id AND c.evaluacion_id = e.evaluacion_id
    WHERE i.estado_inscripcion = 'FINALIZADO'
    GROUP BY i.inscripcion_id, s.materia_id, s.periodo_id
    HAVING COUNT(c.calificacion_id) > 0
)
SELECT COUNT(*) AS reprobadas, SUM(m.unidades_valorativas * cu.costo_por_uv) AS costo
FROM nota n
JOIN academico_oltp.materias m ON m.materia_id = n.materia_id
JOIN academico_oltp.costos_uv cu ON cu.periodo_id = n.periodo_id
WHERE n.ponderacion > 0 AND n.nota < :umbral
"""


COSTO_INSCRIPCIONES_OLTP = """
SELECT COUNT(*) AS inscripciones, SUM(m.unidades_valorativas * cu.costo_por_uv) AS costo
FROM academico_oltp.inscripciones i
JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
JOIN academico_oltp.costos_uv cu ON cu.periodo_id = s.periodo_id
WHERE {filtro}
"""


def validar_costo(s):
    oltp = s.execute(text(COSTO_OLTP), {"umbral": calculos.UMBRAL_NOTA_APROBACION}).one()
    dw_ = s.execute(text(
        "SELECT COUNT(*) FILTER (WHERE reprobado), SUM(costo_reprobacion) "
        "FROM dw_academico.fact_inscripcion"
    )).one()
    registrar("Costo", "Inscripciones reprobadas (OLTP independiente vs DW)", oltp[0], dw_[0])
    registrar("Costo", "Costo de reprobación total en USD (OLTP independiente vs DW)",
              f"{float(oltp[1]):,.2f}", f"{float(dw_[1]):,.2f}")

    # Las otras dos medidas de costo (SCRUM-35): matrícula (todas las
    # inscripciones) y repetición (numero_intento > 1), con SQL propio sobre el
    # OLTP. Ninguna depende de la nota, así que no hace falta reproducir la
    # clasificación del ETL: solo UV × costo por UV de cada inscripción.
    for nombre, filtro, columna, condicion_dw in (
        ("matrícula", "TRUE", "costo_inscripcion", "TRUE"),
        ("repetición", "i.numero_intento > 1", "costo_repeticion", "es_repeticion"),
    ):
        oltp = s.execute(text(COSTO_INSCRIPCIONES_OLTP.format(filtro=filtro))).one()
        dw_ = s.execute(text(
            f"SELECT COUNT(*) FILTER (WHERE {condicion_dw}), SUM({columna}) "
            "FROM dw_academico.fact_inscripcion"
        )).one()
        registrar("Costo", f"Inscripciones con costo de {nombre} (OLTP independiente vs DW)",
                  oltp[0], dw_[0])
        registrar("Costo", f"Costo de {nombre} total en USD (OLTP independiente vs DW)",
                  f"{float(oltp[1]):,.2f}", f"{float(dw_[1]):,.2f}")

    registrar("Costo", "Costo de repetición nunca supera el costo de la inscripción (filas que lo violan)",
              0, _escalar(s, "SELECT count(*) FROM dw_academico.fact_inscripcion "
                             "WHERE costo_repeticion > costo_inscripcion"))


def validar_mart_departamento(s):
    """El data mart por departamento debe repartir exactamente cada medida."""
    medidas = ("costo_matricula_materia", "costo_reprobacion", "costo_repeticion")
    total = s.execute(text(
        "SELECT SUM(costo_inscripcion), SUM(costo_reprobacion), SUM(costo_repeticion) "
        "FROM dw_academico.fact_inscripcion")).one()
    mart = s.execute(text(
        "SELECT SUM(costo_matricula_materia), SUM(costo_reprobacion), SUM(costo_repeticion) "
        "FROM dw_academico.v_mart_departamento")).one()
    for nombre, esperado, obtenido in zip(medidas, total, mart):
        registrar("Data mart", f"Suma por departamento = total ({nombre})",
                  f"{float(esperado):,.2f}", f"{float(obtenido):,.2f}")
    sin_depto = _escalar(s, "SELECT count(*) FROM dw_academico.v_mart_departamento "
                            "WHERE codigo_departamento IS NULL")
    registrar("Data mart", "Filas del mart sin departamento", 0, sin_depto)


# ---------------------------------------------------------------------------
# 3. Mismos números que el sistema transaccional (reportes SCRUM-10 y SCRUM-25)
# ---------------------------------------------------------------------------

def _dw_por_periodo(s, periodo_id):
    # El DW no guarda el número de sección (no es insumo de ningún análisis),
    # pero sí inscripcion_id como dimensión degenerada: con él se recupera la
    # sección del OLTP para comparar contra los reportes caso por caso. Hace
    # falta porque un estudiante puede estar en dos secciones de la misma
    # materia en un mismo período (ver observaciones).
    return _df(s, """
        SELECT e.estudiante_id, m.codigo_materia, sec.numero_seccion,
               f.reprobado, f.cerrada, f.patron_riesgo
        FROM dw_academico.fact_inscripcion f
        JOIN dw_academico.dim_periodo p ON p.periodo_key = f.periodo_key
        JOIN dw_academico.dim_materia m ON m.materia_key = f.materia_key
        JOIN dw_academico.dim_estudiante e ON e.estudiante_key = f.estudiante_key
        JOIN academico_oltp.inscripciones i ON i.inscripcion_id = f.inscripcion_id
        JOIN academico_oltp.secciones sec ON sec.seccion_id = i.seccion_id
        WHERE p.periodo_id = :periodo_id
    """, periodo_id=periodo_id)


def validar_contra_reportes(s):
    periodos = _df(s, "SELECT periodo_id, codigo_periodo FROM academico_oltp.periodos_academicos "
                      "ORDER BY fecha_inicio")
    total_tasa_ok = total_patron_ok = True
    detalle_patron = []
    for periodo_id, codigo in periodos.itertuples(index=False):
        dw_ = _dw_por_periodo(s, periodo_id)

        # Notas finales del reporte: FINALIZADO con todas sus evaluaciones calificadas.
        notas = [f for f in reportes.consultar_notas_finales(s, periodo_id, limite=None)
                 if f.estado_inscripcion == "FINALIZADO" and f.ponderacion_evaluada
                 and f.ponderacion_calificada >= f.ponderacion_evaluada]
        rep_reprobadas = sum(1 for f in notas if f.nota_final < calculos.UMBRAL_NOTA_APROBACION)
        esperado = f"{rep_reprobadas}/{len(notas)}"
        obtenido = f"{int(dw_['reprobado'].sum())}/{int(dw_['cerrada'].sum())}"
        total_tasa_ok &= esperado == obtenido
        registrar("Sistema transaccional", f"Reprobadas/cerradas {codigo} (reporte de notas vs DW)",
                  esperado, obtenido)

        # Patrón de riesgo: intersección de los dos reportes del coordinador.
        # Clave: estudiante + materia + sección, que identifica una inscripción.
        reprobados = Counter((f.estudiante_id, f.codigo_materia, f.numero_seccion) for f in notas
                             if f.nota_final < calculos.UMBRAL_NOTA_APROBACION)
        faltas = Counter((f.estudiante_id, f.codigo_materia, f.numero_seccion) for f in
                         reportes.consultar_asistencia_acumulada(s, periodo_id, solo_riesgo=True,
                                                                 limite=None)
                         if f.estado_inscripcion == "FINALIZADO")
        esperado_patron = reprobados & faltas
        con_patron = dw_[dw_["patron_riesgo"]]
        obtenido_patron = Counter(zip(con_patron["estudiante_id"], con_patron["codigo_materia"],
                                      con_patron["numero_seccion"]))
        iguales = esperado_patron == obtenido_patron
        total_patron_ok &= iguales
        detalle_patron.append((codigo, sum(esperado_patron.values()), sum(obtenido_patron.values())))
        registrar("Patrón de riesgo",
                  f"{codigo}: inscripciones con nota < {calculos.UMBRAL_NOTA_APROBACION} y "
                  f"≥ {calculos.UMBRAL_FALTAS_RIESGO} ausencias (reportes vs DW, caso por caso)",
                  sum(esperado_patron.values()), sum(obtenido_patron.values()), iguales)
    return total_tasa_ok, total_patron_ok


def validar_umbrales():
    _backend_en_path()
    from etl import transformacion  # noqa: PLC0415
    registrar("Umbrales", "Reporte de asistencia y calculos.py usan el mismo umbral de faltas",
              "mismo objeto", "mismo objeto" if reportes.UMBRAL_FALTAS_RIESGO is
              calculos.UMBRAL_FALTAS_RIESGO else "copias distintas")
    registrar("Umbrales", "ETL usa el umbral de faltas del sistema transaccional",
              calculos.UMBRAL_FALTAS_RIESGO, transformacion.UMBRAL_FALTAS_RIESGO)
    registrar("Umbrales", "ETL usa el umbral de aprobación del sistema transaccional",
              float(calculos.UMBRAL_NOTA_APROBACION), transformacion.UMBRAL_APROBACION)


# ---------------------------------------------------------------------------
# 4. Correlaciones: PostgreSQL (lo que muestra el dashboard) contra pandas
# ---------------------------------------------------------------------------

def validar_correlaciones(s):
    del_dashboard = dw.correlaciones(dw.Filtros())  # vía rol_dashboard, igual que la pantalla
    filas = _df(s, "SELECT porcentaje_asistencia AS asistencia, nota_final AS nota, "
                   "numero_intento AS intento, costo_reprobacion AS costo "
                   "FROM dw_academico.fact_inscripcion WHERE cerrada").astype(float)
    peor = 0.0
    for par in del_dashboard.itertuples():
        independiente = filas[[par.x, par.y]].dropna()
        r_pandas = independiente[par.x].corr(independiente[par.y])
        peor = max(peor, abs(r_pandas - par.r))
        registrar("Correlaciones", f"r({par.x}, {par.y}) PostgreSQL vs pandas",
                  f"{r_pandas:+.6f} (n={len(independiente):,})", f"{par.r:+.6f} (n={par.n:,})",
                  abs(r_pandas - par.r) < 1e-6 and len(independiente) == par.n)
    return del_dashboard


# ---------------------------------------------------------------------------
# 5. Consistencia interna: cada segmentación reparte exactamente el total
# ---------------------------------------------------------------------------

def validar_particiones():
    total = dw.totales(dw.Filtros())
    esperado = f"{int(total['reprobadas'])}/{int(total['cerradas'])}"
    cohortes = dw.por_cohorte(dw.Filtros())
    registrar("Particiones", "Suma de cohortes = total (reprobadas/cerradas)", esperado,
              f"{int(cohortes['reprobadas'].sum())}/{int(cohortes['cerradas'].sum())}")
    for clave, (etiqueta, *_resto) in dw.SEGMENTOS.items():
        seg = dw.por_segmento(dw.Filtros(), clave)
        registrar("Particiones", f"Suma por {etiqueta.lower()} = total", esperado,
                  f"{int(seg['reprobadas'].sum())}/{int(seg['cerradas'].sum())}")
        sin_valor = seg["segmento"].isna().sum()
        registrar("Particiones", f"{etiqueta}: grupos sin valor (nulos)", 0, int(sin_valor))


def validar_area(s):
    with sesion_grafo() as g:
        grafo = {r["codigo"]: r["area"] for r in g.run("MATCH (m:Materia) RETURN m.codigo AS codigo, m.area AS area")}
    dw_ = dict(s.execute(text("SELECT codigo_materia, area FROM dw_academico.dim_materia")).all())
    coinciden = sum(1 for c, a in dw_.items() if grafo.get(c) == a)
    registrar("Cruce relacional-grafo", "Materias del DW con el área que registra Neo4j",
              len(dw_), coinciden)


# ---------------------------------------------------------------------------
# 6. Seguridad y anonimización
# ---------------------------------------------------------------------------

def validar_seguridad(s):
    for nombre, verificacion in (
        ("rol_dashboard NO puede leer academico_oltp", verificar_sin_acceso_oltp),
        ("rol_dashboard NO puede escribir en dw_academico", verificar_solo_lectura_dw),
    ):
        try:
            ok = verificacion() == 0
        except Exception as exc:  # noqa: BLE001
            ok, nombre = False, f"{nombre} ({exc})"
        registrar("Seguridad", nombre, "permiso denegado", "permiso denegado" if ok else "permitido", ok)

    invalidos = _escalar(s, "SELECT count(*) FROM dw_academico.dim_estudiante "
                            "WHERE carnet_hash !~ '^[0-9a-f]{64}$'")
    registrar("Anonimización", "carnet_hash con formato distinto de SHA-256 en el DW", 0, invalidos)
    columnas = {c for (c,) in s.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'dw_academico' AND table_name = 'dim_estudiante'"))}
    prohibidas = sorted(c for c in columnas if any(p in c for p in ("nombre", "correo", "email",
                                                                     "telefono", "direccion", "dui")))
    registrar("Anonimización", "Columnas con datos personales en dim_estudiante", "[]", str(prohibidas))
    registrar("Integridad", "CHECK del patrón de riesgo activo en el DW", 1, _escalar(
        s, "SELECT count(*) FROM pg_constraint WHERE conname = 'chk_patron_riesgo_reprobado'"))
    registrar("Integridad", "CHECK de costo_repeticion activo en el DW", 1, _escalar(
        s, "SELECT count(*) FROM pg_constraint WHERE conname = 'chk_costo_repeticion'"))
    registrar("Integridad", "Hechos sin sección o sin docente (llaves nulas)", 0, _escalar(
        s, "SELECT count(*) FROM dw_academico.fact_inscripcion "
           "WHERE seccion_key IS NULL OR docente_key IS NULL"))
    registrar("Integridad", "Llaves de sección y docente exigidas NOT NULL por el DDL", 2, _escalar(
        s, "SELECT count(*) FROM pg_attribute WHERE attrelid = 'dw_academico.fact_inscripcion'::regclass "
           "AND attname IN ('seccion_key', 'docente_key') AND attnotnull"))
    # Cada hecho debe apuntar a la sección y al docente que el OLTP registra
    # para esa inscripción (comparación inscripción por inscripción).
    registrar("Integridad", "Hechos cuya sección o docente difiere del OLTP", 0, _escalar(s, """
        SELECT count(*) FROM dw_academico.fact_inscripcion f
        JOIN dw_academico.dim_seccion ds ON ds.seccion_key = f.seccion_key
        JOIN dw_academico.dim_docente dd ON dd.docente_key = f.docente_key
        JOIN academico_oltp.inscripciones i ON i.inscripcion_id = f.inscripcion_id
        JOIN academico_oltp.secciones sec ON sec.seccion_id = i.seccion_id
        WHERE ds.seccion_id <> sec.seccion_id OR dd.docente_id <> sec.docente_id"""))
    columnas_docente = {c for (c,) in s.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'dw_academico' AND table_name = 'dim_docente'"))}
    registrar("Anonimización", "Columnas con datos personales o código institucional en dim_docente", "[]",
              str(sorted(c for c in columnas_docente
                         if any(p in c for p in ("nombre_docente", "codigo_docente", "correo",
                                                 "email", "telefono", "direccion", "dui")))))

    # Separación de roles (SCRUM-35): leer el OLTP y escribir el DW son permisos
    # de roles distintos. Solo un rechazo por permisos (42501) demuestra algo.
    def _rechazado(ejecutar) -> bool:
        try:
            ejecutar()
        except DBAPIError as exc:
            if getattr(exc.orig, "pgcode", None) == "42501":
                return True
            raise
        return False

    def _etl_escribe_dw():
        # Savepoint: se deshace SIEMPRE (también si el INSERT fuera permitido),
        # sin tocar el resto de la transacción de validación.
        savepoint = s.begin_nested()
        try:
            s.execute(text("INSERT INTO dw_academico.carga_control (fecha_corte, filas_hechos, calidad) "
                           "VALUES (current_date, 0, '{}'::jsonb)"))
        finally:
            savepoint.rollback()

    def _carga_lee_oltp():
        with engine_carga().connect() as conexion:
            try:
                conexion.execute(text("SELECT 1 FROM academico_oltp.estudiantes LIMIT 1"))
            finally:
                conexion.rollback()

    # Además del intento en vivo (que podría ser rechazado por una causa ajena,
    # p. ej. el permiso sobre una secuencia), se inspeccionan los privilegios
    # reales de cada tabla: es lo que no se puede esquivar con una coincidencia.
    escribibles = [r[0] for r in s.execute(text("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'dw_academico' AND c.relkind IN ('r', 'p')
          AND (has_table_privilege('rol_etl', c.oid, 'INSERT')
            OR has_table_privilege('rol_etl', c.oid, 'UPDATE')
            OR has_table_privilege('rol_etl', c.oid, 'DELETE')
            OR has_table_privilege('rol_etl', c.oid, 'TRUNCATE'))
        ORDER BY c.relname"""))]
    registrar("Seguridad", "Tablas de dw_academico que rol_etl puede escribir (privilegios del catálogo)",
              "[]", str(escribibles))
    privilegios_oltp = _escalar(s, """
        SELECT (CASE WHEN has_schema_privilege('rol_dw_carga', 'academico_oltp', 'USAGE') THEN 1 ELSE 0 END)
             + (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'academico_oltp' AND c.relkind IN ('r', 'p', 'v')
                  AND (has_table_privilege('rol_dw_carga', c.oid, 'SELECT')
                    OR has_table_privilege('rol_dw_carga', c.oid, 'INSERT')
                    OR has_table_privilege('rol_dw_carga', c.oid, 'UPDATE')
                    OR has_table_privilege('rol_dw_carga', c.oid, 'DELETE')
                    OR has_table_privilege('rol_dw_carga', c.oid, 'TRUNCATE')))""")
    registrar("Seguridad", "Privilegios de rol_dw_carga sobre academico_oltp (esquema + tablas, catálogo)",
              0, privilegios_oltp)

    for nombre, ejecutar in (
        ("rol_etl (lee el OLTP) NO puede escribir en dw_academico", _etl_escribe_dw),
        ("rol_dw_carga (escribe el DW) NO puede leer academico_oltp", _carga_lee_oltp),
    ):
        try:
            ok = _rechazado(ejecutar)
        except ErrorConfiguracion as exc:
            ok, nombre = False, f"{nombre} ({exc})"
        except Exception as exc:  # noqa: BLE001
            ok, nombre = False, f"{nombre} ({exc})"
        registrar("Seguridad", nombre, "permiso denegado", "permiso denegado" if ok else "permitido", ok)


# ---------------------------------------------------------------------------
# 7. Observaciones sobre los datos (no son pasa/falla: la memoria debe declararlas)
# ---------------------------------------------------------------------------

def observar_datos(s, correlaciones):
    cobertura = _df(s, """
        SELECT p.codigo_periodo, COUNT(*) FILTER (WHERE f.cerrada) AS cerradas,
               COUNT(*) FILTER (WHERE f.cerrada AND f.sesiones > 0) AS con_asistencia
        FROM dw_academico.fact_inscripcion f JOIN dw_academico.dim_periodo p USING (periodo_key)
        GROUP BY p.codigo_periodo, p.orden ORDER BY p.orden""")
    con = cobertura[cobertura["con_asistencia"] > 0]
    observaciones.append(
        f"**Cobertura de asistencia.** Solo {len(con)} de {len(cobertura)} períodos tienen asistencia "
        f"registrada ({', '.join(con['codigo_periodo'])}): "
        f"{int(cobertura['con_asistencia'].sum()):,} de {int(cobertura['cerradas'].sum()):,} "
        "inscripciones cerradas. El generador sintético (scripts/generator, `LIMIT 12000`) solo creó "
        "asistencia para 12,000 inscripciones. El patrón de riesgo y las correlaciones con asistencia "
        "solo pueden observarse en esos períodos."
    )
    dobles = _df(s, """
        SELECT COUNT(*) AS casos, COUNT(DISTINCT estudiante_id) AS estudiantes FROM (
            SELECT i.estudiante_id, s.materia_id, s.periodo_id
            FROM academico_oltp.inscripciones i
            JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
            GROUP BY 1, 2, 3 HAVING COUNT(*) > 1) x""").iloc[0]
    observaciones.append(
        f"**Calidad de datos del OLTP: doble inscripción.** {int(dobles['casos']):,} veces un "
        f"estudiante ({int(dobles['estudiantes']):,} estudiantes distintos) quedó inscrito en dos "
        "secciones de la misma materia en el mismo período. El esquema solo impide repetir la misma "
        "sección (`uq_estudiante_seccion`), y el generador sintético elige secciones al azar. El DW "
        "trata cada inscripción por separado, que es lo correcto; esta validación compara contra "
        "los reportes por estudiante + materia + sección para no mezclarlas. Con datos reales, una "
        "restricción por (estudiante, materia, período) en el OLTP lo evitaría."
    )
    r = {frozenset({p.x, p.y}): p.r for p in correlaciones.itertuples()}
    observaciones.append(
        f"**Asistencia y nota no se relacionan en estos datos** (r = {r[frozenset({'asistencia', 'nota'})]:+.3f}). "
        "El generador crea la asistencia al azar, sin depender de la nota: el dashboard lo reporta "
        "correctamente como relación despreciable. Con datos reales esta relación podría aparecer; "
        "no es un error del análisis sino una propiedad de los datos sintéticos."
    )
    observaciones.append(
        f"**Número de intento y nota** (r = {r[frozenset({'nota', 'intento'})]:+.3f}): relación débil y "
        "negativa, coherente con el generador, que resta 0.4 puntos de media a quien repite."
    )
    observaciones.append(
        f"**Costo y nota** (r = {r[frozenset({'nota', 'costo'})]:+.3f}) es una relación por "
        "construcción: el costo de reprobación solo existe con nota < 6.00. Se usa costo_reprobacion "
        "porque costo_inscripcion es constante (todas las materias tienen 4 UV y el costo por UV es el "
        "mismo supuesto de $25.00 en todos los períodos) y su correlación no está definida."
    )
    trabaja = dw.por_segmento(dw.Filtros(), "trabaja").set_index("segmento")
    tasa = (trabaja["reprobadas"] / trabaja["cerradas"]).to_dict()
    observaciones.append(
        f"**La condición laboral es la variable que más separa la reprobación** "
        f"(trabaja {tasa.get('Trabaja', 0) * 100:.1f} % vs no trabaja "
        f"{tasa.get('No trabaja', 0) * 100:.1f} %), coherente con el generador, que resta 0.6 puntos "
        "de media a quien trabaja. Turno, área, ciclo del plan y cohorte no se modelan en el "
        "generador y sus diferencias son pequeñas o indistinguibles del azar."
    )


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ_PROYECTO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "desconocido"


def escribir_registro(contexto: dict):
    fallos = [r for r in resultados if not r.ok]
    lineas = [
        "# Registro de validación de datos y procesos — Fases 3.3, 4.1 y 4.2",
        "",
        "Generado automáticamente por `python -m etl.validar_dw`. No editar a mano: se regenera en "
        "cada corrida, y el historial de corridas queda en git.",
        "",
        f"- **Fecha:** {contexto['fecha']}",
        f"- **Commit:** `{contexto['commit']}`",
        f"- **Última carga del DW:** {contexto['carga']}",
        f"- **Volumen:** {contexto['volumen']}",
        f"- **Resultado:** {len(resultados) - len(fallos)} de {len(resultados)} verificaciones correctas"
        + (" ✅" if not fallos else f" — **{len(fallos)} fallaron** ❌"),
        "",
        "## Qué se verifica y contra qué",
        "",
        "| Grupo | Fuente de comparación |",
        "|---|---|",
        "| Completitud | Conteos del esquema operacional (`academico_oltp`) |",
        "| Costo | SQL independiente sobre el OLTP, escrito en este script (no reutiliza el ETL): reprobación, matrícula y repetición |",
        "| Data mart | El corte por departamento reparte exactamente cada medida de costo |",
        "| Sistema transaccional | Las mismas funciones de los reportes del coordinador (SCRUM-10) |",
        "| Patrón de riesgo | Intersección de los reportes de notas (SCRUM-10) y asistencia (SCRUM-25), caso por caso |",
        "| Umbrales | Identidad de las constantes en `backend/app/calculos.py`, el reporte y el ETL |",
        "| Correlaciones | `corr()` de PostgreSQL (lo que muestra el dashboard) contra pandas |",
        "| Particiones | Cada segmentación del dashboard debe repartir exactamente el total |",
        "| Cruce relacional-grafo | Área de cada materia en Neo4j |",
        "| Seguridad / Anonimización / Integridad | Permisos reales de PostgreSQL y catálogo del DW |",
        "",
        "## Resultados",
        "",
        "| Grupo | Verificación | Esperado | Obtenido | Estado |",
        "|---|---|---|---|---|",
    ]
    for r in resultados:
        lineas.append(f"| {r.grupo} | {r.nombre} | {r.esperado} | {r.obtenido} | "
                      f"{'✅ OK' if r.ok else '❌ FALLO'} |")
    lineas += ["", "## Observaciones sobre los datos", "",
               "No son fallas: son propiedades de los datos que la memoria debe declarar al "
               "interpretar los resultados.", ""]
    lineas += [f"- {o}" for o in observaciones]
    lineas += ["", "## Cómo reproducir", "", "```bash",
               "python -m etl.carga        # recarga el DW desde el OLTP y Neo4j",
               "python -m etl.validar_dw   # vuelve a validar y regenera este registro",
               "```", ""]
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text("\n".join(lineas), encoding="utf-8")


def main() -> int:
    # Los nombres de las verificaciones llevan "→"; la consola de Windows (cp1252) no
    # puede codificarlo y el script moría a la primera línea. Con errors="replace" lo
    # peor que pasa es que se vea "?", y el registro .md se escribe siempre en UTF-8.
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(errors="replace")
    print("Validación de datos y procesos del DW (Fases 3.3, 4.1 y 4.2)\n")
    with sesion_oltp() as s:
        s.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        validar_completitud(s)
        validar_costo(s)
        validar_mart_departamento(s)
        validar_contra_reportes(s)
        validar_umbrales()
        correlaciones = validar_correlaciones(s)
        validar_particiones()
        validar_area(s)
        validar_seguridad(s)
        observar_datos(s, correlaciones)
        carga = dw.ultima_carga()
        volumen = (f"{_escalar(s, 'SELECT count(*) FROM dw_academico.fact_inscripcion'):,} hechos de "
                   f"inscripción, {_escalar(s, 'SELECT count(*) FROM dw_academico.dim_estudiante'):,} "
                   "estudiantes")
    escribir_registro({
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "commit": _commit(),
        "carga": (f"{carga['ejecutada_en']:%Y-%m-%d %H:%M} UTC, fecha de corte {carga['fecha_corte']}"
                  if carga else "sin cargas"),
        "volumen": volumen,
    })
    fallos = sum(1 for r in resultados if not r.ok)
    print(f"\n{len(resultados) - fallos} de {len(resultados)} verificaciones correctas.")
    print(f"Registro escrito en {REGISTRO.relative_to(RAIZ_PROYECTO)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
````

---

## 11. verificar_conexiones

**`etl/verificar_conexiones.py`** — Comprobación de conectividad y de que el ETL NO puede escribir en el OLTP.

````python
"""Comprobación de las conexiones del ETL — SCRUM-33.

Verifica tres cosas y sale con código distinto de cero si alguna falla:

  1. Que se puede leer el esquema operacional con rol_etl.
  2. Que se puede leer el grafo curricular en Neo4j.
  3. Que el ETL NO puede escribir en el esquema operacional.

El punto 3 es el que importa: es el mismo modelo de seguridad de la Fase 2
aplicado a la capa analítica. Que el ETL sea de solo lectura no depende de la
disciplina de quien escriba el pipeline, sino de los GRANT de PostgreSQL. Este
script deja esa garantía demostrable en vivo, como el README hace con
rol_docente.

    python -m etl.verificar_conexiones
"""

import sys

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from .conexiones import modelos_oltp, sesion_grafo, sesion_oltp

# SQLSTATE insufficient_privilege: lo que devuelve PostgreSQL al negar un GRANT.
PERMISO_DENEGADO = "42501"


def verificar_lectura_oltp() -> int:
    modelos = modelos_oltp()
    with sesion_oltp() as sesion:
        estudiantes = sesion.scalar(select(func.count()).select_from(modelos.Estudiante))
        inscripciones = sesion.scalar(select(func.count()).select_from(modelos.Inscripcion))
        usuario = sesion.scalar(select(func.current_user()))
    print(f"  [OK] Lectura OLTP como '{usuario}': "
          f"{estudiantes:,} estudiantes, {inscripciones:,} inscripciones")
    return 0


def verificar_lectura_grafo() -> int:
    with sesion_grafo() as sesion:
        resultado = sesion.run(
            "MATCH (m:Materia) OPTIONAL MATCH (m)-[r:REQUIERE_APROBADA]->() "
            "RETURN count(DISTINCT m) AS materias, count(r) AS prerrequisitos"
        ).single()
    print(f"  [OK] Lectura Neo4j: {resultado['materias']} materias, "
          f"{resultado['prerrequisitos']} relaciones de prerrequisito")
    return 0


def verificar_solo_lectura() -> int:
    """Intenta escribir a propósito. Lo correcto es que PostgreSQL lo rechace."""
    modelos = modelos_oltp()
    with sesion_oltp() as sesion:
        try:
            sesion.execute(
                text("UPDATE academico_oltp.estudiantes SET activo = activo "
                     "WHERE estudiante_id = (SELECT min(estudiante_id) "
                     "FROM academico_oltp.estudiantes)")
            )
            sesion.flush()
        except DBAPIError as exc:
            # Solo cuenta como éxito el rechazo por permisos. Cualquier otro
            # error (p. ej. la base apagada) no demuestra nada sobre los GRANT.
            if getattr(exc.orig, "pgcode", None) != PERMISO_DENEGADO:
                raise
            print(f"  [OK] Escritura rechazada por PostgreSQL: "
                  f"{exc.orig.diag.message_primary}")
            return 0

    print("  [FALLO] El ETL pudo escribir en academico_oltp. "
          "Revisa los permisos de rol_etl: deberia tener solo SELECT.", file=sys.stderr)
    return 1


def main() -> int:
    print("Verificando conexiones del ETL (SCRUM-33)\n")
    fallos = 0
    for verificacion in (verificar_lectura_oltp, verificar_lectura_grafo, verificar_solo_lectura):
        try:
            fallos += verificacion()
        except Exception as exc:  # noqa: BLE001 - se reporta y se sigue con las demas
            print(f"  [FALLO] {verificacion.__name__}: {exc}", file=sys.stderr)
            fallos += 1

    print()
    if fallos:
        print(f"{fallos} verificacion(es) fallaron.", file=sys.stderr)
        return 1
    print("Todas las verificaciones pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

---

## 12. verificar_pipeline

**`etl/verificar_pipeline.py`** — Comprobación del pipeline de extracción y transformación.

````python
"""Comprobación en vivo del pipeline — SCRUM-34.

Complementa las pruebas unitarias (que no tocan la base) con dos garantías
demostrables contra los datos reales, en el mismo espíritu que
verificar_conexiones.py:

  1. La nota final del ETL coincide, inscripción por inscripción, con la del
     reporte de notas finales de SCRUM-10, en todos los periodos.
  2. Si un carnet en claro se colara en la salida, la verificación de
     anonimización detiene el pipeline.

    python -m etl.verificar_pipeline
"""

import sys

import pandas as pd

from .anonimizacion import ErrorAnonimizacion, verificar_anonimizacion
from .conexiones import _backend_en_path, sesion_grafo, sesion_oltp
from .extraccion import extraer_oltp
from .grafo import extraer_metricas_grafo
from .transformacion import transformar


def _ejecutar_transformacion():
    with sesion_oltp() as sesion:
        datos = extraer_oltp(sesion)
    with sesion_grafo() as sesion:
        metricas = extraer_metricas_grafo(sesion)
    return transformar(datos, metricas)


def verificar_nota_igual_a_scrum_10(resultado) -> int:
    _backend_en_path()
    from app.routers.reportes import consultar_notas_finales  # noqa: PLC0415

    ds = resultado.datasets
    etl = (
        ds["hechos_inscripcion"][ds["hechos_inscripcion"]["nota_final"].notna()]
        .merge(ds["materias"][["materia_id", "codigo_materia"]], on="materia_id")
        .merge(ds["secciones"][["seccion_id", "numero_seccion"]], on="seccion_id")
    )
    comparadas = diferencias = 0
    with sesion_oltp() as sesion:
        for periodo_id in ds["periodos"]["periodo_id"]:
            reporte = pd.DataFrame(
                [dict(f._mapping) for f in
                 consultar_notas_finales(sesion, int(periodo_id), limite=None)]
            )
            if reporte.empty:
                continue
            cruce = etl[etl["periodo_id"] == periodo_id].merge(
                reporte, on=["estudiante_id", "codigo_materia", "numero_seccion"],
                suffixes=("_etl", "_reporte"),
            )
            comparadas += len(cruce)
            diferencias += int(
                ((cruce["nota_final_etl"] - cruce["nota_final_reporte"].astype(float)).abs()
                 > 1e-9).sum()
            )

    if comparadas and not diferencias:
        print(f"  [OK] Nota final idéntica a la del reporte de SCRUM-10 en "
              f"{comparadas:,} inscripciones")
        return 0
    print(f"  [FALLO] {diferencias:,} de {comparadas:,} notas difieren del reporte "
          "de SCRUM-10", file=sys.stderr)
    return 1


def verificar_bloqueo_de_fuga(resultado) -> int:
    """Simula una fuga a propósito. Lo correcto es que la verificación la rechace."""
    estudiantes = resultado.datasets["estudiantes"].copy()
    estudiantes.loc[estudiantes.index[0], "carnet_hash"] = "US2300042"
    datasets = {**resultado.datasets, "estudiantes": estudiantes}
    try:
        verificar_anonimizacion(datasets, comprobar_permisos=False)
    except ErrorAnonimizacion:
        print("  [OK] Un carnet en claro en la salida detiene el pipeline")
        return 0
    print("  [FALLO] La verificación de anonimización dejó pasar un carnet en claro",
          file=sys.stderr)
    return 1


def main() -> int:
    print("Verificando el pipeline ETL (SCRUM-34)\n")
    resultado = _ejecutar_transformacion()
    fallos = 0
    for verificacion in (verificar_nota_igual_a_scrum_10, verificar_bloqueo_de_fuga):
        try:
            fallos += verificacion(resultado)
        except Exception as exc:  # noqa: BLE001 - se reporta y se sigue con las demas
            print(f"  [FALLO] {verificacion.__name__}: {exc}", file=sys.stderr)
            fallos += 1

    print()
    if fallos:
        print(f"{fallos} verificacion(es) fallaron.", file=sys.stderr)
        return 1
    print("Todas las verificaciones pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

---

## 13. tests/__init__

**`etl/tests/__init__.py`** — Paquete de pruebas.

*(archivo vacío)*

---

## 14. tests/test_pipeline

**`etl/tests/test_pipeline.py`** — Pruebas del pipeline.

````python
"""Pruebas de las reglas de limpieza, anonimización y cuellos de botella — SCRUM-34.

No tocan PostgreSQL ni Neo4j: construyen DataFrames pequeños con un caso por
regla, de modo que cada decisión de negocio queda fijada por una prueba.

    python -m unittest discover -s etl/tests -v
"""

import hashlib
import unittest
from datetime import date

import pandas as pd

from etl.anonimizacion import (
    ErrorAnonimizacion,
    escanear_contenido,
    validar_carnet_hash,
    validar_columnas,
    verificar_anonimizacion,
)
from etl.grafo import clasificar_cuellos_de_botella
from etl.transformacion import (
    APROBADO,
    EN_CURSO,
    REPROBADO,
    RETIRADO,
    SIN_CALIFICAR,
    SIN_CIERRE,
    SIN_EVALUACIONES,
    ErrorIntegridad,
    transformar,
)

FECHA_CORTE = date(2025, 10, 1)


def _hash(carnet: str) -> str:
    return hashlib.sha256(carnet.encode()).hexdigest()


def _datos_base():
    """Periodo 1 cerrado, periodo 2 vigente a FECHA_CORTE. Una inscripción por regla."""
    estudiantes = pd.DataFrame({
        "estudiante_id": [1, 2, 3, 4],
        "carnet_hash": [_hash(f"US2300{i}01") for i in range(4)],
        "anio_ingreso": [2023] * 4,
        "carrera_id": [1] * 4,
        "trabaja": [False, True, False, False],
        "condicion_academica": ["REGULAR"] * 4,
        "activo": [True] * 4,
    })
    materias = pd.DataFrame({
        "materia_id": [10, 20, 30],
        "codigo_materia": ["PRG115", "PRG215", "ZZZ999"],
        "nombre": ["Programación I", "Programación II", "Materia fuera de la malla"],
        "unidades_valorativas": [4, 3, 4],
        "ciclo_plan": [1, 2, 3],
        "carrera_id": [1, 1, 1],
        "activo": [True, True, True],
    })
    periodos = pd.DataFrame({
        "periodo_id": [1, 2],
        "codigo_periodo": ["2025-I", "2025-II"],
        "anio": [2025, 2025],
        "ciclo_romano": ["I", "II"],
        "fecha_inicio": [date(2025, 2, 1), date(2025, 8, 1)],
        "fecha_fin": [date(2025, 6, 25), date(2025, 12, 15)],
    })
    secciones = pd.DataFrame({
        "seccion_id": [100, 200, 300, 400],
        "materia_id": [10, 20, 30, 10],
        "docente_id": [1, 1, 1, 1],
        "periodo_id": [1, 1, 1, 2],
        "numero_seccion": [1, 1, 1, 1],
        "turno": ["MATUTINO"] * 4,
        "cupo_maximo": [45] * 4,
    })
    # id: caso
    #  1 aprobado con nota completa      5 retirado
    #  2 reprobado                       6 sección sin evaluaciones
    #  3 aprobado con una nota faltante  7 INSCRITO en periodo cerrado
    #  4 finalizado sin ninguna nota     8 INSCRITO en periodo vigente
    inscripciones = pd.DataFrame({
        "inscripcion_id": [1, 2, 3, 4, 5, 6, 7, 8],
        "estudiante_id": [1, 2, 3, 4, 4, 1, 2, 3],
        "seccion_id": [100, 100, 200, 200, 100, 300, 200, 400],
        "fecha_inscripcion": pd.Timestamp("2025-01-20", tz="UTC"),
        "numero_intento": [1, 2, 1, 1, 1, 1, 1, 1],
        "estado_inscripcion": ["FINALIZADO", "FINALIZADO", "FINALIZADO", "FINALIZADO",
                               "RETIRADO", "FINALIZADO", "INSCRITO", "INSCRITO"],
    })
    notas = pd.DataFrame({
        "inscripcion_id": [1, 2, 3, 4, 5, 6, 7, 8],
        "evaluaciones": [4, 4, 4, 4, 4, 0, 4, 4],
        "evaluaciones_calificadas": [4, 4, 3, 0, 1, 0, 0, 1],
        "ponderacion_evaluada": [100.0, 100, 100, 100, 100, 0, 100, 100],
        "ponderacion_calificada": [100.0, 100, 70, 0, 25, 0, 0, 25],
        "nota_final": [8.5, 4.2, 6.3, 0.0, 1.5, 0.0, 0.0, 2.0],
    })
    asistencia = pd.DataFrame({
        "inscripcion_id": [1, 2],
        "sesiones": [10, 10],
        "presentes": [9, 5],
        "ausentes": [1, 4],
        "justificados": [0, 1],
    })
    metricas = pd.DataFrame({
        "codigo_materia": ["PRG115", "PRG215", "PRG315", "DWB115"],
        "area": ["Desarrollo de Software"] * 4,
        "dependientes_directos": [1, 1, 1, 0],
        "dependientes_indirectos": [2, 1, 0, 0],
        "dependientes_totales": [3, 2, 1, 0],
        "prerrequisitos_directos": [0, 1, 1, 1],
        "longitud_cascada": [3, 2, 1, 0],
        "profundidad_prerrequisitos": [0, 1, 2, 3],
    })
    carreras = pd.DataFrame({
        "carrera_id": [1], "codigo_carrera": ["I10515"],
        "nombre_carrera": ["Ingeniería de Sistemas Informáticos"], "departamento_id": [1],
        "codigo_departamento": ["DIA"], "nombre_departamento": ["Ingeniería y Arquitectura"],
    })
    docentes = pd.DataFrame({
        "docente_id": [1], "escalafon": ["TITULAR"], "departamento_id": [1],
        "codigo_departamento": ["DIA"], "nombre_departamento": ["Ingeniería y Arquitectura"],
        "activo": [True],
    })
    costos_periodo = pd.DataFrame({
        "periodo_id": [1, 2], "costo_por_uv": [25.0, 30.0], "moneda": ["USD", "USD"],
        "fuente_costo": ["SUPUESTO PARAMETRICO", "SUPUESTO PARAMETRICO"],
    })
    # Costo de la materia en el período = UV × costo por UV (como la vista del OLTP).
    costos_materia = (
        materias[["materia_id", "unidades_valorativas"]].merge(costos_periodo, how="cross")
        .assign(costo_materia=lambda d: d["unidades_valorativas"] * d["costo_por_uv"])
        [["materia_id", "periodo_id", "costo_materia"]]
    )
    return {
        "estudiantes": estudiantes, "materias": materias, "periodos": periodos,
        "secciones": secciones, "inscripciones": inscripciones, "notas": notas,
        "asistencia": asistencia, "carreras": carreras, "docentes": docentes,
        "costos_periodo": costos_periodo, "costos_materia": costos_materia,
    }, metricas


class TestLimpiezaInscripciones(unittest.TestCase):
    def setUp(self):
        datos, metricas = _datos_base()
        self.resultado = transformar(datos, metricas, FECHA_CORTE)
        self.h = self.resultado.datasets["hechos_inscripcion"].set_index("inscripcion_id")

    def test_clasificacion_de_cada_caso(self):
        esperado = {1: APROBADO, 2: REPROBADO, 3: APROBADO, 4: SIN_CALIFICAR,
                    5: RETIRADO, 6: SIN_EVALUACIONES, 7: SIN_CIERRE, 8: EN_CURSO}
        self.assertEqual(self.h["resultado"].to_dict(), esperado)

    def test_solo_resultados_cerrados_llevan_nota(self):
        con_nota = set(self.h.index[self.h["nota_final"].notna()])
        self.assertEqual(con_nota, {1, 2, 3})

    def test_retirado_no_se_imputa_como_cero(self):
        self.assertTrue(pd.isna(self.h.loc[5, "nota_final"]))
        self.assertTrue(pd.isna(self.h.loc[5, "aprobado"]))

    def test_nota_faltante_cuenta_como_cero_y_se_marca(self):
        self.assertEqual(self.h.loc[3, "nota_final"], 6.3)
        self.assertFalse(self.h.loc[3, "nota_completa"])
        self.assertEqual(self.h.loc[3, "evaluaciones_sin_nota"], 1)
        self.assertTrue(self.h.loc[1, "nota_completa"])

    def test_sin_asistencia_registrada_no_es_cero_por_ciento(self):
        self.assertEqual(self.h.loc[1, "porcentaje_asistencia"], 90.0)
        self.assertEqual(self.h.loc[3, "sesiones"], 0)
        self.assertTrue(pd.isna(self.h.loc[3, "porcentaje_asistencia"]))

    def test_costo_de_reprobacion_solo_en_reprobados(self):
        # PRG115 en 2025-I: 4 UV × $25 = $100.
        self.assertEqual(self.h.loc[2, "costo_inscripcion"], 100.0)
        self.assertEqual(self.h.loc[2, "costo_reprobacion"], 100.0)
        # Aprobado y retirado tienen costo invertido, pero no costo de reprobación.
        self.assertEqual(self.h.loc[1, "costo_reprobacion"], 0.0)
        self.assertEqual(self.h.loc[5, "costo_inscripcion"], 100.0)
        self.assertEqual(self.h.loc[5, "costo_reprobacion"], 0.0)
        # El costo usa el costo por UV del período: PRG115 en 2025-II = 4 × $30.
        self.assertEqual(self.h.loc[8, "costo_inscripcion"], 120.0)

    def test_repeticion(self):
        self.assertTrue(self.h.loc[2, "es_repeticion"])
        self.assertFalse(self.h.loc[1, "es_repeticion"])

    def test_costo_de_repeticion_solo_en_reintentos(self):
        # Inscripción 2: numero_intento = 2, PRG115 en 2025-I = 4 UV × $25.
        self.assertEqual(self.h.loc[2, "costo_repeticion"], 100.0)
        # Primer intento: cuesta, pero no es costo de repetición.
        self.assertEqual(self.h.loc[1, "costo_inscripcion"], 100.0)
        self.assertEqual(self.h.loc[1, "costo_repeticion"], 0.0)
        # Nunca es mayor que la inversión de la inscripción.
        self.assertTrue((self.h["costo_repeticion"] <= self.h["costo_inscripcion"]).all())

    def test_repeticion_aprobada_cuesta_repeticion_pero_no_reprobacion(self):
        # Una repetición que se aprueba es costo de repetición y NO de reprobación:
        # las dos medidas no son excluyentes, pero tampoco son la misma.
        datos, metricas = _datos_base()
        datos["inscripciones"].loc[0, "numero_intento"] = 2   # inscripción 1: aprobada
        h = transformar(datos, metricas, FECHA_CORTE).datasets["hechos_inscripcion"].set_index("inscripcion_id")
        self.assertEqual(h.loc[1, "resultado"], APROBADO)
        self.assertEqual(h.loc[1, "costo_repeticion"], 100.0)
        self.assertEqual(h.loc[1, "costo_reprobacion"], 0.0)

    def test_inscripcion_con_seccion_inexistente_detiene_el_pipeline(self):
        datos, metricas = _datos_base()
        datos["inscripciones"].loc[0, "seccion_id"] = 999
        with self.assertRaises(ErrorIntegridad):
            transformar(datos, metricas, FECHA_CORTE)


class TestPatronDeRiesgo(unittest.TestCase):
    """Fase 4.2: nota final < 6.00 Y 3 o más ausencias, los umbrales del
    sistema transaccional. Las dos condiciones a la vez, nunca una sola."""

    def _hechos(self, ajustar=None):
        datos, metricas = _datos_base()
        if ajustar:
            ajustar(datos)
        r = transformar(datos, metricas, FECHA_CORTE)
        return r.datasets["hechos_inscripcion"].set_index("inscripcion_id")

    def test_reprobado_con_faltas_presenta_el_patron(self):
        # Inscripción 2: REPROBADO con 4 ausencias.
        self.assertTrue(self._hechos().loc[2, "patron_riesgo"])

    def test_faltas_sin_reprobar_no_es_patron(self):
        def aprobado_con_faltas(d):
            d["asistencia"].loc[d["asistencia"]["inscripcion_id"] == 1, "ausentes"] = 5
        self.assertFalse(self._hechos(aprobado_con_faltas).loc[1, "patron_riesgo"])

    def test_reprobar_con_pocas_faltas_no_es_patron(self):
        def dos_faltas(d):
            d["asistencia"].loc[d["asistencia"]["inscripcion_id"] == 2, "ausentes"] = 2
        self.assertFalse(self._hechos(dos_faltas).loc[2, "patron_riesgo"])

    def test_justo_en_el_umbral_si_es_patron(self):
        def tres_faltas(d):
            d["asistencia"].loc[d["asistencia"]["inscripcion_id"] == 2, "ausentes"] = 3
        self.assertTrue(self._hechos(tres_faltas).loc[2, "patron_riesgo"])

    def test_retirado_con_faltas_no_es_patron(self):
        def retirado_con_faltas(d):
            d["asistencia"].loc[len(d["asistencia"])] = [5, 10, 2, 8, 0]
        self.assertFalse(self._hechos(retirado_con_faltas).loc[5, "patron_riesgo"])

    def test_el_turno_viene_de_la_seccion(self):
        def nocturno(d):
            d["secciones"].loc[d["secciones"]["seccion_id"] == 100, "turno"] = "NOCTURNO"
        h = self._hechos(nocturno)
        self.assertEqual(h.loc[1, "turno"], "NOCTURNO")
        self.assertEqual(h.loc[3, "turno"], "MATUTINO")

    def test_area_viene_del_grafo_y_se_rotula_si_falta(self):
        datos, metricas = _datos_base()
        m = transformar(datos, metricas, FECHA_CORTE).datasets["materias"].set_index("codigo_materia")
        self.assertEqual(m.loc["PRG115", "area"], "Desarrollo de Software")
        self.assertEqual(m.loc["ZZZ999", "area"], "Sin área en la malla")


class TestEstudiantePeriodo(unittest.TestCase):
    def setUp(self):
        datos, metricas = _datos_base()
        r = transformar(datos, metricas, FECHA_CORTE)
        self.ep = r.datasets["estudiante_periodo"].set_index(["estudiante_id", "periodo_id"])
        self.e = r.datasets["estudiantes"].set_index("estudiante_id")

    def test_promedio_ponderado_por_uv_sobre_materias_cerradas(self):
        # Estudiante 1, periodo 1: PRG115 (4 UV, 8.5) cerrada; ZZZ999 sin evaluaciones no cuenta.
        self.assertEqual(self.ep.loc[(1, 1), "promedio_periodo"], 8.5)

    def test_estudiante_sin_actividad_en_el_periodo(self):
        # Estudiante 4: una materia sin calificar y otra retirada, sin asistencia.
        fila = self.ep.loc[(4, 1)]
        self.assertFalse(fila["con_actividad"])
        self.assertTrue(pd.isna(fila["promedio_periodo"]))
        self.assertEqual(fila["materias_retiradas"], 1)

    def test_no_se_fabrican_filas_para_periodos_sin_inscripcion(self):
        self.assertNotIn((4, 2), self.ep.index)

    def test_en_curso_cuenta_como_actividad(self):
        self.assertTrue(self.ep.loc[(3, 2), "con_actividad"])

    def test_dimension_conserva_estudiantes_sin_actividad(self):
        self.assertTrue(self.e.loc[4, "sin_actividad"])
        self.assertEqual(self.e.loc[4, "periodos_inscritos"], 1)
        self.assertEqual(self.e.loc[3, "ultimo_periodo_activo"], "2025-II")


class TestMateriasYGrafo(unittest.TestCase):
    def test_umbral_de_cuello_de_botella(self):
        # 4 materias: bloquear 1 de las otras 3 (33 %) ya supera el 25 %.
        _, metricas = _datos_base()
        c = clasificar_cuellos_de_botella(metricas).set_index("codigo_materia")
        self.assertEqual(c.loc["PRG115", "indice_bloqueo"], 1.0)
        self.assertTrue(c.loc["PRG315", "es_cuello_botella"])
        self.assertFalse(c.loc["DWB115", "es_cuello_botella"])

    def test_cruce_relacional_grafo(self):
        datos, metricas = _datos_base()
        r = transformar(datos, metricas, FECHA_CORTE)
        m = r.datasets["materias"].set_index("codigo_materia")
        self.assertFalse(m.loc["ZZZ999", "en_grafo"])
        self.assertEqual(m.loc["ZZZ999", "dependientes_totales"], 0)
        # PRG115: 1 aprobada + 1 reprobada cerradas -> 50 % × 3 dependientes.
        self.assertEqual(m.loc["PRG115", "tasa_reprobacion"], 0.5)
        self.assertEqual(m.loc["PRG115", "indice_impacto"], 1.5)
        self.assertEqual(r.calidad["materias_sin_nodo_en_grafo"], ["ZZZ999"])
        self.assertEqual(r.calidad["nodos_de_grafo_sin_materia_en_oltp"], ["DWB115", "PRG315"])


class TestAnonimizacion(unittest.TestCase):
    def setUp(self):
        datos, metricas = _datos_base()
        self.datasets = transformar(datos, metricas, FECHA_CORTE).datasets

    def test_salida_limpia_pasa(self):
        verificar_anonimizacion(self.datasets, comprobar_permisos=False)

    def test_columna_no_autorizada_se_rechaza(self):
        self.datasets["estudiantes"]["nombre"] = "Ana Pérez"
        self.assertTrue(validar_columnas(self.datasets))
        with self.assertRaises(ErrorAnonimizacion):
            verificar_anonimizacion(self.datasets, comprobar_permisos=False)

    def test_carnet_en_claro_dentro_de_carnet_hash_se_rechaza(self):
        self.datasets["estudiantes"].loc[0, "carnet_hash"] = "US2300001"
        self.assertTrue(validar_carnet_hash(self.datasets["estudiantes"]))
        self.assertTrue(escanear_contenido(self.datasets))

    def test_correo_en_cualquier_columna_de_texto_se_rechaza(self):
        self.datasets["materias"].loc[0, "nombre"] = "contacto: ana@ues.edu.sv"
        self.assertTrue(escanear_contenido(self.datasets))

    def test_docentes_sin_codigo_ni_nombre(self):
        self.assertNotIn("codigo_docente", self.datasets["docentes"].columns)
        self.datasets["docentes"]["nombre"] = "Pedro Pérez"
        self.assertTrue(validar_columnas(self.datasets))

    def test_codigos_de_materia_y_periodo_no_son_falsos_positivos(self):
        self.assertEqual(escanear_contenido(self.datasets), [])


if __name__ == "__main__":
    unittest.main()


class TestPreparacionDW(unittest.TestCase):
    """La traducción al modelo estrella (etl/carga.py), sin tocar la base."""

    def setUp(self):
        from etl.carga import preparar_tablas
        datos, metricas = _datos_base()
        self.tablas = preparar_tablas(transformar(datos, metricas, FECHA_CORTE))
        self.fact = self.tablas["fact_inscripcion"].set_index("inscripcion_id")

    def test_toda_inscripcion_llega_a_los_hechos_con_sus_llaves(self):
        self.assertEqual(len(self.fact), 8)
        llaves = ["periodo_key", "materia_key", "estudiante_key", "carrera_key"]
        self.assertFalse(self.fact[llaves].isna().any().any())

    def test_banderas_y_costo_cumplen_el_check_del_ddl(self):
        # Mismo invariante que chk_costo_reprobacion en 10_dw_academico.sql.
        f = self.fact
        valido = (f["costo_reprobacion"] == 0) | (
            f["reprobado"] & (f["costo_reprobacion"] == f["costo_inscripcion"]))
        self.assertTrue(valido.all())
        self.assertEqual(f["reprobado"].sum(), 1)
        self.assertEqual(f["cerrada"].sum(), 3)
        self.assertTrue(f.loc[5, "retirado"])

    def test_periodos_ordenados_y_con_costo(self):
        p = self.tablas["dim_periodo"].set_index("codigo_periodo")
        self.assertEqual(p.loc["2025-I", "orden"], 1)
        self.assertEqual(p.loc["2025-II", "costo_por_uv"], 30.0)

    def test_dimensiones_de_docente_y_seccion(self):
        docente = self.tablas["dim_docente"]
        self.assertEqual(len(docente), 1)
        self.assertNotIn("codigo_docente", docente.columns)
        seccion = self.tablas["dim_seccion"].set_index("seccion_id")
        self.assertEqual(len(seccion), 4)
        # La sección 400 es PRG115 en 2025-II: legible por sí sola.
        self.assertEqual(seccion.loc[400, "codigo_materia"], "PRG115")
        self.assertEqual(seccion.loc[400, "codigo_periodo"], "2025-II")

    def test_cada_hecho_apunta_a_su_seccion_y_docente(self):
        f = self.fact
        secciones = self.tablas["dim_seccion"].set_index("seccion_key")["seccion_id"]
        # Inscripción 8 está en la sección 400.
        self.assertEqual(secciones[f.loc[8, "seccion_key"]], 400)
        self.assertFalse(f[["seccion_key", "docente_key"]].isna().any().any())

    def test_costo_repeticion_cumple_el_check_del_ddl(self):
        # Mismo invariante que chk_costo_repeticion en 13_dw_cierre_scrum35.sql.
        f = self.fact
        valido = (f["costo_repeticion"] == 0) | (
            f["es_repeticion"] & (f["costo_repeticion"] == f["costo_inscripcion"]))
        self.assertTrue(valido.all())
        self.assertEqual(f["costo_repeticion"].sum(), 100.0)

    def test_hecho_con_seccion_inexistente_en_la_dimension_detiene_la_carga(self):
        from etl.carga import preparar_tablas
        datos, metricas = _datos_base()
        r = transformar(datos, metricas, FECHA_CORTE)
        r.datasets["secciones"] = r.datasets["secciones"][r.datasets["secciones"]["seccion_id"] != 100]
        with self.assertRaises(ErrorIntegridad):
            preparar_tablas(r)

    def test_dimension_de_estudiante_sin_datos_identificables(self):
        columnas = set(self.tablas["dim_estudiante"].columns)
        self.assertNotIn("nombre", columnas)
        self.assertIn("carnet_hash", columnas)
````

---

