"""Administración de catálogos (coordinador): períodos, secciones, materias,
docentes, estudiantes, carreras y departamentos.

Una sola pantalla de lista y un solo formulario para todos, armados desde
app/catalogos.py. Eliminar solo funciona si nada depende del registro (las FK
son ON DELETE RESTRICT): un estudiante con inscripciones o una materia con
secciones no se borra, se desactiva, y así el historial queda intacto.
"""

import csv
import io
from datetime import date
from math import ceil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .. import carga_catalogos as carga, filtros_catalogo as fl
from ..avisos import redirigir, tomar_aviso
from ..catalogos import (CATALOGOS, Catalogo, aplicar, hash_carnet, leer_formulario, valor_para_formulario,
                         valor_para_lista)
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..importar import TIPO_XLSX, ErrorArchivo, leer_filas
from ..models import Estudiante, PeriodoAcademico
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


LIMITE_EXPORTACION = 20000


def _consulta_filtrada(db: Session, catalogo: Catalogo, seleccion: fl.Seleccion):
    """Todos los registros del catálogo que cumplen la búsqueda y los filtros elegidos."""
    consulta = select(catalogo.modelo)
    texto = seleccion.buscar
    if texto:
        condiciones = [getattr(catalogo.modelo, a).ilike(f"%{texto}%") for a in catalogo.busqueda]
        if texto.isdigit():
            condiciones.append(_clave(catalogo) == int(texto))
        if catalogo.slug == "estudiantes":
            # Por carnet: se compara su hash; el carnet no se guarda ni se registra.
            condiciones.append(Estudiante.carnet_hash == hash_carnet(texto))
        consulta = consulta.where(or_(*condiciones)) if condiciones else consulta.where(False)
    return fl.aplicar(consulta, catalogo, seleccion)


def _por_defecto(db: Session, catalogo: Catalogo) -> dict:
    """Las secciones se listan, mientras no se elija otra cosa, del último período."""
    if not catalogo.filtro_periodo:
        return {}
    ultimo = db.scalar(select(PeriodoAcademico.periodo_id).order_by(
        PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc()).limit(1))
    return {"periodo_id": str(ultimo)} if ultimo else {}


def _tabla(db: Session, catalogo: Catalogo, registros) -> tuple[list[dict], list]:
    """Columnas (con su clave de orden) y filas de una lista de registros."""
    etiquetas = _etiquetas_fk(db, catalogo)
    campos = [c for c in catalogo.campos if c.en_lista]
    columnas = ([{"titulo": nombre, "clave": "id" if nombre == "ID" else None} for nombre, _ in catalogo.columnas_extra]
                + [{"titulo": c.etiqueta, "clave": c.nombre} for c in campos])
    filas = [(getattr(r, _clave(catalogo).name),
              [f(r) for _, f in catalogo.columnas_extra] + [valor_para_lista(c, r, etiquetas) for c in campos])
             for r in registros]
    return columnas, filas


@router.get("/{slug}")
def listar(
    request: Request,
    slug: str,
    usuario: UsuarioSesion = Depends(COORDINADOR),
    db: Session = Depends(get_db),
):
    catalogo = _catalogo(slug)
    ok, error = tomar_aviso(request)
    por_defecto = _por_defecto(db, catalogo)
    seleccion = fl.leer(catalogo, request.query_params, por_defecto)
    consulta = _consulta_filtrada(db, catalogo, seleccion)
    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    total_catalogo = db.scalar(select(func.count()).select_from(catalogo.modelo))
    paginas = max(ceil(total / seleccion.por_pagina), 1)
    pagina = min(seleccion.pagina, paginas)
    registros = db.scalars(consulta.order_by(*fl.clausulas_de_orden(catalogo, seleccion))
                           .offset((pagina - 1) * seleccion.por_pagina).limit(seleccion.por_pagina)).all()
    columnas, filas = _tabla(db, catalogo, registros)
    base = f"/admin/{slug}"
    for columna in columnas:
        clave = columna["clave"]
        if not clave:
            continue
        activa = seleccion.orden == clave
        columna["sentido"] = ("desc" if seleccion.descendente else "asc") if activa else None
        columna["url"] = f"{base}?" + fl.consulta_url(
            seleccion, orden=clave, dir="desc" if activa and not seleccion.descendente else "")
    filtros = [{"nombre": f.nombre, "etiqueta": f.etiqueta, "opciones": fl.opciones(db, f),
                "valor": seleccion.filtros.get(f.nombre, "")} for f in fl.filtros_de(catalogo)]
    return templates.TemplateResponse(request, "modulos/admin_lista.html", {
        "usuario": usuario, "catalogo": catalogo, "ok": ok, "error": error,
        "columnas": columnas, "filas": filas, "total": total, "total_catalogo": total_catalogo,
        "pagina": pagina, "paginas": paginas, "seleccion": seleccion, "filtros": filtros,
        "chips": fl.chips(db, catalogo, seleccion, base, tuple(por_defecto)),
        "limpiar": base + "?" + "&".join(f"{n}=" for n in por_defecto),
        "consulta": fl.consulta_url(seleccion), "pagina_url": base + "?" + fl.consulta_url(seleccion),
        "por_pagina_opciones": fl.POR_PAGINA_OPCIONES,
    })


@router.get("/{slug}/exportar")
def exportar(request: Request, slug: str, usuario: UsuarioSesion = Depends(COORDINADOR),
             db: Session = Depends(get_db)):
    """La lista tal como está filtrada y ordenada, completa (no solo la página), en CSV."""
    catalogo = _catalogo(slug)
    seleccion = fl.leer(catalogo, request.query_params, _por_defecto(db, catalogo))
    consulta = _consulta_filtrada(db, catalogo, seleccion)
    registros = db.scalars(consulta.order_by(*fl.clausulas_de_orden(catalogo, seleccion))
                           .limit(LIMITE_EXPORTACION)).all()
    columnas, filas = _tabla(db, catalogo, registros)
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([c["titulo"] for c in columnas])
    escritor.writerows(valores for _, valores in filas)
    return Response("﻿" + salida.getvalue(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{catalogo.slug}.csv"', "Cache-Control": "no-store"})


# La carga masiva va antes de las rutas /{slug}/{registro_id}: «plantilla» e «importar» no son un id.

@router.get("/{slug}/plantilla")
def descargar_plantilla(slug: str, usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    catalogo = _catalogo(slug)
    return Response(carga.construir_plantilla(db, catalogo), media_type=TIPO_XLSX, headers={
        "Content-Disposition": f'attachment; filename="plantilla_{catalogo.slug}.xlsx"',
        "Cache-Control": "no-store"})


def _mostrar(campo, texto: str, etiquetas_fk: dict) -> str:
    if campo.nombre == "carnet":
        return "Anonimizado"
    if campo.tipo == "bool":
        return "Sí" if texto == "on" else "No"
    if campo.tipo == "fk" and texto:
        return carga.codigo_de_referencia(etiquetas_fk.get(campo.nombre, {}).get(int(texto), texto))
    if campo.tipo == "fecha" and texto:
        return f"{date.fromisoformat(texto):%d/%m/%Y}"
    return texto or "—"


@router.post("/{slug}/importar")
async def importar(request: Request, slug: str, archivo: UploadFile = File(...),
                   usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    catalogo = _catalogo(slug)
    destino = f"/admin/{slug}"
    try:
        filas = await leer_filas(archivo)
        existentes = carga.cargar_existentes(
            db, catalogo, carga.carnets_del_archivo(filas) if catalogo.slug == "estudiantes" else None)
        cambios, errores = carga.analizar(catalogo, filas, carga.cargar_refs(db, catalogo), existentes)
    except ErrorArchivo as exc:
        return redirigir(request, destino, error=str(exc))
    etiquetas_fk = _etiquetas_fk(db, catalogo)
    pendientes = [c for c in cambios if c.tipo != "igual"]
    return templates.TemplateResponse(request, "modulos/importar_vista_previa.html", {
        "usuario": usuario,
        "titulo": f"Carga masiva · {catalogo.titulo}",
        "subtitulo": f"{len(cambios):,} fila(s) leída(s)",
        "archivo": archivo.filename,
        "columnas": ["Fila"] + carga.cabeceras(catalogo) + ["Qué cambia"],
        "filas": [(c.tipo, [c.fila] + [_mostrar(campo, c.formulario.get(campo.nombre, ""), etiquetas_fk)
                                       for campo in catalogo.campos]
                           + [", ".join(c.diferencias) if c.tipo == "cambio" else "—"]) for c in pendientes],
        "conteo": {t: sum(1 for c in cambios if c.tipo == t) for t in ("nueva", "cambio", "igual")},
        "etiquetas": {"nueva": "Se crean", "cambio": "Se actualizan", "igual": "Sin cambios"},
        "errores": errores,
        "accion": f"{destino}/importar/confirmar",
        "ocultos": [("datos", carga.empaquetar(catalogo, cambios))],
        "volver": destino,
    })


@router.post("/{slug}/importar/confirmar")
def confirmar_importacion(request: Request, slug: str, datos: str = Form(...),
                          usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    catalogo = _catalogo(slug)
    destino = f"/admin/{slug}"
    try:
        cambios = carga.leer_carga(catalogo, datos)
        carga.aplicar_carga(db, catalogo, cambios)
    except carga.ErrorCarga as exc:
        return redirigir(request, destino, error=str(exc))
    except DBAPIError as exc:
        fila = getattr(exc, "fila", None)
        return redirigir(request, destino, error=(f"Fila {fila}: " if fila else "") + mensaje_bd(exc, catalogo)
                         + " No se aplicó ningún cambio.")
    creados = sum(1 for c in cambios if c.tipo == "nueva")
    return redirigir(request, destino, ok=f"Carga masiva de {catalogo.titulo.lower()} aplicada: "
                                          f"{creados} nuevo(s) y {len(cambios) - creados} actualizado(s).")


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
