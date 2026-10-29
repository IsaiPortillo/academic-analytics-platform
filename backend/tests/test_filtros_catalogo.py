"""Filtros, orden, paginación y exportación de las listas de Catálogos.

    cd backend && python -m unittest discover -s tests -v

No toca la base: las consultas se revisan como SQL y la sesión es un doble.
"""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

# Las rutas importan la configuración, que exige estas dos variables. Valores de
# prueba: aquí no se conecta a nada.
os.environ.setdefault("APP_DB_PASSWORD", "x")
os.environ.setdefault("APP_SECRET_KEY", "y")

from sqlalchemy import select  # noqa: E402

from app import filtros_catalogo as fl  # noqa: E402
from app.catalogos import CATALOGOS  # noqa: E402
from app.routers import administracion  # noqa: E402

MATERIAS = CATALOGOS["materias"]
SECCIONES = CATALOGOS["secciones"]
ESTUDIANTES = CATALOGOS["estudiantes"]


def _sql(catalogo, **parametros):
    seleccion = fl.leer(catalogo, parametros)
    consulta = fl.aplicar(select(catalogo.modelo), catalogo, seleccion)
    return str(consulta.compile(compile_kwargs={"literal_binds": True})).replace("academico_oltp.", "")


class TestLecturaDeLaUrl(unittest.TestCase):
    def test_un_valor_valido_se_conserva_y_uno_invalido_se_ignora(self):
        s = fl.leer(MATERIAS, {"carrera_id": "3", "ciclo_plan": "no-es-numero", "activo": "1", "buscar": "  mat  "})
        self.assertEqual(s.filtros, {"carrera_id": "3", "activo": "1"})
        self.assertEqual(s.buscar, "mat")

    def test_filtros_que_no_son_del_catalogo_no_pasan(self):
        self.assertEqual(fl.leer(MATERIAS, {"turno": "MATUTINO", "docente_id": "1"}).filtros, {})

    def test_opcion_solo_acepta_los_valores_permitidos(self):
        self.assertEqual(fl.leer(SECCIONES, {"turno": "NOCTURNO"}).filtros, {"turno": "NOCTURNO"})
        self.assertEqual(fl.leer(SECCIONES, {"turno": "'; DROP TABLE x; --"}).filtros, {})

    def test_booleano_solo_uno_o_cero(self):
        self.assertEqual(fl.leer(MATERIAS, {"activo": "0"}).filtros, {"activo": "0"})
        self.assertEqual(fl.leer(MATERIAS, {"activo": "quiza"}).filtros, {})

    def test_el_valor_por_defecto_aplica_solo_si_no_vino_en_la_url(self):
        self.assertEqual(fl.leer(SECCIONES, {}, {"periodo_id": "12"}).filtros, {"periodo_id": "12"})
        self.assertEqual(fl.leer(SECCIONES, {"periodo_id": "5"}, {"periodo_id": "12"}).filtros, {"periodo_id": "5"})
        # vacío = «todos los períodos»: es una elección, no un descuido
        self.assertEqual(fl.leer(SECCIONES, {"periodo_id": ""}, {"periodo_id": "12"}).filtros, {})

    def test_orden_solo_por_columnas_del_catalogo(self):
        self.assertEqual(fl.leer(MATERIAS, {"orden": "nombre"}).orden, "nombre")
        self.assertEqual(fl.leer(MATERIAS, {"orden": "nombre", "dir": "desc"}).descendente, True)
        self.assertIsNone(fl.leer(MATERIAS, {"orden": "password_hash; --"}).orden)
        self.assertIsNone(fl.leer(ESTUDIANTES, {"orden": "carnet"}).orden)     # el carnet no es una columna

    def test_filas_por_pagina_y_pagina_se_depuran(self):
        self.assertEqual(fl.leer(MATERIAS, {"por_pagina": "100"}).por_pagina, 100)
        self.assertEqual(fl.leer(MATERIAS, {"por_pagina": "100000"}).por_pagina, fl.POR_PAGINA)
        self.assertEqual(fl.leer(MATERIAS, {"por_pagina": "abc"}).por_pagina, fl.POR_PAGINA)
        self.assertEqual(fl.leer(MATERIAS, {"pagina": "3"}).pagina, 3)
        self.assertEqual(fl.leer(MATERIAS, {"pagina": "-2"}).pagina, 1)
        self.assertEqual(fl.leer(MATERIAS, {"pagina": "x"}).pagina, 1)


class TestConsulta(unittest.TestCase):
    def test_filtro_directo(self):
        sql = _sql(MATERIAS, carrera_id="3", ciclo_plan="2")
        self.assertIn("materias.carrera_id = 3", sql)
        self.assertIn("materias.ciclo_plan = 2", sql)

    def test_el_departamento_de_una_materia_sale_de_su_carrera_sin_uniones(self):
        sql = _sql(MATERIAS, departamento_id="7")
        self.assertIn("materias.carrera_id IN (SELECT carreras.carrera_id", sql)
        self.assertIn("carreras.departamento_id = 7", sql)
        self.assertNotIn("JOIN", sql)

    def test_los_filtros_de_otra_tabla_se_combinan_en_cualquier_orden(self):
        sql = _sql(SECCIONES, departamento_id="2", carrera_id="5", turno="MATUTINO", docente_id="9", periodo_id="4")
        for texto in ("secciones.materia_id IN", "secciones.turno = 'MATUTINO'", "secciones.docente_id = 9",
                      "secciones.periodo_id = 4"):
            self.assertIn(texto, sql)
        self.assertNotIn("JOIN", sql)

    def test_booleanos(self):
        self.assertIn("estudiantes.trabaja IS true", _sql(ESTUDIANTES, trabaja="1"))
        self.assertIn("estudiantes.activo IS false", _sql(ESTUDIANTES, activo="0"))

    def test_sin_filtros_no_hay_where(self):
        self.assertNotIn("WHERE", _sql(MATERIAS))

    def test_un_valor_invalido_no_llega_al_sql(self):
        sql = _sql(MATERIAS, carrera_id="1; DROP TABLE materias")
        self.assertNotIn("DROP", sql)
        self.assertNotIn("WHERE", sql)

    def test_todos_los_catalogos_con_filtros_tienen_opciones_que_funcionan(self):
        for slug, filtros in fl.FILTROS.items():
            self.assertIn(slug, CATALOGOS)
            for f in filtros:
                self.assertTrue(f.sub or f.columna is not None, f"{slug}.{f.nombre}")
                self.assertIn(f.tipo, ("fk", "valores", "opcion", "bool"))


class TestOrden(unittest.TestCase):
    def _orden(self, catalogo, **p):
        cl = fl.clausulas_de_orden(catalogo, fl.leer(catalogo, p))
        return [str(c.compile(compile_kwargs={"literal_binds": True})).replace("academico_oltp.", "") for c in cl]

    def test_sin_orden_pedido_se_usa_el_del_catalogo(self):
        self.assertEqual(len(self._orden(MATERIAS)), len(MATERIAS.orden))

    def test_ascendente_descendente_y_desempate_por_id(self):
        self.assertEqual(self._orden(MATERIAS, orden="nombre"), ["materias.nombre ASC", "materias.materia_id ASC"])
        self.assertEqual(self._orden(MATERIAS, orden="nombre", dir="desc"),
                         ["materias.nombre DESC", "materias.materia_id ASC"])

    def test_ordenar_por_id(self):
        self.assertEqual(self._orden(ESTUDIANTES, orden="id", dir="desc")[0], "estudiantes.estudiante_id DESC")


class TestEnlaces(unittest.TestCase):
    def test_la_url_conserva_lo_pedido_y_permite_quitar_o_cambiar(self):
        s = fl.leer(MATERIAS, {"buscar": "mat", "carrera_id": "3", "orden": "nombre", "dir": "desc", "por_pagina": "100"})
        completa = fl.consulta_url(s)
        for texto in ("buscar=mat", "carrera_id=3", "orden=nombre", "dir=desc", "por_pagina=100"):
            self.assertIn(texto, completa)
        self.assertNotIn("carrera_id", fl.consulta_url(s, quitar=("carrera_id",)))
        self.assertIn("orden=uv", fl.consulta_url(s, orden="uv"))
        self.assertNotIn("dir=", fl.consulta_url(s, dir=""))

    def test_los_valores_se_codifican(self):
        s = fl.leer(MATERIAS, {"buscar": "a&b=c"})
        self.assertEqual(fl.consulta_url(s), "buscar=a%26b%3Dc")

    def test_el_chip_de_cada_filtro_lo_quita_y_el_del_valor_por_defecto_lo_manda_vacio(self):
        s = fl.leer(SECCIONES, {"turno": "NOCTURNO", "buscar": "lab"}, {"periodo_id": "4"})
        with mock.patch.object(fl, "opciones", side_effect=lambda db, f: [("4", "2026-II"), ("NOCTURNO", "Nocturno")]):
            chips = fl.chips(mock.Mock(), SECCIONES, s, "/admin/secciones", ("periodo_id",))
        por_etiqueta = {c["etiqueta"]: c for c in chips}
        self.assertEqual(por_etiqueta["Período"]["texto"], "2026-II")
        self.assertTrue(por_etiqueta["Período"]["quitar"].endswith("&periodo_id=") or
                        "periodo_id=" in por_etiqueta["Período"]["quitar"])
        self.assertNotIn("periodo_id=4", por_etiqueta["Período"]["quitar"])
        self.assertNotIn("turno", por_etiqueta["Turno"]["quitar"])
        self.assertNotIn("buscar", por_etiqueta["Búsqueda"]["quitar"])


class TestListaYExportacion(unittest.TestCase):
    def test_la_exportacion_trae_la_lista_filtrada_en_csv_con_acentos_para_excel(self):
        departamentos = CATALOGOS["departamentos"]
        registros = [SimpleNamespace(departamento_id=1, codigo_departamento="DIA", nombre="Ingeniería y Arquitectura"),
                     SimpleNamespace(departamento_id=2, codigo_departamento="DCE", nombre="Ciencias Económicas")]
        db = mock.Mock()
        db.scalars.return_value.all.return_value = registros
        peticion = SimpleNamespace(query_params={"buscar": "ing", "orden": "nombre"})
        with mock.patch.object(administracion, "_etiquetas_fk", return_value={}):
            r = administracion.exportar(peticion, "departamentos", SimpleNamespace(), db)
        texto = r.body.decode("utf-8")
        self.assertTrue(texto.startswith("﻿"))
        lineas = texto.lstrip("﻿").splitlines()
        self.assertEqual(lineas[0], "Código,Nombre")
        self.assertEqual(lineas[1], "DIA,Ingeniería y Arquitectura")
        self.assertIn('attachment; filename="departamentos.csv"', r.headers["content-disposition"])
        self.assertEqual(len(lineas), 3)
        consulta = str(db.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("%ing%", consulta)        # la búsqueda también se aplica a lo exportado
        self.assertIn("LIMIT 20000", consulta)

    def test_la_pantalla_muestra_filtros_chips_orden_y_descarga(self):
        from app.templating import templates
        s = fl.leer(MATERIAS, {"carrera_id": "3", "orden": "nombre"})
        columnas = [{"titulo": "Código", "clave": "codigo_materia", "sentido": None,
                     "url": "/admin/materias?orden=codigo_materia"},
                    {"titulo": "Nombre", "clave": "nombre", "sentido": "asc", "url": "/admin/materias?orden=nombre&dir=desc"}]
        filtros = [{"nombre": "carrera_id", "etiqueta": "Carrera", "valor": "3",
                    "opciones": [("3", "I10515 · Sistemas"), ("4", "I10506 · Civil")]}]
        contexto = {
            "request": SimpleNamespace(session={"csrf": "t"}, url=SimpleNamespace(path="/admin/materias")),
            "url_for": lambda *a, **k: "/static/x", "usuario": SimpleNamespace(
                nombre_completo="Coordinación", rol_legible="Coordinador", es_coordinador=True, rol_db="rol_coordinador"),
            "catalogo": MATERIAS, "ok": None, "error": None, "columnas": columnas,
            "filas": [(1, ["MAT115", "Matemática I"])], "total": 1, "total_catalogo": 523, "pagina": 1, "paginas": 1,
            "seleccion": s, "filtros": filtros,
            "chips": [{"etiqueta": "Carrera", "texto": "I10515 · Sistemas", "quitar": "/admin/materias?orden=nombre"}],
            "limpiar": "/admin/materias?", "consulta": "carrera_id=3&orden=nombre",
            "pagina_url": "/admin/materias?carrera_id=3&orden=nombre", "por_pagina_opciones": fl.POR_PAGINA_OPCIONES,
        }
        html = templates.env.get_template("modulos/admin_lista.html").render(**contexto)
        self.assertIn("1 de 523", html)                                      # resultado frente al total
        self.assertIn('<option value="3" selected>', html)                  # el filtro activo queda elegido
        self.assertIn("Quitar filtro Carrera: I10515 · Sistemas", html)     # chip accesible
        self.assertIn('aria-sort="ascending"', html)                        # columna ordenada
        self.assertIn("/admin/materias/exportar?carrera_id=3&amp;orden=nombre", html)    # CSV con los mismos filtros
        self.assertIn("data-filtrar-al-cambiar", html)
        self.assertIn("Filas por página", html)

    def test_sin_resultados_ofrece_quitar_los_filtros(self):
        from app.templating import templates
        html_base = {"request": SimpleNamespace(session={"csrf": "t"}, url=SimpleNamespace(path="/admin/materias")),
                     "url_for": lambda *a, **k: "/static/x",
                     "usuario": SimpleNamespace(nombre_completo="C", rol_legible="Coordinador", es_coordinador=True,
                                                rol_db="rol_coordinador"),
                     "catalogo": MATERIAS, "ok": None, "error": None, "columnas": [], "filas": [], "total": 0,
                     "total_catalogo": 523, "pagina": 1, "paginas": 1, "seleccion": fl.leer(MATERIAS, {}), "filtros": [],
                     "chips": [{"etiqueta": "x", "texto": "y", "quitar": "/q"}], "limpiar": "/admin/materias?",
                     "consulta": "", "pagina_url": "/admin/materias?", "por_pagina_opciones": fl.POR_PAGINA_OPCIONES}
        html = templates.env.get_template("modulos/admin_lista.html").render(**html_base)
        self.assertIn("Sin registros con esos filtros", html)
        self.assertIn("Quitar los filtros", html)
        self.assertNotIn("Descargar lista", html)


if __name__ == "__main__":
    unittest.main()
