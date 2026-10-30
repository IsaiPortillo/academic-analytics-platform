"""Pruebas de las funciones de administración, importación, metas y reportes
personalizados (sin base de datos).

    cd backend && python -m unittest tests.test_funcionalidades -v
"""

import io
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("APP_DB_PASSWORD", "x")
os.environ.setdefault("APP_SECRET_KEY", "y")

import openpyxl  # noqa: E402

from app import catalogos, exportar, graficas, importar, indicadores, malla  # noqa: E402
from app import reporte_personalizado as rp  # noqa: E402
from app.routers import almacen, usuarios  # noqa: E402
from app.routers.asistencia import analizar_importacion_asistencia  # noqa: E402
from app.routers.calificaciones import analizar_importacion_notas  # noqa: E402
from app.routers.matricula import analizar_matricula_masiva  # noqa: E402


def _roster(*pares):
    """[(inscripcion_id, estudiante_id)] -> filas (Inscripcion, Estudiante) de mentira."""
    return [(SimpleNamespace(inscripcion_id=i), SimpleNamespace(estudiante_id=e)) for i, e in pares]


class TestLecturaDeValores(unittest.TestCase):
    def test_nota(self):
        self.assertEqual(importar.como_nota("7,25"), Decimal("7.25"))
        self.assertEqual(importar.como_nota(8.5), Decimal("8.50"))
        self.assertEqual(importar.como_nota(10), Decimal("10.00"))
        for malo in (11, -1, "abc", True, "NaN", "inf"):
            self.assertIsNone(importar.como_nota(malo), malo)

    def test_entero(self):
        self.assertEqual(importar.como_entero(5.0), 5)
        self.assertEqual(importar.como_entero(" 12 "), 12)
        for malo in (5.5, "5.5", "x", None, "", True):
            self.assertIsNone(importar.como_entero(malo), malo)

    def test_fecha(self):
        for valor in ("2025-03-04", "04/03/2025", "04-03-2025", date(2025, 3, 4)):
            self.assertEqual(importar.como_fecha(valor), date(2025, 3, 4))
        self.assertIsNone(importar.como_fecha("2025-13-40"))

    def test_csv_con_punto_y_coma_y_bom(self):
        filas = importar._leer_csv("﻿ID estudiante;Nota\n10;7,5\n".encode("utf-8"))
        self.assertEqual(filas, [["ID estudiante", "Nota"], ["10", "7,5"]])

    def test_cabecera_ausente(self):
        with self.assertRaises(importar.ErrorArchivo):
            importar.ubicar_cabecera([["Otra cosa"], ["1"]], "ID estudiante")

    def test_plantilla_ida_y_vuelta(self):
        contenido = importar.plantilla_xlsx("T", "instr", ["ID estudiante", "Nota"], [[1, None], [2, 7]],
                                            validaciones={1: ("decimal", 0, 10)})
        hoja = openpyxl.load_workbook(io.BytesIO(contenido)).active
        self.assertEqual([c.value for c in hoja[4]], ["ID estudiante", "Nota"])
        self.assertEqual(hoja["A6"].value, 2)
        self.assertEqual(len(hoja.data_validations.dataValidation), 1)
        filas = importar._leer_xlsx(contenido)
        self.assertEqual(importar.ubicar_cabecera(filas, "id estudiante"), 3)


class TestImportarNotas(unittest.TestCase):
    def setUp(self):
        self.evaluaciones = [SimpleNamespace(evaluacion_id=10, nombre_evaluacion="Parcial 1"),
                             SimpleNamespace(evaluacion_id=11, nombre_evaluacion="Parcial 2")]
        self.roster = _roster((100, 1), (101, 2), (102, 3))
        self.actuales = {(100, 10): Decimal("8.00"), (101, 10): Decimal("6.00")}

    def _analizar(self, filas):
        return analizar_importacion_notas(filas, self.evaluaciones, self.roster, self.actuales)

    def test_nueva_cambio_igual(self):
        cambios, errores = self._analizar([
            ["Notas"], ["ID estudiante", "Parcial 1 [10]", "parcial 2"],
            [1, 8, 9], [2, "6,5", None], [3, None, ""]])
        self.assertEqual(errores, [])
        tipos = {(c["estudiante_id"], c["evaluacion_id"]): c["tipo"] for c in cambios}
        self.assertEqual(tipos, {(1, 10): "igual", (1, 11): "nueva", (2, 10): "cambio"})

    def test_errores_que_impiden_aplicar(self):
        _, errores = self._analizar([
            ["ID estudiante", "Parcial 1 [10]", "Examen [99]"],
            [9, 5], [1, 12], [1, 5], ["x", 5]])
        texto = " | ".join(errores)
        for esperado in ("«Examen [99]» no corresponde", "9 no está inscrito", "no es una nota de 0 a 10",
                         "aparece más de una vez", "«x» no es válido"):
            self.assertIn(esperado, texto)


class TestImportarAsistencia(unittest.TestCase):
    def test_estados_fechas_y_errores(self):
        hoy = date.today()
        roster = _roster((100, 1), (101, 2))
        actuales = {(100, hoy - timedelta(days=1)): "PRESENTE"}
        cambios, errores = analizar_importacion_asistencia([
            ["ID estudiante", "Fecha", "Estado"],
            [1, (hoy - timedelta(days=1)).isoformat(), "ausente"],
            [2, (hoy - timedelta(days=1)).isoformat(), "Justificado"],
            [2, (hoy + timedelta(days=2)).isoformat(), "PRESENTE"],
            [1, "ayer", "PRESENTE"],
            [2, hoy.isoformat(), "TARDE"],
            [2, (hoy - timedelta(days=1)).isoformat(), "PRESENTE"],
        ], roster, actuales)
        self.assertEqual([(c["estudiante_id"], c["despues"], c["tipo"]) for c in cambios],
                         [(1, "AUSENTE", "cambio"), (2, "JUSTIFICADO", "nueva")])
        texto = " | ".join(errores)
        for esperado in ("es futura", "«ayer» no es válida", "«TARDE»", "se repite"):
            self.assertIn(esperado, texto)

    def test_fechas_fuera_del_ciclo(self):
        periodo = SimpleNamespace(codigo_periodo="2022-I", fecha_inicio=date(2022, 2, 1), fecha_fin=date(2022, 6, 25))
        cambios, errores = analizar_importacion_asistencia([
            ["ID estudiante", "Fecha", "Estado"],
            [1, "2022-03-10", "PRESENTE"],
            [2, "2024-03-10", "PRESENTE"],      # dos años después del ciclo
            [2, "2022-01-31", "AUSENTE"],       # un día antes del inicio
        ], _roster((100, 1), (101, 2)), {}, periodo)
        self.assertEqual([c["fecha"] for c in cambios], [date(2022, 3, 10)])
        self.assertEqual(len(errores), 2)
        self.assertIn("fuera del ciclo 2022-I (01/02/2022 a 25/06/2022)", errores[0])


class TestFechaDeFiltro(unittest.TestCase):
    # Antes el filtro era <input type="date">: en Edge, escribir la fecha solo
    # funcionaba con el clic justo en «dd»; si no, el navegador bloqueaba «Generar».
    def test_formatos_que_escribe_una_persona(self):
        for texto in ("01/03/2025", "1/3/2025", "01032025", "2025-03-01", "01-03-2025", "01.03.2025", " 01/03/2025 "):
            self.assertEqual(importar.fecha_de_filtro(texto), (date(2025, 3, 1), None), texto)

    def test_vacio_no_es_error(self):
        self.assertEqual(importar.fecha_de_filtro(""), (None, None))
        self.assertEqual(importar.fecha_de_filtro(None), (None, None))

    def test_lo_que_no_es_fecha_se_devuelve_para_avisar(self):
        for texto in ("31/02/2025", "99/99/9999", "abc", "01/03/25", "20/25-03-01", "01/01/0001"):
            self.assertEqual(importar.fecha_de_filtro(texto), (None, texto.strip()), texto)

    def test_el_reporte_ignora_la_fecha_mala_y_la_anota(self):
        from app.routers.reporte_personalizado import _parametros
        p = _parametros(desde="31/02/2025", hasta="15/03/2025", tema="asistencia", dimension="mes", desglose=None,
                        metrica=None, periodo_id=None, materia_id=None, docente_id=None, turno=None,
                        grafica="lineas", orden="natural", carrera_id=None)
        self.assertEqual((p.desde, p.hasta), (None, date(2025, 3, 15)))
        self.assertEqual(p.fechas_invalidas, {"desde": "31/02/2025"})


class TestFechasDelPeriodo(unittest.TestCase):
    def setUp(self):
        from app.fechas_periodo import problema_fecha
        self.problema = problema_fecha
        hoy = date.today()
        self.cerrado = SimpleNamespace(codigo_periodo="2022-I", fecha_inicio=date(2022, 2, 1),
                                       fecha_fin=date(2022, 6, 25))
        self.en_curso = SimpleNamespace(codigo_periodo="EN-CURSO", fecha_inicio=hoy - timedelta(days=30),
                                        fecha_fin=hoy + timedelta(days=60))

    def test_dentro_del_ciclo_y_bordes(self):
        for fecha in (date(2022, 2, 1), date(2022, 4, 1), date(2022, 6, 25)):
            self.assertIsNone(self.problema(self.cerrado, fecha, permitir_futura=False), fecha)

    def test_fuera_del_ciclo(self):
        self.assertIn("fuera del ciclo", self.problema(self.cerrado, date(2024, 3, 1), permitir_futura=True))

    def test_asistencia_futura_no_pero_evaluacion_programada_si(self):
        futura = date.today() + timedelta(days=10)
        self.assertIn("es futura", self.problema(self.en_curso, futura, permitir_futura=False))
        self.assertIsNone(self.problema(self.en_curso, futura, permitir_futura=True))


class TestEscalaDeGraficas(unittest.TestCase):
    def test_divisiones_redondas(self):
        casos = {(0.82, "porcentaje"): 1.0, (0.14, "porcentaje"): 0.16, (0.05, "porcentaje"): 0.08,
                 (7.3, "decimal"): 10.0, (36704, "entero"): 40000, (1234, "entero"): 1600, (0, "entero"): 1.0}
        for (maximo, tipo), tope in casos.items():
            self.assertAlmostEqual(exportar.tope_eje(maximo, tipo), tope, msg=(maximo, tipo))

    def test_un_porcentaje_nunca_pasa_de_100(self):
        self.assertEqual(exportar.tope_eje(0.99, "porcentaje"), 1.0)

    def test_marcas_sin_ceros_de_relleno(self):
        self.assertEqual([t for _, t in graficas._marcas_y(0, 1.0, "porcentaje")],
                         ["0 %", "25 %", "50 %", "75 %", "100 %"])
        self.assertEqual([t for _, t in graficas._marcas_y(0, 10.0, "decimal")], ["0", "2.5", "5", "7.5", "10"])

    def test_cada_porcentaje_explica_su_calculo(self):
        for clave_tema, tema in rp.TEMAS.items():
            for clave, metrica in tema.metricas.items():
                if metrica.tipo == "porcentaje":
                    self.assertIn("÷", metrica.ayuda, (clave_tema, clave))


class TestMatriculaMasiva(unittest.TestCase):
    def test_cupo_reactivacion_y_ya_matriculados(self):
        s1 = SimpleNamespace(seccion_id=1, cupo_maximo=2, numero_seccion=1)
        s2 = SimpleNamespace(seccion_id=2, cupo_maximo=10, numero_seccion=2)
        secciones = {("MAT115", 1): (s1, 1), ("MAT115", 2): (s2, 0)}
        existentes = {(7, 2): "RETIRADO", (8, 2): "INSCRITO"}
        cambios, errores = analizar_matricula_masiva([
            ["ID estudiante", "Materia", "Sección"],
            [5, "mat115", 1],      # ocupa el último cupo
            [6, "MAT115", 1],      # ya no hay cupo
            [7, "MAT115", 2],      # tenía un retiro: se reactiva
            [8, "MAT115", 2],      # ya matriculado
            [9, "MAT115", 3],      # sección inexistente
            [99, "MAT115", 2],     # estudiante inexistente
        ], secciones, existentes, estudiantes_validos={5, 6, 7, 8, 9})
        self.assertEqual([(c["estudiante_id"], c["tipo"]) for c in cambios],
                         [(5, "nueva"), (7, "cambio"), (8, "igual")])
        texto = " | ".join(errores)
        for esperado in ("no tiene cupo", "no hay sección 3", "99 no existe"):
            self.assertIn(esperado, texto)


class TestSemaforo(unittest.TestCase):
    def test_menor_es_mejor(self):
        self.assertEqual(indicadores.estado_meta(0.20, 0.22, 0.03), "favorable")
        self.assertEqual(indicadores.estado_meta(0.22, 0.22, 0.03), "favorable")      # en la meta
        self.assertEqual(indicadores.estado_meta(0.25, 0.22, 0.03), "en_observacion")  # en el borde
        self.assertEqual(indicadores.estado_meta(0.2501, 0.22, 0.03), "desfavorable")

    def test_mayor_es_mejor(self):
        self.assertEqual(indicadores.estado_meta(0.9, 0.85, 0.05, "mayor_mejor"), "favorable")
        self.assertEqual(indicadores.estado_meta(0.81, 0.85, 0.05, "mayor_mejor"), "en_observacion")
        self.assertEqual(indicadores.estado_meta(0.79, 0.85, 0.05, "mayor_mejor"), "desfavorable")

    def test_sin_dato(self):
        self.assertIsNone(indicadores.estado_meta(None, 0.2, 0.03))
        self.assertIsNone(indicadores.estado_meta(0.2, None, 0.03))

    def test_texto_de_la_meta(self):
        meta = {"sentido": "menor_mejor", "unidad": "porcentaje", "meta": 0.22, "tolerancia": 0.03}
        self.assertEqual(indicadores.texto_meta(meta), "Meta ≤ 22.0 % · tolerancia 3.0 pp")
        meta = {"sentido": "menor_mejor", "unidad": "dinero", "meta": 90000, "tolerancia": 10000}
        self.assertIn("90,000", indicadores.texto_meta(meta))

    def test_cada_tarjeta_tiene_su_codigo(self):
        totales = dict(costo_reprobacion=1, costo_cerradas=1, costo_repeticion=0, cerradas=1, reprobadas=0,
                       cerradas_repeticion=0, retiradas=0, estudiantes_reprobados=0, estudiantes_evaluados=1)
        codigos = [t.codigo for t in indicadores.tarjetas(indicadores.calcular(totales), None, None)]
        self.assertEqual(codigos, list(indicadores.CODIGOS_INDICADORES))


class TestCatalogos(unittest.TestCase):
    def test_tipos_limites_y_mayusculas(self):
        materias = catalogos.CATALOGOS["materias"]
        valores, errores = catalogos.leer_formulario(materias, {
            "codigo_materia": " mat999 ", "nombre": "X", "unidades_valorativas": "4", "ciclo_plan": "13",
            "carrera_id": "1"}, creando=True)
        self.assertEqual(valores["codigo_materia"], "MAT999")
        self.assertEqual(valores["activo"], False)  # casilla sin marcar
        self.assertEqual(errores, ["«Ciclo del plan» debe estar entre 1 y 12."])

    def test_obligatorios_y_opciones(self):
        docentes = catalogos.CATALOGOS["docentes"]
        _, errores = catalogos.leer_formulario(docentes, {"escalafon": "DIRECTOR", "departamento_id": "x"}, True)
        self.assertIn("«Código» es obligatorio.", errores)
        self.assertIn("«Escalafón»: valor no permitido.", errores)
        self.assertIn("«Departamento» debe ser un número entero.", errores)

    def test_periodo_fechas(self):
        _, errores = catalogos.leer_formulario(catalogos.CATALOGOS["periodos"], {
            "codigo_periodo": "2099-I", "anio": "2099", "ciclo_romano": "I",
            "fecha_inicio": "2099-05-01", "fecha_fin": "2099-04-01"}, True)
        self.assertEqual(errores, ["La fecha de fin debe ser posterior a la de inicio."])

    def test_el_carnet_solo_se_pide_al_crear(self):
        estudiantes = catalogos.CATALOGOS["estudiantes"]
        valores, _ = catalogos.leer_formulario(estudiantes, {"carnet": "ZZ1", "anio_ingreso": "2026",
                                                            "carrera_id": "1", "condicion_academica": "REGULAR"},
                                               creando=False)
        self.assertNotIn("carnet", valores)

    def test_hash_del_carnet(self):
        import hashlib
        with mock.patch.object(catalogos.settings, "carnet_clave", None):
            self.assertEqual(catalogos.hash_carnet(" us2400001 "), hashlib.sha256(b"US2400001").hexdigest())
        with mock.patch.object(catalogos.settings, "carnet_clave", "secreto"):
            con_clave = catalogos.hash_carnet("US2400001")
        self.assertNotEqual(con_clave, hashlib.sha256(b"US2400001").hexdigest())
        self.assertRegex(con_clave, r"^[0-9a-f]{64}$")   # mismo formato que valida el DW


class TestContrasenas(unittest.TestCase):
    def test_reglas(self):
        self.assertIsNone(usuarios.problema_password("Segura2026x", "ana"))
        self.assertIn("al menos", usuarios.problema_password("Corta1", "ana"))
        self.assertIn("letras y números", usuarios.problema_password("solamenteletras", "ana"))
        self.assertIn("nombre de usuario", usuarios.problema_password("xjperez2026x", "jperez"))

    def test_temporal(self):
        for _ in range(50):
            clave = usuarios.password_temporal()
            self.assertEqual(len(clave), 14)
            self.assertIsNone(usuarios.problema_password(clave, "nadie.x"))  # el punto no está en el alfabeto
            self.assertFalse(set(clave) & set("0O1lI"))


class TestReportePersonalizado(unittest.TestCase):
    def test_lo_que_no_esta_en_la_lista_blanca_se_descarta(self):
        p = rp.Parametros(tema="x' OR 1=1", dimension="grupo; DROP TABLE x", desglose="1); SELECT 1--",
                          metrica="count(*) FROM pg_shadow", grafica="<script>", orden="x", turno="X'").normalizar()
        self.assertEqual((p.tema, p.dimension, p.desglose, p.metrica, p.grafica, p.orden, p.turno),
                         ("asistencia", "mes", None, "porcentaje_asistencia", "lineas", "natural", None))

    def test_dimensiones_propias_solo_en_su_tema(self):
        self.assertEqual(rp.Parametros(tema="asistencia", dimension="motivo_retiro").normalizar().dimension, "mes")
        self.assertEqual(rp.Parametros(tema="matricula", dimension="motivo_retiro").normalizar().dimension,
                         "motivo_retiro")

    def test_el_desglose_no_repite_la_dimension(self):
        self.assertIsNone(rp.Parametros(dimension="turno", desglose="turno").normalizar().desglose)

    def test_fechas_invertidas_se_corrigen(self):
        p = rp.Parametros(desde=date(2025, 5, 1), hasta=date(2025, 1, 1)).normalizar()
        self.assertEqual((p.desde, p.hasta), (date(2025, 1, 1), date(2025, 5, 1)))

    def test_los_valores_van_como_parametros_ligados(self):
        db = mock.Mock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        p = rp.Parametros(tema="matricula", dimension="periodo", desde=date(2025, 1, 1), hasta=date(2025, 6, 30),
                          periodo_id=3, materia_id=4, docente_id=5, turno="NOCTURNO").normalizar()
        rp.consultar(db, p)
        sql, valores = str(db.execute.call_args.args[0]), db.execute.call_args.args[1]
        self.assertNotIn("NOCTURNO", sql)
        self.assertNotIn("2025", sql)
        self.assertEqual(valores, {"desde": date(2025, 1, 1), "hasta": date(2025, 7, 1), "periodo_id": 3,
                                   "materia_id": 4, "docente_id": 5, "turno": "NOCTURNO"})

    def test_tabla_cruzada_con_desglose(self):
        db = mock.Mock()
        db.execute.return_value.mappings.return_value.all.return_value = [
            {"grupo": "2022-I", "serie": "Matutino", "porcentaje_asistencia": 0.8, "marcas": 10},
            {"grupo": "2022-I", "serie": "Nocturno", "porcentaje_asistencia": 0.7, "marcas": 5},
            {"grupo": "2022-II", "serie": "Matutino", "porcentaje_asistencia": 0.9, "marcas": 10},
        ]
        p = rp.Parametros(dimension="periodo", desglose="turno", grafica="columnas").normalizar()
        reporte, resumen = rp.construir(db, p, [])
        self.assertEqual([c.etiqueta for c in reporte.columnas], ["Período", "Matutino", "Nocturno"])
        self.assertEqual(reporte.filas, [["2022-I", 0.8, 0.7], ["2022-II", 0.9, None]])
        self.assertEqual(reporte.grafico.columnas, [1, 2])
        self.assertEqual(resumen["series"], 2)

    def test_la_carrera_tambien_va_ligada(self):
        db = mock.Mock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        rp.consultar(db, rp.Parametros(carrera_id=7).normalizar())
        self.assertIn("m.carrera_id = :carrera_id", str(db.execute.call_args.args[0]))
        self.assertEqual(db.execute.call_args.args[1], {"carrera_id": 7})

    def test_cada_tema_y_agrupacion_arma_su_sql(self):
        # Ninguna dimensión deja un {fecha} sin reemplazar ni rompe el formato.
        for tema in rp.TEMAS:
            for dim in rp.dimensiones_de(tema):
                for desglose in (None, "turno"):
                    db = mock.Mock()
                    db.execute.return_value.mappings.return_value.all.return_value = []
                    rp.consultar(db, rp.Parametros(tema=tema, dimension=dim, desglose=desglose).normalizar())
                    sql = str(db.execute.call_args.args[0])
                    self.assertNotIn("{", sql, (tema, dim))

    def test_las_dimensiones_estan_en_una_seccion_del_menu(self):
        for tema in rp.TEMAS:
            agrupadas = [k for _, lista in rp.dimensiones_agrupadas(tema) for k, _ in lista]
            self.assertEqual(sorted(agrupadas), sorted(rp.dimensiones_de(tema)), tema)


class TestIdeasDeReportes(unittest.TestCase):
    def test_cada_idea_es_valida_tal_cual(self):
        # Si la lista blanca corrigiera algo, la idea mostraría otro reporte del que describe.
        for idea in rp.IDEAS:
            p = rp.Parametros(**idea.config).normalizar()
            for clave, valor in idea.config.items():
                self.assertEqual(getattr(p, clave), valor, (idea.clave, clave))

    def test_cada_idea_se_reconoce_como_ella_misma(self):
        self.assertEqual(len(rp.IDEAS_POR_CLAVE), len(rp.IDEAS))
        for idea in rp.IDEAS:
            self.assertIs(rp.idea_de(rp.Parametros(**idea.config).normalizar()), idea)

    def test_cambiar_la_grafica_deja_de_ser_la_idea(self):
        idea = rp.IDEAS_POR_CLAVE["asistencia_mes"]
        p = rp.Parametros(**{**idea.config, "grafica": "columnas"}).normalizar()
        self.assertIsNone(rp.idea_de(p))

    def test_los_filtros_no_cambian_la_idea(self):
        idea = rp.IDEAS_POR_CLAVE["retiros_motivo"]
        p = rp.Parametros(**idea.config, periodo_id=3, desde=date(2025, 1, 1)).normalizar()
        self.assertIs(rp.idea_de(p), idea)

    def test_los_pasos_describen_el_formulario(self):
        pasos = dict(rp.IDEAS_POR_CLAVE["asistencia_turno_periodo"].pasos())
        self.assertEqual(pasos, {"Tema": "Asistencia", "Agrupar por": "Período", "Comparar por": "Turno",
                                 "Métrica": "Asistencia", "Gráfica": "Columnas"})

    def test_toda_idea_explica_que_responde_y_como_leerla(self):
        for idea in rp.IDEAS:
            self.assertTrue(idea.pregunta.endswith("?"), idea.clave)
            self.assertGreater(len(idea.lectura), 60, idea.clave)
            self.assertIn(idea.categoria, rp.CATEGORIAS_IDEAS)

    def test_los_atajos_son_las_ideas_destacadas(self):
        self.assertEqual([t for t, _, _ in rp.ATAJOS],
                         ["Asistencia por mes", "Asistencia por turno y período", "Notas por materia",
                          "Retiros por motivo"])


class TestGraficas(unittest.TestCase):
    def test_lineas_con_hueco_y_texto_escapado(self):
        svg = str(graficas.lineas("T", ["<script>", "b", "c"], [("Serie", [0.5, None, 0.7])], "porcentaje"))
        self.assertEqual(svg.count("<polyline"), 2)          # el hueco corta la línea
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertIn('role="img"', svg)

    def test_columnas_varias_series_con_leyenda(self):
        svg = str(graficas.columnas("T", ["a", "b"], [("X", [1, 2]), ("Y", [3, None])], "entero"))
        self.assertEqual(svg.count("<rect"), 3)
        self.assertIn("chart-leyenda", svg)

    def test_las_notas_usan_la_escala_completa(self):
        self.assertEqual(graficas._escala([6.5, 7.0], "decimal"), (0.0, 10.0))


class TestExportarConGrafica(unittest.TestCase):
    def _reporte(self, grafico):
        columnas = [exportar.Columna("g", "Mes"), exportar.Columna("v", "Asistencia", "porcentaje")]
        return exportar.Reporte("R", "r", columnas, [("2025-01", 0.8), ("2025-02", 0.85)], [], grafico)

    def test_excel_lleva_un_grafico_nativo(self):
        for tipo in ("lineas", "columnas", "barras"):
            hoja = openpyxl.load_workbook(io.BytesIO(exportar.a_excel_bytes(
                self._reporte(exportar.Grafico(tipo, "Asistencia", "porcentaje", [1]))))).active
            self.assertEqual(len(hoja._charts), 1, tipo)

    def test_pdf_con_grafica(self):
        sin = exportar.a_pdf_bytes(self._reporte(None))
        con = exportar.a_pdf_bytes(self._reporte(exportar.Grafico("lineas", "Asistencia", "porcentaje", [1])))
        self.assertTrue(con.startswith(b"%PDF-"))
        self.assertGreater(len(con), len(sin))

    def test_muchas_barras_caben_en_la_pagina(self):
        # Antes: 40 barras horizontales medían 600 pt y la página horizontal deja
        # ~515 → reportlab LayoutError y un 500 al descargar el PDF.
        for n_columnas in (3, 8):                 # 8 columnas → página horizontal
            for series in ([1], [1, 2]):          # una serie, o varias con leyenda
                columnas = [exportar.Columna("g", "Sección")] + [
                    exportar.Columna(f"c{i}", f"M{i}", "porcentaje") for i in range(1, n_columnas)]
                filas = [[f"MAT{i:03d} s1 · 2024-I"] + [0.1 + i / 1000] * (n_columnas - 1) for i in range(194)]
                reporte = exportar.Reporte("R", "r", columnas, filas, [],
                                           exportar.Grafico("barras", "Ausencias", "porcentaje", series))
                with self.subTest(columnas=n_columnas, series=len(series)):
                    pdf = exportar.a_pdf_bytes(reporte)
                    self.assertTrue(pdf.startswith(b"%PDF-"))

    def test_tipos_de_fecha(self):
        from datetime import datetime, timezone
        self.assertEqual(exportar.formatear(date(2025, 3, 4), "fecha"), "04/03/2025")
        momento = datetime(2025, 3, 4, 15, 30, tzinfo=timezone.utc)
        self.assertRegex(exportar.formatear(momento, "fecha_hora"), r"^0[34]/03/2025 \d\d:30$")
        self.assertIsNone(exportar._numero(momento).tzinfo)   # Excel no admite zonas horarias


class TestRegistroDeValidacion(unittest.TestCase):
    def test_lee_resultado_y_fallos(self):
        texto = ("- **Fecha:** 2026-10-28 21:02\n- **Resultado:** 1 de 2 verificaciones correctas\n\n"
                 "| Grupo | Verificación | Esperado | Obtenido | Estado |\n|---|---|---|---|---|\n"
                 "| Costo | A | 1 | 1 | ✅ OK |\n| Costo | B | 2 | 3 | ❌ FALLO |\n")
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "registro.md"
            ruta.write_text(texto, encoding="utf-8")
            r = almacen.leer_registro_validacion(ruta)
        self.assertEqual((r["fecha"], r["correctas"], r["total"]), ("2026-10-28 21:02", 1, 2))
        self.assertEqual([f["verificacion"] for f in r["fallos"]], ["B"])
        self.assertEqual(r["grupos"], [{"grupo": "Costo", "correctas": 1, "total": 2}])

    def test_sin_registro(self):
        self.assertIsNone(almacen.leer_registro_validacion(Path("no-existe.md")))


class TestMalla(unittest.TestCase):
    def test_una_materia_no_se_exige_a_si_misma(self):
        m = {"codigo": "PRG115", "nombre": "P", "uv": 4, "ciclo": 1}
        with self.assertRaises(malla.ReglaMalla):
            malla.agregar(m, m)

    def test_sin_neo4j_configurado_lo_dice(self):
        with mock.patch.object(malla.settings, "neo4j_password", None), mock.patch.object(malla, "_driver", None):
            with self.assertRaises(malla.MallaNoDisponible):
                malla.leer()


if __name__ == "__main__":
    unittest.main()
