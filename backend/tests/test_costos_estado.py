"""Estado de cada costo frente al tablero (/costos).

El costo por UV se guarda en el OLTP, pero el tablero lee su copia en el Data
Warehouse, que solo cambia con la carga. Estas pruebas fijan que la pantalla diga,
período por período, si lo guardado ya llegó o falta recargar, y que la
confirmación del guardado aparezca en la fila y no en un aviso fuera de la vista.
"""

import os
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("APP_DB_USER", "x")
os.environ.setdefault("APP_DB_PASSWORD", "x")
os.environ.setdefault("POSTGRES_DB", "x")
os.environ.setdefault("SECRET_KEY", "x" * 40)

import pandas as pd  # noqa: E402

from app import dw  # noqa: E402
from app.routers import costos  # noqa: E402
from app.templating import templates  # noqa: E402


def _costo(valor="25.00", moneda="USD", fuente="Acuerdo 2026"):
    return SimpleNamespace(costo_por_uv=Decimal(valor), moneda=moneda, fuente=fuente)


def _almacen(valor=25.0, moneda="USD", fuente="Acuerdo 2026"):
    return {"costo_por_uv": valor, "moneda": moneda, "fuente": fuente}


class TestEstadoEnTablero(unittest.TestCase):
    def test_sin_costo_guardado(self):
        self.assertEqual(costos.estado_en_tablero(None, None), costos.SIN_COSTO)

    def test_igual_en_el_almacen_esta_en_el_tablero(self):
        self.assertEqual(costos.estado_en_tablero(_costo(), _almacen()), costos.EN_TABLERO)

    def test_otro_valor_queda_pendiente(self):
        self.assertEqual(costos.estado_en_tablero(_costo("30.00"), _almacen(25.0)), costos.PENDIENTE)

    def test_otra_fuente_o_moneda_tambien_queda_pendiente(self):
        # La fuente viaja al tablero para advertir cuando la cifra es un supuesto.
        self.assertEqual(costos.estado_en_tablero(_costo(fuente="Nueva"), _almacen()), costos.PENDIENTE)
        self.assertEqual(costos.estado_en_tablero(_costo(moneda="EUR"), _almacen()), costos.PENDIENTE)

    def test_periodo_que_el_almacen_no_tiene_o_sin_costo_alla(self):
        self.assertEqual(costos.estado_en_tablero(_costo(), None), costos.PENDIENTE)
        self.assertEqual(costos.estado_en_tablero(_costo(), _almacen(valor=None)), costos.PENDIENTE)

    def test_compara_a_dos_decimales(self):
        self.assertEqual(costos.estado_en_tablero(_costo("25.10"), _almacen(25.1000001)), costos.EN_TABLERO)


class TestCostosCargados(unittest.TestCase):
    def test_lee_dim_periodo_y_tolera_nulos(self):
        tabla = pd.DataFrame({
            "periodo_id": [1, 2], "costo_por_uv": [25.0, float("nan")],
            "moneda": ["USD", None], "fuente_costo": ["Acuerdo 2026", None],
        })
        with mock.patch.object(dw, "_leer", return_value=tabla):
            cargados = dw.costos_cargados()
        self.assertEqual(cargados[1], {"costo_por_uv": 25.0, "moneda": "USD", "fuente": "Acuerdo 2026"})
        self.assertEqual(cargados[2], {"costo_por_uv": None, "moneda": None, "fuente": None})


class TestPantalla(unittest.TestCase):
    def _html(self, filas, **extra):
        pendientes = [f for f in filas if f["estado"] == costos.PENDIENTE]
        contexto = {
            "request": SimpleNamespace(session={"csrf": "t"}, url=SimpleNamespace(path="/costos")),
            "url_for": lambda *a, **k: "/static/x",
            "usuario": SimpleNamespace(nombre_completo="A", rol_legible="Administrador", es_coordinador=False,
                                       es_admin=True, rol_db="rol_admin"),
            "filas": filas, "ultima_carga": None, "carga_en_curso": False, "monedas": costos.MONEDAS,
            "sin_costo": 0, "con_supuesto": 0, "almacen_consultado": True, "pendientes": pendientes,
            "al_dia": sum(1 for f in filas if f["estado"] == costos.EN_TABLERO),
            "guardado": None, "recargado": False, "ok": None, "error": None,
        }
        contexto.update(extra)
        return templates.env.get_template("modulos/costos.html").render(**contexto)

    def _fila(self, pid, codigo, costo, almacen, estado):
        periodo = SimpleNamespace(periodo_id=pid, codigo_periodo=codigo, activo=False)
        return {"periodo": periodo, "costo": costo, "es_supuesto": False, "estado": estado, "en_almacen": almacen}

    def test_pendiente_avisa_que_el_tablero_muestra_el_valor_anterior(self):
        fila = self._fila(1, "2026-I", _costo("30.00"), _almacen(25.0), costos.PENDIENTE)
        html = self._html([fila])
        self.assertIn("Falta recargar", html)
        self.assertIn("El tablero todavía muestra 25.00 USD por UV", html)
        self.assertIn("1 costo guardado", html)
        self.assertIn("2026-I", html)
        self.assertIn('href="#recarga"', html)

    def test_todo_al_dia(self):
        fila = self._fila(1, "2026-I", _costo(), _almacen(), costos.EN_TABLERO)
        html = self._html([fila])
        self.assertIn("✓ En el tablero", html)
        self.assertIn("El tablero está al día", html)
        self.assertNotIn("Falta recargar", html)

    def test_lo_recien_guardado_se_confirma_en_la_fila(self):
        fila = self._fila(7, "2026-II", _costo("30.00"), _almacen(25.0), costos.PENDIENTE)
        html = self._html([fila], guardado=7)
        self.assertIn('id="costo-7"', html)
        self.assertIn("es-reciente", html)
        self.assertIn("Guardado.", html)
        self.assertIn("recarga el Data Warehouse", html)

    def test_otras_filas_no_se_marcan_como_recien_guardadas(self):
        fila = self._fila(7, "2026-II", _costo(), _almacen(), costos.EN_TABLERO)
        self.assertNotIn("es-reciente", self._html([fila], guardado=99))

    def test_tras_recargar_se_confirma_dentro_de_la_tarjeta(self):
        fila = self._fila(1, "2026-I", _costo(), _almacen(), costos.EN_TABLERO)
        html = self._html([fila], recargado=True)
        self.assertIn("Recarga terminada.", html)
        self.assertIn('id="recarga"', html)

    def test_si_tras_recargar_algo_sigue_pendiente_no_se_dice_que_todo_esta_bien(self):
        fila = self._fila(1, "2026-I", _costo("30.00"), _almacen(25.0), costos.PENDIENTE)
        html = self._html([fila], recargado=True)
        self.assertNotIn("Recarga terminada.", html)
        self.assertIn("La recarga terminó, pero", html)

    def test_sin_acceso_al_almacen_no_se_afirma_nada_del_tablero(self):
        fila = self._fila(1, "2026-I", _costo(), None, None)
        html = self._html([fila], almacen_consultado=False, pendientes=[], al_dia=0)
        self.assertIn("No se pudo consultar el Data Warehouse", html)
        self.assertNotIn("En el tablero", html)
        self.assertNotIn("Falta recargar", html)


if __name__ == "__main__":
    unittest.main()
