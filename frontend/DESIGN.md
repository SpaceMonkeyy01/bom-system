# BOM System — visual design

The app follows the **Blue Cascade HRM** design system so the company's internal tools look like one family.
The approved mockups are in `design/*.html` (open them in a browser; they are static, self-contained HTML built
on the same tokens). This file is the written version: tokens, layout rules and how they map onto Mantine.

One rule sums it up: **the chrome is ink on paper; colour means status. Navy is for actions only.**

## Tokens

### Colour (light theme)

| Token | Hex | Use |
|---|---|---|
| `paper` | `#eef3f6` | App background and sidebar |
| `sheet` | `#ffffff` | The one content surface every page sits on |
| `muted` | `#f3f5f8` | Table header rows, quiet fills, row hover |
| `accent` | `#e7f0f5` | Hover on buttons and menu items |
| `sidebar-active` | `#d9e8ef` | Selected sidebar item |
| `ink` | `#1d2b3a` | Body text |
| `slate` | `#5f6e82` | Secondary text: descriptions, column headers, timestamps. Never lighter than this for text. |
| `rule` | `#dce1e8` | Borders and dividers |
| `input` | `#cbd3dd` | Form-control borders |
| `cascade` | `#00435c` | Brand navy: primary button, links, focus ring. **One primary button per page header.** |
| `on-cascade` | `#ffffff` | Text on cascade |
| `sky` | `#85b4c9` | Decoration only (login panel). Never text on white. |

Status colours — text on its `-soft` fill, always paired with a word (colour is never the only signal):

| Status | Text | Fill | BOM-app meaning |
|---|---|---|---|
| `done` | `#1e7f4f` | `#e3f4ea` | BOM saved, iFlow rate, OK |
| `missing` | `#b3261e` | `#fbe5e3` | Overdue, no template, unknown input, destructive buttons |
| `pending` | `#8f5400` | `#fdf0d9` | Due today, needs attention, stale rate, flagged line, draft |
| `neutral` | `#5d6b7a` | `#eef1f5` | Needs BOM (not urgent), manual line, no orders |
| `info` | `#3e5c7e` | `#e4edf7` | Written back, supplier rate |
| `muted-tone` | `#6b4fa0` | `#efeaf8` | spare |

Rate-source tags: iFlow → `done`, supplier → `info`, BOM (fresh) → `neutral`, BOM stale → `pending`, manual → `neutral`.

### Type

- **Jost 600** for the page title (24/32) and hero numbers (28/32). Nothing else.
- **Atkinson Hyperlegible Next** for everything else (chosen for codes like `BS-ET-16765` and `0O`). Tables use
  `font-variant-numeric: tabular-nums`.
- **JetBrains Mono 12.5px** for formulas and identifiers in the template editor only.
- Scale: section-title 16/24 700 · body 14/20 · body-strong 14/20 700 · caption 12/16 (slate) · column-header 12/16 700 (slate) · pill 12/16 700. Nothing under 11px.
- Load from Google Fonts: `Atkinson+Hyperlegible+Next:wght@400;700`, `Jost:wght@600`, `JetBrains+Mono:wght@400`.

### Spacing and radius

`space-1` 4 · `space-2` 8 · `space-3` 12 · `space-4` 16 · `space-6` 24 · `space-8` 32.
`radius-sm` 2.4px (checkboxes) · `radius-md` 4.4px (buttons, inputs) · `radius-lg` 6.4px (cards, the sheet) · `radius-full` pills only.
Cards use a `rule` border, **no shadow**.

## Layout

- Desktop: 256px sidebar on `paper` (logo mark + "BOM System / Epic Crafting", nav: Orders · Templates · Inventory ·
  Airtable sync · Reports, signed-in user at the bottom), then the `sheet` with `radius-lg`, a `rule` border, 24px padding,
  12px margin from the window edge.
- Page header: title (Jost), one-sentence description in slate, actions on the right with one primary. Breadcrumb in
  caption size above the title on detail pages.
- Filters: one row — search plus at most 3 visible filters; the rest behind a "Filters" button.
- Dashboard numbers are **sentences** ("3 orders need a BOM", with a slate sub-line) and every number links to its list.
- Lists of things to act on: **status pill first**, then the identifier (bold) with its secondary line (slate caption),
  then details, then the date at the end with urgency in words ("2 days ago", "today", "tomorrow").
- Phone (below 768px): sidebar becomes a sheet behind a menu button; any table wider than the screen becomes a list of
  cards (status + code on the first line, details below); touch targets 44px. See `design/06-orders-phone.html`.
- Detail pages (Create BOM, saved BOM, template editor): main column + a 320–360px right rail that is `position: sticky`
  and holds the totals and the "before you save / publish" checklist. Blocking problems are a checklist with To do /
  Check / OK tags, never a red banner.

## Mantine mapping

```ts
// theme.ts — the shape, not the whole file
import { createTheme, rem } from '@mantine/core'
export const theme = createTheme({
  fontFamily: '"Atkinson Hyperlegible Next", ui-sans-serif, system-ui, sans-serif',
  fontFamilyMonospace: '"JetBrains Mono", ui-monospace, monospace',
  headings: { fontFamily: 'Jost, "Atkinson Hyperlegible Next", sans-serif', fontWeight: '600', sizes: { h1: { fontSize: rem(24), lineHeight: '32px' }, h2: { fontSize: rem(16), lineHeight: '24px', fontWeight: '700' } } },
  fontSizes: { xs: rem(12), sm: rem(14), md: rem(14), lg: rem(16), xl: rem(24) },
  primaryColor: 'cascade',
  primaryShade: 6,
  colors: {
    // index 6 is the brand navy; lighter indices are the tints above
    cascade: ['#e7f0f5', '#d9e8ef', '#b9d3df', '#85b4c9', '#4f8aa6', '#1f6581', '#00435c', '#003a50', '#002c3d', '#001f2c'],
  },
  radius: { xs: '2.4px', sm: '4.4px', md: '4.4px', lg: '6.4px', xl: '6.4px' },
  defaultRadius: 'md',
  spacing: { xs: rem(4), sm: rem(8), md: rem(12), lg: rem(16), xl: rem(24) },
  other: {
    paper: '#eef3f6', sheet: '#ffffff', muted: '#f3f5f8', accent: '#e7f0f5', sidebarActive: '#d9e8ef',
    ink: '#1d2b3a', slate: '#5f6e82', rule: '#dce1e8', input: '#cbd3dd',
    status: {
      done: ['#1e7f4f', '#e3f4ea'], missing: ['#b3261e', '#fbe5e3'], pending: ['#8f5400', '#fdf0d9'],
      neutral: ['#5d6b7a', '#eef1f5'], info: ['#3e5c7e', '#e4edf7'], mutedTone: ['#6b4fa0', '#efeaf8'],
    },
  },
  components: {
    Button: { defaultProps: { radius: 'md' }, styles: { root: { fontWeight: 700, height: 36 } } },
    Paper: { defaultProps: { withBorder: true, shadow: 'none', radius: 'lg' } },
    Table: { styles: { th: { fontSize: 12, color: '#5f6e82', background: '#f3f5f8' } } },
  },
})
```

- `StatusPill` component: `radius-full`, height 24, pill text style, props `tone` (done | missing | pending | neutral | info)
  and children = the word. `RateTag` is the same at 20px for rate sources.
- `HeroNumber`: Jost 28/32 number coloured by tone + the sentence + an optional caption; renders as an `<a>` to its list.
- `AppShell`: Mantine `AppShell` with `navbar.width = 256`, navbar background `paper`, main padded 12px with the sheet
  inside; `navbar.collapsed.mobile` behind a burger below 768px.

## Not in the mockups (keep as they are until designed)

Login page (use the `sky` tint panel on the left, wordmark, form on the right), Inventory, Airtable sync and Reports pages.
When they are built, the same rules apply: one sheet, numbers as sentences, status pill first.
