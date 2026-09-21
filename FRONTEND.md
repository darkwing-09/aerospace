# FRONTEND.md — Aeromind UI/UX Redesign Plan

Goal: keep everything the current UI does (agent activity, citations, math readouts, PDF sync) but make it feel like a
clean, trustworthy tool — not an intimidating "tactical system." Every label a user reads should be plain, calm,
and clear. Anything technical (model names, DAG nodes, agent internals) stays visible to you as the builder, but
never surfaces as user-facing copy.

---

## 1. The Core Problem With the Current UI

The current design mixes two audiences into one interface:
- **What the user needs**: a fast, trustworthy answer with sources they can check
- **What the current UI shows them**: military/defense jargon ("TACTICAL INTELLIGENCE ACTIVE", "OPERATOR DIRECTIVE",
  "MISSION PLANNER"), emoji used as functional icons, and internal system state exposed as if it were a feature
  ("4 OPERATIONS", pulsing "radar beacon" for background processing)

None of that helps someone trying to find a fuel-pump procedure quickly. It adds friction and can read as
gimmicky or confusing rather than professional. The redesign below keeps the same functional bones —
DAG-driven agent activity, citations, math panel, PDF sync — but reframes every piece of user-facing copy
in plain language, and fixes the accessibility issues baked into the current design (emoji-as-icons, unclear
contrast, inconsistent iconography).

---

## 2. Language Rewrite — Old Copy → New Copy

Use this table directly as your copy source. Nothing on the right requires the user to know what an "agent,"
"DAG," "SLM," or "verification node" is.

| Component | Old copy | New copy |
|---|---|---|
| Top bar title | `AEROMIND v2.0 — DEFENSE TACTICAL INTELLIGENCE` | `Aeromind` — subtitle: `Flight manual assistant` |
| Status pill | `TACTICAL SYSTEM READY` | `Ready` (green dot, no extra text needed) |
| Data button | `🗄️ DATA REPOSITORY` | `Manuals` |
| Traces button | `🔬 LANGSMITH TRACES` | Move to a separate **Settings / Developer** area — this is a debugging tool, not something a user should see in the main bar at all |
| Activity panel header | `🔴 TACTICAL INTELLIGENCE ACTIVE` | `Working on it...` |
| Intent badge | `[SCHEMATICS & PROCEDURES]` | `Looking through diagrams and steps` |
| Operations count | `[4 OPERATIONS]` | Remove the count entirely — users don't need to know how many internal steps ran; show what's happening, not how many things are happening |
| Worker box title | `🎖️ Mission Planner` | `Understanding your question` |
| Worker box title | `🔍 Visual Schematics` | `Checking diagrams` |
| Worker box title | `📐 Avionics Math` | `Running the calculation` |
| Worker box title | `⚡ Tactical Briefing` | `Putting together the answer` |
| User message label | `OPERATOR DIRECTIVE` | Remove label — a chat bubble doesn't need a header to say "this is what you typed" |
| Assistant message label | `⚠️ EMERGENCY AEROMIND INTELLIGENCE BRIEFING` | Keep an urgency indicator, but make it a small colored tag, not a shouted header: `Safety-critical` (red) or nothing at all for routine answers |
| TTS button | `🔊 READ PROCEDURE` | `Listen` |
| Page ref button | `PAGE REF: 142 ↗` | `Page 142` (still clickable, same function, less shouty) |
| Thinking drawer | `🧠 Analysis Verified (1.8s) (4 operational steps) EXPAND ▼` | `How I found this ▾` |
| Grounding scorecard | `🛡️ Grounding Scorecard (Faithfulness: 98% • Citations: Verified)` | `Sources checked ✓` — collapse the percentages behind a click if a curious user wants detail; don't lead with a raw metric they have no context for |
| Hazard callout | `⚠️ FLIGHT SAFETY WARNING` | Keep as-is — this is the one place where a strong, unambiguous visual warning is correct and should stay loud |
| Input placeholder | `Ask maintenance procedure, calculate Mach/fuel, or inspect schematics…` | `Ask about a procedure, a calculation, or a diagram...` |
| Airframe tag | `MIG-21BIS • SYSTEM ACTIVE` | `MiG-21bis manual` |
| Mic button | `🎙️` | Keep icon, drop nothing — this one's fine, just needs to be a real SVG icon (see Section 4) |

**Rule going forward**: if a piece of copy describes what the *system* is doing internally (planning, routing,
verifying, DAG operations), it either gets translated into what it means *for the user* ("checking diagrams"
instead of "visual schematics agent"), or it doesn't appear in the main UI at all — push it into an optional
"details" expander for anyone curious, never as the default view.

---

## 3. Section-by-Section Redesign

### 3a. Top Bar (`TopBar.jsx`)
- Keep it minimal: product name, aircraft/manual selector, a simple ready/not-ready status dot, and a
  "Manuals" button. That's it.
- Move the LangSmith traces button out entirely — put it behind a small settings/developer menu (gear icon),
  not the primary bar. Regular users never need to see this.
- Status pill: a single colored dot (green/amber/red) with a one-word label (`Ready` / `Starting up` / `Offline`)
  is enough — drop the all-caps `TACTICAL SYSTEM READY` framing.

### 3b. Activity Panel (`AgentActivityHUD.jsx`)
This is the component doing the most "tactical" signaling right now, and the one users will look at most
during a wait. Redesign direction:
- Replace the "radar beacon" pulsing dot with a simple, calm loading indicator (a soft pulse on a single
  neutral-colored dot, not a double-ring orange radar effect)
- Replace the 4 role icons (🎖️ 🔍 📐 ⚡) with a **consistent SVG icon set** (Lucide), one icon style throughout —
  see Section 4
- Turn the "DAG node grid" into a simple horizontal progress list: a short plain-language phrase per active
  step (from the table above), with a checkmark when done. No "operations count," no jargon.
- Keep the parallel/sequential distinction visually (it's genuinely useful — shows the system is doing more
  than one thing when relevant) but represent it as steps appearing together vs. one-after-another, not as
  a "graph" the user has to parse.

### 3c. Message Feed (`MessageBubble.jsx`)
- Drop the `OPERATOR DIRECTIVE` header on user messages entirely — a chat bubble is self-explanatory.
- Assistant messages: keep the left accent color strip (good visual pattern, keep it), but reserve strong
  red/warning treatment only for genuine safety content — not as the default framing for every answer.
- `Sources checked ✓` replaces the raw faithfulness/citation percentages as the default view. If a user taps
  it, then show the detail (faithfulness %, citation accuracy) — power users can dig in, everyone else gets
  a simple reassurance signal.
- Numbered step badges (①②③) for procedures: keep — this is genuinely good UX for step-by-step instructions,
  no jargon problem here.
- Diagram thumbnails: keep the click-to-zoom pattern, just relabel "Blueprint" → "Diagram" (blueprint implies
  engineering drawings specifically; diagram is broader and plainer).

### 3d. Chat Input (`ChatPanel.jsx`)
- Mostly fine as-is structurally. Rewrite placeholder text (Section 2), rename `Ingest Data` → `Add a manual`,
  `Clear Log` → `Clear chat`.
- Send button: replace the `»` double-chevron with a proper send icon (paper plane or arrow, from the same
  SVG set as everything else) — a raw `»` character reads as a placeholder, not a finished button.

### 3e. PDF Viewer (`PdfViewer.jsx`)
- Already the least jargon-heavy part of the UI — keep the structure. Minor polish: replace `⏮ ◀ ▶ ⏭` text
  glyphs with consistent SVG nav icons matching the rest of the app, and make sure the page input box has a
  visible label for screen readers (`aria-label="Go to page"`) since it's currently just a bare number field.

---

## 4. Visual System

### Icons
Every icon in the app should come from **one consistent SVG set** — recommend **Lucide** (clean, permissive
license, huge coverage, already common in shadcn/ui projects). Remove every emoji currently used as a
functional icon (🎖️ 🔍 📐 ⚡ 🛡️ 🔊 🎙️ 🗄️ 🔬) and replace with the matching Lucide icon:

| Old emoji | Lucide replacement |
|---|---|
| 🎖️ (Mission Planner) | `brain-circuit` or `search` |
| 🔍 (Visual Schematics) | `image` |
| 📐 (Avionics Math) | `calculator` |
| ⚡ (Tactical Briefing) | `sparkles` or `file-text` |
| 🛡️ (Grounding Scorecard) | `shield-check` |
| 🔊 (Read Procedure) | `volume-2` |
| 🎙️ (Mic) | `mic` |
| 🗄️ (Data Repository) | `folder` |
| 🔬 (LangSmith) | `activity` (developer menu only) |

Emoji render inconsistently across OS/browser and can't be themed (color, size, stroke weight) — a real icon
set fixes this and instantly reads as more polished.

### Color & Theme
- Dark-first, with a proper light mode — token-driven (see Section 5), not hardcoded hex per component
- Drop the heavy orange-on-navy "tactical" palette as the *default* everywhere; keep a warm accent color for
  primary actions and active states, but reserve red/amber strictly for genuine warnings (safety callouts),
  not general UI chrome — right now urgency colors are overused (emergency red header on routine answers,
  amber radar pulses for normal background work), which dilutes them when a real warning appears
- Every text/background pair needs ≥4.5:1 contrast in both themes — audit the current dark-navy-on-dark-navy
  card patterns specifically, low-contrast surfaces are a common miss

### Typography
- 16px base body size, 1.5 line-height
- One clean sans-serif for all UI copy; monospace reserved only for the math readout panel (this is the one
  place monospace is actually meaningful — calculations benefit from fixed-width alignment)

### Motion
- Loading/streaming states: keep visible feedback, but tone down: replace the "double-ring radar pulse" with
  a single soft pulse animation, 150–300ms transitions, respect `prefers-reduced-motion`
- Live text cursor during streaming: keep — this is a good, standard pattern users already understand from
  other AI chat tools, no change needed

### Layout & Touch
- All buttons/icons ≥44×44px tap target, 8px+ spacing between interactive elements (audit the current
  compact toolbar rows — nav arrows and zoom controls in the PDF viewer are likely under this threshold)
- No color-only status signaling — pair every colored dot/badge with a text label or icon, not color alone

---

## 5. Design Tokens (for `design-system` implementation)

```css
/* Semantic tokens — map these once, theme everything through them */
--color-bg: /* near-black, not pure #000, e.g. #0e0f11 dark / #ffffff light */
--color-surface: /* card backgrounds, one step lighter than bg */
--color-border: /* visible in both themes */
--color-text-primary: /* ≥4.5:1 contrast on surface */
--color-text-secondary: /* ≥3:1 contrast on surface */
--color-accent: /* one warm accent for primary actions, active states */
--color-warning: /* reserved strictly for genuine safety callouts */
--color-success: /* status-ready, sources-checked confirmations */
--radius-card: 8px;
--space-unit: 8px; /* all spacing in multiples of this */
--font-body: 16px/1.5;
--font-mono: /* math panel only */;
--motion-duration: 200ms;
```

---

## 6. Roadmap

**Phase 1 — Copy pass (fast, no visual risk)**
Swap every label using the Section 2 table. Zero component restructuring — just text and moving the LangSmith
button behind a settings menu. Ships in isolation, immediately reduces the "intimidating" feel.

**Phase 2 — Icon system**
Replace all emoji with Lucide icons app-wide, consistent sizing via icon tokens. Touches every component that
currently has an emoji but is a mechanical find-and-replace, not a redesign.

**Phase 3 — Activity panel redesign**
Rebuild `AgentActivityHUD.jsx`'s visual treatment per Section 3b — calmer loading state, plain-language step
list instead of the DAG-grid-with-operation-count framing.

**Phase 4 — Color/contrast/token pass**
Apply the token system (Section 5), audit contrast on existing dark surfaces, tone down default urgency colors
to reserve red/amber for real warnings only.

**Phase 5 — Accessibility & touch audit**
Run the full checklist from Section 4 (Layout & Touch) against every interactive element — nav arrows, zoom
controls, page input — and fix anything under the 44×44px / 8px-spacing / contrast bar.

---

## 7. What NOT to Change

- The numbered step badges (①②③) for procedures — good pattern, no jargon issue
- The PDF viewer's page navigation structure — already clear
- The live streaming text cursor — familiar, expected pattern
- The safety warning callout treatment — this is the one place strong red/amber visual weight is correct;
  don't soften it, just stop using the same visual language for routine status
