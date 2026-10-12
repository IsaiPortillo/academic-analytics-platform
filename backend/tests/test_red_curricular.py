"""Pruebas de la red curricular y su cruce con el costo — Fase 4.3 (SCRUM-46).

No tocan la base de datos: la malla de prueba es la misma de
database/nosql/03_cargar_grafo_neo4j.py (16 materias, 16 relaciones), así que las
cifras que se fijan aquí son las que el jurado verá en pantalla.

    cd backend && python -m unittest discover -s tests -v
"""

import unittest

import pandas as pd

from app import red_curricular as rc

# (código, nombre, ciclo)
MATERIAS = [
    ("MAT115", "Matemática I", 1), ("PRG115", "Programación I", 1),
    ("ACA115", "Álgebra Vectorial y Matrices", 1), ("MAT215", "Matemática II", 2),
    ("PRG215", "Programación II", 2), ("BAD115", "Bases de Datos I", 3),
    ("PRG315", "Programación III", 3), ("MAT315", "Matemática III", 3),
    ("BAD215", "Bases de Datos II", 4), ("ADS115", "Análisis y Diseño de Sistemas I", 4),
    ("SIF115", "Sistemas de Información", 5), ("ADS215", "Análisis y Diseño de Sistemas II", 5),
    ("DWB115", "Diseño Web y Aplicaciones", 6), ("ARC115", "Arquitectura de Computadoras", 6),
    ("IAI115", "Inteligencia Artificial", 7), ("BIN115", "Inteligencia de Negocios", 8),
]
# (materia, prerrequisito)
RELACIONES = [
    ("MAT215", "MAT115"), ("PRG215", "PRG115"), ("MAT315", "MAT215"), ("PRG315", "PRG215"),
    ("BAD115", "PRG115"), ("BAD215", "BAD115"), ("ADS115", "PRG215"), ("SIF115", "ADS115"),
    ("SIF115", "BAD115"), ("ADS215", "ADS115"), ("DWB115", "PRG315"), ("ARC115", "ACA115"),
    ("IAI115", "PRG315"), ("IAI115", "MAT315"), ("BIN115", "BAD215"), ("BIN115", "SIF115"),
]


def _prerrequisitos(relaciones=RELACIONES):
    return pd.DataFrame(relaciones, columns=["codigo_materia", "codigo_prerrequisito"])


def _materias(metricas_de=None):
    """Fichas como las deja dim_materia. Las métricas son las que calcularía Neo4j;
    aquí salen de la propia red para tener una malla coherente de partida."""
    base = pd.DataFrame(MATERIAS, columns=["codigo_materia", "nombre_materia", "ciclo_plan"])
    base["area"] = "Área"
    base["en_grafo"] = True
    red = rc.construir_red(base.assign(es_cuello_botella=False), _prerrequisitos())
    calc = rc.metricas_recalculadas(red)
    for metrica in ("dependientes_directos", "dependientes_indirectos",
                    "dependientes_totales", "longitud_cascada"):
        base[metrica] = base["codigo_materia"].map(lambda c, m=metrica: calc[c][m])
    base["indice_bloqueo"] = (base["dependientes_totales"] / (len(base) - 1)).round(4)
    base["es_cuello_botella"] = base["indice_bloqueo"] >= 0.25
    return base


def _red():
    return rc.construir_red(_materias(), _prerrequisitos())


def _costos(**por_materia):
    """costos[codigo] = (reprobados, cerradas, costo)"""
    filas = [{"codigo_materia": c, "reprobados": r, "cerradas": n,
              "estudiantes_reprobados": r, "costo_reprobacion": float(costo)}
             for c, (r, n, costo) in por_materia.items()]
    return pd.DataFrame(filas, columns=["codigo_materia", "reprobados", "cerradas",
                                        "estudiantes_reprobados", "costo_reprobacion"])


class TestGrafo(unittest.TestCase):
    def test_las_flechas_van_del_prerrequisito_a_la_materia(self):
        red = _red()
        self.assertTrue(red.has_edge("PRG115", "PRG215"))
        self.assertFalse(red.has_edge("PRG215", "PRG115"))
        self.assertEqual((len(red), red.number_of_edges()), (16, 16))

    def test_una_relacion_hacia_una_materia_sin_ficha_se_ignora(self):
        red = rc.construir_red(_materias(), _prerrequisitos(RELACIONES + [("ZZZ999", "PRG115")]))
        self.assertNotIn("ZZZ999", red)
        self.assertEqual(red.number_of_edges(), 16)

    def test_dependientes_de_programacion_i(self):
        # Reprobar PRG115 deja sin poder cursar a 10 de las otras 15 materias.
        m = rc.metricas_recalculadas(_red())["PRG115"]
        self.assertEqual(m["dependientes_directos"], 2)       # PRG215 y BAD115
        self.assertEqual(m["dependientes_indirectos"], 8)
        self.assertEqual(m["dependientes_totales"], 10)
        self.assertEqual(m["longitud_cascada"], 4)            # PRG115→PRG215→ADS115→SIF115→BIN115

    def test_materia_terminal_no_bloquea_nada(self):
        m = rc.metricas_recalculadas(_red())["BIN115"]
        self.assertEqual((m["dependientes_totales"], m["longitud_cascada"]), (0, 0))

    def test_las_metricas_guardadas_coinciden_con_las_recalculadas(self):
        self.assertEqual(rc.discrepancias(_red()), [])

    def test_una_metrica_alterada_en_el_dw_se_detecta(self):
        materias = _materias()
        materias.loc[materias["codigo_materia"] == "PRG115", "dependientes_totales"] = 7
        problemas = rc.discrepancias(rc.construir_red(materias, _prerrequisitos()))
        self.assertEqual(len(problemas), 1)
        self.assertIn("PRG115.dependientes_totales: guardado 7, recalculado 10", problemas[0])

    def test_cadena_mas_larga(self):
        self.assertEqual(rc.cadena_mas_larga(_red()),
                         ["PRG115", "PRG215", "ADS115", "SIF115", "BIN115"])

    def test_sin_relaciones_no_hay_cadena(self):
        self.assertEqual(rc.cadena_mas_larga(rc.construir_red(_materias(), _prerrequisitos([]))), [])


class TestDisposicion(unittest.TestCase):
    def setUp(self):
        self.d = rc.disponer(_red())

    def test_toda_materia_tiene_posicion_y_las_columnas_son_los_ciclos(self):
        self.assertEqual(len(self.d["nodos"]), 16)
        self.assertEqual(self.d["criterio_columnas"], "ciclo")
        self.assertEqual([c["etiqueta"] for c in self.d["columnas"]], [f"Ciclo {i}" for i in range(1, 9)])

    def test_ningun_nodo_se_superpone_con_otro(self):
        posiciones = [(n["x"], n["y"]) for n in self.d["nodos"].values()]
        self.assertEqual(len(posiciones), len(set(posiciones)))
        for (x1, y1), (x2, y2) in ((a, b) for i, a in enumerate(posiciones) for b in posiciones[i + 1:]):
            if x1 == x2:
                self.assertGreaterEqual(abs(y1 - y2), rc.ALTO_NODO + 1)

    def test_toda_relacion_avanza_hacia_la_derecha(self):
        for a in self.d["aristas"]:
            self.assertLess(self.d["nodos"][a["origen"]]["x"], self.d["nodos"][a["destino"]]["x"])
        self.assertEqual(len(self.d["aristas"]), 16)

    def test_todo_cabe_en_el_lienzo(self):
        for n in self.d["nodos"].values():
            self.assertLessEqual(n["x"] + rc.ANCHO_NODO, self.d["ancho"])
            self.assertLessEqual(n["y"] + rc.ALTO_NODO, self.d["alto"])

    def test_es_determinista(self):
        self.assertEqual(self.d, rc.disponer(_red()))

    def test_si_alguna_relacion_no_avanza_de_ciclo_se_usa_la_profundidad(self):
        materias = _materias()
        materias.loc[materias["codigo_materia"] == "PRG115", "ciclo_plan"] = 9  # después de sus dependientes
        d = rc.disponer(rc.construir_red(materias, _prerrequisitos()))
        self.assertEqual(d["criterio_columnas"], "profundidad")
        self.assertTrue(d["columnas"][0]["etiqueta"].startswith("Nivel"))
        for a in d["aristas"]:
            self.assertLess(d["nodos"][a["origen"]]["x"], d["nodos"][a["destino"]]["x"])

    def test_red_vacia(self):
        self.assertEqual(rc.disponer(rc.construir_red(_materias().iloc[0:0], _prerrequisitos([])))["nodos"], {})


class TestCruce(unittest.TestCase):
    def setUp(self):
        # PRG115 (cuello de botella, 10 dependientes) y MAT115 (bloquea 3) cuestan lo mismo;
        # BIN115 es terminal y la más cara; ACA115 casi no cuesta.
        self.costos = _costos(PRG115=(100, 400, 10_000), BIN115=(60, 200, 12_000),
                              MAT115=(40, 300, 1_000), ACA115=(2, 100, 100))
        self.cruce = rc.cruce_costo_posicion(_materias(), self.costos).set_index("codigo_materia")

    def test_bloqueos_son_reprobados_por_dependientes(self):
        self.assertEqual(self.cruce.loc["PRG115", "bloqueos"], 100 * 10)
        self.assertEqual(self.cruce.loc["BIN115", "bloqueos"], 0)  # terminal: no bloquea a nadie

    def test_las_materias_sin_inscripciones_siguen_en_el_cruce_con_costo_cero(self):
        self.assertEqual(len(self.cruce), 16)
        self.assertEqual(self.cruce.loc["BAD215", "costo_reprobacion"], 0)

    def test_los_porcentajes_suman_cien(self):
        self.assertAlmostEqual(self.cruce["pct_costo"].sum(), 1.0)
        self.assertAlmostEqual(self.cruce["pct_bloqueos"].sum(), 1.0)

    def test_tipos_cruzan_cuello_de_botella_y_costo(self):
        t = self.cruce["tipo"]
        self.assertEqual(t["PRG115"], "propaga")        # cuello de botella y costo alto
        self.assertEqual(t["BIN115"], "contenido")      # caro, pero no bloquea nada
        self.assertEqual(t["ACA115"], "sin_hallazgo")   # barata y poco estructural

    def test_cuello_de_botella_barato_es_estructural(self):
        costos = _costos(PRG115=(1, 400, 100), BIN115=(60, 200, 12_000), MAT115=(40, 300, 9_000))
        cruce = rc.cruce_costo_posicion(_materias(), costos).set_index("codigo_materia")
        self.assertEqual(cruce.loc["PRG115", "tipo"], "estructural")

    def test_sin_costos_todo_queda_sin_hallazgo_y_no_falla(self):
        cruce = rc.cruce_costo_posicion(_materias(), _costos())
        self.assertEqual(set(cruce["tipo"]) - {"estructural"}, {"sin_hallazgo"})
        self.assertEqual(cruce["pct_costo"].sum(), 0)


class TestLectura(unittest.TestCase):
    def setUp(self):
        self.red = _red()
        self.materias = _materias()
        costos = _costos(PRG115=(100, 400, 10_000), BIN115=(60, 200, 12_000), MAT115=(40, 300, 1_000))
        self.cruce = rc.cruce_costo_posicion(self.materias, costos)

    def test_estructura_nombra_entradas_terminales_y_cadena(self):
        texto = rc.leer_estructura(self.red)
        self.assertIn("16 materias", texto)
        self.assertIn("16 relaciones", texto)
        self.assertIn("PRG115 → PRG215 → ADS115 → SIF115 → BIN115", texto)

    def test_cuellos_dicen_cuantas_materias_bloquea_la_mayor(self):
        texto = rc.leer_cuellos(self.red, self.materias)
        self.assertIn("Programación I (PRG115) es la mayor", texto)
        self.assertIn("2 dependientes directos y 8 indirectos, 10 en total", texto)

    def test_el_cruce_explica_por_que_el_costo_se_propaga(self):
        texto = rc.leer_cruce(self.cruce, self.red)
        # La más cara (BIN115) es terminal: su costo no se propaga.
        self.assertIn("Inteligencia de Negocios (BIN115) es la materia con más costo", texto)
        self.assertIn("no se propaga al resto del plan", texto)
        # La que más bloqueos genera no es la más cara.
        self.assertIn("La que más bloqueos genera es Programación I (PRG115)", texto)

    def test_cuando_la_mas_cara_es_cuello_de_botella_lo_dice(self):
        costos = _costos(PRG115=(100, 400, 20_000), BIN115=(60, 200, 12_000))
        cruce = rc.cruce_costo_posicion(self.materias, costos)
        texto = rc.leer_cruce(cruce, self.red)
        self.assertIn("Además bloquea a 10 materias", texto)
        self.assertIn("coinciden el costo directo y el efecto sobre la malla", texto)

    def test_sin_costo_lo_dice_en_vez_de_inventar(self):
        cruce = rc.cruce_costo_posicion(self.materias, _costos())
        self.assertIn("No hubo costo de reprobación", rc.leer_cruce(cruce, self.red))

    def test_sin_red_las_tres_lecturas_avisan_como_cargarla(self):
        vacia = rc.construir_red(self.materias, _prerrequisitos([]))
        for texto in (rc.leer_estructura(vacia), rc.leer_cuellos(vacia, self.materias),
                      rc.leer_cruce(self.cruce, vacia)):
            self.assertEqual(texto, rc.SIN_RED)

    def test_resumen(self):
        r = rc.resumen(self.red, self.cruce)
        self.assertEqual((r["materias"], r["relaciones"], r["cadena"]), (16, 16, 5))
        self.assertGreater(r["cuellos"], 0)
        self.assertTrue(0 <= r["pct_costo_cuellos"] <= 1)


class TestDispersion(unittest.TestCase):
    def setUp(self):
        costos = _costos(PRG115=(100, 400, 10_000), BIN115=(60, 200, 12_000),
                         MAT115=(40, 300, 1_000), PRG215=(80, 350, 8_000))
        self.cruce = rc.cruce_costo_posicion(_materias(), costos)
        self.g = rc.dispersion(self.cruce)

    def test_hay_un_punto_por_materia_dentro_del_area(self):
        a = self.g["area"]
        self.assertEqual(len(self.g["puntos"]), 16)
        for p in self.g["puntos"]:
            self.assertTrue(a["x1"] <= p["cx"] <= a["x2"] and a["y1"] <= p["cy"] <= a["y2"], p["codigo"])

    def test_a_mas_costo_mas_a_la_derecha_y_a_mas_dependientes_mas_arriba(self):
        p = {x["codigo"]: x for x in self.g["puntos"]}
        self.assertGreater(p["BIN115"]["cx"], p["MAT115"]["cx"])   # 12 000 contra 1 000
        self.assertLess(p["PRG115"]["cy"], p["BIN115"]["cy"])      # 10 dependientes contra 0

    def test_solo_llevan_rotulo_las_materias_con_costo_o_hallazgo(self):
        con = {x["codigo"] for x in self.g["puntos"] if x["con_rotulo"]}
        self.assertTrue({"PRG115", "BIN115", "MAT115", "PRG215"} <= con)
        self.assertNotIn("ARC115", con)

    def test_los_rotulos_no_se_pisan(self):
        rotulos = [(p["cx"], p["ty"]) for p in self.g["puntos"] if p["con_rotulo"]]
        for i, (x1, y1) in enumerate(rotulos):
            for x2, y2 in rotulos[i + 1:]:
                self.assertFalse(abs(x1 - x2) < 46 and abs(y1 - y2) < 11, ((x1, y1), (x2, y2)))

    def test_las_guias_dividen_el_plano(self):
        self.assertIsNotNone(self.g["x_mediana"])
        self.assertIsNotNone(self.g["y_cuello"])
        self.assertAlmostEqual(self.g["umbral_dependientes"], 0.25 * 15)

    def test_sin_costos_no_falla_ni_traza_mediana(self):
        g = rc.dispersion(rc.cruce_costo_posicion(_materias(), _costos()))
        self.assertIsNone(g["x_mediana"])
        self.assertEqual(len(g["puntos"]), 16)


if __name__ == "__main__":
    unittest.main()
