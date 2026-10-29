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
    return " ".join(str(consulta.compile(compile_kwargs={"literal_binds": True})).replace("academico_oltp.", "").split())


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

    def test_el_departamento_de_una_materia_sale_de_su_carrera(self):
        sql = _sql(MATERIAS, departamento_id="7")
        self.assertIn("(SELECT carreras.departamento_id FROM carreras WHERE carreras.carrera_id = materias.carrera_id) = 7", sql)

    def test_los_filtros_de_otra_tabla_se_combinan_en_cualquier_orden(self):
        sql = _sql(SECCIONES, departamento_id="2", carrera_id="5", turno="MATUTINO", docente_id="9", periodo_id="4")
        for texto in ("materias.materia_id = secciones.materia_id", "= 2", "= 5", "secciones.turno = 'MATUTINO'",
                      "secciones.docente_id = 9", "secciones.periodo_id = 4"):
            self.assertIn(texto, sql)

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
                self.assertIsNotNone(f.expresion, f"{slug}.{f.nombre}")
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


# Una mini tabla de materias: (departamento, carrera, ciclo del plan, activo)
FILAS = [(1, 10, 1, True), (1, 10, 2, True), (1, 11, 1, True), (2, 20, 1, True), (2, 21, 3, False)]
POSICION = {"departamento_id": 0, "carrera_id": 1, "ciclo_plan": 2, "activo": 3}
ETIQUETAS = {"departamento_id": {"1": "Ingeniería", "2": "Medicina"},
             "carrera_id": {"10": "Sistemas", "11": "Civil", "20": "Doctorado", "21": "Enfermería"},
             "activo": {"1": "Sí", "0": "No"}}


def contar_falso(db, catalogo, filtro, seleccion, busqueda):
    """Lo mismo que contar_por_valor, sobre la mini tabla: cuenta por valor entre las filas que cumplen
    los demás filtros."""
    def texto(fila, nombre):
        valor = fila[POSICION[nombre]]
        return str(int(valor)) if isinstance(valor, bool) else str(valor)
    cuentas = {}
    for fila in FILAS:
        if all(texto(fila, n) == v for n, v in seleccion.filtros.items() if n != filtro.nombre):
            clave = texto(fila, filtro.nombre)
            cuentas[clave] = cuentas.get(clave, 0) + 1
    return cuentas


class TestFiltrosEnCascada(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(fl, "_etiquetas", side_effect=lambda db, f: ETIQUETAS.get(f.nombre, {}))
        parche.start()
        self.addCleanup(parche.stop)

    def _facetas(self, **elegidos):
        seleccion = fl.leer(MATERIAS, {})
        seleccion.filtros.update(elegidos)
        return {f["nombre"]: f for f in fl.facetas(mock.Mock(), MATERIAS, seleccion, contar=contar_falso)}

    def test_sin_elegir_nada_cada_selector_trae_todo_lo_que_existe_con_su_cuenta(self):
        f = self._facetas()
        self.assertEqual([t for _, t in f["departamento_id"]["opciones"]], ["Ingeniería (3)", "Medicina (2)"])
        self.assertEqual(len(f["carrera_id"]["opciones"]), 4)
        self.assertEqual([v for v, _ in f["ciclo_plan"]["opciones"]], ["1", "2", "3"])
        self.assertEqual(f["carrera_id"]["total"], 5)

    def test_elegir_un_departamento_deja_solo_sus_carreras(self):
        f = self._facetas(departamento_id="1")
        self.assertEqual([t for _, t in f["carrera_id"]["opciones"]], ["Sistemas (2)", "Civil (1)"])
        self.assertEqual([v for v, _ in f["ciclo_plan"]["opciones"]], ["1", "2"])        # el ciclo 3 es de Medicina
        self.assertEqual(f["carrera_id"]["total"], 3)

    def test_elegir_una_carrera_deja_su_departamento_y_sus_ciclos(self):
        f = self._facetas(carrera_id="21")
        self.assertEqual([t for _, t in f["departamento_id"]["opciones"]], ["Medicina (1)"])
        self.assertEqual([v for v, _ in f["ciclo_plan"]["opciones"]], ["3"])
        self.assertEqual([t for _, t in f["activo"]["opciones"]], ["No (1)"])

    def test_el_selector_elegido_sigue_mostrando_las_alternativas(self):
        # El propio filtro no cuenta contra sí mismo: con el departamento 1 elegido se ve también el 2.
        f = self._facetas(departamento_id="1")
        self.assertEqual([v for v, _ in f["departamento_id"]["opciones"]], ["1", "2"])
        self.assertEqual(f["departamento_id"]["valor"], "1")

    def test_las_opciones_sin_registros_no_aparecen(self):
        f = self._facetas(activo="0")
        self.assertEqual([v for v, _ in f["carrera_id"]["opciones"]], ["21"])

    def test_cambiar_el_departamento_quita_la_carrera_que_ya_no_le_corresponde(self):
        seleccion = fl.leer(MATERIAS, {})
        seleccion.filtros.update({"departamento_id": "2", "carrera_id": "10"})
        quitados = fl.reconciliar(mock.Mock(), MATERIAS, seleccion, contar=contar_falso)
        self.assertEqual(quitados, ["Carrera"])
        self.assertEqual(seleccion.filtros, {"departamento_id": "2"})

    def test_una_combinacion_valida_no_se_toca(self):
        seleccion = fl.leer(MATERIAS, {})
        seleccion.filtros.update({"departamento_id": "1", "carrera_id": "10", "ciclo_plan": "2"})
        self.assertEqual(fl.reconciliar(mock.Mock(), MATERIAS, seleccion, contar=contar_falso), [])
        self.assertEqual(len(seleccion.filtros), 3)

    def test_una_combinacion_imposible_se_despeja_entera(self):
        seleccion = fl.leer(MATERIAS, {})
        seleccion.filtros.update({"carrera_id": "21", "ciclo_plan": "1", "activo": "1"})
        quitados = fl.reconciliar(mock.Mock(), MATERIAS, seleccion, contar=contar_falso)
        self.assertTrue(quitados)
        self.assertGreater(len(contar_falso(None, MATERIAS, fl.filtros_de(MATERIAS)[0], seleccion, None)), 0)

    def test_la_consulta_de_cuentas_agrupa_ignora_el_propio_filtro_y_aplica_la_busqueda(self):
        db = mock.Mock()
        db.execute.return_value.all.return_value = [(1, 3), (2, 2), (None, 5)]
        seleccion = fl.leer(MATERIAS, {"departamento_id": "1", "carrera_id": "10"})
        carrera = [f for f in fl.filtros_de(MATERIAS) if f.nombre == "carrera_id"][0]
        busqueda = MATERIAS.modelo.nombre.ilike("%mat%")
        cuentas = fl.contar_por_valor(db, MATERIAS, carrera, seleccion, busqueda)
        self.assertEqual(cuentas, {"1": 3, "2": 2})                  # el valor nulo no cuenta
        sql = " ".join(str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})).split())
        self.assertIn("GROUP BY valor", sql)
        self.assertIn("LIKE lower('%mat%')", sql)
        self.assertIn("carreras.departamento_id", sql)               # el departamento sí filtra
        self.assertNotIn("materias.carrera_id = 10", sql)            # su propio valor no


class TestOrdenConAcentos(unittest.TestCase):
    def setUp(self):
        fl._colacion_disponible = None
        self.addCleanup(setattr, fl, "_colacion_disponible", None)

    def test_el_texto_se_ordena_con_la_colacion_en_espanol_para_que_alvebra_no_quede_despues_de_zoologia(self):
        seleccion = fl.leer(MATERIAS, {"orden": "nombre"})
        sql = str(fl.clausulas_de_orden(MATERIAS, seleccion, "es-x-icu")[0].compile(compile_kwargs={"literal_binds": True}))
        self.assertIn('COLLATE "es-x-icu"', sql)

    def test_los_numeros_no_llevan_colacion(self):
        seleccion = fl.leer(MATERIAS, {"orden": "unidades_valorativas"})
        sql = str(fl.clausulas_de_orden(MATERIAS, seleccion, "es-x-icu")[0].compile(compile_kwargs={"literal_binds": True}))
        self.assertNotIn("COLLATE", sql)

    def test_sin_colacion_se_ordena_como_siempre(self):
        seleccion = fl.leer(MATERIAS, {"orden": "nombre"})
        sql = str(fl.clausulas_de_orden(MATERIAS, seleccion)[0].compile(compile_kwargs={"literal_binds": True}))
        self.assertNotIn("COLLATE", sql)

    def test_la_colacion_solo_se_usa_si_la_base_la_tiene_y_se_consulta_una_vez(self):
        db = mock.Mock()
        db.scalar.return_value = True
        self.assertEqual(fl.colacion(db), "es-x-icu")
        self.assertEqual(fl.colacion(db), "es-x-icu")
        self.assertEqual(db.scalar.call_count, 1)
        fl._colacion_disponible = None
        db.scalar.return_value = False
        self.assertIsNone(fl.colacion(db))


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
        with mock.patch.object(fl, "_etiquetas", side_effect=lambda db, f: {"4": "2026-II", "NOCTURNO": "Nocturno"}):
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
        filtros = [{"nombre": "carrera_id", "etiqueta": "Carrera", "valor": "3", "total": 523,
                    "opciones": [("3", "I10515 · Sistemas (45)"), ("4", "I10506 · Civil (48)")]}]
        contexto = {
            "request": SimpleNamespace(session={"csrf": "t"}, url=SimpleNamespace(path="/admin/materias")),
            "url_for": lambda *a, **k: "/static/x", "usuario": SimpleNamespace(
                nombre_completo="Coordinación", rol_legible="Coordinador", es_coordinador=True, rol_db="rol_coordinador"),
            "catalogo": MATERIAS, "ok": None, "error": None, "columnas": columnas,
            "filas": [(1, ["MAT115", "Matemática I"])], "total": 1, "total_catalogo": 523, "pagina": 1, "paginas": 1,
            "seleccion": s, "filtros": filtros, "quitados": [],
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
                     "total_catalogo": 523, "pagina": 1, "paginas": 1, "seleccion": fl.leer(MATERIAS, {}), "filtros": [], "quitados": [],
                     "chips": [{"etiqueta": "x", "texto": "y", "quitar": "/q"}], "limpiar": "/admin/materias?",
                     "consulta": "", "pagina_url": "/admin/materias?", "por_pagina_opciones": fl.POR_PAGINA_OPCIONES}
        html = templates.env.get_template("modulos/admin_lista.html").render(**html_base)
        self.assertIn("Sin registros con esos filtros", html)
        self.assertIn("Quitar los filtros", html)
        self.assertNotIn("Descargar lista", html)


if __name__ == "__main__":
    unittest.main()
