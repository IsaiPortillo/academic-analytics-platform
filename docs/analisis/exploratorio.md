# Análisis descriptivo y exploratorio del costo de reprobación

Resultados de `scripts/analisis/exploratorio.sql`, ejecutado sobre el Data Warehouse el 28 de
octubre de 2026. Para reproducirlo:

```bash
docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < scripts/analisis/exploratorio.sql
```

> Los datos son **sintéticos** y el costo por unidad valorativa es un **supuesto paramétrico**. Lo
> que se demuestra aquí es el método de análisis, no la magnitud de un fenómeno real.

---

## 1. Resumen de cinco números

Variable: **costo de reprobación acumulado por estudiante**, sobre los 1.493 estudiantes que
reprobaron al menos una asignatura.

| Mínimo | Q1 | Mediana | Q3 | Máximo | Media | Desviación |
|---|---|---|---|---|---|---|
| 100,00 | 400,00 | 500,00 | 700,00 | 1.500,00 | 537,17 | 246,10 |

**Interpretación.** La media (537) supera a la mediana (500) en un 7 %: hay una asimetría a la
derecha, pero moderada. La mitad central de los estudiantes se concentra entre 400 y 700 dólares,
un rango intercuartílico de 300. El máximo, 1.500, es tres veces la mediana: existen casos
extremos, pero no dominan la distribución.

Se eligió esta variable y no la nota porque es la del problema de negocio y porque su distribución
es asimétrica, que es justamente donde el promedio engaña y el análisis exploratorio aporta.

---

## 2. Histograma

Diez tramos de igual amplitud entre el mínimo y el máximo:

| Tramo (USD) | Estudiantes | % |
|---|---|---|
| 100 – 240 | 179 | 12,0 |
| 240 – 380 | 181 | 12,1 |
| **380 – 520** | **467** | **31,3** |
| 520 – 660 | 201 | 13,5 |
| 660 – 800 | 288 | 19,3 |
| 800 – 940 | 95 | 6,4 |
| 940 – 1.080 | 46 | 3,1 |
| 1.080 – 1.220 | 27 | 1,8 |
| 1.220 – 1.360 | 7 | 0,5 |
| 1.360 – 1.500 | 2 | 0,1 |

**Interpretación.** La distribución tiene una moda marcada en el tramo de 380 a 520 dólares, que
concentra casi un tercio de los estudiantes, y una cola derecha larga y delgada: los cuatro tramos
superiores juntan apenas el 5,5 %. Es la forma típica de un fenómeno acumulativo —cada
reprobación adicional suma un costo fijo— donde pocos acumulan muchas.

El resumen de cinco números por sí solo no habría mostrado la moda ni el segundo repunte en el
tramo de 660 a 800. Es el argumento de por qué el histograma acompaña al resumen y no lo sustituye.

---

## 3. Valores atípicos (criterio del rango intercuartílico)

Criterio de Tukey: es atípico lo que queda fuera de `[Q1 − 1,5·RIC, Q3 + 1,5·RIC]`. Se usó este
criterio y no el de las desviaciones estándar porque los cuartiles no se dejan arrastrar por los
propios valores extremos, que es exactamente lo que se quiere detectar.

| Rango intercuartílico | Cerco superior | Atípicos altos | % de estudiantes | Su costo | % del costo total |
|---|---|---|---|---|---|
| 300,00 | 1.150,00 | 20 | 1,34 % | 25.200,00 | 3,1 % |

No hay atípicos por debajo: el mínimo posible es una sola reprobación.

Los diez casos más extremos:

| Estudiante (anonimizado) | Costo | Materias reprobadas | Repeticiones |
|---|---|---|---|
| 25659e57… | 1.500,00 | 15 | 4 |
| c61ebbc9… | 1.400,00 | 14 | 3 |
| cf99a38e… | 1.300,00 | 13 | 2 |
| c26b0569… | 1.300,00 | 13 | 4 |
| 49b837bb… | 1.300,00 | 13 | 2 |

**Interpretación.** Los veinte atípicos son el 1,34 % de los estudiantes y explican el 3,1 % del
costo. La concentración existe pero es débil: no estamos ante un caso donde unos pocos expliquen
el grueso del gasto.

Lo que sí revela la tabla es el **mecanismo**: los extremos no son estudiantes que reprobaron una
materia muy cara, sino que reprobaron **muchas** —de 12 a 15— y además repitieron varias. El costo
extremo se construye por acumulación, no por un evento aislado. Esa distinción importa para
cualquier intervención: actuar sobre el número de materias que un estudiante cursa a la vez tendría
más efecto que actuar sobre una asignatura concreta.

---

## 4. Análisis de Pareto por asignatura

| Puesto | Código | Materia | Costo | % | % acumulado |
|---|---|---|---|---|---|
| 1 | BAD215 | Bases de Datos II | 59.400 | 7,4 | 7,4 |
| 2 | ACA115 | Álgebra Vectorial y Matrices | 55.200 | 6,9 | 14,3 |
| 3 | DWB115 | Diseño Web y Aplicaciones | 55.000 | 6,9 | 21,1 |
| 4 | BAD115 | Bases de Datos I | 52.800 | 6,6 | 27,7 |
| … | | | | | |
| 13 | PRG115 | Programación I **(cuello de botella)** | 46.600 | 5,8 | 83,8 |
| 15 | PRG215 | Programación II **(cuello de botella)** | 43.600 | 5,4 | 94,8 |
| 16 | MAT115 | Matemática I | 41.700 | 5,2 | 100,0 |

**El principio de Pareto no se cumple en este conjunto de datos.** El 20 % de las asignaturas
concentra el **27,7 %** del costo, no el 80 %; y para llegar al 80 % hacen falta **13 de las 16**
asignaturas. La distribución es casi uniforme: entre la primera y la última hay solo 2,2 puntos
porcentuales de diferencia.

**Interpretación.** Esto es una propiedad de los datos sintéticos, no un hallazgo sobre la
institución: el generador reparte las reprobaciones de forma aproximadamente uniforme entre
asignaturas. Con datos reales cabría esperar concentración, y el análisis la detectaría. Declararlo
es preferible a forzar una lectura de Pareto que los datos no sostienen.

**Un hallazgo que sí es del modelo y no de los datos.** Las dos asignaturas cuello de botella
—Programación I y Programación II— aparecen en los puestos 13 y 15, es decir, entre las **más
baratas** en costo directo. Esto confirma el argumento del planteamiento: el costo directo
**subestima** el efecto de una asignatura crítica, porque no captura que reprobarla bloquea el
avance hacia otras diez. Medir solo el costo directo llevaría a priorizar Bases de Datos II sobre
Programación I, que es probablemente la decisión equivocada.

---

## 5. Comparación temporal con media móvil

| Ciclo | Costo | Media móvil (3) | Tasa | Tasa media móvil (3) | Variación |
|---|---|---|---|---|---|
| 2022-I | 98.900 | 98.900 | 24,0 % | 24,0 % | — |
| 2022-II | 101.500 | 100.200 | 25,1 % | 24,5 % | +2,6 % |
| 2023-I | 104.600 | 101.667 | 25,1 % | 24,7 % | +3,1 % |
| 2023-II | 99.500 | 101.867 | 24,3 % | 24,9 % | −4,9 % |
| 2024-I | 100.500 | 101.533 | 24,2 % | 24,6 % | +1,0 % |
| 2024-II | 98.600 | 99.533 | 23,6 % | 24,0 % | −1,9 % |
| 2025-I | 97.700 | 98.933 | 23,9 % | 23,9 % | −0,9 % |
| 2025-II | 100.700 | 99.000 | 24,4 % | 24,0 % | +3,1 % |

**Interpretación.** La serie original oscila entre −4,9 % y +3,1 % de un ciclo a otro, lo que
invita a leer cada movimiento como una señal. La media móvil muestra que no lo es: el suavizado
describe una meseta en torno a 100.000 dólares con un descenso leve desde 2023-II. Ninguna
variación individual se sostiene en la tendencia.

**Nota metodológica importante.** La media móvil del costo se calcula promediando los costos,
porque el costo es una medida aditiva. La de la **tasa** no puede calcularse así: promediar las
tasas de tres ciclos sería un promedio de promedios. Se calcula dividiendo la suma de los
numeradores entre la suma de los denominadores dentro de la ventana, que es la forma correcta de
agregar una razón. La consulta lo implementa explícitamente.

---

## Síntesis

| Técnica | Qué mostró |
|---|---|
| Cinco números | Asimetría moderada a la derecha; mitad central entre 400 y 700 |
| Histograma | Moda en 380–520 y cola derecha delgada, que el resumen no revelaba |
| Atípicos | 1,34 % de estudiantes, 3,1 % del costo; extremos por acumulación, no por evento |
| Pareto | **No se cumple**; propiedad de los datos sintéticos, declarada como tal |
| Media móvil | Meseta en torno a 100.000; las variaciones por ciclo son ruido |

El hallazgo más útil para la institución no sale de la distribución del costo, sino del cruce con
la malla curricular: **las asignaturas más caras no son las más críticas**. Las dos que bloquean el
avance de más estudiantes están entre las de menor costo directo.
