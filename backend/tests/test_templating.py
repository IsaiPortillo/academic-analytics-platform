"""Huella de los archivos estáticos en las URLs (evita CSS viejo tras desplegar)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import templating


class TestStaticV(unittest.TestCase):
    def test_la_url_cambia_cuando_cambia_el_archivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "static").mkdir()
            archivo = Path(tmp) / "static" / "a.css"
            archivo.write_text("uno")
            with mock.patch.object(templating, "DIRECTORIO_APP", Path(tmp)):
                v1 = templating.static_v("a.css")
                archivo.write_text("dos distinto")
                # La caché se indexa por fecha de modificación: dos escrituras seguidas pueden
                # caer en el mismo tick del reloj del sistema, así que se separa a mano.
                sello = archivo.stat().st_mtime_ns + 5_000_000_000
                os.utime(archivo, ns=(sello, sello))
                v2 = templating.static_v("/a.css")
        self.assertTrue(v1.startswith("/static/a.css?v="))
        self.assertNotEqual(v1, v2)

    def test_misma_url_si_no_cambia(self):
        self.assertEqual(templating.static_v("app.css"), templating.static_v("app.css"))

    def test_archivo_inexistente_no_rompe_la_pagina(self):
        self.assertEqual(templating.static_v("no-existe.css"), "/static/no-existe.css")

    def test_es_relativa(self):
        self.assertTrue(templating.static_v("app.js").startswith("/static/"))


if __name__ == "__main__":
    unittest.main()
