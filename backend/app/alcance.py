"""Alcance por carrera de la petición en curso, para las consultas al almacén.

El recorte del coordinador en el OLTP viaja en la propia sesión de base de datos
(database.get_db declara app.carrera_id junto al SET LOCAL ROLE). El almacén no
puede usar ese camino: lo lee una conexión aparte, como rol_dashboard, que no
pasa por get_db. Y las 22 funciones de dw.py no reciben al usuario.

Así que el alcance viaja en un ContextVar que fija un middleware al empezar la
petición (main.py) y que dw._leer() consulta al abrir su conexión. Se usa un
ContextVar y no una variable global porque cada petición necesita el suyo: una
global se pisaría entre peticiones concurrentes.

Si vale None, la consulta va como siempre (institucional). Si trae una carrera,
dw._leer() adopta rol_dw_carrera y declara la carrera, y las políticas del
script 24 recortan las filas.
"""

from contextvars import ContextVar
from typing import Optional

_carrera: ContextVar[Optional[int]] = ContextVar("alcance_carrera", default=None)


def fijar(carrera_id: Optional[int]) -> None:
    _carrera.set(carrera_id)


def carrera_actual() -> Optional[int]:
    return _carrera.get()
