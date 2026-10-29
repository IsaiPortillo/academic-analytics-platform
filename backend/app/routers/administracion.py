"""Administración de catálogos (coordinador): períodos, secciones, materias,
docentes, estudiantes, carreras y departamentos.

Una sola pantalla de lista y un solo formulario para todos, armados desde
app/catalogos.py. Eliminar solo funciona si nada depende del registro (las FK
son ON DELETE RESTRICT): un estudiante con inscripciones o una materia con
secciones no se borra, se desactiva, y así el historial queda intacto.
"""

from math import ceil
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..avisos import redirigir, tomar_aviso
from ..catalogos import (CATALOGOS, Catalogo, aplicar, hash_carnet, leer_formulario, valor_para_formulario,
                         valor_para_lista)
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import Estudiante, PeriodoAcademico, Seccion
from ..templating import templates

router = APIRouter(prefix="/admin", tags=["administración"])

POR_PAGINA = 50
COORDINADOR = requiere_rol("rol_coordinador")


def _catalogo(slug: str) -> Catalogo:
    if slug not in CATALOGOS:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado")
    return CATALOGOS[slug]


def _clave(catalogo: Catalogo):
    return catalogo.modelo.__mapper__.primary_key[0]


def mensaje_bd(exc: DBAPIError, catalogo: Catalogo) -> str:
    diag = getattr(exc.orig, "diag", None)
    codigo = getattr(exc.orig, "pgcode", None)
    if codigo == "23505":   # unique_violation
        return (f"Ya existe {'una' if catalogo.femenino else 'un'} {catalogo.singular} "
                "con ese código o combinación de datos.")
    if codigo == "23503":   # foreign_key_violation
        tabla = diag.table_name if diag is not None else ""
        if tabla == catalogo.modelo.__tablename__:
            return "Uno de los datos elegidos ya no existe. Vuelve a cargar el formulario."
        return (f"No se puede eliminar: hay registros que dependen de este ({tabla or 'otra tabla'}). "
                "Si ya no se usa, desactívalo.")
    if codigo == "23514":   # check_violation
        return "Algún valor está fuera de lo permitido por la base de datos."
    return diag.message_primary if diag is not None and diag.message_primary else "La base de datos rechazó la operación."


def _etiquetas_fk(db: Session, catalogo: Catalogo) -> dict:
    return {c.nombre: dict(c.fk(db)) for c in catalogo.campos if c.tipo == "fk"}


@router.get("")
def inicio(request: Request, usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    tarjetas = [(c, db.scalar(select(func.count()).select_from(c.modelo))) for c in CATALOGOS.values()]
    return templates.TemplateResponse(request, "modulos/admin_inicio.html", {
        "usuario": usuario, "tarjetas": tarjetas})


@router.get("/{slug}")
def listar(
    request: Request,
    slug: str,
    buscar: Optional[str] = Query(None),
    periodo_id: Optional[int] = Query(None),
    pagina: int = Query(1, ge=1),
    usuario: UsuarioSesion = Depends(COORDINADOR),
    db: Session = Depends(get_db),
):
    catalogo = _catalogo(slug)
    ok, error = tomar_aviso(request)
    consulta = select(catalogo.modelo)
    texto = (buscar or "").strip()
    if texto:
        condiciones = [getattr(catalogo.modelo, a).ilike(f"%{texto}%") for a in catalogo.busqueda]
        if texto.isdigit():
            condiciones.append(_clave(catalogo) == int(texto))
        if catalogo.slug == "estudiantes":
            # Por carnet: se compara su hash; el carnet no se guarda ni se registra.
            condiciones.append(Estudiante.carnet_hash == hash_carnet(texto))
        consulta = consulta.where(or_(*condiciones)) if condiciones else consulta.where(False)
    periodos = []
    if catalogo.filtro_periodo:
        periodos = db.scalars(select(PeriodoAcademico).order_by(
            PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc())).all()
        if periodo_id is None and periodos:
            periodo_id = periodos[0].periodo_id
        if periodo_id:
            consulta = consulta.where(Seccion.periodo_id == periodo_id)
    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    paginas = max(ceil(total / POR_PAGINA), 1)
    pagina = min(pagina, paginas)
    registros = db.scalars(consulta.order_by(*catalogo.orden)
                           .offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA)).all()
    etiquetas = _etiquetas_fk(db, catalogo)
    columnas = [c for c in catalogo.campos if c.en_lista]
    filas = [(getattr(r, _clave(catalogo).name),
              [f(r) for _, f in catalogo.columnas_extra] + [valor_para_lista(c, r, etiquetas) for c in columnas])
             for r in registros]
    filtros = {k: v for k, v in (("buscar", texto), ("periodo_id", periodo_id)) if v}
    return templates.TemplateResponse(request, "modulos/admin_lista.html", {
        "usuario": usuario, "catalogo": catalogo, "ok": ok, "error": error,
        "cabeceras": [n for n, _ in catalogo.columnas_extra] + [c.etiqueta for c in columnas],
        "filas": filas, "total": total, "pagina": pagina, "paginas": paginas,
        "buscar": texto, "periodos": periodos, "periodo_id": periodo_id,
        "consulta": urlencode(filtros),
    })


def _formulario(request, usuario, db, catalogo, registro, valores=None, errores=None, status_code=200):
    ok, error = tomar_aviso(request)
    opciones = {c.nombre: c.fk(db) for c in catalogo.campos if c.tipo == "fk"}
    campos = [(c, (valores or {}).get(c.nombre, valor_para_formulario(c, registro)) if valores is not None
               else valor_para_formulario(c, registro)) for c in catalogo.campos]
    return templates.TemplateResponse(request, "modulos/admin_formulario.html", {
        "usuario": usuario, "catalogo": catalogo, "registro": registro,
        "id": getattr(registro, _clave(catalogo).name) if registro is not None else None,
        "campos": campos, "opciones": opciones, "errores": errores or [], "ok": ok, "error": error,
    }, status_code=status_code)


@router.get("/{slug}/nuevo")
def nuevo(request: Request, slug: str, usuario: UsuarioSesion = Depends(COORDINADOR),
          db: Session = Depends(get_db)):
    return _formulario(request, usuario, db, _catalogo(slug), None)


def _guardar(request, usuario, db, catalogo, registro, formulario):
    creando = registro is None
    valores, errores = leer_formulario(catalogo, formulario, creando)
    crudos = {c.nombre: formulario.get(c.nombre, "") for c in catalogo.campos}
    for c in catalogo.campos:
        if c.tipo == "bool":
            crudos[c.nombre] = formulario.get(c.nombre) in ("on", "true", "1")
    if errores:
        return _formulario(request, usuario, db, catalogo, registro, crudos, errores, 422)
    try:
        # Punto de guardado y no rollback(): deshacer la transacción entera
        # también desharía el SET LOCAL ROLE, y volver a mostrar el formulario
        # (que consulta las opciones) fallaría por falta de permisos.
        with db.begin_nested():
            if creando:
                registro = catalogo.modelo()
                db.add(registro)
            aplicar(catalogo, registro, valores)
            db.flush()
            if catalogo.slug == "periodos" and valores.get("activo"):
                # Un solo período vigente.
                db.execute(update(PeriodoAcademico)
                           .where(PeriodoAcademico.periodo_id != registro.periodo_id)
                           .values(activo=False))
    except DBAPIError as exc:
        return _formulario(request, usuario, db, catalogo, None if creando else registro, crudos,
                           [mensaje_bd(exc, catalogo)], 422)
    nombre = catalogo.etiqueta(registro)
    accion = ("creada" if creando else "actualizada") if catalogo.femenino else ("creado" if creando else "actualizado")
    return redirigir(request, f"/admin/{catalogo.slug}", ok=f"{catalogo.singular.capitalize()} «{nombre}» {accion}.")


@router.post("/{slug}/nuevo")
async def crear(request: Request, slug: str, usuario: UsuarioSesion = Depends(COORDINADOR),
                db: Session = Depends(get_db)):
    return _guardar(request, usuario, db, _catalogo(slug), None, await request.form())


def _registro(db: Session, catalogo: Catalogo, registro_id: int):
    registro = db.get(catalogo.modelo, registro_id)
    if registro is None:
        raise HTTPException(status_code=404, detail=f"No existe ese {catalogo.singular}")
    return registro


@router.get("/{slug}/{registro_id}")
def editar(request: Request, slug: str, registro_id: int, usuario: UsuarioSesion = Depends(COORDINADOR),
           db: Session = Depends(get_db)):
    catalogo = _catalogo(slug)
    return _formulario(request, usuario, db, catalogo, _registro(db, catalogo, registro_id))


@router.post("/{slug}/{registro_id}")
async def actualizar(request: Request, slug: str, registro_id: int,
                     usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    catalogo = _catalogo(slug)
    return _guardar(request, usuario, db, catalogo, _registro(db, catalogo, registro_id), await request.form())


@router.post("/{slug}/{registro_id}/eliminar")
def eliminar(request: Request, slug: str, registro_id: int, usuario: UsuarioSesion = Depends(COORDINADOR),
             db: Session = Depends(get_db)):
    catalogo = _catalogo(slug)
    registro = _registro(db, catalogo, registro_id)
    nombre = catalogo.etiqueta(registro)
    try:
        db.delete(registro)
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, f"/admin/{slug}/{registro_id}", error=mensaje_bd(exc, catalogo))
    return redirigir(request, f"/admin/{slug}",
                     ok=f"{catalogo.singular.capitalize()} «{nombre}» {'eliminada' if catalogo.femenino else 'eliminado'}.")
