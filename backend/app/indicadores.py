"""KPIs de la vista ejecutiva y su interpretación en texto — Fase 4.1.

Nivel analítico: descriptivo (¿qué ocurrió?). Cada función de interpretación
traduce un número a lo que significa para la institución, con las cifras del
filtro activo. No hay predicción ni recomendación: se describe lo observado.

Funciones puras, sin FastAPI ni base de datos, para poder probarlas.

Definiciones (las mismas que se defienden ante el jurado):

  Costo de reprobación    SUM(costo_reprobacion): lo invertido en inscripciones
                          que terminaron REPROBADO (UV × costo por UV del período).
  Costo por estudiante    costo de reprobación ÷ estudiantes que reprobaron al
                          menos una materia. Se divide entre quienes reprobaron,
                          no entre todos, porque mide cuánto representa cada caso
                          de reprobación; el promedio sobre todos se da como
                          contexto en el texto.
  Tasa de reprobación     reprobadas ÷ inscripciones cerradas (con nota final).
                          Retiros y cursos sin cierre no entran: no son reprobación.
  Proporción por          costo de reprobación de inscripciones con
  repetición              numero_intento > 1 ÷ costo de reprobación total: qué
                          parte del costo viene de estudiantes que ya cursaban la
                          materia por segunda vez o más.
"""

from dataclasses import dataclass

# Margen para decir que los repitentes reprueban "más" o "menos" que el resto:
# ±15 % sobre lo esperado por su peso en la matrícula. Por debajo de eso la
# diferencia es demasiado pequeña para afirmarla en una lectura descriptiva.
MARGEN_COMPARACION = 0.15


def _division(numerador, denominador) -> float | None:
    return float(numerador) / float(denominador) if denominador else None


def dinero(valor: float | None, moneda: str = "USD") -> str:
    if valor is None:
        return "—"
    simbolo = "$" if moneda == "USD" else f"{moneda} "
    return f"{simbolo}{valor:,.2f}" if abs(valor) < 100 else f"{simbolo}{valor:,.0f}"


def porcentaje(valor: float | None, decimales: int = 1) -> str:
    return "—" if valor is None else f"{valor * 100:.{decimales}f} %"


@dataclass(frozen=True)
class Indicadores:
    costo_reprobacion: float
    costo_por_estudiante: float | None
    tasa_reprobacion: float | None
    tasa_retiro: float | None
    proporcion_repeticion: float | None
    # Insumos, para las interpretaciones.
    costo_cerradas: float
    costo_repeticion: float
    cerradas: int
    reprobadas: int
    cerradas_repeticion: int
    retiradas: int
    estudiantes_reprobados: int
    estudiantes_evaluados: int

    @property
    def hay_datos(self) -> bool:
        return self.cerradas > 0

    @property
    def desenlaces(self) -> int:
        """Inscripciones que ya terminaron, de una forma o de otra."""
        return self.cerradas + self.retiradas


def calcular(totales: dict) -> Indicadores:
    t = {k: (v if v is not None else 0) for k, v in totales.items()}
    return Indicadores(
        costo_reprobacion=float(t["costo_reprobacion"]),
        costo_por_estudiante=_division(t["costo_reprobacion"], t["estudiantes_reprobados"]),
        tasa_reprobacion=_division(t["reprobadas"], t["cerradas"]),
        # Denominador: inscripciones con desenlace definitivo. Una que sigue en
        # curso todavia puede terminar de cualquier forma, asi que no entra.
        tasa_retiro=_division(t["retiradas"], t["cerradas"] + t["retiradas"]),
        proporcion_repeticion=_division(t["costo_repeticion"], t["costo_reprobacion"]),
        costo_cerradas=float(t["costo_cerradas"]),
        costo_repeticion=float(t["costo_repeticion"]),
        cerradas=int(t["cerradas"]),
        reprobadas=int(t["reprobadas"]),
        cerradas_repeticion=int(t["cerradas_repeticion"]),
        retiradas=int(t["retiradas"]),
        estudiantes_reprobados=int(t["estudiantes_reprobados"]),
        estudiantes_evaluados=int(t["estudiantes_evaluados"]),
    )


SIN_DATOS = "Sin inscripciones con nota final para estos filtros."


def _frase_variacion(actual: float | None, anterior: float | None, periodo_anterior: str | None,
                     en_puntos: bool = False, moneda: str = "USD") -> str:
    if periodo_anterior is None or actual is None or anterior is None:
        return ""
    diferencia = actual - anterior
    if en_puntos:
        puntos = diferencia * 100
        if abs(puntos) < 0.05:
            return f" Igual que en {periodo_anterior}."
        return f" {'Sube' if puntos > 0 else 'Baja'} {abs(puntos):.1f} pp frente a {periodo_anterior}."
    if anterior == 0:
        return ""
    cambio = diferencia / anterior
    if abs(cambio) < 0.005:
        return f" Igual que en {periodo_anterior}."
    return f" {porcentaje(abs(cambio))} {'más' if cambio > 0 else 'menos'} que en {periodo_anterior}."


def interpretar_costo(ind: Indicadores, anterior: Indicadores | None = None,
                      periodo_anterior: str | None = None, moneda: str = "USD") -> str:
    if not ind.hay_datos:
        return SIN_DATOS
    proporcion = _division(ind.costo_reprobacion, ind.costo_cerradas)
    texto = (f"{ind.reprobadas:,} materias reprobadas: el {porcentaje(proporcion)} de lo invertido "
             f"en las materias cerradas.")
    return texto + _frase_variacion(
        ind.costo_reprobacion, anterior.costo_reprobacion if anterior else None,
        periodo_anterior, moneda=moneda,
    )


def interpretar_costo_por_estudiante(ind: Indicadores, moneda: str = "USD") -> str:
    if not ind.hay_datos:
        return SIN_DATOS
    if not ind.estudiantes_reprobados:
        return "Ningún estudiante reprobó con estos filtros."
    materias_por_estudiante = ind.reprobadas / ind.estudiantes_reprobados
    return (f"{ind.estudiantes_reprobados:,} estudiantes reprobaron al menos una materia, "
            f"{materias_por_estudiante:.1f} en promedio cada uno.")


def interpretar_tasa(ind: Indicadores, anterior: Indicadores | None = None,
                     periodo_anterior: str | None = None) -> str:
    if not ind.hay_datos:
        return SIN_DATOS
    if not ind.reprobadas:
        return "Ninguna inscripción con nota final terminó reprobada."
    texto = f"1 de cada {round(1 / ind.tasa_reprobacion)} inscripciones con nota final terminó reprobada."
    return texto + _frase_variacion(
        ind.tasa_reprobacion, anterior.tasa_reprobacion if anterior else None,
        periodo_anterior, en_puntos=True,
    )


def interpretar_retiro(ind: Indicadores, anterior: Indicadores | None = None,
                       periodo_anterior: str | None = None) -> str:
    """El retiro no entra en la tasa ni en el costo de reprobación: se mide aparte."""
    if not ind.desenlaces:
        return "Sin inscripciones terminadas para estos filtros."
    if not ind.retiradas:
        return "Ninguna inscripción terminó en retiro."
    texto = f"{ind.retiradas:,} inscripciones terminaron en retiro, sin llegar a nota final."
    return texto + _frase_variacion(
        ind.tasa_retiro, anterior.tasa_retiro if anterior else None,
        periodo_anterior, en_puntos=True,
    )


def interpretar_repeticion(ind: Indicadores, moneda: str = "USD") -> str:
    if not ind.hay_datos:
        return SIN_DATOS
    if not ind.costo_reprobacion:
        return "No hubo costo de reprobación."
    peso_matricula = _division(ind.cerradas_repeticion, ind.cerradas)
    if not peso_matricula:
        return "Ninguna inscripción cerrada fue en segundo intento o más."
    texto = (f"Los repitentes son el {porcentaje(peso_matricula)} de las inscripciones y generan "
             f"el {porcentaje(ind.proporcion_repeticion)} del costo")
    razon = ind.proporcion_repeticion / peso_matricula
    if razon > 1 + MARGEN_COMPARACION:
        return texto + ": reprueban más que el resto."
    if razon < 1 - MARGEN_COMPARACION:
        return texto + ": reprueban menos que el resto."
    return texto + ", en proporción similar al resto."


def interpretar_ranking(ranking, costo_total: float, moneda: str = "USD") -> str:
    """ranking: DataFrame de datos.ranking_materias, ya ordenado por costo."""
    if ranking.empty or not costo_total:
        return "No hubo costo de reprobación con estos filtros."
    concentracion = ranking["costo_reprobacion"].sum() / costo_total
    primera = ranking.iloc[0]
    if len(ranking) == 1:
        texto = (f"{primera['codigo_materia']} concentra el {porcentaje(concentracion)} del costo "
                 f"({dinero(primera['costo_reprobacion'], moneda)}).")
    else:
        texto = (f"Estas {len(ranking)} materias concentran el {porcentaje(concentracion)} del costo; "
                 f"{primera['codigo_materia']} encabeza con {dinero(primera['costo_reprobacion'], moneda)}.")
    cuellos = ranking[ranking["es_cuello_botella"]]
    if cuellos.empty:
        return texto
    nombres = ", ".join(cuellos["codigo_materia"])
    return texto + f" {nombres} {'es' if len(cuellos) == 1 else 'son'} cuello de botella en la malla."


# ---------------------------------------------------------------------------
# Tarjetas de KPI compartidas por las dos pantallas (SCRUM-44)
#
# La vista web (/vista-ejecutiva, FastAPI) y la app Streamlit de dashboard/
# muestran exactamente los mismos cuatro indicadores. Sus etiquetas, ayudas e
# interpretaciones viven AQUÍ, una sola vez: si una pantalla cambiara una
# definición sin la otra, el jurado vería dos cifras distintas para el mismo
# indicador.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Tarjeta:
    etiqueta: str
    valor: str          # ya formateado para mostrar
    ayuda: str          # definición corta del indicador
    texto: str          # interpretación en texto, con las cifras del filtro activo
    actual: float | None
    previo: float | None
    formato: str        # "dinero" o "puntos": cómo se muestra el cambio contra el período previo


def formatear_cambio(valor: float, formato: str, moneda: str = "USD") -> str:
    return dinero(valor, moneda) if formato == "dinero" else f"{valor * 100:.1f} pp"


def tarjetas(ind: Indicadores, previos: Indicadores | None, periodo_anterior: str | None,
             moneda: str = "USD") -> list[Tarjeta]:
    def previo(campo: str):
        return getattr(previos, campo) if previos else None

    return [
        Tarjeta(
            "Costo de reprobación", dinero(ind.costo_reprobacion, moneda),
            "Suma de lo invertido (UV × costo por UV) en inscripciones que terminaron reprobadas.",
            interpretar_costo(ind, previos, periodo_anterior, moneda),
            ind.costo_reprobacion, previo("costo_reprobacion"), "dinero",
        ),
        Tarjeta(
            "Costo por estudiante que reprobó", dinero(ind.costo_por_estudiante, moneda),
            "Costo de reprobación ÷ estudiantes que reprobaron al menos una materia.",
            interpretar_costo_por_estudiante(ind, moneda),
            ind.costo_por_estudiante, previo("costo_por_estudiante"), "dinero",
        ),
        Tarjeta(
            "Tasa de reprobación", porcentaje(ind.tasa_reprobacion),
            "Reprobadas ÷ inscripciones con nota final. Los retiros no cuentan.",
            interpretar_tasa(ind, previos, periodo_anterior),
            ind.tasa_reprobacion, previo("tasa_reprobacion"), "puntos",
        ),
        Tarjeta(
            "Tasa de retiro", porcentaje(ind.tasa_retiro),
            "Retiros ÷ inscripciones con desenlace definitivo (cerradas + retiradas).",
            interpretar_retiro(ind, previos, periodo_anterior),
            ind.tasa_retiro, previo("tasa_retiro"), "puntos",
        ),
        Tarjeta(
            "Costo atribuible a repetición", porcentaje(ind.proporcion_repeticion),
            "Costo de reprobación de inscripciones en segundo intento o más ÷ costo total.",
            interpretar_repeticion(ind, moneda),
            ind.proporcion_repeticion, previo("proporcion_repeticion"), "puntos",
        ),
    ]


def interpretar_evolucion(evolucion, moneda: str = "USD") -> str | None:
    """El período más caro y el más barato. None si no hay costo que comparar."""
    if evolucion.empty:
        return None
    mayor = evolucion.loc[evolucion["costo_reprobacion"].idxmax()]
    menor = evolucion.loc[evolucion["costo_reprobacion"].idxmin()]
    if not mayor["costo_reprobacion"]:
        return None
    return (f"Mayor costo en {mayor['codigo_periodo']} ({dinero(mayor['costo_reprobacion'], moneda)}); "
            f"menor en {menor['codigo_periodo']} ({dinero(menor['costo_reprobacion'], moneda)}).")
