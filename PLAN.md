# Plan: Master Informatik Schedule Parser + Calendar App

## Context

- **Input:** `Master Informatik.html` (SS 2026, ~34 modules, TYPO3 CMS-generated)
- **Output:** `courses.json` (Python parser) + `app.html` (browser-only calendar)
- **Tech:** Python + beautifulsoup4/lxml, FullCalendar v6 (CDN), vanilla JS, no build step

---

## Phase 1 — Python Parser (`parse.py`)

### Libraries
- `beautifulsoup4` + `lxml`

### Extraction logic

**Per module** (`.s-column-container`):
- Module number → `.s-modul-number`
- Module name → `.s-modul-title`
- Module category → `.s-modul-sg-category` (may be absent → `null`)
- Semester → inferred from accordion section heading

**Per course** (`.s-cours-box`):
- Course type → `.s-cours-typ`
- Course title → `.s-cours-title`
- Additional info → `.s-addinfo-row` (all rows joined)
- Lecturers → `.s-dozenten-box a` text (split on `;<br>`)

**Per event slot** (`.s-event-box`):
- Slot group → `.s-event-group` text (`a`/`b`/`c`/`d` or empty → `null`)
- Day → `.s_termin_tag` text (German → English, handle `"n.V."` → `null`)
- Week pattern → `.s_termin_woche` text (`A`/`B`/`null`)
- Time start/end → `.s_termin_von` / `.s_termin_bis` (HH:MM, may be a date or empty)
- Room → `.s_termin_raum`

### Edge cases
- **Block events:** `.s_termin_von` contains `DD.MM.YYYY` → `isBlockEvent: true`
- **Online/no schedule:** empty time/day fields + addinfo mention → `isOnline: true`
- **"n.V." (by appointment):** day = `null`, timeStart = `null`
- **Multiple lecturers:** parse `;<br>` separator in dozenten box

### JSON schema
```json
{
  "modules": [{
    "id": "10-202-2204",
    "number": "10-202-2204",
    "name": "...",
    "category": "Vertiefungsmodul | Kernmodul | Seminarmodul | Ergänzungsbereich | null",
    "semester": 2,
    "courses": [{
      "id": "10-202-2204-PR-0",
      "type": "Vorlesung | Übung | Praktikum | Seminar | ...",
      "title": "...",
      "lecturers": ["..."],
      "additionalInfo": "...",
      "hasMultipleSlotGroups": true,
      "slots": [{
        "slotGroup": "a | null",
        "day": "monday | tuesday | wednesday | thursday | friday | null",
        "weekPattern": "A | B | null",
        "timeStart": "09:15 | null",
        "timeEnd": "10:45 | null",
        "room": "...",
        "isBlockEvent": false,
        "isOnline": false
      }]
    }]
  }]
}
```

---

## Phase 2 — Web App (`app.html`)

### 2.1 Calendar

- **FullCalendar v6** via global CDN bundle (single `<script>` tag, ~150 KB)
- View: `timeGridWeek` (Mon–Fri only, no real dates — fixed hidden reference Monday)
- Time range: **08:00–20:00**
- Day headers show names only (no dates) via `dayHeaderFormat`
- **A/B week toggle button:** switches which `weekPattern` events are rendered (A, B, or both)

### 2.2 Sidebar — parsed courses

- Module list, grouped and collapsible
- Per-module: master checkbox to show/hide all its events
- Per-course with multiple slot groups: labeled checkbox row — `☐ Slot A  ☐ Slot B  ☐ Slot C`
- Color coding by module category:
  | Category | Color |
  |---|---|
  | Kernmodul | Blue |
  | Vertiefungsmodul | Teal |
  | Seminarmodul | Green |
  | Ergänzungsbereich | Orange |
- Per-event custom color override (see §2.4)
- "Select all / Deselect all" global shortcuts
- Sidebar can be fully collapsed to give more calendar space

### 2.3 Manual Event Creation

Users can add events not from the HTML file (e.g. external courses, appointments):

- **"+ Add Event" button** in the sidebar (separate "Custom Events" section)
- Click opens a **modal/inline form** with fields:
  - Title (required)
  - Day of week (Mon–Fri, dropdown)
  - Time start / Time end (time pickers)
  - Room / Location (optional free text)
  - Notes / additional info (optional free text)
  - Color (color picker — see §2.4)
- On save: event is added to the calendar and appears as a checkbox entry in the sidebar's "Custom Events" section (can be shown/hidden like parsed events)
- Custom events are **persisted in `localStorage`** so they survive page reloads (key: `modulplan_custom_events`)
- Each custom event has a generated `id` (e.g. `custom-<timestamp>`)
- Edit button (✏️) and delete button (🗑️) on each custom event sidebar entry
- Clicking an event on the calendar also opens the edit modal for custom events

### 2.4 Event Color Customization

Both parsed and custom events support per-event color overrides:

- **Color picker** available in the event's edit/detail modal
- Color overrides stored in `localStorage` keyed by event `id` (key: `modulplan_colors`)
- Default colors remain the category-based scheme from §2.2; overrides take precedence
- A "Reset color" link restores the category default
- The sidebar colored dot next to each event name reflects the active color

### 2.5 Work Day Optimizer Panel

Collapsible panel below the sidebar (operates on currently **visible** events only):

**Inputs:**
- N — number of working days per week (default: 2, range: 1–5)
- Work block start (default: 11:00)
- Work block end (default: 15:00)
- "Morning seminars are OK on work days" checkbox — events ending by 11:00 (or starting after 15:00) do not count as conflicts

**Algorithm (brute-force C(5, N) — max 10 combinations for N=2):**
1. Gather all currently visible events (parsed + custom, respects sidebar checkbox state and A/B toggle)
2. Enumerate all day combinations
3. For each combination: count events where `day ∈ working days AND time overlaps [workStart, workEnd]`
4. Rank by minimum conflict count; break ties by fewest "near-miss" events (ending just after workStart or starting just before workEnd)

**Result display:**
- Best day combination highlighted with conflict count
- All combinations ranked (collapsible detail table)
- Selecting a result shades the work block on the calendar as a FullCalendar `backgroundEvent` (11:00–15:00 on chosen days)

### 2.6 Calendar Events (FullCalendar internals)

- One FC event object per slot per visible checkbox
- `id` encodes: `${moduleId}-${courseIdx}-${slotIdx}` (or `custom-<timestamp>` for manual)
- `extendedProps`: full raw data for tooltip/popover
- Tooltip on hover: module name, type, room, lecturers, additional info
- Sidebar checkbox toggles call `event.setProp('display', 'none'|'auto')` — O(1), no re-render

### 2.7 Performance

- Event generation is pure JS array ops — no DOM thrashing
- FullCalendar batches all DOM updates internally
- ~100–200 total events is well within FullCalendar's sweet spot
- `localStorage` reads happen only once on page load

---

## Files to Create

| File | Description |
|---|---|
| `parse.py` | Python 3 parser using bs4 + lxml |
| `courses.json` | Output of the parser (committed alongside the app) |
| `app.html` | Single-file browser app (inline CSS + JS, no server needed) |

---

## Verification Checklist

1. `python parse.py` → inspect `courses.json`:
   - ~34 modules present
   - Datenschutz Übung has 2 slots (A/B week)
   - Lineare Algebra Übung has 4 slots (a/b/c/d)
2. Open `app.html` directly in browser (`fetch('./courses.json')`, no server needed)
3. Toggle module checkboxes → events appear/disappear on calendar
4. Toggle Übung slot checkboxes → individual slot events show/hide
5. A/B toggle: Datenschutz Übung shows only one of its two slots at a time
6. Add a custom event via modal → event appears on calendar + in sidebar
7. Reload page → custom events still present (localStorage)
8. Change event color → dot and calendar block update immediately
9. Optimizer with N=2: result avoids midday-conflict days; background shading appears on click

---

## Key Decisions

| Decision | Choice |
|---|---|
| Parser language | Python + bs4 (user preference) |
| Calendar library | FullCalendar v6 via CDN (no build step, feature-rich) |
| Übung slot selection | Checkboxes (any combination, not mutually exclusive) |
| Optimizer scope | Currently visible (sidebar-checked + A/B toggled) events only |
| Week reference | Generic Mon–Fri, no real semester dates |
| Work block | Configurable, default 11:00–15:00 |
| A/B week switching | Toggle button (not simultaneous display) |
| Custom events storage | `localStorage` (no backend needed) |
| Color overrides storage | `localStorage` |
| JS framework | Vanilla JS only |
