"""Carga al modelo dimensional dw_academico — SCRUM-35 (Fase 3.3).

Toma lo que produce el pipeline de SCRUM-34 (ya limpio, enriquecido y con la
anonimización verificada) y lo escribe en el esquema estrella definido en
database/oltp/10_dw_academico.sql.

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
from .conexiones import engine
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
TABLAS_DW = ["dim_periodo", "dim_carrera", "dim_materia", "dim_estudiante", "fact_inscripcion"]


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

    h = ds["hechos_inscripcion"]
    materia = dim_materia.set_index("materia_id")
    fact = pd.DataFrame({
        "inscripcion_id": h["inscripcion_id"],
        "periodo_key": h["periodo_id"].map(_mapa(dim_periodo, "periodo_id", "periodo_key")),
        "materia_key": h["materia_id"].map(materia["materia_key"]),
        "estudiante_key": h["estudiante_id"].map(_mapa(dim_estudiante, "estudiante_id", "estudiante_key")),
        # La carrera que oferta la materia: es la que asume su costo.
        "carrera_key": h["materia_id"].map(materia["carrera_key"]),
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
        "sesiones": h["sesiones"],
        "presentes": h["presentes"],
        "ausentes": h["ausentes"],
        "porcentaje_asistencia": h["porcentaje_asistencia"],
        "turno": h["turno"],
        "patron_riesgo": h["patron_riesgo"],
    })

    llaves = ["periodo_key", "materia_key", "estudiante_key", "carrera_key"]
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
        "fact_inscripcion": fact,
    }


def cargar_dw(resultado: ResultadoTransformacion) -> dict[str, int]:
    """Recarga completa y atómica del DW. Devuelve filas cargadas por tabla."""
    tablas = preparar_tablas(resultado)
    with engine.begin() as conexion:
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
    except (ErrorAnonimizacion, ErrorIntegridad) as exc:
        print(f"\n[DETENIDO] {exc}\nEl DW no se modificó.", file=sys.stderr)
        return 1

    for nombre, n in filas.items():
        print(f"      {nombre:<18} {n:>8,} filas")
    print("\nDW cargado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
