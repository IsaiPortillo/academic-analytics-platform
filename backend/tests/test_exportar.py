"""Pruebas de la exportación de reportes a CSV, Excel y PDF (sin base de datos)."""

import asyncio
import csv
import io
import unittest
from decimal import Decimal

import openpyxl

from app import exportar
from app.exportar import Columna, Reporte


def _reporte(n=3):
    columnas = [
        Columna("estudiante_id", "ID estudiante", "id", 0.8),
        Columna("materia", "Materia", "texto", 2.5),
        Columna("inscritos", "Inscritos", "entero"),
        Columna("nota", "Nota final", "decimal"),
        Columna("tasa", "Tasa", "porcentaje"),
        Columna("costo", "Costo", "dinero"),
    ]
    filas = [(1197 + i, "Álgebra Vectorial y Matrices", 4603, Decimal("5.50"), 0.2399, 98900.0)
             for i in range(n)]
    return Reporte("Notas finales", "Notas finales por sección", columnas, filas,
                   [("Período", "2022-I"), ("Materia", "Todas")])


def _contenido(respuesta) -> bytes:
    if hasattr(respuesta, "body_iterator"):
        async def leer():
            return b"".join([p.encode() if isinstance(p, str) else p
                             async for p in respuesta.body_iterator])
        return asyncio.run(leer())
    return respuesta.body


class TestFormato(unittest.TestCase):
    def test_tipos(self):
        self.assertEqual(exportar.formatear(1197, "id"), "1197")
        self.assertEqual(exportar.formatear(4603, "entero"), "4,603")
        self.assertEqual(exportar.formatear(Decimal("5.5"), "decimal"), "5.50")
        self.assertEqual(exportar.formatear(0.2399, "porcentaje"), "24.0 %")
        self.assertEqual(exportar.formatear(98900, "dinero"), "$98,900.00")
        self.assertEqual(exportar.formatear(None, "decimal"), "—")
        self.assertEqual(exportar.formatear(float("nan"), "porcentaje"), "—")

    def test_nombre_de_archivo_sin_acentos_ni_espacios(self):
        nombre = exportar._nombre_archivo(_reporte(), "pdf")
        self.assertRegex(nombre, r"^notas_finales_por_seccion_\d{4}-\d{2}-\d{2}\.pdf$")


class TestCSV(unittest.TestCase):
    def test_bom_claves_y_valores_sin_formato(self):
        texto = _contenido(exportar.a_csv(_reporte())).decode("utf-8")
        self.assertTrue(texto.startswith("﻿"))
        filas = list(csv.reader(io.StringIO(texto.lstrip("﻿"))))
        self.assertEqual(filas[0], ["estudiante_id", "materia", "inscritos", "nota", "tasa", "costo"])
        self.assertEqual(filas[1], ["1197", "Álgebra Vectorial y Matrices", "4603", "5.5", "0.2399", "98900.0"])
        self.assertEqual(len(filas), 4)


class TestExcel(unittest.TestCase):
    def setUp(self):
        self.hoja = openpyxl.load_workbook(io.BytesIO(exportar.a_excel_bytes(_reporte()))).active

    def test_titulo_filtros_y_cabecera(self):
        self.assertEqual(self.hoja["A1"].value, "Notas finales")
        self.assertIn("Período: 2022-I", self.hoja["A2"].value)
        self.assertEqual(self.hoja["A5"].value, "ID estudiante")
        self.assertEqual(self.hoja.freeze_panes, "A6")

    def test_numeros_reales_con_formato_de_celda(self):
        self.assertEqual(self.hoja["A6"].value, 1197)
        self.assertEqual(self.hoja["A6"].number_format, "0")
        self.assertEqual(self.hoja["D6"].value, 5.5)
        self.assertEqual(self.hoja["E6"].number_format, "0.0%")
        self.assertEqual(self.hoja["F6"].number_format, '"$"#,##0.00')

    def test_vacio_es_valido(self):
        vacio = Reporte("Vacío", "vacio", _reporte().columnas, [])
        hoja = openpyxl.load_workbook(io.BytesIO(exportar.a_excel_bytes(vacio))).active
        self.assertEqual(hoja["A4"].value, "ID estudiante")


class TestPDF(unittest.TestCase):
    def test_es_un_pdf_completo(self):
        pdf = exportar.a_pdf_bytes(_reporte())
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))

    def test_largo_se_corta_y_lo_indica(self):
        pdf_largo = exportar.a_pdf_bytes(_reporte(exportar.LIMITE_FILAS_PDF + 10))
        self.assertTrue(pdf_largo.startswith(b"%PDF-"))
        # Más páginas que uno corto, pero acotado por el límite.
        self.assertGreater(len(pdf_largo), len(exportar.a_pdf_bytes(_reporte(10))))

    def test_vacio_es_valido(self):
        vacio = Reporte("Vacío", "vacio", _reporte().columnas, [])
        self.assertTrue(exportar.a_pdf_bytes(vacio).startswith(b"%PDF-"))

    def test_cabeceras_http_de_descarga(self):
        respuesta = exportar.responder(_reporte(), "pdf")
        self.assertEqual(respuesta.media_type, "application/pdf")
        self.assertIn("attachment;", respuesta.headers["content-disposition"])
        self.assertEqual(respuesta.headers["cache-control"], "no-store")
        self.assertEqual(int(respuesta.headers["content-length"]), len(respuesta.body))


if __name__ == "__main__":
    unittest.main()
