"""Pruebas de los KPIs y su interpretación — Fase 4.1.

No tocan la base de datos: fijan las definiciones de cada indicador y que el
texto diga lo que los números dicen, incluidos los casos sin datos.

    cd backend && python -m unittest discover -s tests -v
"""

import unittest

import pandas as pd

from app import indicadores as ind


def _totales(**cambios):
    base = {
        "costo_reprobacion": 10_000.0, "costo_cerradas": 40_000.0, "costo_repeticion": 3_000.0,
        "cerradas": 400, "reprobadas": 100, "cerradas_repeticion": 40, "retiradas": 25,
        "estudiantes_reprobados": 80, "estudiantes_evaluados": 150,
    }
    base.update(cambios)
    return base


class TestDefiniciones(unittest.TestCase):
    def test_cuatro_kpis(self):
        i = ind.calcular(_totales())
        self.assertEqual(i.costo_reprobacion, 10_000.0)
        self.assertEqual(i.costo_por_estudiante, 125.0)      # 10 000 / 80 que reprobaron
        self.assertEqual(i.tasa_reprobacion, 0.25)           # 100 / 400 cerradas
        self.assertEqual(i.proporcion_repeticion, 0.30)      # 3 000 / 10 000

    def test_sin_datos_no_divide_entre_cero(self):
        i = ind.calcular(_totales(costo_reprobacion=0, costo_cerradas=0, costo_repeticion=0,
                                  cerradas=0, reprobadas=0, cerradas_repeticion=0,
                                  estudiantes_reprobados=0, estudiantes_evaluados=0))
        self.assertIsNone(i.tasa_reprobacion)
        self.assertIsNone(i.costo_por_estudiante)
        self.assertIsNone(i.proporcion_repeticion)
        for texto in (ind.interpretar_costo(i), ind.interpretar_tasa(i),
                      ind.interpretar_costo_por_estudiante(i), ind.interpretar_repeticion(i)):
            self.assertEqual(texto, ind.SIN_DATOS)

    def test_nulos_de_sql_se_tratan_como_cero(self):
        i = ind.calcular(_totales(costo_repeticion=None))
        self.assertEqual(i.proporcion_repeticion, 0.0)


class TestInterpretaciones(unittest.TestCase):
    def test_costo_dice_proporcion_de_lo_invertido(self):
        texto = ind.interpretar_costo(ind.calcular(_totales()))
        self.assertIn("100 materias reprobadas", texto)
        self.assertIn("25.0 %", texto)  # 10 000 de 40 000

    def test_costo_compara_contra_periodo_anterior(self):
        actual = ind.calcular(_totales())
        previo = ind.calcular(_totales(costo_reprobacion=8_000.0))
        self.assertIn("25.0 % más que en 2024-I", ind.interpretar_costo(actual, previo, "2024-I"))

    def test_tasa_en_lenguaje_llano_y_variacion_en_puntos(self):
        actual = ind.calcular(_totales())
        previo = ind.calcular(_totales(reprobadas=80))  # 20 %
        texto = ind.interpretar_tasa(actual, previo, "2024-I")
        self.assertIn("1 de cada 4", texto)
        self.assertIn("Sube 5.0 pp frente a 2024-I", texto)

    def test_repitentes_que_reprueban_mas(self):
        # 30 % del costo con 10 % de la matrícula.
        self.assertIn("reprueban más que el resto", ind.interpretar_repeticion(ind.calcular(_totales())))

    def test_repitentes_en_proporcion_similar(self):
        texto = ind.interpretar_repeticion(ind.calcular(_totales(cerradas_repeticion=120)))
        self.assertIn("en proporción similar", texto)  # 30 % del costo con 30 % de la matrícula

    def test_ranking_menciona_cuellos_de_botella(self):
        ranking = pd.DataFrame({
            "codigo_materia": ["MAT315", "PRG115"],
            "nombre_materia": ["Matemática III", "Programación I"],
            "reprobados": [120, 90], "tasa_reprobacion": [0.28, 0.24],
            "costo_reprobacion": [12_000.0, 9_000.0],
            "es_cuello_botella": [False, True], "dependientes_totales": [1, 10],
        })
        texto = ind.interpretar_ranking(ranking, 30_000.0)
        self.assertIn("70.0 %", texto)          # 21 000 de 30 000
        self.assertIn("MAT315 encabeza", texto)
        self.assertIn("PRG115 es cuello de botella", texto)

    def test_ranking_sin_cuellos_no_afirma_lo_que_no_es(self):
        ranking = pd.DataFrame({
            "codigo_materia": ["MAT315"], "nombre_materia": ["Matemática III"],
            "reprobados": [120], "tasa_reprobacion": [0.28], "costo_reprobacion": [12_000.0],
            "es_cuello_botella": [False], "dependientes_totales": [1],
        })
        self.assertNotIn("cuello de botella", ind.interpretar_ranking(ranking, 12_000.0))


if __name__ == "__main__":
    unittest.main()


class TestTarjetasCompartidas(unittest.TestCase):
    """SCRUM-44: la web (FastAPI) y la app Streamlit muestran los mismos cinco
    indicadores a partir de estas tarjetas, así que sus definiciones se fijan aquí."""

    def setUp(self):
        self.actual = ind.calcular(_totales())
        self.previo = ind.calcular(_totales(costo_reprobacion=8_000.0, costo_repeticion=2_000.0))
        self.tarjetas = ind.tarjetas(self.actual, self.previo, "2024-I")

    def test_son_los_cinco_kpis_y_en_este_orden(self):
        self.assertEqual(
            [t.etiqueta for t in self.tarjetas],
            ["Costo de reprobación", "Costo por estudiante que reprobó",
             "Tasa de reprobación", "Tasa de retiro", "Costo atribuible a repetición"],
        )

    def test_cada_indicador_trae_definicion_e_interpretacion(self):
        for t in self.tarjetas:
            self.assertTrue(t.ayuda, f"{t.etiqueta} sin definición")
            self.assertTrue(t.texto, f"{t.etiqueta} sin interpretación")

    def test_valores_formateados(self):
        self.assertEqual([t.valor for t in self.tarjetas],
                         ["$10,000", "$125", "25.0 %", "5.9 %", "30.0 %"])

    def test_la_interpretacion_es_la_misma_que_las_funciones_individuales(self):
        self.assertEqual(self.tarjetas[0].texto, ind.interpretar_costo(self.actual, self.previo, "2024-I"))
        self.assertEqual(self.tarjetas[2].texto, ind.interpretar_tasa(self.actual, self.previo, "2024-I"))
        self.assertEqual(self.tarjetas[3].texto, ind.interpretar_retiro(self.actual, self.previo, "2024-I"))

    def test_cifra_actual_y_previa_para_la_variacion(self):
        costo = self.tarjetas[0]
        self.assertEqual((costo.actual, costo.previo), (10_000.0, 8_000.0))
        self.assertEqual(ind.formatear_cambio(costo.actual - costo.previo, costo.formato), "$2,000")
        tasa = self.tarjetas[2]
        self.assertEqual(tasa.formato, "puntos")
        self.assertEqual(ind.formatear_cambio(0.006, tasa.formato), "0.6 pp")

    def test_sin_periodo_previo_no_hay_cifra_previa(self):
        sin_previo = ind.tarjetas(self.actual, None, None)
        self.assertTrue(all(t.previo is None for t in sin_previo))

    def test_sin_datos_las_tarjetas_no_fallan(self):
        vacio = ind.calcular(_totales(costo_reprobacion=0, costo_cerradas=0, costo_repeticion=0,
                                      cerradas=0, reprobadas=0, cerradas_repeticion=0,
                                      retiradas=0, estudiantes_reprobados=0,
                                      estudiantes_evaluados=0))
        tarjetas = ind.tarjetas(vacio, None, None)
        self.assertEqual([t.valor for t in tarjetas], ["$0.00", "—", "—", "—", "—"])
        self.assertTrue(all(t.texto for t in tarjetas), "toda tarjeta explica por qué no hay cifra")
        # Los cuatro que dependen de la nota final comparten el mismo aviso; el retiro
        # tiene el suyo porque su denominador es otro (incluye las retiradas).
        self.assertTrue(all(t.texto == ind.SIN_DATOS for i, t in enumerate(tarjetas) if i != 3))

    def test_hay_retiros_pero_ninguna_cerrada(self):
        """Caso real al filtrar un período en curso: nadie tiene nota final todavía,
        pero algunos ya se retiraron. El retiro es el único indicador que puede
        calcularse, y debe hacerlo en vez de decir que no hay datos."""
        solo_retiros = ind.calcular(_totales(costo_reprobacion=0, costo_cerradas=0,
                                             costo_repeticion=0, cerradas=0, reprobadas=0,
                                             cerradas_repeticion=0, retiradas=25,
                                             estudiantes_reprobados=0, estudiantes_evaluados=0))
        self.assertEqual(solo_retiros.tasa_retiro, 1.0)
        self.assertEqual(ind.tarjetas(solo_retiros, None, None)[3].valor, "100.0 %")


class TestInterpretarEvolucion(unittest.TestCase):
    def _evolucion(self, costos):
        return pd.DataFrame({
            "codigo_periodo": [f"2025-{i}" for i in range(len(costos))],
            "costo_reprobacion": costos,
        })

    def test_nombra_el_periodo_mas_caro_y_el_mas_barato(self):
        texto = ind.interpretar_evolucion(self._evolucion([8_000.0, 10_000.0, 9_000.0]))
        self.assertIn("2025-1 ($10,000)", texto)
        self.assertIn("2025-0 ($8,000)", texto)

    def test_sin_filas_o_sin_costo_no_hay_texto(self):
        self.assertIsNone(ind.interpretar_evolucion(self._evolucion([])))
        self.assertIsNone(ind.interpretar_evolucion(self._evolucion([0.0, 0.0])))


class TestConexionInyectada(unittest.TestCase):
    """dw.configurar (SCRUM-44): la app Streamlit fija su propia conexión sin
    cargar la configuración del backend."""

    def tearDown(self):
        from app import dw
        dw._engine = None
        dw._url_inyectada = None

    def test_configurar_fija_la_url_del_engine(self):
        from app import dw
        dw.configurar("postgresql+psycopg2://rol_dashboard:x@localhost:5432/academico_db")
        motor = dw.engine()
        self.assertEqual(motor.url.username, "rol_dashboard")
        self.assertEqual(motor.url.database, "academico_db")

    def test_reconfigurar_descarta_el_engine_anterior(self):
        from app import dw
        dw.configurar("postgresql+psycopg2://a:x@localhost/uno")
        primero = dw.engine()
        dw.configurar("postgresql+psycopg2://b:x@localhost/dos")
        self.assertIsNot(dw.engine(), primero)
        self.assertEqual(dw.engine().url.username, "b")
