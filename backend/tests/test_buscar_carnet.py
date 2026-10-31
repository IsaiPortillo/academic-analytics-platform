"""Buscar por carnet en la matriz de notas (app/routers/calificaciones.py).

La matriz identifica a cada estudiante por su ID interno, porque el sistema no
guarda nombres ni el carnet (solo su hash). Esta pantalla traduce un carnet al
ID, limitada al roster de la sección.

    cd backend && python -m unittest tests.test_buscar_carnet -v

No toca la base: la sesión de BD y el roster son dobles.
"""

import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("APP_DB_PASSWORD", "x")
os.environ.setdefault("APP_SECRET_KEY", "y")

from app.catalogos import hash_carnet  # noqa: E402
from app.dependencies import UsuarioSesion  # noqa: E402
from app.routers import calificaciones  # noqa: E402

CARNET = "QQ00001"           # distinto del ejemplo del placeholder, a propósito
CARNET_AJENO = "ZZ99999"


def _estudiante(estudiante_id, carnet):
    return SimpleNamespace(estudiante_id=estudiante_id, carnet_hash=hash_carnet(carnet))


def _docente(docente_id=3):
    return UsuarioSesion(usuario_id=7, username="ana.lopez", nombre_completo="Ana López",
                         rol_db="rol_docente", docente_id=docente_id)


class TestBuscarPorCarnet(unittest.TestCase):
    def setUp(self):
        self.peticion = SimpleNamespace(session={})
        self.db = mock.Mock()
        # Sección 173 del docente 3, con el acta abierta.
        self.seccion = SimpleNamespace(seccion_id=173, docente_id=3, periodo_id=8, acta_cerrada=False)
        self.db.get.return_value = self.seccion
        self.en_curso = _estudiante(125, CARNET)
        self.finalizado = _estudiante(900, "CD67890")

    def _roster(self, db, seccion_id, incluir_finalizados=False):
        filas = [(SimpleNamespace(inscripcion_id=1), self.en_curso)]
        if incluir_finalizados:
            filas.append((SimpleNamespace(inscripcion_id=2), self.finalizado))
        return filas

    def _buscar(self, carnet, usuario=None, evaluacion_id=None):
        with mock.patch.object(calificaciones, "_roster", self._roster):
            return calificaciones.buscar_por_carnet(
                self.peticion, periodo_id=8, seccion_id=173, carnet=carnet,
                evaluacion_id=evaluacion_id, usuario=usuario or _docente(), db=self.db)

    def _aviso(self):
        return self.peticion.session.get("aviso", {})

    def test_el_carnet_de_un_estudiante_en_curso_devuelve_su_id(self):
        r = self._buscar(CARNET)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"],
                         "/calificaciones?periodo_id=8&seccion_id=173&resaltar=125")
        self.assertEqual(self._aviso().get("ok"),
                         "El carnet corresponde al ID 125: su fila está resaltada")

    def test_tolera_espacios_y_minusculas_como_el_alta(self):
        r = self._buscar("  qq00001  ")
        self.assertIn("resaltar=125", r.headers["location"])

    def test_conserva_la_evaluacion_que_se_estaba_viendo(self):
        r = self._buscar(CARNET, evaluacion_id=689)
        self.assertEqual(r.headers["location"],
                         "/calificaciones?periodo_id=8&seccion_id=173&evaluacion_id=689&resaltar=125")

    def test_un_carnet_de_otra_seccion_no_revela_si_existe(self):
        r = self._buscar(CARNET_AJENO)
        self.assertNotIn("resaltar", r.headers["location"])
        self.assertEqual(self._aviso().get("error"),
                         "Ese carnet no corresponde a ningún estudiante de esta sección")

    def test_un_estudiante_finalizado_no_se_resalta_pero_se_explica(self):
        # Con el acta abierta la matriz solo dibuja las inscripciones en curso.
        r = self._buscar("CD67890")
        self.assertNotIn("resaltar", r.headers["location"])
        self.assertIn("ya está finalizada", self._aviso().get("error", ""))
        self.assertIn("ID 900", self._aviso().get("error", ""))

    def test_con_el_acta_cerrada_si_se_resalta_al_finalizado(self):
        self.seccion.acta_cerrada = True
        r = self._buscar("CD67890")
        self.assertIn("resaltar=900", r.headers["location"])

    def test_el_carnet_vacio_pide_uno_en_vez_de_buscar(self):
        r = self._buscar("   ")
        self.assertNotIn("resaltar", r.headers["location"])
        self.assertEqual(self._aviso().get("error"), "Escribe el carnet que quieres buscar")

    def test_una_seccion_ajena_no_se_consulta(self):
        r = self._buscar(CARNET, usuario=_docente(docente_id=99))
        self.assertNotIn("resaltar", r.headers["location"])
        self.assertEqual(self._aviso().get("error"), "Sección no encontrada")

    def test_el_carnet_no_aparece_ni_en_la_direccion_ni_en_el_aviso(self):
        # Es un dato personal: en un GET quedaría en el historial y en los
        # registros de nginx. Lo que viaja de vuelta es el ID.
        r = self._buscar(CARNET)
        self.assertNotIn(CARNET, r.headers["location"])
        self.assertNotIn(CARNET, str(self._aviso()))
        r = self._buscar(CARNET_AJENO)
        self.assertNotIn(CARNET_AJENO, r.headers["location"])
        self.assertNotIn(CARNET_AJENO, str(self._aviso()))

    def test_el_hash_no_se_guarda_en_ninguna_parte(self):
        self._buscar(CARNET)
        self.db.add.assert_not_called()
        self.db.execute.assert_not_called()


def _renderizar(request, **contexto):
    from app.templating import templates
    contexto.setdefault("url_for", lambda *a, **k: "/static/x")
    return templates.env.get_template("modulos/calificaciones.html").render(request=request, **contexto)


class TestMatrizConResaltado(unittest.TestCase):
    """La pantalla: el buscador y la fila resaltada."""

    def setUp(self):
        self.peticion = SimpleNamespace(session={"csrf": "t"}, url=SimpleNamespace(path="/calificaciones"))
        self.db = mock.Mock()
        self.seccion = SimpleNamespace(seccion_id=173, docente_id=3, periodo_id=8,
                                       acta_cerrada=False, numero_seccion=1, materia_id=5)
        self.db.get.return_value = SimpleNamespace(codigo_materia="MAT215", nombre="Matemática II",
                                                   unidades_valorativas=4)
        self.evaluacion = SimpleNamespace(evaluacion_id=689, nombre_evaluacion="Parcial 1",
                                          porcentaje=25, fecha_evaluacion=date(2025, 9, 15))
        self.filas = [
            {"inscripcion": SimpleNamespace(inscripcion_id=1), "estudiante": _estudiante(125, CARNET),
             "celdas": [None], "acumulado": 0},
            {"inscripcion": SimpleNamespace(inscripcion_id=2), "estudiante": _estudiante(126, "EF11111"),
             "celdas": [None], "acumulado": 0},
        ]

    def _pagina(self, resaltar=None):
        parches = {
            "_periodos": lambda db: [SimpleNamespace(periodo_id=8, codigo_periodo="2025-II")],
            "_secciones_visibles": lambda db, p, u: [
                (self.seccion, SimpleNamespace(codigo_materia="MAT215", nombre="Matemática II"), 100)],
            "_seccion_permitida": lambda db, s, u: self.seccion,
            "_evaluaciones_de_seccion": lambda db, s: [self.evaluacion],
            "_roster": lambda db, s, incluir_finalizados=False: [(f["inscripcion"], f["estudiante"]) for f in self.filas],
            "_tabla_notas": lambda db, roster, evaluaciones: self.filas,
            "_notas_de_evaluacion": lambda db, e, roster: {},
        }
        with mock.patch.multiple(calificaciones, **parches), \
                mock.patch.object(calificaciones, "periodo_de", lambda db, s: None), \
                mock.patch.object(calificaciones, "templates") as plantillas:
            calificaciones.inicio_calificaciones(
                self.peticion, periodo_id=8, seccion_id=173, evaluacion_id=689,
                resaltar=resaltar, usuario=_docente(), db=self.db)
        contexto = plantillas.TemplateResponse.call_args.args[2]
        return _renderizar(self.peticion, **contexto)

    def test_la_matriz_trae_el_buscador_por_carnet(self):
        html = self._pagina()
        self.assertIn('action="/calificaciones/buscar"', html)
        self.assertIn('name="carnet"', html)
        self.assertIn("method=\"post\"", html)

    def test_sin_busqueda_ninguna_fila_queda_resaltada(self):
        self.assertNotIn('aria-current="true"', self._pagina())

    def test_con_busqueda_se_resalta_solo_la_fila_encontrada(self):
        html = self._pagina(resaltar=125)
        self.assertEqual(html.count('aria-current="true"'), 1)
        fila = html.split('aria-current="true"')[1]
        self.assertIn(">125<", fila[:400])

    def test_un_id_que_no_esta_en_la_matriz_no_resalta_nada(self):
        self.assertNotIn('aria-current="true"', self._pagina(resaltar=999))

    def test_la_matriz_no_muestra_el_carnet_de_nadie(self):
        # No hay nombres ni carnets: solo el ID. Es el motivo de que exista el buscador.
        html = self._pagina(resaltar=125)
        self.assertNotIn(CARNET, html)
        self.assertNotIn(hash_carnet(CARNET), html)
