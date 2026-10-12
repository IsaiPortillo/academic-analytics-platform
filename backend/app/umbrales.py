"""Umbrales académicos compartidos, sin ninguna dependencia.

Viven en un módulo propio y mínimo (y no solo en calculos.py) para que el dashboard
de Streamlit pueda leerlos sin importar los modelos de SQLAlchemy ni la configuración
de la app web: ese proceso no debe cargar las credenciales del rol de servicio.
calculos.py los re-exporta con los mismos nombres de siempre.
"""

from decimal import Decimal

# Nota mínima para aprobar un curso (escala 0-10), la misma que usa el
# generador de datos sintéticos (scripts/generator/02_generador_datos_sinteticos.py)
# como media de aprobación.
UMBRAL_NOTA_APROBACION = Decimal("6.00")

# Umbral de faltas a partir del cual se marca al estudiante en riesgo (SCRUM-25).
# Coincide con el HAVING del benchmark de la Fase 1.4 y con el badge rojo que ya
# usa el resumen por sección de asistencia.html. Está junto al umbral de
# aprobación porque el análisis diagnóstico (Fase 4.2) define el patrón de
# riesgo con estos dos números: el reporte del coordinador y el dashboard deben
# medir lo mismo con los mismos umbrales, no con dos copias que se separen.
UMBRAL_FALTAS_RIESGO = 3
