"""Ejecución de la carga del Data Warehouse desde la aplicación.

Permite al coordinador recargar el DW sin abrir una terminal, que es el paso que
faltaba después de editar el costo por unidad valorativa: el costo se escribe en
el esquema operacional, pero el tablero lee el DW, así que hasta ahora había que
correr `python -m etl.carga` a mano.

Por qué un SUBPROCESO y no una función importada
------------------------------------------------
La aplicación web se conecta como rol_app (no puede escribir en el DW) y como
rol_dashboard (solo lectura). Quien escribe el DW es rol_dw_carga, y esa
separación de privilegios es el argumento de seguridad más fuerte del proyecto.

Si la carga se ejecutara dentro del proceso web, ese proceso necesitaría una
conexión de escritura al DW y el aislamiento se perdería. Lanzándola como
proceso aparte, la aplicación ORQUESTA pero no escribe: quien escribe sigue
siendo el ETL con su propio rol. El modelo de seguridad se mantiene intacto y
se puede seguir demostrando.

Concurrencia
------------
Dos cargas simultáneas no corromperían el DW —cada una corre en una transacción
con TRUNCATE, así que el motor las serializa— pero sí harían trabajo al pedo y
dejarían dos filas en carga_control. El candado evita la segunda y devuelve un
mensaje claro.

Es un candado en memoria del proceso, no distribuido. Alcanza porque el servicio
corre con un solo worker (ver deploy/academico-web.service). Si algún día se
despliega con varios, habría que moverlo a un lock de PostgreSQL
(pg_try_advisory_lock), que no exige permisos sobre tablas.
"""

import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]

# Medido el 26/10/2026: ~45 s de extremo a extremo con ~37k hechos. Ojo con el
# número que registra carga_control (unos 3 s): ese mide solo la escritura del
# modelo dimensional, no la extracción del OLTP y de Neo4j ni la transformación,
# que es donde se va casi todo el tiempo.
#
# El margen hasta 5 minutos es amplio a propósito: si alguna vez tarda más, algo
# va mal y es mejor cortar que dejar la petición colgada. Detrás de nginx hace
# falta subir proxy_read_timeout para esta ruta (ver deploy/nginx-edumetrics.conf):
# el valor por defecto son 60 s y la carga seguiría corriendo tras el 504.
TIEMPO_LIMITE_SEGUNDOS = 300

_candado = threading.Lock()


@dataclass(frozen=True)
class Resultado:
    ok: bool
    mensaje: str
    # Últimas líneas de la salida del proceso. Se guardan para el registro del
    # servidor y para poder explicar un fallo sin tener que reproducirlo.
    detalle: str = ""


def _ultimas_lineas(texto: str, cuantas: int = 12) -> str:
    lineas = [l.rstrip() for l in (texto or "").splitlines() if l.strip()]
    return "\n".join(lineas[-cuantas:])


def hay_carga_en_curso() -> bool:
    return _candado.locked()


def _correr(modulo: str) -> subprocess.CompletedProcess:
    # UTF-8 explícito: en Windows la salida del proceso hijo llega en la página
    # de códigos local y los mensajes con acentos se leían rotos.
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", modulo],
        cwd=RAIZ_PROYECTO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=entorno,
        timeout=TIEMPO_LIMITE_SEGUNDOS,
    )


def ejecutar_validacion() -> Resultado:
    """Corre `python -m etl.validar_dw`, que compara el DW contra el OLTP y Neo4j
    y reescribe docs/validacion/registro_validacion.md.

    Comparte el candado con la carga: validar mientras se recarga compararía un
    DW a medio escribir contra el OLTP y daría fallos que no existen.
    """
    if not _candado.acquire(blocking=False):
        return Resultado(False, "Hay una carga o una validación en curso. Espera a que termine.")
    try:
        proceso = _correr("etl.validar_dw")
    except subprocess.TimeoutExpired:
        return Resultado(False, f"La validación superó el límite de {TIEMPO_LIMITE_SEGUNDOS // 60} minutos.")
    except OSError as exc:
        return Resultado(False, f"No se pudo iniciar la validación: {exc}")
    finally:
        _candado.release()
    resumen = re.search(r"(\d+) de (\d+) verificaciones correctas", proceso.stdout or "")
    if resumen and proceso.returncode == 0:
        return Resultado(True, f"Validación completa: {resumen.group(0)}.", _ultimas_lineas(proceso.stdout))
    if resumen:
        return Resultado(False, f"Validación con fallos: {resumen.group(0)}. Revisa el detalle abajo.",
                         _ultimas_lineas(proceso.stdout))
    return Resultado(False, f"La validación no terminó (código {proceso.returncode}).",
                     _ultimas_lineas(proceso.stderr) or _ultimas_lineas(proceso.stdout))


def ejecutar_carga() -> Resultado:
    """Corre `python -m etl.carga` y resume cómo terminó.

    No lanza excepciones: cualquier fallo se devuelve como Resultado para que la
    interfaz pueda mostrarlo en vez de responder un error 500.
    """
    if not _candado.acquire(blocking=False):
        return Resultado(False, "Ya hay una recarga en curso. Espera a que termine.")

    try:
        proceso = _correr("etl.carga")
    except subprocess.TimeoutExpired:
        return Resultado(
            False,
            f"La carga superó el límite de {TIEMPO_LIMITE_SEGUNDOS // 60} minutos y se canceló. "
            "El Data Warehouse quedó como estaba: la carga corre en una sola transacción.",
        )
    except OSError as exc:
        return Resultado(False, f"No se pudo iniciar el proceso de carga: {exc}")
    finally:
        _candado.release()

    if proceso.returncode == 0:
        return Resultado(
            True,
            "Data Warehouse recargado. El tablero ya muestra las cifras actualizadas.",
            _ultimas_lineas(proceso.stdout),
        )

    # El ETL imprime el motivo en stderr; si viene vacío, se cae a stdout.
    detalle = _ultimas_lineas(proceso.stderr) or _ultimas_lineas(proceso.stdout)
    return Resultado(
        False,
        f"La carga falló (código {proceso.returncode}). El Data Warehouse quedó como estaba.",
        detalle,
    )
