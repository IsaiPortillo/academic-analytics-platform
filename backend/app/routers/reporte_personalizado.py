"""Reportes personalizados (coordinador). La lógica está en app/reporte_personalizado.py."""

from datetime import date
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import graficas
from .. import reporte_personalizado as rp
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..exportar import FORMATOS, formatear, responder
from ..models import Docente, Materia, PeriodoAcademico
from ..templating import templates

router = APIRouter(prefix="/reportes/personalizado", tags=["reportes"])
COORDINADOR = requiere_rol("rol_coordinador")


def _parametros(
    tema: str = Query("asistencia"),
    dimension: str = Query("mes"),
    desglose: Optional[str] = Query(None),
    metrica: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    periodo_id: Optional[str] = Query(None),
    materia_id: Optional[str] = Query(None),
    docente_id: Optional[str] = Query(None),
    turno: Optional[str] = Query(None),
    grafica: str = Query("lineas"),
    orden: str = Query("natural"),
) -> rp.Parametros:
    # Los <select> envían "" para «Todos»: se trata como ausente, no como error.
    def entero(v):
        return int(v) if v and v.isdigit() else None
    return rp.Parametros(tema, dimension, desglose or None, metrica or None, desde, hasta, entero(periodo_id),
                         entero(materia_id), entero(docente_id), turno or None, grafica, orden).normalizar()


def _catalogos(db: Session):
    return {
        "periodos": db.scalars(select(PeriodoAcademico).order_by(PeriodoAcademico.anio.desc(),
                                                                  PeriodoAcademico.ciclo_romano.desc())).all(),
        "materias": db.scalars(select(Materia).order_by(Materia.codigo_materia)).all(),
        "docentes": db.scalars(select(Docente).order_by(Docente.codigo_docente)).all(),
    }


def _etiquetas(p: rp.Parametros, catalogos) -> list[tuple[str, str]]:
    tema = rp.TEMAS[p.tema]
    etiquetas = [("Tema", tema.titulo), ("Agrupado por", rp.DIMENSIONES[p.dimension].etiqueta)]
    if p.desglose:
        etiquetas.append(("Desglose", rp.DIMENSIONES[p.desglose].etiqueta))
    if p.desde or p.hasta:
        etiquetas.append(("Fechas", f"{formatear(p.desde, 'fecha') if p.desde else 'inicio'} a "
                                    f"{formatear(p.hasta, 'fecha') if p.hasta else 'hoy'}"))
    nombres = {"periodo_id": ("Período", {x.periodo_id: x.codigo_periodo for x in catalogos["periodos"]}),
               "materia_id": ("Materia", {x.materia_id: x.codigo_materia for x in catalogos["materias"]}),
               "docente_id": ("Docente", {x.docente_id: x.codigo_docente for x in catalogos["docentes"]})}
    for campo, (etiqueta, mapa) in nombres.items():
        if getattr(p, campo):
            etiquetas.append((etiqueta, mapa.get(getattr(p, campo), str(getattr(p, campo)))))
    if p.turno:
        etiquetas.append(("Turno", p.turno.capitalize()))
    return etiquetas


def consulta_de(p: rp.Parametros) -> str:
    valores = {"tema": p.tema, "dimension": p.dimension, "desglose": p.desglose, "metrica": p.metrica,
               "desde": p.desde, "hasta": p.hasta, "periodo_id": p.periodo_id, "materia_id": p.materia_id,
               "docente_id": p.docente_id, "turno": p.turno, "grafica": p.grafica, "orden": p.orden}
    return urlencode({k: v for k, v in valores.items() if v not in (None, "")})


@router.get("/exportar")
def exportar(
    formato: str = Query("csv", pattern=f"^({'|'.join(FORMATOS)})$"),
    p: rp.Parametros = Depends(_parametros),
    usuario: UsuarioSesion = Depends(COORDINADOR),
    db: Session = Depends(get_db),
):
    reporte, _ = rp.construir(db, p, _etiquetas(p, _catalogos(db)))
    return responder(reporte, formato)


def _grafica_pantalla(reporte, p: rp.Parametros):
    g = reporte.grafico
    if not g or not reporte.filas:
        return None, []
    categorias = [f[0] for f in reporte.filas]
    series = [(reporte.columnas[c].etiqueta, [None if f[c] is None else float(f[c]) for f in reporte.filas])
              for c in g.columnas]
    if g.tipo == "barras":
        valores = series[0][1]
        maximo = max((v for v in valores if v is not None), default=0) or 1
        barras = [{"etiqueta": c, "valor": formatear(v, g.tipo_valor), "pct": (v or 0) / maximo}
                  for c, v in zip(categorias, valores)][:40]
        return None, barras
    dibujar = graficas.lineas if g.tipo == "lineas" else graficas.columnas
    return dibujar(reporte.titulo, categorias[:60], [(n, v[:60]) for n, v in series], g.tipo_valor), []


@router.get("")
def ver(
    request: Request,
    p: rp.Parametros = Depends(_parametros),
    usuario: UsuarioSesion = Depends(COORDINADOR),
    db: Session = Depends(get_db),
):
    catalogos = _catalogos(db)
    reporte, resumen = rp.construir(db, p, _etiquetas(p, catalogos))
    svg, barras = _grafica_pantalla(reporte, p)
    filas = [[(formatear(v, c.tipo), c.tipo) for c, v in zip(reporte.columnas, fila)] for fila in reporte.filas]
    tema = rp.TEMAS[p.tema]
    return templates.TemplateResponse(request, "modulos/reporte_personalizado.html", {
        "usuario": usuario, "p": p, "reporte": reporte, "resumen": resumen, "filas": filas,
        "svg": svg, "barras": barras, "consulta": consulta_de(p),
        "temas": rp.TEMAS, "tema": tema, "dimensiones": [(k, rp.DIMENSIONES[k]) for k in rp.dimensiones_de(p.tema)],
        "graficas": rp.GRAFICAS, "atajos": [(t, d, urlencode(q)) for t, d, q in rp.ATAJOS], **catalogos,
    })
