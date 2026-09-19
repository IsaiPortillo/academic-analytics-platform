"""Módulo de matrícula — SCRUM-7 (responsable: Edras Ariel Viera Lazo).

Esqueleto listo para implementar. Recursos ya disponibles:
  - models.Inscripcion, models.Seccion, models.Estudiante, models.PeriodoAcademico
  - db (Session) ya viene con SET LOCAL ROLE aplicado según el rol del usuario
Criterios de aceptación en el ticket SCRUM-7.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/matricula", tags=["matrícula"])


@router.get("")
def inicio_matricula(
    request: Request,
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "modulos/placeholder.html",
        {
            "usuario": usuario,
            "titulo": "Gestión de matrícula",
            "ticket": "SCRUM-7",
            "responsable": "Edras Ariel Viera Lazo",
            "descripcion": (
                "Matricular y retirar estudiantes de secciones, respetando el cupo "
                "máximo y la restricción uq_estudiante_seccion."
            ),
        },
    )
