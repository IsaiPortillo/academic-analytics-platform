"""Definición de los catálogos que el coordinador administra desde la aplicación.

Cada catálogo describe sus campos una vez (tipo, límites, si es obligatorio, de
qué tabla salen las opciones) y de ahí salen la lista, el formulario y la
validación. Los límites repiten los CHECK de la base solo para dar un mensaje
claro antes de intentar: quien realmente los impone sigue siendo PostgreSQL.

Antes estos datos solo entraban con el generador de datos de prueba
(scripts/generator), lo que impedía usar el sistema con datos reales.
"""

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import (Carrera, Departamento, Docente, Estudiante, Materia, PeriodoAcademico,
                     Seccion)


@dataclass(frozen=True)
class Campo:
    nombre: str
    etiqueta: str
    tipo: str = "texto"          # texto | entero | fecha | bool | opcion | fk
    requerido: bool = True
    maximo_largo: Optional[int] = None
    minimo: Optional[int] = None
    maximo: Optional[int] = None
    opciones: tuple = ()         # tipo opcion: valores permitidos
    fk: Optional[Callable[[Session], list[tuple[int, str]]]] = None
    mayusculas: bool = False
    solo_alta: bool = False      # no se edita después de crear (p. ej. el carnet)
    virtual: bool = False        # no es una columna: lo traduce el catálogo (carnet -> hash)
    en_lista: bool = True
    ayuda: str = ""
    por_defecto: Any = None      # valor inicial en el formulario de alta


@dataclass(frozen=True)
class Catalogo:
    slug: str
    titulo: str
    singular: str
    modelo: Any
    campos: tuple[Campo, ...]
    busqueda: tuple[str, ...]
    orden: tuple
    etiqueta: Callable[[Any], str]
    descripcion: str = ""
    femenino: bool = False       # «sección creada», «período creado»
    filtro_periodo: bool = False
    columnas_extra: tuple[tuple[str, Callable[[Any], Any]], ...] = field(default_factory=tuple)


def _opciones(modelo, etiqueta, orden):
    def cargar(db: Session):
        return [(getattr(o, modelo.__mapper__.primary_key[0].name), etiqueta(o))
                for o in db.scalars(select(modelo).order_by(*orden)).all()]
    return cargar


def hash_carnet(carnet: str) -> str:
    """Carnet anonimizado. Con CARNET_CLAVE en el .env se usa HMAC: un carnet
    tiene pocas combinaciones y un SHA-256 sin clave se revierte probándolas
    todas. Sin clave se usa SHA-256 simple, igual que el generador de datos."""
    normalizado = carnet.strip().upper()
    if settings.carnet_clave:
        return hmac.new(settings.carnet_clave.encode(), normalizado.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(normalizado.encode()).hexdigest()


DEPARTAMENTOS = _opciones(Departamento, lambda d: f"{d.codigo_departamento} · {d.nombre}",
                          (Departamento.codigo_departamento,))
CARRERAS = _opciones(Carrera, lambda c: f"{c.codigo_carrera} · {c.nombre}", (Carrera.codigo_carrera,))
MATERIAS = _opciones(Materia, lambda m: f"{m.codigo_materia} · {m.nombre}", (Materia.codigo_materia,))
DOCENTES = _opciones(Docente, lambda d: f"{d.codigo_docente} · {d.escalafon.capitalize()}",
                     (Docente.codigo_docente,))
PERIODOS = _opciones(PeriodoAcademico, lambda p: p.codigo_periodo,
                     (PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc()))

ACTIVO = Campo("activo", "Activo", "bool", requerido=False, por_defecto=True)

CATALOGOS: dict[str, Catalogo] = {c.slug: c for c in (
    Catalogo(
        "periodos", "Períodos académicos", "período", PeriodoAcademico,
        (Campo("codigo_periodo", "Código", maximo_largo=10, mayusculas=True, ayuda="Ej.: 2026-I"),
         Campo("anio", "Año", "entero", minimo=2000, maximo=2100),
         Campo("ciclo_romano", "Ciclo", "opcion", opciones=("I", "II", "EXTRA")),
         Campo("fecha_inicio", "Inicio", "fecha"),
         Campo("fecha_fin", "Fin", "fecha"),
         Campo("activo", "Período vigente", "bool", requerido=False,
               ayuda="Solo uno a la vez: al marcarlo, los demás dejan de estar vigentes.")),
        ("codigo_periodo",), (PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc()),
        lambda p: p.codigo_periodo, "Ciclos lectivos con sus fechas."),
    Catalogo(
        "secciones", "Secciones", "sección", Seccion,
        (Campo("periodo_id", "Período", "fk", fk=PERIODOS),
         Campo("materia_id", "Materia", "fk", fk=MATERIAS),
         Campo("numero_seccion", "Número", "entero", minimo=1, maximo=99),
         Campo("docente_id", "Docente", "fk", fk=DOCENTES),
         Campo("turno", "Turno", "opcion", opciones=("MATUTINO", "VESPERTINO", "NOCTURNO")),
         Campo("aula", "Aula", maximo_largo=30, mayusculas=True),
         Campo("cupo_maximo", "Cupo", "entero", minimo=1, maximo=500)),
        ("aula",), (Seccion.periodo_id.desc(), Seccion.materia_id, Seccion.numero_seccion),
        lambda s: f"sección {s.numero_seccion}", "Oferta de cada período: materia, docente, turno y cupo.",
        femenino=True, filtro_periodo=True),
    Catalogo(
        "materias", "Materias", "materia", Materia,
        (Campo("codigo_materia", "Código", maximo_largo=15, mayusculas=True),
         Campo("nombre", "Nombre", maximo_largo=150),
         Campo("unidades_valorativas", "UV", "entero", minimo=1, maximo=10),
         Campo("ciclo_plan", "Ciclo del plan", "entero", minimo=1, maximo=12),
         Campo("carrera_id", "Carrera", "fk", fk=CARRERAS),
         ACTIVO),
        ("codigo_materia", "nombre"), (Materia.codigo_materia,),
        lambda m: m.codigo_materia, "Asignaturas del plan. Sus prerrequisitos se editan en «Malla curricular».",
        femenino=True),
    Catalogo(
        "docentes", "Docentes", "docente", Docente,
        (Campo("codigo_docente", "Código", maximo_largo=20, mayusculas=True),
         Campo("escalafon", "Escalafón", "opcion", opciones=("HORA CLASE", "AUXILIAR", "ADJUNTO", "TITULAR")),
         Campo("departamento_id", "Departamento", "fk", fk=DEPARTAMENTOS),
         ACTIVO),
        ("codigo_docente",), (Docente.codigo_docente,),
        lambda d: d.codigo_docente, "Planta docente. La cuenta de acceso se crea en «Usuarios»."),
    Catalogo(
        "estudiantes", "Estudiantes", "estudiante", Estudiante,
        (Campo("carnet", "Carnet", virtual=True, solo_alta=True, mayusculas=True, maximo_largo=20,
               en_lista=False, ayuda="Se guarda anonimizado (hash): el sistema nunca conserva el carnet."),
         Campo("anio_ingreso", "Año de ingreso", "entero", minimo=2000, maximo=2100),
         Campo("carrera_id", "Carrera", "fk", fk=CARRERAS),
         Campo("trabaja", "Trabaja", "bool", requerido=False),
         Campo("condicion_academica", "Condición", "opcion",
               opciones=("REGULAR", "CONDICIONAL", "EGRESADO", "RETIRADO")),
         ACTIVO),
        (), (Estudiante.estudiante_id.desc(),),
        lambda e: f"estudiante {e.estudiante_id}",
        "Sin datos personales: se identifica por su ID y su carnet anonimizado.",
        columnas_extra=(("ID", lambda e: e.estudiante_id), ("Carnet (hash)", lambda e: e.carnet_hash[:12] + "…"))),
    Catalogo(
        "carreras", "Carreras", "carrera", Carrera,
        (Campo("codigo_carrera", "Código", maximo_largo=10, mayusculas=True),
         Campo("nombre", "Nombre", maximo_largo=120),
         Campo("departamento_id", "Departamento", "fk", fk=DEPARTAMENTOS),
         Campo("plan_anio", "Plan (año)", "entero", minimo=1990, maximo=2100),
         Campo("total_uv_carrera", "UV totales", "entero", minimo=1, maximo=1000),
         ACTIVO),
        ("codigo_carrera", "nombre"), (Carrera.codigo_carrera,),
        lambda c: c.codigo_carrera, "Planes de estudio.", femenino=True),
    Catalogo(
        "departamentos", "Departamentos", "departamento", Departamento,
        (Campo("codigo_departamento", "Código", maximo_largo=10, mayusculas=True),
         Campo("nombre", "Nombre", maximo_largo=100)),
        ("codigo_departamento", "nombre"), (Departamento.codigo_departamento,),
        lambda d: d.codigo_departamento, "Unidades académicas."),
)}


def leer_formulario(catalogo: Catalogo, formulario, creando: bool) -> tuple[dict, list[str]]:
    """Convierte el formulario en valores tipados. Devuelve (valores, errores)."""
    valores, errores = {}, []
    for campo in catalogo.campos:
        if campo.solo_alta and not creando:
            continue
        crudo = formulario.get(campo.nombre)
        if campo.tipo == "bool":
            valores[campo.nombre] = crudo in ("on", "true", "1")
            continue
        texto = (crudo or "").strip()
        if not texto:
            if campo.requerido:
                errores.append(f"«{campo.etiqueta}» es obligatorio.")
            else:
                valores[campo.nombre] = None
            continue
        if campo.tipo == "texto":
            if campo.mayusculas:
                texto = texto.upper()
            if campo.maximo_largo and len(texto) > campo.maximo_largo:
                errores.append(f"«{campo.etiqueta}» admite hasta {campo.maximo_largo} caracteres.")
                continue
            valores[campo.nombre] = texto
        elif campo.tipo in ("entero", "fk"):
            try:
                numero = int(texto)
            except ValueError:
                errores.append(f"«{campo.etiqueta}» debe ser un número entero.")
                continue
            if campo.minimo is not None and numero < campo.minimo or campo.maximo is not None and numero > campo.maximo:
                errores.append(f"«{campo.etiqueta}» debe estar entre {campo.minimo} y {campo.maximo}.")
                continue
            valores[campo.nombre] = numero
        elif campo.tipo == "fecha":
            try:
                valores[campo.nombre] = date.fromisoformat(texto)
            except ValueError:
                errores.append(f"«{campo.etiqueta}» no es una fecha válida.")
        elif campo.tipo == "opcion":
            if texto not in campo.opciones:
                errores.append(f"«{campo.etiqueta}»: valor no permitido.")
                continue
            valores[campo.nombre] = texto
    if catalogo.slug == "periodos" and not errores and valores["fecha_fin"] <= valores["fecha_inicio"]:
        errores.append("La fecha de fin debe ser posterior a la de inicio.")
    return valores, errores


def aplicar(catalogo: Catalogo, registro, valores: dict) -> None:
    for nombre, valor in valores.items():
        if nombre == "carnet":
            registro.carnet_hash = hash_carnet(valor)
        else:
            setattr(registro, nombre, valor)


def valor_para_formulario(campo: Campo, registro) -> Any:
    if registro is None or campo.virtual:
        if campo.tipo == "bool":
            return bool(campo.por_defecto)
        return "" if campo.por_defecto is None else campo.por_defecto
    valor = getattr(registro, campo.nombre)
    if campo.tipo == "fecha" and valor:
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return "" if valor is None else valor


def valor_para_lista(campo: Campo, registro, etiquetas_fk: dict) -> str:
    valor = getattr(registro, campo.nombre)
    if campo.tipo == "bool":
        return "Sí" if valor else "No"
    if campo.tipo == "fk":
        return etiquetas_fk.get(campo.nombre, {}).get(valor, str(valor))
    if campo.tipo == "fecha" and valor:
        return f"{valor:%d/%m/%Y}"
    return "—" if valor is None else str(valor)
