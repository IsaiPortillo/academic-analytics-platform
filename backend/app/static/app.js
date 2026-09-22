document.getElementById("navToggle")?.addEventListener("click", () => {
  document.getElementById("navMenu")?.classList.toggle("hidden");
});

document.querySelectorAll("[data-alert-close]").forEach((boton) => {
  boton.addEventListener("click", () => boton.closest(".alert")?.remove());
});
