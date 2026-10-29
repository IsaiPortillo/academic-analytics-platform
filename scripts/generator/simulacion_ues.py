"""
Simulación de la vida académica de la FMO con los datos de catalogo_ues.py.

Función pura: no toca la base. Devuelve listas de filas con referencias por posición
(índice de estudiante, de sección, de evaluación, de inscripción) y por código (materia,
docente, período); el generador las traduce a los identificadores de la base al insertarlas.

Qué se simula, ciclo a ciclo:
  - cada año entra una cohorte por carrera (en el Ciclo I) y avanza por su plan: se
    inscribe en lo que le toca según los prerrequisitos que aprobó (hasta tres intentos por
    materia, como en la UES);
  - cada materia que alguien cursa abre secciones (cupo de 40) con un docente de su
    departamento (Matemática y Física las da Ciencias Naturales; Inglés, Humanidades);
  - cada docente evalúa a su manera (ver ESTILOS_DE_EVALUACION: casi todos, un parcial
    corto por módulo) y a veces cambia su plan en una sección;
  - las notas dependen del estudiante, de la dificultad de la materia, de si trabaja y de si
    repite; con nota final de 6.0 o más se aprueba;
  - algunos retiran la materia y algunos abandonan la carrera, más si trabajan o reprueban;
  - el ciclo vigente va en curso: sus evaluaciones futuras todavía no tienen nota.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import random
from datetime import date, timedelta

import catalogo_ues as cat

UMBRAL_APROBACION = 6.0
INTENTOS_MAXIMOS = 3
CUPO_SECCION = 40
PRIMER_CICLO_CON_ASISTENCIA = "2025-I"   # antes no se simula asistencia: pesa mucho y no aporta
SESIONES_POR_CICLO = 10

PREFIJO_CARNET = {
    "I10515": "IS", "I10506": "IC", "E20118": "AE", "E20218": "CP", "E20318": "EC", "M10108": "MD",
    "M10214": "EN", "J10116": "CJ", "H10116": "CE", "G10110": "AG", "B10115": "BI", "Q10112": "QF",
}
PROBABILIDAD_TRABAJA = {"M10108": 0.08, "M10214": 0.15, "E20118": 0.45, "E20218": 0.45, "J10116": 0.42,
                        "H10116": 0.40}
DIFICULTAD_BASE = {cat.BASICAS: 0.40, "Desarrollo de Software": 0.15, "Gestión de Datos": 0.20,
                   "Ingeniería de Software": 0.10, "Hardware y Redes": 0.25, "Ciencia de Datos e IA": 0.30}
MATERIAS_DURAS = ("matemática i", "cálculo", "física i", "química general", "anatomía humana i", "programación i",
                  "derecho civil obligaciones", "contabilidad ii", "fisiología i")


def hash_carnet(carnet: str, clave: str | None) -> str:
    """Igual que app/catalogos.py: con CARNET_CLAVE, HMAC-SHA256; sin ella, SHA-256 simple."""
    normalizado = carnet.strip().upper()
    if clave:
        return hmac.new(clave.encode(), normalizado.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(normalizado.encode()).hexdigest()


def numeracion_de_docentes() -> dict[str, list[str]]:
    """Códigos de docente por departamento, consecutivos desde DOC-101 en el orden del catálogo."""
    siguiente = cat.PRIMER_NUMERO_DOCENTE
    reparto = {}
    for departamento, _ in cat.DEPARTAMENTOS:
        cantidad = cat.DOCENTES_POR_DEPARTAMENTO[departamento]
        reparto[departamento] = [f"DOC-{n}" for n in range(siguiente, siguiente + cantidad)]
        siguiente += cantidad
    return reparto


def estilo_de_docente(codigo: str) -> str:
    """El estilo de evaluación de un docente: fijo (sale de su código) y repartido según el peso de cada estilo."""
    punto = int(hashlib.sha256(codigo.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    acumulado = 0.0
    for estilo, (peso, _) in cat.ESTILOS_DE_EVALUACION.items():
        acumulado += peso
        if punto <= acumulado:
            return estilo
    return "parcial_corto"


def _dificultad(materia: cat.Materia, rng: random.Random) -> float:
    base = DIFICULTAD_BASE.get(materia.area, 0.0)
    if materia.nombre.lower() in MATERIAS_DURAS:
        base += 0.25
    return base + max(0.0, 0.25 - 0.04 * materia.ciclo) + rng.gauss(0, 0.2)


def _recortar(valor: float) -> float:
    return round(min(10.0, max(0.0, valor)), 2)


def _aula(departamento: str, materia: cat.Materia, rng: random.Random) -> str:
    laboratorio = any(p in materia.nombre.lower() for p in ("programación", "bases de datos", "redes", "sistemas",
                                                            "laboratorio", "química", "física", "anatomía",
                                                            "microbiología", "botánica", "zoología"))
    if laboratorio:
        return f"Lab-{departamento[1]}{rng.randint(1, 4)}"
    edificio = {"DIA": "B", "DCE": "C", "DME": "M", "DCH": "H", "DJS": "J", "DAG": "A", "DCN": "N", "DQF": "Q"}[departamento]
    return f"Edif-{edificio}{rng.randint(101, 306)}"


def simular(hoy: date, semilla: int = 42, clave_carnet: str | None = None,
            carreras: list[cat.Carrera] | None = None) -> dict:
    carreras = carreras if carreras is not None else cat.CARRERAS
    rng = random.Random(semilla)
    periodos = cat.periodos(cat.ANIO_INICIAL, cat.ANIO_FINAL)
    indice_periodo = {codigo: i for i, (codigo, *_) in enumerate(periodos)}
    docentes = numeracion_de_docentes()
    materias = {m.codigo: m for c in carreras for m in c.materias}
    dificultad = {codigo: _dificultad(m, rng) for codigo, m in materias.items()}
    depto_de_carrera = {c.codigo: c.departamento for c in carreras}

    estudiantes: list[dict] = []
    for carrera in carreras:
        for anio in range(cat.ANIO_INICIAL, cat.ANIO_FINAL + 1):
            cuantos = max(3, round(carrera.ingreso_anual * rng.uniform(0.85, 1.15)))
            for n in range(1, cuantos + 1):
                carnet = f"{PREFIJO_CARNET[carrera.codigo]}{anio % 100:02d}{n:03d}"
                estudiantes.append({
                    "carnet": carnet, "hash": hash_carnet(carnet, clave_carnet), "carrera": carrera.codigo,
                    "anio_ingreso": anio, "trabaja": rng.random() < PROBABILIDAD_TRABAJA.get(carrera.codigo, 0.28),
                    "habilidad": max(-2.5, min(2.5, rng.gauss(0, 1))), "primer_periodo": indice_periodo[f"{anio}-I"],
                    "aprobadas": set(), "intentos": {}, "estado": "ACTIVO", "ultimas_reprobadas": 0,
                    "condicion": "REGULAR", "activo": True,
                })

    por_carrera = {c.codigo: c for c in carreras}
    secciones: list[dict] = []
    evaluaciones: list[tuple] = []          # (índice de sección, nombre, porcentaje, fecha)
    inscripciones: list[dict] = []
    calificaciones: list[tuple] = []        # (índice de inscripción, índice de evaluación, nota)
    asistencias: list[tuple] = []           # (índice de inscripción, fecha, estado)
    docente_habitual: dict[str, list[str]] = {}
    plan_evaluacion_de_seccion: dict[int, list[int]] = {}   # sección -> índices de sus evaluaciones

    for codigo_periodo, anio, ciclo, inicio, fin in periodos:
        i_periodo = indice_periodo[codigo_periodo]
        en_curso = inicio <= hoy <= fin
        if inicio > hoy:
            break
        modulos = cat.modulos_del_ciclo(inicio, fin)

        # 1. Quién se inscribe en qué
        demanda: dict[str, list[int]] = {}
        for idx, est in enumerate(estudiantes):
            if est["estado"] != "ACTIVO" or est["primer_periodo"] > i_periodo:
                continue
            carrera = por_carrera[est["carrera"]]
            pendientes = [m for m in carrera.materias
                          if m.codigo not in est["aprobadas"] and est["intentos"].get(m.codigo, 0) < INTENTOS_MAXIMOS
                          and all(r in est["aprobadas"] for r in m.prerrequisitos)]
            if not pendientes:
                est["estado"] = "EGRESADO" if len(est["aprobadas"]) == len(carrera.materias) else "BLOQUEADO"
                continue
            # Primero lo que se arrastra (ya intentado) y luego lo que sigue del plan.
            pendientes.sort(key=lambda m: (-est["intentos"].get(m.codigo, 0), m.ciclo, m.codigo))
            carga = rng.choice((3, 4)) if est["trabaja"] else rng.choice((4, 5, 5))
            for materia in pendientes[:carga]:
                demanda.setdefault(materia.codigo, []).append(idx)

        # 2. Secciones, docente, evaluaciones
        asignacion: dict[int, dict] = {}   # estudiante -> {materia: índice de sección}
        for codigo_materia, lista in sorted(demanda.items()):
            materia = materias[codigo_materia]
            carrera = next(c for c in carreras if any(m.codigo == codigo_materia for m in c.materias))
            n_secciones = max(1, math.ceil(len(lista) / CUPO_SECCION))
            if materia.area == cat.BASICAS:
                depto_docente = "DCN"
            elif materia.area == cat.IDIOMAS:
                depto_docente = "DCH"
            else:
                depto_docente = depto_de_carrera[carrera.codigo]
            primero = len(secciones)
            for numero in range(1, n_secciones + 1):
                habituales = docente_habitual.setdefault(f"{codigo_materia}:{numero}", [])
                if habituales and rng.random() < 0.75:
                    docente = rng.choice(habituales)
                else:
                    docente = rng.choice(docentes[depto_docente])
                    habituales.append(docente)
                turno = rng.choices(("MATUTINO", "VESPERTINO", "NOCTURNO"), weights=carrera.peso_turnos)[0]
                secciones.append({"periodo": codigo_periodo, "materia": codigo_materia, "numero": numero,
                                  "docente": docente, "turno": turno, "aula": _aula(depto_docente, materia, rng),
                                  "cupo": CUPO_SECCION + (5 if numero == 1 else 0), "cerrada": not en_curso})
                estilo = estilo_de_docente(docente)
                if rng.random() < 0.15:   # a veces el docente cambia su plan de evaluación en esta sección
                    estilo = rng.choice(list(cat.ESTILOS_DE_EVALUACION))
                plan = cat.evaluaciones_de(estilo)
                indices = []
                for k, (nombre, porcentaje, modulo) in enumerate(plan):
                    indices.append(len(evaluaciones))
                    evaluaciones.append((len(secciones) - 1, nombre, porcentaje,
                                         cat.fecha_de_evaluacion(k, len(plan), modulo, modulos)))
                plan_evaluacion_de_seccion[len(secciones) - 1] = indices
            for orden, idx in enumerate(lista):
                asignacion.setdefault(idx, {})[codigo_materia] = primero + (orden % n_secciones)

        # 3. Resultados de cada inscripción
        for idx, materias_del_estudiante in asignacion.items():
            est = estudiantes[idx]
            reprobadas_en_el_ciclo = 0
            for codigo_materia, i_seccion in materias_del_estudiante.items():
                intento = est["intentos"].get(codigo_materia, 0) + 1
                p_retiro = (0.06 if est["trabaja"] else 0.035) if not en_curso else 0.02
                retira = rng.random() < p_retiro
                i_insc = len(inscripciones)
                inscripcion = {"estudiante": idx, "seccion": i_seccion, "intento": intento,
                               "estado": "FINALIZADO" if not en_curso else "INSCRITO", "motivo": None,
                               "fecha_retiro": None,
                               "fecha_inscripcion": inicio - timedelta(days=rng.randint(3, 12))}
                if retira:
                    inscripcion["estado"] = "RETIRADO"
                    inscripcion["motivo"] = rng.choice(cat.MOTIVOS_DE_RETIRO)
                    dia = rng.randint(7, max(8, min((fin - inicio).days, (hoy - inicio).days) - 1))
                    inscripcion["fecha_retiro"] = inicio + timedelta(days=dia)
                    inscripciones.append(inscripcion)
                    continue
                inscripciones.append(inscripcion)
                est["intentos"][codigo_materia] = intento

                media = (7.3 + 0.95 * est["habilidad"] - dificultad[codigo_materia] - (0.45 if est["trabaja"] else 0.0)
                         - 0.35 * (intento - 1) + rng.gauss(0, 0.6))
                ponderado, peso_con_nota = 0.0, 0.0
                for i_eval in plan_evaluacion_de_seccion[i_seccion]:
                    _, _, porcentaje, fecha = evaluaciones[i_eval]
                    if fecha > hoy:
                        continue
                    nota = _recortar(rng.gauss(media, 0.9))
                    calificaciones.append((i_insc, i_eval, nota))
                    ponderado += nota * porcentaje
                    peso_con_nota += porcentaje
                if not en_curso:
                    final = ponderado / peso_con_nota if peso_con_nota else 0.0
                    if final >= UMBRAL_APROBACION:
                        est["aprobadas"].add(codigo_materia)
                    else:
                        reprobadas_en_el_ciclo += 1

                if codigo_periodo >= PRIMER_CICLO_CON_ASISTENCIA:
                    p_presente = min(0.98, max(0.5, 0.88 + 0.04 * est["habilidad"] - (0.05 if est["trabaja"] else 0.0)))
                    for k in range(1, SESIONES_POR_CICLO + 1):
                        dia = inicio + timedelta(days=7 * k)
                        if dia > min(fin, hoy):
                            break
                        punto = rng.random()
                        estado = "PRESENTE" if punto < p_presente else ("JUSTIFICADO" if punto < p_presente + 0.03 else "AUSENTE")
                        asistencias.append((i_insc, dia, estado))

            # 4. Abandono (solo al cerrar un ciclo)
            if not en_curso:
                est["ultimas_reprobadas"] = reprobadas_en_el_ciclo
                p_abandono = (0.025 + (0.05 if reprobadas_en_el_ciclo >= 3 else 0.0)
                              + (0.03 if est["trabaja"] else 0.0) + (0.02 if reprobadas_en_el_ciclo >= 1 else 0.0))
                if rng.random() < p_abandono:
                    est["estado"] = "ABANDONO"

    for est in estudiantes:
        if est["estado"] in ("ABANDONO", "BLOQUEADO"):
            est["condicion"], est["activo"] = "RETIRADO", False
        elif est["estado"] == "EGRESADO":
            est["condicion"], est["activo"] = "EGRESADO", False
        elif est["ultimas_reprobadas"] >= 2:
            est["condicion"] = "CONDICIONAL"

    return {"periodos": periodos, "estudiantes": estudiantes, "secciones": secciones, "evaluaciones": evaluaciones,
            "inscripciones": inscripciones, "calificaciones": calificaciones, "asistencias": asistencias,
            "docentes": docentes}
