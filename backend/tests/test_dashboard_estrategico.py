"""Pruebas del dashboard estratégico: aprobación por ciclo y materias que más frenan
la malla. No tocan la base de datos.

    cd backend && python -m unittest discover -s tests -v
"""

import unittest

import pandas as pd

from app import dashboard_estrategico as panel
from tests.test_red_curricular import _costos, _materias
from app import red_curricular as rc


def _ciclos(*filas):
    return pd.DataFrame(filas, columns=["ciclo_plan", "cerradas", "reprobados", "costo_reprobacion"])


class TestAprobacionPorCiclo(unittest.TestCase):
    def test_la_aprobacion_es_aprobadas_entre_cerradas(self):
        f = panel.aprobacion_por_ciclo(_ciclos((1, 1000, 250, 10_000.0)))[0]
        self.assertEqual((f["aprobacion"], f["aprobacion_texto"], f["pct"]), (0.75, "75.0 %", 0.75))
        self.assertEqual(f["costo_texto"], "$10,000")

    def test_ciclo_sin_inscripciones_cerradas_no_divide_entre_cero(self):
        f = panel.aprobacion_por_ciclo(_ciclos((8, 0, 0, 0.0)))[0]
        self.assertIsNone(f["aprobacion"])
        self.assertEqual((f["aprobacion_texto"], f["pct"]), ("—", 0.0))

    def test_lectura_nombra_el_ciclo_donde_menos_y_donde_mas_se_aprueba(self):
        filas = panel.aprobacion_por_ciclo(_ciclos((1, 1000, 300, 0.0), (2, 800, 160, 0.0), (3, 900, 90, 0.0)))
        texto = panel.leer_aprobacion(filas)
        self.assertIn("El ciclo 1 es donde menos se aprueba (70.0 %", texto)
        self.assertIn("el ciclo 3 donde más (90.0 %)", texto)
        self.assertIn("20.0 puntos porcentuales", texto)

    def test_si_los_ciclos_se_parecen_lo_dice_en_vez_de_inventar_un_hallazgo(self):
        filas = panel.aprobacion_por_ciclo(_ciclos((1, 1000, 250, 0.0), (2, 1000, 255, 0.0)))
        self.assertIn("prácticamente la misma", panel.leer_aprobacion(filas))

    def test_ciclos_con_pocas_inscripciones_no_se_comparan(self):
        filas = panel.aprobacion_por_ciclo(_ciclos((1, 20, 10, 0.0), (2, 1000, 100, 0.0)))
        self.assertIn("No hay suficientes inscripciones", panel.leer_aprobacion(filas))


class TestMateriasQueMasFrenan(unittest.TestCase):
    def setUp(self):
        costos = _costos(PRG115=(100, 400, 10_000), PRG215=(80, 350, 8_000), BIN115=(60, 200, 12_000))
        self.cruce = rc.cruce_costo_posicion(_materias(), costos)
        self.lista = panel.materias_que_mas_bloquean(self.cruce)

    def test_ordena_por_dependientes_y_trae_cinco(self):
        self.assertEqual(len(self.lista), 5)
        self.assertEqual([m["codigo"] for m in self.lista[:2]], ["PRG115", "PRG215"])
        self.assertEqual(self.lista[0]["dependientes"], 10)

    def test_marca_los_cuellos_de_botella(self):
        self.assertTrue(self.lista[0]["cuello"] and self.lista[1]["cuello"])

    def test_la_lectura_dice_que_parte_de_los_bloqueos_concentra(self):
        texto = panel.leer_impacto(self.lista, int(self.cruce["bloqueos"].sum()))
        self.assertIn("generan el", texto)
        self.assertIn("PRG115, PRG215 son cuello de botella", texto)
        self.assertIn("Red curricular", texto)

    def test_sin_bloqueos_no_inventa(self):
        self.assertIn("no hay bloqueos", panel.leer_impacto([], 0))


if __name__ == "__main__":
    unittest.main()
