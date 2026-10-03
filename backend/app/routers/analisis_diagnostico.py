"""Análisis diagnóstico: correlaciones y patrones de riesgo — Fase 4.2.

Para el coordinador académico: entender por qué se reprueba y qué caracteriza
a los casos de riesgo. Nivel analítico diagnóstico (¿por qué ocurrió?) sobre
datos históricos ya observados: no predice ni recomienda.

Igual que la vista ejecutiva, NO usa database.get_db(): lee el Data Warehouse
con su propia conexión como rol_dashboard (app/dw.py), que no puede leer el
esquema operacional. Los umbrales del patrón de riesgo se importan de
app/calculos.py, los mismos que usan los reportes del sistema transaccional.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import DBAPIError

from .. import dw, indicadores_diagnostico as diag
from ..calculos import UMBRAL_FALTAS_RIESGO, UMBRAL_NOTA_APROBACION
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/analisis-diagnostico", tags=["analitica"])

TODOS = "todos"
LIMITE_ESTUDIANTES = 50


def _matriz(pares: list[dict]) -> dict:
    """Matriz simétrica de correlaciones para la plantilla (diagonal = 1)."""
    claves = list(dw.VARIABLES_CORRELACION)
    indice = {frozenset({p["x"], p["y"]}): p for p in pares}
    filas = []
    for a in claves:
        celdas = []
        for b in claves:
            if a == b:
                celdas.append({"diagonal": True})
                continue
            par = indice[frozenset({a, b})]
            r = par["r"]
            valido = r is not None and r == r  # NaN != NaN
            celdas.append({
                "r": r if valido else None,
                "n": par["n"],
                "lectura": diag.leer_correlacion(par),
                "construccion": frozenset({a, b}) in diag.PARES_POR_CONSTRUCCION,
            })
        filas.append({"etiqueta": dw.VARIABLES_CORRELACION[a][0], "celdas": celdas})
    return {"columnas": [dw.VARIABLES_CORRELACION[c][0] for c in claves], "filas": filas}


def _barras_tasa(filas: list[dict]) -> list[dict]:
    """Tasa de reprobación por grupo, escalada contra la mayor para las barras."""
    for f in filas:
        f["tasa"] = f["reprobadas"] / f["cerradas"] if f["cerradas"] else 0.0
    maximo = max((f["tasa"] for f in filas), default=0.0)
    for f in filas:
        f["pct"] = f["tasa"] / maximo if maximo else 0.0
        f["tasa_texto"] = f"{f['tasa'] * 100:.1f} %"
    return filas


@router.get("")
def analisis_diagnostico(
    request: Request,
    periodo: Optional[str] = Query(None),
    departamento: Optional[str] = Query(None),
    carrera: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
):
    plantilla = "modulos/analisis_diagnostico.html"
    try:
        periodos = dw.catalogo_periodos()
        carreras = dw.catalogo_carreras()
    except dw.DWNoConfigurado as exc:
        return templates.TemplateResponse(request, plantilla, {"usuario": usuario, "error": str(exc)})
    except DBAPIError:
        return templates.TemplateResponse(request, plantilla, {
            "usuario": usuario,
            "error": "No se pudo leer el Data Warehouse. Verifica que exista (database/oltp/10 a 12) "
                     "y que esté cargado: python -m etl.carga",
        })

    # El diagnóstico mira el historial: por defecto, todos los períodos.
    codigos = periodos["codigo_periodo"].tolist()
    sel_periodos = (periodo,) if periodo in codigos else ()
    departamentos = (carreras[["codigo_departamento", "nombre_departamento"]]
                     .drop_duplicates().to_dict("records"))
    if departamento not in {d["codigo_departamento"] for d in departamentos}:
        departamento = None
    carreras_visibles = carreras if not departamento else carreras[
        carreras["codigo_departamento"] == departamento
    ]
    if carrera not in set(carreras_visibles["codigo_carrera"]):
        carrera = None
    filtros = dw.Filtros(sel_periodos, (carrera,) if carrera else (),
                         (departamento,) if departamento else ())

    pares = dw.correlaciones(filtros).to_dict("records")

    grupos = {bool(f["sobre_umbral"]): f
              for f in dw.reprobacion_por_ausencias(filtros, UMBRAL_FALTAS_RIESGO).to_dict("records")}
    ausencias = _barras_tasa([
        dict(grupos[clave], segmento=etiqueta) for clave, etiqueta in (
            (True, f"{UMBRAL_FALTAS_RIESGO} o más ausencias"),
            (False, f"Menos de {UMBRAL_FALTAS_RIESGO} ausencias"),
        ) if clave in grupos
    ])

    cohortes = dw.por_cohorte(filtros).to_dict("records")
    for c in cohortes:
        c["segmento"] = f"Cohorte {c['cohorte']}"
        c["patron_texto"] = (f"{c['estudiantes_patron'] / c['estudiantes'] * 100:.1f} %"
                             if c["estudiantes"] else "—")
    cohortes = _barras_tasa(cohortes)

    segmentos = []
    for clave, (etiqueta, nombre, _, _) in dw.SEGMENTOS.items():
        filas = dw.por_segmento(filtros, clave).to_dict("records")
        segmentos.append({
            "clave": clave,
            "etiqueta": etiqueta,
            "filas": _barras_tasa(filas),
            "lectura": diag.interpretar_segmentos([dict(f) for f in filas], nombre),
            "adicional": clave == "trabaja",
        })

    resumen = dw.resumen_patron(filtros)

    return templates.TemplateResponse(request, plantilla, {
        "usuario": usuario,
        "periodos": codigos,
        "periodo": sel_periodos[0] if sel_periodos else TODOS,
        "departamentos": departamentos,
        "departamento": departamento,
        "carreras": carreras_visibles.to_dict("records"),
        "carrera": carrera,
        "etiqueta_periodo": sel_periodos[0] if sel_periodos else "todos los períodos",
        "matriz": _matriz(pares),
        "lectura_correlaciones": diag.interpretar_correlaciones(pares),
        "ausencias": ausencias,
        "lectura_ausencias": diag.interpretar_ausencias(
            grupos.get(True), grupos.get(False), UMBRAL_FALTAS_RIESGO),
        "cohortes": cohortes,
        "lectura_cohortes": diag.interpretar_cohortes([dict(c) for c in cohortes]),
        "segmentos": segmentos,
        "resumen_patron": resumen,
        "lectura_patron": diag.interpretar_patron(resumen, UMBRAL_FALTAS_RIESGO, UMBRAL_NOTA_APROBACION),
        "estudiantes": dw.estudiantes_con_patron(filtros, LIMITE_ESTUDIANTES).to_dict("records"),
        "limite_estudiantes": LIMITE_ESTUDIANTES,
        "umbral_faltas": UMBRAL_FALTAS_RIESGO,
        "umbral_nota": UMBRAL_NOTA_APROBACION,
        "ultima_carga": dw.ultima_carga(),
    })
