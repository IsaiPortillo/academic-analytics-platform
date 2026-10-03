"""Pruebas de las lecturas del análisis diagnóstico — Fase 4.2.

Fijan las reglas estadísticas con casos de respuesta conocida, y que el texto
no afirme más de lo que los datos sostienen (ni prediga).

    cd backend && python -m unittest discover -s tests -v
"""

import math
import unittest

from app import indicadores_diagnostico as d


def _par(x, y, r, n):
    return {"x": x, "y": y, "r": r, "n": n}


class TestEstadistica(unittest.TestCase):
    def test_rangos_de_cohen(self):
        self.assertEqual(d.fuerza(0.05), "despreciable")
        self.assertEqual(d.fuerza(-0.14), "débil")
        self.assertEqual(d.fuerza(0.35), "moderada")
        self.assertEqual(d.fuerza(-0.74), "fuerte")

    def test_significancia_depende_de_n(self):
        # r = 0.015 con 12 000 observaciones: t ≈ 1.64 < 1.96 → no significativa.
        self.assertFalse(d.correlacion_significativa(0.015, 12_000))
        # r = 0.026 con 12 000: t ≈ 2.85 → significativa (aunque despreciable).
        self.assertTrue(d.correlacion_significativa(0.026, 12_000))
        # La misma r grande con pocos datos no alcanza.
        self.assertFalse(d.correlacion_significativa(0.4, 10))

    def test_sin_datos_no_es_significativa(self):
        self.assertFalse(d.correlacion_significativa(float("nan"), 0))
        self.assertFalse(d.correlacion_significativa(None, 100))

    def test_diferencia_de_proporciones(self):
        # 42.3 % vs 19.8 % con miles de casos: claramente significativa.
        diferencia, significativa = d.diferencia_proporciones(2814, 6654, 5206, 26312)
        self.assertAlmostEqual(diferencia, 2814 / 6654 - 5206 / 26312)
        self.assertTrue(significativa)
        # 25.5 % vs 24.6 %: no se distingue del azar (z ≈ 0.85).
        self.assertFalse(d.diferencia_proporciones(481, 1883, 2485, 10117)[1])

    def test_grupo_vacio(self):
        self.assertEqual(d.diferencia_proporciones(0, 0, 5, 10), (0.0, False))


class TestLecturaCorrelaciones(unittest.TestCase):
    def test_par_por_construccion_no_se_presenta_como_hallazgo(self):
        texto = d.leer_correlacion(_par("nota", "costo", -0.74, 30_000))
        self.assertIn("por construcción", texto)
        self.assertIn("no es un hallazgo", texto)

    def test_par_no_significativo(self):
        self.assertIn("no distinguible del azar",
                      d.leer_correlacion(_par("asistencia", "nota", 0.015, 12_000)))

    def test_par_debil_y_real_no_sugiere_causalidad(self):
        texto = d.leer_correlacion(_par("nota", "intento", -0.145, 32_966))
        self.assertIn("débil", texto)
        self.assertIn("sentido contrario", texto)
        self.assertNotIn("causa", texto)

    def test_par_sin_datos(self):
        self.assertIn("Sin datos suficientes",
                      d.leer_correlacion(_par("asistencia", "nota", math.nan, 0)))

    def test_conjunto_advierte_que_correlacion_no_es_causalidad(self):
        pares = [_par("asistencia", "nota", 0.015, 12_000), _par("nota", "intento", -0.145, 32_966),
                 _par("nota", "costo", -0.74, 32_966)]
        texto = d.interpretar_correlaciones(pares)
        self.assertIn("nota final y el número de intento", texto)  # la más clara, sin contar la de construcción
        self.assertIn("no demuestra que una cause la otra", texto)
        self.assertIn("faltar más no se asocia con sacar menos", texto)

    def test_conjunto_sin_asistencia(self):
        pares = [_par("asistencia", "nota", math.nan, 0), _par("nota", "intento", -0.13, 4_000)]
        self.assertIn("No hay asistencia registrada", d.interpretar_correlaciones(pares))


class TestLecturasDeGrupos(unittest.TestCase):
    def test_ausencias_sin_diferencia_real(self):
        texto = d.interpretar_ausencias({"cerradas": 1883, "reprobadas": 481},
                                        {"cerradas": 10117, "reprobadas": 2485}, 3)
        self.assertIn("no se distingue del azar", texto)
        self.assertIn("las ausencias no explican la reprobación", texto)

    def test_ausencias_con_diferencia_real(self):
        texto = d.interpretar_ausencias({"cerradas": 2000, "reprobadas": 1000},
                                        {"cerradas": 10000, "reprobadas": 2000}, 3)
        self.assertIn("reprueban 30.0 puntos porcentuales más", texto)

    def test_ausencias_sin_asistencia_registrada(self):
        self.assertIn("No hay asistencia registrada", d.interpretar_ausencias(None, None, 3))

    def test_segmento_apreciable(self):
        filas = [{"segmento": "Trabaja", "cerradas": 6654, "reprobadas": 2814},
                 {"segmento": "No trabaja", "cerradas": 26312, "reprobadas": 5206}]
        texto = d.interpretar_segmentos(filas, "la condición laboral")
        self.assertIn("real y apreciable", texto)
        self.assertIn("la condición laboral sí se asocia", texto)

    def test_segmento_indistinguible(self):
        filas = [{"segmento": "Vespertino", "cerradas": 11227, "reprobadas": 2777},
                 {"segmento": "Matutino", "cerradas": 10877, "reprobadas": 2612}]
        self.assertIn("el turno no explica", d.interpretar_segmentos(filas, "el turno"))

    def test_segmento_real_pero_pequeno(self):
        filas = [{"segmento": "A", "cerradas": 200_000, "reprobadas": 51_000},
                 {"segmento": "B", "cerradas": 200_000, "reprobadas": 49_000}]
        self.assertIn("pequeña", d.interpretar_segmentos(filas, "la variable"))

    def test_un_solo_grupo_no_se_compara(self):
        filas = [{"segmento": "Único", "cerradas": 100, "reprobadas": 20}]
        self.assertIn("No hay suficientes grupos", d.interpretar_segmentos(filas, "el turno"))


class TestPatron(unittest.TestCase):
    RESUMEN = {"inscripciones": 481, "estudiantes": 395, "reprobadas": 8020,
               "reprobadas_con_asistencia": 2966, "periodos_con_asistencia": 3, "periodos": 8}

    def test_describe_sin_pronosticar(self):
        texto = d.interpretar_patron(self.RESUMEN, 3, "6.00")
        self.assertIn("395 estudiantes ya presentan el patrón", texto)
        self.assertIn("no un pronóstico", texto)
        for palabra in ("predic", "probabilidad de desertar", "va a desertar"):
            self.assertNotIn(palabra, texto.lower())

    def test_advierte_cobertura_parcial_de_asistencia(self):
        self.assertIn("Solo 3 de los 8 períodos", d.interpretar_patron(self.RESUMEN, 3, "6.00"))

    def test_periodo_sin_asistencia(self):
        resumen = dict(self.RESUMEN, inscripciones=0, estudiantes=0,
                       periodos_con_asistencia=0, periodos=1)
        self.assertIn("no se puede observar", d.interpretar_patron(resumen, 3, "6.00"))


if __name__ == "__main__":
    unittest.main()
