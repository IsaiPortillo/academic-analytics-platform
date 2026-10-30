"""Auditoría — consulta de la bitácora de notas y del historial de actas.

Solo lectura y solo coordinador: el esquema auditoria lo escriben únicamente
las funciones SECURITY DEFINER de los triggers (database/oltp/09 y 17), así que
lo que se ve aquí no lo pudo fabricar ni alterar ningún rol de la aplicación.
"""

from datetime import date, timedelta
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..exportar import FORMATOS, Columna, Reporte, formatear, responder
from ..importar import fecha_de_filtro
from ..templating import templates

router = APIRouter(prefix="/auditoria", tags=["auditoría"])

LIMITE_PANTALLA = 500
OPERACIONES = {"I": "Registro", "U": "Cambio", "D": "Eliminación"}
VISTAS = ("notas", "actas")


def _filtros(desde: Optional[date], hasta: Optional[date], usuario: Optional[str],
             operacion: Optional[str], periodo_id: Optional[int], columna_fecha: str):
    condiciones, params = [], {}
    if desde:
        condiciones.append(f"{columna_fecha} >= :desde")
        params["desde"] = desde
    if hasta:
        # Hasta inclusive: todo el día elegido.
        condiciones.append(f"{columna_fecha} < :hasta")
        params["hasta"] = hasta + timedelta(days=1)
    if usuario:
        condiciones.append("l.usuario_app = :usuario")
        params["usuario"] = usuario
    if operacion in OPERACIONES and columna_fecha == "l.fecha_modificacion":
        condiciones.append("l.operacion = :operacion")
        params["operacion"] = operacion
    if periodo_id:
        condiciones.append("s.periodo_id = :periodo_id")
        params["periodo_id"] = periodo_id
    return ("WHERE " + " AND ".join(condiciones)) if condiciones else "", params


def consultar_notas(db: Session, **filtros):
    where, params = _filtros(columna_fecha="l.fecha_modificacion", **filtros)
    return db.execute(text(f"""
        SELECT l.fecha_modificacion, COALESCE(l.usuario_app, '(fuera de la app)') AS usuario_app,
               l.usuario_db, l.operacion, i.estudiante_id, p.codigo_periodo, m.codigo_materia,
               s.numero_seccion, COALESCE(l.evaluacion_nombre, '(evaluación eliminada)') AS evaluacion,
               l.nota_anterior, l.nota_nueva
        FROM auditoria.log_cambios_notas l
        LEFT JOIN academico_oltp.inscripciones i ON i.inscripcion_id = l.inscripcion_id
        LEFT JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
        LEFT JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
        LEFT JOIN academico_oltp.periodos_academicos p ON p.periodo_id = s.periodo_id
        {where}
        ORDER BY l.fecha_modificacion DESC, l.log_id DESC
    """), params).all()


def consultar_actas(db: Session, **filtros):
    filtros.pop("operacion", None)
    where, params = _filtros(columna_fecha="l.fecha", operacion=None, **filtros)
    return db.execute(text(f"""
        SELECT l.fecha, l.accion, COALESCE(l.usuario_app, '(fuera de la app)') AS usuario_app,
               l.usuario_db, p.codigo_periodo, m.codigo_materia, s.numero_seccion,
               cardinality(l.inscripciones) AS inscripciones, l.motivo
        FROM auditoria.log_actas l
        JOIN academico_oltp.secciones s ON s.seccion_id = l.seccion_id
        JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
        JOIN academico_oltp.periodos_academicos p ON p.periodo_id = s.periodo_id
        {where}
        ORDER BY l.fecha DESC, l.log_id DESC
    """), params).all()


COLUMNAS_NOTAS = [
    Columna("fecha", "Fecha", "fecha_hora", 1.2),
    Columna("usuario_app", "Usuario", "texto", 1.0),
    Columna("rol_db", "Rol", "texto", 1.0),
    Columna("operacion", "Operación", "texto", 0.9),
    Columna("estudiante_id", "Estudiante", "id", 0.8),
    Columna("periodo", "Período", "texto", 0.7),
    Columna("materia", "Materia", "texto", 0.7),
    Columna("seccion", "Secc.", "id", 0.5),
    Columna("evaluacion", "Evaluación", "texto", 1.4),
    Columna("nota_anterior", "Antes", "decimal", 0.6),
    Columna("nota_nueva", "Después", "decimal", 0.6),
]
COLUMNAS_ACTAS = [
    Columna("fecha", "Fecha", "fecha_hora", 1.2),
    Columna("accion", "Acción", "texto", 0.9),
    Columna("usuario_app", "Usuario", "texto", 1.0),
    Columna("rol_db", "Rol", "texto", 1.0),
    Columna("periodo", "Período", "texto", 0.7),
    Columna("materia", "Materia", "texto", 0.7),
    Columna("seccion", "Secc.", "id", 0.5),
    Columna("inscripciones", "Inscripciones", "entero", 0.9),
    Columna("motivo", "Motivo", "texto", 2.0),
]


def _filtros_legibles(db, desde, hasta, usuario, operacion, periodo_id, vista):
    legibles = [("Desde", formatear(desde, "fecha") if desde else "el inicio"),
                ("Hasta", formatear(hasta, "fecha") if hasta else "hoy")]
    if usuario:
        legibles.append(("Usuario", usuario))
    if vista == "notas" and operacion in OPERACIONES:
        legibles.append(("Operación", OPERACIONES[operacion]))
    if periodo_id:
        codigo = db.scalar(text("SELECT codigo_periodo FROM academico_oltp.periodos_academicos "
                                "WHERE periodo_id = :p"), {"p": periodo_id})
        legibles.append(("Período", codigo or str(periodo_id)))
    return legibles


def construir_reporte(db: Session, vista: str, **filtros) -> Reporte:
    legibles = _filtros_legibles(db, vista=vista, **filtros)
    if vista == "actas":
        filas = [(f.fecha, f.accion.capitalize(), f.usuario_app, f.usuario_db, f.codigo_periodo,
                  f.codigo_materia, f.numero_seccion, f.inscripciones, f.motivo or "")
                 for f in consultar_actas(db, **filtros)]
        return Reporte("Historial de actas", "historial_actas", COLUMNAS_ACTAS, filas, legibles)
    filas = [(f.fecha_modificacion, f.usuario_app, f.usuario_db, OPERACIONES.get(f.operacion, f.operacion),
              f.estudiante_id, f.codigo_periodo, f.codigo_materia, f.numero_seccion, f.evaluacion,
              f.nota_anterior, f.nota_nueva)
             for f in consultar_notas(db, **filtros)]
    return Reporte("Bitácora de notas", "bitacora_notas", COLUMNAS_NOTAS, filas, legibles)


def _params(desde: Optional[str] = Query(None), hasta: Optional[str] = Query(None),
            usuario: Optional[str] = Query(None), operacion: Optional[str] = Query(None),
            periodo_id: Optional[int] = Query(None)):
    # Fechas escritas (dd/mm/aaaa, ddmmaaaa o aaaa-mm-dd): una que no se entiende se ignora.
    return {"desde": fecha_de_filtro(desde)[0], "hasta": fecha_de_filtro(hasta)[0],
            "usuario": (usuario or "").strip() or None, "operacion": operacion or None, "periodo_id": periodo_id}


def _fechas_invalidas(desde: Optional[str] = Query(None), hasta: Optional[str] = Query(None)) -> dict:
    """{"desde": "31/02/2025"}: lo que se escribió y no se entendió, para avisarlo y conservarlo."""
    return {k: v for k, v in (("desde", fecha_de_filtro(desde)[1]), ("hasta", fecha_de_filtro(hasta)[1])) if v}


@router.get("/exportar")
def exportar(
    formato: str = Query("csv", pattern=f"^({'|'.join(FORMATOS)})$"),
    vista: str = Query("notas"),
    filtros: dict = Depends(_params),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    return responder(construir_reporte(db, vista if vista in VISTAS else "notas", **filtros), formato)


@router.get("")
def ver(
    request: Request,
    vista: str = Query("notas"),
    filtros: dict = Depends(_params),
    invalidas: dict = Depends(_fechas_invalidas),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    vista = vista if vista in VISTAS else "notas"
    reporte = construir_reporte(db, vista, **filtros)
    filas = [[(formatear(v, c.tipo), c.tipo) for c, v in zip(reporte.columnas, fila)]
             for fila in reporte.filas[:LIMITE_PANTALLA]]
    usuarios = db.scalars(text(
        "SELECT DISTINCT usuario_app FROM ("
        " SELECT usuario_app FROM auditoria.log_cambios_notas"
        " UNION SELECT usuario_app FROM auditoria.log_actas"
        " UNION SELECT username FROM academico_oltp.usuarios) u "
        "WHERE usuario_app IS NOT NULL ORDER BY 1")).all()
    periodos = db.execute(text(
        "SELECT periodo_id, codigo_periodo FROM academico_oltp.periodos_academicos "
        "ORDER BY anio DESC, ciclo_romano DESC")).all()
    consulta = urlencode({k: v for k, v in filtros.items() if v})
    return templates.TemplateResponse(request, "modulos/auditoria.html", {
        "usuario": usuario,
        "vista": vista,
        "filtros": filtros,
        "fechas_invalidas": invalidas,
        "consulta": consulta,
        "reporte": reporte,
        "filas": filas,
        "total": len(reporte.filas),
        "limite": LIMITE_PANTALLA,
        "usuarios": usuarios,
        "periodos": periodos,
        "operaciones": OPERACIONES,
    })
