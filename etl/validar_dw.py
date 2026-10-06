"""Validación de datos y procesos del Data Warehouse — Fases 3.3, 4.1 y 4.2.

Reconcilia lo que muestra el dashboard contra fuentes independientes, y deja
un registro fechado para la memoria (docs/validacion/registro_validacion.md):

  - Contra el OLTP, con SQL escrito aquí y no con el código del ETL: conteos,
    costo de reprobación.
  - Contra los reportes del sistema transaccional (SCRUM-10/25), llamando a sus
    mismas funciones: tasa de reprobación y patrón de riesgo, inscripción por
    inscripción. Es lo que exige el criterio "el dashboard y el sistema
    transaccional deben medir lo mismo con los mismos números".
  - Contra un segundo cálculo: la correlación de PostgreSQL contra pandas.
  - Consistencia interna: cada segmentación reparte exactamente el total.
  - Seguridad: aislamiento de rol_dashboard y anonimización del DW.

Además registra observaciones sobre los datos (cobertura de asistencia,
relaciones que el generador sintético no modela) que la memoria debe declarar.

    python -m etl.validar_dw

Sale con código distinto de cero si alguna verificación falla.
"""

import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from sqlalchemy.exc import DBAPIError

from .conexiones import _backend_en_path, engine_carga, sesion_grafo, sesion_oltp
from .config import RAIZ_PROYECTO, ErrorConfiguracion

REGISTRO = RAIZ_PROYECTO / "docs" / "validacion" / "registro_validacion.md"
TOLERANCIA = 1e-9

_backend_en_path()
from app import calculos, dw  # noqa: E402
from app.routers import reportes  # noqa: E402
from app.verificar_dw import verificar_sin_acceso_oltp, verificar_solo_lectura_dw  # noqa: E402


@dataclass
class Resultado:
    grupo: str
    nombre: str
    esperado: str
    obtenido: str
    ok: bool


resultados: list[Resultado] = []
observaciones: list[str] = []


def registrar(grupo, nombre, esperado, obtenido, ok=None):
    ok = (esperado == obtenido) if ok is None else ok
    resultados.append(Resultado(grupo, nombre, str(esperado), str(obtenido), bool(ok)))
    marca = "OK   " if ok else "FALLO"
    print(f"  [{marca}] {grupo} · {nombre}: esperado {esperado} · obtenido {obtenido}")


def _escalar(sesion, sql, **params):
    return sesion.execute(text(sql), params).scalar()


def _df(sesion, sql, **params):
    return pd.read_sql(text(sql), sesion.connection(), params=params)


# ---------------------------------------------------------------------------
# 1. Completitud del DW frente al OLTP
# ---------------------------------------------------------------------------

def validar_completitud(s):
    pares = [
        ("Inscripciones → fact_inscripcion", "academico_oltp.inscripciones", "dw_academico.fact_inscripcion"),
        ("Estudiantes → dim_estudiante", "academico_oltp.estudiantes", "dw_academico.dim_estudiante"),
        ("Materias → dim_materia", "academico_oltp.materias", "dw_academico.dim_materia"),
        ("Períodos → dim_periodo", "academico_oltp.periodos_academicos", "dw_academico.dim_periodo"),
        ("Docentes → dim_docente", "academico_oltp.docentes", "dw_academico.dim_docente"),
        ("Secciones → dim_seccion", "academico_oltp.secciones", "dw_academico.dim_seccion"),
    ]
    for nombre, origen, destino in pares:
        registrar("Completitud", nombre,
                  _escalar(s, f"SELECT count(*) FROM {origen}"),
                  _escalar(s, f"SELECT count(*) FROM {destino}"))


# ---------------------------------------------------------------------------
# 2. Costo de reprobación contra un cálculo independiente sobre el OLTP
# ---------------------------------------------------------------------------

COSTO_OLTP = """
WITH nota AS (
    SELECT i.inscripcion_id, s.materia_id, s.periodo_id,
           ROUND(COALESCE(SUM(c.nota * e.porcentaje / 100), 0), 2) AS nota,
           COALESCE(SUM(e.porcentaje), 0) AS ponderacion
    FROM academico_oltp.inscripciones i
    JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
    LEFT JOIN academico_oltp.evaluaciones e ON e.seccion_id = s.seccion_id
    LEFT JOIN academico_oltp.calificaciones c
           ON c.inscripcion_id = i.inscripcion_id AND c.evaluacion_id = e.evaluacion_id
    WHERE i.estado_inscripcion = 'FINALIZADO'
    GROUP BY i.inscripcion_id, s.materia_id, s.periodo_id
    HAVING COUNT(c.calificacion_id) > 0
)
SELECT COUNT(*) AS reprobadas, SUM(m.unidades_valorativas * cu.costo_por_uv) AS costo
FROM nota n
JOIN academico_oltp.materias m ON m.materia_id = n.materia_id
JOIN academico_oltp.costos_uv cu ON cu.periodo_id = n.periodo_id
WHERE n.ponderacion > 0 AND n.nota < :umbral
"""


COSTO_INSCRIPCIONES_OLTP = """
SELECT COUNT(*) AS inscripciones, SUM(m.unidades_valorativas * cu.costo_por_uv) AS costo
FROM academico_oltp.inscripciones i
JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
JOIN academico_oltp.costos_uv cu ON cu.periodo_id = s.periodo_id
WHERE {filtro}
"""


def validar_costo(s):
    oltp = s.execute(text(COSTO_OLTP), {"umbral": calculos.UMBRAL_NOTA_APROBACION}).one()
    dw_ = s.execute(text(
        "SELECT COUNT(*) FILTER (WHERE reprobado), SUM(costo_reprobacion) "
        "FROM dw_academico.fact_inscripcion"
    )).one()
    registrar("Costo", "Inscripciones reprobadas (OLTP independiente vs DW)", oltp[0], dw_[0])
    registrar("Costo", "Costo de reprobación total en USD (OLTP independiente vs DW)",
              f"{float(oltp[1]):,.2f}", f"{float(dw_[1]):,.2f}")

    # Las otras dos medidas de costo (SCRUM-35): matrícula (todas las
    # inscripciones) y repetición (numero_intento > 1), con SQL propio sobre el
    # OLTP. Ninguna depende de la nota, así que no hace falta reproducir la
    # clasificación del ETL: solo UV × costo por UV de cada inscripción.
    for nombre, filtro, columna, condicion_dw in (
        ("matrícula", "TRUE", "costo_inscripcion", "TRUE"),
        ("repetición", "i.numero_intento > 1", "costo_repeticion", "es_repeticion"),
    ):
        oltp = s.execute(text(COSTO_INSCRIPCIONES_OLTP.format(filtro=filtro))).one()
        dw_ = s.execute(text(
            f"SELECT COUNT(*) FILTER (WHERE {condicion_dw}), SUM({columna}) "
            "FROM dw_academico.fact_inscripcion"
        )).one()
        registrar("Costo", f"Inscripciones con costo de {nombre} (OLTP independiente vs DW)",
                  oltp[0], dw_[0])
        registrar("Costo", f"Costo de {nombre} total en USD (OLTP independiente vs DW)",
                  f"{float(oltp[1]):,.2f}", f"{float(dw_[1]):,.2f}")

    registrar("Costo", "Costo de repetición nunca supera el costo de la inscripción (filas que lo violan)",
              0, _escalar(s, "SELECT count(*) FROM dw_academico.fact_inscripcion "
                             "WHERE costo_repeticion > costo_inscripcion"))


def validar_mart_departamento(s):
    """El data mart por departamento debe repartir exactamente cada medida."""
    medidas = ("costo_matricula_materia", "costo_reprobacion", "costo_repeticion")
    total = s.execute(text(
        "SELECT SUM(costo_inscripcion), SUM(costo_reprobacion), SUM(costo_repeticion) "
        "FROM dw_academico.fact_inscripcion")).one()
    mart = s.execute(text(
        "SELECT SUM(costo_matricula_materia), SUM(costo_reprobacion), SUM(costo_repeticion) "
        "FROM dw_academico.v_mart_departamento")).one()
    for nombre, esperado, obtenido in zip(medidas, total, mart):
        registrar("Data mart", f"Suma por departamento = total ({nombre})",
                  f"{float(esperado):,.2f}", f"{float(obtenido):,.2f}")
    sin_depto = _escalar(s, "SELECT count(*) FROM dw_academico.v_mart_departamento "
                            "WHERE codigo_departamento IS NULL")
    registrar("Data mart", "Filas del mart sin departamento", 0, sin_depto)


# ---------------------------------------------------------------------------
# 3. Mismos números que el sistema transaccional (reportes SCRUM-10 y SCRUM-25)
# ---------------------------------------------------------------------------

def _dw_por_periodo(s, periodo_id):
    # El DW no guarda el número de sección (no es insumo de ningún análisis),
    # pero sí inscripcion_id como dimensión degenerada: con él se recupera la
    # sección del OLTP para comparar contra los reportes caso por caso. Hace
    # falta porque un estudiante puede estar en dos secciones de la misma
    # materia en un mismo período (ver observaciones).
    return _df(s, """
        SELECT e.estudiante_id, m.codigo_materia, sec.numero_seccion,
               f.reprobado, f.cerrada, f.patron_riesgo
        FROM dw_academico.fact_inscripcion f
        JOIN dw_academico.dim_periodo p ON p.periodo_key = f.periodo_key
        JOIN dw_academico.dim_materia m ON m.materia_key = f.materia_key
        JOIN dw_academico.dim_estudiante e ON e.estudiante_key = f.estudiante_key
        JOIN academico_oltp.inscripciones i ON i.inscripcion_id = f.inscripcion_id
        JOIN academico_oltp.secciones sec ON sec.seccion_id = i.seccion_id
        WHERE p.periodo_id = :periodo_id
    """, periodo_id=periodo_id)


def validar_contra_reportes(s):
    periodos = _df(s, "SELECT periodo_id, codigo_periodo FROM academico_oltp.periodos_academicos "
                      "ORDER BY fecha_inicio")
    total_tasa_ok = total_patron_ok = True
    detalle_patron = []
    for periodo_id, codigo in periodos.itertuples(index=False):
        dw_ = _dw_por_periodo(s, periodo_id)

        # Notas finales del reporte: FINALIZADO con todas sus evaluaciones calificadas.
        notas = [f for f in reportes.consultar_notas_finales(s, periodo_id, limite=None)
                 if f.estado_inscripcion == "FINALIZADO" and f.ponderacion_evaluada
                 and f.ponderacion_calificada >= f.ponderacion_evaluada]
        rep_reprobadas = sum(1 for f in notas if f.nota_final < calculos.UMBRAL_NOTA_APROBACION)
        esperado = f"{rep_reprobadas}/{len(notas)}"
        obtenido = f"{int(dw_['reprobado'].sum())}/{int(dw_['cerrada'].sum())}"
        total_tasa_ok &= esperado == obtenido
        registrar("Sistema transaccional", f"Reprobadas/cerradas {codigo} (reporte de notas vs DW)",
                  esperado, obtenido)

        # Patrón de riesgo: intersección de los dos reportes del coordinador.
        # Clave: estudiante + materia + sección, que identifica una inscripción.
        reprobados = Counter((f.estudiante_id, f.codigo_materia, f.numero_seccion) for f in notas
                             if f.nota_final < calculos.UMBRAL_NOTA_APROBACION)
        faltas = Counter((f.estudiante_id, f.codigo_materia, f.numero_seccion) for f in
                         reportes.consultar_asistencia_acumulada(s, periodo_id, solo_riesgo=True,
                                                                 limite=None)
                         if f.estado_inscripcion == "FINALIZADO")
        esperado_patron = reprobados & faltas
        con_patron = dw_[dw_["patron_riesgo"]]
        obtenido_patron = Counter(zip(con_patron["estudiante_id"], con_patron["codigo_materia"],
                                      con_patron["numero_seccion"]))
        iguales = esperado_patron == obtenido_patron
        total_patron_ok &= iguales
        detalle_patron.append((codigo, sum(esperado_patron.values()), sum(obtenido_patron.values())))
        registrar("Patrón de riesgo",
                  f"{codigo}: inscripciones con nota < {calculos.UMBRAL_NOTA_APROBACION} y "
                  f"≥ {calculos.UMBRAL_FALTAS_RIESGO} ausencias (reportes vs DW, caso por caso)",
                  sum(esperado_patron.values()), sum(obtenido_patron.values()), iguales)
    return total_tasa_ok, total_patron_ok


def validar_umbrales():
    _backend_en_path()
    from etl import transformacion  # noqa: PLC0415
    registrar("Umbrales", "Reporte de asistencia y calculos.py usan el mismo umbral de faltas",
              "mismo objeto", "mismo objeto" if reportes.UMBRAL_FALTAS_RIESGO is
              calculos.UMBRAL_FALTAS_RIESGO else "copias distintas")
    registrar("Umbrales", "ETL usa el umbral de faltas del sistema transaccional",
              calculos.UMBRAL_FALTAS_RIESGO, transformacion.UMBRAL_FALTAS_RIESGO)
    registrar("Umbrales", "ETL usa el umbral de aprobación del sistema transaccional",
              float(calculos.UMBRAL_NOTA_APROBACION), transformacion.UMBRAL_APROBACION)


# ---------------------------------------------------------------------------
# 4. Correlaciones: PostgreSQL (lo que muestra el dashboard) contra pandas
# ---------------------------------------------------------------------------

def validar_correlaciones(s):
    del_dashboard = dw.correlaciones(dw.Filtros())  # vía rol_dashboard, igual que la pantalla
    filas = _df(s, "SELECT porcentaje_asistencia AS asistencia, nota_final AS nota, "
                   "numero_intento AS intento, costo_reprobacion AS costo "
                   "FROM dw_academico.fact_inscripcion WHERE cerrada").astype(float)
    peor = 0.0
    for par in del_dashboard.itertuples():
        independiente = filas[[par.x, par.y]].dropna()
        r_pandas = independiente[par.x].corr(independiente[par.y])
        peor = max(peor, abs(r_pandas - par.r))
        registrar("Correlaciones", f"r({par.x}, {par.y}) PostgreSQL vs pandas",
                  f"{r_pandas:+.6f} (n={len(independiente):,})", f"{par.r:+.6f} (n={par.n:,})",
                  abs(r_pandas - par.r) < 1e-6 and len(independiente) == par.n)
    return del_dashboard


# ---------------------------------------------------------------------------
# 5. Consistencia interna: cada segmentación reparte exactamente el total
# ---------------------------------------------------------------------------

def validar_particiones():
    total = dw.totales(dw.Filtros())
    esperado = f"{int(total['reprobadas'])}/{int(total['cerradas'])}"
    cohortes = dw.por_cohorte(dw.Filtros())
    registrar("Particiones", "Suma de cohortes = total (reprobadas/cerradas)", esperado,
              f"{int(cohortes['reprobadas'].sum())}/{int(cohortes['cerradas'].sum())}")
    for clave, (etiqueta, *_resto) in dw.SEGMENTOS.items():
        seg = dw.por_segmento(dw.Filtros(), clave)
        registrar("Particiones", f"Suma por {etiqueta.lower()} = total", esperado,
                  f"{int(seg['reprobadas'].sum())}/{int(seg['cerradas'].sum())}")
        sin_valor = seg["segmento"].isna().sum()
        registrar("Particiones", f"{etiqueta}: grupos sin valor (nulos)", 0, int(sin_valor))


def validar_area(s):
    with sesion_grafo() as g:
        grafo = {r["codigo"]: r["area"] for r in g.run("MATCH (m:Materia) RETURN m.codigo AS codigo, m.area AS area")}
    dw_ = dict(s.execute(text("SELECT codigo_materia, area FROM dw_academico.dim_materia")).all())
    coinciden = sum(1 for c, a in dw_.items() if grafo.get(c) == a)
    registrar("Cruce relacional-grafo", "Materias del DW con el área que registra Neo4j",
              len(dw_), coinciden)


# ---------------------------------------------------------------------------
# 6. Seguridad y anonimización
# ---------------------------------------------------------------------------

def validar_seguridad(s):
    for nombre, verificacion in (
        ("rol_dashboard NO puede leer academico_oltp", verificar_sin_acceso_oltp),
        ("rol_dashboard NO puede escribir en dw_academico", verificar_solo_lectura_dw),
    ):
        try:
            ok = verificacion() == 0
        except Exception as exc:  # noqa: BLE001
            ok, nombre = False, f"{nombre} ({exc})"
        registrar("Seguridad", nombre, "permiso denegado", "permiso denegado" if ok else "permitido", ok)

    invalidos = _escalar(s, "SELECT count(*) FROM dw_academico.dim_estudiante "
                            "WHERE carnet_hash !~ '^[0-9a-f]{64}$'")
    registrar("Anonimización", "carnet_hash con formato distinto de SHA-256 en el DW", 0, invalidos)
    columnas = {c for (c,) in s.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'dw_academico' AND table_name = 'dim_estudiante'"))}
    prohibidas = sorted(c for c in columnas if any(p in c for p in ("nombre", "correo", "email",
                                                                     "telefono", "direccion", "dui")))
    registrar("Anonimización", "Columnas con datos personales en dim_estudiante", "[]", str(prohibidas))
    registrar("Integridad", "CHECK del patrón de riesgo activo en el DW", 1, _escalar(
        s, "SELECT count(*) FROM pg_constraint WHERE conname = 'chk_patron_riesgo_reprobado'"))
    registrar("Integridad", "CHECK de costo_repeticion activo en el DW", 1, _escalar(
        s, "SELECT count(*) FROM pg_constraint WHERE conname = 'chk_costo_repeticion'"))
    registrar("Integridad", "Hechos sin sección o sin docente (llaves nulas)", 0, _escalar(
        s, "SELECT count(*) FROM dw_academico.fact_inscripcion "
           "WHERE seccion_key IS NULL OR docente_key IS NULL"))
    registrar("Integridad", "Llaves de sección y docente exigidas NOT NULL por el DDL", 2, _escalar(
        s, "SELECT count(*) FROM pg_attribute WHERE attrelid = 'dw_academico.fact_inscripcion'::regclass "
           "AND attname IN ('seccion_key', 'docente_key') AND attnotnull"))
    # Cada hecho debe apuntar a la sección y al docente que el OLTP registra
    # para esa inscripción (comparación inscripción por inscripción).
    registrar("Integridad", "Hechos cuya sección o docente difiere del OLTP", 0, _escalar(s, """
        SELECT count(*) FROM dw_academico.fact_inscripcion f
        JOIN dw_academico.dim_seccion ds ON ds.seccion_key = f.seccion_key
        JOIN dw_academico.dim_docente dd ON dd.docente_key = f.docente_key
        JOIN academico_oltp.inscripciones i ON i.inscripcion_id = f.inscripcion_id
        JOIN academico_oltp.secciones sec ON sec.seccion_id = i.seccion_id
        WHERE ds.seccion_id <> sec.seccion_id OR dd.docente_id <> sec.docente_id"""))
    columnas_docente = {c for (c,) in s.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'dw_academico' AND table_name = 'dim_docente'"))}
    registrar("Anonimización", "Columnas con datos personales o código institucional en dim_docente", "[]",
              str(sorted(c for c in columnas_docente
                         if any(p in c for p in ("nombre_docente", "codigo_docente", "correo",
                                                 "email", "telefono", "direccion", "dui")))))

    # Separación de roles (SCRUM-35): leer el OLTP y escribir el DW son permisos
    # de roles distintos. Solo un rechazo por permisos (42501) demuestra algo.
    def _rechazado(ejecutar) -> bool:
        try:
            ejecutar()
        except DBAPIError as exc:
            if getattr(exc.orig, "pgcode", None) == "42501":
                return True
            raise
        return False

    def _etl_escribe_dw():
        # Savepoint: se deshace SIEMPRE (también si el INSERT fuera permitido),
        # sin tocar el resto de la transacción de validación.
        savepoint = s.begin_nested()
        try:
            s.execute(text("INSERT INTO dw_academico.carga_control (fecha_corte, filas_hechos, calidad) "
                           "VALUES (current_date, 0, '{}'::jsonb)"))
        finally:
            savepoint.rollback()

    def _carga_lee_oltp():
        with engine_carga().connect() as conexion:
            try:
                conexion.execute(text("SELECT 1 FROM academico_oltp.estudiantes LIMIT 1"))
            finally:
                conexion.rollback()

    # Además del intento en vivo (que podría ser rechazado por una causa ajena,
    # p. ej. el permiso sobre una secuencia), se inspeccionan los privilegios
    # reales de cada tabla: es lo que no se puede esquivar con una coincidencia.
    escribibles = [r[0] for r in s.execute(text("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'dw_academico' AND c.relkind IN ('r', 'p')
          AND (has_table_privilege('rol_etl', c.oid, 'INSERT')
            OR has_table_privilege('rol_etl', c.oid, 'UPDATE')
            OR has_table_privilege('rol_etl', c.oid, 'DELETE')
            OR has_table_privilege('rol_etl', c.oid, 'TRUNCATE'))
        ORDER BY c.relname"""))]
    registrar("Seguridad", "Tablas de dw_academico que rol_etl puede escribir (privilegios del catálogo)",
              "[]", str(escribibles))
    privilegios_oltp = _escalar(s, """
        SELECT (CASE WHEN has_schema_privilege('rol_dw_carga', 'academico_oltp', 'USAGE') THEN 1 ELSE 0 END)
             + (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'academico_oltp' AND c.relkind IN ('r', 'p', 'v')
                  AND (has_table_privilege('rol_dw_carga', c.oid, 'SELECT')
                    OR has_table_privilege('rol_dw_carga', c.oid, 'INSERT')
                    OR has_table_privilege('rol_dw_carga', c.oid, 'UPDATE')
                    OR has_table_privilege('rol_dw_carga', c.oid, 'DELETE')
                    OR has_table_privilege('rol_dw_carga', c.oid, 'TRUNCATE')))""")
    registrar("Seguridad", "Privilegios de rol_dw_carga sobre academico_oltp (esquema + tablas, catálogo)",
              0, privilegios_oltp)

    for nombre, ejecutar in (
        ("rol_etl (lee el OLTP) NO puede escribir en dw_academico", _etl_escribe_dw),
        ("rol_dw_carga (escribe el DW) NO puede leer academico_oltp", _carga_lee_oltp),
    ):
        try:
            ok = _rechazado(ejecutar)
        except ErrorConfiguracion as exc:
            ok, nombre = False, f"{nombre} ({exc})"
        except Exception as exc:  # noqa: BLE001
            ok, nombre = False, f"{nombre} ({exc})"
        registrar("Seguridad", nombre, "permiso denegado", "permiso denegado" if ok else "permitido", ok)


# ---------------------------------------------------------------------------
# 7. Observaciones sobre los datos (no son pasa/falla: la memoria debe declararlas)
# ---------------------------------------------------------------------------

def observar_datos(s, correlaciones):
    cobertura = _df(s, """
        SELECT p.codigo_periodo, COUNT(*) FILTER (WHERE f.cerrada) AS cerradas,
               COUNT(*) FILTER (WHERE f.cerrada AND f.sesiones > 0) AS con_asistencia
        FROM dw_academico.fact_inscripcion f JOIN dw_academico.dim_periodo p USING (periodo_key)
        GROUP BY p.codigo_periodo, p.orden ORDER BY p.orden""")
    con = cobertura[cobertura["con_asistencia"] > 0]
    observaciones.append(
        f"**Cobertura de asistencia.** Solo {len(con)} de {len(cobertura)} períodos tienen asistencia "
        f"registrada ({', '.join(con['codigo_periodo'])}): "
        f"{int(cobertura['con_asistencia'].sum()):,} de {int(cobertura['cerradas'].sum()):,} "
        "inscripciones cerradas. El generador sintético (scripts/generator, `LIMIT 12000`) solo creó "
        "asistencia para 12,000 inscripciones. El patrón de riesgo y las correlaciones con asistencia "
        "solo pueden observarse en esos períodos."
    )
    dobles = _df(s, """
        SELECT COUNT(*) AS casos, COUNT(DISTINCT estudiante_id) AS estudiantes FROM (
            SELECT i.estudiante_id, s.materia_id, s.periodo_id
            FROM academico_oltp.inscripciones i
            JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
            GROUP BY 1, 2, 3 HAVING COUNT(*) > 1) x""").iloc[0]
    observaciones.append(
        f"**Calidad de datos del OLTP: doble inscripción.** {int(dobles['casos']):,} veces un "
        f"estudiante ({int(dobles['estudiantes']):,} estudiantes distintos) quedó inscrito en dos "
        "secciones de la misma materia en el mismo período. El esquema solo impide repetir la misma "
        "sección (`uq_estudiante_seccion`), y el generador sintético elige secciones al azar. El DW "
        "trata cada inscripción por separado, que es lo correcto; esta validación compara contra "
        "los reportes por estudiante + materia + sección para no mezclarlas. Con datos reales, una "
        "restricción por (estudiante, materia, período) en el OLTP lo evitaría."
    )
    r = {frozenset({p.x, p.y}): p.r for p in correlaciones.itertuples()}
    observaciones.append(
        f"**Asistencia y nota no se relacionan en estos datos** (r = {r[frozenset({'asistencia', 'nota'})]:+.3f}). "
        "El generador crea la asistencia al azar, sin depender de la nota: el dashboard lo reporta "
        "correctamente como relación despreciable. Con datos reales esta relación podría aparecer; "
        "no es un error del análisis sino una propiedad de los datos sintéticos."
    )
    observaciones.append(
        f"**Número de intento y nota** (r = {r[frozenset({'nota', 'intento'})]:+.3f}): relación débil y "
        "negativa, coherente con el generador, que resta 0.4 puntos de media a quien repite."
    )
    observaciones.append(
        f"**Costo y nota** (r = {r[frozenset({'nota', 'costo'})]:+.3f}) es una relación por "
        "construcción: el costo de reprobación solo existe con nota < 6.00. Se usa costo_reprobacion "
        "porque costo_inscripcion es constante (todas las materias tienen 4 UV y el costo por UV es el "
        "mismo supuesto de $25.00 en todos los períodos) y su correlación no está definida."
    )
    trabaja = dw.por_segmento(dw.Filtros(), "trabaja").set_index("segmento")
    tasa = (trabaja["reprobadas"] / trabaja["cerradas"]).to_dict()
    observaciones.append(
        f"**La condición laboral es la variable que más separa la reprobación** "
        f"(trabaja {tasa.get('Trabaja', 0) * 100:.1f} % vs no trabaja "
        f"{tasa.get('No trabaja', 0) * 100:.1f} %), coherente con el generador, que resta 0.6 puntos "
        "de media a quien trabaja. Turno, área, ciclo del plan y cohorte no se modelan en el "
        "generador y sus diferencias son pequeñas o indistinguibles del azar."
    )


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ_PROYECTO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "desconocido"


def escribir_registro(contexto: dict):
    fallos = [r for r in resultados if not r.ok]
    lineas = [
        "# Registro de validación de datos y procesos — Fases 3.3, 4.1 y 4.2",
        "",
        "Generado automáticamente por `python -m etl.validar_dw`. No editar a mano: se regenera en "
        "cada corrida, y el historial de corridas queda en git.",
        "",
        f"- **Fecha:** {contexto['fecha']}",
        f"- **Commit:** `{contexto['commit']}`",
        f"- **Última carga del DW:** {contexto['carga']}",
        f"- **Volumen:** {contexto['volumen']}",
        f"- **Resultado:** {len(resultados) - len(fallos)} de {len(resultados)} verificaciones correctas"
        + (" ✅" if not fallos else f" — **{len(fallos)} fallaron** ❌"),
        "",
        "## Qué se verifica y contra qué",
        "",
        "| Grupo | Fuente de comparación |",
        "|---|---|",
        "| Completitud | Conteos del esquema operacional (`academico_oltp`) |",
        "| Costo | SQL independiente sobre el OLTP, escrito en este script (no reutiliza el ETL): reprobación, matrícula y repetición |",
        "| Data mart | El corte por departamento reparte exactamente cada medida de costo |",
        "| Sistema transaccional | Las mismas funciones de los reportes del coordinador (SCRUM-10) |",
        "| Patrón de riesgo | Intersección de los reportes de notas (SCRUM-10) y asistencia (SCRUM-25), caso por caso |",
        "| Umbrales | Identidad de las constantes en `backend/app/calculos.py`, el reporte y el ETL |",
        "| Correlaciones | `corr()` de PostgreSQL (lo que muestra el dashboard) contra pandas |",
        "| Particiones | Cada segmentación del dashboard debe repartir exactamente el total |",
        "| Cruce relacional-grafo | Área de cada materia en Neo4j |",
        "| Seguridad / Anonimización / Integridad | Permisos reales de PostgreSQL y catálogo del DW |",
        "",
        "## Resultados",
        "",
        "| Grupo | Verificación | Esperado | Obtenido | Estado |",
        "|---|---|---|---|---|",
    ]
    for r in resultados:
        lineas.append(f"| {r.grupo} | {r.nombre} | {r.esperado} | {r.obtenido} | "
                      f"{'✅ OK' if r.ok else '❌ FALLO'} |")
    lineas += ["", "## Observaciones sobre los datos", "",
               "No son fallas: son propiedades de los datos que la memoria debe declarar al "
               "interpretar los resultados.", ""]
    lineas += [f"- {o}" for o in observaciones]
    lineas += ["", "## Cómo reproducir", "", "```bash",
               "python -m etl.carga        # recarga el DW desde el OLTP y Neo4j",
               "python -m etl.validar_dw   # vuelve a validar y regenera este registro",
               "```", ""]
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text("\n".join(lineas), encoding="utf-8")


def main() -> int:
    print("Validación de datos y procesos del DW (Fases 3.3, 4.1 y 4.2)\n")
    with sesion_oltp() as s:
        s.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        validar_completitud(s)
        validar_costo(s)
        validar_mart_departamento(s)
        validar_contra_reportes(s)
        validar_umbrales()
        correlaciones = validar_correlaciones(s)
        validar_particiones()
        validar_area(s)
        validar_seguridad(s)
        observar_datos(s, correlaciones)
        carga = dw.ultima_carga()
        volumen = (f"{_escalar(s, 'SELECT count(*) FROM dw_academico.fact_inscripcion'):,} hechos de "
                   f"inscripción, {_escalar(s, 'SELECT count(*) FROM dw_academico.dim_estudiante'):,} "
                   "estudiantes")
    escribir_registro({
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "commit": _commit(),
        "carga": (f"{carga['ejecutada_en']:%Y-%m-%d %H:%M} UTC, fecha de corte {carga['fecha_corte']}"
                  if carga else "sin cargas"),
        "volumen": volumen,
    })
    fallos = sum(1 for r in resultados if not r.ok)
    print(f"\n{len(resultados) - fallos} de {len(resultados)} verificaciones correctas.")
    print(f"Registro escrito en {REGISTRO.relative_to(RAIZ_PROYECTO)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
