# HENRI Dashboard — Design Revision

Fixes and improvements to the current dashboard implementation based on 
review. This prompt addresses layout, readability, and visual polish.

Reference the existing design system in `henri-design-system-prompt.md` 
for colors, typography, and interaction patterns. This prompt provides 
specific corrections to the current implementation.

---

## 1. Precursor alerts — compact into a single summary card

**Problem**: 6 full-width banners push the dashboard below the fold.

**Fix**: Replace the stacked banners with a single compact alert card.

When collapsed (default state):
```
┌──────────────────────────────────────────────────────────┐
│ ⚠ 6 active precursor warnings                    [▾]    │
│                                                          │
│ Tanzania 4x · Peru 3x · Jordan 3x · Yemen 3x ·          │
│ Israel 2x · Burkina Faso 2x                              │
│                                                          │
│ Delegations at risk:                                     │
│ [DAR] [LIM] [AMM] [ADE] [SAN] [SAR] [TEL] [OUG]       │
└──────────────────────────────────────────────────────────┘
```

- Full width, `--bg-surface` background with `border-left: 3px solid --orange`
- Country names in `--text-primary` (DM Sans), multiplier in `--text-muted`
- Delegation codes as small pills/badges: `--bg-elevated` background, 
  `--text-primary` text, DM Mono, rounded
- Click [▾] expands to show full detail for each country 
  (the current banner content, but stacked inside the card)
- When no alerts are active, this card disappears entirely — don't show 
  an empty "0 alerts" card

---

## 2. Replace mini-globe with flat dot-matrix map

**Problem**: 3D globe doesn't render well and feels gimmicky at small size.

**Fix**: Use the `dotted-map` npm package to generate a flat dot-matrix 
world map. This matches the Michele Du aesthetic perfectly.

Install: `npm install dotted-map`

Implementation:
```tsx
import DottedMap from 'dotted-map';

// Pre-compute map grid (do this once, cache the result)
const map = new DottedMap({ height: 60, grid: 'diagonal' });

// Add ICRC delegation pins, colored by risk tier
countries.forEach(country => {
  country.delegations.forEach(del => {
    map.addPin({
      lat: del.latitude,
      lng: del.longitude,
      svgOptions: { 
        color: riskTierColor(country.risk_score), 
        radius: 0.5 
      }
    });
  });
});

// Generate SVG
const svgMap = map.getSVG({
  radius: 0.22,
  color: '#3A3D44',      // --border color for background dots
  shape: 'circle',
  backgroundColor: 'transparent'  // let card bg show through
});
```

- Background dots in `--border` (#3A3D44) — subtle, implies geography
- ICRC delegation dots sized larger (radius 0.5) and colored by risk tier:
  high → `--red`, medium → `--orange`, low → `--yellow`, minimal → `--green`
- Active precursor countries: dots pulse gently (CSS animation on opacity)
- No timezone/meridian lines needed — the dot pattern implies the geography
- Hover on a delegation dot → tooltip with site code, country, risk score
- Click anywhere → navigate to `/globe` (when Phase 4 is built)

Verify `dotted-map` does NOT pull `axios` as a dependency before installing.

---

## 3. Risk table row colors — extend to full width

**Problem**: Row background colors appear cropped, not reaching table edges.

**Fix**: Ensure the risk tier background color extends to the full width 
of the table. The issue is likely padding or border-collapse:

```css
.risk-table {
  width: 100%;
  border-collapse: collapse;  /* not 'separate' */
}

.risk-table tr {
  /* Remove any cell padding that creates gaps */
}

.risk-table td:first-child {
  padding-left: 16px;  /* add padding to first cell, not the row */
}

.risk-table td:last-child {
  padding-right: 16px;
}
```

The `background-color` on the `<tr>` should paint the entire row seamlessly.
Also: remove any `border-radius` on table rows — it breaks the full-bleed 
background in most browsers.

---

## 4. Stat cards — larger with explanatory one-liners

**Problem**: Three bare numbers with no context. A first-time viewer 
doesn't know what "118", "55%", or "87.0h" mean.

**Fix**: Make each stat card larger and add a one-line explanation.

```
┌──────────────────────────────┐
│ SURGES WITH PRECURSORS       │  ← .label style (uppercase, muted)
│                              │
│ 118 / 216                    │  ← .data-display style (DM Mono, 39px)
│                              │
│ Of 216 outage clusters,      │  ← .body style (DM Sans 14px, text-muted)
│ 118 had warning signals      │
│ visible before the outage.   │
└──────────────────────────────┘

┌──────────────────────────────┐
│ DETECTION RATE               │
│                              │
│ 55%                          │
│                              │
│ More than half of all        │
│ network outages could have   │
│ been anticipated.            │
└──────────────────────────────┘

┌──────────────────────────────┐
│ AVG LEAD TIME                │
│                              │
│ 87.0h                        │
│                              │
│ Average warning time before  │
│ connectivity loss: ~3.5 days │
│ of advance notice.           │
└──────────────────────────────┘
```

- Each card spans 4 columns (not 2) in the grid for breathing room
- The explanation text is `--text-muted`, DM Sans 14px, max 2 lines
- Left border accent on the most critical stat: 
  `border-left: 3px solid --accent`

---

## 5. Surge pulse and source health rings — add context

**Problem**: Both visualisations are unreadable with zero context.

### Surge pulse fix:
- Add a `.label` title: "Surge activity — last 90 days"
- Add subtle x-axis month labels below: "Nov", "Dec", "Jan", "Feb", "Mar"
- Add a `.small` annotation on the rightmost spike: "latest"
- Add a legend: solid colored spike = "had precursors", 
  grey spike = "no precursors"
- Hover tooltip must work: date, region, delegations, score

### Source health rings fix:
- Add a `.label` title: "Source health"
- Add small labels next to each ring: "ACLED", "IODA", "CF", "SNOW", 
  "Grafana", "NetBox" — positioned radially or as a legend below
- Add last-pull timestamps in `.small` style: "2min ago", "15min ago"
- Keep the concentric ring design — it's beautiful — just make it 
  informative

---

## 6. Region volume dot histogram — add context

**Problem**: No axis labels, no legend, unreadable.

**Fix**:
- Add month labels on x-axis: "Nov", "Dec", "Jan", "Feb", "Mar"
- Add a color legend for regions (positioned top-right of the card):
  small colored dots + region names in `.small` style
- Add a `.label` title: "Incident volume by region"
- Ensure dots are large enough to distinguish colors — minimum 6px 
  diameter with 2px gap
- Each region's dots should stack from bottom to top in a consistent 
  order across all months (same order as legend)
- Hover on a region's column → dim other regions, show count tooltip

---

## 7. Navigation — collapse the sidebar

**Problem**: Persistent sidebar with 4 items wastes 170px of horizontal 
space.

**Fix**: Replace with a collapsed icon sidebar (50-60px wide):

```
┌────┐
│ ◆  │  ← HENRI logo mark (small)
├────┤
│ ▦  │  Dashboard (active: --accent left border)
│ ⚡ │  Surges
│ ◉  │  Delegations
│ ◨  │  Report
├────┤
│    │
│    │  (empty space)
│    │
├────┤
│ ●  │  Pipeline status dot (green/red)
└────┘
```

- Icons only, no text labels
- Hover on icon → tooltip with page name
- Active page indicated by `--accent` left border (3px)
- The HENRI wordmark moves to the top-left corner of the content area, 
  or disappears entirely (the logo mark in the sidebar is enough)
- This recovers ~110px of horizontal space for the bento grid

Use Lucide icons: `LayoutDashboard`, `Zap`, `Radio`, `FileText`

---

## 8. Masonry / bento fit

**Problem**: Cards don't feel like they fill the viewport properly.

**Fix**: The bento grid should fill the viewport height (100vh minus 
any top padding). Use:

```css
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-auto-rows: minmax(80px, auto);
  gap: 12px;
  padding: 16px;
  min-height: calc(100vh - 32px);
}
```

Each card declares its own `grid-column: span N` and `grid-row: span N`.
The row heights flex to fill available space. No card should have excessive 
empty internal space, and no card should overflow causing scrollbars within 
the dashboard viewport.

Updated grid spans:
- Alert card: `grid-column: span 12` (full width, only when alerts active)
- Dot-matrix map: `grid-column: span 5; grid-row: span 3`
- Threat landscape table: `grid-column: span 7; grid-row: span 3`
- Stat cards: `grid-column: span 4` each (3 cards = 12 cols)
- Surge pulse: `grid-column: span 5`
- Source health: `grid-column: span 2`
- Region volume: `grid-column: span 5`
- Top delegations: `grid-column: span 5`
- Pipeline status: `grid-column: span 2`

---

## 9. Top delegations — field only

**Problem**: GVA (headquarters) is #1 with 6,629 WindowsServerMemory 
alerts. This is noise in a field intelligence dashboard.

**Fix**: Filter the "Top delegations" list to field regions only 
(exclude HQ). Same filter as the threat landscape table.

---

## Summary of changes

1. ✅ Compact precursor alerts into collapsible summary card
2. ✅ Replace 3D globe with `dotted-map` flat dot-matrix map
3. ✅ Fix risk table row colors to extend full width
4. ✅ Enlarge stat cards with explanatory one-liners
5. ✅ Add titles, legends, and axis labels to surge pulse + source rings
6. ✅ Add context to region volume dot histogram
7. ✅ Collapse sidebar to icon-only (50-60px)
8. ✅ Make bento grid fill viewport (masonry fit)
9. ✅ Filter top delegations to field only (no HQ)
