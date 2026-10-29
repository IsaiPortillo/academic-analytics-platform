// Sidebar móvil — panel deslizante con fondo atenuado (< 1024px). Cierra al
// tocar el fondo, al elegir un enlace, con Escape y al ensanchar la ventana
// (girar la tablet); mientras está abierto la página de atrás no se desplaza,
// y el foco vuelve al botón que lo abrió.
const sidebarEl = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const navToggleEl = document.getElementById("navToggle");
function fijarSidebar(abierto) {
  sidebarEl?.classList.toggle("is-open", abierto);
  sidebarBackdrop?.classList.toggle("is-open", abierto);
  document.documentElement.classList.toggle("nav-open", abierto);
  navToggleEl?.setAttribute("aria-expanded", abierto ? "true" : "false");
  navToggleEl?.setAttribute("aria-label", abierto ? "Cerrar menú" : "Abrir menú");
}
function cerrarSidebar({ devolverFoco = false } = {}) {
  if (!sidebarEl?.classList.contains("is-open")) return;
  fijarSidebar(false);
  if (devolverFoco) navToggleEl?.focus();
}
navToggleEl?.addEventListener("click", () => {
  const abrir = !sidebarEl?.classList.contains("is-open");
  fijarSidebar(abrir);
  if (abrir) sidebarEl?.querySelector(".sidebar-link")?.focus({ preventScroll: true });
});
sidebarBackdrop?.addEventListener("click", () => cerrarSidebar());
sidebarEl?.querySelectorAll(".sidebar-link").forEach((enlace) => {
  enlace.addEventListener("click", () => cerrarSidebar());
});
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") cerrarSidebar({ devolverFoco: true });
});
window.matchMedia("(min-width: 1024px)").addEventListener("change", (evento) => {
  if (evento.matches) cerrarSidebar();
});

// Filtro de filas — la lista de secciones del coordinador trae TODAS las del período
// (casi 200); este campo la acota en el cliente por materia, código, número de
// sección o turno, sin tildes ni mayúsculas y con varios términos a la vez.
document.querySelectorAll("[data-filter-rows]").forEach((campo) => {
  const tabla = document.querySelector(campo.dataset.filterRows);
  if (!tabla) return;
  const contador = campo.dataset.filterCount ? document.querySelector(campo.dataset.filterCount) : null;
  const normalizar = (texto) => texto.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const filas = Array.from(tabla.querySelectorAll("tbody tr")).filter((fila) => !fila.querySelector("td[colspan]"));
  // Solo las celdas de datos: el texto de los botones ("Agregar", "Ver") no cuenta.
  const textos = filas.map((fila) => normalizar(
    Array.from(fila.cells).filter((c) => !c.classList.contains("cell-actions")).map((c) => c.textContent).join(" ")
  ));
  const aplicar = () => {
    const terminos = normalizar(campo.value.trim()).split(/\s+/).filter(Boolean);
    let visibles = 0;
    filas.forEach((fila, i) => {
      const coincide = terminos.every((termino) => textos[i].includes(termino));
      fila.hidden = !coincide;
      if (coincide) visibles += 1;
    });
    if (contador) {
      contador.textContent = terminos.length
        ? `${visibles} de ${filas.length} secciones`
        : `${filas.length} secciones`;
    }
  };
  campo.addEventListener("input", aplicar);
  aplicar();
});

// Altura real de la barra superior, para fijar debajo de ella los encabezados
// pegajosos (cambia con objetivos táctiles de 44px y con el notch).
(() => {
  const barra = document.querySelector(".topbar");
  if (!barra) return;
  const medir = () => {
    document.documentElement.style.setProperty("--topbar-h", `${barra.offsetHeight}px`);
  };
  medir();
  window.addEventListener("resize", medir);
})();

// ---------------------------------------------------------------------------
// Login — el campo de usuario toma el foco solo con puntero fino: en un
// teléfono el foco automático abre el teclado y tapa el formulario antes de
// que se vea. El rol de la sesión lo decide el rol_db real del usuario en la
// tabla usuarios, leído en auth.py después de validar la contraseña.
if (window.matchMedia("(pointer: fine)").matches) {
  document.querySelector('form[action="/login"] #username')?.focus();
}

// Acceso rápido de demostración — rellena y envía el mismo formulario con
// las cuentas sintéticas ya sembradas en la base (coordinador / docente),
// nunca credenciales o personas inventadas.
document.querySelectorAll(".js-demo-login").forEach((boton) => {
  boton.addEventListener("click", () => {
    const formulario = boton.closest("form") || document.querySelector('form[action="/login"]');
    const campoUsuario = document.getElementById("username");
    const campoPassword = document.getElementById("password");
    if (!formulario || !campoUsuario || !campoPassword) return;
    campoUsuario.value = boton.dataset.usuario;
    campoPassword.value = boton.dataset.password;
    formulario.requestSubmit();
  });
});

// ---------------------------------------------------------------------------
// Matrícula — dock de inscripción. El backend sigue aceptando una sola
// (estudiante_id, seccion_id) por POST a /matricula/inscribir; nada de esto
// es una API nueva, es el mismo endpoint llamado varias veces en secuencia
// desde el cliente. El dock junta las secciones elegidas para UN estudiante
// y las envía todas al pulsar "Confirmar Matrícula (N Materias)".
(() => {
  const dockPanel = document.getElementById("dock-panel");
  if (!dockPanel) return; // esta página no es /matricula

  const periodoId = dockPanel.dataset.periodoId;
  const listaEl = document.getElementById("dock-lista");
  const vacioEl = document.getElementById("dock-vacio");
  const advertenciaEl = document.getElementById("dock-advertencia");
  const confirmarBtn = document.getElementById("dock-confirmar");
  const estudianteChip = document.getElementById("dock-estudiante-chip");
  const estudianteIdManual = document.getElementById("estudiante-id-manual");

  // Estado en memoria: Map<seccion_id, {materia, numeroSeccion, turno, cupoTexto}>
  const dock = new Map();
  let estudianteId = null;

  function estudianteSeleccionado(id) {
    estudianteId = String(id);
    if (estudianteChip) {
      estudianteChip.textContent = `Estudiante en el dock: ${estudianteId}`;
      estudianteChip.classList.remove("hidden");
    }
    actualizarUI();
  }

  function renderDock() {
    if (!listaEl) return;
    listaEl.innerHTML = "";
    dock.forEach((item, seccionId) => {
      const fila = document.createElement("div");
      fila.className = "dock-item";
      fila.innerHTML = `
        <div>
          <div class="font-semibold text-sm">${item.materia}</div>
          <div class="text-xs text-muted">Sección ${item.numeroSeccion} &middot; ${item.turno} &middot; Cupo ${item.cupoTexto}</div>
        </div>
        <button type="button" class="dock-item-remove" data-seccion-id="${seccionId}" aria-label="Quitar">&times;</button>
      `;
      listaEl.appendChild(fila);
    });
    listaEl.querySelectorAll(".dock-item-remove").forEach((boton) => {
      boton.addEventListener("click", () => {
        dock.delete(boton.dataset.seccionId);
        renderDock();
        actualizarUI();
      });
    });
  }

  // Aviso informativo, no un bloqueo: no hay datos de horario (solo turno:
  // MATUTINO/VESPERTINO/NOCTURNO) ni de prerrequisitos en el sistema, así
  // que esto nunca finge validar un choque real — solo avisa que dos
  // materias comparten turno para que el coordinador lo verifique.
  function actualizarAdvertencia() {
    if (!advertenciaEl) return;
    const turnos = {};
    dock.forEach((item) => {
      turnos[item.turno] = (turnos[item.turno] || 0) + 1;
    });
    const repetido = Object.entries(turnos).find(([, n]) => n > 1);
    if (repetido) {
      advertenciaEl.textContent = `Dos o más materias comparten el turno ${repetido[0]} — verifica que no se traslapen en horario.`;
      advertenciaEl.classList.remove("hidden");
    } else {
      advertenciaEl.classList.add("hidden");
    }
  }

  // Atajo flotante (solo móvil/tablet, ver .dock-fab): el dock queda debajo de
  // toda la lista de secciones, así que mientras lleva algo y no está a la
  // vista, un botón fijo muestra cuántas lleva y salta a él.
  const fabEl = document.getElementById("dock-fab");
  const fabTextoEl = document.getElementById("dock-fab-texto");
  let dockVisible = false;
  function actualizarFab() {
    if (!fabEl) return;
    const mostrar = dock.size > 0 && !dockVisible;
    fabEl.classList.toggle("is-visible", mostrar);
    document.body.classList.toggle("has-fab", dock.size > 0);
    if (fabTextoEl) {
      fabTextoEl.textContent = `Ver dock · ${dock.size} ${dock.size === 1 ? "materia" : "materias"}`;
    }
  }
  fabEl?.addEventListener("click", () => {
    dockPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  if (fabEl && "IntersectionObserver" in window) {
    new IntersectionObserver((entradas) => {
      dockVisible = entradas[0].isIntersecting;
      actualizarFab();
    }, { threshold: 0.15 }).observe(dockPanel);
  }

  function actualizarUI() {
    actualizarFab();
    if (vacioEl) vacioEl.classList.toggle("hidden", dock.size > 0);
    if (listaEl) listaEl.classList.toggle("hidden", dock.size === 0);
    actualizarAdvertencia();
    if (confirmarBtn) {
      confirmarBtn.textContent = `Confirmar Matrícula (${dock.size} Materias)`;
      confirmarBtn.disabled = dock.size === 0 || !estudianteId;
    }
  }

  document.querySelectorAll(".js-dock-add").forEach((boton) => {
    boton.addEventListener("click", () => {
      const seccionId = boton.dataset.seccionId;
      if (dock.has(seccionId)) return; // ya está en el dock
      dock.set(seccionId, {
        materia: boton.dataset.materia,
        numeroSeccion: boton.dataset.numeroSeccion,
        turno: boton.dataset.turno,
        cupoTexto: boton.dataset.cupoTexto,
      });
      renderDock();
      actualizarUI();
    });
  });

  // Elegir en resultados de búsqueda: fija el estudiante del dock (ya no
  // envía un formulario — antes el botón y el input manual compartían
  // name="estudiante_id" dentro de un solo <form>, y el required del input
  // manual bloqueaba la validación nativa en cada click de "Elegir").
  document.querySelectorAll(".js-elegir-estudiante").forEach((boton) => {
    boton.addEventListener("click", () => {
      if (estudianteIdManual) estudianteIdManual.value = boton.dataset.estudianteId;
      estudianteSeleccionado(boton.dataset.estudianteId);
    });
  });
  document.getElementById("dock-usar-id")?.addEventListener("click", () => {
    const valor = estudianteIdManual ? estudianteIdManual.value.trim() : "";
    if (!valor) return;
    estudianteSeleccionado(valor);
  });

  confirmarBtn?.addEventListener("click", () => {
    if (!estudianteId || dock.size === 0) return;
    const materiaCount = dock.size;
    if (!confirm(`¿Matricular al estudiante ${estudianteId} en ${materiaCount} materia(s)?`)) {
      return;
    }

    confirmarBtn.disabled = true; // candado de doble clic: una sola pasada por dock
    confirmarBtn.textContent = "Matriculando…";

    // Un solo POST con todas las secciones: el servidor matricula cada una y deja
    // el resultado en la sesión, que la página de matrícula muestra al volver.
    const formulario = document.createElement("form");
    formulario.method = "post";
    formulario.action = "/matricula/inscribir";
    formulario.hidden = true;
    const campos = [
      ["csrf_token", dockPanel.querySelector('input[name="csrf_token"]')?.value || ""],
      ["periodo_id", periodoId],
      ["estudiante_id", estudianteId],
      ...[...dock.keys()].map((seccionId) => ["seccion_id", seccionId]),
    ];
    for (const [nombre, valor] of campos) {
      const campo = document.createElement("input");
      campo.type = "hidden";
      campo.name = nombre;
      campo.value = valor;
      formulario.appendChild(campo);
    }
    document.body.appendChild(formulario);
    formulario.submit();
  });
})();

document.querySelectorAll("[data-alert-close]").forEach((boton) => {
  boton.addEventListener("click", () => {
    const alerta = boton.closest(".alert");
    if (!alerta) return;
    alerta.classList.add("is-closing");
    alerta.addEventListener("transitionend", () => alerta.remove(), { once: true });
  });
});

// Tema claro/oscuro: el script en <head> ya aplicó la preferencia guardada
// (o ninguna, dejando que prefers-color-scheme decida) antes de pintar. Este
// botón solo alterna y persiste; nunca decide el estado inicial.
document.getElementById("temaToggle")?.addEventListener("click", () => {
  const raiz = document.documentElement;
  const actual = raiz.getAttribute("data-theme")
    || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const siguiente = actual === "dark" ? "light" : "dark";
  raiz.setAttribute("data-theme", siguiente);
  try {
    localStorage.setItem("tema", siguiente);
  } catch (e) {}
});

// Apariencia en Mi cuenta: Automático (sigue al dispositivo), Claro u Oscuro.
// Usa la misma clave de localStorage que el botón de la barra superior; Automático
// borra la preferencia y deja que decida prefers-color-scheme.
document.querySelectorAll("[data-tema-opciones]").forEach((grupo) => {
  const opciones = grupo.querySelectorAll("[data-tema]");
  const marcar = (valor) => {
    opciones.forEach((o) => o.setAttribute("aria-pressed", o.dataset.tema === valor ? "true" : "false"));
  };
  let guardado = "auto";
  try {
    const previo = localStorage.getItem("tema");
    if (previo === "light" || previo === "dark") guardado = previo;
  } catch (e) {}
  marcar(guardado);
  opciones.forEach((opcion) => {
    opcion.addEventListener("click", () => {
      const valor = opcion.dataset.tema;
      const raiz = document.documentElement;
      if (valor === "auto") raiz.removeAttribute("data-theme");
      else raiz.setAttribute("data-theme", valor);
      try {
        if (valor === "auto") localStorage.removeItem("tema");
        else localStorage.setItem("tema", valor);
      } catch (e) {}
      marcar(valor);
    });
  });
});

// ---------------------------------------------------------------------------
// Calificaciones — matriz densa. Cada columna de evaluación es su propio
// <form> (misma forma que espera POST /calificaciones/registrar: un solo
// evaluacion_id por envío) referenciado por atributo form="..." desde los
// <input> dentro de la tabla — así una sola tabla puede tener N formularios
// de columna sin anidarlos. Esto solo valida en el cliente lo que la base
// también exige (CHECK nota entre 0 y 10); el servidor sigue siendo la
// autoridad real.
document.querySelectorAll(".matrix-input").forEach((campo) => {
  campo.addEventListener("input", () => {
    const valor = campo.value.trim();
    const numero = Number(valor);
    const fueraDeRango = valor !== "" && (Number.isNaN(numero) || numero < 0 || numero > 10);
    campo.classList.toggle("is-invalid", fueraDeRango);
    const columna = campo.dataset.columna;
    if (!columna) return;
    const boton = document.querySelector(`.js-matrix-save[data-columna="${columna}"]`);
    if (!boton) return;
    const algunaInvalida = document.querySelectorAll(
      `.matrix-input[data-columna="${columna}"].is-invalid`
    ).length > 0;
    boton.disabled = algunaInvalida;
  });
});

// Gráfico de columnas por período (vista ejecutiva): en pantallas angostas desliza
// dentro de su tarjeta; al cargar se centra en el período seleccionado, que de lo
// contrario queda a la derecha, fuera de vista.
document.querySelectorAll(".chart-scroll").forEach((contenedor) => {
  const elegida = contenedor.querySelector(".column.is-selected");
  if (!elegida || contenedor.scrollWidth <= contenedor.clientWidth) return;
  const desplazamiento = elegida.getBoundingClientRect().left
    - contenedor.getBoundingClientRect().left + contenedor.scrollLeft;
  contenedor.scrollLeft = desplazamiento - (contenedor.clientWidth - elegida.offsetWidth) / 2;
});

// Chequeo de ponderación — 100% es la meta declarada por el docente al crear
// evaluaciones; esto solo visualiza sum(porcentaje) ya calculado en el
// servidor (ponderacion_usada), nunca la recalcula en el cliente.
document.querySelectorAll("[data-weight-check]").forEach((contenedor) => {
  const usada = Number(contenedor.dataset.weightCheck);
  const fill = contenedor.querySelector(".weight-check-fill");
  if (!fill) return;
  fill.style.setProperty("--pct", Math.min(usada, 100) / 100);
  fill.classList.toggle("is-complete", usada === 100);
  fill.classList.toggle("is-over", usada > 100);
});

// ---------------------------------------------------------------------------
// Asistencia — toggle de un toque. Cada fila tiene un <input type="hidden"
// name="estado"> (el mismo campo que ya esperaba el <select> que reemplaza)
// más tres botones que lo fijan; el conteo del encabezado se recalcula en
// cada toque a partir del DOM, no de una llamada al servidor.
function recalcularTally() {
  const contenedor = document.getElementById("tally-bar");
  if (!contenedor) return;
  const conteo = { PRESENTE: 0, AUSENTE: 0, JUSTIFICADO: 0 };
  let pendientes = 0;
  document.querySelectorAll(".tap-toggle-group").forEach((grupo) => {
    // El input oculto es hermano del grupo dentro del mismo <td>, no
    // descendiente — querySelector debe buscar desde el <td>, y por nombre
    // específico: inscripcion_id es otro hidden en la misma celda.
    const campo = grupo.closest("td")?.querySelector('input[name="estado"]');
    const valor = campo ? campo.value : "";
    if (valor && conteo[valor] !== undefined) {
      conteo[valor] += 1;
    } else {
      pendientes += 1;
    }
  });
  const total = document.querySelectorAll(".tap-toggle-group").length;
  contenedor.querySelector(".js-tally-presente").textContent = conteo.PRESENTE;
  contenedor.querySelector(".js-tally-ausente").textContent = conteo.AUSENTE;
  contenedor.querySelector(".js-tally-justificado").textContent = conteo.JUSTIFICADO;
  const pendienteChip = contenedor.querySelector(".js-tally-pendiente");
  if (pendienteChip) {
    pendienteChip.textContent = `${pendientes} pendiente(s) de ${total}`;
    pendienteChip.classList.toggle("hidden", pendientes === 0);
  }
}

document.querySelectorAll(".tap-toggle").forEach((boton) => {
  boton.addEventListener("click", () => {
    const grupo = boton.closest(".tap-toggle-group");
    if (!grupo) return;
    const campo = grupo.closest("td")?.querySelector('input[name="estado"]');
    if (campo) campo.value = boton.dataset.estado;
    grupo.querySelectorAll(".tap-toggle").forEach((hermano) => {
      hermano.setAttribute("aria-pressed", hermano === boton ? "true" : "false");
    });
    recalcularTally();
  });
});
recalcularTally();

// "Marcar todos presentes": fija el mismo estado en cada fila. No guarda: el
// docente revisa las excepciones y luego pulsa Guardar.
document.querySelectorAll("[data-marcar-todos]").forEach((boton) => {
  boton.addEventListener("click", () => {
    const estado = boton.dataset.marcarTodos;
    boton.closest("form")?.querySelectorAll(`.tap-toggle[data-estado="${estado}"]`).forEach((opcion) => {
      if (!opcion.disabled) opcion.click();
    });
  });
});

// ---------------------------------------------------------------------------
// Skeleton de carga en filtros — periodo/materia/checkbox ya disparaban
// this.form.submit() en el onchange existente; esto solo cubre el hueco real
// entre ese click y la respuesta del servidor con filas de esqueleto en vez
// de dejar la tabla vieja congelada sin ninguna señal.
document.querySelectorAll("[data-skeleton-on-filter]").forEach((filtro) => {
  filtro.addEventListener("change", () => {
    const tabla = document.querySelector(filtro.dataset.skeletonOnFilter);
    if (!tabla) return;
    const columnas = tabla.querySelectorAll("thead th").length || 1;
    const filas = Array.from({ length: 5 }, () => {
      const celdas = Array.from(
        { length: columnas },
        () => `<td><span class="skeleton skeleton-text"></span></td>`
      ).join("");
      return `<tr class="skeleton-row">${celdas}</tr>`;
    }).join("");
    const cuerpo = tabla.querySelector("tbody");
    if (cuerpo) cuerpo.innerHTML = filas;
  });
});

// ---------------------------------------------------------------------------
// Red curricular (Fase 4.3) — elegir una materia resalta lo que bloquea (sus
// dependientes, en cascada) y lo que hay que aprobar antes (sus prerrequisitos).
// Todo sale de #red-datos, que la plantilla arma con las relaciones del DW: no
// hay consultas ni cálculo de grafo en el navegador, solo pintar clases.
(() => {
  const fuente = document.getElementById("red-datos");
  if (!fuente) return;
  const datos = JSON.parse(fuente.textContent);
  const panel = document.getElementById("red-detalle");
  const nodosEl = new Map();
  document.querySelectorAll(".red-nodo").forEach((el) => nodosEl.set(el.dataset.codigo, el));
  const aristasEl = Array.from(document.querySelectorAll(".red-arista"));

  const lista = (codigos) => (codigos.length ? codigos.join(", ") : "ninguna");
  const linea = (texto, clase) => {
    const p = document.createElement("p");
    if (clase) p.className = clase;
    p.textContent = texto;
    return p;
  };

  function pintarPanel(n) {
    panel.replaceChildren();
    const titulo = document.createElement("div");
    titulo.className = "red-detalle-titulo";
    const nombre = document.createElement("span");
    nombre.textContent = `${n.codigo} · ${n.nombre}`;
    titulo.appendChild(nombre);
    const etiqueta = document.createElement("span");
    etiqueta.className = `badge ${n.cuello ? "badge-danger" : "badge-neutral"}`;
    etiqueta.textContent = n.cuello ? "Cuello de botella" : `Ciclo ${n.ciclo}`;
    titulo.appendChild(etiqueta);
    panel.appendChild(titulo);

    panel.appendChild(linea(
      n.totales === 0
        ? "No es prerrequisito de ninguna materia: reprobarla no deja bloqueada a otra."
        : `Reprobarla deja sin poder cursar a ${n.totales} materia${n.totales === 1 ? "" : "s"} ` +
          `(${n.directos} directa${n.directos === 1 ? "" : "s"} y ${n.indirectos} en cascada, ` +
          `${n.pct_plan} del plan): ${lista(n.dependientes)}.`
    ));
    panel.appendChild(linea(
      n.requisitos.length === 0
        ? "No exige ninguna materia previa."
        : `Exige aprobar antes: ${lista(n.requisitos_directos)}` +
          (n.requisitos.length > n.requisitos_directos.length
            ? ` (${n.requisitos.length} en toda la cadena).` : ".")
    ));
    panel.appendChild(linea(
      `Costo de reprobación ${n.costo} (${n.pct_costo} del total) · ${n.reprobados} reprobados` +
      `${n.tasa !== "—" ? ` (tasa ${n.tasa})` : ""} · ${n.bloqueos.toLocaleString("es-SV")} bloqueos generados. ` +
      `${n.tipo_texto}.`, "red-detalle-dato"
    ));
  }

  function limpiar() {
    nodosEl.forEach((el) => {
      el.classList.remove("is-seleccion", "is-dependiente", "is-prerrequisito", "is-atenuado");
      el.setAttribute("aria-pressed", "false");
    });
    aristasEl.forEach((el) => el.classList.remove("is-dependiente", "is-prerrequisito", "is-atenuado"));
  }

  function seleccionar(codigo) {
    const n = datos.nodos[codigo];
    if (!n) return;
    const dependientes = new Set(n.dependientes);
    const requisitos = new Set(n.requisitos);
    nodosEl.forEach((el, c) => {
      el.classList.toggle("is-seleccion", c === codigo);
      el.classList.toggle("is-dependiente", dependientes.has(c));
      el.classList.toggle("is-prerrequisito", requisitos.has(c));
      el.classList.toggle("is-atenuado", c !== codigo && !dependientes.has(c) && !requisitos.has(c));
      el.setAttribute("aria-pressed", c === codigo ? "true" : "false");
    });
    aristasEl.forEach((el) => {
      const { origen, destino } = el.dataset;
      const baja = (origen === codigo || dependientes.has(origen)) && dependientes.has(destino);
      const sube = (destino === codigo || requisitos.has(destino)) && requisitos.has(origen);
      el.classList.toggle("is-dependiente", baja);
      el.classList.toggle("is-prerrequisito", sube);
      el.classList.toggle("is-atenuado", !baja && !sube);
    });
    pintarPanel(n);
  }

  nodosEl.forEach((el, codigo) => {
    el.addEventListener("click", () => {
      seleccionar(codigo);
      // En pantallas angostas la materia elegida puede quedar en el borde: se centra
      // dentro del lienzo (solo en horizontal, sin mover la página).
      const lienzo = document.getElementById("red-lienzo");
      if (lienzo) {
        const caja = el.getBoundingClientRect();
        const marco = lienzo.getBoundingClientRect();
        lienzo.scrollBy({
          left: caja.left - marco.left - (marco.width - caja.width) / 2,
          behavior: "smooth",
        });
      }
    });
    el.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter" || evento.key === " ") {
        evento.preventDefault();
        seleccionar(codigo);
      }
    });
  });
  document.getElementById("red-reiniciar")?.addEventListener("click", () => {
    limpiar();
    panel.replaceChildren(linea("Toca una materia de la red para ver qué bloquea y qué exige.", "text-sm text-muted"));
  });

  seleccionar(datos.inicial);
})();

// Usuarios: el campo «Docente» solo aplica (y solo se envía) con el rol docente.
document.querySelectorAll("select[data-rol-docente]").forEach((selector) => {
  const campo = document.querySelector(selector.dataset.rolDocente);
  if (!campo) return;
  const sincronizar = () => {
    const esDocente = selector.value === "rol_docente";
    campo.hidden = !esDocente;
    const lista = campo.querySelector("select");
    if (lista) {
      lista.disabled = !esDocente;
      lista.required = esDocente;
    }
  };
  selector.addEventListener("change", sincronizar);
  sincronizar();
});

// Copiar al portapapeles (contraseña temporal).
document.querySelectorAll("[data-copiar]").forEach((boton) => {
  boton.addEventListener("click", async () => {
    const origen = document.querySelector(boton.dataset.copiar);
    if (!origen) return;
    try {
      await navigator.clipboard.writeText(origen.textContent.trim());
      boton.textContent = "Copiada";
    } catch (e) {
      const rango = document.createRange();
      rango.selectNodeContents(origen);
      const seleccion = window.getSelection();
      seleccion.removeAllRanges();
      seleccion.addRange(rango);
      boton.textContent = "Selecciónala y cópiala";
    }
  });
});

// Confirmaciones antes de enviar. Van en fase de captura para correr antes que
// el candado de doble clic: si se cancelan, el botón no queda bloqueado.
//   data-confirmar="…"                  pregunta siempre.
//   data-confirmar-sobrescritura="…{n}…" pregunta solo si el envío cambia valores
//     ya registrados (campos con data-original no vacío), y dice cuántos.
//     Usa formulario.elements, que incluye los campos asociados con form="…"
//     fuera del <form> (la matriz de notas).
function mismoValor(a, b) {
  const x = Number(a);
  const y = Number(b);
  return a !== "" && b !== "" && !Number.isNaN(x) && !Number.isNaN(y) ? x === y : a === b;
}
document.querySelectorAll("form[data-confirmar]").forEach((formulario) => {
  formulario.addEventListener("submit", (evento) => {
    if (!confirm(formulario.dataset.confirmar)) evento.preventDefault();
  }, true);
});
document.querySelectorAll("form[data-confirmar-sobrescritura]").forEach((formulario) => {
  formulario.addEventListener("submit", (evento) => {
    const cambiados = Array.from(formulario.elements).filter((campo) => {
      const original = campo.dataset ? campo.dataset.original : undefined;
      const actual = (campo.value || "").trim();
      return original !== undefined && original !== "" && actual !== "" && !mismoValor(actual, original);
    }).length;
    if (cambiados === 0) return;
    const mensaje = formulario.dataset.confirmarSobrescritura.replace("{n}", cambiados);
    if (!confirm(mensaje)) evento.preventDefault();
  }, true);
});

// Candado de doble clic genérico — deshabilita cualquier submit marcado
// data-lock-on-submit apenas se envía, para que una escritura no idempotente
// (crear evaluación, registrar asistencia) no viaje dos veces por un doble
// clic mientras la página todavía no recarga.
document.querySelectorAll("[data-lock-on-submit]").forEach((formulario) => {
  formulario.addEventListener("submit", (evento) => {
    if (evento.defaultPrevented) return; // se canceló una confirmación: no bloquear
    const boton = formulario.querySelector('button[type="submit"]');
    if (!boton) return;
    boton.disabled = true;
    boton.dataset.textoOriginal = boton.textContent;
    boton.textContent = formulario.dataset.lockOnSubmit || "Guardando…";
  });
});

// Descargas de reportes: evita pedir el mismo archivo varias veces mientras el
// servidor lo genera (un PDF largo tarda uno o dos segundos).
document.querySelectorAll("[data-descarga]").forEach((enlace) => {
  enlace.addEventListener("click", () => {
    enlace.classList.add("is-generando");
    enlace.setAttribute("aria-busy", "true");
    setTimeout(() => {
      enlace.classList.remove("is-generando");
      enlace.removeAttribute("aria-busy");
    }, 3000);
  });
});
