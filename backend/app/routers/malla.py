"""Malla curricular (coordinador): prerrequisitos en Neo4j. Ver app/malla.py."""

from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import malla, recarga
from ..avisos import redirigir, tomar_aviso
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import Materia
from ..templating import templates

router = APIRouter(prefix="/admin/malla", tags=["malla"])
COORDINADOR = requiere_rol("rol_coordinador")


def _materias(db: Session) -> dict[str, dict]:
    return {m.codigo_materia: {"codigo": m.codigo_materia, "nombre": m.nombre, "uv": m.unidades_valorativas,
                               "ciclo": m.ciclo_plan, "activo": m.activo}
            for m in db.scalars(select(Materia).order_by(Materia.ciclo_plan, Materia.codigo_materia)).all()}


@router.get("")
def ver(request: Request, usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    ok, error = tomar_aviso(request)
    materias = _materias(db)
    nodos, aristas, no_disponible = {}, [], None
    try:
        nodos, aristas = malla.leer()
    except malla.MallaNoDisponible as exc:
        no_disponible = str(exc)
    requisitos = defaultdict(list)
    for a in aristas:
        requisitos[a.materia].append(a.requisito)
    filas = [{**m, "area": nodos.get(c, {}).get("area"), "en_grafo": c in nodos,
              "requisitos": requisitos.get(c, [])} for c, m in materias.items()]
    huerfanos = sorted(set(nodos) - set(materias))
    areas = sorted({n["area"] for n in nodos.values() if n.get("area")})
    return templates.TemplateResponse(request, "modulos/admin_malla.html", {
        "usuario": usuario, "ok": ok, "error": error, "no_disponible": no_disponible,
        "filas": filas, "materias": materias, "aristas": aristas, "huerfanos": huerfanos, "areas": areas,
        "sin_nodo": sum(1 for f in filas if not f["en_grafo"]),
        "carga_en_curso": recarga.hay_carga_en_curso(),
    })


@router.post("/agregar")
def agregar(request: Request, materia: str = Form(...), requisito: str = Form(...),
            usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    materias = _materias(db)
    if materia not in materias or requisito not in materias:
        return redirigir(request, "/admin/malla", error="Elige dos materias del catálogo.")
    try:
        malla.agregar(materias[materia], materias[requisito])
    except (malla.ReglaMalla, malla.MallaNoDisponible) as exc:
        return redirigir(request, "/admin/malla", error=str(exc))
    return redirigir(request, "/admin/malla", ok=f"{materia} ahora exige {requisito}. "
                                                 "Recarga el Data Warehouse para verlo en la red curricular.")


@router.post("/quitar")
def quitar(request: Request, materia: str = Form(...), requisito: str = Form(...),
           usuario: UsuarioSesion = Depends(COORDINADOR)):
    try:
        quitado = malla.quitar(materia, requisito)
    except malla.MallaNoDisponible as exc:
        return redirigir(request, "/admin/malla", error=str(exc))
    if not quitado:
        return redirigir(request, "/admin/malla", error="Ese prerrequisito ya no existía.")
    return redirigir(request, "/admin/malla", ok=f"{materia} ya no exige {requisito}. "
                                                 "Recarga el Data Warehouse para verlo en la red curricular.")


@router.post("/sincronizar")
async def sincronizar(request: Request, usuario: UsuarioSesion = Depends(COORDINADOR),
                      db: Session = Depends(get_db)):
    formulario = await request.form()
    areas = {k[5:]: str(v).strip()[:60] for k, v in formulario.items() if k.startswith("area_") and str(v).strip()}
    try:
        n = malla.sincronizar(list(_materias(db).values()), areas)
    except malla.MallaNoDisponible as exc:
        return redirigir(request, "/admin/malla", error=str(exc))
    return redirigir(request, "/admin/malla", ok=f"{n} materia(s) sincronizadas con el grafo.")
