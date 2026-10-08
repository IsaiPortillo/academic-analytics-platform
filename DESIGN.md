---
name: Sistema Minerva
description: Institutional BI/transactional platform for UES-FMO — a high-fidelity academic-analytics dashboard shell (sidebar + topbar), cold corporate surfaces, deep crimson brand, real shadow-based elevation, single-face type system.
colors:
  brand: "#8b0105"
  brand-hover: "#6b0000"
  brand-active: "#560000"
  bg: "#f7f9fb"
  surface: "#ffffff"
  surface-sunken: "#eef2f6"
  border: "#e2e8f0"
  text: "#0f172a"
  muted: "#64748b"
  warning-text: "#b45309"
  success-text: "#047857"
  danger-text: "#dc2626"
  neutral-text: "#475569"
typography:
  title:
    fontFamily: "'Plus Jakarta Sans', Inter, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  subtitle:
    fontFamily: "'Plus Jakarta Sans', Inter, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: normal
  body:
    fontFamily: "'Plus Jakarta Sans', Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: normal
  label:
    fontFamily: "'Plus Jakarta Sans', Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: normal
  caption:
    fontFamily: "'Plus Jakarta Sans', Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.02em"
  telemetry:
    fontFamily: "'JetBrains Mono', ui-monospace, 'SF Mono', Consolas, monospace"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.6
    letterSpacing: "0.01em"
rounded:
  sm: "8px"
  md: "12px"
  lg: "16px"
components:
  button-login:
    backgroundColor: "{colors.brand}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  button-save:
    backgroundColor: "{colors.brand}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "7px 14px"
  button-view:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.brand}"
    rounded: "{rounded.sm}"
    padding: "5px 10px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "18px"
  kpi-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "16px 18px"
---

# Design System: Sistema Minerva

## Overview

**Creative North Star: "The Institutional BI Console"**

Sistema Minerva is the analytics-and-registrar console for UES-FMO — where a coordinador reads institutional risk signals (retention, curricular bottlenecks, dropout alerts) and a docente processes grades and attendance. It reads like an enterprise Business Intelligence product (Tableau/Looker register), not a warm administrative tool: cold neutral surfaces, crisp 1px borders, real elevation via shadow, and exactly one saturated color — a deep academic crimson — carrying identity through the shell, not through decoration.

This is a full rebrand (October 2026), approved by the user as a replacement of the prior "Arterial Nocturne" identity, not a refinement of it. The prior system's gradients, warm cream/blush palette, and dual-font pairing are retired; nothing from that world carries forward except the underlying CSS-custom-property architecture and the already-built dense-data components (dock, matrix, tap-toggle, KPI cards, skeleton), which are re-skinned onto the new tokens rather than rebuilt.

**Key Characteristics:**
- Persistent left sidebar + slim top bar (replaces the prior horizontal navbar) — the app shell of a multi-module institutional console, not a single-page marketing site.
- One brand crimson (`#8b0105`) anchors identity (sidebar active state, primary buttons, brand mark); a visually distinct bright crimson (`#dc2626`) is reserved exclusively for critical/danger signals, so "this is the brand" and "this is an alarm" never share a hue reading.
- Real elevation: cards cast an actual soft shadow (`--shadow-card`) — the prior system's flatness rule is retired by the same rebrand authority that retired its gradients.
- A single type family (Plus Jakarta Sans, Inter fallback) carries the whole hierarchy through weight (800/700/600/500/400), not through a second face.
- A monospace face (JetBrains Mono) is reserved for technical telemetry only — badges naming the active database role, SQL/Cypher illustrative banners — never for body copy.
- Status is communicated through soft-tint badges (background + border + text + icon) — unchanged discipline from the prior system, just re-tinted.
- Two screens (Dashboard & Grafo, Alertas & OLAP) are explicitly labeled illustrative previews — see Honesty Boundary below — because their backing engines (Neo4j graph analytics, the OLAP/BI layer) are Phases 3–4 of the project roadmap and do not exist yet.

## Honesty Boundary (read before touching Dashboard/OLAP)

Two sidebar items — **Dashboard & Grafo** (`/dashboard`) and **Alertas & OLAP Tesis** (`/analitica-olap`) — visualize capabilities this system does not yet have: a live Neo4j curriculum graph with centrality/shortest-path analytics, and an OLAP cube over a star schema. Per PRODUCT.md, both are unbuilt roadmap phases.

**Named Rule: The Preview Boundary.** Every screen backed by a not-yet-built engine opens with `.preview-banner` stating plainly that its numbers are illustrative, not a query result. Nothing on those two pages may claim to be live: no fabricated "Query Time" on a real console (the modal's telemetry is sample text, explicitly commented as such in the template), no invented legal citations, no named fictional personas. The one exception the user explicitly asked to keep real: the two CSV export links on `/analitica-olap` point at the actual `/reportes/*/csv` endpoints — real data, real download — because building that page is not an excuse to downgrade an existing real feature to a mockup.

The login page's quick-demo buttons use the real seeded `coordinador` / `docente` accounts already in the database — never invented jurado personas with fabricated credentials, per explicit user decision during this rebrand.

### Real analytics screens are outside the Preview Boundary

**Vista ejecutiva** (`/vista-ejecutiva`, Fase 4.1) shows real query results from the data warehouse, so it does **not** carry `.preview-banner`. Its only caveat banner (`.alert-warning`) comes from the data itself — `dim_periodo.fuente_costo` — and disappears on its own once the official cost per UV is registered. Components added for it, all on existing tokens (dark mode included): `.kpi-interpretacion` (the text reading under each KPI number — indicator and interpretation are one piece), `.kpi-trend-neutral`, `.bar-list` / `.bar-row` / `.bar-track` / `.bar-fill` / `.bar-value` (horizontal magnitude bars: one series, brand color, zero baseline, value labelled at the end) and `.column-chart` / `.column` / `.column-bar` / `.column-labels` (per-period columns; selected periods at full opacity, the rest dimmed — distinguished without a second hue). On these four KPIs a rise is a deterioration, so `.kpi-trend-down` (red) marks an increase and the arrow always shows the real direction.

**Análisis diagnóstico** (`/analisis-diagnostico`, Fase 4.2) is also real data and reuses the same pieces, plus a correlation heatmap: `.corr-table` / `.corr-cell` (intensity follows |r| over a neutral surface; `r` is always printed in the cell, so color never carries the value alone), `.is-negative`, `.is-construccion` (diagonal texture + `*` for pairs related by definition, e.g. cost vs grade), and `.corr-legend`. It introduces the diverging pair tokens `--color-div-pos` (blue) / `--color-div-neg` (red), with a neutral midpoint and separate dark-mode steps. Text in cells keeps the theme's text color: white on the mixed cell color failed contrast (~2.6:1). Copy rule specific to this screen: it describes patterns **observed** in history and never predicts (“ya presentan el patrón”, never “en riesgo de desertar”).

## Colors

### Primary
- **Brand Crimson** (`#8b0105`): sidebar active-link fill, `.btn-login`/`.btn-save`, the brand mark, focus rings, text selection. Does not change between light and dark mode (dark mode brightens it slightly for contrast against a near-black surface — see Dark Mode — but it stays recognizably "the one red").

### Neutral (theme-adaptive — light values shown; dark values in Dark Mode below)
- **Background** (`#f7f9fb`) — page/app background, cold slate-50.
- **Surface** (`#ffffff`) — card, sidebar, topbar background.
- **Surface Sunken** (`#eef2f6`) — hover states, the sidebar's active-icon rest, telemetry-badge fill.
- **Border** (`#e2e8f0`) — the system's only structural line color, 1px everywhere.
- **Text** (`#0f172a`) — near-black slate, not pure black.
- **Muted** (`#64748b`) — secondary text, labels, telemetry badge text.

### Status (soft-tint: background + border + text, always paired with an icon — never color alone)
- **Success** (emerald) — bg `#e7f7f0` / border `#a7e8cb` / text `#047857`. Approved, verified, at/above target.
- **Warning** (amber) — bg `#fef3e2` / border `#fbd9a5` / text `#b45309`. Approaching a limit, intermediate metric.
- **Danger** (bright crimson) — bg `#fdecec` / border `#f7b9b9` / text `#dc2626`. Over a limit, high-risk, critical bottleneck. Deliberately a different hue value from `--color-brand` — see Named Rule below.
- **Neutral** (slate) — bg `#eef2f7` / border `#dce3ec` / text `#475569`. Zero-state or a plain count with no risk implication.

### Named Rules
**The Status-Only Color Rule.** Success/warning/danger/neutral exist to answer "is this okay?" on a badge or alert, and for nothing else.
**The Two-Reds Rule.** `--color-brand` (`#8b0105`, dark academic crimson) is identity; `--color-danger-text` (`#dc2626`, bright crimson) is alarm. They read as clearly different weights of red precisely so a coordinador never mistakes "this is the primary action" for "this is a critical alert" — a risk the brief's own reference palette anticipated by specifying two distinct crimsons.
**The Real Elevation Rule.** Cards, KPI cards, and the mobile sidebar cast a real `box-shadow` (`--shadow-card` / `--shadow-raised`). This replaces the prior system's flatness rule entirely — a deliberate, brief-directed reversal, not drift.

## Typography

**Single face:** Plus Jakarta Sans (weights 400–800), Inter as system fallback. One family carries the whole hierarchy through weight and size, not through a second face — titles at 800, subtitles/card headers at 600–700, body/labels at 400–500.
**Telemetry face:** JetBrains Mono, reserved for `.telemetry-badge` and `.sql-banner` — technical facts about the running system (active role, engine versions), never body copy, never decorative.
Both load from Google Fonts (`base.html`, `display=swap`) and fully cover Spanish diacritics (á é í ó ú ñ ü).

### Hierarchy
- **Title** (weight 800, 1.5rem, -0.01em tracking): page headers (`.page-title`).
- **Subtitle** (weight 700, 1.25rem): card/section headers, `.page-subtitle`.
- **Body** (weight 400, 1rem): paragraph copy.
- **Label** (weight 500, 0.875rem): field labels, table headers, button text.
- **Caption** (weight 700, 0.75rem, 0.02em tracking, uppercase): badge text, sidebar section labels.
- **Telemetry** (JetBrains Mono, 0.6875rem): `.telemetry-badge`, `.sql-banner`.
- **Dense-data tier** (unchanged from the prior system's October 2026 addition, now on the new face): 0.6875rem (matrix inline errors), 0.8125rem (matrix cells, KPI labels, dense table headers), 0.9375rem (dock CTA, tally numbers), 1.75rem/weight 800 (KPI headline figures).

### Named Rules
**The One-Face Rule** (replaces the prior Two-Face Rule): exactly one display/body family, differentiated by weight and size, not by swapping fonts. JetBrains Mono is the sole, sanctioned exception, reserved for telemetry.

## Layout

App shell: a persistent left sidebar (`.sidebar`, fixed 15.5rem, two link groups — "Inteligencia institucional" for the preview pages, "Módulos operativos" for the four real transactional modules) plus a slim sticky top bar (`.topbar`) carrying the live `SET LOCAL ROLE` badge, theme toggle, user identity, and logout. Below 1024px the sidebar becomes an off-canvas drawer (`.sidebar.is-open`, slide-in + backdrop) triggered by a hamburger button in the top bar. The drawer carries the user's name and role (`.sidebar-user`), since the top bar no longer has room for them; the role-telemetry badge in the top bar appears from 640px up. See Responsive behavior below.

### Responsive behavior (phones and tablets)

Mobile-web is a first-class target (staff use phones and tablets in the classroom and in the office). The rules, all in `input.css`:

- **Breakpoints:** 640px (phone → tablet) and 1024px (drawer → persistent sidebar). Landscape tablets (1024px) keep the sidebar, so the content column is narrow; that is why tables key off their *card*, not the screen.
- **Tables decide by their card's width** (`.card` is a `container-type: inline-size`). A `.table-stack` table inside a card narrower than 36rem turns each row into a mini-card: title cell (`.cell-title`), labelled cells (`data-label`, shown via `::before`), and a full-width action row (`.cell-actions`). The header is visually hidden, not removed. Use it for tables whose *actions* must stay in reach (matrícula, secciones, asistencia, roster). Wide *data* tables (reportes, cohortes) do not stack: they scroll horizontally (`.table-wrap` shows edge shadows when content is hidden) and pin their first column (`.table-sticky-first`).
- **Filters:** `.filter-bar` (controls full-width on phones, inline from 640px) replaces ad-hoc `flex items-end` rows.
- **Touch (`@media (pointer: coarse)`):** 44px minimum targets for buttons, links, inputs, toggles and the drawer; form fields at 16px so iOS does not zoom on focus. Decided by input type, not width.
- **Drawer:** closes on backdrop, link tap, Escape, or widening past 1024px; locks page scroll while open (`html.nav-open`); keeps closed links out of the tab order (`visibility: hidden`); focus returns to the toggle.
- **Master-detail (asistencia, calificaciones):** below 1024px, opening a section hides the section list (`.master-detail.has-detail > .master-list`) and the period filter, leaving only the detail with a "← Cambiar de sección" link; at 1024px+ both columns stay side by side. In asistencia the tally header (`.sticky-header`) and the save bar (`.sticky-actions`) stay pinned while a long roster scrolls; `app.js` sets `--topbar-h` to the real top bar height so the header sits right under it.
- **Matrícula dock:** on < 1024px a floating `.dock-fab` shows how many sections the dock holds and jumps to it when it is out of view.
- **Charts:** the period column chart (`.chart-scroll`) scrolls inside its card and centers the selected period; columns are focusable so a tap reveals the value (no hover on touch).
- **Safe areas:** `viewport-fit=cover` plus `env(safe-area-inset-*)` on the top bar, content padding and the dock shortcut.

### Named Rules
**The Container Rule.** Responsive components key off their container, not the viewport, whenever the same component can sit in a wide or a narrow column.
**The Fixed-Ancestor Rule.** `main`'s entrance animation uses `fill-mode: backwards`, never `both`/`forwards`: a retained `transform` makes `<main>` the containing block of every `position: fixed` descendant (dock shortcut, graph modal), which then stops anchoring to the screen. Grid children also get `min-width: 0` so a wide table scrolls inside its card instead of widening the page.

## Elevation & Depth

Real shadow-based elevation (see The Real Elevation Rule above): `--shadow-card` for resting cards/KPI cards, `--shadow-raised` for hover states on primary buttons and the open mobile sidebar. No lift-on-hover transform system (the prior gradient-button hover-lift is retired along with the gradients) — hover communicates through shadow deepening and background-color shift instead.

### Motion

- **Page entrance** (`fade-rise`, 0.35s, ease-out-expo): the `<main>` content area fades and rises 8px on every page load.
- **Sidebar slide-in** (mobile only): `transform: translateX()`, 0.2s, plus a fading backdrop.
- **Theme toggle**: sun/moon icons cross-fade and rotate instead of hard-swapping.
- **Alert dismiss**: fades and scales down slightly before removal from the DOM.
- **Skeleton shimmer**: a looping gradient sweep on filter-triggered loading rows.
- All motion respects `prefers-reduced-motion: reduce`.

### Named Rules
**The One Moment Rule.** A page gets exactly one entrance animation (`main`'s fade-rise). Motion elsewhere is reserved for genuine state changes (hover, toggle, dismiss, sidebar open/close), never decorative.

## Shapes

`--radius-sm` (8px) for buttons, inputs, small controls; `--radius-md` (12px) for telemetry badges and mid-size elements; `--radius-lg` (16px) for cards and the modal panel. No pill shapes (progress-bar tracks/fills use `--radius-sm`, not 999px), no sharp corners.

## Dark Mode

Follows `prefers-color-scheme` until the user toggles it (sun/moon icon in the top bar); the choice persists to `localStorage` and an inline `<head>` script applies it before first paint. The brief itself specifies only a light institutional-BI surface — dark mode is a translation of the same token roles onto a near-black slate canvas (`#0b1220` background, `#141b2d` cards), not a separately designed world, kept because it was already a working accessibility preference rather than removed unasked.

**What changes between themes:** background, surface, border, text, muted, all four status-token triplets, shadow opacity/depth. `--color-brand` brightens slightly (`#8b0105` → `#c73838`) for legibility against the dark surface, same rationale as the prior system's gradient-end brightening.

### Named Rules
**The Fixed Anchor Rule.** Any new color token must define both a light and a dark value, kept in sync between the two CSS blocks in `input.css`.

## Components

Built as a `@layer components` vocabulary in `backend/app/static/src/input.css`, compiled by the standalone Tailwind CLI into `backend/app/static/app.css`.

### Shell
- **`.sidebar`** / **`.sidebar-link`** (`.is-active` fills brand crimson) / **`.sidebar-footer`** (engine-status telemetry chips).
- **`.topbar`** / **`.telemetry-badge`** (mono, dot indicator, states a real architectural fact — the active `SET LOCAL ROLE`, never a live query timer).

### Buttons
- **`.btn-login`** / **`.btn-save`**: solid brand crimson, shadow-card, the two highest-emphasis write actions.
- **`.btn-view`**: white surface, brand-crimson text and border on hover — secondary navigation.
- **`.btn-destructive`**: danger-bordered outline, fills bright crimson on hover — always behind `confirm()`.
- **`.btn-outline-neutral`** / **`.btn-nav-action`**: tertiary actions.

### Badges (`_macros.html`'s `badge(estado, texto)`)
Unchanged discipline: icon + text pair, flat soft-tint fill, never color alone.

### Data-dense components (dock, matrix, tap-toggle, KPI, skeleton)
Structurally unchanged from the prior system's October 2026 addition — see their own inline comments in `input.css` for the why. Only their token values changed (crimson instead of the old brand red, 8/12/16px radius instead of 4/6px, real shadows on `.kpi-card`). **The Advisory-Not-Validation Rule** still applies: the matrícula dock's same-turno note is a suggestion to verify, never a pass/fail claim, because the schema has no real schedule/prerequisite data.

### Graph & Modal (new)
- **`.graph-node`** / **`.graph-edge`**: SVG-drawn curricular graph nodes/edges — `.is-blocked` (danger tint), `.is-approved` (success tint), `.is-bottleneck` (thicker danger stroke). Never approximated with `clip-path` or a raster image — the mesh is real SVG geometry.
- **`.modal-backdrop`** / **`.modal-panel`**: centered overlay with backdrop blur, used for the student graph-detail view. Its Cypher/telemetry content is illustrative (see Honesty Boundary) and says so via inline comment in `dashboard.html`.
- **`.preview-banner`**: the required marker for any screen backed by an unbuilt engine — see Honesty Boundary.

## Do's and Don'ts

### Do:
- **Do** call `{{ badge(estado, texto) }}` from `_macros.html` for every status indicator.
- **Do** give any new color token both a light and a dark value.
- **Do** keep `--color-brand` and `--color-danger-text` visually distinct reds — never let a primary action and a critical alert share the same hue weight.
- **Do** cast a real `box-shadow` on cards — this system's elevation is real, not implied by gradient.
- **Do** use Plus Jakarta Sans/Inter for everything except telemetry (JetBrains Mono).
- **Do** open any screen backed by an unbuilt engine (Neo4j GDS, OLAP cube) with `.preview-banner`, and comment illustrative data as such in the template.
- **Do** phrase any unverified advisory (schedule/prerequisite hints) as a suggestion, never a pass/fail claim.
- **Do** animate a progress fill with `transform: scaleX()`, never `width`.

### Don't:
- **Don't** introduce a second body/display font family; JetBrains Mono is the one sanctioned exception, for telemetry only.
- **Don't** use `.btn-login` for anything but the single most important action on a page.
- **Don't** hardcode a hex color in a template — reference a theme token or a component class.
- **Don't** use `border-radius: 999px` (pill shapes) anywhere.
- **Don't** fabricate a named fictional persona, a specific legal/regulatory citation, or a live query measurement (e.g. "Query Time: 2.14ms") without disclosing it as illustrative — see Honesty Boundary.
- **Don't** let a mockup page (Dashboard, OLAP) go without its `.preview-banner`, or let a real feature (the CSV exports) get demoted to decorative inside a mockup page.
- **Don't** reintroduce Bootstrap or a second CSS framework alongside Tailwind.
