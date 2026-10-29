"""
UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL (San Miguel)
Catálogo de datos de prueba que se parecen a la oferta pública de la FMO.

Lo público: la FMO tiene ocho departamentos académicos (Ingeniería y Arquitectura,
Medicina, Ciencias Económicas, Ciencias y Humanidades, Jurisprudencia y Ciencias
Sociales, Ciencias Agronómicas, Ciencias Naturales y Matemática, Química y
Farmacia), cerca de cuarenta carreras de pregrado, dos ciclos lectivos al año
(Ciclo I y Ciclo II), escala de notas de 0 a 10 con 6.0 como mínimo de aprobación,
unidades valorativas (UV) por asignatura y planes de estudio por ciclo.

Lo inventado (todo es sintético, no hay datos de personas): los planes de estudio
de cada carrera son genéricos y se parecen a los de una universidad pública
salvadoreña, no son los planes oficiales; los códigos de materia siguen el estilo de
la UES (tres letras, un correlativo y el año del plan: MAT115) pero no son los
oficiales; las fechas de cada ciclo son aproximadas.

Este módulo es solo datos y funciones puras: lo comparten el generador de la base
relacional (02_generador_datos_sinteticos.py) y la carga del grafo de la malla
(database/nosql/03_cargar_grafo_neo4j.py). No importa nada de la base.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Departamentos
# ---------------------------------------------------------------------------

DEPARTAMENTOS = [
    ("DIA", "Departamento de Ingeniería y Arquitectura"),
    ("DCE", "Departamento de Ciencias Económicas"),
    ("DCN", "Departamento de Ciencias Naturales y Matemática"),
    ("DME", "Departamento de Medicina"),
    ("DCH", "Departamento de Ciencias y Humanidades"),
    ("DJS", "Departamento de Jurisprudencia y Ciencias Sociales"),
    ("DAG", "Departamento de Ciencias Agronómicas"),
    ("DQF", "Departamento de Química y Farmacia"),
]

# Docentes por departamento. Los 20 de DIA (DOC-101 a DOC-120) ya existían: el
# generador conserva esos registros (hay cuentas de usuario ligadas a ellos) y
# solo agrega los que faltan hasta este total.
DOCENTES_POR_DEPARTAMENTO = {"DIA": 30, "DCE": 14, "DCN": 10, "DME": 22, "DCH": 10, "DJS": 8, "DAG": 6, "DQF": 5}
PRIMER_NUMERO_DOCENTE = 101
ESCALAFONES = ("TITULAR", "ADJUNTO", "AUXILIAR", "HORA CLASE")
PESO_ESCALAFON = (0.20, 0.15, 0.25, 0.40)

# ---------------------------------------------------------------------------
# Calendario: dos ciclos al año y cuatro módulos dentro de cada ciclo
# ---------------------------------------------------------------------------

MODULOS_POR_CICLO = 4


def fechas_del_ciclo(anio: int, ciclo: str) -> tuple[date, date]:
    """Inicio y fin aproximados de un ciclo. Ciclo I: de mediados de febrero a fines de
    junio. Ciclo II: de principios de agosto a mediados de diciembre."""
    if ciclo == "I":
        return date(anio, 2, 9), date(anio, 6, 26)
    return date(anio, 8, 3), date(anio, 12, 18)


def modulos_del_ciclo(inicio: date, fin: date) -> list[tuple[date, date]]:
    """Los cuatro módulos del ciclo: cuatro tramos consecutivos de igual duración."""
    dias = (fin - inicio).days + 1
    tramo = dias // MODULOS_POR_CICLO
    modulos = []
    for k in range(MODULOS_POR_CICLO):
        desde = inicio + timedelta(days=k * tramo)
        hasta = fin if k == MODULOS_POR_CICLO - 1 else inicio + timedelta(days=(k + 1) * tramo - 1)
        modulos.append((desde, hasta))
    return modulos


def periodos(anio_inicial: int, anio_final: int) -> list[tuple[str, int, str, date, date]]:
    """(código, año, ciclo, inicio, fin) de cada ciclo, en orden cronológico."""
    resultado = []
    for anio in range(anio_inicial, anio_final + 1):
        for ciclo in ("I", "II"):
            inicio, fin = fechas_del_ciclo(anio, ciclo)
            resultado.append((f"{anio}-{ciclo}", anio, ciclo, inicio, fin))
    return resultado


# ---------------------------------------------------------------------------
# Cómo evalúa cada docente
# ---------------------------------------------------------------------------
# Cada docente arma su propio plan de evaluación (la mayoría con un parcial corto
# por módulo, otros con más evaluaciones y su propio porcentaje). Cada plan suma
# exactamente 100 %. Un plan es una lista de (nombre, porcentaje, módulo): el módulo
# (1 a 4) ubica la fecha dentro de ese módulo; None la reparte en todo el ciclo.

def _por_modulo(prefijo: str, pesos: tuple[int, ...]) -> list[tuple[str, int, int | None]]:
    return [(f"{prefijo} · Módulo {k}", p, k) for k, p in enumerate(pesos, start=1)]


ESTILOS_DE_EVALUACION = {
    "parcial_corto": (0.45, _por_modulo("Parcial corto", (25, 25, 25, 25))),
    "parcial_corto_creciente": (0.10, _por_modulo("Parcial corto", (20, 20, 30, 30))),
    "parciales_laboratorio_y_proyecto": (0.15, _por_modulo("Parcial corto", (15, 15, 15, 15))
                                         + [("Laboratorio", 15, None), ("Proyecto final", 25, 4)]),
    "evaluacion_y_tareas": (0.12, _por_modulo("Evaluación", (20, 20, 20, 20)) + [("Tareas y participación", 20, None)]),
    "seis_evaluaciones": (0.08, [("Tarea 1", 10, 1), ("Parcial 1", 20, 2), ("Tarea 2", 10, 2),
                                 ("Parcial 2", 20, 3), ("Informe de laboratorio", 15, 3), ("Examen final", 25, 4)]),
    "tres_parciales": (0.10, [("Primer parcial", 30, 2), ("Segundo parcial", 30, 3), ("Examen final", 40, 4)]),
}


def evaluaciones_de(estilo: str) -> list[tuple[str, int, int | None]]:
    return ESTILOS_DE_EVALUACION[estilo][1]


def fecha_de_evaluacion(indice: int, total: int, modulo: int | None, modulos: list[tuple[date, date]]) -> date:
    """Fecha dentro del módulo indicado (a mitad de ese tramo, escalonada si hay varias en el
    mismo) o repartida por todo el ciclo cuando no pertenece a un módulo."""
    if modulo is None:
        inicio, fin = modulos[0][0], modulos[-1][1]
        return inicio + timedelta(days=int((fin - inicio).days * (indice + 1) / (total + 1)))
    desde, hasta = modulos[modulo - 1]
    return desde + timedelta(days=int((hasta - desde).days * 0.75))


# ---------------------------------------------------------------------------
# Planes de estudio
# ---------------------------------------------------------------------------

BASICAS = "Ciencias Básicas"
IDIOMAS = "Idiomas"
GENERAL = "Formación General"

_PALABRAS_BASICAS = ("matemática", "física", "química general", "estadística", "biología general", "cálculo",
                     "álgebra", "bioestadística")


@dataclass(frozen=True)
class Materia:
    codigo: str
    nombre: str
    uv: int
    ciclo: int
    area: str
    prerrequisitos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Carrera:
    codigo: str
    nombre: str
    departamento: str
    plan_anio: int
    ingreso_anual: int              # estudiantes de nuevo ingreso por año
    area_base: str                  # área de las asignaturas propias de la carrera
    peso_turnos: tuple[float, float, float]   # matutino, vespertino, nocturno
    materias: tuple[Materia, ...] = field(default_factory=tuple)

    @property
    def total_uv(self) -> int:
        return sum(m.uv for m in self.materias)

    @property
    def ciclos(self) -> int:
        return max(m.ciclo for m in self.materias)


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def area_de(nombre: str, area_base: str) -> str:
    claro = nombre.lower()
    if claro.startswith("inglés"):
        return IDIOMAS
    if any(p in claro for p in ("metodología", "ética", "seminario", "trabajo de graduación", "electiva",
                                "realidad nacional", "anteproyecto", "práctica profesional")):
        return GENERAL
    if any(p in claro for p in _PALABRAS_BASICAS):
        return BASICAS
    return area_base


def _uv_de(nombre: str) -> int:
    claro = nombre.lower()
    if claro.startswith("trabajo de graduación"):
        return 8
    if claro.startswith("internado"):
        return 10
    if claro.startswith(("práctica", "clínica")):
        return 6
    if claro.startswith("electiva"):
        return 3
    return 4


_ROMANOS = {"I": 1, "II": 2, "III": 3, "IV": 4}


def _prerrequisito_de_serie(nombre: str, por_nombre: dict[str, str]) -> str | None:
    """«Anatomía II» exige «Anatomía I»."""
    partes = nombre.rsplit(" ", 1)
    if len(partes) == 2 and partes[1] in _ROMANOS and _ROMANOS[partes[1]] > 1:
        anterior = {v: k for k, v in _ROMANOS.items()}[_ROMANOS[partes[1]] - 1]
        return por_nombre.get(f"{partes[0]} {anterior}")
    return None


def _abreviatura(nombre: str) -> str:
    palabras = [p for p in re.findall(r"[A-Za-z]+", _sin_acentos(nombre))
                if p.lower() not in {"de", "del", "la", "las", "los", "el", "y", "en", "a", "al", "para", "introduccion",
                                     "fundamentos", "teoria", "general"} and len(p) > 2]
    base = (palabras[0] if palabras else "MAT").upper()
    return base[:3].ljust(3, "X")


def construir_plan(plan_anio: int, area_base: str, ciclos: list[list[str]],
                   codigos_usados: set[str]) -> tuple[Materia, ...]:
    """Convierte la lista de asignaturas por ciclo en materias con código y prerrequisitos.

    Código: tres letras de la asignatura, un correlativo y los dos últimos dígitos del año
    del plan (MAT115). Prerrequisitos: la serie I -> II -> III y, para el resto, la primera
    asignatura de la misma área del ciclo anterior. Siempre apuntan a un ciclo anterior, así
    que la malla nunca tiene ciclos."""
    sufijo = f"{plan_anio % 100:02d}"
    contadores: dict[str, int] = {}
    codigo_de: dict[str, str] = {}
    ciclo_de: dict[str, int] = {}
    area_por_nombre: dict[str, str] = {}
    for numero, nombres in enumerate(ciclos, start=1):
        for nombre in nombres:
            abreviatura = _abreviatura(nombre)
            while True:
                contadores[abreviatura] = contadores.get(abreviatura, 0) + 1
                codigo = f"{abreviatura}{contadores[abreviatura]}{sufijo}"
                if codigo not in codigos_usados:
                    break
            codigos_usados.add(codigo)
            codigo_de[nombre] = codigo
            ciclo_de[nombre] = numero
            area_por_nombre[nombre] = area_de(nombre, area_base)

    materias = []
    for numero, nombres in enumerate(ciclos, start=1):
        anteriores = ciclos[numero - 2] if numero > 1 else []
        for nombre in nombres:
            requisitos: list[str] = []
            serie = _prerrequisito_de_serie(nombre, codigo_de)
            if serie:
                requisitos.append(serie)
            elif nombre.lower().startswith("electiva ") and nombre.rsplit(" ", 1)[1] in _ROMANOS \
                    and _ROMANOS[nombre.rsplit(" ", 1)[1]] > 1:
                pass  # las electivas se cursan en cualquier orden
            elif nombre.lower().startswith("trabajo de graduación"):
                semin = next((n for ciclo in ciclos[:numero - 1] for n in ciclo if n.lower().startswith("seminario")), None)
                if semin:
                    requisitos.append(codigo_de[semin])
            elif numero > 1 and not nombre.lower().startswith("electiva"):
                misma_area = next((n for n in anteriores if area_por_nombre[n] == area_por_nombre[nombre]), None)
                if misma_area:
                    requisitos.append(codigo_de[misma_area])
            materias.append(Materia(codigo_de[nombre], nombre, _uv_de(nombre), numero, area_por_nombre[nombre],
                                    tuple(dict.fromkeys(requisitos))))
    return tuple(materias)


# --- Ingeniería de Sistemas Informáticos: plan completo y con códigos propios -------------------------
# (los 16 primeros códigos ya existían en la base y en el grafo; se conservan tal cual)

_DEV, _DAT, _SW, _HW, _IA, _GES = ("Desarrollo de Software", "Gestión de Datos", "Ingeniería de Software",
                                   "Hardware y Redes", "Ciencia de Datos e IA", "Gestión y Emprendimiento")

_ISI = [
    # (código, nombre, UV, ciclo, área, prerrequisitos)
    ("MAT115", "Matemática I", 4, 1, BASICAS, ()),
    ("PRG115", "Programación I", 4, 1, _DEV, ()),
    ("ACA115", "Álgebra Vectorial y Matrices", 4, 1, BASICAS, ()),
    ("ING115", "Inglés Técnico I", 4, 1, IDIOMAS, ()),
    ("MET115", "Metodología de la Investigación", 4, 1, GENERAL, ()),
    ("MAT215", "Matemática II", 4, 2, BASICAS, ("MAT115",)),
    ("PRG215", "Programación II", 4, 2, _DEV, ("PRG115",)),
    ("FIS115", "Física I", 4, 2, BASICAS, ("MAT115",)),
    ("ING215", "Inglés Técnico II", 4, 2, IDIOMAS, ("ING115",)),
    ("EDA115", "Estructuras de Datos y Algoritmos", 4, 2, _DEV, ("PRG115",)),
    ("BAD115", "Bases de Datos I", 4, 3, _DAT, ("PRG115",)),
    ("PRG315", "Programación III", 4, 3, _DEV, ("PRG215",)),
    ("MAT315", "Matemática III", 4, 3, BASICAS, ("MAT215",)),
    ("EST115", "Estadística I", 4, 3, BASICAS, ("MAT215",)),
    ("FIS215", "Física II", 4, 3, BASICAS, ("FIS115", "MAT215")),
    ("BAD215", "Bases de Datos II", 4, 4, _DAT, ("BAD115",)),
    ("ADS115", "Análisis y Diseño de Sistemas I", 4, 4, _SW, ("PRG215",)),
    ("EST215", "Estadística II", 4, 4, BASICAS, ("EST115",)),
    ("SOP115", "Sistemas Operativos", 4, 4, _HW, ("EDA115",)),
    ("CON115", "Contabilidad Financiera", 4, 4, _GES, ()),
    ("SIF115", "Sistemas de Información", 4, 5, _SW, ("ADS115", "BAD115")),
    ("ADS215", "Análisis y Diseño de Sistemas II", 4, 5, _SW, ("ADS115",)),
    ("RED115", "Redes de Datos I", 4, 5, _HW, ("SOP115",)),
    ("ECO115", "Introducción a la Economía", 4, 5, _GES, ()),
    ("ELD115", "Electrónica Digital", 4, 5, _HW, ("FIS215",)),
    ("DWB115", "Diseño Web y Aplicaciones", 4, 6, _DEV, ("PRG315",)),
    ("ARC115", "Arquitectura de Computadoras", 4, 6, _HW, ("ACA115",)),
    ("RED215", "Redes de Datos II", 4, 6, _HW, ("RED115",)),
    ("IDS115", "Ingeniería de Software", 4, 6, _SW, ("ADS215",)),
    ("ADM115", "Administración de Proyectos", 4, 6, _GES, ("CON115",)),
    ("IAI115", "Inteligencia Artificial", 4, 7, _IA, ("PRG315", "MAT315")),
    ("SEG115", "Seguridad Informática", 4, 7, _HW, ("RED215",)),
    ("APM115", "Aplicaciones Móviles", 4, 7, _DEV, ("DWB115",)),
    ("CAL115", "Calidad de Software", 4, 7, _SW, ("IDS115",)),
    ("EL1115", "Electiva I", 3, 7, GENERAL, ()),
    ("BIN115", "Inteligencia de Negocios", 4, 8, _IA, ("BAD215", "SIF115")),
    ("DSD115", "Sistemas Distribuidos", 4, 8, _DEV, ("RED215",)),
    ("AUD115", "Auditoría Informática", 4, 8, _GES, ("SEG115",)),
    ("EL2115", "Electiva II", 3, 8, GENERAL, ()),
    ("ETI115", "Ética Profesional", 4, 8, GENERAL, ()),
    ("ANT115", "Anteproyecto de Trabajo de Graduación", 4, 9, GENERAL, ("MET115", "IDS115")),
    ("EMP115", "Emprendimiento e Innovación", 4, 9, _GES, ("ADM115",)),
    ("EL3115", "Electiva III", 3, 9, GENERAL, ()),
    ("GTI115", "Gestión de Tecnologías de la Información", 4, 9, _GES, ("AUD115",)),
    ("TGR115", "Trabajo de Graduación", 8, 10, GENERAL, ("ANT115",)),
]

# --- Resto de carreras: asignaturas por ciclo (los códigos y prerrequisitos se derivan) -----------------

_PLANES: list[tuple[str, str, str, int, int, str, tuple[float, float, float], list[list[str]]]] = [
    ("I10506", "Ingeniería Civil", "DIA", 2012, 28, "Ingeniería Civil", (0.50, 0.35, 0.15), [
        ["Matemática I", "Química General", "Dibujo Técnico", "Introducción a la Ingeniería Civil", "Inglés Técnico I"],
        ["Matemática II", "Física I", "Topografía I", "Geología", "Inglés Técnico II"],
        ["Matemática III", "Física II", "Topografía II", "Estática", "Materiales de Construcción"],
        ["Ecuaciones Diferenciales", "Resistencia de Materiales I", "Dinámica", "Hidráulica I", "Estadística I"],
        ["Resistencia de Materiales II", "Mecánica de Suelos I", "Hidráulica II", "Análisis Estructural I",
         "Metodología de la Investigación"],
        ["Análisis Estructural II", "Mecánica de Suelos II", "Concreto Reforzado I", "Hidrología",
         "Instalaciones Hidrosanitarias"],
        ["Concreto Reforzado II", "Ingeniería de Carreteras", "Cimentaciones", "Estructuras de Acero", "Ingeniería Sanitaria"],
        ["Pavimentos", "Costos y Presupuestos", "Construcción de Edificaciones", "Ingeniería Sísmica", "Electiva I"],
        ["Administración de Proyectos de Construcción", "Legislación de la Construcción", "Obras Hidráulicas",
         "Electiva II", "Seminario de Trabajo de Graduación"],
        ["Trabajo de Graduación", "Ética Profesional", "Gerencia de Obras"],
    ]),
    ("E20118", "Licenciatura en Administración de Empresas", "DCE", 2018, 45, "Administración", (0.25, 0.30, 0.45), [
        ["Introducción a la Administración", "Matemática Básica", "Contabilidad I", "Introducción a la Economía", "Inglés I"],
        ["Teoría Administrativa", "Matemática Financiera", "Contabilidad II", "Microeconomía", "Inglés II"],
        ["Estadística I", "Derecho Mercantil", "Contabilidad de Costos", "Macroeconomía", "Metodología de la Investigación"],
        ["Estadística II", "Comportamiento Organizacional", "Mercadeo I", "Informática Aplicada a la Administración",
         "Derecho Laboral"],
        ["Administración Financiera I", "Mercadeo II", "Administración de Recursos Humanos", "Investigación de Operaciones",
         "Legislación Tributaria"],
        ["Administración Financiera II", "Administración de la Producción", "Presupuesto Empresarial",
         "Ética Empresarial", "Comercio Internacional"],
        ["Administración Estratégica", "Gerencia de Operaciones", "Formulación y Evaluación de Proyectos", "Electiva I"],
        ["Planeación Estratégica", "Auditoría Administrativa", "Emprendimiento e Innovación", "Electiva II",
         "Seminario de Investigación"],
        ["Consultoría Empresarial", "Responsabilidad Social Empresarial", "Trabajo de Graduación I"],
        ["Trabajo de Graduación II"],
    ]),
    ("E20218", "Licenciatura en Contaduría Pública", "DCE", 2018, 40, "Contabilidad", (0.25, 0.30, 0.45), [
        ["Introducción a la Contaduría Pública", "Matemática Básica", "Contabilidad I", "Introducción a la Economía", "Inglés I"],
        ["Contabilidad II", "Matemática Financiera", "Derecho Mercantil", "Microeconomía", "Inglés II"],
        ["Contabilidad III", "Estadística I", "Administración I", "Derecho Civil", "Metodología de la Investigación"],
        ["Contabilidad de Costos I", "Estadística II", "Administración II", "Legislación Tributaria I", "Informática Contable"],
        ["Contabilidad de Costos II", "Contabilidad Bancaria", "Legislación Tributaria II", "Derecho Laboral",
         "Administración Financiera I"],
        ["Auditoría I", "Contabilidad de Sociedades", "Administración Financiera II", "Presupuestos", "Ética Profesional"],
        ["Auditoría II", "Contabilidad Gubernamental", "Normas Internacionales de Información Financiera",
         "Finanzas Públicas", "Electiva I"],
        ["Auditoría Financiera", "Contabilidad Agropecuaria", "Análisis de Estados Financieros", "Electiva II",
         "Seminario de Investigación"],
        ["Auditoría Fiscal", "Peritaje Contable", "Trabajo de Graduación I"],
        ["Trabajo de Graduación II"],
    ]),
    ("E20318", "Licenciatura en Economía", "DCE", 2018, 22, "Economía", (0.35, 0.35, 0.30), [
        ["Introducción a la Economía", "Matemática I", "Contabilidad General", "Historia Económica", "Inglés I"],
        ["Microeconomía I", "Matemática II", "Estadística I", "Economía Política", "Inglés II"],
        ["Microeconomía II", "Macroeconomía I", "Estadística II", "Derecho Económico", "Metodología de la Investigación"],
        ["Macroeconomía II", "Econometría I", "Matemática Financiera", "Economía Salvadoreña",
         "Informática Aplicada a la Economía"],
        ["Econometría II", "Teoría Monetaria", "Economía Internacional I", "Finanzas Públicas", "Desarrollo Económico"],
        ["Economía Internacional II", "Evaluación de Proyectos", "Economía Laboral", "Análisis del Sector Externo",
         "Ética Profesional"],
        ["Política Económica", "Economía Agrícola", "Mercados Financieros", "Electiva I", "Seminario de Investigación"],
        ["Economía Ambiental", "Planificación Económica", "Electiva II", "Trabajo de Graduación I"],
        ["Trabajo de Graduación II"],
    ]),
    ("M10108", "Doctorado en Medicina", "DME", 2008, 28, "Ciencias Médicas", (0.80, 0.15, 0.05), [
        ["Biología Celular y Molecular", "Anatomía Humana I", "Histología I", "Química Médica", "Introducción a la Medicina"],
        ["Anatomía Humana II", "Histología II", "Embriología", "Bioquímica I", "Psicología Médica"],
        ["Fisiología I", "Bioquímica II", "Microbiología Médica", "Parasitología", "Bioestadística"],
        ["Fisiología II", "Inmunología", "Patología General", "Farmacología I", "Salud Pública I"],
        ["Patología Sistémica", "Farmacología II", "Semiología Médica", "Epidemiología", "Salud Pública II"],
        ["Medicina Interna I", "Cirugía I", "Pediatría I", "Ginecología y Obstetricia I", "Imagenología"],
        ["Medicina Interna II", "Cirugía II", "Pediatría II", "Ginecología y Obstetricia II", "Medicina Legal"],
        ["Psiquiatría", "Dermatología", "Oftalmología y Otorrinolaringología", "Ortopedia y Traumatología", "Urología"],
        ["Medicina Familiar", "Medicina Comunitaria", "Emergencias Médicas", "Cuidados Intensivos", "Bioética"],
        ["Clínica Médica Integrada", "Clínica Quirúrgica Integrada", "Clínica Pediátrica Integrada",
         "Clínica Gineco-Obstétrica Integrada"],
        ["Internado Rotatorio de Medicina", "Internado Rotatorio de Cirugía"],
        ["Internado Rotatorio de Pediatría", "Internado Rotatorio de Ginecología"],
    ]),
    ("M10214", "Licenciatura en Enfermería", "DME", 2014, 22, "Enfermería", (0.65, 0.25, 0.10), [
        ["Fundamentos de Enfermería", "Anatomía y Fisiología I", "Microbiología y Parasitología", "Psicología General", "Inglés I"],
        ["Enfermería Básica", "Anatomía y Fisiología II", "Nutrición y Dietética", "Sociología de la Salud", "Inglés II"],
        ["Enfermería del Adulto I", "Farmacología en Enfermería", "Salud Pública I", "Bioestadística",
         "Metodología de la Investigación"],
        ["Enfermería del Adulto II", "Enfermería Materno Infantil I", "Salud Pública II", "Educación para la Salud",
         "Epidemiología"],
        ["Enfermería Materno Infantil II", "Enfermería Pediátrica", "Enfermería en Salud Mental",
         "Administración en Enfermería I", "Ética y Bioética"],
        ["Enfermería Quirúrgica", "Enfermería Comunitaria", "Administración en Enfermería II", "Enfermería Geriátrica",
         "Electiva I"],
        ["Práctica Clínica Integrada I", "Cuidados Críticos", "Gerencia de Servicios de Salud", "Seminario de Investigación"],
        ["Práctica Clínica Integrada II", "Trabajo de Graduación"],
    ]),
    ("J10116", "Licenciatura en Ciencias Jurídicas", "DJS", 2016, 35, "Derecho", (0.25, 0.30, 0.45), [
        ["Introducción al Derecho", "Historia del Derecho", "Sociología Jurídica", "Economía Política",
         "Metodología de la Investigación Jurídica"],
        ["Derecho Romano", "Derecho Constitucional I", "Teoría del Estado", "Derecho Civil Personas", "Lógica Jurídica"],
        ["Derecho Constitucional II", "Derecho Civil Bienes", "Derecho Penal I", "Derecho Internacional Público",
         "Derecho Administrativo I"],
        ["Derecho Civil Obligaciones", "Derecho Penal II", "Derecho Administrativo II", "Derecho Mercantil I",
         "Derecho Procesal Constitucional"],
        ["Derecho Civil Contratos", "Derecho Penal III", "Derecho Mercantil II", "Derecho del Trabajo I",
         "Derecho Procesal Civil I"],
        ["Derecho Civil Familia", "Derecho Procesal Penal I", "Derecho del Trabajo II", "Derecho Procesal Civil II",
         "Derecho Tributario"],
        ["Derecho Civil Sucesiones", "Derecho Procesal Penal II", "Derecho Notarial", "Derecho Procesal Laboral",
         "Derecho Internacional Privado"],
        ["Derecho Registral", "Criminología", "Medicina Legal", "Derecho Procesal Mercantil", "Derecho Ambiental"],
        ["Práctica Forense I", "Derechos Humanos", "Filosofía del Derecho", "Electiva I", "Ética Profesional"],
        ["Práctica Forense II", "Seminario de Investigación Jurídica", "Trabajo de Graduación"],
    ]),
    ("H10116", "Licenciatura en Ciencias de la Educación, Especialidad Inglés", "DCH", 2016, 20, "Educación",
     (0.40, 0.40, 0.20), [
        ["Fundamentos de la Educación", "Psicología General", "Inglés Básico I", "Español Instrumental",
         "Introducción a la Lingüística"],
        ["Psicología del Desarrollo", "Inglés Básico II", "Fonética y Fonología del Inglés I", "Pedagogía General",
         "Tecnología Educativa"],
        ["Didáctica General", "Inglés Intermedio I", "Fonética y Fonología del Inglés II", "Gramática Inglesa I",
         "Metodología de la Investigación"],
        ["Evaluación Educativa", "Inglés Intermedio II", "Gramática Inglesa II", "Literatura Inglesa I", "Currículo"],
        ["Didáctica del Inglés I", "Inglés Avanzado I", "Gramática Inglesa III", "Literatura Inglesa II", "Estadística Educativa"],
        ["Didáctica del Inglés II", "Inglés Avanzado II", "Traducción", "Literatura Norteamericana", "Administración Educativa"],
        ["Práctica Docente I", "Lingüística Aplicada", "Elaboración de Materiales Didácticos", "Electiva I",
         "Seminario de Investigación"],
        ["Práctica Docente II", "Trabajo de Graduación"],
    ]),
    ("G10110", "Ingeniería Agronómica", "DAG", 2010, 18, "Ciencias Agronómicas", (0.55, 0.30, 0.15), [
        ["Matemática I", "Química General", "Biología General", "Introducción a la Agronomía", "Inglés I"],
        ["Matemática II", "Química Orgánica", "Botánica General", "Física Aplicada", "Inglés II"],
        ["Estadística I", "Bioquímica", "Fisiología Vegetal", "Edafología I", "Topografía Agrícola"],
        ["Edafología II", "Genética", "Microbiología Agrícola", "Climatología", "Metodología de la Investigación"],
        ["Entomología General", "Fitopatología", "Fitomejoramiento", "Hidráulica Agrícola", "Economía Agrícola"],
        ["Cultivos Anuales", "Fruticultura", "Zootecnia General", "Riego y Drenaje", "Maquinaria Agrícola"],
        ["Horticultura", "Producción de Granos Básicos", "Manejo Integrado de Plagas", "Nutrición Vegetal", "Extensión Agrícola"],
        ["Agroindustria", "Administración de Empresas Agrícolas", "Producción Pecuaria", "Agroecología", "Electiva I"],
        ["Evaluación de Proyectos Agrícolas", "Poscosecha", "Manejo de Recursos Naturales", "Seminario de Investigación"],
        ["Práctica Profesional", "Trabajo de Graduación"],
    ]),
    ("B10115", "Licenciatura en Biología", "DCN", 2015, 15, "Biología", (0.55, 0.30, 0.15), [
        ["Biología General I", "Química General", "Matemática I", "Introducción a la Biología", "Inglés I"],
        ["Biología General II", "Química Orgánica", "Matemática II", "Física General", "Inglés II"],
        ["Botánica I", "Zoología I", "Bioquímica", "Estadística I", "Ecología General"],
        ["Botánica II", "Zoología II", "Microbiología", "Genética", "Metodología de la Investigación"],
        ["Fisiología Vegetal", "Fisiología Animal", "Biología Molecular", "Evolución", "Biogeografía"],
        ["Ecología de Poblaciones", "Biología de la Conservación", "Parasitología", "Edafología", "Técnicas de Muestreo"],
        ["Limnología", "Biología Marina", "Impacto Ambiental", "Electiva I", "Seminario de Investigación"],
        ["Práctica de Campo", "Trabajo de Graduación"],
    ]),
    ("Q10112", "Licenciatura en Química y Farmacia", "DQF", 2012, 22, "Química y Farmacia", (0.55, 0.30, 0.15), [
        ["Química General I", "Matemática I", "Biología General", "Introducción a las Ciencias Farmacéuticas", "Inglés I"],
        ["Química General II", "Matemática II", "Física General", "Anatomía y Fisiología I", "Inglés II"],
        ["Química Orgánica I", "Química Analítica I", "Estadística I", "Anatomía y Fisiología II", "Microbiología"],
        ["Química Orgánica II", "Química Analítica II", "Fisicoquímica I", "Bioquímica I", "Botánica Farmacéutica"],
        ["Fisicoquímica II", "Análisis Instrumental I", "Bioquímica II", "Farmacognosia", "Parasitología"],
        ["Análisis Instrumental II", "Farmacología I", "Tecnología Farmacéutica I", "Química Farmacéutica I",
         "Metodología de la Investigación"],
        ["Farmacología II", "Tecnología Farmacéutica II", "Química Farmacéutica II", "Control de Calidad",
         "Legislación Farmacéutica"],
        ["Farmacia Hospitalaria", "Toxicología", "Cosmetología", "Administración Farmacéutica", "Electiva I"],
        ["Atención Farmacéutica", "Farmacoepidemiología", "Seminario de Investigación", "Electiva II"],
        ["Práctica Profesional", "Trabajo de Graduación"],
    ]),
]

CODIGO_ISI = "I10515"
NOMBRE_ISI = "Ingeniería de Sistemas Informáticos"
INGRESO_ISI = 90


def _carrera_isi() -> Carrera:
    materias = tuple(Materia(c, n, uv, ciclo, area, tuple(req)) for c, n, uv, ciclo, area, req in _ISI)
    return Carrera(CODIGO_ISI, NOMBRE_ISI, "DIA", 2015, INGRESO_ISI, _SW, (0.40, 0.35, 0.25), materias)


def construir_carreras() -> list[Carrera]:
    """La carrera de Sistemas con su plan propio y las demás con el plan derivado de su lista."""
    carreras = [_carrera_isi()]
    usados = {m.codigo for m in carreras[0].materias}
    for codigo, nombre, depto, plan, ingreso, area_base, turnos, ciclos in _PLANES:
        carreras.append(Carrera(codigo, nombre, depto, plan, ingreso, area_base, turnos,
                                construir_plan(plan, area_base, ciclos, usados)))
    return carreras


CARRERAS = construir_carreras()
ISI = CARRERAS[0]

# Años de la simulación: cohortes de nuevo ingreso desde ANIO_INICIAL; el último ciclo es el vigente.
ANIO_INICIAL = 2021
ANIO_FINAL = 2026
CICLO_VIGENTE = "2026-II"

MOTIVOS_DE_RETIRO = (
    "Solicitud del estudiante", "Situación económica", "Motivos de salud", "Choque de horario",
    "Cambio de carrera o institución", "Carga laboral", "Bajo rendimiento", "Otro",
)
