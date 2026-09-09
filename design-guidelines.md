# Design guidelines — Zo-Pro Copilot

## 1. Concept

Zo-Pro Copilot is a conversational product over two flows every business runs: sales (money and goods in) and purchasing (money and goods out). Data behaves like a current, not a static grid. Insight cards arrive when something real is found; nothing appears without a reason.

HTML mockups in `mock ui/` are **palette, type, and card anatomy** references. They use a popup/drawer for tables. **That interaction is not the MVP.** The MVP chat lives in a dynamic column: it shrinks, and a fragment of the clicked article extracts and becomes the data view.

Three commitments:

1. **Nothing is shown without a source.** Every insight and chart traces back to a named table. The person can reach the raw rows in one motion.
2. **Nothing teleports.** Screen state changes are motion, not cuts. A card does not vanish while a table pops in from nowhere.
3. **Calm at rest, precise when it matters.** The background is quiet. Numbers, warnings, and real findings are the only things allowed to draw attention.

## 2. Color

Two hues carry meaning: gold for sales/inflow, teal for purchasing/outflow. Ember is reserved for genuine warnings and is never decorative.

| Token | Hex | Usage |
|---|---|---|
| `ink` | `#14120F` | Page background. Warm near-black, not blue-black. |
| `ink-1` | `#1C1915` | Card / elevated surface. |
| `ink-2` | `#241F19` | Hover on cards, elevated-of-elevated. |
| `line` | `rgba(245,240,230,0.08)` | Default hairline border. |
| `line-strong` | `rgba(245,240,230,0.16)` | Emphasized border (composer, active data pane). |
| `text-hi` | `#F5F0E6` | Primary text. Warm off-white, never pure white. |
| `text-mid` | `#B9AF9D` | Secondary text, body copy inside cards. |
| `text-low` | `#756D5E` | Labels, metadata, timestamps. |
| `gold` | `#E3A542` | Sales-side accent. Positive signals. User avatar. |
| `teal` | `#2E6E62` | Purchase-side accent. Informational accent. |
| `ember` | `#C1502E` | Critical warnings only, and only when a rule fired. |

Rules:

- Never introduce a fourth accent hue. New categories borrow gold or teal, or stay neutral.
- Ember appears in at most one place per screen at a time.
- Do not casually lighten `ink`. A future light mode inverts the ramp (`ink` family → warm paper) and keeps gold/teal/ember roles.

## 3. Typography

| Face | Role | Where |
|---|---|---|
| **Fraunces** (serif, variable optical size) | The copilot’s voice | Agent chat responses only |
| **Inter** | Interface chrome | User messages, labels, buttons, navigation, card body |
| **IBM Plex Mono** | Data | KPI values, table cells, chart axes, SQL |

Type scale:

- Agent response: 16px / 1.6, Fraunces regular
- User message: 14.5px / 1.5, Inter regular
- Card body: 13.5px / 1.55, Inter regular, `text-mid`
- Metric numbers: 21–24px, Plex Mono medium
- Table cells: 13px, Plex Mono numeric / Inter labels
- Labels / citations: 11–11.5px, Inter medium, `text-low`

Chat column line length stays under ~70 characters at 16px serif.

## 4. Layout

Target canvas: **1440px** wide, comfortable padding. Desktop-first; a later shared demo link should still assume this width.

No fixed sidebar of alerts. The conversation is the channel. Insight cards attach inline to the message that owns them.

### 4.1 Chat-only (rest)

Centered riverbed. Max chat width **760px**.

```
┌──────────────────────── 1440px ────────────────────────┐
│  ambient lines                                         │
│  brand · demo clock ──────────────── connection status │
│                                                        │
│              [ agent message          ]                │
│                 └─ insight card                        │
│                    [ user message → ]                  │
│              [ agent message          ]                │
│                 └─ chart card                          │
│              ~~ composer ~~                            │
│              quick-action chips                        │
└────────────────────────────────────────────────────────┘
```

- User messages align right, max 70% of the chat column.
- Agent messages align left, max 86%.
- Cards indent 42px (avatar + gap) so they belong to the agent message.

### 4.2 Split (data open) — the product’s main motion

Chat docks left and **shrinks**. A data pane fills the remaining width. Composer stays in the chat column so the person can keep asking.

At 1440px:

| Region | Width | Notes |
|---|---|---|
| Chat column | ~440–480px | Still scrollable; line length tighter is acceptable |
| Gutter | 16–20px | Hairline, `line` |
| Data pane | remaining (~920px) | Tabs + table/chart; this is a dashboard, not a modal |

```
┌──────── chat ~460 ──┬──────── data pane ~960 ─────────┐
│ brand  clock        │ tabs: [Stockout] [Q3 by region] │
│                     │ breadcrumb · View SQL · close   │
│ [agent] …           │                                 │
│  └─ card (origin,   │  table / chart                  │
│      highlighted)   │                                 │
│ [user] …            │                                 │
│ ~~ composer ~~      │                                 │
└─────────────────────┴─────────────────────────────────┘
```

### 4.3 Tabs

Each distinct drill-down is a **tab** in the data pane (stockout rows vs monthly revenue vs a chart). Switching tabs does not replay the extract animation. Closing a tab removes that dashboard. Closing the **last** tab reverses the split and restores centered chat.

Do not stack overlapping popups. Do not use a scrim that blocks the chat.

## 5. Motion

Motion answers an action or marks that a real finding arrived. It is not decoration beyond the ambient current lines.

**The split is the design focus of the product.** It must feel like the article itself opened, not like a second app appeared.

### 5.1 Extract-and-split (open)

On click of an insight card or chart card:

1. **Capture** the card’s bounding rect (FLIP).
2. **Clone a fragment** of that card (the left edge / metric block is enough). The original card stays in the thread, highlighted (`line-strong`, category border held).
3. **Chat column** animates: centered 760px → left-docked ~460px. Messages reflow with the width; they do not jump.
4. The **fragment** travels from the card toward the data pane and **expands** into the pane’s header/surface (shared-element morph). Inner table content fades in only after the shape has mostly settled.
5. If the data pane is **already open**, skip the chat-width animation; the fragment still morphs into a **new tab**.

| Step | Duration / easing |
|---|---|
| Chat width + fragment travel | 520–600ms, `cubic-bezier(0.22, 0.8, 0.28, 1)` |
| Pane inner content fade-in | 250ms, starting ~220ms into the morph |
| Origin card highlight | 200ms border/background step, no scale |

### 5.2 Collapse (close last tab)

Exact reverse: table content fades out, fragment returns toward the origin card (re-measured after scroll), chat expands back to centered 760px.

Closing a non-last tab: tab exit only (~200ms), layout stays split.

### 5.3 Other motion

| Moment | Motion | Duration / easing |
|---|---|---|
| Insight card arrives | Drift-and-settle: translateY(10px) translateX(-6px) → 0,0, fade in | 700ms, same ease, ~300ms delay after the triggering message |
| Agent response text | Stream word-by-word | ~30–40ms per word |
| Hover on interactive card | `ink-1` → `ink-2`, `line` → `line-strong` | 200ms ease, **no** scale/lift |
| Ambient lines | Slow dash-offset; gold slower/fainter, teal slightly faster | 20s and 26s linear, opacity 0.3–0.7 |
| Tab switch | Instant content swap or 150ms opacity; no layout morph | — |

Rule of thumb: one orchestrated motion per new piece of information (its arrival), plus extract-and-split as the one “big” transition. Nothing else animates on its own.

## 6. Components

### Insight card

- 2px left border: `ember` warning, `gold` positive
- Header: icon + label (`Needs attention` / `Worth noting`), expand icon (`ti-arrows-diagonal`)
- Body: Inter, `text-mid`, 13.5px
- Optional metric row: Plex Mono, 21px
- Source line: `ti-database` + display names (`Sales.Orders`, not “our sales data”)
- Entire card is a real button; click starts extract-and-split

### Inline chart card

- Same surface as insight cards (`ink-1`, 1px `line`, 12px radius)
- Expand affordance on the label row
- Bars: `teal` default, `gold` for the bar that is the point
- Axes: Plex Mono, 10px, `text-low`

### Data pane (replaces the mock “drawer”)

- Not a modal. Does not cover the chat.
- Tab strip for open dashboards
- Header: breadcrumb (`Warehouse.StockItems filtered Product = X`), title in Fraunces medium, close
- Collapsible **View SQL** (collapsed by default), Plex Mono — transparency mechanism
- KPI strip from the query (Plex Mono values, Inter labels)
- Live chart above the table, inferred from the result columns — bar, horizontal bar, line, or pie — teal default, gold for the highlighted series/slice. Not LLM-authored chart JSON.
- Table: sticky header; numeric columns right, Plex Mono; labels left, Inter
- Rows that caused the insight: 2px left accent `ember` or `gold`

### Composer

- Anchored at the bottom of the **chat column** (not the viewport edge)
- Soft-bordered field, same as cards
- Quick-action chips under it: generated from the last agent response, not a static menu
- Stays usable while the data pane is open

### Demo clock control

- In the header, quiet, `text-low` until hovered/focused
- Shows the active as-of date (e.g. `As of 14 Sep 2015`)
- Adjustable for the demo; changing it re-runs insights and is treated as a new “today” for relative language
- Chrome, not the copilot’s voice — Inter, not Fraunces

## 7. Iconography

Tabler outline icons only, never filled. 15–16px inline; 20px max standalone. Icons inherit text color unless they mark a card category.

## 8. Voice and microcopy

- Sentence case. No title case, no all-caps labels.
- Copilot speaks in first person (“I found two things worth a look”). System chrome never does.
- Insight labels: “Needs attention” (ember), “Worth noting” (gold). Never “Critical!” / “Urgent!!”.
- Source citations are literal display names (`Sales.Orders`).
- Errors say what happened and what to do next, in the interface voice, without apologizing for a system fault.
- Empty insights: “Nothing needs your attention right now.”
- Forward-looking answers must say they are a **suggestion** and name the metrics used.

## 9. Accessibility

- `prefers-reduced-motion`: extract-and-split and drift-and-settle collapse to an opacity/layout crossfade under ~150ms. No flying fragment.
- Color is never the only signal: warning vs positive differ in icon and label, not border alone.
- Contrast: `text-mid` on `ink-1` and `text-hi` on `ink` meet WCAG AA at their sizes.
- Cards and tabs are real buttons; focus rings use `teal` or `gold` matching category.

## 10. What not to do

- No popup, drawer, or scrim that disconnects the table from the chat.
- No generic SaaS card grid with identical shadows.
- No ember/red except a rule-layer warning.
- No hover-lift/scale on every card.
- No number without a clickable path to its source.
- No hardcoded question chips that are the only way to use the product. Chips suggest; they do not define the catalog.
