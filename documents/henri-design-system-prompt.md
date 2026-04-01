# HENRI Design System — Dashboard & Visual Language

## Design philosophy

HENRI is a humanitarian network intelligence tool. Its interface should feel like a **command center** — data-dense but breathing, operational but beautiful, serious but not sterile. The aesthetic references are Shift5's military-grade monitoring UI, Zajno's asymmetric analytics dashboard, and Michele Du's dot-matrix data artistry.

This is an internal tool for network infrastructure experts. It should look like something that belongs on Dribbble or Cosmos.so — the kind of interface that makes the Head of Field IT say "I want this on my screen every morning."

**The visual treatment described here applies to the Dashboard page only.** All other pages (Country, Surges, Delegations, Report) use the same color palette and typography but with clean, functional layouts — standard tables, standard Recharts charts, no bespoke visualisations.

Design references are saved in `documents/design-inspiration/`.

---

## Color palette

Derived from ICRC brand book colors (Graphite, Snow, Brick, Pomegranate) adapted for a dark operational interface.

### Surfaces

```css
--bg-deepest:    #1A1C20;   /* sidebar, dropdowns — from ICRC Graphite */
--bg-base:       #22242A;   /* page background */
--bg-surface:    #2A2C32;   /* cards, panels, table headers */
--bg-elevated:   #32353B;   /* hover states, active rows */
--bg-highlight:  #3A3D44;   /* selected items, focus rings */
--bg-button:     #2E3036;   /* button backgrounds */
--border:        #3A3D44;   /* all visible borders */
```

### Text

```css
--text-primary:  #F5F7F7;   /* headings, data values — ICRC Snow */
--text-body:     #DEDEDE;   /* body text, labels — from ICRC Pebble */
--text-muted:    #8A8D94;   /* timestamps, secondary info */
--text-disabled: #5C5F66;   /* inactive elements */
--text-comment:  #9A9DA6;   /* chart axis labels, annotations */
```

### Accent & interactive

```css
--accent:        #D83C3B;   /* ICRC Brick — active indicators, selected tabs */
--accent-deep:   #921F1C;   /* ICRC Pomegranate — text selection, deep emphasis */
--link:          #E5A89A;   /* clickable text — blush-tinted from Brick */
```

### OSINT source colors

```css
--source-acled:      #C792EA;   /* purple — conflict data */
--source-ioda:       #82AAFF;   /* blue — outage detection */
--source-cloudflare: #89DDFF;   /* cyan — radar/BGP */
```

### Status & risk

```css
--green:   #A8C97A;   /* healthy, minimal risk, lead time >48h */
--yellow:  #E5C46B;   /* warning, low risk, lead time 12-48h */
--orange:  #D88A6C;   /* escalation, medium risk, lead time <12h */
--red:     #D83C3B;   /* critical, high risk — same as accent (Brick) */
--error:   #D83C3B;   /* pipeline failures — same as accent */
```

### Risk table row backgrounds (semi-transparent on dark)

```css
--risk-high:    #D83C3B30;   /* red at 19% opacity */
--risk-medium:  #D88A6C28;   /* orange at 16% opacity */
--risk-low:     #E5C46B1C;   /* yellow at 11% opacity */
--risk-minimal: #A8C97A14;   /* green at 8% opacity */
```

### Selection

```css
--selection-bg: #921F1C80;   /* Pomegranate at 50% */
--selection-fg: #FFFFFF;
```

---

## Typography

Based on ICRC brand book: DM Sans (primary), Noto Sans (secondary/long text), DM Mono (data — same design family as DM Sans).

### Font loading

```css
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,400&family=DM+Mono:wght@300;400;500&family=Noto+Sans:wght@400;500&display=swap');
```

For on-prem deployment without external CDN: self-host the font files in `frontend/public/fonts/` and use `@font-face` declarations instead.

### Type scale (1.25 major third, per brand book)

```
10px — SMALL: axis labels, footnotes (Noto Sans)
13px — DATA: site codes, scores, timestamps (DM Mono)
16px — BODY: body text, table cells, descriptions (DM Sans)
20px — HEADING: panel titles, section headers (DM Sans)
25px — SUBHEAD: page titles (DM Sans)
31px — not commonly used
39px — DATA-DISPLAY: prominent data values (DM Mono)
49px — DISPLAY: hero numbers on dashboard (DM Sans)
61px — DISPLAY-LARGE: single hero stat if needed (DM Sans)
```

### Type styles

```css
/* Hero numbers — the "117" in "117 surges" */
.display {
  font-family: 'DM Sans', sans-serif;
  font-size: 49px;
  font-weight: 400;          /* brand book: prefer regular over bold */
  color: var(--text-primary);
  line-height: 1.1;
}

/* Prominent data values needing tabular alignment */
.data-display {
  font-family: 'DM Mono', monospace;
  font-size: 39px;
  font-weight: 400;
  color: var(--text-primary);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

/* Panel titles — sentence case, not bold */
.heading {
  font-family: 'DM Sans', sans-serif;
  font-size: 20px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.3;
  /* Sentence case: "Threat landscape", NOT "THREAT LANDSCAPE" */
}

/* Category labels — the one exception to the no-caps rule */
/* These are interface chrome, not communication text */
.label {
  font-family: 'DM Sans', sans-serif;
  font-size: 10px;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  line-height: 1.4;
}

/* Body text */
.body {
  font-family: 'DM Sans', sans-serif;
  font-size: 16px;
  font-weight: 400;
  color: var(--text-body);
  line-height: 1.5;
}

/* Data values — monospaced for alignment */
.data {
  font-family: 'DM Mono', monospace;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

/* Axis labels, footnotes, fine print */
.small {
  font-family: 'Noto Sans', sans-serif;
  font-size: 10px;
  font-weight: 400;
  color: var(--text-comment);
}
```

---

## Dashboard layout — bento grid

The dashboard (`/`) uses an asymmetric bento grid. Not a uniform card grid — panel sizes vary by importance. The most critical information gets the most real estate.

```
┌──────────────────────────────────────────────────────────────────┐
│  ⚠ Alert banner (full width)                                    │
│  Precursor warnings + delta escalations. Dismissible.            │
├─────────────────────────┬────────────────────────────────────────┤
│                         │                                        │
│   MINI-GLOBE            │   THREAT LANDSCAPE                     │
│   (live 3D widget)      │   (risk table, scrollable)             │
│                         │                                        │
│   Three.js scene:       │   51 countries, color-coded rows       │
│   dot-matrix earth,     │   dot-stream sparklines per row        │
│   delegation points     │   sortable columns                     │
│   glowing by risk       │   click → /country/:iso2               │
│   tier, slow rotation   │                                        │
│                         │                                        │
│   span: 5 cols          │   span: 7 cols                         │
│   height: ~400px        │   height: ~400px                       │
├───────┬───────┬─────────┼──────────────┬─────────────────────────┤
│       │       │         │              │                         │
│ STAT  │ STAT  │ STAT    │ SURGE PULSE  │ SOURCE HEALTH           │
│       │       │         │              │                         │
│ 117   │ 54.2% │ 92.0h   │ EKG-style    │ Concentric rings        │
│       │       │         │ timeline     │ per source              │
│       │       │         │              │                         │
│ 2 col │ 2 col │ 2 col   │ 4 col        │ 2 col                   │
├───────┴───────┴─────────┼──────────────┼─────────────────────────┤
│                         │              │                         │
│ REGION VOLUME           │ TOP          │ PIPELINE                │
│ (dot histogram)         │ DELEGATIONS  │ STATUS                  │
│                         │ (ranked)     │ (last run, next run)    │
│ 6 col                   │ 4 col        │ 2 col                   │
└─────────────────────────┴──────────────┴─────────────────────────┘
```

Use CSS Grid with `grid-template-columns: repeat(12, 1fr)` and `gap: 12px`. Cards span different column counts as annotated above.

---

## Bespoke visualisations (dashboard only)

### 1. Mini-globe (hero, top-left)

A live Three.js scene embedded in a React component. NOT the full `/globe` page — a simplified preview.

- Sphere rendered with a dot-matrix texture: small dots at country centroids, sized by number of ICRC delegations in that country
- Dots colored by risk tier: `--red` for high, `--orange` for medium, `--yellow` for low, `--green` for minimal, `--text-disabled` for no data
- Active precursor alerts: affected country dots pulse gently (opacity oscillation, not size — subtle, not distracting)
- Slow auto-rotation (~1 revolution per 60 seconds). Pauses on hover.
- Background: transparent (shows card `--bg-surface` behind)
- No land mass geometry — just the dots floating in space, implying the globe. Less is more.
- Camera: slight perspective tilt, looking slightly down at the earth (the "overview effect" angle)
- Click anywhere on the mini-globe → navigates to `/globe` for the full experience

### 2. Surge pulse (mid-row)

A horizontal heartbeat/seismograph timeline showing surge events over the last 90 days.

- X axis: time (left = 90 days ago, right = now)
- Each surge event is a vertical spike: height = surge score (normalized 0-100)
- Spike color: `--source-cloudflare` (#89DDFF) if the surge had external precursors, `--text-disabled` if no precursors detected
- Draw as a continuous line connecting spike peaks, with the baseline at 0 — looks like an EKG trace
- Thin vertical hairline at "now" on the right edge
- Hover on a spike → tooltip with: date, region, delegations affected, precursor summary
- Implementation: Canvas or SVG, not Recharts — this needs to feel hand-crafted, not chart-library-generic

### 3. Dot histogram (bottom-left: region volume)

Like the Zajno dot-array visualization. Shows incident volume by region over the last 5 months.

- X axis: months. Y axis: stacked by region.
- Each dot represents N incidents (e.g. 1 dot = 50 incidents)
- Dots stacked vertically per region-month, colored by region:
  - AFRICA East: `--red` (#D83C3B)
  - AFRICA West: `--source-ioda` (#82AAFF)
  - AMERICAS: `--green` (#A8C97A)
  - ASIA: `--orange` (#D88A6C)
  - EURASIA: `--source-acled` (#C792EA)
  - NAME: `--source-cloudflare` (#89DDFF)
- Dots are small circles (4-5px radius), tightly packed with 1-2px gap
- The visual accumulation pattern immediately shows which regions generate the most volume
- Hover on a region's dot cluster → highlight that region, dim others, show count

### 4. Dot-stream sparklines (in risk table rows)

Each country row in the threat landscape table has a 30-day sparkline.

- 30 dots, one per day, arranged horizontally
- Y position = risk score for that day (normalized within the row's range)
- Dot color: interpolated from `--green` to `--red` based on the score value
- Dot size: 3px normally, 4px for the latest (rightmost) dot
- No connecting line — just the dots floating in a stream pattern
- If trending up over the last 7 days: rightmost dots tint toward `--red`
- If trending down: rightmost dots tint toward `--green`
- Implementation: inline SVG, generated per row

### 5. Source health rings (mid-right)

Concentric rings showing OSINT source freshness, inspired by the Shift5 orbital diagram.

- 6 concentric rings, one per data source (outermost to innermost): 
  ACLED, IODA, Cloudflare, ServiceNow, Grafana, NetBox
- Each ring is a circular arc: completeness = data freshness
  - Full ring (360°): pulled within the last scheduled interval
  - Partial ring: stale (last pull > 1 interval ago)
  - Broken/dotted ring: failed
- Ring color: the source's designated color (purple, blue, cyan for OSINT; `--text-muted` for internal sources)
- Ring stroke: 2-3px, with rounded caps
- Center: small dot or the HENRI logo mark
- Hover on a ring → tooltip with source name, last pull time, record count
- Total size: small (~120x120px). This is a status indicator, not a hero visualization.

### 6. Stat cards

Three stat cards in a row, Shift5 style:

- Large number in `.data-display` style (DM Mono, 39px)
- Small `.label` above (uppercase, letter-spaced): "Surges with precursors", "Detection rate", "Avg lead time"
- Optional supporting detail below in `.small` style
- Card background: `--bg-surface`. Subtle left border accent in `--accent` (2px) for the most critical stat.

---

## Card component specification

```css
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  transition: background 150ms ease;
}

.card:hover {
  background: var(--bg-elevated);
}

/* For the mini-globe card, remove padding to let the 3D scene fill edge-to-edge */
.card--hero {
  padding: 0;
  overflow: hidden;
}
```

---

## Alert banner specification

Full-width, pinned to top of dashboard content area (below nav). Dismissible per session (dismissed state in React state, not persisted).

```css
/* Precursor warning */
.alert--precursor {
  background: #D88A6C18;              /* orange at 9% */
  border-left: 3px solid var(--orange);
  padding: 14px 20px;
  border-radius: 6px;
  margin-bottom: 8px;
}

/* Escalation */
.alert--escalation {
  background: #D83C3B18;              /* red at 9% */
  border-left: 3px solid var(--red);
}

/* De-escalation */
.alert--deescalation {
  background: #A8C97A18;              /* green at 9% */
  border-left: 3px solid var(--green);
}

.alert__title {
  /* .label style: DM Sans 10px uppercase letter-spaced */
  color: var(--orange);  /* or --red / --green per type */
  margin-bottom: 4px;
}

.alert__message {
  /* .body style: DM Sans 14px */
  color: var(--text-body);
}

.alert__delegations {
  /* .data style: DM Mono 13px */
  color: var(--text-primary);
}
```

---

## Interaction patterns

**Risk table row hover**: background transitions to `--bg-elevated`, sparkline dots scale up 1.3x, country name color shifts to `--link`. Transition: 150ms ease.

**Mini-globe hover**: rotation pauses. Hovered country dot enlarges 2x. Tooltip appears with country name, risk score, and active alert count.

**Surge pulse hover**: spike under cursor highlights with a vertical line, tooltip appears with surge details. Other spikes dim to 30% opacity.

**Dot histogram hover**: hovered region's dots brighten to full opacity, other regions dim to 30%. Region name and count appear as tooltip.

**Page transitions**: instant React Router navigation. Content area fades in (opacity 0→1, 150ms). Data loads with skeleton placeholders matching card dimensions and the bento grid layout — never a centered spinner.

**Skeleton placeholders**: rectangles in `--bg-elevated` with a subtle shimmer animation (a highlight band sweeping left to right). Shaped to match the content they replace: table skeletons look like table rows, chart skeletons look like chart areas.

---

## Other pages (clean/functional)

Country, Surges, Delegations, and Report pages use the same palette, typography, and card component but with standard layouts:

- Single-column or two-column layout, not bento grid
- Standard Recharts charts (bar, line, area) styled with the palette colors
- Standard tables with the risk row background colors
- No bespoke visualisations — data presented clearly and efficiently
- Same card component, same hover states, same transition timing

The dashboard is the showpiece. The other pages are where you get work done.

---

## Accessibility notes

Per ICRC brand book: all typography must meet WCAG AA contrast minimum.

- `--text-primary` (#F5F7F7) on `--bg-base` (#22242A): contrast ratio ~13:1 ✅ AAA
- `--text-body` (#DEDEDE) on `--bg-base` (#22242A): contrast ratio ~10:1 ✅ AAA
- `--text-muted` (#8A8D94) on `--bg-base` (#22242A): contrast ratio ~4.5:1 ✅ AA
- `--link` (#E5A89A) on `--bg-base` (#22242A): contrast ratio ~6:1 ✅ AA — verify; if it fails, brighten to #EBB5A8
- `--accent` (#D83C3B) on `--bg-surface` (#2A2C32): contrast ratio ~4.5:1 ✅ AA for large text

All interactive elements must have visible focus indicators using `--bg-highlight` as a focus ring.
