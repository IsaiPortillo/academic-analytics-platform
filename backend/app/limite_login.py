"""Bloqueo temporal tras varios inicios de sesión fallidos.

Dos contadores por ventana de tiempo:
  - por (IP, usuario): frena a quien prueba contraseñas contra una cuenta.
  - por IP: frena a quien recorre muchas cuentas desde el mismo origen.
Al llegar al máximo, ese par (o esa IP) queda bloqueado unos minutos; mientras
dure no se consulta la base ni se calcula bcrypt.

No hay bloqueo por usuario a secas, a propósito: permitiría que cualquiera
dejara sin acceso a un docente con solo fallar cinco veces con su nombre.

El estado vive en la memoria del proceso: alcanza con el único worker de
uvicorn del despliegue (deploy/academico-web.service) y se reinicia al
reiniciar el servicio. nginx aplica además su propio límite de peticiones a
/login (deploy/nginx-edumetrics.conf), que no depende de este proceso.
"""

import threading
import time
from collections import deque

from .config import settings


class LimiteIntentos:
    def __init__(self, max_por_cuenta: int, max_por_ip: int, ventana_s: int, bloqueo_s: int,
                 reloj=time.monotonic):
        self.max_por_cuenta = max_por_cuenta
        self.max_por_ip = max_por_ip
        self.ventana_s = ventana_s
        self.bloqueo_s = bloqueo_s
        self._reloj = reloj
        self._fallos: dict[tuple, deque] = {}
        self._bloqueado_hasta: dict[tuple, float] = {}
        self._candado = threading.Lock()

    @staticmethod
    def _claves(ip: str, usuario: str) -> list[tuple]:
        return [("cuenta", ip, usuario.strip().lower()), ("ip", ip)]

    def segundos_de_bloqueo(self, ip: str, usuario: str) -> int:
        """0 si puede intentar; si no, cuántos segundos le faltan."""
        ahora = self._reloj()
        with self._candado:
            restante = max((self._bloqueado_hasta.get(c, 0) - ahora for c in self._claves(ip, usuario)),
                           default=0)
        return max(0, int(restante + 0.999))

    def registrar_fallo(self, ip: str, usuario: str) -> None:
        ahora = self._reloj()
        with self._candado:
            if len(self._fallos) > 10_000:
                self._purgar(ahora)
            for clave, maximo in zip(self._claves(ip, usuario), (self.max_por_cuenta, self.max_por_ip)):
                fallos = self._fallos.setdefault(clave, deque())
                fallos.append(ahora)
                while fallos and ahora - fallos[0] > self.ventana_s:
                    fallos.popleft()
                if len(fallos) >= maximo:
                    self._bloqueado_hasta[clave] = ahora + self.bloqueo_s
                    fallos.clear()

    def registrar_exito(self, ip: str, usuario: str) -> None:
        # Solo se limpia el par: los fallos de esa IP contra otras cuentas siguen contando.
        clave = self._claves(ip, usuario)[0]
        with self._candado:
            self._fallos.pop(clave, None)
            self._bloqueado_hasta.pop(clave, None)

    def _purgar(self, ahora: float) -> None:
        for clave in [c for c, f in self._fallos.items() if not f or ahora - f[-1] > self.ventana_s]:
            del self._fallos[clave]
        for clave in [c for c, t in self._bloqueado_hasta.items() if t <= ahora]:
            del self._bloqueado_hasta[clave]


limite_login = LimiteIntentos(
    max_por_cuenta=settings.login_max_intentos,
    max_por_ip=settings.login_max_intentos_ip,
    ventana_s=settings.login_ventana_minutos * 60,
    bloqueo_s=settings.login_bloqueo_minutos * 60,
)
