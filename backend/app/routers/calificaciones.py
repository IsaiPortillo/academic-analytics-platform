"""Módulo de calificaciones — SCRUM-8 (responsable: Isai Portillo).

Esqueleto listo para implementar. Recursos ya disponibles:
  - models.Calificacion, models.Evaluacion, models.Inscripcion, models.LogCambioNota
  - db (Session) ya viene con SET LOCAL ROLE aplicado según el rol del usuario
Nota: la auditoría de cambios de nota y la validación de ponderación <= 100%
ya están resueltas por triggers en la base (script 01); la UI solo debe mostrar
el error que devuelve PostgreSQL, no reimplementar esas reglas.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/calificaciones", tags=["calificaciones"])


@router.get("")
def inicio_calificaciones(
    request: Request,
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "modulos/placeholder.html",
        {
            "usuario": usuario,
            "titulo": "Registro de calificaciones",
            "ticket": "SCRUM-8",
            "responsable": "Isai Portillo",
            "descripcion": (
                "Ingreso y edición de notas por evaluación y sección, con vista de "
                "promedio ponderado por estudiante."
            ),
        },
    )
