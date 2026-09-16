// =============================================================================
// UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
// CURSO DE ESPECIALIZACIÓN: BD & BI 2026
// FASE 1 - PUNTO 1.3: MODELADO Y CARGA DE GRAFO DE MALLA CURRICULAR
// =============================================================================

// 1. RESTRICCIONES DE INTEGRIDAD Y UNICIDAD
CREATE CONSTRAINT uq_materia_codigo IF NOT EXISTS
FOR (m:Materia) REQUIRE m.codigo IS UNIQUE;

// 2. CREACIÓN DE NODOS (Materias del Tronco de Ingeniería de Sistemas Informáticos)
CREATE 
  (mat115:Materia {codigo: 'MAT115', nombre: 'Matemática I', uv: 4, ciclo: 1, area: 'Ciencias Básicas'}),
  (prg115:Materia {codigo: 'PRG115', nombre: 'Programación I', uv: 4, ciclo: 1, area: 'Desarrollo de Software'}),
  (aca115:Materia {codigo: 'ACA115', nombre: 'Álgebra Vectorial y Matrices', uv: 4, ciclo: 1, area: 'Ciencias Básicas'}),

  (mat215:Materia {codigo: 'MAT215', nombre: 'Matemática II', uv: 4, ciclo: 2, area: 'Ciencias Básicas'}),
  (prg215:Materia {codigo: 'PRG215', nombre: 'Programación II', uv: 4, ciclo: 2, area: 'Desarrollo de Software'}),

  (bad115:Materia {codigo: 'BAD115', nombre: 'Bases de Datos I', uv: 4, ciclo: 3, area: 'Gestión de Datos'}),
  (prg315:Materia {codigo: 'PRG315', nombre: 'Programación III', uv: 4, ciclo: 3, area: 'Desarrollo de Software'}),
  (mat315:Materia {codigo: 'MAT315', nombre: 'Matemática III', uv: 4, ciclo: 3, area: 'Ciencias Básicas'}),

  (bad215:Materia {codigo: 'BAD215', nombre: 'Bases de Datos II', uv: 4, ciclo: 4, area: 'Gestión de Datos'}),
  (ads115:Materia {codigo: 'ADS115', nombre: 'Análisis y Diseño de Sistemas I', uv: 4, ciclo: 4, area: 'Ingeniería de Software'}),

  (sif115:Materia {codigo: 'SIF115', nombre: 'Sistemas de Información', uv: 4, ciclo: 5, area: 'Ingeniería de Software'}),
  (ads215:Materia {codigo: 'ADS215', nombre: 'Análisis y Diseño de Sistemas II', uv: 4, ciclo: 5, area: 'Ingeniería de Software'}),

  (dwb115:Materia {codigo: 'DWB115', nombre: 'Diseño Web y Aplicaciones', uv: 4, ciclo: 6, area: 'Desarrollo de Software'}),
  (arc115:Materia {codigo: 'ARC115', nombre: 'Arquitectura de Computadoras', uv: 4, ciclo: 6, area: 'Hardware y Redes'}),

  (iai115:Materia {codigo: 'IAI115', nombre: 'Inteligencia Artificial', uv: 4, ciclo: 7, area: 'Ciencia de Datos e IA'}),
  (bin115:Materia {codigo: 'BIN115', nombre: 'Inteligencia de Negocios', uv: 4, ciclo: 8, area: 'Ciencia de Datos e IA'});

// 3. DEFINICIÓN DE DEPENDENCIAS Y PRERREQUISITOS (:MateriaA)-[:REQUIERE_APROBADA]->(:MateriaB)
// Significado semántico: Para cursar MateriaA es requisito previo haber cursado MateriaB
MATCH (m1:Materia {codigo: 'MAT215'}), (m2:Materia {codigo: 'MAT115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'PRG215'}), (m2:Materia {codigo: 'PRG115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);

MATCH (m1:Materia {codigo: 'MAT315'}), (m2:Materia {codigo: 'MAT215'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'PRG315'}), (m2:Materia {codigo: 'PRG215'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'BAD115'}), (m2:Materia {codigo: 'PRG115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);

MATCH (m1:Materia {codigo: 'BAD215'}), (m2:Materia {codigo: 'BAD115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'ADS115'}), (m2:Materia {codigo: 'PRG215'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);

MATCH (m1:Materia {codigo: 'SIF115'}), (m2:Materia {codigo: 'ADS115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'SIF115'}), (m2:Materia {codigo: 'BAD115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'ADS215'}), (m2:Materia {codigo: 'ADS115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);

MATCH (m1:Materia {codigo: 'DWB115'}), (m2:Materia {codigo: 'PRG315'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'ARC115'}), (m2:Materia {codigo: 'ACA115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);

MATCH (m1:Materia {codigo: 'IAI115'}), (m2:Materia {codigo: 'PRG315'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'IAI115'}), (m2:Materia {codigo: 'MAT315'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);

MATCH (m1:Materia {codigo: 'BIN115'}), (m2:Materia {codigo: 'BAD215'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);
MATCH (m1:Materia {codigo: 'BIN115'}), (m2:Materia {codigo: 'SIF115'}) CREATE (m1)-[:REQUIERE_APROBADA]->(m2);