"""Acceso a datos del dashboard, con caché corta.

Todo sale de backend/app/dw.py: las mismas consultas, solo sobre dw_academico y
con rol_dashboard, que usa la app web. El DW cambia solo cuando se vuelve a
cargar, así que un minuto de caché basta. Los filtros viajan como tuplas simples
(hashables y estables para la caché).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import dw, red_curricular as rc
from dashboard.config import settings

LIMITE_RANKING = 10
LIMITE_ESTUDIANTES = 50


def _f(periodos: tuple, carreras: tuple, departamentos: tuple) -> dw.Filtros:
    return dw.Filtros(periodos, carreras, departamentos)


@st.cache_resource
def conectar() -> None:
    """Fija, una vez por proceso, la conexión de rol_dashboard. Si falta la contraseña
    lanza ErrorConfiguracion y no se cachea: el siguiente intento vuelve a probar."""
    dw.configurar(settings.database_url)


@st.cache_data(ttl=60, show_spinner=False)
def catalogos() -> tuple[pd.DataFrame, pd.DataFrame]:
    return dw.catalogo_periodos(), dw.catalogo_carreras()


@st.cache_data(ttl=60, show_spinner=False)
def totales(periodos: tuple, carreras: tuple, departamentos: tuple) -> dict:
    return dw.totales(_f(periodos, carreras, departamentos))


@st.cache_data(ttl=60, show_spinner=False)
def ranking(periodos: tuple, carreras: tuple, departamentos: tuple) -> pd.DataFrame:
    return dw.ranking_materias(_f(periodos, carreras, departamentos), LIMITE_RANKING)


@st.cache_data(ttl=60, show_spinner=False)
def evolucion(carreras: tuple, departamentos: tuple) -> pd.DataFrame:
    return dw.evolucion_por_periodo(dw.Filtros((), carreras, departamentos))


@st.cache_data(ttl=60, show_spinner=False)
def aprobacion_por_ciclo(periodos: tuple, carreras: tuple, departamentos: tuple) -> pd.DataFrame:
    return dw.aprobacion_por_ciclo(_f(periodos, carreras, departamentos))


@st.cache_data(ttl=60, show_spinner=False)
def malla() -> tuple[pd.DataFrame, pd.DataFrame]:
    return dw.malla(), dw.prerrequisitos()


@st.cache_data(ttl=60, show_spinner=False)
def cruce(periodos: tuple, carreras: tuple, departamentos: tuple) -> pd.DataFrame:
    nodos, _ = malla()
    return rc.cruce_costo_posicion(nodos, dw.costo_por_materia(_f(periodos, carreras, departamentos)))


@st.cache_data(ttl=60, show_spinner=False)
def cubo(dimensiones: tuple, modo: str, periodos: tuple, carreras: tuple, departamentos: tuple) -> pd.DataFrame:
    return dw.cubo(_f(periodos, carreras, departamentos), list(dimensiones), modo)


@st.cache_data(ttl=60, show_spinner=False)
def resumen_patron(periodos: tuple, carreras: tuple, departamentos: tuple) -> dict:
    return dw.resumen_patron(_f(periodos, carreras, departamentos))


@st.cache_data(ttl=60, show_spinner=False)
def estudiantes_con_patron(periodos: tuple, carreras: tuple, departamentos: tuple) -> pd.DataFrame:
    return dw.estudiantes_con_patron(_f(periodos, carreras, departamentos), LIMITE_ESTUDIANTES)


@st.cache_data(ttl=60, show_spinner=False)
def ultima_carga() -> dict | None:
    return dw.ultima_carga()
