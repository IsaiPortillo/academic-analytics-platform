"""Almacén de datos (coordinador): historial de cargas y última validación.

El historial sale de dw_academico.carga_control (la carga agrega una fila y
nunca la vacía). La validación es la de etl/validar_dw.py: compara el DW contra
el OLTP y Neo4j y deja su resultado en docs/validacion/registro_validacion.md,
que es lo que aquí se lee. Se puede volver a ejecutar desde la pantalla.
"""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from .. import dw, recarga
from ..avisos import redirigir, tomar_aviso
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/almacen", tags=["almacén"])
COORDINADOR = requiere_rol("rol_coordinador")
REGISTRO = recarga.RAIZ_PROYECTO / "docs" / "validacion" / "registro_validacion.md"


def leer_registro_validacion(ruta: Path = REGISTRO) -> dict | None:
    """Fecha, resultado y verificaciones que fallaron, desde el registro en Markdown."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    fecha = re.search(r"\*\*Fecha:\*\*\s*(.+)", texto)
    resultado = re.search(r"\*\*Resultado:\*\*\s*(\d+) de (\d+)", texto)
    filas, fallos = [], []
    for linea in texto.splitlines():
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) == 5 and celdas[0] not in ("Grupo", "---") and not set(celdas[0]) <= {"-"}:
            fila = {"grupo": celdas[0], "verificacion": celdas[1], "esperado": celdas[2],
                    "obtenido": celdas[3], "ok": "OK" in celdas[4]}
            filas.append(fila)
            if not fila["ok"]:
                fallos.append(fila)
    grupos = {}
    for f in filas:
        g = grupos.setdefault(f["grupo"], [0, 0])
        g[0] += f["ok"]
        g[1] += 1
    return {
        "fecha": fecha.group(1).strip() if fecha else None,
        "correctas": int(resultado.group(1)) if resultado else sum(f["ok"] for f in filas),
        "total": int(resultado.group(2)) if resultado else len(filas),
        "fallos": fallos,
        "grupos": [{"grupo": k, "correctas": v[0], "total": v[1]} for k, v in grupos.items()],
    }


def _resumen_calidad(calidad: dict) -> list[tuple[str, str]]:
    """Las señales de calidad que conviene ver de un vistazo."""
    if not isinstance(calidad, dict):
        return []
    resultado = calidad.get("inscripciones_por_resultado") or {}
    sin_nodo = calidad.get("materias_sin_nodo_en_grafo") or []
    return [
        ("Duración", f"{calidad.get('duracion_segundos', 0):.1f} s"),
        ("Resultados", " · ".join(f"{k.capitalize().replace('_', ' ')} {v:,}" for k, v in resultado.items())),
        ("Inscripciones sin costo", f"{calidad.get('inscripciones_sin_costo', 0):,}"),
        ("Materias sin nodo en el grafo", ", ".join(sin_nodo) if sin_nodo else "ninguna"),
        ("Cuellos de botella", ", ".join(calidad.get("cuellos_de_botella") or []) or "ninguno"),
    ]


@router.get("")
def ver(request: Request, usuario: UsuarioSesion = Depends(COORDINADOR)):
    ok, error = tomar_aviso(request)
    cargas, sin_dw = [], None
    try:
        cargas = dw.historial_cargas()
    except dw.DWNoConfigurado as exc:
        sin_dw = str(exc)
    except Exception:  # noqa: BLE001 - el DW puede no existir todavía
        sin_dw = "No se pudo leer el Data Warehouse."
    for c in cargas:
        # pandas entrega Timestamp: a datetime/date de Python para la plantilla.
        c["ejecutada_en"] = c["ejecutada_en"].to_pydatetime() if hasattr(c["ejecutada_en"], "to_pydatetime") else c["ejecutada_en"]
        c["fecha_corte"] = c["fecha_corte"].date() if hasattr(c["fecha_corte"], "date") else c["fecha_corte"]
        c["resumen"] = _resumen_calidad(c.get("calidad"))
    return templates.TemplateResponse(request, "modulos/almacen.html", {
        "usuario": usuario, "ok": ok, "error": error, "cargas": cargas, "sin_dw": sin_dw,
        "validacion": leer_registro_validacion(), "en_curso": recarga.hay_carga_en_curso(),
    })


@router.post("/validar")
def validar(request: Request, usuario: UsuarioSesion = Depends(COORDINADOR)):
    resultado = recarga.ejecutar_validacion()
    if resultado.ok:
        return redirigir(request, "/almacen", ok=resultado.mensaje)
    detalle = f" Detalle: {resultado.detalle.splitlines()[-1][:160]}" if resultado.detalle else ""
    return redirigir(request, "/almacen", error=resultado.mensaje + detalle)
