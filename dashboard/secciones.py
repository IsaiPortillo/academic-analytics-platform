"""Las secciones del dashboard interactivo.

Cada una es la versión interactiva de una pantalla de la app web y reutiliza, sin
copiarla, la lógica y los textos de backend/app/: las cifras coinciden por
construcción. Todas son descriptivas o diagnósticas; ninguna predice.

  Vista ejecutiva            <-> /vista-ejecutiva       (Fase 4.1)
  Panorama estratégico       <-> /dashboard
  Red curricular             <-> /red-curricular        (Fase 4.3)
  Cubo OLAP                  <-> /analitica-olap
  Patrón de riesgo observado <-> /analisis-diagnostico  (el equivalente descriptivo de las
                                 antiguas «alertas de deserción», que eran predictivas)
"""

from __future__ import annotations

from dataclasses import dataclass

import altair as alt
import networkx as nx
import pandas as pd
import streamlit as st

from app import (
    dashboard_estrategico as panel,
    indicadores as ind,
    indicadores_diagnostico as diag,
    olap,
    red_curricular as rc,
)
from app.umbrales import UMBRAL_FALTAS_RIESGO, UMBRAL_NOTA_APROBACION
from dashboard import datos, red, shell


@dataclass(frozen=True)
class Contexto:
    """Lo que toda sección necesita: filtros ya normalizados, moneda y paleta."""

    periodos: tuple
    carreras: tuple
    departamentos: tuple
    codigos: list
    moneda: str
    p: dict

    @property
    def filtros(self) -> tuple:
        return (self.periodos, self.carreras, self.departamentos)

    @property
    def etiqueta_periodo(self) -> str:
        return self.periodos[0] if self.periodos else "todos los períodos"


def md(texto: str) -> str:
    """Streamlit interpreta $...$ como fórmula LaTeX: los montos en dólares hay
    que escaparlos o dos cifras seguidas se renderizan como una ecuación."""
    return texto.replace("$", r"\$")


def lectura(texto: str) -> None:
    st.html(shell.lectura_html(texto))


# ---------------------------------------------------------------------------
# Vista ejecutiva (SCRUM-44): los cuatro KPIs, el ranking y la evolución
# ---------------------------------------------------------------------------

def _delta(tarjeta: ind.Tarjeta, periodo_anterior: str | None, moneda: str) -> str | None:
    """Variación contra el período anterior, con el signo que st.metric colorea.
    En los cuatro KPIs subir es empeorar, por eso se usa delta_color="inverse"."""
    if periodo_anterior is None or tarjeta.actual is None or tarjeta.previo is None:
        return None
    cambio = tarjeta.actual - tarjeta.previo
    if abs(cambio) < 1e-9:
        return None
    signo = "+" if cambio > 0 else "-"
    return f"{signo}{ind.formatear_cambio(abs(cambio), tarjeta.formato, moneda)} vs. {periodo_anterior}"


def vista_ejecutiva(ctx: Contexto) -> None:
    st.title("Vista ejecutiva: costo y rendimiento")
    st.caption("Nivel analítico descriptivo — ¿qué ocurrió en el ciclo y cuánto costó?")

    actual = ind.calcular(datos.totales(*ctx.filtros))
    periodo_anterior = None
    if len(ctx.periodos) == 1 and ctx.codigos.index(ctx.periodos[0]) > 0:
        periodo_anterior = ctx.codigos[ctx.codigos.index(ctx.periodos[0]) - 1]
    previos = ind.calcular(datos.totales((periodo_anterior,), ctx.carreras, ctx.departamentos)) if periodo_anterior else None

    st.header(f"Indicadores clave · {ctx.etiqueta_periodo}")
    if periodo_anterior:
        st.caption(f"Variación contra {periodo_anterior} · en rojo cuando el indicador empeora")
    tarjetas = ind.tarjetas(actual, previos, periodo_anterior, ctx.moneda)
    for fila in (tarjetas[:2], tarjetas[2:]):
        for columna, t in zip(st.columns(2), fila):
            with columna.container(border=True):
                st.metric(t.etiqueta, t.valor, delta=_delta(t, periodo_anterior, ctx.moneda),
                          delta_color="inverse", help=t.ayuda)
                lectura(t.texto)

    st.header("Materias que concentran el mayor costo de reprobación")
    clasificacion = datos.ranking(*ctx.filtros)
    if clasificacion.empty:
        st.info("No hubo costo de reprobación con los filtros elegidos.")
    else:
        formato_costo = "dollar" if ctx.moneda == "USD" else f"{ctx.moneda} %.0f"
        tabla = pd.DataFrame({
            "Materia": clasificacion["codigo_materia"] + " — " + clasificacion["nombre_materia"],
            "Reprobados": clasificacion["reprobados"],
            "Tasa de reprobación": clasificacion["tasa_reprobacion"],
            "Costo de reprobación": clasificacion["costo_reprobacion"],
            "Cuello de botella": clasificacion["es_cuello_botella"].map({True: "Sí", False: "—"}),
            "Bloquea": clasificacion["dependientes_totales"],
        })
        st.dataframe(tabla, hide_index=True, width="stretch", column_config={
            "Tasa de reprobación": st.column_config.NumberColumn(format="percent"),
            "Costo de reprobación": st.column_config.ProgressColumn(
                format=formato_costo, min_value=0, max_value=float(clasificacion["costo_reprobacion"].max())),
            "Bloquea": st.column_config.NumberColumn(
                help="Materias posteriores que quedan bloqueadas si no se aprueba esta (grafo en Neo4j)."),
        })
        lectura(ind.interpretar_ranking(clasificacion, actual.costo_reprobacion, ctx.moneda))

    st.header("Costo de reprobación por período")
    evolucion = datos.evolucion(ctx.carreras, ctx.departamentos)
    if not evolucion.empty:
        d = evolucion.assign(seleccionado=lambda x: x["codigo_periodo"].isin(ctx.periodos) if ctx.periodos else True)
        grafico = alt.Chart(d).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("codigo_periodo:N", sort=None, title="Período"),
            y=alt.Y("costo_reprobacion:Q", title=f"Costo de reprobación ({ctx.moneda})"),
            color=alt.condition("datum.seleccionado", alt.value(ctx.p["brand"]),
                                alt.value(ctx.p["input_border"])),
            tooltip=[alt.Tooltip("codigo_periodo:N", title="Período"),
                     alt.Tooltip("costo_reprobacion:Q", title="Costo", format=",.0f"),
                     alt.Tooltip("tasa_reprobacion:Q", title="Tasa de reprobación", format=".1%")],
        ).properties(height=260)
        st.altair_chart(grafico, width="stretch")
        texto = ind.interpretar_evolucion(evolucion, ctx.moneda)
        if texto:
            lectura(texto)


# ---------------------------------------------------------------------------
# Panorama estratégico
# ---------------------------------------------------------------------------

def panorama(ctx: Contexto) -> None:
    st.title("Dashboard estratégico")
    st.caption("Panorama institucional — ¿cómo va el rendimiento y dónde se concentra?")

    st.header(f"Aprobación por ciclo del plan · {ctx.etiqueta_periodo}")
    ciclos = panel.aprobacion_por_ciclo(datos.aprobacion_por_ciclo(*ctx.filtros), ctx.moneda)
    if ciclos:
        df = pd.DataFrame(ciclos).assign(ciclo_txt=lambda d: "Ciclo " + d["ciclo"].astype(str))
        barras = alt.Chart(df).mark_bar(cornerRadiusEnd=4, color=ctx.p["brand"]).encode(
            y=alt.Y("ciclo_txt:N", sort=None, title=None),
            x=alt.X("aprobacion:Q", title="Tasa de aprobación", scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(format="%")),
            tooltip=[alt.Tooltip("ciclo_txt:N", title="Ciclo"), alt.Tooltip("aprobacion:Q", title="Aprobación", format=".1%"),
                     alt.Tooltip("cerradas:Q", title="Con nota final", format=","),
                     alt.Tooltip("reprobados:Q", title="Reprobados", format=",")],
        ).properties(height=max(180, 32 * len(df)))
        st.altair_chart(barras, width="stretch")
    lectura(panel.leer_aprobacion(ciclos))

    st.header("Tasa de reprobación por período")
    evolucion = datos.evolucion(ctx.carreras, ctx.departamentos)
    if not evolucion.empty:
        d = evolucion.assign(seleccionado=lambda x: x["codigo_periodo"].isin(ctx.periodos) if ctx.periodos else True)
        st.altair_chart(
            alt.Chart(d).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                x=alt.X("codigo_periodo:N", sort=None, title="Período"),
                y=alt.Y("tasa_reprobacion:Q", title="Tasa de reprobación", axis=alt.Axis(format="%")),
                color=alt.condition("datum.seleccionado", alt.value(ctx.p["brand"]), alt.value(ctx.p["input_border"])),
                tooltip=[alt.Tooltip("codigo_periodo:N", title="Período"),
                         alt.Tooltip("tasa_reprobacion:Q", title="Tasa", format=".1%")],
            ).properties(height=240), width="stretch")
        lectura("Las columnas resaltadas son los períodos del filtro; el gráfico respeta el departamento y la "
                "carrera, pero muestra siempre todos los períodos.")

    st.header("Materias que más frenan la malla")
    cruce = datos.cruce(*ctx.filtros)
    materias = panel.materias_que_mas_bloquean(cruce, ctx.moneda)
    if materias:
        st.dataframe(pd.DataFrame(materias).rename(columns={
            "codigo": "Materia", "nombre": "Nombre", "dependientes": "Dependientes", "pct_plan": "% del plan",
            "reprobados": "Reprobados", "costo_texto": f"Costo ({ctx.moneda})", "bloqueos": "Bloqueos",
            "cuello": "Cuello de botella"}).assign(**{"Cuello de botella": lambda d: d["Cuello de botella"].map({True: "Sí", False: "—"})}),
            hide_index=True, width="stretch")
    lectura(panel.leer_impacto(materias, int(cruce["bloqueos"].sum())))


# ---------------------------------------------------------------------------
# Red curricular
# ---------------------------------------------------------------------------

def red_curricular(ctx: Contexto) -> None:
    st.title("Red curricular: dónde se concentra el costo")
    st.caption("Nivel diagnóstico — ¿por qué el costo de una materia se propaga al resto del plan? "
               "Describe lo ocurrido; no pronostica.")

    nodos_df, relaciones = datos.malla()
    grafo = rc.construir_red(nodos_df, relaciones)
    if not grafo.number_of_edges():
        st.warning(rc.SIN_RED)
        return
    if not nx.is_directed_acyclic_graph(grafo):
        st.error("La malla cargada tiene un ciclo de prerrequisitos; una malla así no se puede cursar. "
                 "Revisa el grafo de Neo4j y recarga: `python -m etl.carga`.")
        return

    cruce = datos.cruce(*ctx.filtros)
    disposicion = rc.disponer(grafo)
    maximo = max(int(cruce["dependientes_totales"].max()), 1)
    info = {}
    for f in cruce.to_dict("records"):
        tasa = f["tasa_reprobacion"]
        info[f["codigo_materia"]] = {
            "nombre": f["nombre_materia"], "cuello": bool(f["es_cuello_botella"]),
            "calor": f["dependientes_totales"] / maximo, "totales": int(f["dependientes_totales"]),
            "directos": int(f["dependientes_directos"]), "indirectos": int(f["dependientes_indirectos"]),
            "pct_plan": ind.porcentaje(f["indice_bloqueo"]), "costo": ind.dinero(f["costo_reprobacion"], ctx.moneda),
            "reprobados": int(f["reprobados"]), "tasa": ind.porcentaje(tasa if tasa == tasa else None),
            "pct_costo": ind.porcentaje(f["pct_costo"]), "bloqueos": int(f["bloqueos"]), "tipo_texto": f["tipo_texto"],
        }

    cuellos = cruce[cruce["es_cuello_botella"].fillna(False).astype(bool)]
    por_defecto = cuellos.iloc[0]["codigo_materia"] if not cuellos.empty else cruce.iloc[0]["codigo_materia"]
    codigos = sorted(info)
    elegida = st.selectbox("Materia", codigos, index=codigos.index(por_defecto),
                           format_func=lambda c: f"{c} · {info[c]['nombre']}",
                           help="Resalta lo que bloquea (dependientes en cascada) y lo que hay que aprobar antes.")
    dependientes, requisitos = set(nx.descendants(grafo, elegida)), set(nx.ancestors(grafo, elegida))

    with st.container(border=True):
        st.markdown(f"**{elegida} · {info[elegida]['nombre']}**" + ("  ·  cuello de botella" if info[elegida]["cuello"] else ""))
        for linea in red.texto_detalle(info[elegida], sorted(dependientes), sorted(requisitos),
                                       sorted(grafo.predecessors(elegida))):
            st.markdown(md(linea))

    svg = red.svg_red(disposicion, info, elegida, dependientes, requisitos, ctx.p)
    # st.markdown y no st.html: este último elimina los <svg>. Una sola línea, sin sangría ni líneas en blanco.
    st.markdown(f'<div style="overflow-x:auto;border:1px solid {ctx.p["border"]};border-radius:12px;'
                f'background:{ctx.p["bg"]}">{svg}</div>', unsafe_allow_html=True)
    st.caption("Las relaciones avanzan de izquierda a derecha: de la materia que hay que aprobar a la que la exige. "
               "Rojo: se bloquea si se reprueba la elegida · gris: hay que aprobarla antes · borde rojo: cuello de "
               "botella · más oscura: más dependientes. Desplaza la red para ver todos los ciclos.")
    lectura(rc.leer_estructura(grafo))

    st.header("Materias cuello de botella")
    ordenado = cruce.sort_values(["dependientes_totales", "codigo_materia"], ascending=[False, True])
    st.dataframe(pd.DataFrame({
        "Materia": ordenado["codigo_materia"] + " — " + ordenado["nombre_materia"],
        "Ciclo": ordenado["ciclo_plan"], "Dependientes directos": ordenado["dependientes_directos"],
        "Indirectos": ordenado["dependientes_indirectos"], "Total": ordenado["dependientes_totales"],
        "% del plan": ordenado["indice_bloqueo"],
        "Cuello de botella": ordenado["es_cuello_botella"].map({True: "Sí", False: "—"}),
    }), hide_index=True, width="stretch",
        column_config={"% del plan": st.column_config.NumberColumn(format="percent")})
    lectura(rc.leer_cuellos(grafo, nodos_df))

    st.header(f"Costo según la posición en la malla · {ctx.etiqueta_periodo}")
    g = rc.dispersion(cruce, ctx.moneda)
    orden = {"propaga": ctx.p["danger_text"], "estructural": ctx.p["warning_text"],
             "contenido": ctx.p["neutral_text"], "sin_hallazgo": ctx.p["muted"]}
    dispersion = cruce.assign(Lectura=cruce["tipo_texto"])
    puntos = alt.Chart(dispersion).mark_circle(size=110, opacity=0.9).encode(
        x=alt.X("costo_reprobacion:Q", title=f"Costo de reprobación ({ctx.moneda})", axis=alt.Axis(format=",.0f")),
        y=alt.Y("dependientes_totales:Q", title="Materias dependientes"),
        color=alt.Color("Lectura:N", scale=alt.Scale(domain=[rc.TIPOS[k] for k in orden], range=list(orden.values())),
                        legend=alt.Legend(orient="bottom", title=None)),
        tooltip=[alt.Tooltip("codigo_materia:N", title="Materia"), alt.Tooltip("nombre_materia:N", title="Nombre"),
                 alt.Tooltip("costo_reprobacion:Q", title="Costo", format=",.0f"),
                 alt.Tooltip("dependientes_totales:Q", title="Dependientes"), alt.Tooltip("Lectura:N")])
    etiquetas = alt.Chart(dispersion[(dispersion["tipo"] != "sin_hallazgo") | (dispersion["costo_reprobacion"] > 0)]
                          ).mark_text(align="left", dx=8, dy=-6, fontSize=10, fontWeight="bold", color=ctx.p["text"]
                                      ).encode(x="costo_reprobacion:Q", y="dependientes_totales:Q", text="codigo_materia:N")
    guias = []
    if g["x_mediana"] is not None and (cruce["costo_reprobacion"] > 0).any():
        mediana = float(cruce.loc[cruce["costo_reprobacion"] > 0, "costo_reprobacion"].median())
        guias.append(alt.Chart(pd.DataFrame({"x": [mediana]})).mark_rule(strokeDash=[4, 4], color=ctx.p["muted"]).encode(x="x:Q"))
    guias.append(alt.Chart(pd.DataFrame({"y": [g["umbral_dependientes"]]})).mark_rule(
        strokeDash=[4, 4], color=ctx.p["muted"]).encode(y="y:Q"))
    st.altair_chart(alt.layer(puntos, etiquetas, *guias).properties(height=340), width="stretch")
    st.caption("Línea vertical: costo mediano de las materias con costo. Línea horizontal: umbral de cuello de botella "
               f"({g['umbral_dependientes']:.1f} dependientes). Bloqueos = reprobados × materias dependientes: un conteo "
               "de lo ocurrido en el historial, no una proyección.")
    lectura(rc.leer_cruce(cruce, grafo, ctx.moneda))


# ---------------------------------------------------------------------------
# Cubo OLAP
# ---------------------------------------------------------------------------

def cubo_olap(ctx: Contexto) -> None:
    st.title("Cubo OLAP: resultados por dimensiones")
    st.caption("Elige hasta tres dimensiones y PostgreSQL calcula con ROLLUP o CUBE las medidas de cada "
               "combinación, los subtotales y el total sobre fact_inscripcion. Descriptivo.")

    claves = list(olap.DIMENSIONES)
    etiqueta = lambda c: olap.DIMENSIONES[c][0]  # noqa: E731
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1.2])
    d1 = col1.selectbox("Dimensión 1", claves, index=claves.index("periodo"), format_func=etiqueta)
    d2 = col2.selectbox("Dimensión 2 (opcional)", [None, *claves], index=([None, *claves].index("ciclo")),
                        format_func=lambda c: "— ninguna —" if c is None else etiqueta(c))
    d3 = col3.selectbox("Dimensión 3 (opcional)", [None, *claves], format_func=lambda c: "— ninguna —" if c is None else etiqueta(c))
    modo = col4.radio("Subtotales", list(olap.MODOS), format_func=lambda m: olap.MODOS[m], horizontal=False)

    dims = olap.validar_dimensiones([d1, d2, d3])
    df = datos.cubo(tuple(dims), modo, *ctx.filtros)
    truncado = len(df) > olap.LIMITE_FILAS
    filas = olap.preparar_filas(df.head(olap.LIMITE_FILAS), dims, ctx.moneda)
    if truncado:
        st.warning(f"El cubo tiene más de {olap.LIMITE_FILAS:,} filas y se muestran solo las primeras. "
                   "Acota con un filtro o elige menos dimensiones.")

    nombres = olap.etiquetas(dims)
    tabla = pd.DataFrame([
        dict(zip(nombres, f["celdas"]), **{
            "Con nota final": f["cerradas"], "Reprobados": f["reprobados"], "Tasa de reprobación": f["tasa"],
            "Nota promedio": None if f["nota_texto"] == "—" else float(f["nota_texto"]),
            f"Costo ({ctx.moneda})": f["costo"]})
        for f in filas])
    niveles = [f["nivel"] for f in filas]
    totales = [f["es_total"] for f in filas]

    def estilo(fila):
        i = fila.name
        if totales[i]:
            return [f"font-weight:800;background-color:{ctx.p['sunken']}"] * len(fila)
        if niveles[i] > 0:
            return [f"font-weight:600;background-color:{ctx.p['sunken']}"] * len(fila)
        return [""] * len(fila)

    st.dataframe(tabla.style.apply(estilo, axis=1), hide_index=True, width="stretch", column_config={
        "Tasa de reprobación": st.column_config.NumberColumn(format="percent"),
        f"Costo ({ctx.moneda})": st.column_config.NumberColumn(format="dollar" if ctx.moneda == "USD" else "%.0f"),
        "Con nota final": st.column_config.NumberColumn(format="%d"), "Reprobados": st.column_config.NumberColumn(format="%d"),
        "Nota promedio": st.column_config.NumberColumn(format="%.2f")})
    st.download_button("Descargar CSV", tabla.to_csv(index=False).encode("utf-8-sig"),
                       file_name="cubo_olap.csv", mime="text/csv")
    st.caption("«Todos» marca una dimensión agrupada: la fila es un subtotal (fondo tenue) o el total general "
               "(negrita). ROLLUP arma la jerarquía en el orden elegido; CUBE calcula además todas las demás "
               "combinaciones. Solo cuentan las inscripciones con nota final.")
    lectura(olap.leer_cubo(filas, dims, modo, ctx.moneda))


# ---------------------------------------------------------------------------
# Patrón de riesgo observado (el equivalente descriptivo de las «alertas»)
# ---------------------------------------------------------------------------

def patron_riesgo(ctx: Contexto) -> None:
    st.title("Estudiantes con patrón de riesgo observado")
    st.caption(f"Nivel diagnóstico. Describe lo ya observado (nota final menor a {UMBRAL_NOTA_APROBACION} y "
               f"{UMBRAL_FALTAS_RIESGO} o más ausencias en una misma materia): no pronostica quién desertará "
               "ni recomienda acciones.")

    r = datos.resumen_patron(*ctx.filtros)
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.metric("Estudiantes con el patrón", f"{int(r['estudiantes']):,}")
    with c2.container(border=True):
        st.metric("Inscripciones con el patrón", f"{int(r['inscripciones']):,}")
    lectura(diag.interpretar_patron(r, UMBRAL_FALTAS_RIESGO, UMBRAL_NOTA_APROBACION))

    estudiantes = datos.estudiantes_con_patron(*ctx.filtros)
    if estudiantes.empty:
        st.info("Ningún estudiante presenta el patrón con los filtros elegidos.")
        return
    tabla = estudiantes.rename(columns={
        "estudiante_id": "ID estudiante", "carnet_hash": "Carnet (SHA-256)", "anio_ingreso": "Cohorte",
        "trabaja": "Trabaja", "inscripciones": "Materias con el patrón", "materias": "Materias",
        "periodos": "Períodos", "max_ausencias": "Máx. ausencias", "nota_promedio": "Nota promedio"})
    tabla["Trabaja"] = tabla["Trabaja"].map({True: "Sí", False: "No"})
    st.dataframe(tabla, hide_index=True, width="stretch")
    st.caption(f"Se muestran como máximo {datos.LIMITE_ESTUDIANTES} estudiantes, con más materias en el patrón primero. "
               "Cada uno se identifica por el mismo ID que muestran los reportes del sistema; el carnet va anonimizado.")
