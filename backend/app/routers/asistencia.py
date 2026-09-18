"""Módulo de asistencia — SCRUM-9 (sin asignar).

Esqueleto listo para implementar. Recursos ya disponibles:
  - models.Asistencia, models.Inscripcion, models.Seccion
  - db (Session) ya viene con SET LOCAL ROLE aplicado según el rol del usuario
Criterios de aceptación en el ticket SCRUM-9.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/asistencia", tags=["asistencia"])


@router.get("")
def inicio_asistencia(
    request: Request,
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "modulos/placeholder.html",
        {
            "usuario": usuario,
            "titulo": "Control de asistencia",
            "ticket": "SCRUM-9",
            "responsable": "Sin asignar",
            "descripcion": (
                "Registro de asistencia por sección y fecha de sesión, más resumen "
                "de faltas acumuladas por estudiante."
            ),
        },
    )
