"""Dashboard interactivo de Sistema Minerva — Streamlit (SCRUM-44 y Fases 4.1 a 4.3).

Para el coordinador académico: qué ocurrió con el rendimiento, cuánto costó y
dónde se concentra, sin escribir consultas. Niveles analíticos descriptivo y
diagnóstico; nada aquí predice.

    streamlit run dashboard/app.py        # desde la raíz del proyecto

Es la versión interactiva de las pantallas de inteligencia de la app web y se ve
como parte de ella: misma marca, paleta, tipografía y modo oscuro (tema.py), mismo
marco de barra lateral y barra superior (shell.py). NO duplica su lógica: las
consultas son las de backend/app/dw.py y las definiciones y lecturas en texto son
las de backend/app/ (indicadores, red_curricular, olap, ...). Las cifras de ambas
interfaces coinciden por construcción.

Aislamiento (el criterio que el proyecto no negocia):
  - Solo lee dw_academico. Nunca academico_oltp.
  - Se conecta como rol_dashboard, que no tiene ningún permiso sobre el esquema
    operacional: no es disciplina del código, lo impone PostgreSQL
    (ver backend/app/verificar_dw.py).
  - Las credenciales salen del .env (dashboard/config.py), no del código. Este
    proceso no carga las del rol de servicio de la aplicación web.

Esta app NO tiene inicio de sesión propio. Sola escucha en 127.0.0.1; publicada, está
detrás de nginx con la sesión de la app web (deploy/): ver README.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
for ruta in (RAIZ, RAIZ / "backend"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

import streamlit as st  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from app import indicadores as ind  # noqa: E402
from dashboard import datos, secciones, shell, tema  # noqa: E402
from dashboard.config import ErrorConfiguracion, settings  # noqa: E402

TODOS_LOS_PERIODOS = "Todos los períodos"

# Mismo orden y nombres que el grupo «Inteligencia institucional» del menú de la app web.
SECCIONES = {
    "Vista ejecutiva": secciones.vista_ejecutiva,
    "Dashboard estratégico": secciones.panorama,
    "Red curricular": secciones.red_curricular,
    "Cubo OLAP": secciones.cubo_olap,
    "Patrón de riesgo observado": secciones.patron_riesgo,
}


def _cabeceras() -> dict:
    try:
        return dict(st.context.headers.items())
    except Exception:  # noqa: BLE001 — ejecución sin contexto de petición (pruebas)
        return {}


def main() -> None:
    st.set_page_config(page_title="Dashboard interactivo · Sistema Minerva", page_icon=":material/monitoring:",
                       layout="wide")
    p = tema.paleta(tema.nombre_tema())
    # st.markdown y no st.html: este último sanea el HTML y descarta la hoja de estilos entera
    # si trae url(data:...), y elimina los <svg> (la marca).
    st.markdown(f"<style>{tema.css(p)}</style>", unsafe_allow_html=True)
    app_url = settings.dashboard_app_url
    # nginx pasa quién es el usuario; aquí solo se muestra (ver shell.py). Cabeceras sin distinguir mayúsculas.
    cabeceras = {k.lower(): v for k, v in _cabeceras().items()}
    usuario = shell.usuario_de_cabeceras({"X-Minerva-Usuario": cabeceras.get("x-minerva-usuario"),
                                          "X-Minerva-Rol": cabeceras.get("x-minerva-rol")})
    rotulo = "Data Warehouse · dw_academico · rol_dashboard (solo lectura)"

    try:
        datos.conectar()
        periodos, carreras = datos.catalogos()
    except ErrorConfiguracion as exc:
        st.html(shell.barra_superior_html(usuario, app_url, rotulo))
        st.error(str(exc))
        st.stop()
    except DBAPIError:
        st.html(shell.barra_superior_html(usuario, app_url, rotulo))
        st.error("No se pudo leer el Data Warehouse. Verifica que exista (database/oltp/10 a 15), que "
                 "`rol_dashboard` pueda iniciar sesión y que esté cargado: `python -m etl.carga`.")
        st.stop()
    if periodos.empty:
        st.html(shell.barra_superior_html(usuario, app_url, rotulo))
        st.warning("El Data Warehouse está vacío. Cárgalo con: `python -m etl.carga`.")
        st.stop()

    codigos = periodos["codigo_periodo"].tolist()
    departamentos = dict(carreras[["codigo_departamento", "nombre_departamento"]].drop_duplicates().values)

    # --- Barra lateral: marca, secciones, filtros y vuelta al sistema -------------
    with st.sidebar:
        st.markdown(shell.marca_html(), unsafe_allow_html=True)
        st.html('<div class="mn-seccion">Inteligencia institucional</div>')
        pedida = st.query_params.get("seccion")
        seccion = st.radio("Sección", list(SECCIONES), label_visibility="collapsed",
                           index=list(SECCIONES).index(pedida) if pedida in SECCIONES else 0)
        st.html('<div class="mn-seccion">Filtros</div>')
        periodo = st.selectbox("Período", [TODOS_LOS_PERIODOS] + codigos, index=len(codigos))  # el más reciente
        departamento = st.selectbox("Departamento", [None, *departamentos],
                                    format_func=lambda c: "Todos" if c is None else departamentos[c])
        visibles = carreras if departamento is None else carreras[carreras["codigo_departamento"] == departamento]
        nombres_carrera = dict(visibles[["codigo_carrera", "nombre_carrera"]].values)
        # La clave incluye el departamento: al cambiarlo, la carrera vuelve a "Todas".
        carrera = st.selectbox("Carrera", [None, *nombres_carrera], key=f"carrera_{departamento}",
                               format_func=lambda c: "Todas" if c is None else nombres_carrera[c])
        enlaces = shell.enlaces_html(app_url)
        if enlaces:
            st.html(enlaces)

    sel_periodos = () if periodo == TODOS_LOS_PERIODOS else (periodo,)
    seleccion = periodos[periodos["codigo_periodo"].isin(sel_periodos)] if sel_periodos else periodos
    moneda = seleccion["moneda"].dropna().iloc[0] if seleccion["moneda"].notna().any() else "USD"
    ctx = secciones.Contexto(sel_periodos, (carrera,) if carrera else (), (departamento,) if departamento else (),
                             codigos, moneda, p)

    # --- Marco: barra superior y aviso de costo supuesto (sale del dato, no está escrito aquí) ---
    st.html(shell.barra_superior_html(usuario, app_url, rotulo))
    fuentes = seleccion["fuente_costo"].dropna().unique().tolist()
    if any("SUPUESTO" in f.upper() for f in fuentes):
        cifra = ", ".join(ind.dinero(c, moneda) for c in seleccion["costo_por_uv"].dropna().unique())
        st.warning(secciones.md(
            f"**Costo por UV: {cifra}** — supuesto paramétrico, no es una cifra oficial."
        ))

    SECCIONES[seccion](ctx)

    carga = datos.ultima_carga()
    if carga:
        st.caption(f"Datos al {carga['fecha_corte']}.")


main()
