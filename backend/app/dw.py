"""Consultas de la vista ejecutiva sobre el Data Warehouse — Fase 4.1.

Toda consulta de este módulo lee de dw_academico y de nada más. No es solo
disciplina: usa su propia conexión, como rol_dashboard, que no tiene permisos
sobre academico_oltp (ver app/verificar_dw.py). Es una conexión aparte de la
de database.get_db() a propósito: esa adopta rol_coordinador, que sí puede
leer el OLTP, y la vista ejecutiva nunca debe poder hacerlo.

La agregación se hace en PostgreSQL. El modelo estrella existe justamente para
que estas preguntas sean un SUM/COUNT con filtros sobre dimensiones, sin
recalcular notas ni costos: eso ya lo resolvió el ETL una sola vez.
"""

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


class DWNoConfigurado(Exception):
    """Falta DASHBOARD_DB_PASSWORD en el .env."""


_engine = None
_url_inyectada: str | None = None


def configurar(url: str) -> None:
    """Fija la conexión al DW, en vez de leerla de la configuración del backend.

    Lo usa la app Streamlit de dashboard/ (SCRUM-44): reutiliza estas mismas
    consultas, pero tiene su propia configuración con solo las credenciales de
    rol_dashboard, sin cargar las del rol de servicio de la aplicación web.
    """
    global _engine, _url_inyectada
    _url_inyectada = url
    _engine = None


def engine():
    """Engine perezoso: la app arranca aunque el DW no esté configurado."""
    global _engine
    if _engine is None:
        url = _url_inyectada
        if url is None:
            # Import diferido: quien inyecta su propia URL no necesita (ni debe
            # cargar) la configuración completa del backend.
            from .config import settings
            url = settings.dw_url
        if url is None:
            raise DWNoConfigurado(
                "Falta DASHBOARD_DB_PASSWORD en el .env (ver .env.example)."
            )
        _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine

DESDE_HECHOS = """
FROM dw_academico.fact_inscripcion f
JOIN dw_academico.dim_periodo p ON p.periodo_key = f.periodo_key
JOIN dw_academico.dim_carrera c ON c.carrera_key = f.carrera_key
"""


@dataclass(frozen=True)
class Filtros:
    """Selección del usuario. Una tupla vacía significa "todos"."""

    periodos: tuple[str, ...] = ()
    carreras: tuple[str, ...] = ()
    departamentos: tuple[str, ...] = ()

    def con_periodos(self, periodos: tuple[str, ...]) -> "Filtros":
        return Filtros(periodos, self.carreras, self.departamentos)


def _condiciones(filtros: Filtros) -> tuple[str, dict]:
    """WHERE con parámetros ligados; nunca se interpola texto del usuario."""
    partes, params = [], {}
    for columna, valores, nombre in (
        ("p.codigo_periodo", filtros.periodos, "periodos"),
        ("c.codigo_carrera", filtros.carreras, "carreras"),
        ("c.codigo_departamento", filtros.departamentos, "departamentos"),
    ):
        if valores:
            partes.append(f"{columna} = ANY(:{nombre})")
            params[nombre] = list(valores)
    return ("WHERE " + " AND ".join(partes)) if partes else "", params


def _leer(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine().connect() as conexion:
        return pd.read_sql(text(sql), conexion, params=params or {}, coerce_float=True)


def catalogo_periodos() -> pd.DataFrame:
    return _leer("""
        SELECT codigo_periodo, orden, costo_por_uv, moneda, fuente_costo
        FROM dw_academico.dim_periodo ORDER BY orden
    """)


def catalogo_carreras() -> pd.DataFrame:
    return _leer("""
        SELECT codigo_carrera, nombre_carrera, codigo_departamento, nombre_departamento
        FROM dw_academico.dim_carrera ORDER BY nombre_departamento, nombre_carrera
    """)


def totales(filtros: Filtros) -> dict:
    """Los conteos y sumas de los que salen los cuatro KPIs."""
    where, params = _condiciones(filtros)
    fila = _leer(f"""
        SELECT
            COALESCE(SUM(f.costo_reprobacion), 0)                          AS costo_reprobacion,
            COALESCE(SUM(f.costo_inscripcion) FILTER (WHERE f.cerrada), 0) AS costo_cerradas,
            COALESCE(SUM(f.costo_reprobacion) FILTER (WHERE f.es_repeticion), 0)
                                                                            AS costo_repeticion,
            COUNT(*) FILTER (WHERE f.cerrada)                               AS cerradas,
            COUNT(*) FILTER (WHERE f.reprobado)                             AS reprobadas,
            COUNT(*) FILTER (WHERE f.cerrada AND f.es_repeticion)           AS cerradas_repeticion,
            COUNT(*) FILTER (WHERE f.retirado)                              AS retiradas,
            COUNT(DISTINCT f.estudiante_key) FILTER (WHERE f.reprobado)     AS estudiantes_reprobados,
            COUNT(DISTINCT f.estudiante_key) FILTER (WHERE f.cerrada)       AS estudiantes_evaluados
        {DESDE_HECHOS}
        {where}
    """, params).iloc[0]
    return fila.to_dict()


def ranking_materias(filtros: Filtros, limite: int = 10) -> pd.DataFrame:
    """Materias ordenadas por costo de reprobación, con su papel en la malla."""
    where, params = _condiciones(filtros)
    params["limite"] = limite
    return _leer(f"""
        SELECT
            m.codigo_materia,
            m.nombre_materia,
            COUNT(*) FILTER (WHERE f.reprobado)                   AS reprobados,
            COUNT(*) FILTER (WHERE f.cerrada)                     AS cerradas,
            ROUND(COUNT(*) FILTER (WHERE f.reprobado)::numeric
                  / NULLIF(COUNT(*) FILTER (WHERE f.cerrada), 0), 4) AS tasa_reprobacion,
            COALESCE(SUM(f.costo_reprobacion), 0)                 AS costo_reprobacion,
            m.es_cuello_botella,
            m.dependientes_totales
        {DESDE_HECHOS}
        JOIN dw_academico.dim_materia m ON m.materia_key = f.materia_key
        {where}
        GROUP BY m.materia_key
        HAVING COALESCE(SUM(f.costo_reprobacion), 0) > 0
        ORDER BY costo_reprobacion DESC, m.codigo_materia
        LIMIT :limite
    """, params)


def evolucion_por_periodo(filtros: Filtros) -> pd.DataFrame:
    """Costo y tasa de cada período, con los filtros de carrera y departamento
    pero sin el de período: es el contexto contra el que se lee el ciclo."""
    where, params = _condiciones(filtros.con_periodos(()))
    return _leer(f"""
        SELECT
            p.codigo_periodo,
            p.orden,
            COALESCE(SUM(f.costo_reprobacion), 0)                 AS costo_reprobacion,
            ROUND(COUNT(*) FILTER (WHERE f.reprobado)::numeric
                  / NULLIF(COUNT(*) FILTER (WHERE f.cerrada), 0), 4) AS tasa_reprobacion
        {DESDE_HECHOS}
        {where}
        GROUP BY p.codigo_periodo, p.orden
        ORDER BY p.orden
    """, params)


def historial_cargas(limite: int = 20) -> list[dict]:
    """Últimas cargas registradas en carga_control (la carga nunca la vacía)."""
    return _leer("""
        SELECT carga_id, ejecutada_en, fecha_corte, filas_hechos, calidad
        FROM dw_academico.carga_control
        ORDER BY carga_id DESC
        LIMIT :limite
    """, {"limite": limite}).to_dict("records")


def metas_indicadores() -> dict[str, dict]:
    """Meta y banda de tolerancia de cada KPI (dim_indicador, script 20).
    Vacío si el DW todavía no tiene el script 20 aplicado."""
    try:
        df = _leer("""
            SELECT codigo, nombre, unidad, sentido, perspectiva, responsable_cargo,
                   meta_por_periodo, meta, tolerancia, justificacion
            FROM dw_academico.dim_indicador ORDER BY orden
        """)
    except DBAPIError:
        return {}
    return {fila["codigo"]: fila for fila in df.to_dict("records")}


def semaforo_por_periodo() -> pd.DataFrame:
    """Lo que calcula la vista v_semaforo_indicador: estado de cada KPI por período."""
    try:
        return _leer("""
            SELECT codigo, codigo_periodo, orden_periodo, valor, estado
            FROM dw_academico.v_semaforo_indicador ORDER BY orden_periodo
        """)
    except DBAPIError:
        return pd.DataFrame(columns=["codigo", "codigo_periodo", "orden_periodo", "valor", "estado"])


def ultima_carga() -> dict | None:
    fila = _leer("""
        SELECT ejecutada_en, fecha_corte, filas_hechos
        FROM dw_academico.carga_control ORDER BY carga_id DESC LIMIT 1
    """)
    return None if fila.empty else fila.iloc[0].to_dict()


# ---------------------------------------------------------------------------
# Análisis diagnóstico — Fase 4.2 (¿por qué ocurrió?)
#
# Mismas reglas que arriba: solo dw_academico, agregación en PostgreSQL y
# filtros siempre como parámetros ligados. Las columnas por las que se
# segmenta salen de una lista blanca, nunca del texto de la petición.
# ---------------------------------------------------------------------------

DESDE_HECHOS_DIAGNOSTICO = DESDE_HECHOS + """
JOIN dw_academico.dim_materia m ON m.materia_key = f.materia_key
JOIN dw_academico.dim_estudiante e ON e.estudiante_key = f.estudiante_key
"""

# Variables de la matriz de correlaciones. El costo es costo_reprobacion y no
# costo_inscripcion: con un costo por UV constante y todas las materias de 4 UV,
# costo_inscripcion no varía (desviación estándar 0) y su correlación no está
# definida. Ver indicadores_diagnostico.py sobre cómo se lee ese par.
VARIABLES_CORRELACION = {
    "asistencia": ("Asistencia acumulada (%)", "f.porcentaje_asistencia"),
    "nota": ("Nota final", "f.nota_final"),
    "intento": ("Número de intento", "f.numero_intento"),
    "costo": ("Costo de reprobación", "f.costo_reprobacion"),
}

# Variables cualitativas de segmentación: (etiqueta, nombre con artículo para
# las lecturas, expresión SQL del grupo, expresión SQL del orden).
SEGMENTOS = {
    "turno": ("Turno", "el turno", "initcap(f.turno)", "MIN(f.turno)"),
    "area": ("Área de la materia", "el área de la materia", "m.area", "MIN(m.area)"),
    "ciclo": ("Ciclo del plan", "el ciclo del plan", "'Ciclo ' || m.ciclo_plan",
              "MIN(m.ciclo_plan)"),
    "trabaja": ("Condición laboral", "la condición laboral",
                "CASE WHEN e.trabaja THEN 'Trabaja' ELSE 'No trabaja' END", "1"),
}


def correlaciones(filtros: Filtros) -> pd.DataFrame:
    """Pearson por pares sobre inscripciones cerradas, con corr() de PostgreSQL.

    Cada par usa las filas donde ambas variables existen (corr() ignora los
    nulos): por eso los pares con asistencia tienen menos observaciones, solo
    las inscripciones con sesiones registradas.
    """
    claves = list(VARIABLES_CORRELACION)
    pares = [(a, b) for i, a in enumerate(claves) for b in claves[i + 1:]]
    columnas = []
    for i, (a, b) in enumerate(pares):
        xa, xb = VARIABLES_CORRELACION[a][1], VARIABLES_CORRELACION[b][1]
        columnas.append(f"corr({xa}, {xb}) AS r_{i}, regr_count({xa}, {xb}) AS n_{i}")
    where, params = _condiciones(filtros)
    where = (where + " AND " if where else "WHERE ") + "f.cerrada"
    fila = _leer(f"SELECT {', '.join(columnas)} {DESDE_HECHOS} {where}", params).iloc[0]
    return pd.DataFrame([
        {"x": a, "y": b, "r": fila[f"r_{i}"], "n": int(fila[f"n_{i}"])}
        for i, (a, b) in enumerate(pares)
    ])


def reprobacion_por_ausencias(filtros: Filtros, umbral: int) -> pd.DataFrame:
    """Tasa de reprobación de quienes llegaron al umbral de faltas frente al resto,
    solo entre inscripciones cerradas con asistencia registrada."""
    where, params = _condiciones(filtros)
    where = (where + " AND " if where else "WHERE ") + "f.cerrada AND f.sesiones > 0"
    params["umbral"] = umbral
    return _leer(f"""
        SELECT (f.ausentes >= :umbral)                 AS sobre_umbral,
               COUNT(*)                                AS cerradas,
               COUNT(*) FILTER (WHERE f.reprobado)     AS reprobadas,
               ROUND(AVG(f.nota_final), 2)             AS nota_promedio
        {DESDE_HECHOS} {where}
        GROUP BY 1 ORDER BY 1
    """, params)


def por_cohorte(filtros: Filtros) -> pd.DataFrame:
    """Indicadores por año de ingreso (cohorte) del estudiante."""
    where, params = _condiciones(filtros)
    return _leer(f"""
        SELECT e.anio_ingreso                                           AS cohorte,
               COUNT(DISTINCT e.estudiante_key)                         AS estudiantes,
               COUNT(*) FILTER (WHERE f.cerrada)                        AS cerradas,
               COUNT(*) FILTER (WHERE f.reprobado)                      AS reprobadas,
               ROUND(AVG(f.nota_final), 2)                              AS nota_promedio,
               ROUND(AVG(f.porcentaje_asistencia) FILTER (WHERE f.cerrada), 1)
                                                                        AS asistencia_promedio,
               COALESCE(SUM(f.costo_reprobacion), 0)                    AS costo_reprobacion,
               COUNT(*) FILTER (WHERE f.cerrada AND f.es_repeticion)    AS cerradas_repeticion,
               COUNT(DISTINCT e.estudiante_key) FILTER (WHERE f.patron_riesgo)
                                                                        AS estudiantes_patron
        {DESDE_HECHOS_DIAGNOSTICO} {where}
        GROUP BY e.anio_ingreso ORDER BY e.anio_ingreso
    """, params)


def por_segmento(filtros: Filtros, segmento: str) -> pd.DataFrame:
    """Tasa de reprobación, nota y costo por una variable cualitativa."""
    _, _, expresion, orden = SEGMENTOS[segmento]  # KeyError si no está en la lista blanca
    where, params = _condiciones(filtros)
    return _leer(f"""
        SELECT {expresion}                               AS segmento,
               COUNT(*) FILTER (WHERE f.cerrada)         AS cerradas,
               COUNT(*) FILTER (WHERE f.reprobado)       AS reprobadas,
               ROUND(AVG(f.nota_final), 2)               AS nota_promedio,
               COALESCE(SUM(f.costo_reprobacion), 0)     AS costo_reprobacion
        {DESDE_HECHOS_DIAGNOSTICO} {where}
        GROUP BY 1 ORDER BY {orden}
    """, params)


def resumen_patron(filtros: Filtros) -> dict:
    where, params = _condiciones(filtros)
    return _leer(f"""
        SELECT COUNT(*) FILTER (WHERE f.patron_riesgo)                         AS inscripciones,
               COUNT(DISTINCT f.estudiante_key) FILTER (WHERE f.patron_riesgo) AS estudiantes,
               COUNT(*) FILTER (WHERE f.reprobado)                             AS reprobadas,
               COUNT(*) FILTER (WHERE f.reprobado AND f.sesiones > 0)          AS reprobadas_con_asistencia,
               COUNT(DISTINCT p.codigo_periodo) FILTER (WHERE f.sesiones > 0)  AS periodos_con_asistencia,
               COUNT(DISTINCT p.codigo_periodo)                                AS periodos
        {DESDE_HECHOS} {where}
    """, params).iloc[0].to_dict()


def estudiantes_con_patron(filtros: Filtros, limite: int = 50) -> pd.DataFrame:
    """Estudiantes que ya presentan el patrón: identificados por estudiante_id
    (el mismo que muestran los reportes del sistema transaccional) y por su
    carnet anonimizado. Nada identificable sale del DW."""
    where, params = _condiciones(filtros)
    where = (where + " AND " if where else "WHERE ") + "f.patron_riesgo"
    params["limite"] = limite
    return _leer(f"""
        SELECT e.estudiante_id,
               LEFT(e.carnet_hash, 12)                          AS carnet_hash,
               e.anio_ingreso,
               e.trabaja,
               COUNT(*)                                         AS inscripciones,
               STRING_AGG(DISTINCT m.codigo_materia, ', ')      AS materias,
               STRING_AGG(DISTINCT p.codigo_periodo, ', ')      AS periodos,
               MAX(f.ausentes)                                  AS max_ausencias,
               ROUND(AVG(f.nota_final), 2)                      AS nota_promedio
        {DESDE_HECHOS_DIAGNOSTICO} {where}
        GROUP BY e.estudiante_key
        ORDER BY COUNT(*) DESC, AVG(f.nota_final), e.estudiante_id
        LIMIT :limite
    """, params)


# ---------------------------------------------------------------------------
# Red curricular y materias cuello de botella — Fase 4.3 (SCRUM-46)
#
# La malla se dibuja con lo que el ETL trajo de Neo4j: las métricas viven en
# dim_materia (SCRUM-35) y las relaciones en bridge_prerrequisito (script 15).
# La pantalla no necesita ninguna credencial del grafo.
# ---------------------------------------------------------------------------

def malla() -> pd.DataFrame:
    """Nodos de la malla con las métricas de grafo calculadas en Neo4j.

    Solo las materias que están en el grafo: la malla de Neo4j es la de una carrera
    (Ingeniería de Sistemas Informáticos); las materias de las demás carreras están en el
    almacén para el resto del análisis, pero no tienen red que dibujar."""
    return _leer("""
        SELECT m.codigo_materia, m.nombre_materia, m.ciclo_plan, m.unidades_valorativas, m.area,
               m.en_grafo, m.dependientes_directos, m.dependientes_indirectos,
               m.dependientes_totales, m.longitud_cascada, m.indice_bloqueo, m.es_cuello_botella,
               c.codigo_carrera
        FROM dw_academico.dim_materia m
        JOIN dw_academico.dim_carrera c ON c.carrera_key = m.carrera_key
        WHERE m.en_grafo
        ORDER BY m.ciclo_plan, m.codigo_materia
    """)


def prerrequisitos() -> pd.DataFrame:
    """Relaciones de la malla: para cursar `codigo_materia` hay que aprobar `codigo_prerrequisito`."""
    return _leer("""
        SELECT m.codigo_materia, p.codigo_materia AS codigo_prerrequisito
        FROM dw_academico.bridge_prerrequisito b
        JOIN dw_academico.dim_materia m ON m.materia_key = b.materia_key
        JOIN dw_academico.dim_materia p ON p.materia_key = b.prerrequisito_key
        ORDER BY m.codigo_materia, p.codigo_materia
    """)


def costo_por_materia(filtros: Filtros) -> pd.DataFrame:
    """Costo y reprobación de cada materia con los filtros elegidos. Solo las
    materias con inscripciones aparecen: el resto de la malla se une en Python."""
    where, params = _condiciones(filtros)
    return _leer(f"""
        SELECT m.codigo_materia,
               COUNT(*) FILTER (WHERE f.reprobado)                          AS reprobados,
               COUNT(*) FILTER (WHERE f.cerrada)                            AS cerradas,
               COUNT(DISTINCT f.estudiante_key) FILTER (WHERE f.reprobado)  AS estudiantes_reprobados,
               COALESCE(SUM(f.costo_reprobacion), 0)                        AS costo_reprobacion
        {DESDE_HECHOS}
        JOIN dw_academico.dim_materia m ON m.materia_key = f.materia_key
        {where}
        GROUP BY m.codigo_materia
    """, params)


# ---------------------------------------------------------------------------
# Dashboard estratégico y cubo OLAP — datos reales que reemplazan las maquetas
# ---------------------------------------------------------------------------

def aprobacion_por_ciclo(filtros: Filtros) -> pd.DataFrame:
    """Inscripciones con nota final y reprobadas de cada ciclo del plan."""
    where, params = _condiciones(filtros)
    return _leer(f"""
        SELECT m.ciclo_plan,
               COUNT(*) FILTER (WHERE f.cerrada)               AS cerradas,
               COUNT(*) FILTER (WHERE f.reprobado)             AS reprobados,
               COALESCE(SUM(f.costo_reprobacion), 0)           AS costo_reprobacion
        {DESDE_HECHOS_DIAGNOSTICO} {where}
        GROUP BY m.ciclo_plan ORDER BY m.ciclo_plan
    """, params)


def cubo(filtros: Filtros, dimensiones: list[str], modo: str) -> pd.DataFrame:
    """Cubo OLAP: las dimensiones salen del catálogo de app/olap.py (nunca de texto
    del usuario) y los filtros van como parámetros ligados. Devuelve una fila más
    que el límite para que la pantalla sepa si el resultado se truncó."""
    from . import olap  # diferido: olap importa indicadores, que no necesita la base
    where, params = _condiciones(filtros)
    return _leer(olap.construir_sql(dimensiones, modo, f"{DESDE_HECHOS_DIAGNOSTICO} {where}"), params)
