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
    ayuda: str = ""    # cómo se calcula (sobre todo el denominador de un porcentaje)


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


# Alias comunes: i inscripción, s sección, m materia, p período, d docente,
# c carrera, dep departamento de la carrera, est estudiante.
_COMUNES = """
    JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
    JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
    JOIN academico_oltp.periodos_academicos p ON p.periodo_id = s.periodo_id
    JOIN academico_oltp.docentes d ON d.docente_id = s.docente_id
    JOIN academico_oltp.carreras c ON c.carrera_id = m.carrera_id
    JOIN academico_oltp.estudiantes est ON est.estudiante_id = i.estudiante_id
    LEFT JOIN academico_oltp.departamentos dep ON dep.departamento_id = c.departamento_id
"""

TEMAS: dict[str, Tema] = {
    "asistencia": Tema(
        "Asistencia", "a.fecha_sesion",
        "FROM academico_oltp.asistencias a JOIN academico_oltp.inscripciones i ON i.inscripcion_id = a.inscripcion_id"
        + _COMUNES,
        {
            "porcentaje_asistencia": Metrica("Asistencia", "porcentaje",
                "count(*) FILTER (WHERE a.estado_asistencia = 'PRESENTE')::numeric / NULLIF(count(*), 0)",
                "Marcas «Presente» ÷ todas las marcas. Las justificadas no cuentan como presentes."),
            "tasa_ausencia": Metrica("Ausencias ÷ marcas", "porcentaje",
                "count(*) FILTER (WHERE a.estado_asistencia = 'AUSENTE')::numeric / NULLIF(count(*), 0)",
                "Marcas «Ausente» ÷ todas las marcas. Asistencia + ausencias + justificadas suman 100 %."),
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
            "nota_promedio": Metrica("Nota promedio", "decimal", "avg(cal.nota)",
                "Promedio simple de las notas de evaluación (sin ponderar por el % de cada evaluación)."),
            "bajo_umbral": Metrica(f"Notas bajo {UMBRAL_NOTA_APROBACION:.0f}", "porcentaje",
                f"count(*) FILTER (WHERE cal.nota < {float(UMBRAL_NOTA_APROBACION)})::numeric / NULLIF(count(*), 0)",
                f"Notas de evaluación menores que {UMBRAL_NOTA_APROBACION:.0f} ÷ notas registradas. Se cuenta por "
                "evaluación, no por estudiante: no es la tasa de reprobación de la materia."),
            "desviacion": Metrica("Dispersión (desv. estándar)", "decimal", "stddev_samp(cal.nota)",
                "Cuánto se alejan las notas de su promedio: cerca de 0, notas parecidas; 2 o más, muy dispares."),
            "nota_maxima": Metrica("Nota más alta", "decimal", "max(cal.nota)"),
            "nota_minima": Metrica("Nota más baja", "decimal", "min(cal.nota)"),
            "notas": Metrica("Notas registradas", "entero", "count(*)"),
            "evaluaciones": Metrica("Evaluaciones", "entero", "count(DISTINCT e.evaluacion_id)"),
            "estudiantes": Metrica("Estudiantes", "entero", "count(DISTINCT i.estudiante_id)"),
        },
        "nota_promedio", "notas",
        dimensiones_propias=("tipo_evaluacion", "rango_nota"),
        descripcion="Notas de cada evaluación por su fecha. Es la nota de la evaluación, no la nota final.",
    ),
    "matricula": Tema(
        "Matrícula y retiros", "i.fecha_inscripcion::date",
        "FROM academico_oltp.inscripciones i" + _COMUNES,
        {
            "inscripciones": Metrica("Inscripciones", "entero", "count(*)"),
            "retiros": Metrica("Retiros", "entero", "count(*) FILTER (WHERE i.estado_inscripcion = 'RETIRADO')"),
            "tasa_retiro": Metrica("Retiros ÷ inscripciones", "porcentaje",
                "count(*) FILTER (WHERE i.estado_inscripcion = 'RETIRADO')::numeric / NULLIF(count(*), 0)",
                "Inscripciones retiradas ÷ todas las inscripciones, incluidas las del ciclo en curso."),
            "repitentes": Metrica("En segundo intento o más", "entero", "count(*) FILTER (WHERE i.numero_intento > 1)"),
            "tasa_repitencia": Metrica("Repitentes ÷ inscripciones", "porcentaje",
                "count(*) FILTER (WHERE i.numero_intento > 1)::numeric / NULLIF(count(*), 0)",
                "Inscripciones en segundo intento o más ÷ todas las inscripciones."),
            "secciones": Metrica("Secciones", "entero", "count(DISTINCT s.seccion_id)"),
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
    grupo: str = "Oferta académica"   # para ordenar el <select> en secciones


_DIAS = " ".join(f"WHEN {n} THEN '{d}'" for n, d in enumerate(
    ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"), start=1))

DIMENSIONES: dict[str, Dimension] = {
    "dia": Dimension("Día", "to_char({fecha}, 'YYYY-MM-DD')", es_fecha=True, grupo="Tiempo"),
    "semana": Dimension("Semana (lunes)", "to_char(date_trunc('week', {fecha}), 'YYYY-MM-DD')", es_fecha=True,
                        grupo="Tiempo"),
    "mes": Dimension("Mes", "to_char(date_trunc('month', {fecha}), 'YYYY-MM')", es_fecha=True, grupo="Tiempo"),
    "dia_semana": Dimension("Día de la semana", f"CASE extract(isodow FROM {{fecha}})::int {_DIAS} END",
                            "min(extract(isodow FROM {fecha}))", grupo="Tiempo"),
    "periodo": Dimension("Período", "p.codigo_periodo", "min(p.fecha_inicio)", grupo="Tiempo"),
    "anio": Dimension("Año", "p.anio::text", grupo="Tiempo"),
    "ciclo": Dimension("Ciclo (I o II)", "'Ciclo ' || p.ciclo_romano", grupo="Tiempo"),
    "carrera": Dimension("Carrera", "c.nombre"),
    "departamento": Dimension("Departamento", "COALESCE(dep.nombre, 'Sin departamento')"),
    "materia": Dimension("Materia", "m.codigo_materia || ' · ' || m.nombre"),
    "ciclo_plan": Dimension("Ciclo de la carrera (plan)", "'Ciclo ' || lpad(m.ciclo_plan::text, 2, '0')"),
    "uv": Dimension("Unidades valorativas", "m.unidades_valorativas || ' UV'", "min(m.unidades_valorativas)"),
    "seccion": Dimension("Sección", "m.codigo_materia || ' s' || s.numero_seccion || ' · ' || p.codigo_periodo",
                         "min(p.fecha_inicio), grupo"),
    "turno": Dimension("Turno", "initcap(s.turno)"),
    "docente": Dimension("Docente", "d.codigo_docente", grupo="Docente"),
    "escalafon": Dimension("Escalafón docente", "initcap(d.escalafon)", grupo="Docente"),
    "cohorte": Dimension("Año de ingreso (cohorte)", "'Ingreso ' || est.anio_ingreso", grupo="Estudiante"),
    "trabaja": Dimension("Trabaja o no", "CASE WHEN est.trabaja THEN 'Trabaja' WHEN est.trabaja IS NULL "
                                         "THEN 'Sin dato' ELSE 'No trabaja' END", grupo="Estudiante"),
    "condicion": Dimension("Condición académica", "initcap(COALESCE(est.condicion_academica, 'Sin dato'))",
                           grupo="Estudiante"),
    "intento": Dimension("Intento en la materia", "CASE WHEN i.numero_intento >= 3 THEN '3.er intento o más' "
                                                  "WHEN i.numero_intento = 2 THEN '2.º intento' "
                                                  "ELSE '1.er intento' END",
                         "min(i.numero_intento)", grupo="Estudiante"),
    # Solo calificaciones.
    "tipo_evaluacion": Dimension("Tipo de evaluación", r"regexp_replace(e.nombre_evaluacion, '\s*\d+$', '')",
                                 grupo="Propias del tema"),
    "rango_nota": Dimension("Rango de nota", "CASE WHEN cal.nota >= 9 THEN '9 a 10' "
                                             "ELSE floor(cal.nota)::int || ' a ' || (floor(cal.nota)::int + 1) END",
                            "min(cal.nota)", grupo="Propias del tema"),
    # Solo matrícula: el detalle libre se descarta para poder agrupar.
    "motivo_retiro": Dimension("Motivo de retiro",
                               "CASE WHEN i.estado_inscripcion <> 'RETIRADO' THEN '(no retirada)' "
                               "ELSE COALESCE(split_part(i.motivo_retiro, ' — ', 1), 'Sin registrar') END",
                               grupo="Propias del tema"),
    "estado": Dimension("Estado de la inscripción", "initcap(i.estado_inscripcion)", grupo="Propias del tema"),
}
DIMENSIONES_GENERALES = ("mes", "semana", "dia", "dia_semana", "periodo", "anio", "ciclo",
                         "carrera", "departamento", "materia", "ciclo_plan", "uv", "seccion", "turno",
                         "docente", "escalafon", "cohorte", "trabaja", "condicion", "intento")
GRUPOS_DIMENSION = ("Tiempo", "Oferta académica", "Docente", "Estudiante", "Propias del tema")


def dimensiones_de(tema: str) -> list[str]:
    return list(DIMENSIONES_GENERALES) + list(TEMAS[tema].dimensiones_propias)


def dimensiones_agrupadas(tema: str) -> list[tuple[str, list[tuple[str, Dimension]]]]:
    """Para el <select>: [(grupo, [(clave, dimensión), …]), …] en el orden de GRUPOS_DIMENSION."""
    claves = dimensiones_de(tema)
    return [(g, [(k, DIMENSIONES[k]) for k in claves if DIMENSIONES[k].grupo == g]) for g in GRUPOS_DIMENSION
            if any(DIMENSIONES[k].grupo == g for k in claves)]


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
    carrera_id: Optional[int] = None
    # Fechas escritas que no se entendieron: {"desde": "31/02/2025"}. Se ignoran y se avisa.
    fechas_invalidas: dict = field(default_factory=dict)

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
                           ("docente_id", "s.docente_id"), ("turno", "s.turno"), ("carrera_id", "m.carrera_id")):
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
             else dim.orden.format(fecha=tema.fecha))
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


# --- Ideas de reportes -------------------------------------------------------
# Reportes ya armados que enseñan a usar el constructor: cada uno dice qué
# pregunta responde, cómo se arma (se deriva de su configuración) y cómo leerlo
# sin sacar conclusiones de más. El alcance es descriptivo y diagnóstico: las
# ideas muestran lo que ocurrió y con qué se relaciona, no predicen.

@dataclass(frozen=True)
class Idea:
    clave: str
    categoria: str
    titulo: str
    pregunta: str
    config: dict
    lectura: str                 # cómo interpretarlo y qué filtro probar después
    destacada: bool = False      # aparece también como atajo en /reportes

    def coincide(self, p: "Parametros") -> bool:
        """¿Los parámetros actuales son los de esta idea? (los filtros pueden variar)."""
        base = Parametros(**{k: v for k, v in self.config.items()}).normalizar()
        return all(getattr(p, k) == getattr(base, k)
                   for k in ("tema", "dimension", "desglose", "metrica", "grafica", "orden"))

    def pasos(self) -> list[tuple[str, str]]:
        """«Cómo se arma»: los valores a elegir en el formulario, en su orden."""
        p = Parametros(**self.config).normalizar()
        tema = TEMAS[p.tema]
        pasos = [("Tema", tema.titulo), ("Agrupar por", DIMENSIONES[p.dimension].etiqueta)]
        if p.desglose:
            pasos.append(("Comparar por", DIMENSIONES[p.desglose].etiqueta))
        pasos.append(("Métrica", tema.metricas[p.metrica].etiqueta))
        pasos.append(("Gráfica", GRAFICAS[p.grafica]))
        if p.orden == "metrica":
            pasos.append(("Orden", "Por la métrica"))
        if p.turno:
            pasos.append(("Turno", p.turno.capitalize()))
        return pasos


def _idea(clave, categoria, titulo, pregunta, lectura, destacada=False, **config):
    return Idea(clave, categoria, titulo, pregunta, config, lectura, destacada)


IDEAS: list[Idea] = [
    # Asistencia
    _idea("asistencia_mes", "Asistencia", "Asistencia por mes",
          "¿Cómo se mueve la asistencia a lo largo del tiempo?",
          "Busca caídas puntuales y compáralas con el calendario (parciales, feriados, inicio de ciclo). "
          "Después filtra por una carrera o un turno para ver si la caída es general o de un grupo.",
          destacada=True, tema="asistencia", dimension="mes", metrica="porcentaje_asistencia", grafica="lineas"),
    _idea("asistencia_turno_periodo", "Asistencia", "Asistencia por turno y período",
          "¿Algún turno asiste menos, y es así en todos los ciclos?",
          "Si un turno queda abajo ciclo tras ciclo, la diferencia es estable y vale la pena revisarla; "
          "si solo pasa en un período, busca qué cambió ese ciclo.",
          destacada=True, tema="asistencia", dimension="periodo", desglose="turno",
          metrica="porcentaje_asistencia", grafica="columnas"),
    _idea("ausencia_dia_semana", "Asistencia", "¿Qué día se falta más?",
          "¿Las ausencias se concentran en algún día de la semana?",
          "Un día con más ausencias puede indicar choques de horario o traslados. Compara por turno "
          "para ver si el patrón es del día o de la jornada.",
          tema="asistencia", dimension="dia_semana", metrica="tasa_ausencia", grafica="columnas"),
    _idea("ausencia_materia", "Asistencia", "Materias con más ausencias",
          "¿En qué materias faltan más los estudiantes?",
          "Las primeras de la lista son candidatas a revisar junto con sus notas (tema Calificaciones, "
          "agrupado por materia). Una materia con pocas marcas puede quedar arriba por azar: mira la columna Marcas.",
          tema="asistencia", dimension="materia", metrica="tasa_ausencia", grafica="barras", orden="metrica"),
    _idea("ausencia_seccion", "Asistencia", "Secciones con más ausencias",
          "¿Qué grupos concretos tienen el problema de asistencia?",
          "Baja de la materia a la sección: dos secciones de la misma materia con asistencias muy distintas "
          "apuntan al grupo o al horario, no a la materia.",
          tema="asistencia", dimension="seccion", metrica="tasa_ausencia", grafica="barras", orden="metrica"),
    _idea("asistencia_trabaja", "Asistencia", "Asistencia de quienes trabajan",
          "¿Los estudiantes que trabajan asisten menos? ¿Siempre?",
          "Si la brecha aparece en todos los períodos, es un patrón estable. Relación no es causa: "
          "filtra por turno (los que trabajan suelen ir por la tarde o noche) antes de concluir.",
          tema="asistencia", dimension="periodo", desglose="trabaja", metrica="porcentaje_asistencia",
          grafica="lineas"),
    _idea("asistencia_intento", "Asistencia", "Asistencia según el intento",
          "¿Quien cursa una materia por segunda o tercera vez asiste igual?",
          "Una asistencia menor en repitentes sugiere que la reprobación anterior y la inasistencia "
          "van juntas. Revisa el mismo corte en el tema Calificaciones.",
          tema="asistencia", dimension="intento", metrica="porcentaje_asistencia", grafica="columnas"),

    # Rendimiento
    _idea("notas_materia", "Rendimiento", "Notas por materia",
          "¿Qué materias tienen las notas más bajas?",
          "Ordena por «Notas bajo 6» en vez de por promedio para ver dónde se concentra la reprobación: "
          "un promedio aceptable puede esconder muchos reprobados.",
          destacada=True, tema="calificaciones", dimension="materia", metrica="nota_promedio", grafica="barras",
          orden="metrica"),
    _idea("distribucion_notas", "Rendimiento", "Distribución de las notas",
          "¿Cómo se reparten las notas: hay dos grupos, muchos cerca del 6?",
          "Una montaña justo debajo de 6 indica estudiantes que reprueban por poco. Filtra por una materia "
          "o un docente para comparar su forma con la general.",
          tema="calificaciones", dimension="rango_nota", metrica="notas", grafica="columnas"),
    _idea("reprobacion_tipo_evaluacion", "Rendimiento", "¿Qué tipo de evaluación reprueba más?",
          "¿Los parciales, los laboratorios o el proyecto final concentran las notas bajas?",
          "Si un tipo de evaluación destaca, revisa si es en todas las materias o en unas pocas "
          "(compara por materia con un filtro de período).",
          tema="calificaciones", dimension="tipo_evaluacion", metrica="bajo_umbral", grafica="barras",
          orden="metrica"),
    _idea("notas_periodo_carrera", "Rendimiento", "Evolución de las notas por carrera",
          "¿El rendimiento de cada carrera mejora o empeora ciclo a ciclo?",
          "Fíjate en la tendencia, no en un punto aislado. Si todas las carreras bajan el mismo ciclo, "
          "la causa probablemente es común (calendario, cambio de modalidad).",
          tema="calificaciones", dimension="periodo", desglose="carrera", metrica="nota_promedio", grafica="lineas"),
    _idea("reprobacion_ciclo_plan", "Rendimiento", "¿En qué ciclo de la carrera se reprueba más?",
          "¿Las notas bajas se concentran en los primeros ciclos del plan o más adelante?",
          "Un pico en los primeros ciclos suele hablar de la transición desde el bachillerato; uno más "
          "adelante, de materias puente. Baja después a las materias de ese ciclo.",
          tema="calificaciones", dimension="ciclo_plan", metrica="bajo_umbral", grafica="columnas"),
    _idea("notas_cohorte", "Rendimiento", "Notas por cohorte de ingreso",
          "¿Las generaciones más recientes rinden distinto de las anteriores?",
          "Compara cohortes en el mismo período (filtro Período) para no mezclar el efecto del año "
          "con el de estar en ciclos más avanzados.",
          tema="calificaciones", dimension="cohorte", metrica="nota_promedio", grafica="columnas"),
    _idea("notas_intento", "Rendimiento", "¿Mejora el estudiante al repetir?",
          "¿Las notas de segundo y tercer intento son mejores que las del primero?",
          "Si el tercer intento no mejora, repetir la materia sin apoyo adicional no está funcionando "
          "para ese grupo. Mira la columna Estudiantes: el tercer intento suele ser un grupo pequeño.",
          tema="calificaciones", dimension="intento", metrica="nota_promedio", grafica="columnas"),
    _idea("notas_trabaja", "Rendimiento", "Rendimiento de quienes trabajan",
          "¿Hay brecha de notas entre quienes trabajan y quienes no, y se mantiene?",
          "Compárala con la brecha de asistencia: si las dos van juntas, la asistencia puede ser parte "
          "de la explicación. Es una relación observada, no una causa probada.",
          tema="calificaciones", dimension="periodo", desglose="trabaja", metrica="nota_promedio", grafica="lineas"),
    _idea("notas_uv", "Rendimiento", "Reprobación según la carga en UV",
          "¿Las materias con más unidades valorativas se reprueban más?",
          "Si sube con las UV, la carga de la materia pesa. Si no hay relación, la dificultad está en "
          "materias concretas: vuelve a la idea «Notas por materia».",
          tema="calificaciones", dimension="uv", metrica="bajo_umbral", grafica="columnas"),
    _idea("ciclo_i_vs_ii", "Rendimiento", "Ciclo I frente a ciclo II",
          "¿Se rinde distinto en el primer y en el segundo ciclo del año?",
          "Una diferencia que se repite todos los años sugiere algo del calendario (vacaciones, "
          "materias que se ofrecen solo en un ciclo).",
          tema="calificaciones", dimension="anio", desglose="ciclo", metrica="nota_promedio", grafica="columnas"),

    # Matrícula y retención
    _idea("retiros_motivo", "Matrícula y retención", "Retiros por motivo",
          "¿Por qué se retiran los estudiantes?",
          "«Sin registrar» son retiros anteriores a que se pidiera el motivo. Filtra por un período "
          "reciente para ver solo los que sí lo tienen.",
          destacada=True, tema="matricula", dimension="motivo_retiro", metrica="retiros", grafica="barras",
          orden="metrica"),
    _idea("retiro_periodo_turno", "Matrícula y retención", "Retiro por período y turno",
          "¿El retiro sube o baja con el tiempo, y en qué turno pesa más?",
          "Usa la tasa, no el número de retiros: un turno con más estudiantes tendrá más retiros "
          "aunque retenga mejor.",
          tema="matricula", dimension="periodo", desglose="turno", metrica="tasa_retiro", grafica="lineas"),
    _idea("retiro_materia", "Matrícula y retención", "Materias con más retiro",
          "¿De qué materias se retiran más los estudiantes?",
          "Cruza con «Notas por materia»: una materia con mucho retiro y notas altas puede estar "
          "ocultando su reprobación en los retiros.",
          tema="matricula", dimension="materia", metrica="tasa_retiro", grafica="barras", orden="metrica"),
    _idea("repitencia_materia", "Matrícula y retención", "Materias con más repitentes",
          "¿Qué materias tienen más estudiantes cursándolas por segunda vez o más?",
          "Son las materias cuello de botella en la práctica. Compáralas con la red curricular para ver "
          "cuántas materias dependen de ellas.",
          tema="matricula", dimension="materia", metrica="tasa_repitencia", grafica="barras", orden="metrica"),
    _idea("matricula_carrera_periodo", "Matrícula y retención", "Matrícula por carrera y período",
          "¿Cuántas inscripciones tiene cada carrera ciclo a ciclo?",
          "Sirve para planificar secciones y docentes. Cambia la métrica a «Estudiantes» para contar "
          "personas en vez de inscripciones.",
          tema="matricula", dimension="periodo", desglose="carrera", metrica="inscripciones", grafica="columnas"),
    _idea("retiro_condicion", "Matrícula y retención", "Retiro según la condición académica",
          "¿Los estudiantes en condición condicional se retiran más?",
          "Si la tasa es mucho mayor, la condición académica es una señal temprana útil para el "
          "seguimiento. Revisa también la columna Inscripciones: un grupo pequeño varía mucho.",
          tema="matricula", dimension="condicion", metrica="tasa_retiro", grafica="columnas"),
    _idea("retiro_trabaja", "Matrícula y retención", "Retiro de quienes trabajan",
          "¿Quienes trabajan se retiran más de las materias, y en qué períodos?",
          "Si la brecha crece en ciertos períodos, busca qué cambió (horarios, modalidad). "
          "Combínalo con el motivo de retiro filtrando por turno.",
          tema="matricula", dimension="periodo", desglose="trabaja", metrica="tasa_retiro", grafica="lineas"),

    # Docentes y oferta
    _idea("carga_docente", "Docentes y oferta", "Carga de estudiantes por docente",
          "¿Cuántas inscripciones atiende cada docente?",
          "Filtra por un período: sin filtro se suman todos los ciclos. Cambia la métrica a «Secciones» "
          "para ver cuántos grupos tiene cada uno.",
          tema="matricula", dimension="docente", metrica="inscripciones", grafica="barras", orden="metrica"),
    _idea("dispersion_docente", "Docentes y oferta", "Dispersión de notas por docente",
          "¿En qué grupos las notas son más dispares?",
          "Una dispersión alta indica grupos muy heterogéneos o criterios de evaluación distintos. "
          "No sirve por sí sola para evaluar al docente: compárala con la misma materia en otras secciones.",
          tema="calificaciones", dimension="docente", metrica="desviacion", grafica="barras", orden="metrica"),
    _idea("notas_escalafon", "Docentes y oferta", "Notas según el escalafón docente",
          "¿Hay diferencias de notas entre los grupos de docentes titulares, adjuntos o auxiliares?",
          "Los escalafones suelen dar materias distintas: filtra por una materia o un ciclo del plan "
          "antes de comparar.",
          tema="calificaciones", dimension="escalafon", metrica="nota_promedio", grafica="columnas"),
    _idea("reprobacion_departamento", "Docentes y oferta", "Reprobación por departamento",
          "¿Qué departamento concentra más notas bajas?",
          "Útil para la jefatura: baja después a las materias del departamento con el filtro de carrera.",
          tema="calificaciones", dimension="departamento", metrica="bajo_umbral", grafica="barras", orden="metrica"),
    _idea("secciones_turno_periodo", "Docentes y oferta", "Secciones abiertas por turno",
          "¿Cómo se reparte la oferta de secciones entre turnos, ciclo a ciclo?",
          "Compárala con la matrícula por turno: si un turno crece en estudiantes pero no en secciones, "
          "los grupos se están llenando.",
          tema="matricula", dimension="periodo", desglose="turno", metrica="secciones", grafica="columnas"),
]
IDEAS_POR_CLAVE = {i.clave: i for i in IDEAS}
CATEGORIAS_IDEAS = list(dict.fromkeys(i.categoria for i in IDEAS))


def idea_de(p: Parametros) -> Optional[Idea]:
    return next((i for i in IDEAS if i.coincide(p)), None)


# Atajos del hub de reportes: las ideas destacadas.
ATAJOS = [(i.titulo, i.pregunta, i.config) for i in IDEAS if i.destacada]
