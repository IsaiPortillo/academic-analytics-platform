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
