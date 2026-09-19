"""Modelos SQLAlchemy del esquema operacional.

IMPORTANTE: la fuente de verdad del esquema son los scripts de database/oltp/.
Estos modelos solo lo mapean; nunca se debe invocar Base.metadata.create_all().

Las columnas que tienen DEFAULT en el DDL se declaran aquí con server_default.
No es decorativo: sin esa marca, SQLAlchemy incluye la columna en el INSERT con
un NULL explícito, y un NULL explícito ANULA el DEFAULT de PostgreSQL. Eso
dejaría, por ejemplo, usuarios con activo NULL (imposibles de autenticar) o
inscripciones con numero_intento NULL (violando su NOT NULL).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ESQUEMA = {"schema": "academico_oltp"}

AHORA = text("CURRENT_TIMESTAMP")
VERDADERO = text("TRUE")
FALSO = text("FALSE")


class Departamento(Base):
    __tablename__ = "departamentos"
    __table_args__ = ESQUEMA

    departamento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_departamento: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    creado_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=AHORA
    )


class Carrera(Base):
    __tablename__ = "carreras"
    __table_args__ = ESQUEMA

    carrera_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_carrera: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    departamento_id: Mapped[int] = mapped_column(
        ForeignKey("academico_oltp.departamentos.departamento_id")
    )
    plan_anio: Mapped[int] = mapped_column(Integer)
    total_uv_carrera: Mapped[int] = mapped_column(Integer)
    activo: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=VERDADERO)

    departamento: Mapped["Departamento"] = relationship()


class Materia(Base):
    __tablename__ = "materias"
    __table_args__ = ESQUEMA

    materia_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_materia: Mapped[str] = mapped_column(String(15), unique=True)
    nombre: Mapped[str] = mapped_column(String(150))
    unidades_valorativas: Mapped[int] = mapped_column(Integer)
    ciclo_plan: Mapped[int] = mapped_column(Integer)
    carrera_id: Mapped[int] = mapped_column(ForeignKey("academico_oltp.carreras.carrera_id"))
    activo: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=VERDADERO)

    carrera: Mapped["Carrera"] = relationship()


class Estudiante(Base):
    __tablename__ = "estudiantes"
    __table_args__ = ESQUEMA

    estudiante_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carnet_hash: Mapped[str] = mapped_column(String(64), unique=True)
    anio_ingreso: Mapped[int] = mapped_column(Integer)
    carrera_id: Mapped[int] = mapped_column(ForeignKey("academico_oltp.carreras.carrera_id"))
    trabaja: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=FALSO)
    condicion_academica: Mapped[Optional[str]] = mapped_column(
        String(20), server_default=text("'REGULAR'")
    )
    activo: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=VERDADERO)
    creado_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=AHORA
    )

    carrera: Mapped["Carrera"] = relationship()


class Docente(Base):
    __tablename__ = "docentes"
    __table_args__ = ESQUEMA

    docente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_docente: Mapped[str] = mapped_column(String(20), unique=True)
    escalafon: Mapped[str] = mapped_column(String(50))
    departamento_id: Mapped[int] = mapped_column(
        ForeignKey("academico_oltp.departamentos.departamento_id")
    )
    activo: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=VERDADERO)
    creado_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=AHORA
    )

    departamento: Mapped["Departamento"] = relationship()


class PeriodoAcademico(Base):
    __tablename__ = "periodos_academicos"
    __table_args__ = ESQUEMA

    periodo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_periodo: Mapped[str] = mapped_column(String(10), unique=True)
    anio: Mapped[int] = mapped_column(Integer)
    ciclo_romano: Mapped[str] = mapped_column(String(5))
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    # Ojo: aquí el DDL usa FALSE, no TRUE como en el resto de tablas.
    activo: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=FALSO)


class Seccion(Base):
    __tablename__ = "secciones"
    __table_args__ = ESQUEMA

    seccion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    materia_id: Mapped[int] = mapped_column(ForeignKey("academico_oltp.materias.materia_id"))
    docente_id: Mapped[int] = mapped_column(ForeignKey("academico_oltp.docentes.docente_id"))
    periodo_id: Mapped[int] = mapped_column(
        ForeignKey("academico_oltp.periodos_academicos.periodo_id")
    )
    numero_seccion: Mapped[int] = mapped_column(Integer)
    turno: Mapped[str] = mapped_column(String(15))
    aula: Mapped[str] = mapped_column(String(30))
    cupo_maximo: Mapped[int] = mapped_column(Integer)
    creado_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=AHORA
    )

    materia: Mapped["Materia"] = relationship()
    docente: Mapped["Docente"] = relationship()
    periodo: Mapped["PeriodoAcademico"] = relationship()


class Inscripcion(Base):
    __tablename__ = "inscripciones"
    __table_args__ = ESQUEMA

    inscripcion_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        ForeignKey("academico_oltp.estudiantes.estudiante_id")
    )
    seccion_id: Mapped[int] = mapped_column(ForeignKey("academico_oltp.secciones.seccion_id"))
    fecha_inscripcion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=AHORA
    )
    numero_intento: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    estado_inscripcion: Mapped[Optional[str]] = mapped_column(
        String(20), server_default=text("'INSCRITO'")
    )

    estudiante: Mapped["Estudiante"] = relationship()
    seccion: Mapped["Seccion"] = relationship()


class Evaluacion(Base):
    __tablename__ = "evaluaciones"
    __table_args__ = ESQUEMA

    evaluacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seccion_id: Mapped[int] = mapped_column(ForeignKey("academico_oltp.secciones.seccion_id"))
    nombre_evaluacion: Mapped[str] = mapped_column(String(100))
    porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    fecha_evaluacion: Mapped[date] = mapped_column(Date)

    seccion: Mapped["Seccion"] = relationship()


class Calificacion(Base):
    __tablename__ = "calificaciones"
    __table_args__ = ESQUEMA

    calificacion_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inscripcion_id: Mapped[int] = mapped_column(
        ForeignKey("academico_oltp.inscripciones.inscripcion_id")
    )
    evaluacion_id: Mapped[int] = mapped_column(
        ForeignKey("academico_oltp.evaluaciones.evaluacion_id")
    )
    nota: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    fecha_registro: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=AHORA
    )

    inscripcion: Mapped["Inscripcion"] = relationship()
    evaluacion: Mapped["Evaluacion"] = relationship()


class Asistencia(Base):
    __tablename__ = "asistencias"
    __table_args__ = ESQUEMA

    asistencia_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inscripcion_id: Mapped[int] = mapped_column(
        ForeignKey("academico_oltp.inscripciones.inscripcion_id")
    )
    fecha_sesion: Mapped[date] = mapped_column(Date)
    estado_asistencia: Mapped[str] = mapped_column(String(15))

    inscripcion: Mapped["Inscripcion"] = relationship()


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = ESQUEMA

    usuario_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nombre_completo: Mapped[str] = mapped_column(String(120))
    rol_db: Mapped[str] = mapped_column(String(30))
    docente_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academico_oltp.docentes.docente_id")
    )
    activo: Mapped[bool] = mapped_column(Boolean, server_default=VERDADERO)
    creado_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=AHORA
    )

    docente: Mapped[Optional["Docente"]] = relationship()


class LogCambioNota(Base):
    __tablename__ = "log_cambios_notas"
    __table_args__ = {"schema": "auditoria"}

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    calificacion_id: Mapped[int] = mapped_column(BigInteger)
    nota_anterior: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    nota_nueva: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    usuario_db: Mapped[Optional[str]] = mapped_column(
        String(50), server_default=text("CURRENT_USER")
    )
    fecha_modificacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=AHORA
    )
