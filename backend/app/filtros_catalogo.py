"""Filtros, orden y paginación de las listas de Catálogos (Administración).

Cada catálogo declara qué se puede filtrar (departamento, carrera, ciclo del plan, turno,
condición…). De ahí salen los selectores de la pantalla, la lectura segura de la URL y la
consulta: un valor que no corresponde a ninguna opción se ignora (no rompe nada ni se
interpola en el SQL: siempre va como parámetro). Los filtros que dependen de otra tabla
(por ejemplo el departamento de una materia, que viene de su carrera) se escriben como
subconsulta y no como unión, así se pueden combinar en cualquier orden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalogos import CARRERAS, DEPARTAMENTOS, DOCENTES, PERIODOS, Catalogo
from .models import Carrera, Docente, Estudiante, Materia, PeriodoAcademico, Seccion

POR_PAGINA_OPCIONES = (25, 50, 100, 200)
POR_PAGINA = 50
SI_NO = (("1", "Sí"), ("0", "No"))


@dataclass(frozen=True)
class Filtro:
    nombre: str                                   # parámetro de la URL
    etiqueta: str
    tipo: str                                     # fk | valores | opcion | bool
    columna: Any = None                           # columna del modelo (si el filtro es directo)
    sub: Optional[Callable[[int], Any]] = None    # condición ya armada (si depende de otra tabla)
    valores: tuple = ()                           # tipo opcion: los permitidos
    cargar: Optional[Callable[[Session], list]] = None   # tipo fk: [(id, texto)]


def _carreras_del_departamento(departamento_id: int):
    return select(Carrera.carrera_id).where(Carrera.departamento_id == departamento_id)


def _departamento(columna_carrera):
    return lambda valor: columna_carrera.in_(_carreras_del_departamento(valor))


def _materias_de_carrera(carrera_id: int):
    return select(Materia.materia_id).where(Materia.carrera_id == carrera_id)


def _materias_del_departamento(departamento_id: int):
    return select(Materia.materia_id).where(Materia.carrera_id.in_(_carreras_del_departamento(departamento_id)))


def _depto(columna=None, sub=None):
    return Filtro("departamento_id", "Departamento", "fk", columna=columna, sub=sub, cargar=DEPARTAMENTOS)


def _activo(columna, etiqueta="Activo"):
    return Filtro("activo", etiqueta, "bool", columna)


FILTROS: dict[str, tuple[Filtro, ...]] = {
    "periodos": (
        Filtro("anio", "Año", "valores", PeriodoAcademico.anio),
        Filtro("ciclo_romano", "Ciclo", "opcion", PeriodoAcademico.ciclo_romano, valores=("I", "II", "EXTRA")),
        _activo(PeriodoAcademico.activo, "Vigente"),
    ),
    "secciones": (
        Filtro("periodo_id", "Período", "fk", Seccion.periodo_id, cargar=PERIODOS),
        _depto(sub=lambda v: Seccion.materia_id.in_(_materias_del_departamento(v))),
        Filtro("carrera_id", "Carrera", "fk", sub=lambda v: Seccion.materia_id.in_(_materias_de_carrera(v)),
               cargar=CARRERAS),
        Filtro("docente_id", "Docente", "fk", Seccion.docente_id, cargar=DOCENTES),
        Filtro("turno", "Turno", "opcion", Seccion.turno, valores=("MATUTINO", "VESPERTINO", "NOCTURNO")),
    ),
    "materias": (
        _depto(sub=_departamento(Materia.carrera_id)),
        Filtro("carrera_id", "Carrera", "fk", Materia.carrera_id, cargar=CARRERAS),
        Filtro("ciclo_plan", "Ciclo del plan", "valores", Materia.ciclo_plan),
        _activo(Materia.activo),
    ),
    "docentes": (
        _depto(Docente.departamento_id),
        Filtro("escalafon", "Escalafón", "opcion", Docente.escalafon,
               valores=("HORA CLASE", "AUXILIAR", "ADJUNTO", "TITULAR")),
        _activo(Docente.activo),
    ),
    "estudiantes": (
        _depto(sub=_departamento(Estudiante.carrera_id)),
        Filtro("carrera_id", "Carrera", "fk", Estudiante.carrera_id, cargar=CARRERAS),
        Filtro("anio_ingreso", "Año de ingreso", "valores", Estudiante.anio_ingreso),
        Filtro("condicion_academica", "Condición", "opcion", Estudiante.condicion_academica,
               valores=("REGULAR", "CONDICIONAL", "EGRESADO", "RETIRADO")),
        Filtro("trabaja", "Trabaja", "bool", Estudiante.trabaja),
        _activo(Estudiante.activo),
    ),
    "carreras": (
        _depto(Carrera.departamento_id),
        _activo(Carrera.activo),
    ),
    "departamentos": (),
}


def filtros_de(catalogo: Catalogo) -> tuple[Filtro, ...]:
    return FILTROS.get(catalogo.slug, ())


def opciones(db: Session, filtro: Filtro) -> list[tuple[str, str]]:
    """[(valor para la URL, texto)] de un filtro. Para «valores» se leen los que de verdad existen."""
    if filtro.tipo == "fk":
        return [(str(i), texto) for i, texto in filtro.cargar(db)]
    if filtro.tipo == "valores":
        columna = filtro.columna
        return [(str(v), str(v)) for v in db.scalars(select(columna).distinct().order_by(columna)).all()
                if v is not None]
    if filtro.tipo == "bool":
        return list(SI_NO)
    return [(v, v.capitalize()) for v in filtro.valores]


def condicion(filtro: Filtro, crudo: str):
    """La condición SQL de un valor de la URL, o None si el valor no vale."""
    crudo = (crudo or "").strip()
    if not crudo:
        return None
    if filtro.tipo in ("fk", "valores"):
        if not crudo.lstrip("-").isdigit():
            return None
        numero = int(crudo)
        return filtro.sub(numero) if filtro.sub else filtro.columna == numero
    if filtro.tipo == "bool":
        return filtro.columna.is_(True) if crudo == "1" else filtro.columna.is_(False) if crudo == "0" else None
    return filtro.columna == crudo if crudo in filtro.valores else None


@dataclass
class Seleccion:
    """Lo que la persona pidió en la URL, ya depurado."""
    buscar: str = ""
    filtros: dict[str, str] = None            # nombre -> valor válido
    orden: Optional[str] = None
    descendente: bool = False
    por_pagina: int = POR_PAGINA
    pagina: int = 1

    def __post_init__(self):
        self.filtros = self.filtros or {}


def leer(catalogo: Catalogo, parametros: Mapping[str, str], por_defecto: Optional[Mapping[str, str]] = None) -> Seleccion:
    """Depura los parámetros de la URL. `por_defecto` aplica a un filtro que no vino en la URL
    (que venga vacío es una elección: «todos»)."""
    por_defecto = por_defecto or {}
    seleccion = Seleccion(buscar=(parametros.get("buscar") or "").strip()[:80])
    for filtro in filtros_de(catalogo):
        crudo = parametros.get(filtro.nombre, por_defecto.get(filtro.nombre))
        if crudo is not None and condicion(filtro, crudo) is not None:
            seleccion.filtros[filtro.nombre] = crudo.strip()
    ordenables = {c.nombre for c in catalogo.campos if not c.virtual} | {"id"}
    orden = (parametros.get("orden") or "").strip()
    if orden in ordenables:
        seleccion.orden = orden
        seleccion.descendente = parametros.get("dir") == "desc"
    try:
        por_pagina = int(parametros.get("por_pagina", POR_PAGINA))
    except ValueError:
        por_pagina = POR_PAGINA
    seleccion.por_pagina = por_pagina if por_pagina in POR_PAGINA_OPCIONES else POR_PAGINA
    pagina = (parametros.get("pagina") or "1").strip()
    seleccion.pagina = int(pagina) if pagina.isdigit() and int(pagina) > 0 else 1
    return seleccion


def aplicar(consulta, catalogo: Catalogo, seleccion: Seleccion):
    """Agrega los filtros a la consulta. (La búsqueda por texto la arma el router: depende del catálogo.)"""
    for filtro in filtros_de(catalogo):
        crudo = seleccion.filtros.get(filtro.nombre)
        if crudo is not None:
            consulta = consulta.where(condicion(filtro, crudo))
    return consulta


def clausulas_de_orden(catalogo: Catalogo, seleccion: Seleccion):
    if not seleccion.orden:
        return list(catalogo.orden)
    modelo = catalogo.modelo
    columna = modelo.__mapper__.primary_key[0] if seleccion.orden == "id" else getattr(modelo, seleccion.orden)
    principal = columna.desc() if seleccion.descendente else columna.asc()
    return [principal, modelo.__mapper__.primary_key[0].asc()]


def consulta_url(seleccion: Seleccion, *, quitar: tuple = (), **cambios) -> str:
    """Los parámetros de la selección como query string; `quitar` los omite y `cambios` los reemplaza."""
    datos: dict[str, Any] = {}
    if seleccion.buscar:
        datos["buscar"] = seleccion.buscar
    datos.update(seleccion.filtros)
    if seleccion.orden:
        datos["orden"] = seleccion.orden
        if seleccion.descendente:
            datos["dir"] = "desc"
    if seleccion.por_pagina != POR_PAGINA:
        datos["por_pagina"] = seleccion.por_pagina
    for nombre in quitar:
        datos.pop(nombre, None)
    for nombre, valor in cambios.items():
        if valor in (None, ""):
            datos.pop(nombre, None)
        else:
            datos[nombre] = valor
    return urlencode(datos)


def chips(db: Session, catalogo: Catalogo, seleccion: Seleccion, base: str, con_defecto: tuple = ()) -> list[dict]:
    """Un chip por cada filtro o búsqueda activa, con el enlace que lo quita.

    `con_defecto`: filtros que la pantalla rellena sola cuando no vienen en la URL (el período de
    las secciones). Quitarlos no basta con omitirlos —volverían a su valor por defecto—: el
    enlace los manda vacíos, que significa «todos»."""
    resultado = []
    if seleccion.buscar:
        resultado.append({"etiqueta": "Búsqueda", "texto": seleccion.buscar,
                          "quitar": f"{base}?{consulta_url(seleccion, quitar=('buscar',))}"})
    for filtro in filtros_de(catalogo):
        valor = seleccion.filtros.get(filtro.nombre)
        if valor is None:
            continue
        texto = dict(opciones(db, filtro)).get(valor, valor)
        consulta = consulta_url(seleccion, quitar=(filtro.nombre,))
        if filtro.nombre in con_defecto:
            consulta = (consulta + "&" if consulta else "") + f"{filtro.nombre}="
        resultado.append({"etiqueta": filtro.etiqueta, "texto": texto, "quitar": f"{base}?{consulta}"})
    return resultado
