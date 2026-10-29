"""Reportes personalizados: el coordinador arma el reporte eligiendo tema,
agrupación, filtros (incluido un rango de fechas) y gráfica.

Seguridad: el SQL se arma solo con fragmentos de las listas de abajo (TEMAS y
DIMENSIONES). Lo que llega por la URL es una CLAVE de esas listas; una clave
desconocida se ignora. Los valores de los filtros van siempre como parámetros
ligados. Es el mismo criterio que el cubo OLAP (app/olap.py).

Fechas: cada tema filtra y agrupa por la fecha del propio evento:
    asistencia      fecha de la sesión
    calificaciones  fecha de la evaluación
    matrícula       fecha de inscripción
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .exportar import Columna, Grafico, Reporte
from .umbrales import UMBRAL_NOTA_APROBACION

MAX_FILAS = 500          # filas de la agrupación principal
MAX_SERIES = 6           # valores distintos del desglose (el resto se agrupa en «Otros»)
GRAFICAS = {"lineas": "Líneas", "columnas": "Columnas", "barras": "Barras horizontales", "ninguna": "Sin gráfica"}


@dataclass(frozen=True)
class Metrica:
    etiqueta: str
    tipo: str          # tipo de Columna (entero, decimal, porcentaje)
    sql: str


@dataclass(frozen=True)
class Tema:
    titulo: str
    fecha: str                         # expresión de fecha del evento
    desde: str                         # FROM ... con los alias estándar
    metricas: dict[str, Metrica]
    metrica_inicial: str
    metrica_volumen: str               # cuántos registros: decide qué series del desglose se muestran
    dimensiones_propias: tuple[str, ...] = field(default_factory=tuple)
    descripcion: str = ""


# Alias comunes: i inscripción, s sección, m materia, p período, d docente, c carrera.
_COMUNES = """
    JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
    JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
    JOIN academico_oltp.periodos_academicos p ON p.periodo_id = s.periodo_id
    JOIN academico_oltp.docentes d ON d.docente_id = s.docente_id
    JOIN academico_oltp.carreras c ON c.carrera_id = m.carrera_id
"""

TEMAS: dict[str, Tema] = {
    "asistencia": Tema(
        "Asistencia", "a.fecha_sesion",
        "FROM academico_oltp.asistencias a JOIN academico_oltp.inscripciones i ON i.inscripcion_id = a.inscripcion_id"
        + _COMUNES,
        {
            "porcentaje_asistencia": Metrica("Asistencia", "porcentaje",
                "count(*) FILTER (WHERE a.estado_asistencia = 'PRESENTE')::numeric / NULLIF(count(*), 0)"),
            "ausencias": Metrica("Ausencias", "entero", "count(*) FILTER (WHERE a.estado_asistencia = 'AUSENTE')"),
            "justificadas": Metrica("Justificadas", "entero",
                "count(*) FILTER (WHERE a.estado_asistencia = 'JUSTIFICADO')"),
            "marcas": Metrica("Marcas", "entero", "count(*)"),
            "sesiones": Metrica("Sesiones", "entero", "count(DISTINCT (s.seccion_id, a.fecha_sesion))"),
            "estudiantes": Metrica("Estudiantes", "entero", "count(DISTINCT i.estudiante_id)"),
        },
        "porcentaje_asistencia", "marcas",
        descripcion="Marcas de asistencia por fecha de sesión.",
    ),
    "calificaciones": Tema(
        "Calificaciones", "e.fecha_evaluacion",
        "FROM academico_oltp.calificaciones cal "
        "JOIN academico_oltp.evaluaciones e ON e.evaluacion_id = cal.evaluacion_id "
        "JOIN academico_oltp.inscripciones i ON i.inscripcion_id = cal.inscripcion_id" + _COMUNES,
        {
            "nota_promedio": Metrica("Nota promedio", "decimal", "avg(cal.nota)"),
            "bajo_umbral": Metrica(f"Notas bajo {UMBRAL_NOTA_APROBACION:.0f}", "porcentaje",
                f"count(*) FILTER (WHERE cal.nota < {float(UMBRAL_NOTA_APROBACION)})::numeric / NULLIF(count(*), 0)"),
            "notas": Metrica("Notas registradas", "entero", "count(*)"),
            "evaluaciones": Metrica("Evaluaciones", "entero", "count(DISTINCT e.evaluacion_id)"),
            "estudiantes": Metrica("Estudiantes", "entero", "count(DISTINCT i.estudiante_id)"),
        },
        "nota_promedio", "notas",
        descripcion="Notas de cada evaluación por su fecha. Es la nota de la evaluación, no la nota final.",
    ),
    "matricula": Tema(
        "Matrícula y retiros", "i.fecha_inscripcion::date",
        "FROM academico_oltp.inscripciones i" + _COMUNES,
        {
            "inscripciones": Metrica("Inscripciones", "entero", "count(*)"),
            "retiros": Metrica("Retiros", "entero", "count(*) FILTER (WHERE i.estado_inscripcion = 'RETIRADO')"),
            "tasa_retiro": Metrica("Retiros ÷ inscripciones", "porcentaje",
                "count(*) FILTER (WHERE i.estado_inscripcion = 'RETIRADO')::numeric / NULLIF(count(*), 0)"),
            "repitentes": Metrica("En segundo intento o más", "entero", "count(*) FILTER (WHERE i.numero_intento > 1)"),
            "estudiantes": Metrica("Estudiantes", "entero", "count(DISTINCT i.estudiante_id)"),
        },
        "inscripciones", "inscripciones",
        dimensiones_propias=("motivo_retiro", "estado"),
        descripcion="Inscripciones por fecha de inscripción, con sus retiros y el motivo registrado.",
    ),
}


@dataclass(frozen=True)
class Dimension:
    etiqueta: str
    sql: str                # {fecha} se reemplaza por la fecha del tema
    orden: str = "grupo"    # orden natural de sus valores (expresión SQL sobre el resultado agrupado)
    es_fecha: bool = False


DIMENSIONES: dict[str, Dimension] = {
    "dia": Dimension("Día", "to_char({fecha}, 'YYYY-MM-DD')", es_fecha=True),
    "semana": Dimension("Semana (lunes)", "to_char(date_trunc('week', {fecha}), 'YYYY-MM-DD')", es_fecha=True),
    "mes": Dimension("Mes", "to_char(date_trunc('month', {fecha}), 'YYYY-MM')", es_fecha=True),
    "periodo": Dimension("Período", "p.codigo_periodo", "min(p.fecha_inicio)"),
    "materia": Dimension("Materia", "m.codigo_materia || ' · ' || m.nombre"),
    "docente": Dimension("Docente", "d.codigo_docente"),
    "carrera": Dimension("Carrera", "c.nombre"),
    "turno": Dimension("Turno", "initcap(s.turno)"),
    "seccion": Dimension("Sección", "m.codigo_materia || ' s' || s.numero_seccion || ' · ' || p.codigo_periodo",
                         "min(p.fecha_inicio), grupo"),
    # Solo matrícula: el detalle libre se descarta para poder agrupar.
    "motivo_retiro": Dimension("Motivo de retiro",
                               "CASE WHEN i.estado_inscripcion <> 'RETIRADO' THEN '(no retirada)' "
                               "ELSE COALESCE(split_part(i.motivo_retiro, ' — ', 1), 'Sin registrar') END"),
    "estado": Dimension("Estado de la inscripción", "initcap(i.estado_inscripcion)"),
}
DIMENSIONES_GENERALES = ("mes", "semana", "dia", "periodo", "materia", "docente", "carrera", "turno", "seccion")


def dimensiones_de(tema: str) -> list[str]:
    return list(DIMENSIONES_GENERALES) + list(TEMAS[tema].dimensiones_propias)


@dataclass
class Parametros:
    tema: str = "asistencia"
    dimension: str = "mes"
    desglose: Optional[str] = None
    metrica: Optional[str] = None
    desde: Optional[date] = None
    hasta: Optional[date] = None
    periodo_id: Optional[int] = None
    materia_id: Optional[int] = None
    docente_id: Optional[int] = None
    turno: Optional[str] = None
    grafica: str = "lineas"
    orden: str = "natural"       # natural | metrica

    def normalizar(self) -> "Parametros":
        """Descarta lo que no esté en las listas blancas (llega por la URL)."""
        if self.tema not in TEMAS:
            self.tema = "asistencia"
        tema = TEMAS[self.tema]
        validas = dimensiones_de(self.tema)
        if self.dimension not in validas:
            self.dimension = "mes"
        if self.desglose not in validas or self.desglose == self.dimension:
            self.desglose = None
        if self.metrica not in tema.metricas:
            self.metrica = tema.metrica_inicial
        if self.grafica not in GRAFICAS:
            self.grafica = "lineas"
        if self.orden not in ("natural", "metrica"):
            self.orden = "natural"
        if self.turno not in (None, "MATUTINO", "VESPERTINO", "NOCTURNO"):
            self.turno = None
        if self.desde and self.hasta and self.desde > self.hasta:
            self.desde, self.hasta = self.hasta, self.desde
        return self


def _where(p: Parametros) -> tuple[str, dict]:
    tema = TEMAS[p.tema]
    condiciones, valores = [], {}
    if p.desde:
        condiciones.append(f"{tema.fecha} >= :desde")
        valores["desde"] = p.desde
    if p.hasta:
        condiciones.append(f"{tema.fecha} < :hasta")
        valores["hasta"] = p.hasta + timedelta(days=1)
    for campo, columna in (("periodo_id", "s.periodo_id"), ("materia_id", "s.materia_id"),
                           ("docente_id", "s.docente_id"), ("turno", "s.turno")):
        if getattr(p, campo) is not None:
            condiciones.append(f"{columna} = :{campo}")
            valores[campo] = getattr(p, campo)
    return ("WHERE " + " AND ".join(condiciones)) if condiciones else "", valores


def consultar(db: Session, p: Parametros) -> list[dict]:
    """Filas agrupadas: {grupo, serie, <métricas>}. Sin desglose, serie es None."""
    tema = TEMAS[p.tema]
    dim = DIMENSIONES[p.dimension]
    expr_grupo = dim.sql.format(fecha=tema.fecha)
    expr_serie = DIMENSIONES[p.desglose].sql.format(fecha=tema.fecha) if p.desglose else "NULL"
    metricas = ",\n".join(f"{m.sql} AS {clave}" for clave, m in tema.metricas.items())
    where, valores = _where(p)
    # Con desglose el orden es siempre el natural: la gráfica necesita los grupos
    # en su secuencia (meses, períodos) para todas las series por igual.
    orden = (f"{p.metrica} DESC NULLS LAST, grupo" if p.orden == "metrica" and not p.desglose
             else dim.orden)
    sql = f"""
        SELECT {expr_grupo} AS grupo, {expr_serie} AS serie, {metricas}
        {tema.desde}
        {where}
        GROUP BY 1, 2
        ORDER BY {orden}, serie
    """
    return [dict(f) for f in db.execute(text(sql), valores).mappings().all()]


def construir(db: Session, p: Parametros, etiquetas_filtros: list[tuple[str, str]]) -> tuple[Reporte, dict]:
    """El Reporte (tabla + gráfica) y un resumen para la pantalla."""
    tema = TEMAS[p.tema]
    dim = DIMENSIONES[p.dimension]
    filas = consultar(db, p)
    metrica = tema.metricas[p.metrica]
    titulo = f"{tema.titulo} por {dim.etiqueta.lower()}"
    if not p.desglose:
        filas = filas[:MAX_FILAS]
        columnas = [Columna("grupo", dim.etiqueta, "texto", 1.8)] + [
            Columna(clave, m.etiqueta, m.tipo, 1.0) for clave, m in tema.metricas.items()]
        datos = [[f["grupo"]] + [f[clave] for clave in tema.metricas] for f in filas]
        indice = 1 + list(tema.metricas).index(p.metrica)
        grafico = Grafico(p.grafica, metrica.etiqueta, metrica.tipo, [indice]) if p.grafica != "ninguna" else None
        reporte = Reporte(titulo, f"reporte_{p.tema}_{p.dimension}", columnas, datos, etiquetas_filtros, grafico)
        return reporte, {"filas": len(datos), "series": 1}

    # Con desglose: tabla cruzada de la métrica elegida (una columna por serie).
    # Se muestran las series con más registros; una tasa no se puede sumar en
    # un «Otros», así que las demás se omiten y se avisa.
    volumen: dict = {}
    for f in filas:
        volumen[f["serie"]] = volumen.get(f["serie"], 0) + (f[tema.metrica_volumen] or 0)
    series = [s for s, _ in sorted(volumen.items(), key=lambda x: -x[1])][:MAX_SERIES]
    otros = len(volumen) - len(series)
    grupos: dict = {}
    for f in filas:
        if f["serie"] in series:
            grupos.setdefault(f["grupo"], {})[f["serie"]] = f[p.metrica]
    nombres = [str(s) if s is not None else "Sin valor" for s in series]
    columnas = [Columna("grupo", dim.etiqueta, "texto", 1.8)] + [
        Columna(f"serie_{i}", n, metrica.tipo, 1.0) for i, n in enumerate(nombres)]
    datos = [[g] + [valores.get(s) for s in series] for g, valores in list(grupos.items())[:MAX_FILAS]]
    grafico = (Grafico(p.grafica if p.grafica != "barras" else "columnas", metrica.etiqueta, metrica.tipo,
                       list(range(1, len(series) + 1))) if p.grafica != "ninguna" else None)
    titulo += f" y {DIMENSIONES[p.desglose].etiqueta.lower()}"
    if metrica.etiqueta.lower() != tema.titulo.lower():
        titulo += f" · {metrica.etiqueta.lower()}"
    reporte = Reporte(titulo, f"reporte_{p.tema}_{p.dimension}_{p.desglose}", columnas, datos,
                      etiquetas_filtros, grafico)
    return reporte, {"filas": len(datos), "series": len(series), "otros": otros}


# Atajos del hub de reportes: reportes personalizados ya armados.
ATAJOS = [
    ("Asistencia por mes", "Tendencia del porcentaje de asistencia.",
     {"tema": "asistencia", "dimension": "mes", "metrica": "porcentaje_asistencia", "grafica": "lineas"}),
    ("Asistencia por turno y período", "Compara turnos ciclo a ciclo.",
     {"tema": "asistencia", "dimension": "periodo", "desglose": "turno", "metrica": "porcentaje_asistencia",
      "grafica": "columnas"}),
    ("Notas por materia", "Nota promedio de las evaluaciones de cada materia.",
     {"tema": "calificaciones", "dimension": "materia", "metrica": "nota_promedio", "grafica": "barras",
      "orden": "metrica"}),
    ("Retiros por motivo", "Por qué se retiran los estudiantes.",
     {"tema": "matricula", "dimension": "motivo_retiro", "metrica": "retiros", "grafica": "barras",
      "orden": "metrica"}),
]
