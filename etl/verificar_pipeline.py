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
