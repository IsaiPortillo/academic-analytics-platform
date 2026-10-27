"""Pruebas del cubo OLAP: catálogo, SQL y lectura. No tocan la base de datos.

    cd backend && python -m unittest discover -s tests -v
"""

import unittest

import pandas as pd

from app import olap


class TestValidacion(unittest.TestCase):
    def test_solo_claves_del_catalogo_en_el_orden_pedido(self):
        self.assertEqual(olap.validar_dimensiones(["ciclo", "periodo"]), ["ciclo", "periodo"])

    def test_claves_desconocidas_y_repetidas_se_descartan(self):
        self.assertEqual(olap.validar_dimensiones(["x", "periodo", "periodo", "", None, "ciclo"]),
                         ["periodo", "ciclo"])

    def test_maximo_tres_dimensiones(self):
        self.assertEqual(len(olap.validar_dimensiones(list(olap.DIMENSIONES))), olap.MAX_DIMENSIONES)

    def test_modo_desconocido_es_rollup(self):
        self.assertEqual(olap.validar_modo("DROP TABLE"), "rollup")
        self.assertEqual(olap.validar_modo(None), "rollup")
        self.assertEqual(olap.validar_modo("cube"), "cube")


class TestSql(unittest.TestCase):
    DESDE = "FROM dw_academico.fact_inscripcion f WHERE 1 = 1"

    def test_rollup_agrupa_en_el_orden_elegido(self):
        sql = olap.construir_sql(["periodo", "ciclo"], "rollup", self.DESDE)
        self.assertIn("GROUP BY ROLLUP (p.codigo_periodo, m.ciclo_plan)", sql)
        self.assertIn("GROUPING(p.codigo_periodo) AS g1", sql)
        self.assertIn("ORDER BY g1, d1, g2, d2", sql)

    def test_cube_agrupa_todas_las_combinaciones(self):
        self.assertIn("GROUP BY CUBE (m.area, f.turno)", olap.construir_sql(["area", "turno"], "cube", self.DESDE))

    def test_el_texto_del_usuario_nunca_llega_al_sql(self):
        sql = olap.construir_sql(["periodo; DROP TABLE x", "ciclo"], "cube; DROP", self.DESDE)
        self.assertNotIn("DROP", sql)
        self.assertIn("ROLLUP (m.ciclo_plan)", sql)  # la clave inválida se descartó; el modo cayó a rollup

    def test_sin_dimensiones_no_hay_cubo(self):
        with self.assertRaises(ValueError):
            olap.construir_sql(["nada"], "rollup", self.DESDE)

    def test_trae_una_fila_mas_que_el_limite_para_saber_si_se_trunco(self):
        self.assertIn(f"LIMIT {olap.LIMITE_FILAS + 1}", olap.construir_sql(["periodo"], "rollup", self.DESDE))

    def test_incluye_las_cinco_medidas(self):
        sql = olap.construir_sql(["periodo"], "rollup", self.DESDE)
        for nombre, _, _ in olap.MEDIDAS:
            self.assertIn(f"AS {nombre}", sql)


def _resultado():
    """Lo que devolvería ROLLUP(periodo, ciclo): detalle, subtotal por periodo, total."""
    base = {"cerradas": 0, "reprobados": 0, "tasa_reprobacion": None, "nota_promedio": None,
            "costo_reprobacion": 0.0}
    filas = [
        dict(base, d1="2024-I", g1=0, d2=1, g2=0, cerradas=400, reprobados=100, tasa_reprobacion=0.25,
             nota_promedio=6.4, costo_reprobacion=10_000.0),
        dict(base, d1="2024-I", g1=0, d2=2, g2=0, cerradas=300, reprobados=36, tasa_reprobacion=0.12,
             nota_promedio=7.1, costo_reprobacion=3_600.0),
        dict(base, d1="2024-I", g1=0, d2=None, g2=1, cerradas=700, reprobados=136, tasa_reprobacion=0.1943,
             nota_promedio=6.7, costo_reprobacion=13_600.0),
        dict(base, d1=None, g1=1, d2=None, g2=1, cerradas=700, reprobados=136, tasa_reprobacion=0.1943,
             nota_promedio=6.7, costo_reprobacion=13_600.0),
    ]
    return pd.DataFrame(filas)


class TestFilas(unittest.TestCase):
    def setUp(self):
        self.filas = olap.preparar_filas(_resultado(), ["periodo", "ciclo"])

    def test_los_niveles_distinguen_detalle_subtotal_y_total(self):
        self.assertEqual([f["nivel"] for f in self.filas], [0, 0, 1, 2])
        self.assertEqual([f["es_total"] for f in self.filas], [False, False, False, True])

    def test_la_dimension_agrupada_se_rotula_todos(self):
        self.assertEqual(self.filas[0]["celdas"], ["2024-I", "1"])    # el ciclo llega como float 1.0
        self.assertEqual(self.filas[2]["celdas"], ["2024-I", "Todos"])
        self.assertEqual(self.filas[3]["celdas"], ["Todos", "Todos"])

    def test_textos_de_las_medidas(self):
        f = self.filas[0]
        self.assertEqual((f["tasa_texto"], f["nota_texto"], f["costo_texto"]), ("25.0 %", "6.40", "$10,000"))

    def test_un_valor_nulo_de_la_dimension_es_sin_dato_no_todos(self):
        df = _resultado().iloc[[0]].copy()
        df["d1"] = None
        self.assertEqual(olap.preparar_filas(df, ["periodo", "ciclo"])[0]["celdas"][0], "Sin dato")

    def test_tasa_nula_no_rompe(self):
        df = _resultado().iloc[[0]].copy()
        df["tasa_reprobacion"] = None
        df["nota_promedio"] = None
        f = olap.preparar_filas(df, ["periodo", "ciclo"])[0]
        self.assertEqual((f["tasa_texto"], f["nota_texto"]), ("—", "—"))


class TestLectura(unittest.TestCase):
    def test_describe_el_cubo_y_compara_celdas_con_base_suficiente(self):
        filas = olap.preparar_filas(_resultado(), ["periodo", "ciclo"])
        texto = olap.leer_cubo(filas, ["periodo", "ciclo"], "rollup")
        self.assertIn("2 combinaciones y 1 subtotal", texto)
        self.assertIn("tasa de reprobación total: 19.4 %", texto)
        self.assertIn("Más alta: 2024-I · 1 (25.0 %); más baja: 2024-I · 2 (12.0 %)", texto)

    def test_si_la_diferencia_es_minima_dice_que_ninguna_dimension_separa(self):
        df = _resultado()
        df.loc[1, ["reprobados", "tasa_reprobacion"]] = [76, 0.2533]
        texto = olap.leer_cubo(olap.preparar_filas(df, ["periodo", "ciclo"]), ["periodo", "ciclo"], "rollup")
        self.assertIn("Sin diferencias apreciables", texto)

    def test_celdas_con_pocas_inscripciones_no_se_comparan(self):
        df = _resultado()
        df.loc[0, "cerradas"] = 10
        texto = olap.leer_cubo(olap.preparar_filas(df, ["periodo", "ciclo"]), ["periodo", "ciclo"], "rollup")
        self.assertNotIn("Más alta", texto)

    def test_sin_filas(self):
        self.assertIn("Sin resultados", olap.leer_cubo([], ["periodo"], "rollup"))


if __name__ == "__main__":
    unittest.main()
