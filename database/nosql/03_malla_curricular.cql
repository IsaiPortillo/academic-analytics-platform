// =============================================================================
// UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
// CURSO DE ESPECIALIZACIÓN: BD & BI 2026
// FASE 1 - PUNTO 1.3: MODELADO Y CARGA DE GRAFO DE MALLA CURRICULAR
// =============================================================================
// Generado a partir de scripts/generator/catalogo_ues.py (el mismo plan que carga
// 03_cargar_grafo_neo4j.py). Si cambia el plan, regenera este archivo desde el catálogo.

// 1. RESTRICCIONES DE INTEGRIDAD Y UNICIDAD
CREATE CONSTRAINT uq_materia_codigo IF NOT EXISTS
FOR (m:Materia) REQUIRE m.codigo IS UNIQUE;

// 2. CREACIÓN DE NODOS (Plan de Ingeniería de Sistemas Informáticos: 45 asignaturas en 10 ciclos)
UNWIND [
  {codigo: 'MAT115', nombre: 'Matemática I', uv: 4, ciclo: 1, area: 'Ciencias Básicas'},
  {codigo: 'PRG115', nombre: 'Programación I', uv: 4, ciclo: 1, area: 'Desarrollo de Software'},
  {codigo: 'ACA115', nombre: 'Álgebra Vectorial y Matrices', uv: 4, ciclo: 1, area: 'Ciencias Básicas'},
  {codigo: 'ING115', nombre: 'Inglés Técnico I', uv: 4, ciclo: 1, area: 'Idiomas'},
  {codigo: 'MET115', nombre: 'Metodología de la Investigación', uv: 4, ciclo: 1, area: 'Formación General'},
  {codigo: 'MAT215', nombre: 'Matemática II', uv: 4, ciclo: 2, area: 'Ciencias Básicas'},
  {codigo: 'PRG215', nombre: 'Programación II', uv: 4, ciclo: 2, area: 'Desarrollo de Software'},
  {codigo: 'FIS115', nombre: 'Física I', uv: 4, ciclo: 2, area: 'Ciencias Básicas'},
  {codigo: 'ING215', nombre: 'Inglés Técnico II', uv: 4, ciclo: 2, area: 'Idiomas'},
  {codigo: 'EDA115', nombre: 'Estructuras de Datos y Algoritmos', uv: 4, ciclo: 2, area: 'Desarrollo de Software'},
  {codigo: 'BAD115', nombre: 'Bases de Datos I', uv: 4, ciclo: 3, area: 'Gestión de Datos'},
  {codigo: 'PRG315', nombre: 'Programación III', uv: 4, ciclo: 3, area: 'Desarrollo de Software'},
  {codigo: 'MAT315', nombre: 'Matemática III', uv: 4, ciclo: 3, area: 'Ciencias Básicas'},
  {codigo: 'EST115', nombre: 'Estadística I', uv: 4, ciclo: 3, area: 'Ciencias Básicas'},
  {codigo: 'FIS215', nombre: 'Física II', uv: 4, ciclo: 3, area: 'Ciencias Básicas'},
  {codigo: 'BAD215', nombre: 'Bases de Datos II', uv: 4, ciclo: 4, area: 'Gestión de Datos'},
  {codigo: 'ADS115', nombre: 'Análisis y Diseño de Sistemas I', uv: 4, ciclo: 4, area: 'Ingeniería de Software'},
  {codigo: 'EST215', nombre: 'Estadística II', uv: 4, ciclo: 4, area: 'Ciencias Básicas'},
  {codigo: 'SOP115', nombre: 'Sistemas Operativos', uv: 4, ciclo: 4, area: 'Hardware y Redes'},
  {codigo: 'CON115', nombre: 'Contabilidad Financiera', uv: 4, ciclo: 4, area: 'Gestión y Emprendimiento'},
  {codigo: 'SIF115', nombre: 'Sistemas de Información', uv: 4, ciclo: 5, area: 'Ingeniería de Software'},
  {codigo: 'ADS215', nombre: 'Análisis y Diseño de Sistemas II', uv: 4, ciclo: 5, area: 'Ingeniería de Software'},
  {codigo: 'RED115', nombre: 'Redes de Datos I', uv: 4, ciclo: 5, area: 'Hardware y Redes'},
  {codigo: 'ECO115', nombre: 'Introducción a la Economía', uv: 4, ciclo: 5, area: 'Gestión y Emprendimiento'},
  {codigo: 'ELD115', nombre: 'Electrónica Digital', uv: 4, ciclo: 5, area: 'Hardware y Redes'},
  {codigo: 'DWB115', nombre: 'Diseño Web y Aplicaciones', uv: 4, ciclo: 6, area: 'Desarrollo de Software'},
  {codigo: 'ARC115', nombre: 'Arquitectura de Computadoras', uv: 4, ciclo: 6, area: 'Hardware y Redes'},
  {codigo: 'RED215', nombre: 'Redes de Datos II', uv: 4, ciclo: 6, area: 'Hardware y Redes'},
  {codigo: 'IDS115', nombre: 'Ingeniería de Software', uv: 4, ciclo: 6, area: 'Ingeniería de Software'},
  {codigo: 'ADM115', nombre: 'Administración de Proyectos', uv: 4, ciclo: 6, area: 'Gestión y Emprendimiento'},
  {codigo: 'IAI115', nombre: 'Inteligencia Artificial', uv: 4, ciclo: 7, area: 'Ciencia de Datos e IA'},
  {codigo: 'SEG115', nombre: 'Seguridad Informática', uv: 4, ciclo: 7, area: 'Hardware y Redes'},
  {codigo: 'APM115', nombre: 'Aplicaciones Móviles', uv: 4, ciclo: 7, area: 'Desarrollo de Software'},
  {codigo: 'CAL115', nombre: 'Calidad de Software', uv: 4, ciclo: 7, area: 'Ingeniería de Software'},
  {codigo: 'EL1115', nombre: 'Electiva I', uv: 3, ciclo: 7, area: 'Formación General'},
  {codigo: 'BIN115', nombre: 'Inteligencia de Negocios', uv: 4, ciclo: 8, area: 'Ciencia de Datos e IA'},
  {codigo: 'DSD115', nombre: 'Sistemas Distribuidos', uv: 4, ciclo: 8, area: 'Desarrollo de Software'},
  {codigo: 'AUD115', nombre: 'Auditoría Informática', uv: 4, ciclo: 8, area: 'Gestión y Emprendimiento'},
  {codigo: 'EL2115', nombre: 'Electiva II', uv: 3, ciclo: 8, area: 'Formación General'},
  {codigo: 'ETI115', nombre: 'Ética Profesional', uv: 4, ciclo: 8, area: 'Formación General'},
  {codigo: 'ANT115', nombre: 'Anteproyecto de Trabajo de Graduación', uv: 4, ciclo: 9, area: 'Formación General'},
  {codigo: 'EMP115', nombre: 'Emprendimiento e Innovación', uv: 4, ciclo: 9, area: 'Gestión y Emprendimiento'},
  {codigo: 'EL3115', nombre: 'Electiva III', uv: 3, ciclo: 9, area: 'Formación General'},
  {codigo: 'GTI115', nombre: 'Gestión de Tecnologías de la Información', uv: 4, ciclo: 9, area: 'Gestión y Emprendimiento'},
  {codigo: 'TGR115', nombre: 'Trabajo de Graduación', uv: 8, ciclo: 10, area: 'Formación General'}
] AS m
MERGE (mat:Materia {codigo: m.codigo})
SET mat.nombre = m.nombre, mat.uv = m.uv, mat.ciclo = m.ciclo, mat.area = m.area;

// 3. DEFINICIÓN DE DEPENDENCIAS Y PRERREQUISITOS (:MateriaA)-[:REQUIERE_APROBADA]->(:MateriaB)
// Significado semántico: para cursar MateriaA hay que haber aprobado MateriaB
UNWIND [
  ['MAT215', 'MAT115'],
  ['PRG215', 'PRG115'],
  ['FIS115', 'MAT115'],
  ['ING215', 'ING115'],
  ['EDA115', 'PRG115'],
  ['BAD115', 'PRG115'],
  ['PRG315', 'PRG215'],
  ['MAT315', 'MAT215'],
  ['EST115', 'MAT215'],
  ['FIS215', 'FIS115'],
  ['FIS215', 'MAT215'],
  ['BAD215', 'BAD115'],
  ['ADS115', 'PRG215'],
  ['EST215', 'EST115'],
  ['SOP115', 'EDA115'],
  ['SIF115', 'ADS115'],
  ['SIF115', 'BAD115'],
  ['ADS215', 'ADS115'],
  ['RED115', 'SOP115'],
  ['ELD115', 'FIS215'],
  ['DWB115', 'PRG315'],
  ['ARC115', 'ACA115'],
  ['RED215', 'RED115'],
  ['IDS115', 'ADS215'],
  ['ADM115', 'CON115'],
  ['IAI115', 'PRG315'],
  ['IAI115', 'MAT315'],
  ['SEG115', 'RED215'],
  ['APM115', 'DWB115'],
  ['CAL115', 'IDS115'],
  ['BIN115', 'BAD215'],
  ['BIN115', 'SIF115'],
  ['DSD115', 'RED215'],
  ['AUD115', 'SEG115'],
  ['ANT115', 'MET115'],
  ['ANT115', 'IDS115'],
  ['EMP115', 'ADM115'],
  ['GTI115', 'AUD115'],
  ['TGR115', 'ANT115']
] AS p
MATCH (a:Materia {codigo: p[0]}), (b:Materia {codigo: p[1]})
MERGE (a)-[:REQUIERE_APROBADA]->(b);
