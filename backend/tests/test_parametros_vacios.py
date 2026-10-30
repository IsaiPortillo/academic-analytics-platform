"""Filtros vacíos en la URL (app/main.py: SinParametrosVacios y el manejador de 422).

Un formulario GET envía también los campos en «Todos» o sin fecha
(«desde=&periodo_id=»). Antes FastAPI respondía 422 con JSON en inglés en el
reporte personalizado, los reportes, la auditoría y los módulos operativos.

    cd backend && python -m unittest tests.test_parametros_vacios -v
"""

import asyncio
import os
import unittest

os.environ.setdefault("APP_SECRET_KEY", "prueba")
os.environ.setdefault("APP_DB_PASSWORD", "prueba")

from app.main import SinParametrosVacios, app  # noqa: E402


def _query_que_llega(query: bytes) -> bytes:
    recibido = {}

    async def destino(scope, receive, send):
        recibido["query"] = scope["query_string"]

    asyncio.run(SinParametrosVacios(destino)({"type": "http", "query_string": query}, None, None))
    return recibido["query"]


class TestSinParametrosVacios(unittest.TestCase):
    def test_quita_los_vacios_y_conserva_el_resto(self):
        query = (b"tema=calificaciones&dimension=mes&desglose=&metrica=porcentaje_asistencia"
                 b"&desde=&hasta=&periodo_id=&turno=")
        self.assertEqual(_query_que_llega(query),
                         b"tema=calificaciones&dimension=mes&metrica=porcentaje_asistencia")

    def test_conserva_valores_con_igual_o_codificados(self):
        query = b"q=a%3Db&desde=2024-01-01&vacio=&&x"
        self.assertEqual(_query_que_llega(query), b"q=a%3Db&desde=2024-01-01&x")

    def test_sin_query_no_cambia_nada(self):
        self.assertEqual(_query_que_llega(b""), b"")

    def test_esta_registrado_en_la_aplicacion(self):
        self.assertIn(SinParametrosVacios, [m.cls for m in app.user_middleware])


class TestParametroInvalido(unittest.TestCase):
    def _responder(self, ruta):
        from fastapi.exceptions import RequestValidationError
        from starlette.requests import Request

        from app.main import manejar_parametros_invalidos

        scope = {"type": "http", "method": "GET", "path": ruta, "query_string": b"desde=abc", "headers": [],
                 "session": {}, "app": app, "router": app.router}
        error = RequestValidationError([{"type": "date_from_datetime_parsing", "loc": ("query", "desde"),
                                         "msg": "Input should be a valid date", "input": "abc"}])
        return asyncio.run(manejar_parametros_invalidos(Request(scope), error))

    def test_pagina_en_espanol_con_el_campo(self):
        r = self._responder("/reportes/personalizado")
        self.assertEqual(r.status_code, 400)
        cuerpo = r.body.decode()
        self.assertIn("Algún filtro tiene un valor no válido (desde)", cuerpo)
        self.assertNotIn('"detail"', cuerpo)

    def test_la_api_conserva_su_422(self):
        r = self._responder("/api/algo")
        self.assertEqual(r.status_code, 422)
        self.assertIn(b'"detail"', r.body)


if __name__ == "__main__":
    unittest.main()
