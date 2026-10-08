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

// ---------------------------------------------------------------------------
// Login — el selector de rol solo cambia el rótulo ilustrativo del banner
// SQL (qué SET LOCAL ROLE ejecutará el backend real al autenticar), nunca
// decide el rol de la sesión: eso lo determina el rol_db real del usuario en
// la tabla usuarios, leído en auth.py después de validar la contraseña.
// El campo de usuario toma el foco solo con puntero fino: en un teléfono el
// foco automático abre el teclado y tapa el formulario antes de que se vea.
if (window.matchMedia("(pointer: fine)").matches) {
  document.querySelector('form[action="/login"] #username')?.focus();
}

document.querySelectorAll("#rolSelector .tap-toggle").forEach((boton) => {
  boton.addEventListener("click", () => {
    document.querySelectorAll("#rolSelector .tap-toggle").forEach((hermano) => {
      hermano.setAttribute("aria-pressed", hermano === boton ? "true" : "false");
    });
    const banner = document.getElementById("sqlBanner");
    if (!banner) return;
    const rol = boton.dataset.rol;
    banner.innerHTML = `BEGIN;\n<span class="kw">SET LOCAL ROLE</span> ${rol};\n<span class="str">-- transacción autorizada por PostgreSQL, no por esta interfaz</span>\nCOMMIT;`;
  });
});

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

  confirmarBtn?.addEventListener("click", async () => {
    if (!estudianteId || dock.size === 0) return;
    const materiaCount = dock.size;
    if (!confirm(`¿Matricular al estudiante ${estudianteId} en ${materiaCount} materia(s)?`)) {
      return;
    }

    confirmarBtn.disabled = true; // candado de doble clic: una sola pasada por dock
    confirmarBtn.textContent = "Matriculando…";

    let exitos = 0;
    let ultimoError = null;
    let ultimaSeccion = null;
    for (const [seccionId] of dock) {
      ultimaSeccion = seccionId;
      try {
        const cuerpo = new URLSearchParams({
          periodo_id: periodoId,
          seccion_id: seccionId,
          estudiante_id: estudianteId,
        });
        const respuesta = await fetch("/matricula/inscribir", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: cuerpo,
        });
        const url = new URL(respuesta.url);
        if (url.searchParams.get("ok")) {
          exitos += 1;
        } else {
          ultimoError = url.searchParams.get("error") || "Error desconocido";
        }
      } catch (e) {
        ultimoError = "No se pudo conectar con el servidor";
      }
    }

    const destino = new URL(`/matricula`, window.location.origin);
    destino.searchParams.set("periodo_id", periodoId);
    destino.searchParams.set("seccion_id", ultimaSeccion || "");
    if (exitos > 0) {
      destino.searchParams.set(
        "ok",
        exitos === materiaCount
          ? `Estudiante ${estudianteId} matriculado en ${exitos} materia(s) correctamente`
          : `Estudiante ${estudianteId} matriculado en ${exitos} de ${materiaCount} materia(s)`
      );
    }
    if (ultimoError) {
      destino.searchParams.set("error", ultimoError);
    }
    window.location.href = destino.toString();
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
// Dashboard — modal de detalle de grafo del estudiante. Contenido ilustrativo
// (ver preview-banner de la página): la telemetría de la consulta Cypher es
// texto de ejemplo, nunca una medición real, porque el motor GDS de Neo4j
// todavía no está desplegado (Fase 3 del roadmap).
(() => {
  const modal = document.getElementById("modalGrafo");
  if (!modal) return;
  const titulo = document.getElementById("modalGrafoTitulo");
  const descripcion = document.getElementById("modalGrafoDescripcion");
  const badges = document.getElementById("modalGrafoBadges");
  const cypher = document.getElementById("modalGrafoCypher");

  document.querySelectorAll(".graph-node-group").forEach((nodo) => {
    nodo.addEventListener("click", () => {
      const { codigo, nombre, uv, reprobacion, bloqueada } = nodo.dataset;
      titulo.textContent = `${codigo} · ${nombre}`;
      descripcion.textContent = bloqueada === "true"
        ? `Bloqueada aguas abajo: reprobar el prerrequisito proyecta +2 ciclos de retraso hasta grado.`
        : `${uv} unidades valorativas · ${reprobacion}% de reprobación histórica en este subgrafo.`;
      badges.innerHTML = "";
      [
        bloqueada === "true" ? ["Bloqueada", "badge-danger"] : ["Habilitada", "badge-success"],
        ["DAG verificado", "badge-neutral"],
      ].forEach(([texto, clase]) => {
        const span = document.createElement("span");
        span.className = `badge ${clase}`;
        span.textContent = texto;
        badges.appendChild(span);
      });
      cypher.innerHTML = `MATCH (a:Asignatura {codigo: "${codigo}"})-[:REQUIERE*1..3]->(p)\n<span class="kw">RETURN</span> p.codigo, p.nombre, p.estado\n<span class="str">// subgrafo ilustrativo — motor GDS aún no desplegado</span>`;
      modal.classList.remove("hidden");
    });
  });
  document.getElementById("modalGrafoCerrar")?.addEventListener("click", () => {
    modal.classList.add("hidden");
  });
  modal.addEventListener("click", (evento) => {
    if (evento.target === modal) modal.classList.add("hidden");
  });

  document.getElementById("btnExportCypher")?.addEventListener("click", () => {
    alert("Exportación .cypher disponible cuando el motor de grafo entre en producción (Fase 3 del roadmap).");
  });
})();

// Alertas/OLAP — "Notificar a Consejería" es una maqueta: confirma la
// intención de la acción sin enviar nada, porque no existe todavía un canal
// real de notificación a consejería en el backend.
document.querySelectorAll(".js-notificar").forEach((boton) => {
  boton.addEventListener("click", () => {
    boton.textContent = "Notificado (simulado)";
    boton.disabled = true;
  });
});

// Candado de doble clic genérico — deshabilita cualquier submit marcado
// data-lock-on-submit apenas se envía, para que una escritura no idempotente
// (crear evaluación, registrar asistencia) no viaje dos veces por un doble
// clic mientras la página todavía no recarga.
document.querySelectorAll("[data-lock-on-submit]").forEach((formulario) => {
  formulario.addEventListener("submit", () => {
    const boton = formulario.querySelector('button[type="submit"]');
    if (!boton) return;
    boton.disabled = true;
    boton.dataset.textoOriginal = boton.textContent;
    boton.textContent = formulario.dataset.lockOnSubmit || "Guardando…";
  });
});
