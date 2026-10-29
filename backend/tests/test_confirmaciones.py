"""Las confirmaciones se hacen con el diálogo de la aplicación, no con el del navegador.

    cd backend && python -m unittest discover -s tests -v
"""

import re
import unittest
from pathlib import Path

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"


def _plantillas():
    return sorted((RAIZ_APP / "templates").rglob("*.html"))


class TestConfirmaciones(unittest.TestCase):
    def test_ninguna_plantilla_usa_el_confirm_del_navegador(self):
        for ruta in _plantillas():
            texto = ruta.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"\bconfirm\(", f"{ruta.name}: usa confirm() del navegador")
            self.assertNotRegex(texto, r"\bonsubmit\s*=", f"{ruta.name}: usa onsubmit en línea")

    def test_el_javascript_solo_cae_al_confirm_del_navegador_si_no_hay_dialog(self):
        js = (RAIZ_APP / "static" / "app.js").read_text(encoding="utf-8")
        usos = re.findall(r"(?<![\w.])confirm\(|window\.confirm\(", js)
        self.assertEqual(usos, ["window.confirm("], "solo el respaldo para navegadores sin <dialog>")

    def test_las_acciones_destructivas_piden_confirmar_en_rojo(self):
        # Quitar, eliminar, retirar, desactivar y restablecer cortan o borran algo.
        palabras = ("Retirar", "Eliminar", "Quitar", "Desactivar", "Restablecer")
        encontradas = set()
        for ruta in _plantillas():
            for etiqueta in re.findall(r"<form[^>]*data-confirmar-boton=\"([^\"]+)\"[^>]*>", ruta.read_text(encoding="utf-8")):
                if etiqueta in palabras:
                    encontradas.add(etiqueta)
        self.assertEqual(encontradas, set(palabras))
        for ruta in _plantillas():
            for fragmento in re.findall(r"<form[^>]*data-confirmar-boton=\"(?:%s)\"[^>]*>" % "|".join(palabras),
                                        ruta.read_text(encoding="utf-8")):
                self.assertIn("data-confirmar-peligro", fragmento, f"{ruta.name}: {fragmento[:80]}")


if __name__ == "__main__":
    unittest.main()
