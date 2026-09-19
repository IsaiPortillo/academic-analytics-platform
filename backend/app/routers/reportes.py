"""Módulo de reportes operacionales — SCRUM-10 (sin asignar).

Esqueleto listo para implementar. Depende de que SCRUM-8 (calificaciones) y
SCRUM-9 (asistencia) estén funcionando, porque lee los datos que ellos capturan.
Criterios de aceptación en el ticket SCRUM-10.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/reportes", tags=["reportes"])


@router.get("")
def inicio_reportes(
    request: Request,
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "modulos/placeholder.html",
        {
            "usuario": usuario,
            "titulo": "Reportes operacionales",
            "ticket": "SCRUM-10",
            "responsable": "Sin asignar",
            "descripcion": (
                "Notas finales por sección, asistencia acumulada y exportación a CSV."
            ),
        },
    )
