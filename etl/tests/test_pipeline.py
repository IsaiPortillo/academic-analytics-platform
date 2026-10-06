"""Pruebas de las reglas de limpieza, anonimización y cuellos de botella — SCRUM-34.

No tocan PostgreSQL ni Neo4j: construyen DataFrames pequeños con un caso por
regla, de modo que cada decisión de negocio queda fijada por una prueba.

    python -m unittest discover -s etl/tests -v
"""

import hashlib
import unittest
from datetime import date

import pandas as pd

from etl.anonimizacion import (
    ErrorAnonimizacion,
    escanear_contenido,
    validar_carnet_hash,
    validar_columnas,
    verificar_anonimizacion,
)
from etl.grafo import clasificar_cuellos_de_botella
from etl.transformacion import (
    APROBADO,
    EN_CURSO,
    REPROBADO,
    RETIRADO,
    SIN_CALIFICAR,
    SIN_CIERRE,
    SIN_EVALUACIONES,
    ErrorIntegridad,
    transformar,
)

FECHA_CORTE = date(2025, 10, 1)


def _hash(carnet: str) -> str:
    return hashlib.sha256(carnet.encode()).hexdigest()


def _datos_base():
    """Periodo 1 cerrado, periodo 2 vigente a FECHA_CORTE. Una inscripción por regla."""
    estudiantes = pd.DataFrame({
        "estudiante_id": [1, 2, 3, 4],
        "carnet_hash": [_hash(f"US2300{i}01") for i in range(4)],
        "anio_ingreso": [2023] * 4,
        "carrera_id": [1] * 4,
        "trabaja": [False, True, False, False],
        "condicion_academica": ["REGULAR"] * 4,
        "activo": [True] * 4,
    })
    materias = pd.DataFrame({
        "materia_id": [10, 20, 30],
        "codigo_materia": ["PRG115", "PRG215", "ZZZ999"],
        "nombre": ["Programación I", "Programación II", "Materia fuera de la malla"],
        "unidades_valorativas": [4, 3, 4],
        "ciclo_plan": [1, 2, 3],
        "carrera_id": [1, 1, 1],
        "activo": [True, True, True],
    })
    periodos = pd.DataFrame({
        "periodo_id": [1, 2],
        "codigo_periodo": ["2025-I", "2025-II"],
        "anio": [2025, 2025],
        "ciclo_romano": ["I", "II"],
        "fecha_inicio": [date(2025, 2, 1), date(2025, 8, 1)],
        "fecha_fin": [date(2025, 6, 25), date(2025, 12, 15)],
    })
    secciones = pd.DataFrame({
        "seccion_id": [100, 200, 300, 400],
        "materia_id": [10, 20, 30, 10],
        "docente_id": [1, 1, 1, 1],
        "periodo_id": [1, 1, 1, 2],
        "numero_seccion": [1, 1, 1, 1],
        "turno": ["MATUTINO"] * 4,
        "cupo_maximo": [45] * 4,
    })
    # id: caso
    #  1 aprobado con nota completa      5 retirado
    #  2 reprobado                       6 sección sin evaluaciones
    #  3 aprobado con una nota faltante  7 INSCRITO en periodo cerrado
    #  4 finalizado sin ninguna nota     8 INSCRITO en periodo vigente
    inscripciones = pd.DataFrame({
        "inscripcion_id": [1, 2, 3, 4, 5, 6, 7, 8],
        "estudiante_id": [1, 2, 3, 4, 4, 1, 2, 3],
        "seccion_id": [100, 100, 200, 200, 100, 300, 200, 400],
        "fecha_inscripcion": pd.Timestamp("2025-01-20", tz="UTC"),
        "numero_intento": [1, 2, 1, 1, 1, 1, 1, 1],
        "estado_inscripcion": ["FINALIZADO", "FINALIZADO", "FINALIZADO", "FINALIZADO",
                               "RETIRADO", "FINALIZADO", "INSCRITO", "INSCRITO"],
    })
    notas = pd.DataFrame({
        "inscripcion_id": [1, 2, 3, 4, 5, 6, 7, 8],
        "evaluaciones": [4, 4, 4, 4, 4, 0, 4, 4],
        "evaluaciones_calificadas": [4, 4, 3, 0, 1, 0, 0, 1],
        "ponderacion_evaluada": [100.0, 100, 100, 100, 100, 0, 100, 100],
        "ponderacion_calificada": [100.0, 100, 70, 0, 25, 0, 0, 25],
        "nota_final": [8.5, 4.2, 6.3, 0.0, 1.5, 0.0, 0.0, 2.0],
    })
    asistencia = pd.DataFrame({
        "inscripcion_id": [1, 2],
        "sesiones": [10, 10],
        "presentes": [9, 5],
        "ausentes": [1, 4],
        "justificados": [0, 1],
    })
    metricas = pd.DataFrame({
        "codigo_materia": ["PRG115", "PRG215", "PRG315", "DWB115"],
        "area": ["Desarrollo de Software"] * 4,
        "dependientes_directos": [1, 1, 1, 0],
        "dependientes_indirectos": [2, 1, 0, 0],
        "dependientes_totales": [3, 2, 1, 0],
        "prerrequisitos_directos": [0, 1, 1, 1],
        "longitud_cascada": [3, 2, 1, 0],
        "profundidad_prerrequisitos": [0, 1, 2, 3],
    })
    carreras = pd.DataFrame({
        "carrera_id": [1], "codigo_carrera": ["I10515"],
        "nombre_carrera": ["Ingeniería de Sistemas Informáticos"], "departamento_id": [1],
        "codigo_departamento": ["DIA"], "nombre_departamento": ["Ingeniería y Arquitectura"],
    })
    docentes = pd.DataFrame({
        "docente_id": [1], "escalafon": ["TITULAR"], "departamento_id": [1],
        "codigo_departamento": ["DIA"], "nombre_departamento": ["Ingeniería y Arquitectura"],
        "activo": [True],
    })
    costos_periodo = pd.DataFrame({
        "periodo_id": [1, 2], "costo_por_uv": [25.0, 30.0], "moneda": ["USD", "USD"],
        "fuente_costo": ["SUPUESTO PARAMETRICO", "SUPUESTO PARAMETRICO"],
    })
    # Costo de la materia en el período = UV × costo por UV (como la vista del OLTP).
    costos_materia = (
        materias[["materia_id", "unidades_valorativas"]].merge(costos_periodo, how="cross")
        .assign(costo_materia=lambda d: d["unidades_valorativas"] * d["costo_por_uv"])
        [["materia_id", "periodo_id", "costo_materia"]]
    )
    return {
        "estudiantes": estudiantes, "materias": materias, "periodos": periodos,
        "secciones": secciones, "inscripciones": inscripciones, "notas": notas,
        "asistencia": asistencia, "carreras": carreras, "docentes": docentes,
        "costos_periodo": costos_periodo, "costos_materia": costos_materia,
    }, metricas


class TestLimpiezaInscripciones(unittest.TestCase):
    def setUp(self):
        datos, metricas = _datos_base()
        self.resultado = transformar(datos, metricas, FECHA_CORTE)
        self.h = self.resultado.datasets["hechos_inscripcion"].set_index("inscripcion_id")

    def test_clasificacion_de_cada_caso(self):
        esperado = {1: APROBADO, 2: REPROBADO, 3: APROBADO, 4: SIN_CALIFICAR,
                    5: RETIRADO, 6: SIN_EVALUACIONES, 7: SIN_CIERRE, 8: EN_CURSO}
        self.assertEqual(self.h["resultado"].to_dict(), esperado)

    def test_solo_resultados_cerrados_llevan_nota(self):
        con_nota = set(self.h.index[self.h["nota_final"].notna()])
        self.assertEqual(con_nota, {1, 2, 3})

    def test_retirado_no_se_imputa_como_cero(self):
        self.assertTrue(pd.isna(self.h.loc[5, "nota_final"]))
        self.assertTrue(pd.isna(self.h.loc[5, "aprobado"]))

    def test_nota_faltante_cuenta_como_cero_y_se_marca(self):
        self.assertEqual(self.h.loc[3, "nota_final"], 6.3)
        self.assertFalse(self.h.loc[3, "nota_completa"])
        self.assertEqual(self.h.loc[3, "evaluaciones_sin_nota"], 1)
        self.assertTrue(self.h.loc[1, "nota_completa"])

    def test_sin_asistencia_registrada_no_es_cero_por_ciento(self):
        self.assertEqual(self.h.loc[1, "porcentaje_asistencia"], 90.0)
        self.assertEqual(self.h.loc[3, "sesiones"], 0)
        self.assertTrue(pd.isna(self.h.loc[3, "porcentaje_asistencia"]))

    def test_costo_de_reprobacion_solo_en_reprobados(self):
        # PRG115 en 2025-I: 4 UV × $25 = $100.
        self.assertEqual(self.h.loc[2, "costo_inscripcion"], 100.0)
        self.assertEqual(self.h.loc[2, "costo_reprobacion"], 100.0)
        # Aprobado y retirado tienen costo invertido, pero no costo de reprobación.
        self.assertEqual(self.h.loc[1, "costo_reprobacion"], 0.0)
        self.assertEqual(self.h.loc[5, "costo_inscripcion"], 100.0)
        self.assertEqual(self.h.loc[5, "costo_reprobacion"], 0.0)
        # El costo usa el costo por UV del período: PRG115 en 2025-II = 4 × $30.
        self.assertEqual(self.h.loc[8, "costo_inscripcion"], 120.0)

    def test_repeticion(self):
        self.assertTrue(self.h.loc[2, "es_repeticion"])
        self.assertFalse(self.h.loc[1, "es_repeticion"])

    def test_costo_de_repeticion_solo_en_reintentos(self):
        # Inscripción 2: numero_intento = 2, PRG115 en 2025-I = 4 UV × $25.
        self.assertEqual(self.h.loc[2, "costo_repeticion"], 100.0)
        # Primer intento: cuesta, pero no es costo de repetición.
        self.assertEqual(self.h.loc[1, "costo_inscripcion"], 100.0)
        self.assertEqual(self.h.loc[1, "costo_repeticion"], 0.0)
        # Nunca es mayor que la inversión de la inscripción.
        self.assertTrue((self.h["costo_repeticion"] <= self.h["costo_inscripcion"]).all())

    def test_repeticion_aprobada_cuesta_repeticion_pero_no_reprobacion(self):
        # Una repetición que se aprueba es costo de repetición y NO de reprobación:
        # las dos medidas no son excluyentes, pero tampoco son la misma.
        datos, metricas = _datos_base()
        datos["inscripciones"].loc[0, "numero_intento"] = 2   # inscripción 1: aprobada
        h = transformar(datos, metricas, FECHA_CORTE).datasets["hechos_inscripcion"].set_index("inscripcion_id")
        self.assertEqual(h.loc[1, "resultado"], APROBADO)
        self.assertEqual(h.loc[1, "costo_repeticion"], 100.0)
        self.assertEqual(h.loc[1, "costo_reprobacion"], 0.0)

    def test_inscripcion_con_seccion_inexistente_detiene_el_pipeline(self):
        datos, metricas = _datos_base()
        datos["inscripciones"].loc[0, "seccion_id"] = 999
        with self.assertRaises(ErrorIntegridad):
            transformar(datos, metricas, FECHA_CORTE)


class TestPatronDeRiesgo(unittest.TestCase):
    """Fase 4.2: nota final < 6.00 Y 3 o más ausencias, los umbrales del
    sistema transaccional. Las dos condiciones a la vez, nunca una sola."""

    def _hechos(self, ajustar=None):
        datos, metricas = _datos_base()
        if ajustar:
            ajustar(datos)
        r = transformar(datos, metricas, FECHA_CORTE)
        return r.datasets["hechos_inscripcion"].set_index("inscripcion_id")

    def test_reprobado_con_faltas_presenta_el_patron(self):
        # Inscripción 2: REPROBADO con 4 ausencias.
        self.assertTrue(self._hechos().loc[2, "patron_riesgo"])

    def test_faltas_sin_reprobar_no_es_patron(self):
        def aprobado_con_faltas(d):
            d["asistencia"].loc[d["asistencia"]["inscripcion_id"] == 1, "ausentes"] = 5
        self.assertFalse(self._hechos(aprobado_con_faltas).loc[1, "patron_riesgo"])

    def test_reprobar_con_pocas_faltas_no_es_patron(self):
        def dos_faltas(d):
            d["asistencia"].loc[d["asistencia"]["inscripcion_id"] == 2, "ausentes"] = 2
        self.assertFalse(self._hechos(dos_faltas).loc[2, "patron_riesgo"])

    def test_justo_en_el_umbral_si_es_patron(self):
        def tres_faltas(d):
            d["asistencia"].loc[d["asistencia"]["inscripcion_id"] == 2, "ausentes"] = 3
        self.assertTrue(self._hechos(tres_faltas).loc[2, "patron_riesgo"])

    def test_retirado_con_faltas_no_es_patron(self):
        def retirado_con_faltas(d):
            d["asistencia"].loc[len(d["asistencia"])] = [5, 10, 2, 8, 0]
        self.assertFalse(self._hechos(retirado_con_faltas).loc[5, "patron_riesgo"])

    def test_el_turno_viene_de_la_seccion(self):
        def nocturno(d):
            d["secciones"].loc[d["secciones"]["seccion_id"] == 100, "turno"] = "NOCTURNO"
        h = self._hechos(nocturno)
        self.assertEqual(h.loc[1, "turno"], "NOCTURNO")
        self.assertEqual(h.loc[3, "turno"], "MATUTINO")

    def test_area_viene_del_grafo_y_se_rotula_si_falta(self):
        datos, metricas = _datos_base()
        m = transformar(datos, metricas, FECHA_CORTE).datasets["materias"].set_index("codigo_materia")
        self.assertEqual(m.loc["PRG115", "area"], "Desarrollo de Software")
        self.assertEqual(m.loc["ZZZ999", "area"], "Sin área en la malla")


class TestEstudiantePeriodo(unittest.TestCase):
    def setUp(self):
        datos, metricas = _datos_base()
        r = transformar(datos, metricas, FECHA_CORTE)
        self.ep = r.datasets["estudiante_periodo"].set_index(["estudiante_id", "periodo_id"])
        self.e = r.datasets["estudiantes"].set_index("estudiante_id")

    def test_promedio_ponderado_por_uv_sobre_materias_cerradas(self):
        # Estudiante 1, periodo 1: PRG115 (4 UV, 8.5) cerrada; ZZZ999 sin evaluaciones no cuenta.
        self.assertEqual(self.ep.loc[(1, 1), "promedio_periodo"], 8.5)

    def test_estudiante_sin_actividad_en_el_periodo(self):
        # Estudiante 4: una materia sin calificar y otra retirada, sin asistencia.
        fila = self.ep.loc[(4, 1)]
        self.assertFalse(fila["con_actividad"])
        self.assertTrue(pd.isna(fila["promedio_periodo"]))
        self.assertEqual(fila["materias_retiradas"], 1)

    def test_no_se_fabrican_filas_para_periodos_sin_inscripcion(self):
        self.assertNotIn((4, 2), self.ep.index)

    def test_en_curso_cuenta_como_actividad(self):
        self.assertTrue(self.ep.loc[(3, 2), "con_actividad"])

    def test_dimension_conserva_estudiantes_sin_actividad(self):
        self.assertTrue(self.e.loc[4, "sin_actividad"])
        self.assertEqual(self.e.loc[4, "periodos_inscritos"], 1)
        self.assertEqual(self.e.loc[3, "ultimo_periodo_activo"], "2025-II")


class TestMateriasYGrafo(unittest.TestCase):
    def test_umbral_de_cuello_de_botella(self):
        # 4 materias: bloquear 1 de las otras 3 (33 %) ya supera el 25 %.
        _, metricas = _datos_base()
        c = clasificar_cuellos_de_botella(metricas).set_index("codigo_materia")
        self.assertEqual(c.loc["PRG115", "indice_bloqueo"], 1.0)
        self.assertTrue(c.loc["PRG315", "es_cuello_botella"])
        self.assertFalse(c.loc["DWB115", "es_cuello_botella"])

    def test_cruce_relacional_grafo(self):
        datos, metricas = _datos_base()
        r = transformar(datos, metricas, FECHA_CORTE)
        m = r.datasets["materias"].set_index("codigo_materia")
        self.assertFalse(m.loc["ZZZ999", "en_grafo"])
        self.assertEqual(m.loc["ZZZ999", "dependientes_totales"], 0)
        # PRG115: 1 aprobada + 1 reprobada cerradas -> 50 % × 3 dependientes.
        self.assertEqual(m.loc["PRG115", "tasa_reprobacion"], 0.5)
        self.assertEqual(m.loc["PRG115", "indice_impacto"], 1.5)
        self.assertEqual(r.calidad["materias_sin_nodo_en_grafo"], ["ZZZ999"])
        self.assertEqual(r.calidad["nodos_de_grafo_sin_materia_en_oltp"], ["DWB115", "PRG315"])


class TestAnonimizacion(unittest.TestCase):
    def setUp(self):
        datos, metricas = _datos_base()
        self.datasets = transformar(datos, metricas, FECHA_CORTE).datasets

    def test_salida_limpia_pasa(self):
        verificar_anonimizacion(self.datasets, comprobar_permisos=False)

    def test_columna_no_autorizada_se_rechaza(self):
        self.datasets["estudiantes"]["nombre"] = "Ana Pérez"
        self.assertTrue(validar_columnas(self.datasets))
        with self.assertRaises(ErrorAnonimizacion):
            verificar_anonimizacion(self.datasets, comprobar_permisos=False)

    def test_carnet_en_claro_dentro_de_carnet_hash_se_rechaza(self):
        self.datasets["estudiantes"].loc[0, "carnet_hash"] = "US2300001"
        self.assertTrue(validar_carnet_hash(self.datasets["estudiantes"]))
        self.assertTrue(escanear_contenido(self.datasets))

    def test_correo_en_cualquier_columna_de_texto_se_rechaza(self):
        self.datasets["materias"].loc[0, "nombre"] = "contacto: ana@ues.edu.sv"
        self.assertTrue(escanear_contenido(self.datasets))

    def test_docentes_sin_codigo_ni_nombre(self):
        self.assertNotIn("codigo_docente", self.datasets["docentes"].columns)
        self.datasets["docentes"]["nombre"] = "Pedro Pérez"
        self.assertTrue(validar_columnas(self.datasets))

    def test_codigos_de_materia_y_periodo_no_son_falsos_positivos(self):
        self.assertEqual(escanear_contenido(self.datasets), [])


if __name__ == "__main__":
    unittest.main()


class TestPreparacionDW(unittest.TestCase):
    """La traducción al modelo estrella (etl/carga.py), sin tocar la base."""

    def setUp(self):
        from etl.carga import preparar_tablas
        datos, metricas = _datos_base()
        self.tablas = preparar_tablas(transformar(datos, metricas, FECHA_CORTE))
        self.fact = self.tablas["fact_inscripcion"].set_index("inscripcion_id")

    def test_toda_inscripcion_llega_a_los_hechos_con_sus_llaves(self):
        self.assertEqual(len(self.fact), 8)
        llaves = ["periodo_key", "materia_key", "estudiante_key", "carrera_key"]
        self.assertFalse(self.fact[llaves].isna().any().any())

    def test_banderas_y_costo_cumplen_el_check_del_ddl(self):
        # Mismo invariante que chk_costo_reprobacion en 10_dw_academico.sql.
        f = self.fact
        valido = (f["costo_reprobacion"] == 0) | (
            f["reprobado"] & (f["costo_reprobacion"] == f["costo_inscripcion"]))
        self.assertTrue(valido.all())
        self.assertEqual(f["reprobado"].sum(), 1)
        self.assertEqual(f["cerrada"].sum(), 3)
        self.assertTrue(f.loc[5, "retirado"])

    def test_periodos_ordenados_y_con_costo(self):
        p = self.tablas["dim_periodo"].set_index("codigo_periodo")
        self.assertEqual(p.loc["2025-I", "orden"], 1)
        self.assertEqual(p.loc["2025-II", "costo_por_uv"], 30.0)

    def test_dimensiones_de_docente_y_seccion(self):
        docente = self.tablas["dim_docente"]
        self.assertEqual(len(docente), 1)
        self.assertNotIn("codigo_docente", docente.columns)
        seccion = self.tablas["dim_seccion"].set_index("seccion_id")
        self.assertEqual(len(seccion), 4)
        # La sección 400 es PRG115 en 2025-II: legible por sí sola.
        self.assertEqual(seccion.loc[400, "codigo_materia"], "PRG115")
        self.assertEqual(seccion.loc[400, "codigo_periodo"], "2025-II")

    def test_cada_hecho_apunta_a_su_seccion_y_docente(self):
        f = self.fact
        secciones = self.tablas["dim_seccion"].set_index("seccion_key")["seccion_id"]
        # Inscripción 8 está en la sección 400.
        self.assertEqual(secciones[f.loc[8, "seccion_key"]], 400)
        self.assertFalse(f[["seccion_key", "docente_key"]].isna().any().any())

    def test_costo_repeticion_cumple_el_check_del_ddl(self):
        # Mismo invariante que chk_costo_repeticion en 13_dw_cierre_scrum35.sql.
        f = self.fact
        valido = (f["costo_repeticion"] == 0) | (
            f["es_repeticion"] & (f["costo_repeticion"] == f["costo_inscripcion"]))
        self.assertTrue(valido.all())
        self.assertEqual(f["costo_repeticion"].sum(), 100.0)

    def test_hecho_con_seccion_inexistente_en_la_dimension_detiene_la_carga(self):
        from etl.carga import preparar_tablas
        datos, metricas = _datos_base()
        r = transformar(datos, metricas, FECHA_CORTE)
        r.datasets["secciones"] = r.datasets["secciones"][r.datasets["secciones"]["seccion_id"] != 100]
        with self.assertRaises(ErrorIntegridad):
            preparar_tablas(r)

    def test_dimension_de_estudiante_sin_datos_identificables(self):
        columnas = set(self.tablas["dim_estudiante"].columns)
        self.assertNotIn("nombre", columnas)
        self.assertIn("carnet_hash", columnas)
