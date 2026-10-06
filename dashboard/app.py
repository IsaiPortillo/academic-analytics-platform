"""Vista ejecutiva en Streamlit — SCRUM-44 (Fase 4.1).

Para el coordinador académico: qué ocurrió con el rendimiento y cuánto costó,
sin escribir consultas. Nivel analítico descriptivo (¿qué ocurrió?).

    streamlit run dashboard/app.py        # desde la raíz del proyecto

Es la misma vista ejecutiva que /vista-ejecutiva (la app web), con otra interfaz
y SIN duplicar su lógica: las consultas son las de backend/app/dw.py y las
definiciones, ayudas e interpretaciones de los indicadores son las de
backend/app/indicadores.py. Los números de ambas pantallas coinciden por
construcción.

Aislamiento (el criterio que el proyecto no negocia):
  - Solo lee dw_academico. Nunca academico_oltp.
  - Se conecta como rol_dashboard, que no tiene ningún permiso sobre el esquema
    operacional: no es disciplina del código, lo impone PostgreSQL
    (ver backend/app/verificar_dw.py).
  - Las credenciales salen del .env (dashboard/config.py), no del código. Este
    proceso no carga las del rol de servicio de la aplicación web.

Esta app NO tiene inicio de sesión (la web sí exige un coordinador). Por eso
escucha solo en 127.0.0.1 (ver .streamlit/config.toml).
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
for ruta in (RAIZ, RAIZ / "backend"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from app import dw, indicadores as ind  # noqa: E402
from dashboard.config import ErrorConfiguracion, settings  # noqa: E402

LIMITE_RANKING = 10
TODOS_LOS_PERIODOS = "Todos los períodos"
CRIMSON = "#8b0105"


def md(texto: str) -> str:
    """Streamlit interpreta $...$ como fórmula LaTeX: los montos en dólares hay
    que escaparlos o dos cifras seguidas se renderizan como una ecuación."""
    return texto.replace("$", r"\$")


# ---------------------------------------------------------------------------
# Acceso a datos (con caché corta: el DW solo cambia cuando se vuelve a cargar)
# ---------------------------------------------------------------------------

@st.cache_resource
def _conectar() -> None:
    """Fija, una vez por proceso, la conexión de rol_dashboard. Si falta la
    contraseña lanza ErrorConfiguracion y no se cachea: el siguiente intento
    vuelve a probar."""
    dw.configurar(settings.database_url)


@st.cache_data(ttl=60, show_spinner=False)
def _catalogos() -> tuple[pd.DataFrame, pd.DataFrame]:
    return dw.catalogo_periodos(), dw.catalogo_carreras()


# Los filtros se pasan como tuplas simples (hashables y estables para la caché).
@st.cache_data(ttl=60, show_spinner=False)
def _totales(periodos: tuple, carreras: tuple, departamentos: tuple) -> dict:
    return dw.totales(dw.Filtros(periodos, carreras, departamentos))


@st.cache_data(ttl=60, show_spinner=False)
def _ranking(periodos: tuple, carreras: tuple, departamentos: tuple) -> pd.DataFrame:
    return dw.ranking_materias(dw.Filtros(periodos, carreras, departamentos), LIMITE_RANKING)


@st.cache_data(ttl=60, show_spinner=False)
def _evolucion(carreras: tuple, departamentos: tuple) -> pd.DataFrame:
    return dw.evolucion_por_periodo(dw.Filtros((), carreras, departamentos))


@st.cache_data(ttl=60, show_spinner=False)
def _ultima_carga() -> dict | None:
    return dw.ultima_carga()


# ---------------------------------------------------------------------------
# Presentación
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


def _mostrar_kpis(tarjetas: list[ind.Tarjeta], periodo_anterior: str | None, moneda: str) -> None:
    for fila in (tarjetas[:2], tarjetas[2:]):
        for columna, tarjeta in zip(st.columns(2), fila):
            with columna.container(border=True):
                st.metric(tarjeta.etiqueta, tarjeta.valor,
                          delta=_delta(tarjeta, periodo_anterior, moneda),
                          delta_color="inverse", help=tarjeta.ayuda)
                st.markdown(md(tarjeta.texto))


def _mostrar_ranking(ranking: pd.DataFrame, costo_total: float, moneda: str) -> None:
    st.subheader("Materias que concentran el mayor costo de reprobación")
    if ranking.empty:
        st.info("No hubo costo de reprobación con los filtros elegidos.")
        return
    # El preset "dollar" agrega el separador de miles ($13,000); para otra
    # moneda se usa un formato con su código.
    formato_costo = "dollar" if moneda == "USD" else f"{moneda} %.0f"
    tabla = pd.DataFrame({
        "Materia": ranking["codigo_materia"] + " — " + ranking["nombre_materia"],
        "Reprobados": ranking["reprobados"],
        "Tasa de reprobación": ranking["tasa_reprobacion"],
        "Costo de reprobación": ranking["costo_reprobacion"],
        "Cuello de botella": ranking["es_cuello_botella"].map({True: "Sí", False: "—"}),
        "Bloquea": ranking["dependientes_totales"],
    })
    st.dataframe(
        tabla, hide_index=True, width="stretch",
        column_config={
            "Tasa de reprobación": st.column_config.NumberColumn(format="percent"),
            "Costo de reprobación": st.column_config.ProgressColumn(
                format=formato_costo, min_value=0, max_value=float(ranking["costo_reprobacion"].max())),
            "Bloquea": st.column_config.NumberColumn(
                help="Materias posteriores que quedan bloqueadas si no se aprueba esta (grafo en Neo4j)."),
        },
    )
    st.markdown(md(ind.interpretar_ranking(ranking, costo_total, moneda)))


def _mostrar_evolucion(evolucion: pd.DataFrame, seleccion: tuple, moneda: str) -> None:
    st.subheader("Costo de reprobación por período")
    if evolucion.empty:
        return
    datos = evolucion.assign(
        seleccionado=lambda d: d["codigo_periodo"].isin(seleccion) if seleccion else True
    )
    grafico = alt.Chart(datos).mark_bar().encode(
        x=alt.X("codigo_periodo:N", sort=None, title="Período"),
        y=alt.Y("costo_reprobacion:Q", title=f"Costo de reprobación ({moneda})"),
        color=alt.condition("datum.seleccionado", alt.value(CRIMSON), alt.value("#cbd5e1")),
        tooltip=[alt.Tooltip("codigo_periodo:N", title="Período"),
                 alt.Tooltip("costo_reprobacion:Q", title="Costo", format=",.0f"),
                 alt.Tooltip("tasa_reprobacion:Q", title="Tasa de reprobación", format=".1%")],
    ).properties(height=260)
    st.altair_chart(grafico, width="stretch")
    texto = ind.interpretar_evolucion(evolucion, moneda)
    if texto:
        st.caption(md(texto))


def main() -> None:
    st.set_page_config(page_title="Vista ejecutiva · Sistema Minerva", page_icon=":material/monitoring:",
                       layout="wide")
    st.title("Vista ejecutiva: costo y rendimiento")
    st.caption("Nivel analítico descriptivo — ¿qué ocurrió en el ciclo y cuánto costó? · "
               "Data Warehouse `dw_academico` · rol `rol_dashboard` (solo lectura)")

    try:
        _conectar()
        periodos, carreras = _catalogos()
    except ErrorConfiguracion as exc:
        st.error(str(exc))
        st.stop()
    except DBAPIError:
        st.error("No se pudo leer el Data Warehouse. Verifica que exista (database/oltp/10 y 11), "
                 "que `rol_dashboard` pueda iniciar sesión y que esté cargado: `python -m etl.carga`.")
        st.stop()
    if periodos.empty:
        st.warning("El Data Warehouse está vacío. Cárgalo con: `python -m etl.carga`.")
        st.stop()

    # --- Filtros ---------------------------------------------------------------
    codigos = periodos["codigo_periodo"].tolist()
    departamentos = dict(carreras[["codigo_departamento", "nombre_departamento"]].drop_duplicates().values)
    with st.sidebar:
        st.header("Filtros")
        periodo = st.selectbox("Período", [TODOS_LOS_PERIODOS] + codigos, index=len(codigos))  # el más reciente
        departamento = st.selectbox("Departamento", [None, *departamentos],
                                    format_func=lambda c: "Todos" if c is None else departamentos[c])
        visibles = carreras if departamento is None else carreras[carreras["codigo_departamento"] == departamento]
        nombres_carrera = dict(visibles[["codigo_carrera", "nombre_carrera"]].values)
        # La clave incluye el departamento: al cambiarlo, la carrera vuelve a "Todas".
        carrera = st.selectbox("Carrera", [None, *nombres_carrera], key=f"carrera_{departamento}",
                               format_func=lambda c: "Todas" if c is None else nombres_carrera[c])

    sel_periodos = () if periodo == TODOS_LOS_PERIODOS else (periodo,)
    sel_carreras = (carrera,) if carrera else ()
    sel_departamentos = (departamento,) if departamento else ()

    seleccion = periodos[periodos["codigo_periodo"].isin(sel_periodos)] if sel_periodos else periodos
    moneda = seleccion["moneda"].dropna().iloc[0] if seleccion["moneda"].notna().any() else "USD"

    # --- Aviso de costo supuesto (sale del dato, no está escrito aquí) -----------
    fuentes = seleccion["fuente_costo"].dropna().unique().tolist()
    if any("SUPUESTO" in f.upper() for f in fuentes):
        cifra = ", ".join(ind.dinero(c, moneda) for c in seleccion["costo_por_uv"].dropna().unique())
        st.warning(md(
            f"**Costo por unidad valorativa: {cifra}, supuesto paramétrico.** No es una cifra "
            f"presupuestaria oficial de la UES (fuente registrada: “{fuentes[0]}”). Los montos "
            "muestran el orden de magnitud y se recalculan solos cuando se registre la cifra oficial."
        ))

    # --- Indicadores -------------------------------------------------------------
    totales = ind.calcular(_totales(sel_periodos, sel_carreras, sel_departamentos))
    periodo_anterior = None
    if len(sel_periodos) == 1 and codigos.index(sel_periodos[0]) > 0:
        periodo_anterior = codigos[codigos.index(sel_periodos[0]) - 1]
    previos = (ind.calcular(_totales((periodo_anterior,), sel_carreras, sel_departamentos))
               if periodo_anterior else None)

    st.header(f"Indicadores clave · {sel_periodos[0] if sel_periodos else 'todos los períodos'}")
    if periodo_anterior:
        st.caption(f"Variación contra {periodo_anterior} · en rojo cuando el indicador empeora")
    _mostrar_kpis(ind.tarjetas(totales, previos, periodo_anterior, moneda), periodo_anterior, moneda)

    st.divider()
    _mostrar_ranking(_ranking(sel_periodos, sel_carreras, sel_departamentos), totales.costo_reprobacion, moneda)

    st.divider()
    _mostrar_evolucion(_evolucion(sel_carreras, sel_departamentos), sel_periodos, moneda)

    carga = _ultima_carga()
    if carga:
        st.caption(
            f"Última carga del Data Warehouse: {carga['ejecutada_en']:%Y-%m-%d %H:%M} UTC · fecha de "
            f"corte {carga['fecha_corte']} · {int(carga['filas_hechos']):,} inscripciones. Esta vista "
            "no consulta el sistema transaccional: lee solo el Data Warehouse."
        )


main()
