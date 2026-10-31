"""Traducir un carnet al ID con el que las pantallas identifican al estudiante.

El sistema no guarda nombres ni el carnet: de cada estudiante conserva su ID
interno y el hash del carnet (`academico_oltp.estudiantes`). Las listas de clase
—la matriz de notas y el control de asistencia— muestran el ID, pero el docente
tiene en la mano el carnet. Esto hace la traducción: calcula el hash de lo que se
escribió y lo compara con el de los estudiantes de la sección.

Vive aparte porque lo usan dos pantallas (calificaciones y asistencia) y los
mensajes tienen que ser los mismos en las dos: lo que una pantalla responda sobre
un carnet no puede depender de por dónde se preguntó.

El carnet no se guarda, no se registra en la bitácora y no vuelve en el aviso.
Las pantallas lo reciben por POST, nunca en la URL: es un dato personal y en un
GET quedaría en el historial del navegador y en los registros de nginx.
"""

from dataclasses import dataclass
from typing import Iterable, Optional

from .catalogos import hash_carnet


@dataclass(frozen=True)
class Resultado:
    """Qué hacer con la búsqueda: resaltar una fila, o explicar por qué no."""

    estudiante_id: Optional[int] = None
    ok: Optional[str] = None
    error: Optional[str] = None


def localizar(carnet: str, completo: Iterable, visible: Iterable) -> Resultado:
    """Busca el carnet en la sección.

    `completo` son los estudiantes de la sección y `visible` los que la lista
    está dibujando ahora mismo (que son menos cuando hay inscripciones
    finalizadas y el acta sigue abierta).
    """
    carnet = (carnet or "").strip()
    if not carnet:
        return Resultado(error="Escribe el carnet que quieres buscar")

    # Solo esta sección. Si el carnet existe pero el estudiante está en otra, la
    # respuesta es la misma que si no existiera: la pantalla no sirve para
    # averiguar quién cursa en otra parte.
    buscado = hash_carnet(carnet)
    encontrado = next((e for e in completo if e.carnet_hash == buscado), None)
    if encontrado is None:
        return Resultado(error="Ese carnet no corresponde a ningún estudiante de esta sección")

    # Resaltar una fila que no se dibuja sería peor que no encontrarla.
    if encontrado.estudiante_id not in {e.estudiante_id for e in visible}:
        return Resultado(error=(
            f"El carnet corresponde al ID {encontrado.estudiante_id}, pero su inscripción "
            "ya está finalizada y la lista solo muestra las que están en curso"))

    return Resultado(
        estudiante_id=encontrado.estudiante_id,
        ok=f"El carnet corresponde al ID {encontrado.estudiante_id}: su fila está resaltada",
    )
