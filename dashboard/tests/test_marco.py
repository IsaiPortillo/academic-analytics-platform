"""Marco visual del dashboard: tema, barra superior y dibujo de la red. Sin Streamlit.

    python -m unittest discover -s dashboard/tests -v
"""

import re
import unittest

from dashboard import red, shell, tema


class TestTema(unittest.TestCase):
    def test_las_dos_paletas_traen_los_mismos_tokens(self):
        self.assertEqual(set(tema.PALETAS["claro"]), set(tema.PALETAS["oscuro"]))

    def test_la_marca_es_la_de_la_app_web(self):
        # backend/app/static/src/input.css: --color-brand claro #8b0000 y oscuro #c73838
        self.assertEqual((tema.PALETAS["claro"]["brand"], tema.PALETAS["oscuro"]["brand"]), ("#8b0000", "#c73838"))

    def test_mezclar_extremos_y_punto_medio(self):
        self.assertEqual(tema.mezclar("#ff0000", "#000000", 1.0), "#ff0000")
        self.assertEqual(tema.mezclar("#ff0000", "#000000", 0.0), "#000000")
        self.assertEqual(tema.mezclar("#ffffff", "#000000", 0.5), "#808080")

    def test_los_tintes_resueltos_son_hex_validos(self):
        for nombre in tema.PALETAS:
            p = tema.paleta(nombre)
            for clave in ("danger_fill", "warning_fill", "success_fill", "neutral_fill"):
                self.assertRegex(p[clave], r"^#[0-9a-f]{6}$", (nombre, clave))

    def test_paleta_desconocida_cae_en_claro(self):
        self.assertEqual(tema.paleta("otra")["bg"], tema.PALETAS["claro"]["bg"])

    def test_el_css_usa_la_tipografia_y_los_colores_de_la_paleta(self):
        css = tema.css(tema.paleta("oscuro"))
        self.assertIn("Plus+Jakarta+Sans", css)
        self.assertIn("--mn-bg: #0b1220", css)
        self.assertIn("--mn-brand: #c73838", css)

    def test_el_css_no_contiene_llaves_sin_resolver(self):
        self.assertNotIn("{p[", tema.css(tema.paleta("claro")))
        self.assertEqual(tema.css(tema.paleta("claro")).count("{"), tema.css(tema.paleta("claro")).count("}"))


class TestMarco(unittest.TestCase):
    def test_usuario_de_las_cabeceras_decodifica_tildes(self):
        u = shell.usuario_de_cabeceras({"X-Minerva-Usuario": "Jos%C3%A9%20%C3%91and%C3%BA", "X-Minerva-Rol": "Coordinador"})
        self.assertEqual(u, {"nombre": "José Ñandú", "rol": "Coordinador"})

    def test_sin_cabeceras_no_hay_usuario(self):
        self.assertIsNone(shell.usuario_de_cabeceras({}))
        self.assertIsNone(shell.usuario_de_cabeceras({"X-Minerva-Usuario": None}))

    def test_la_barra_escapa_html_en_el_nombre(self):
        html = shell.barra_superior_html({"nombre": "<script>alert(1)</script>", "rol": "Coordinador"}, "/", "x")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_sin_url_de_la_app_no_hay_enlaces_rotos(self):
        self.assertEqual(shell.enlaces_html(""), "")
        self.assertNotIn("Salir", shell.barra_superior_html(None, "", "x"))

    def test_con_url_de_la_app_vuelve_al_sistema_y_sale(self):
        self.assertIn('href="/vista-ejecutiva"', shell.enlaces_html("/"))
        self.assertIn('href="/logout"', shell.barra_superior_html(None, "/", "x"))

    def test_la_lectura_escapa_el_texto(self):
        self.assertIn("&lt;b&gt;", shell.lectura_html("<b>hola</b>"))


def _disposicion():
    return {
        "ancho": 400, "alto": 160,
        "columnas": [{"etiqueta": "Ciclo 1", "x": 20}, {"etiqueta": "Ciclo 2", "x": 216}],
        "nodos": {"A": {"x": 20, "y": 48}, "B": {"x": 216, "y": 48}, "C": {"x": 216, "y": 120}},
        "aristas": [{"origen": "A", "destino": "B", "d": "M156,82 C186,82 186,82 216,82"}],
    }


def _info():
    base = {"nombre": "Materia", "cuello": False, "calor": 0.5, "totales": 1, "costo": "$1,000"}
    return {"A": dict(base, nombre="Programación I", cuello=True), "B": dict(base), "C": dict(base, calor=0.0, totales=0)}


class TestRed(unittest.TestCase):
    def setUp(self):
        self.p = tema.paleta("claro")

    def test_estados(self):
        self.assertEqual(red.estados("A", {"B"}, set(), "A"), "seleccion")
        self.assertEqual(red.estados("B", {"B"}, set(), "A"), "dependiente")
        self.assertEqual(red.estados("B", set(), {"B"}, "A"), "prerrequisito")
        self.assertEqual(red.estados("C", {"B"}, set(), "A"), "atenuado")
        self.assertEqual(red.estados("C", set(), set(), None), "normal")

    def test_dibuja_cada_materia_y_cada_relacion(self):
        svg = red.svg_red(_disposicion(), _info(), "A", {"B"}, set(), self.p)
        for codigo in "ABC":
            self.assertIn(f">{codigo}</text>", svg)
        self.assertEqual(svg.count("<path "), 1)
        self.assertTrue(svg.startswith("<svg") and svg.endswith("</svg>"))

    def test_los_estados_cambian_el_color_y_la_materia_sin_relacion_se_atenua(self):
        svg = red.svg_red(_disposicion(), _info(), "A", {"B"}, set(), self.p)
        self.assertIn(self.p["danger_fill"], svg)                  # B se bloquea
        self.assertEqual(len(re.findall(r'opacity="0\.38"', svg)), 1)   # C, sin relación
        self.assertIn(f'stroke="{self.p["brand"]}" stroke-width="3.5"', svg)   # A elegida

    def test_sin_seleccion_nada_se_atenua(self):
        svg = red.svg_red(_disposicion(), _info(), None, set(), set(), self.p)
        self.assertNotIn('opacity="0.38"', svg)

    def test_el_nombre_se_escapa_y_se_recorta(self):
        info = _info()
        info["B"]["nombre"] = "<img src=x onerror=1> con un nombre larguísimo"
        svg = red.svg_red(_disposicion(), info, None, set(), set(), self.p)
        self.assertNotIn("<img", svg)
        self.assertIn("…", svg)

    def test_texto_de_detalle(self):
        n = {"totales": 2, "directos": 1, "indirectos": 1, "pct_plan": "13.3 %", "costo": "$1,000", "pct_costo": "5.0 %",
             "reprobados": 10, "tasa": "20.0 %", "bloqueos": 20, "tipo_texto": "Costo contenido"}
        a, b, c = red.texto_detalle(n, ["B", "C"], [], [])
        self.assertIn("deja sin poder cursar a 2 materias (1 directa y 1 en cascada, 13.3 % del plan): B, C", a)
        self.assertEqual(b, "No exige ninguna materia previa.")
        self.assertIn("20 bloqueos generados. Costo contenido.", c)

    def test_materia_terminal(self):
        n = {"totales": 0, "directos": 0, "indirectos": 0, "pct_plan": "0.0 %", "costo": "$0", "pct_costo": "0.0 %",
             "reprobados": 0, "tasa": "—", "bloqueos": 0, "tipo_texto": "Sin hallazgo"}
        self.assertIn("No es prerrequisito de ninguna materia", red.texto_detalle(n, [], ["A"], ["A"])[0])


if __name__ == "__main__":
    unittest.main()
