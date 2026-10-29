"""Datos de prueba que se parecen a la FMO-UES: catálogo, calendario y simulación.

    cd backend && python -m unittest discover -s tests -v

No toca la base: el catálogo y la simulación son funciones puras.
"""

import importlib.util
import sys
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts" / "generator"))

import catalogo_ues as cat  # noqa: E402
import simulacion_ues as sim  # noqa: E402

HOY = date(2026, 10, 29)


class TestCatalogo(unittest.TestCase):
    def test_ocho_departamentos_y_doce_carreras(self):
        self.assertEqual(len(cat.DEPARTAMENTOS), 8)
        self.assertEqual(len(cat.CARRERAS), 12)
        codigos = {d for d, _ in cat.DEPARTAMENTOS}
        self.assertEqual({c.departamento for c in cat.CARRERAS}, codigos)   # todos tienen carrera

    def test_codigos_nombres_y_limites_caben_en_la_base(self):
        vistos = set()
        for carrera in cat.CARRERAS:
            self.assertLessEqual(len(carrera.codigo), 10)
            self.assertLessEqual(len(carrera.nombre), 120)
            self.assertLessEqual(carrera.ciclos, 12)
            for m in carrera.materias:
                self.assertNotIn(m.codigo, vistos, m.codigo)
                vistos.add(m.codigo)
                self.assertLessEqual(len(m.codigo), 15)
                self.assertLessEqual(len(m.nombre), 150)
                self.assertTrue(1 <= m.uv <= 10 and 1 <= m.ciclo <= 12, m)

    def test_los_prerrequisitos_apuntan_a_ciclos_anteriores_de_la_misma_carrera(self):
        for carrera in cat.CARRERAS:
            por_codigo = {m.codigo: m for m in carrera.materias}
            for m in carrera.materias:
                for requisito in m.prerrequisitos:
                    self.assertIn(requisito, por_codigo, f"{m.codigo} exige {requisito}")
                    self.assertLess(por_codigo[requisito].ciclo, m.ciclo, f"{m.codigo} <- {requisito}")

    def test_cada_ciclo_del_plan_tiene_materias(self):
        for carrera in cat.CARRERAS:
            self.assertEqual({m.ciclo for m in carrera.materias}, set(range(1, carrera.ciclos + 1)), carrera.nombre)

    def test_sistemas_conserva_las_16_materias_y_prerrequisitos_que_ya_existian(self):
        originales = {"MAT115": (), "PRG115": (), "ACA115": (), "MAT215": ("MAT115",), "PRG215": ("PRG115",),
                      "BAD115": ("PRG115",), "PRG315": ("PRG215",), "MAT315": ("MAT215",), "BAD215": ("BAD115",),
                      "ADS115": ("PRG215",), "SIF115": ("ADS115", "BAD115"), "ADS215": ("ADS115",),
                      "DWB115": ("PRG315",), "ARC115": ("ACA115",), "IAI115": ("PRG315", "MAT315"),
                      "BIN115": ("BAD215", "SIF115")}
        isi = {m.codigo: m for m in cat.ISI.materias}
        self.assertEqual(cat.ISI.codigo, "I10515")
        for codigo, requisitos in originales.items():
            self.assertEqual(set(isi[codigo].prerrequisitos), set(requisitos), codigo)

    def test_docentes_por_departamento_y_los_de_dia_son_los_que_ya_existian(self):
        reparto = sim.numeracion_de_docentes()
        self.assertEqual({d: len(v) for d, v in reparto.items()}, cat.DOCENTES_POR_DEPARTAMENTO)
        self.assertEqual(reparto["DIA"][:20], [f"DOC-{n}" for n in range(101, 121)])
        todos = [c for v in reparto.values() for c in v]
        self.assertEqual(len(todos), len(set(todos)))


class TestCalendario(unittest.TestCase):
    def test_dos_ciclos_al_ano(self):
        lista = cat.periodos(2025, 2026)
        self.assertEqual([p[0] for p in lista], ["2025-I", "2025-II", "2026-I", "2026-II"])
        for _, anio, ciclo, inicio, fin in lista:
            self.assertEqual(inicio.year, anio)
            self.assertGreater(fin, inicio)

    def test_el_ciclo_i_no_se_traslapa_con_el_ii(self):
        (_, _, _, _, fin_i), (_, _, _, inicio_ii, _) = cat.periodos(2026, 2026)
        self.assertLess(fin_i, inicio_ii)

    def test_cuatro_modulos_consecutivos_que_cubren_el_ciclo_completo(self):
        for _, _, _, inicio, fin in cat.periodos(2024, 2026):
            modulos = cat.modulos_del_ciclo(inicio, fin)
            self.assertEqual(len(modulos), cat.MODULOS_POR_CICLO)
            self.assertEqual((modulos[0][0], modulos[-1][1]), (inicio, fin))
            for (_, hasta), (desde, _) in zip(modulos, modulos[1:]):
                self.assertEqual((desde - hasta).days, 1)    # ni huecos ni traslapes


class TestEvaluaciones(unittest.TestCase):
    def test_cada_estilo_suma_cien_por_ciento(self):
        for estilo in cat.ESTILOS_DE_EVALUACION:
            self.assertEqual(sum(p for _, p, _ in cat.evaluaciones_de(estilo)), 100, estilo)

    def test_los_pesos_de_los_estilos_suman_uno_y_domina_el_parcial_corto_por_modulo(self):
        pesos = {e: v[0] for e, v in cat.ESTILOS_DE_EVALUACION.items()}
        self.assertAlmostEqual(sum(pesos.values()), 1.0)
        self.assertEqual(max(pesos, key=pesos.get), "parcial_corto")
        self.assertEqual([n for n, _, _ in cat.evaluaciones_de("parcial_corto")],
                         [f"Parcial corto · Módulo {k}" for k in range(1, 5)])

    def test_la_fecha_de_cada_evaluacion_cae_dentro_de_su_modulo(self):
        inicio, fin = cat.fechas_del_ciclo(2026, "II")
        modulos = cat.modulos_del_ciclo(inicio, fin)
        for estilo in cat.ESTILOS_DE_EVALUACION:
            plan = cat.evaluaciones_de(estilo)
            for k, (_, _, modulo) in enumerate(plan):
                fecha = cat.fecha_de_evaluacion(k, len(plan), modulo, modulos)
                limites = modulos[modulo - 1] if modulo else (inicio, fin)
                self.assertTrue(limites[0] <= fecha <= limites[1], (estilo, k, fecha))

    def test_el_estilo_de_un_docente_es_fijo(self):
        self.assertEqual(sim.estilo_de_docente("DOC-105"), sim.estilo_de_docente("DOC-105"))
        estilos = Counter(sim.estilo_de_docente(f"DOC-{n}") for n in range(101, 206))
        self.assertGreaterEqual(len(estilos), 4)     # no todos evalúan igual


class TestSimulacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = sim.simular(HOY)

    def test_es_determinista(self):
        otra = sim.simular(HOY)
        for clave in ("estudiantes", "secciones", "evaluaciones", "inscripciones", "calificaciones", "asistencias"):
            self.assertEqual(len(otra[clave]), len(self.r[clave]), clave)

    def test_volumen_razonable(self):
        r = self.r
        self.assertGreater(len(r["estudiantes"]), 1500)
        self.assertGreater(len(r["inscripciones"]), 30000)
        self.assertLess(len(r["asistencias"]), 400000)

    def test_los_ciclos_cerrados_estan_finalizados_y_el_vigente_en_curso(self):
        secciones = self.r["secciones"]
        for i in self.r["inscripciones"]:
            sec = secciones[i["seccion"]]
            if sec["periodo"] == cat.CICLO_VIGENTE:
                self.assertIn(i["estado"], ("INSCRITO", "RETIRADO"))
                self.assertFalse(sec["cerrada"])
            else:
                self.assertIn(i["estado"], ("FINALIZADO", "RETIRADO"))
                self.assertTrue(sec["cerrada"])

    def test_cada_seccion_suma_cien_por_ciento_en_evaluaciones(self):
        suma = Counter()
        for seccion, _, porcentaje, _ in self.r["evaluaciones"]:
            suma[seccion] += porcentaje
        self.assertEqual(set(suma.values()), {100})
        self.assertEqual(len(suma), len(self.r["secciones"]))

    def test_notas_validas_y_ninguna_posterior_a_hoy(self):
        fechas = [e[3] for e in self.r["evaluaciones"]]
        for _, i_eval, nota in self.r["calificaciones"]:
            self.assertTrue(0 <= nota <= 10)
            self.assertLessEqual(fechas[i_eval], HOY)
        for _, dia, _ in self.r["asistencias"]:
            self.assertLessEqual(dia, HOY)

    def test_el_ciclo_vigente_tiene_modulos_evaluados_y_modulos_pendientes(self):
        vigentes = {i for i, s in enumerate(self.r["secciones"]) if s["periodo"] == cat.CICLO_VIGENTE}
        evaluaciones = [e for e in self.r["evaluaciones"] if e[0] in vigentes]
        pasadas = [e for e in evaluaciones if e[3] <= HOY]
        self.assertTrue(pasadas and len(pasadas) < len(evaluaciones))

    def test_una_inscripcion_no_se_repite_y_el_intento_es_valido(self):
        pares = Counter((i["estudiante"], i["seccion"]) for i in self.r["inscripciones"])
        self.assertEqual(max(pares.values()), 1)
        self.assertTrue(all(1 <= i["intento"] <= sim.INTENTOS_MAXIMOS for i in self.r["inscripciones"]))

    def test_cada_estudiante_cursa_materias_de_su_carrera(self):
        carrera_de_materia = {m.codigo: c.codigo for c in cat.CARRERAS for m in c.materias}
        for i in self.r["inscripciones"][:20000]:
            materia = self.r["secciones"][i["seccion"]]["materia"]
            self.assertEqual(carrera_de_materia[materia], self.r["estudiantes"][i["estudiante"]]["carrera"])

    def test_nadie_cursa_sin_haber_aprobado_los_prerrequisitos(self):
        # Se reconstruye la historia de cada estudiante en orden de ciclo y se comprueba cada inscripción.
        orden = {codigo: i for i, (codigo, *_) in enumerate(self.r["periodos"])}
        finales = {}
        peso = [e[2] for e in self.r["evaluaciones"]]
        acumulado = {}
        for i_insc, i_eval, nota in self.r["calificaciones"]:
            suma, total = acumulado.get(i_insc, (0.0, 0.0))
            acumulado[i_insc] = (suma + nota * peso[i_eval], total + peso[i_eval])
        por_codigo = {m.codigo: m for c in cat.CARRERAS for m in c.materias}
        historia: dict[int, list] = {}
        for i, insc in enumerate(self.r["inscripciones"]):
            if insc["estado"] == "RETIRADO":
                continue
            sec = self.r["secciones"][insc["seccion"]]
            historia.setdefault(insc["estudiante"], []).append((orden[sec["periodo"]], sec["materia"], i, insc["estado"]))
        for est, filas in list(historia.items())[:600]:
            aprobadas = set()
            for periodo in sorted({f[0] for f in filas}):
                del_ciclo = [f for f in filas if f[0] == periodo]
                for _, materia, _, _ in del_ciclo:
                    self.assertTrue(set(por_codigo[materia].prerrequisitos) <= aprobadas, (est, materia))
                for _, materia, i, estado in del_ciclo:
                    suma, total = acumulado.get(i, (0.0, 0.0))
                    if estado == "FINALIZADO" and total and suma / total >= sim.UMBRAL_APROBACION:
                        aprobadas.add(materia)

    def test_los_retiros_traen_motivo_y_fecha_y_las_demas_no(self):
        for i in self.r["inscripciones"]:
            if i["estado"] == "RETIRADO":
                self.assertIn(i["motivo"], cat.MOTIVOS_DE_RETIRO)
                self.assertIsNotNone(i["fecha_retiro"])
            else:
                self.assertIsNone(i["motivo"])

    def test_carnets_unicos_y_anonimizados(self):
        carnets = [e["carnet"] for e in self.r["estudiantes"]]
        hashes = [e["hash"] for e in self.r["estudiantes"]]
        self.assertEqual(len(set(carnets)), len(carnets))
        self.assertEqual(len(set(hashes)), len(hashes))
        self.assertTrue(all(len(h) == 64 for h in hashes))
        self.assertNotEqual(sim.hash_carnet("IS21001", "clave"), sim.hash_carnet("IS21001", None))

    def test_hay_aprobacion_variada_con_materias_cuello_de_botella(self):
        peso = [e[2] for e in self.r["evaluaciones"]]
        finales = {}
        for i_insc, i_eval, nota in self.r["calificaciones"]:
            suma, total = finales.get(i_insc, (0.0, 0.0))
            finales[i_insc] = (suma + nota * peso[i_eval], total + peso[i_eval])
        aprobacion = {}
        for i, insc in enumerate(self.r["inscripciones"]):
            if insc["estado"] != "FINALIZADO":
                continue
            materia = self.r["secciones"][insc["seccion"]]["materia"]
            suma, total = finales[i]
            ap, n = aprobacion.get(materia, (0, 0))
            aprobacion[materia] = (ap + (suma / total >= sim.UMBRAL_APROBACION), n + 1)
        global_ = sum(a for a, _ in aprobacion.values()) / sum(n for _, n in aprobacion.values())
        self.assertTrue(0.60 < global_ < 0.90, global_)
        matematica = aprobacion["MAT115"][0] / aprobacion["MAT115"][1]
        self.assertLess(matematica, global_ - 0.1)      # Matemática I frena más que el promedio


class TestCargaDelGrafo(unittest.TestCase):
    def test_el_cargador_de_neo4j_usa_el_mismo_plan(self):
        especificacion = importlib.util.spec_from_file_location("cargador", RAIZ / "database" / "nosql" / "03_cargar_grafo_neo4j.py")
        cargador = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(cargador)
        self.assertEqual(len(cargador.MATERIAS_DATA), len(cat.ISI.materias))
        self.assertEqual(len(cargador.PRERREQUISITOS_DATA), sum(len(m.prerrequisitos) for m in cat.ISI.materias))

    def test_el_archivo_cql_coincide_con_el_catalogo(self):
        texto = (RAIZ / "database" / "nosql" / "03_malla_curricular.cql").read_text(encoding="utf-8")
        for m in cat.ISI.materias:
            self.assertIn(f"codigo: '{m.codigo}'", texto)
        self.assertEqual(texto.count("['"), sum(len(m.prerrequisitos) for m in cat.ISI.materias))


if __name__ == "__main__":
    unittest.main()
