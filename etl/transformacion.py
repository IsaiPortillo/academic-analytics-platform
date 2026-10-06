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
