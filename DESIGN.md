---
name: Plataforma de Gestión Académica y Analítica de Rendimiento Estudiantil
description: Internal staff tool for academic records, grades, attendance, and enrollment — DB-enforced security, plain and procedural by design.
colors:
  slate-authority: "#212529"
  registrar-blue: "#0d6efd"
  neutral-paper: "#f8f9fa"
  ledger-green: "#198754"
  filed-red: "#dc3545"
  caution-amber: "#ffc107"
  index-cyan: "#0dcaf0"
  quiet-gray: "#6c757d"
  hairline-border: "rgba(0, 0, 0, 0.08)"
  input-border: "#ced4da"
  alert-success-text: "#0f5132"
  alert-danger-text: "#842029"
typography:
  title:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: normal
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: normal
  label:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: normal
  caption:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.02em"
rounded:
  sm: "4px"
  md: "6px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-login:
    backgroundColor: "{colors.slate-authority}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-save:
    backgroundColor: "{colors.ledger-green}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-view:
    backgroundColor: "transparent"
    textColor: "{colors.registrar-blue}"
    rounded: "{rounded.md}"
    padding: "4px 8px"
  button-destructive:
    backgroundColor: "transparent"
    textColor: "{colors.filed-red}"
    rounded: "{rounded.md}"
    padding: "4px 8px"
  card:
    backgroundColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "16px"
---

# Design System: Plataforma de Gestión Académica y Analítica de Rendimiento Estudiantil

## Overview

**Creative North Star: "The Registrar's Desk"**

This is the interface of a university records office, not a product marketing site. Every screen exists so a coordinador or docente can process a specific transaction — enroll a student, post a grade, mark a session — and trust that the database, not the UI, is the actual authority on whether that transaction is allowed. The visual system gets out of the way of that trust: a near-black navbar and login action stand in for an official stamp rather than a brand mark, and color never appears without a status to report.

This plainness is currently a placeholder rather than a locked identity — no dedicated visual-design pass has happened yet — but until that pass happens, consistency with the patterns below matters more than novelty. Don't let one new screen drift toward decoration while the rest of the app stays procedural.

**Key Characteristics:**
- Dense, table-driven, procedural — optimized for a staff member processing many records quickly.
- Status is communicated through color (badges), never through illustration or iconography.
- Completely flat: no shadows, no gradients, anywhere.
- Spanish-only copy; no decorative imagery, ever (no real photography or illustration exists or should be fabricated).

## Colors

Built as a small, named Tailwind v4 theme (`@theme` in `backend/app/static/src/input.css`) rather than a generic palette — every color exists to mark status or structure, never to decorate.

### Primary
- **Slate Authority** (`#212529`): the navbar background and the single highest-weight action on a page (`login`'s "Ingresar" button). Reserved for the one action per screen that matters most.

### Secondary
- **Registrar Blue** (`#0d6efd`): links and "view / navigate" actions (`Ver` buttons opening a sección's detail panel). Never used for the primary call-to-action — that's Slate Authority's role.

### Neutral
- **Neutral Paper** (`#f8f9fa`): the page background.
- **Quiet Gray** (`#6c757d`): secondary/muted text, eyebrow labels, helper copy.
- **Hairline Border** (`rgba(0, 0, 0, 0.08)`): every card and table-row border in the system.
- **Input Border** (`#ced4da`): the resting-state border on text inputs and selects (distinct from the structural hairline — slightly more visible, since it marks an editable control).

### Status (badges, alerts)
- **Ledger Green** (`#198754`): success — save/submit buttons, "at 100%" or "no faltas" badges, success alert banners.
- **Filed Red** (`#dc3545`): danger — destructive actions (Retirar), over-capacity or high-faltas badges, error alert banners.
- **Caution Amber** (`#ffc107`): warning — near-capacity, some-but-not-critical faltas.
- **Index Cyan** (`#0dcaf0`): informational counts with no risk implication (e.g. "sesiones registradas").
- **Alert Success Text** (`#0f5132`) / **Alert Danger Text** (`#842029`): the readable foreground colors used inside the tinted success/danger alert banners — never the raw status color at full strength as text-on-tint.

### Named Rules
**The Status-Only Color Rule.** Color beyond ink/blue/gray exists to answer "is this okay?" — success, warning, danger, info, secondary badges — and for nothing else. A screen with no status to report has no colored elements beyond the navbar and its one primary button.

## Typography

**Body & Display Font:** system UI stack (`system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`), set once via the `--font-sans` theme token. No webfont is loaded anywhere in the app.

**Character:** Plain and administrative. The type system makes no personality claim of its own; it defers entirely to the OS default so nothing about the typography competes with the data it's presenting.

### Hierarchy
- **Title** (weight 500, 1.75rem, line-height 1.2): page headers ("Registro de calificaciones", "Control de asistencia").
- **Subtitle** (weight 500, 1.25rem): one-off moments like the login screen's "Gestión Académica".
- **Body** (weight 400, 1rem, line-height 1.5): table cells, form labels, paragraph copy — the vast majority of all on-screen text.
- **Label** (weight 400, 0.875rem): card headers, field labels, button and nav-link text, secondary helper text.
- **Caption** (weight 700, 0.75rem, 0.02em tracking): badge text only — the smallest, boldest, most compressed role in the system, reserved for status markers.

## Layout

Everything lives inside a centered `max-w-6xl` column with `px-4 py-6` padding — the Tailwind equivalent of the old Bootstrap container, applied directly as utilities rather than a named class. The established module pattern (Matrícula, Calificaciones, Asistencia) is: a top filter card (periodo selector) full-width, then a two-column CSS grid below it — a narrower list/selector column on the left (`grid-cols-1 lg:grid-cols-[1fr_2fr]` for the record-heavy modules, `lg:grid-cols-2` for matrícula) and a wider detail/action column on the right. Forms inside dense contexts (table rows, filter bars) stay on one line with `flex items-end gap-2`. The navbar collapses to a hamburger below Tailwind's `md` breakpoint (768px), toggled by ~10 lines of vanilla JS in `app.js` — no framework, no build-time JS beyond the CSS compile step.

## Elevation & Depth

Fully flat. No `box-shadow` appears anywhere in the system, including the login card — depth is not part of this design's vocabulary at all right now.

### Named Rules
**The No-Lift Rule.** Nothing casts a shadow. Every surface — card, button, dropdown, alert — sits flush against the page. If a future visual pass introduces elevation, it replaces this rule deliberately; it is never added piecemeal to one screen.

## Shapes

Two radius steps throughout, defined as theme tokens: **6px** (`--radius-md`) on cards, buttons, and inputs; **4px** (`--radius-sm`) reserved for the smallest controls. Badges use the standard `md` radius — never a pill shape. No sharp (0px) corners, no exaggerated (>8px) rounding anywhere.

## Components

The system is built as a small `@layer components` vocabulary in `backend/app/static/src/input.css`, compiled by the standalone Tailwind CLI into `backend/app/static/app.css`. Templates use these named classes (`.card`, `.btn-save`, `.badge-danger`, …) instead of ad-hoc utility strings, so every button/badge/card in the app traces back to one definition.

### Buttons
- **Shape:** 6px radius, role-specific padding (see frontmatter `components`).
- **`.btn-login`** (Slate Authority): the one highest-weight action on a screen. Currently only the login "Ingresar" button qualifies.
- **`.btn-save`** (Ledger Green): every write/submit action — "Guardar notas", "Guardar asistencia", "Matricular", "Agregar" (evaluación).
- **`.btn-view`** (Registrar Blue outline, fills solid on hover): non-destructive navigation, chiefly the "Ver" buttons that open a sección's detail panel.
- **`.btn-destructive`** (Filed Red outline, fills solid on hover): "Retirar" and any future delete/undo action — always outline at rest, never filled, and always behind a `confirm()` prompt.
- **`.btn-outline-neutral`** (Quiet Gray outline): tertiary actions on a light background — "Volver al inicio", "Buscar".
- **`.btn-nav-action`** (white-on-transparent, for the dark navbar): "Salir" — the one action that lives inside the navbar itself, so it needs a variant legible against Slate Authority rather than against white.

### Badges
- **Style:** `.badge` base (6px radius, solid fill, Caption typography) plus one modifier: `.badge-success` / `.badge-warning` / `.badge-danger` / `.badge-secondary` / `.badge-info`.
- **Semantics:** success = at/above a good threshold (100% ponderación, 0 faltas); warning = approaching a limit; danger = over a limit or high-risk; secondary = zero/neutral; info = a plain count with no risk implication.

### Cards
- **Corner Style:** 6px (`.card`).
- **Background:** white on the Neutral Paper page background.
- **Shadow Strategy:** none — see Elevation & Depth.
- **Border:** `1px solid` Hairline Border — the system's one deliberate departure from a plain neutral gray.
- **Internal Padding:** `.card-body` (1rem); dense contexts drop to the compact `.table` instead of shrinking card padding. `.card-pending` is a one-off modifier (amber-tinted border) for the still-unimplemented module placeholders.

### Tables
- **Style:** `.table` inside `.table-wrap` (the overflow-x container) — compact padding, hover row highlight, tabular-figure numerals on every `<td>` so IDs and notas align vertically. This is the system's primary content surface — more screen real estate goes to tables than to any other component.
- **Empty state:** a centered, muted single row spanning all columns — never a separate empty-state illustration or panel.

### Forms / Inputs
- **Style:** `.input` / `.select` — Input Border at rest, Registrar Blue ring on focus.
- **Submission feedback:** every write posts back to a `GET` with `ok=` / `error=` query parameters, rendered as a dismissible `.alert-success` / `.alert-danger` banner at the top of the page (closed by the same ~10-line `app.js`) — never a toast, never inline-only validation for a server-side rejection.

### Navigation
- **Style:** `.navbar` (Slate Authority background), `.navbar-brand` / `.navbar-suffix` for the wordmark, `.nav-link` for each route, role-gated (coordinador-only items hidden from docentes). Collapses to a hamburger below `md` (768px); the toggle is plain `classList.toggle("hidden")`, no animation library.

## Do's and Don'ts

### Do:
- **Do** keep the interface completely flat — no `box-shadow` anywhere, including on cards that might feel like they deserve one.
- **Do** reserve color for status communication only (badges, alerts) — success/warning/danger/info/secondary, nothing decorative.
- **Do** use the `.table` / `.table-wrap` classes for every data table, including `tabular-nums` alignment — never a bare `<table>`.
- **Do** follow the established module layout (top filter card, then a narrower selector column beside a wider detail column) for any new record-management screen.
- **Do** surface every write operation's result as a dismissible `.alert-success` / `.alert-danger` banner driven by `ok`/`error` query parameters, matching the existing modules.
- **Do** add new colors, radii, or component classes to `input.css`'s `@theme` / `@layer components` blocks first, then reference the token by name in templates — never invent a one-off value inline.

### Don't:
- **Don't** introduce a custom font or webfont — the system uses the OS default stack everywhere, deliberately.
- **Don't** add `box-shadow`, gradients, or decorative imagery to "improve" a screen — the current plainness is an intentional placeholder awaiting a real visual-design pass, not an invitation to freelance polish on one screen at a time.
- **Don't** use `.btn-login` (Slate Authority) for anything but the single most important action on a page — Registrar Blue (`.btn-view`) stays for secondary "view" actions.
- **Don't** hardcode a hex color or arbitrary Tailwind value (`bg-[#...]`) in a template — use a `.btn-*` / `.badge-*` / `.card` component class or a theme color utility (`bg-slate-authority`, `text-filed-red`, …) so the whole system stays swappable from one file (`input.css`) later.
- **Don't** reintroduce Bootstrap, or any second CSS framework alongside Tailwind — the two fight over utility-class names and specificity; this system is Tailwind-only by design as of the September 2026 migration.
