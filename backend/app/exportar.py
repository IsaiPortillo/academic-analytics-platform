"""Exportación de reportes a CSV, Excel y PDF.

Todos los reportes del sistema se describen con la misma estructura (Reporte:
título, filtros aplicados, columnas tipadas y filas) y este módulo los convierte
al formato pedido. Así la pantalla y los tres archivos salen de los mismos datos
y con el mismo formato.

    CSV    para análisis externo: claves en snake_case y valores sin formatear.
    Excel  para trabajar los datos: tipos numéricos reales y formato de celda.
    PDF    para leer o imprimir: tabla paginada con la cabecera repetida.
"""

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Any, Sequence

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

FORMATOS = ("csv", "xlsx", "pdf")

# El PDF es para leer o imprimir. Por encima de este número de filas se corta y
# se indica en el propio archivo; el conjunto completo va en Excel o CSV.
LIMITE_FILAS_PDF = 3000

COLOR_MARCA = "8B0000"
COLOR_TEXTO = "0F172A"
COLOR_TENUE = "64748B"
COLOR_LINEA = "E2E8F0"

# Excel en Windows asume la codificación local si el CSV no lleva BOM.
BOM_UTF8 = "﻿"

TIPOS = ("texto", "id", "entero", "decimal", "porcentaje", "dinero")
FORMATO_EXCEL = {
    "id": "0",
    "entero": "#,##0",
    "decimal": "0.00",
    "porcentaje": "0.0%",
    "dinero": '"$"#,##0.00',
}


@dataclass(frozen=True)
class Columna:
    clave: str             # nombre en el CSV
    etiqueta: str          # nombre en pantalla, Excel y PDF
    tipo: str = "texto"    # texto | id (entero sin separador) | entero | decimal | porcentaje (0–1) | dinero
    ancho: float = 1.0     # ancho relativo en el PDF


@dataclass
class Reporte:
    titulo: str
    nombre_archivo: str
    columnas: list[Columna]
    filas: list[Sequence[Any]]
    filtros: list[tuple[str, str]] = field(default_factory=list)


def formatear(valor: Any, tipo: str) -> str:
    """Texto para mostrar un valor en pantalla o en el PDF."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return "—"
    if tipo == "id":
        return str(int(valor))
    if tipo == "entero":
        return f"{int(valor):,}"
    if tipo == "decimal":
        return f"{float(valor):.2f}"
    if tipo == "porcentaje":
        return f"{float(valor) * 100:.1f} %"
    if tipo == "dinero":
        return f"${float(valor):,.2f}"
    return str(valor)


def _numero(valor: Any) -> Any:
    """Valor nativo para Excel: Decimal a float, None se queda vacío."""
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, float) and valor != valor:
        return None
    return valor


def _nombre_archivo(reporte: Reporte, extension: str) -> str:
    base = unicodedata.normalize("NFKD", reporte.nombre_archivo).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_").lower() or "reporte"
    return f"{base}_{date.today().isoformat()}.{extension}"


def _cabeceras(nombre: str, tipo_mime: str) -> dict:
    return {
        "Content-Disposition": f'attachment; filename="{nombre}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


def _linea_filtros(reporte: Reporte) -> str:
    return " · ".join(f"{etiqueta}: {valor}" for etiqueta, valor in reporte.filtros)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def a_csv(reporte: Reporte) -> StreamingResponse:
    def generar():
        buffer = StringIO()
        escritor = csv.writer(buffer)
        escritor.writerow([c.clave for c in reporte.columnas])
        yield BOM_UTF8 + buffer.getvalue()
        for fila in reporte.filas:
            buffer.seek(0)
            buffer.truncate()
            escritor.writerow(["" if v is None else _numero(v) for v in fila])
            yield buffer.getvalue()

    nombre = _nombre_archivo(reporte, "csv")
    return StreamingResponse(generar(), media_type="text/csv; charset=utf-8",
                             headers=_cabeceras(nombre, "text/csv"))


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def a_excel_bytes(reporte: Reporte) -> bytes:
    from openpyxl import Workbook  # noqa: PLC0415 (solo se carga si se pide Excel)
    from openpyxl.cell import WriteOnlyCell  # noqa: PLC0415
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: PLC0415
    from openpyxl.utils import get_column_letter  # noqa: PLC0415

    # write_only: las filas se escriben en secuencia sin quedar todas en memoria.
    libro = Workbook(write_only=True)
    hoja = libro.create_sheet(re.sub(r"[\[\]:*?/\\]", "", reporte.titulo)[:31] or "Reporte")

    for i, columna in enumerate(reporte.columnas, start=1):
        ancho = max(len(columna.etiqueta) + 2, 10 if columna.tipo != "texto" else 14)
        hoja.column_dimensions[get_column_letter(i)].width = min(ancho * max(columna.ancho, 1), 48)
    fila_cabecera = 5 if reporte.filtros else 4
    hoja.freeze_panes = f"A{fila_cabecera + 1}"

    def celda(valor, **estilo):
        c = WriteOnlyCell(hoja, value=valor)
        for clave, v in estilo.items():
            setattr(c, clave, v)
        return c

    hoja.append([celda(reporte.titulo, font=Font(bold=True, size=14, color=COLOR_MARCA))])
    if reporte.filtros:
        hoja.append([celda(_linea_filtros(reporte), font=Font(size=9, color=COLOR_TENUE))])
    hoja.append([celda(f"Generado el {datetime.now():%d/%m/%Y %H:%M}",
                       font=Font(size=9, color=COLOR_TENUE))])
    hoja.append([])

    borde = Border(bottom=Side(style="medium", color=COLOR_MARCA))
    fondo = PatternFill("solid", fgColor="F7F9FB")
    hoja.append([
        celda(c.etiqueta, font=Font(bold=True, color=COLOR_TEXTO), border=borde, fill=fondo,
              alignment=Alignment(horizontal="left" if c.tipo == "texto" else "right"))
        for c in reporte.columnas
    ])

    linea = Border(bottom=Side(style="thin", color=COLOR_LINEA))
    for fila in reporte.filas:
        hoja.append([
            celda(_numero(v), border=linea, number_format=FORMATO_EXCEL.get(c.tipo, "General"))
            for c, v in zip(reporte.columnas, fila)
        ])

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def a_excel(reporte: Reporte) -> Response:
    nombre = _nombre_archivo(reporte, "xlsx")
    tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(a_excel_bytes(reporte), media_type=tipo, headers=_cabeceras(nombre, tipo))


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def a_pdf_bytes(reporte: Reporte) -> bytes:
    from reportlab.lib import colors  # noqa: PLC0415 (solo se carga si se pide PDF)
    from reportlab.lib.pagesizes import landscape, letter  # noqa: PLC0415
    from reportlab.lib.styles import ParagraphStyle  # noqa: PLC0415
    from reportlab.lib.units import mm  # noqa: PLC0415
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle  # noqa: PLC0415

    marca, texto, tenue, linea = (colors.HexColor(f"#{c}") for c in
                                  (COLOR_MARCA, COLOR_TEXTO, COLOR_TENUE, COLOR_LINEA))
    pagina = landscape(letter) if len(reporte.columnas) > 6 else letter
    margen = 14 * mm
    util = pagina[0] - 2 * margen
    generado = f"{datetime.now():%d/%m/%Y %H:%M}"

    def pie(lienzo, documento):
        lienzo.saveState()
        lienzo.setFont("Helvetica", 7)
        lienzo.setFillColor(tenue)
        lienzo.drawString(margen, 8 * mm, f"Sistema Minerva · UES-FMO · {generado}")
        lienzo.drawRightString(pagina[0] - margen, 8 * mm, f"Página {documento.page}")
        lienzo.restoreState()

    filas = reporte.filas[:LIMITE_FILAS_PDF]
    estilo_titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=14, leading=17,
                                   textColor=marca)
    estilo_meta = ParagraphStyle("m", fontName="Helvetica", fontSize=8, leading=11, textColor=tenue)
    historia = [Paragraph(reporte.titulo, estilo_titulo), Spacer(1, 2)]
    if reporte.filtros:
        historia.append(Paragraph(_linea_filtros(reporte), estilo_meta))
    if len(reporte.filas) > LIMITE_FILAS_PDF:
        historia.append(Paragraph(f"Primeras {LIMITE_FILAS_PDF:,} de {len(reporte.filas):,} filas. "
                                  "El conjunto completo está en Excel o CSV.", estilo_meta))
    historia.append(Spacer(1, 8))

    total = sum(c.ancho for c in reporte.columnas)
    anchos = [util * c.ancho / total for c in reporte.columnas]
    tamano = 7.5

    def recortar(valor: str, ancho: float) -> str:
        maximo = max(int(ancho / (tamano * 0.5)), 4)
        return valor if len(valor) <= maximo else valor[: maximo - 1] + "…"

    def cabecera(columna: Columna) -> Paragraph:
        return Paragraph(columna.etiqueta, ParagraphStyle(
            "c", fontName="Helvetica-Bold", fontSize=tamano, leading=tamano + 1.5, textColor=marca,
            alignment=0 if columna.tipo == "texto" else 2))

    datos = [[cabecera(c) for c in reporte.columnas]]
    datos += [[recortar(formatear(v, c.tipo), a) for c, v, a in zip(reporte.columnas, fila, anchos)]
              for fila in filas]
    if not filas:
        datos.append(["Sin registros para los filtros elegidos."] + [""] * (len(reporte.columnas) - 1))

    estilo = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", tamano),
        ("FONT", (0, 1), (-1, -1), "Helvetica", tamano),
        ("TEXTCOLOR", (0, 0), (-1, 0), marca),
        ("TEXTCOLOR", (0, 1), (-1, -1), texto),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, marca),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, linea),
        ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, c in enumerate(reporte.columnas):
        if c.tipo != "texto":
            estilo.append(("ALIGN", (i, 0), (i, -1), "RIGHT"))
    if not filas:
        estilo.append(("SPAN", (0, 1), (-1, 1)))

    tabla = LongTable(datos, colWidths=anchos, repeatRows=1)
    tabla.setStyle(TableStyle(estilo))
    historia.append(tabla)

    salida = BytesIO()
    SimpleDocTemplate(salida, pagesize=pagina, leftMargin=margen, rightMargin=margen,
                      topMargin=margen, bottomMargin=16 * mm, title=reporte.titulo,
                      author="Sistema Minerva").build(historia, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()


def a_pdf(reporte: Reporte) -> Response:
    nombre = _nombre_archivo(reporte, "pdf")
    return Response(a_pdf_bytes(reporte), media_type="application/pdf",
                    headers=_cabeceras(nombre, "application/pdf"))


def responder(reporte: Reporte, formato: str):
    """Respuesta de descarga en el formato pedido (csv, xlsx o pdf)."""
    if formato == "csv":
        return a_csv(reporte)
    if formato == "xlsx":
        return a_excel(reporte)
    if formato == "pdf":
        return a_pdf(reporte)
    raise HTTPException(status_code=400, detail=f"Formato no soportado: {formato}")
