# AeroMind 2.0 — Frontend Design Spec & Tickable Walkthrough

> **Status:** Proposed (part of the Stage 4 proposal; nothing here is implemented yet). **Date:** 2026-11-03.
> **Audience:** the engineer or coding agent implementing the UI. Work top to bottom; tick boxes in §8 only when the *Acceptance* line is actually met and the *Verify* step was run in that session.
> **Skill:** follow `.claude/skills/aeromind-frontend/SKILL.md` (non-negotiables, workflow) and its references: `references/tokens.md` (colour/type/space/motion values), `references/patterns.md` (component recipes, markdown overrides, layout), `references/checklist.md` (pre-merge checklist).
> **Related:** `doc/03-architecture/IMPROVEMENT-PROPOSAL.md` §4.1 (rationale, audit, wireframes), `doc/03-architecture/MULTI-SLM-ARCHITECTURE.md` §2.5, §10.5, §11 (hardware tiers, SSE stream, observability), `doc/02-analysis/adaptation-map.md` (API seams), `doc/04-plan/EXECUTION_PLAN.md` (phase tasks).
> **Legacy:** the root `FRONTEND.md` (copy-change plan, Lucide, de-jargon intent) is preserved as rationale. This file supersedes it as the working spec, and doesn't modify it.

## Contents
1. Design vision & principles
2. Design system
3. Component library — `frontend/src/ui/`
4. App shell & information architecture
5. Screen specs (with mockups)
6. Interaction, keyboard, accessibility, responsive, i18n
7. Frontend ↔ backend contract
8. **Tickable walkthrough (FE-0 … FE-11)**
9. Definition of done

---

## 1. Design vision & principles

### 1.1 Personality
**Calm, precise, trustworthy.** AeroMind is the private AI colleague of a plant engineer, a defence analyst, a bank auditor. It should feel like a well-made professional tool — closer to Linear, Vercel and GitHub than to a cockpit HUD. One warm amber accent on quiet neutral surfaces; hairline borders; generous whitespace; typography doing the work instead of glow effects.

Three words to test every screen against: **quiet** (nothing moves or glows without a reason), **legible** (a multi-model run is understandable at a glance), **honest** (the UI never claims more than the backend proved).

### 1.2 The "trust surface"
Every answer is a claim about the user's own documents. The UI's real job is to let a sceptical expert decide in seconds whether to trust it. So the most-designed parts of the product are not decorations but evidence:
- **Inline citations** on each claim, colour + icon + word by evidence tag (● Observed, ◆ Retrieved, ▲ Inferred, ? Uncertain), opening the exact page / row range / audio timestamp.
- **A verification ribbon** on each answer: "✓ Verified by Critic", "! Needs review", "✕ Failed checks", or — until the Critic exists — **"Unverified"**.
- **The agent-activity timeline**: who did what, on which model, on which device tier, how long, whether it was escalated, whether it passed.
- **Honest empties:** a missing value is "—" with a tooltip, never a plausible default.

### 1.3 Before → after positioning
| Today (audit) | AeroMind 2.0 |
|---|---|
| Dark "tactical HUD" with radar scanlines and pings (`frontend/src/index.css:34-44`, `frontend/src/components/AgentActivityHUD.jsx:104-110`) | Quiet light + dark themes, motion only for state changes |
| Always-green scorecard; invented 85/95 defaults (`frontend/src/components/EvaluationScorecard.jsx:17-18,31-34`) | Critic ribbon and "—" for unknowns |
| Fixed 45/55 split, no mobile (`frontend/src/components/ChatPanel.jsx:100`) | 3-pane / 2-pane / mobile tabs |
| Fighter-jet starter prompts (`frontend/src/components/ChatPanel.jsx:92-97`) | Prompts from the active workspace's starter kit (aviation MRO becomes one kit) |
| One page citation per answer, last `[PAGE_REF]` wins (`frontend/src/hooks/useChat.js:218-233`) | Numbered per-claim citations from `evidence_refs` |
| Google Fonts and browser cloud speech (`frontend/index.html:7-8`, `frontend/src/components/VoiceController.jsx:20-31`) | Self-hosted fonts, local ASR, zero egress |

### 1.4 Copy rules (de-jargon)
1. Say what is happening in plain words, then (optionally) the technical name: "Checking the answer · Critic · gemma-3-12b".
2. No military framing unless the active starter kit is defence and the user opted in. No "tactical", "mission", "intelligence briefing", "operational command".
3. Sentence case. Verbs for buttons ("Upload files", "Approve and write"). No exclamation marks, no emoji in system copy (status glyphs ● ◆ ▲ ? ✓ ! ✕ are icons with text labels, not emoji).
4. Errors say what failed, what was kept, what to do: "Couldn't read page 4 (corrupted PDF). The other 41 pages were added. Try re-exporting the file."
5. All copy lives in `frontend/src/locales/en/*.json` (see §6.5).

**Old → new copy table** (strings found in the audit):

| Where | Today | New (key → English) |
|---|---|---|
| `frontend/src/components/ChatPanel.jsx:121` | AeroMind Defense Intelligence Platform | `chat.welcome.title` → "Ask about your documents" |
| `frontend/src/components/ChatPanel.jsx:124` | Tactical aerospace operations platform for flight systems, cockpit schematics, … | `chat.welcome.body` → "Answers cite the exact page, row or timestamp they came from." |
| `frontend/src/components/ChatPanel.jsx:131` | Suggested Tactical Inquiries: | `chat.welcome.suggestions` → "Try asking" |
| `frontend/src/components/ChatPanel.jsx:170` | Compiling tactical intelligence briefing… | `chat.thinking` → "Working on it…" |
| `frontend/src/hooks/useChat.js:56` | Mission Commander SLM | `agent.main.title` → "Planning the steps" |
| `frontend/src/hooks/useChat.js:57` | Decomposing tactical objectives and planning dynamic execution DAG... | `agent.main.planning` → "Breaking your request into steps" |
| `frontend/src/hooks/useChat.js:288` | ⚠️ Connection to AeroMind defense server lost. Please verify backend is running. | `error.connection` → "Lost connection to the AeroMind server. Your message wasn't sent. Retry" |
| `frontend/src/components/MessageBubble.jsx:152` | OPERATIONAL CAUTION | `callout.caution` → "Caution" |
| `frontend/src/components/PromptInspectorModal.jsx:51` | AEROMIND PROMPT & LANGSMITH TRACE INSPECTOR | `admin.traces.title` → "Run traces" (admin only) |
| `frontend/src/components/PromptInspectorModal.jsx:120` | User Query / Operational Command | `admin.traces.query` → "Request" |
| `frontend/src/components/UniversalDocumentManager.jsx:81` | All Intelligence | `docs.filter.all` → "All documents" |
| `frontend/src/components/UniversalDocumentManager.jsx:82` | Flight Manuals (PDF) | `docs.filter.manuals` → "Manuals" (category names come from the kit) |
| `frontend/src/components/UniversalDocumentManager.jsx:83` | Tactical SOPs (DOCX) | `docs.filter.sops` → "Procedures (SOPs)" |
| `frontend/src/components/UniversalDocumentManager.jsx:84` | Logistics Manifests (CSV) | `docs.filter.tables` → "Spreadsheets & logs" |
| `frontend/src/components/UniversalDocumentManager.jsx:213` | Load in HUD ↗ | `docs.open` → "Open" |
| `frontend/src/components/PdfViewer.jsx:91` | Flight Manual Viewer | `artifact.empty.title` → "Select a citation or file to view it here" |
| `frontend/src/components/AircraftSelector.jsx:109` | NATO: {nato_name} | shown only in the aviation kit, as document metadata |
| `frontend/index.html:6` | AeroMind — Aviation Maintenance AI | `app.title` → "AeroMind" |
| `frontend/src/components/TopBar.jsx:49` | Offline | `status.offline` → "Server offline" with reason tooltip |

---

## 2. Design system

All values live in `frontend/src/index.css` as CSS variables on `:root` (light) and `[data-theme="dark"]`, exposed in `frontend/tailwind.config.js` (`colors: { bg: 'var(--bg)', … }`). Components never use raw hex or undefined Tailwind classes. **The authoritative values are `references/tokens.md`** (copied from proposal §4.1.1, contrast computed with the WCAG 2.1 formula). Summary:

### 2.1 Colour tokens
| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0D1117` | `#FFFFFF` | app background |
| `--surface` | `#161B22` | `#F6F8FA` | panes, cards |
| `--surface-raised` | `#21262D` | `#FFFFFF` + shadow | popovers, dialogs |
| `--text` | `#E6EDF3` | `#1F2328` | body (16.02 / 15.80 : 1) |
| `--text-muted` | `#9DA7B3` | `#59636E` | secondary (7.76 / 6.11 : 1) |
| `--accent` | `#F59E3D` | `#B45309` | brand amber, links, focus |
| `--on-accent` | `#1A1206` | `#FFFFFF` | text on accent buttons (8.68 / 5.02 : 1) |
| `--accent-hover` | `#F8B26A` | `#9A3F07` | hover |
| `--success` / `--danger` / `--warning` / `--info` | `#3FB950` / `#FF7B72` / `#D29922` / `#79C0FF` | `#1A7F37` / `#CF222E` / `#9A6700` / `#0969DA` | status |
| `--border` | `#30363D` | `#D0D7DE` | decorative dividers |
| `--border-strong` | `#6E7681` | `#8C959F` | control borders (≥ 3:1) |
| `--focus-ring` | `#F59E3D` | `#B45309` | 2 px outline + 2 px offset |
| `--evidence-observed/retrieved/inferred/uncertain` | success / info / warning / danger | same mapping | citation chips (always with icon + label) |

### 2.2 Typography
Inter for UI; JetBrains Mono only for code, IDs, hashes and numeric table columns (`font-variant-numeric: tabular-nums`). Base 16 px, ratio 1.2, `rem` units.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `--fs-xs` | 12 / 16 | 500 | metadata only — the floor (replaces 46 uses of 9–10 px text) |
| `--fs-sm` | 14 / 20 | 400–500 | secondary UI, table cells |
| `--fs-md` | 16 / 24 | 400 | body, chat |
| `--fs-lg` | 19 / 28 | 600 | section titles |
| `--fs-xl` | 23 / 32 | 600 | page titles |
| `--fs-2xl` | 28 / 36 | 600 | empty-state headlines |

Indic scripts: line height ×1.6 for `--fs-md` and below (§6.5).

### 2.3 Space, radius, elevation, motion
- **Space** (4 px grid): `--space-1` 4 · `-2` 8 · `-3` 12 · `-4` 16 · `-5` 24 · `-6` 32 · `-7` 48 · `-8` 64. Pane padding `--space-5`; card padding `--space-4`; stack gap `--space-3`.
- **Radius:** `--radius-sm` 4 (chips) · `-md` 8 (inputs, buttons) · `-lg` 12 (cards, dialogs) · `-full` (avatars, pills).
- **Elevation:** `--shadow-1` cards, `--shadow-2` popovers, `--shadow-3` dialogs; in dark mode pair with `--surface-raised` instead of relying on shadow.
- **Motion:** `--dur-fast` 120 ms (hover, press), `--dur-base` 200 ms (open/close, chip fade-in), easing `cubic-bezier(.2,.8,.2,1)`. Everything inside `@media (prefers-reduced-motion: reduce)` drops to no transition. **No infinite decorative animation.** Allowed loops: the streaming caret and skeleton shimmer (both disabled under reduced motion).

### 2.4 Iconography
`lucide-react` (already a dependency, `frontend/package.json`). 16 px in dense UI, 20 px in buttons, 1.75 stroke. Every icon-only control has a text label via `aria-label` and a tooltip. Import as `ImageIcon` etc. to avoid shadowing the global `Image` (audit: `UniversalDocumentManager.jsx:2`). Directional icons (ChevronRight, Send) get `rtl:-scale-x-100`.

### 2.5 Fonts (zero egress)
Remove `fonts.googleapis.com` from `frontend/index.html:7-8`. Self-host Inter and JetBrains Mono WOFF2 in `frontend/public/fonts/` with `@font-face` + `font-display: swap` (no new dependency), or `@fontsource/inter` + `@fontsource/jetbrains-mono` (**ADR needed**). Indic: Noto Sans Devanagari / Bengali / Tamil / Telugu subsets, loaded only for that locale.

### 2.6 Theme switch
Default follows `prefers-color-scheme`. Manual choice (Light / Dark / System) stored in `localStorage['aeromind.theme']` (wrapped in try/catch). A 6-line inline script in `index.html` sets `<html data-theme>` before first paint to avoid a flash. Tailwind: `darkMode: ['class', '[data-theme="dark"]']`. Remove `color-scheme: dark` hard-coding (`frontend/src/index.css:5-7`).

### 2.7 Density
`comfortable` (default; 40 px rows, `--space-4` padding) and `compact` (32 px rows, `--space-3`) via `<html data-density>`. Compact is offered on admin tables and task history; chat stays comfortable.

---

## 3. Component library — `frontend/src/ui/`

Plain React + Tailwind + tokens. Behaviour-heavy primitives (Dialog, Popover, Menu, Select, Tabs, Tooltip, Toast) use **Radix UI** (`@radix-ui/react-*`, **ADR needed**) for focus management and ARIA; the alternative (hand-rolled) is listed in the ADR. Each component gets a story-like demo on the `/dev/ui` route (dev builds only) used for manual light/dark/RTL checks.

| Component | Key props | Variants / states | A11y behaviour | Replaces / fixes |
|---|---|---|---|---|
| `Button` | `variant`, `size`, `loading`, `iconStart`, `iconEnd` | primary · secondary · ghost · danger; sm (36) · md (44) | native `<button>`, `aria-busy` when loading, focus ring | orange buttons at 2.95:1 (`UniversalDocumentManager.jsx:115`, `ChatPanel.jsx:245`) |
| `IconButton` | `label` (required), `icon`, `size` | ghost · subtle | `aria-label`=label, tooltip, ≥ 44 px hit area | `p-1` icon buttons (`PdfViewer.jsx:116-161`) |
| `Dialog` | `open`, `onOpenChange`, `title`, `description`, `size` | sm · md · lg · fullscreen-on-mobile | `role=dialog`, `aria-modal`, labelled, focus trap, Esc, focus return, backdrop click | 3 modal shells (`UniversalDocumentManager.jsx:94`, `PromptInspectorModal.jsx:43`, `VisualDiagramCard.jsx:89`) |
| `Popover` / `Tooltip` | `trigger`, `side`, `align` | — | Esc closes, focusable content, tooltip on focus not just hover | ad hoc popovers (`VoiceController.jsx:138`) |
| `Menu` / `Select` | `items`, `value`, `onChange` | single · searchable | listbox/menu roles, arrows, typeahead, `aria-selected` | `AircraftSelector.jsx:32-92` |
| `Tabs` | `tabs`, `value` | line · pill | roving tabindex, arrows | mobile panes, artifact panel |
| `Card` | `as`, `interactive` | flat · raised | interactive → `<button>`/`<a>` semantics | clickable `div`s (`UniversalDocumentManager.jsx:175-177`) |
| `Badge` / `Chip` | `tone`, `icon` | neutral · success · warning · danger · info | icon + text, never colour alone | `StatusBadge.jsx` (dead code; folded in, removal noted in PR) |
| `CitationChip` | `index`, `ref: EvidenceRef`, `onOpen` | observed ◆ retrieved ▲ inferred ? uncertain | `<button>` with `aria-describedby` popover; `[`/`]` keyboard nav | single `Page N` button (`MessageBubble.jsx:216-224`) |
| `VerificationRibbon` | `verdict`, `counts` | unverified · verified · needs-review · failed | text + icon; announced via live region | always-green "Sources checked ✓" (`EvaluationScorecard.jsx:31-34`) |
| `Toast` + `LiveRegion` | `tone`, `action` | info · success · error | polite / assertive live regions | `alert()` (`UniversalDocumentManager.jsx:68`), swallowed errors |
| `Skeleton` / `Spinner` | `shape`, `lines` | — | `aria-busy` on container, hidden from AT | 4 duplicated spinners |
| `EmptyState` / `ErrorState` | `title`, `body`, `action` | — | heading + actionable button | missing states (§5) |
| `ProgressSteps` | `steps[]`, `current`, `error` | horizontal · compact | `role=list`, each step has text status | — (ingestion) |
| `Timeline` | `lanes`, `events: AgentActivity[]`, `now` | live · replay | table semantics fallback (`role=table`) for screen readers | `AgentActivityHUD.jsx` |
| `DataTable` | `columns`, `rows`, `sort`, `filters` | comfortable · compact | `<table>` with `scope`, sortable headers as buttons with `aria-sort` | trace list, audit |
| `Kbd` / `CommandPalette` | `commands[]` | — | combobox pattern, Esc, arrows | — |
| `ThemeToggle` / `LocaleSwitcher` | — | — | labelled menus | — |
| `TierBadge` | `hardware`, `agents` (from `/api/health`) | cpu_lite · gpu_standard · gpu_high · gpu_multi · apple_full | button → popover with reasons, enabled/unavailable agents | — (ADR-0007) |
| `ApprovalCard` | `request`, `onApprove`, `onDeny`, `onEdit` | pending · approved · denied · expired | heading, focus moves to card on arrival, `A`/`D` shortcuts when focused | — |
| `SafeMarkdown` | `children` | — | `img`/`a`/`code`/`table` overrides (`references/patterns.md` §7) | `MessageBubble.jsx:117-176` |

---

## 4. App shell & information architecture

### 4.1 Layout
| Width | Layout |
|---|---|
| ≥ 1280 px | **3 panes:** Task rail (280 px, collapsible) · Conversation (flex) · Artifact panel (40 %, resizable splitter, width remembered) |
| 768–1279 px | **2 panes:** Conversation · Artifact panel; task rail becomes a drawer (☰) |
| < 768 px | **Single column + bottom tabs:** Chat · Sources · Activity · Tasks. Citation tap → bottom sheet. Dialogs go fullscreen. |

Remove `select-none` from the root (`frontend/src/App.jsx:56`) so answers can be copied.

### 4.2 Top bar
```
┌ ☰  ◆ AeroMind   Workspace: Plant-A Maintenance ▾   ⌕ Search or run a command  ⌘K   [Lite mode · CPU]  ● Online  ◐  अ  (JD) ┐
```
Left → right: rail toggle · logo · **workspace switcher** (Select; shows "Default workspace" until workspaces exist — planned API) · **command palette** trigger · **TierBadge** · server status (from `/api/health`, with reason tooltip; replaces silent "Offline", `TopBar.jsx:32,49`) · **ThemeToggle** · **LocaleSwitcher** · user menu (Settings, Admin if ADMIN, Sign out once auth exists). On mobile, everything after the workspace switcher moves into an overflow menu (fixes hidden controls, `TopBar.jsx:83,94`).

### 4.3 Views / routes
No router library today. Use a tiny hash router (`lib/route.ts`, no dependency) or React Router (**ADR needed**).

| Route | View | Role |
|---|---|---|
| `#/` | Workspace home → latest conversation or first-run onboarding | all |
| `#/c/:conversationId` | Conversation (chat + artifact panel) | all |
| `#/t/:taskId/activity` | Full-screen activity timeline for a task | all |
| `#/files` | Workspace files & ingestion jobs | all |
| `#/settings` | Profile, theme, density, language, voice | all |
| `#/admin/{audit,metrics,models,hardware,agents,evals,traces}` | Admin console | ADMIN |
| `#/dev/ui` | Component gallery (dev builds only) | dev |

---

## 5. Screen specs

Each screen lists **Data** (endpoint / SSE event; ⏳ = planned, not in the backend yet), **States**, **Keys**, and **Acceptance**. Planned data shows the "not available yet" state — never a mock in the real app.

### 5.1 Chat — streaming, inline citations, Critic ribbon

**Desktop (dark shown; light = same layout on `--bg #FFFFFF`, surfaces `#F6F8FA`, accent `#B45309`)**
```
┌ ☰ ◆ AeroMind  Plant-A Maintenance ▾   ⌕ ⌘K                         [GPU mode · 24 GB] ● ◐ (JD) ┐
├ Tasks ──────────┬──────────────────── Conversation ───────────────────┬ Sources │ Artifacts │ Diff ┤
│ Today           │  You                                            12:04│ inspection_03.pdf · p.4    │
│ ● RCA P-104   ⟳ │  Did pump P-104 fail before the seal replacement?    │ ┌────────────────────────┐ │
│ ○ Shift handov. │                                                      │ │ 4.2 Drive-end seal     │ │
│ ○ SOP check     │  AeroMind                     ✓ Verified by Critic  │ │ …seal weeping observed │◀┼─[1]
│ Yesterday       │  The inspection report states seal weeping on        │ │ at drive end on 14 Aug │ │
│ ○ Tender T-88   │  14 Aug [1]●, and the maintenance log records the    │ │ ▒▒▒▒▒▒▒ (highlight)    │ │
│                 │  replacement on 15 Aug [2]● (rows 212–214). Based    │ └────────────────────────┘ │
│                 │  on the available evidence, the failure preceded     │ maint_log.csv · rows 212–214│
│                 │  the replacement [3]▲.                               │                            │
│                 │  ┌ 3 sources · 2 observed · 1 inferred · 6 steps ▸ ┐ │                            │
│                 │  └ 👍 👎  ⧉ Copy  ↻ Regenerate                     ┘ │                            │
│                 │  Suggested next: Compare with P-105 history?  [Ask]  │                            │
│                 │ ┌───────────────────────────────────────────────────┐│                            │
│ + New chat      │ │ Ask about this workspace…            📎  🎤   ➤  ││                            │
│                 │ └ Enter to send · Shift+Enter new line ─────────────┘│                            │
└─────────────────┴──────────────────────────────────────────────────────┴────────────────────────────┘
  ● Observed  ◆ Retrieved  ▲ Inferred  ? Uncertain        (each chip = icon + colour + number; label in popover)
```

**Mobile (360 px)**
```
┌ ☰ Plant-A ▾        [Lite·CPU] ⋯ ┐
│ You: Did P-104 fail before…     │
│ AeroMind        ! Unverified    │
│ The inspection report states    │
│ seal weeping on 14 Aug [1]● …   │
│ [3 sources ▸]  👍 👎 ⧉          │
│┌ Ask…                  🎤  ➤ ┐ │
├─ Chat ─ Sources ─ Activity ─ Tasks ┤
└─────────────────────────────────┘
 tap [1] → bottom sheet with source page & snippet
```

- **Data:** `POST /api/chat/stream` (today; legacy frames via adapter) → ⏳ `POST /api/tasks` + `GET /api/tasks/{id}/stream` with typed events `token`, `plan`, `agent_activity`, `finding`, `contradiction`, `critic`, `approval`, `artifact`, `continuation`, `error`, `done` (§7). Feedback ⏳ `POST /api/tasks/{id}/feedback`.
- **States:** empty (welcome + 4 starter prompts from the workspace kit) · sending (optimistic user bubble) · streaming (caret, skeleton for the ribbon) · **unverified** (default until a `critic` final event) · needs-review / failed (ribbon + "What was checked" disclosure listing claim checks) · error (inline card: what failed, retry; input unlocked) · aborted ("Stopped" note, partial text kept) · no-document (sends to workspace-wide chat; fixes silent drop, `frontend/src/hooks/useChat.js:28`) · contradiction (amber callout listing both values with their sources).
- **Keys:** `/` focus input · `Enter` send (IME-safe: `e.nativeEvent.isComposing`) · `Shift+Enter` newline · `Esc` stop streaming (confirm) · `[` / `]` previous/next citation · `Ctrl/⌘ C` on focused answer copies it.
- **Acceptance:** every claim with `evidence_refs` shows a chip; chip popover shows source name + location + snippet; click opens the artifact panel at that location; ribbon reflects the last `critic` event or "Unverified"; stream ending without `done` unlocks input within 1 s; markdown external image renders as "[external image blocked]"; answer text selectable; zero axe AA violations.

### 5.2 Artifact panel — Source · Artifacts · Diff
```
┌ Sources │ Artifacts │ Diff ───────────────────────────── ⤢  ✕ ┐
│ inspection_03.pdf ▾   p. [ 4 ] / 42   − 100% +   ⌕ Find       │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │  4.2 Drive-end seal                                      │ │
│ │  ███ seal weeping observed at drive end on 14 Aug ███    │ │ ← highlight from source_ref
│ │  (text layer on: selectable & searchable)                │ │
│ └──────────────────────────────────────────────────────────┘ │
│ Cited in this answer: [1] p.4  [3] p.5                        │
└───────────────────────────────────────────────────────────────┘

Artifacts tab                                  Diff tab
┌ RCA_P-104.docx          v2 ▾  ⤓  ⓘ ┐        ┌ RCA_P-104  v1 ⇄ v2 ───────────┐
│ v2 · 12:31 · approved by J. Doe     │        │ − Root cause: bearing wear     │
│ v1 · 12:20 · superseded             │        │ + Root cause: seal failure [4] │
│ ⓘ Provenance: task t_7f2 · agents   │        │   (word-level, side-by-side    │
│   main→execution · 9 evidence refs  │        │    on ≥1280, stacked on mobile)│
│   model qwen3-8b sha:9c1… · tier    │        └────────────────────────────────┘
└─────────────────────────────────────┘
```
- **Data:** `GET /api/pdf/{id}`, `GET /api/documents/{id}/page/{n}/image` (today) · ⏳ `GET /api/artifacts/{id}` (+ versions), ⏳ `GET /api/ui/provenance/{evidence_id}` (lookup by id), CSV/XLSX rows ⏳ `GET /api/documents/{id}/rows?from=&to=`.
- **States:** empty ("Select a citation or file") · loading (page skeleton) · error (no server paths; fixes `frontend/src/components/PdfViewer.jsx:197`) · unsupported type (download link + extracted text) · artifacts unavailable ("Document generation arrives with the Execution agent").
- **Keys:** `Alt+2` focus panel · arrows/PgUp/PgDn page **only when the viewer has focus** (fixes global capture, `PdfViewer.jsx:70-83`) · `Ctrl/⌘ F` find in source.
- **Acceptance:** opening `file#page=N` lands on N with the snippet highlighted; `file#rows=a-b` opens a table scrolled to the rows; react-pdf text layer enabled (`PdfViewer.jsx:222-223`); versions listed newest first, never overwritten.

### 5.3 Upload & ingestion progress
```
┌ Add files to "Plant-A Maintenance" ───────────────────────────────── ✕ ┐
│ ┌ ⇪  Drop files here, paste, or [Browse]                              ┐│
│ └ PDF · DOCX · PPTX · XLSX/CSV · images · audio — up to 200 MB each   ┘│
│ Classification [INTERNAL ▾]    Category [Procedures ▾]                  │
│ ─────────────────────────────────────────────────────────────────────── │
│ inspection_01.pdf  ✓Uploaded ✓Scanned ✓Text PDF ✓42 units ◐Embedding    │
│ scan_02.pdf        ✓Uploaded ✓Scanned ✓Scanned PDF ◐OCR page 3/7        │
│ maint_log.csv      ✓Uploaded ✓Scanned ✓Table ✓61 units ✓Indexed         │
│ note.m4a           ✓Uploaded ✓Scanned ◐Transcribing 00:42 / 02:10       │
│ broken.pdf         ✕ CORRUPTED_PDF — no readable pages  [Details] [Retry]│
│                                         [Continue in background] [Done] │
└─────────────────────────────────────────────────────────────────────────┘
```
- **Data:** today `POST /api/documents/upload` and `POST /api/documents/session-upload` (synchronous; one "Uploaded → Indexed" step only) · ⏳ `POST /api/ingest` → `job_id`, ⏳ `GET /api/jobs/{id}`, ⏳ SSE `ingest_progress` `{file, stage, done, total}`.
- **States:** idle · dragging (outlined drop zone) · per-file progress · per-file error with `ExtractionError.error_code` · partial (`PARTIAL` status: "41 of 42 pages added") · background (toast + badge on Files) · stage-level progress unavailable ("Detailed progress arrives with background ingestion" — show a single indeterminate step, never fake stages).
- **Keys:** `Ctrl/⌘ U` open · `Esc` close (jobs continue).
- **Acceptance:** Classification, category and name inputs are real (fixes never-rendered fields, `UniversalDocumentManager.jsx:21-23`); no "RAG INDEXED" badge unless the backend said indexed (`UniversalDocumentManager.jsx:234-236`); client-side size check before upload; failures don't block other files.

### 5.4 Task history
```
┌ Tasks ─────────────── ⌕  ⚙ ┐
│ Plant-A Maintenance ▾       │
│ RUNNING                     │
│ ⟳ RCA P-104        2 m ago ▸│
│ APPROVAL NEEDED             │
│ ⚠ Write RCA report   ▸ [Review]
│ Today                       │
│ ✓ Shift handover   0:38 s   │
│ ✕ SOP check        failed   │
│ ⏸ Tender T-88      paused   │
└ + New chat ─────────────────┘
```
- **Data:** ⏳ `GET /api/ui/workspaces`, ⏳ `GET /api/tasks?workspace_id=`, ⏳ `GET /api/tasks/{id}`, ⏳ `POST /api/tasks/{id}/cancel`. Until then: conversations kept in the browser for this session only, labelled "History isn't saved yet".
- **States:** empty ("No tasks yet") · loading (rail skeleton) · error ("History unavailable — Retry") · status pills: RUNNING · WAITING_FOR_USER · APPROVAL_REQUIRED · PAUSED · COMPLETED · FAILED · CANCELLED (icon + word).
- **Keys:** `Alt+3` focus rail · arrows move · `Enter` open · `Del` cancel running (confirm).
- **Acceptance:** status pills match `ExecutionStatus` values exactly; cancel shows "Cancelling…" until the backend confirms `CANCELLED`.

### 5.5 Agent-activity timeline (signature element)
```
┌ Activity · RCA P-104 · task t_7f2 ·  [GPU mode · 24 GB]          38.4 s   ⏸ Pause  ✕ Cancel ┐
│ Plain language ◉  Technical ○                                     VRAM ███████░░░ 15.8/24 GB │
│ time ▸ 0s      5s      10s      15s      20s      25s      30s      35s                       │
│ Planning      ▇▇ Breaking the request into 9 steps · rules (no model)                        │
│ Reading files   ▇▇▇▇▇ 3 PDFs · pdf_text + RapidOCR      ▇▇▇▇▇▇ Audio note · faster-whisper   │
│ Extracting           ▇▇▇▇ Equipment & dates · qwen3-4b · 1.2 s first token · schema ✓        │
│                         ╰─▶ ▇▇▇ retried on qwen3-8b · "schema invalid"   (escalation 1/1)    │
│ Looking at images            ▇▇▇▇▇▇ Photos · qwen3-vl-8b · conf 0.71       ║ parallel lane   │
│ Analysing table              ▇▇▇▇▇ Failure timeline · coder-7b · sandbox exit 0 ║            │
│ Linking evidence                     ▇▇▇ P-104 ≡ Pump 104 · CORROBORATES 0.86                 │
│ Writing draft                           ▇▇▇▇▇ qwen3-8b ──✕ Critic: 1 unsupported ─▶ qwen3-32b ▇▇▇│
│ Checking answer                                            ▇▇ gemma-3-12b · ✓ PASS · cross-family│
│ Waiting for you                                               ⚠ Approval: write RCA report    │
│ ─────────────────────────────────────────────────────────────────────────────────────────────│
│ 9 steps · 2 parallel lanes · 1 escalation · 0 failovers · 9.1k tokens · Critic ✓            │
│ Not available on this device: Correlation (Lite mode) ← shown on cpu_lite instead of the row │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
 Click a bar → side sheet: inputs/outputs refs, evidence refs, critic claim checks, audit ids (ADMIN: full trail)
```
**Mobile:** a vertical list (one card per step: status icon · plain title · model · duration), escalations as an indented "↳ retried on …" line; swipe-free, tap to expand.

- **Data:** SSE `plan`, `agent_activity` (`AgentActivity` schema, `doc/03-architecture/MULTI-SLM-ARCHITECTURE.md` §11.3: `subtask_id, agent, title, phase, capability, model, model_version, tier, attempt, from_model, to_model, trigger, queue_wait_ms, latency_ms, tokens_out, confidence, evidence_refs, reason, ts`), `critic`, `hardware`; header VRAM from ⏳ `/api/health` (`hardware`, from Ollama `/api/ps`). Today: legacy `[DAG_PLAN]`, `[AGENT_STATUS]`, `[AGENT_THOUGHT]` frames via the adapter, which carry the *configured* model name — show "model: not reported" rather than the configured name.
- **States:** idle (collapsed summary line in chat) · live · replay (after completion, from ⏳ `GET /api/tasks/{id}`) · step failed (red bar, reason) · skipped · **unavailable on this tier** (grey row "Not available on this device (Lite mode)") · degraded ("answered from flat retrieval — graph unavailable").
- **Keys:** `Ctrl/⌘ .` toggle panel · arrows move between bars · `Enter` open details · `P` pause / resume (when supported).
- **Acceptance:** model shown is the served model from the event, never the configured name; parallel subtasks are visibly side by side; each escalation shows from → to and the trigger; Critic verdict per subtask and final; plain-language toggle swaps titles without losing technical data; screen reader gets a table fallback with the same data; reduced motion → no bar growth animation.

### 5.6 Approval prompt
```
┌ ⚠ Approval needed ─────────────────────────────────────────────────────┐
│ AeroMind wants to: write a Word document  RCA_P-104_v1.docx (6 pages)   │
│ Why it's asking: it's a factual deliverable · 2 claims are inferred ·   │
│                  the request came from document content                 │
│ Evidence: 9 references (7 observed ● · 2 inferred ▲)   [Preview] [Diff] │
│ Who can approve: policy not decided yet (needs ANALYST)                 │
│ Note (optional) [                                              ]        │
│                     [Deny  D]   [Edit, then approve]   [Approve  A]     │
└─────────────────────────────────────────────────────────────────────────┘
```
- **Data:** SSE `approval` `{action, artifact, risk, requires}` · ⏳ `POST /api/tasks/{id}/approve` `{decision, note}`.
- **States:** pending (focus moves to the card, assertive announcement) · approving (buttons disabled, spinner) · approved / denied (card collapses to a one-line record with who/when) · expired / superseded · not permitted ("You don't have permission to approve this. Ask an analyst.") · policy pending (plan §12.4; shown verbatim until decided).
- **Keys:** `A` approve / `D` deny when the card has focus; `Esc` moves focus back to input without deciding.
- **Acceptance:** nothing is written until approve returns success; the decision appears in the task history and audit; deny keeps the draft available as text.

### 5.7 Admin console (ADMIN only)
```
┌ Admin ── Audit │ Metrics │ Models │ Hardware │ Agents │ Evals │ Traces ───────────────────────┐
│ Hardware  tier gpu_high · source probe · NVIDIA (1×, 24 GB) · override: none  [Probe details ▾]│
│           Enabled: main execution coding retrieval data_analysis multimodal critic memory     │
│           Unavailable: optimization (production only)                                          │
│ VRAM      ████████████████░░░░░░░ 15.8 / 24 GB   qwen3-8b 5.6 · qwen3-vl-8b 6.1 · bge-m3 1.2  │
│ Models    name           cap         status     TTFT p50  tok/s  version     circuit   loaded  │
│           qwen3-8b-q4    planning…   ● healthy  410 ms    48     sha:9c1…    closed    hot     │
│           qwen3-vl-8b    vision      ○ cold     —         —      sha:41a…    closed    cold    │
│           gemma-3-12b    evaluation  ▲ slow     2.1 s     19     sha:77e…    half-open hot     │
│ Metrics   completion 92% · claims with valid evidence 97% · Critic pass 88% · escalations 11% │
│ Audit     [Workspace ▾][Event ▾][Failure ▾][From–To][⌕]                Export JSONL · CEF     │
│           12:04:11 GATEWAY_REJECTED  ws=B  user=u17  SECURITY_VIOLATION   ▸ trail             │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```
On `cpu_lite` the VRAM row becomes "CPU · 8 cores · RAM 23.4 / 31 GB" and the hardware card says "Lite mode — fewer agents and small models on this device".

- **Data:** `GET /api/health` (today, minimal) → ⏳ `hardware`, `agents`, `models` fields (`doc/03-architecture/MULTI-SLM-ARCHITECTURE.md` §2.5) · ⏳ `GET /api/audit?workspace_id=&failure_category=` · ⏳ `GET /api/ui/metrics` · ⏳ eval runs `GET /api/ui/evals` · Traces: `GET /api/prompts/inspect` (today; **must become ADMIN-only**, it currently exposes every trace, `backend/main.py:298-304`).
- **States:** per-widget loading/error so one failing widget doesn't blank the page · "No events match filters" · not-ADMIN → 403 page with plain explanation · planned widgets show "Not available yet — arrives in Phase N".
- **Keys:** `g a` / `g m` / `g h` jump to Audit / Metrics / Hardware; `/` focuses table filter.
- **Acceptance:** numbers come only from the backend (no client-side invented metrics); traces hidden from non-admins; exports produce the backend's JSONL/CEF unmodified.

**Eval dashboard** (tab "Evals"): runs table (date, commit, tier, pass rate, claims-with-evidence %, Critic pass, p50/p95), per-capability quality per model (feeds `quality` in `config/models.yaml`, ADR-0005), regressions highlighted against the previous run. Until the harness exists: "No evaluation runs yet".

### 5.8 Settings
Profile (name/email from IdP once decided) · Appearance (Theme: System/Light/Dark; Density; Reduce motion: follow system/always) · Language (locale list with native names; RTL preview) · Voice (local ASR on/off; input language; "Voice input is processed on this server" note; cloud speech never offered in production) · Keyboard shortcuts (read-only table) · About (version, tier, zero-egress status from `/api/health`).

### 5.9 Onboarding / first run
```
┌──────────────────────────────────────────────────────────────┐
│                       ◆ Welcome to AeroMind                  │
│   Your private AI workspace. Nothing leaves this server.     │
│                                                              │
│   1 ● Pick a starter kit   [Aviation MRO] [Process plant]    │
│                            [Legal] [Banking] [Blank]         │
│   2 ○ Add a few documents  (drag files or skip)              │
│   3 ○ Ask your first question                                │
│                                                              │
│   This device: Lite mode · CPU — answers may take ~30 s.     │
│                               [Skip]   [Get started →]       │
└──────────────────────────────────────────────────────────────┘
```
- **Data:** `/api/health` (tier, model availability) · ⏳ kits list. If no model is reachable: blocking card "No model is available. Start Ollama and install the models listed in config/models.yaml" with the missing names from `models.unavailable`.
- **Acceptance:** tier expectation shown honestly (latency hint from B1 numbers, e.g. ~9 tok/s on this i7 for qwen2.5:3b); skipping lands on an empty chat with kit prompts.

---

## 6. Interaction, keyboard, accessibility, responsive, i18n

### 6.1 Micro-interactions catalogue
| Interaction | Behaviour | Duration | Reduced motion |
|---|---|---|---|
| Send | optimistic user bubble slides 4 px up + fades in | 120 ms | instant |
| Streaming | blinking caret at end of text | 1 s loop | static caret |
| Citation arrival | chip fades in as its claim completes | 200 ms | instant |
| Critic verdict | ribbon cross-fades Unverified → Verified; polite announcement | 200 ms | instant |
| Ingestion step done | step icon ◐ → ✓ with a brief `--success` tint | 200 ms | instant |
| Escalation | arrow draws from small → large model bar | 200 ms | static arrow |
| Copy | button label → "Copied" for 1.5 s | — | same |
| Feedback 👍/👎 | toggles, optional note popover | 120 ms | instant |
| Pane resize | splitter follows pointer; double-click resets | — | — |
| Hover on cards/rows | `--surface` → `--surface-raised` | 120 ms | instant |

### 6.2 Keyboard shortcuts (`?` opens the overlay)
| Keys | Action | Scope |
|---|---|---|
| `Ctrl/⌘ K` | Command palette (workspace, file, task, theme, language) | global |
| `/` | Focus chat input | global |
| `Enter` / `Shift+Enter` | Send / new line (IME-safe) | input |
| `Esc` | Close dialog/popover · stop streaming (confirm) | global |
| `Ctrl/⌘ U` | Upload files | global |
| `Alt+1` / `Alt+2` / `Alt+3` | Focus chat / artifact panel / task rail | global |
| `[` / `]` | Previous / next citation | chat |
| `Ctrl/⌘ .` | Toggle activity timeline | global |
| `A` / `D` | Approve / deny | approval card focused |
| `g a` · `g m` · `g h` | Admin: audit · metrics · hardware | admin |
| `?` | Shortcut help | global |

Shortcuts never fire while typing in an input (except Enter/Esc), and single-letter ones only when their target has focus (WCAG 2.1.4).

### 6.3 WCAG 2.1 AA plan (mapped to audit findings)
| # | Audit finding (location) | Fix | SC |
|---|---|---|---|
| 1 | Chat textarea unlabelled (`frontend/src/components/ChatPanel.jsx:222-228`) | `<label class="sr-only">` + visible hint | 1.3.1, 4.1.2 |
| 2 | 3 modals without dialog semantics/trap/Esc | `ui/Dialog` | 2.1.2, 2.4.3, 4.1.2 |
| 3 | Dropdown without ARIA/keys (`frontend/src/components/AircraftSelector.jsx:32-92`) | `ui/Select` | 2.1.1, 4.1.2 |
| 4 | Clickable `div` cards (`frontend/src/components/UniversalDocumentManager.jsx:175-177`) | `ui/Card interactive` | 2.1.1 |
| 5 | Filters/traces lack `aria-pressed`/`aria-current` | add | 4.1.2 |
| 6 | No `aria-live` anywhere | `LiveRegion` polite/assertive | 4.1.3 |
| 7 | `outline-none` focus (`ChatPanel.jsx:227`, `PdfViewer.jsx:139`) | `:focus-visible` ring with `--focus-ring` | 2.4.7 |
| 8 | Global arrow-key capture (`frontend/src/components/PdfViewer.jsx:70-83`) | scope to focused viewer | 2.1.1 |
| 9 | `select-none` app-wide (`frontend/src/App.jsx:56`) | remove | usability |
| 10 | Contrast 3.91 / 2.95 / 2.54 / 2.50 : 1 | §2.1 token pairs | 1.4.3, 1.4.11 |
| 11 | Infinite animations, no reduced-motion | §2.3 motion rules | 2.2.2, 2.3.3 |
| 12 | Touch targets < 44 px | `Button`/`IconButton` sizes | 2.5.8 |
| 13 | Generic alt text (`frontend/src/components/VisualDiagramCard.jsx:53,60,142`) | title + page + heading | 1.1.1 |
| 14 | Glyph-only state ▴▾ ↵ | text + `aria-expanded` | 1.1.1, 4.1.2 |
| 15 | IME breaks Enter-to-send (`ChatPanel.jsx:77-81`) | `isComposing` guard | usability (CJK/Indic) |

**Tooling:** `eslint-plugin-jsx-a11y` (dev dep, **ADR needed**), `@axe-core/playwright` on the 5 key screens (**ADR needed**), manual NVDA (Windows) + VoiceOver (macOS) pass before each release, keyboard-only walkthrough of every flow.

### 6.4 Responsive rules
- Breakpoints: `sm` 640 · `md` 768 · `lg` 1024 · `xl` 1280. Layout per §4.1.
- No fixed percentage widths or `vh` heights for panes/dialogs (replace `w-[45%]` `ChatPanel.jsx:100`, `h-[88vh]` `UniversalDocumentManager.jsx:95`, `w-72` popovers); use `min()`/`clamp()` and `dvh`.
- Dialogs fullscreen below `md`; popovers become bottom sheets below `sm`.
- Tables scroll horizontally inside their card with a sticky first column; never the page.
- Test widths: 360, 768, 1024, 1280, 1920; zoom 200 % (WCAG 1.4.4) and 320 px reflow (1.4.10).

### 6.5 i18n, RTL, Indic
- **Library:** `i18next` + `react-i18next` (**ADR needed**). Files `frontend/src/locales/<lng>/<namespace>.json` (namespaces: `common`, `chat`, `files`, `activity`, `admin`, `settings`, `agents`). Keys are dotted (`chat.welcome.title`). No string concatenation; use interpolation and ICU plurals.
- **RTL:** `<html dir>` from locale (`ar`, `ur`, `he`). Tailwind logical utilities only: `ms-/me-`, `ps-/pe-`, `start-/end-`, `text-start/end`, `border-s/e`. Mirror directional icons. The timeline's time axis stays left→right (time is not text) — documented exception.
- **Indic:** `hi`, `bn`, `ta`, `te`, `mr`, `gu`, `kn`, `ml`. Noto Sans subsets per script loaded on demand; line-height ×1.6; no letter-spacing on Indic text; `Intl.NumberFormat('en-IN')` lakh/crore grouping; dates via `Intl.DateTimeFormat`.
- **Voice:** input language follows locale (replace fixed `en-US`, `VoiceController.jsx:31`); ASR is the local Whisper endpoint (⏳ `POST /api/asr`), not the browser Web Speech API.
- **Agent output:** the Main Agent answers in the UI locale (backend concern); citation snippets stay in the source language with a "Translate" action (IndicTrans2 candidate, ADR).

---

## 7. Frontend ↔ backend contract

### 7.1 SSE events
Canonical schema: `doc/03-architecture/MULTI-SLM-ARCHITECTURE.md` §10.5 and §11.3. Parser: `frontend/src/lib/sse.ts` — spec-compliant (multi-line `data:`, `data:` without space, CRLF), dispatches by `event:` name, JSON payloads only. During transition it also understands the legacy in-band frames from `/api/chat/stream` (`[DONE]`, `[DAG_PLAN:`, `[AGENT_THOUGHT:`, `[AGENT_STATUS:`, `[AGENT_STEP:`, `[VISUAL_REF:`, `[EVAL_REPORT:`, `[PAGE_REF:`, `[ERROR:` — `frontend/src/hooks/useChat.js:106-257`) behind `LEGACY_SSE`, mapping them to the typed events below with `model: null` where the legacy frame only carried the configured name.

| Event | Payload (key fields) | UI consumer | Exists today? |
|---|---|---|---|
| `hardware` | `tier`, `badge` | TierBadge, activity header | ⏳ |
| `plan` | `plan_id`, `template`, `subtasks[]`, `depth` | Timeline lanes | legacy `[DAG_PLAN]` |
| `agent_activity` | `AgentActivity` (§5.5) | Timeline rows | legacy `[AGENT_STATUS]`/`[AGENT_THOUGHT]` (partial) |
| `ingest_progress` | `file`, `stage`, `done`, `total` | Upload ProgressSteps | ⏳ |
| `finding` | `claim`, `evidence_refs[]`, `tag` | Citation chips | ⏳ (legacy `[VISUAL_REF]`/`[PAGE_REF]` → one page chip) |
| `contradiction` | `subject`, `predicate`, `values[]` | Contradiction callout | ⏳ |
| `critic` | `scope` (subtasks/final), `verdict`, `claims{}`, `cross_family` | VerificationRibbon, timeline | ⏳ (legacy `[EVAL_REPORT]` is heuristic → shown as "Heuristic score (not verification)" in admin only) |
| `token` | `text`, `revision?` | Answer body | legacy plain `data:` lines |
| `approval` | `action`, `artifact`, `risk`, `requires` | ApprovalCard | ⏳ |
| `artifact` | `artifact_id`, `version`, `name` | Artifacts tab | ⏳ |
| `continuation` | `proposal` \| `null` | "Suggested next" line (hidden when null) | ⏳ |
| `error` | `category` (FailureCategory), `message`, `recoverable` | Error card / toast | legacy `[ERROR:` |
| `done` | `status`, `latency_ms` | unlock input, finalise | legacy `[DONE]` |

> `.claude/skills/aeromind-frontend/references/patterns.md` §1–2 mirrors this table.

Rules: input unlocks on `done`, `error`, stream end **or** abort; `error` text is never overwritten by later tokens (fixes `useChat.js:245` vs `:258-267`); abort on new send, on `clearChat`, and on unmount.

### 7.2 REST endpoints per screen
| Screen | Today (exists) | Planned (⏳, show "not available yet") |
|---|---|---|
| Shell | `GET /api/health`, `GET /api/model/status` (poll → replace by health with backoff) | `hardware`/`agents`/`models` in health; `GET /api/ui/workspaces` |
| Chat | `POST /api/chat/stream` | `POST /api/tasks`, `GET /api/tasks/{id}/stream`, `POST /api/tasks/{id}/feedback`, `POST /api/tasks/{id}/cancel` |
| Artifact panel | `GET /api/pdf/{id}`, `GET /api/documents/{id}`, `GET /api/documents/{id}/page/{n}/image`, `/thumb` | `GET /api/artifacts/{id}` (+versions), `GET /api/ui/provenance/{evidence_id}` |
| Upload / Files | `POST /api/documents/upload`, `POST /api/documents/session-upload`, `GET /api/documents/list` | `POST /api/ingest`, `GET /api/jobs/{id}` |
| Task history | — | `GET /api/tasks`, `GET /api/tasks/{id}` |
| Approval | — | `POST /api/tasks/{id}/approve` |
| Admin | `GET /api/prompts/inspect` (must become ADMIN-only) | `GET /api/audit`, `GET /api/ui/metrics`, `GET /api/ui/evals`, `GET /api/memory` |
| Voice | — (browser Web Speech today) | `POST /api/asr` |

All requests go through `frontend/src/lib/api.ts` (one place for base URL from `import.meta.env.VITE_API_BASE` with `/api` default, auth header once an IdP exists, error normalisation). Later, generate a typed client from FastAPI's OpenAPI schema (proposal §4.5.4).

---

## 8. Tickable walkthrough

How to use: do stages in order; inside a stage, respect *Depends*. Tick a box only after its *Verify* step passed **in your session**; if a Verify step can't be run (no browser, no tool), leave it unticked and write why in `doc/01-status/PROJECT_STATE.md`. Steps marked **ADR needed** require an accepted ADR in `doc/07-decisions/adr/` before `npm install`.

Shared commands (from repo root):
- Build: `cd frontend && npm run build`
- Dev: `cd frontend && npm run dev` (backend on `127.0.0.1:8000`, see `frontend/vite.config.js:7-10`)
- Egress grep: `grep -rnE "https?://" frontend/src frontend/index.html | grep -v "127.0.0.1\|localhost"`
- Raw-hex grep: `grep -rnE "#[0-9a-fA-F]{3,8}\b" frontend/src --include=*.jsx --include=*.tsx`

### FE-0 — Safety, egress and blocking bugs (QW9 + QW10; no new dependencies)
- [ ] **FE-0.1 Remove Google Fonts.** Delete `fonts.googleapis.com` links (`frontend/index.html:7-8`); add `@font-face` for self-hosted Inter + JetBrains Mono WOFF2 in `frontend/public/fonts/`.
  *Acceptance:* no external font request; text renders in Inter. *Verify:* egress grep returns nothing for fonts; DevTools Network shows fonts from `/fonts/`. *Depends:* —
- [ ] **FE-0.2 SafeMarkdown.** Add `ui/SafeMarkdown.jsx` with `img`/`a`/`code` overrides (`references/patterns.md` §7) and use it in `MessageBubble.jsx:278-283`.
  *Acceptance:* `![](https://example.com/x.png)` in an answer renders "[external image blocked]"; external links are plain text with URL; inline code renders inline (fixes `MessageBubble.jsx:164-172`). *Verify:* paste a test answer via a dev fixture route; inspect DOM has no `<img src="https://…">`. *Depends:* —
- [ ] **FE-0.3 Validate backend image URLs.** `VisualDiagramCard.jsx:52,141` only accepts `/api/…` or `data:image/` sources.
  *Acceptance:* a payload with an external `image_url` shows a placeholder. *Verify:* fixture event in dev. *Depends:* —
- [ ] **FE-0.4 Null-document send.** `useChat.js:28` no longer drops the message when no manual is selected; it sends with `doc_id: null` (workspace-wide) and the input is cleared only after the request starts.
  *Acceptance:* typing a question with "All documents" selected produces an answer or a visible error. *Verify:* manual in dev with backend running. *Depends:* —
- [ ] **FE-0.5 Voice re-init bug.** `VoiceController.jsx:82` effect no longer depends on an unstable `onTranscript` (use a ref); dictation survives typing and streaming; input cleared after "Send"; mic hidden when unsupported (`VoiceController.jsx:85`).
  *Acceptance:* a 10 s dictation is captured while tokens stream. *Verify:* manual in Chrome dev (dev-only; production voice is local ASR, FE-9.4). *Depends:* —
- [ ] **FE-0.6 Stuck stream + abort.** Reset `isStreaming` after the read loop ends without `[DONE]` (`useChat.js:296-298`), on `AbortError` (`:281`) and in `clearChat` (`:20-25`); stop overwriting `[ERROR:]` text (`:245` vs `:258-267`).
  *Acceptance:* killing the backend mid-stream unlocks the input within 1 s and keeps the error visible. *Verify:* manual: start a question, stop uvicorn. *Depends:* —
- [ ] **FE-0.7 Honest scorecard (UI half of QW4).** Remove invented defaults 85/95 (`EvaluationScorecard.jsx:17-18`) and the unconditional "Sources checked ✓" (`:31-34`); missing values show "—". Remove unconditional "RAG INDEXED" / "Rendered" / "Active Grounding" labels and the 330-page fallback (`UniversalDocumentManager.jsx:234-236,289,294-302`).
  *Acceptance:* an `[EVAL_REPORT]` with missing fields shows "—"; badges only appear when the backend states them. *Verify:* fixture event; visual check. *Depends:* —
- [ ] **FE-0.8 Hide the trace inspector from general users.** Move the Prompt Inspector out of the general Settings button (`TopBar.jsx:90-98`) behind a dev/admin flag until the backend enforces ADMIN.
  *Acceptance:* default build shows no trace inspector entry. *Verify:* `npm run build` then preview. *Depends:* —
- [ ] **FE-0.9 Stop exposing server paths.** `PdfViewer.jsx:197` error shows a friendly message, no `backend/pdfs/...` path.
  *Acceptance/Verify:* request a missing doc in dev; message has no path. *Depends:* —
- [ ] **FE-0.10 Build gate.** *Acceptance:* `npm run build` succeeds with no new warnings; egress grep clean. *Verify:* record the build output verbatim in `doc/01-status/PROJECT_STATE.md`. *Depends:* FE-0.1–0.9

### FE-1 — Tooling baseline (needs ADRs)
- [ ] **FE-1.1 Lint.** ESLint + `eslint-plugin-react` + `eslint-plugin-jsx-a11y` + `npm run lint` script. **ADR needed** (dev tooling).
  *Acceptance:* `npm run lint` runs; existing violations recorded as baseline, not suppressed. *Verify:* `cd frontend && npm run lint`. *Depends:* ADR
- [ ] **FE-1.2 Unit tests.** Vitest + Testing Library, `npm test`. **ADR needed.**
  *Acceptance:* tests for FE-0.4/0.6 bugs reproduce the old failure (on a branch) and pass after the fix. *Verify:* `cd frontend && npm test`. *Depends:* ADR
- [ ] **FE-1.3 E2E + axe.** Playwright + `@axe-core/playwright` on chat, upload, activity, approval, admin. **ADR needed.**
  *Acceptance:* report produced; violations count recorded as baseline. *Verify:* `cd frontend && npx playwright test`. *Depends:* ADR
- [ ] **FE-1.4 Dependency hygiene.** Ensure `frontend/node_modules` and `frontend/dist` are git-ignored (untracking itself is QW8 and needs the user's decision).
  *Acceptance/Verify:* `.gitignore` change reviewed; `git status` clean after build. *Depends:* user decision on QW8

### FE-2 — Tokens & theme
- [ ] **FE-2.1 CSS variables.** Add all tokens from `references/tokens.md` to `frontend/src/index.css` (`:root` light, `[data-theme="dark"]` dark).
  *Acceptance:* variables present for colour, type, space, radius, shadow, motion. *Verify:* DevTools → computed styles on `<html>`. *Depends:* FE-0.10
- [ ] **FE-2.2 Tailwind mapping.** `frontend/tailwind.config.js` maps colours/spacing/radius/fontSize to the variables; `darkMode: ['class','[data-theme="dark"]']`; define or remove `navy-900`, `navy-750`; replace `animate-in*` classes (no plugin) with token transitions.
  *Acceptance:* no undefined classes remain. *Verify:* `grep -rnE "navy-(900|750)|animate-in|fade-in|slide-in-from" frontend/src` returns nothing. *Depends:* FE-2.1
- [ ] **FE-2.3 Theme switch.** Inline pre-paint script in `index.html`, `ThemeToggle` (System/Light/Dark), `localStorage['aeromind.theme']` with try/catch; drop forced `color-scheme: dark` (`index.css:5-7`).
  *Acceptance:* reload keeps choice; no flash of wrong theme; System follows OS. *Verify:* manual toggle + reload in both OS modes. *Depends:* FE-2.1
- [ ] **FE-2.4 Replace raw hex.** Swap hex backgrounds (`App.jsx:56`, `PdfViewer.jsx:87,192`, `MessageBubble.jsx:71,168,198,237`, `VisualDiagramCard.jsx:43`, `index.css:28-197`) for tokens; delete unused CSS (`.cursor-blink`, `.glow-orange`, `.glass-panel`, `.step-block`, `.step-number`) noting it in the PR.
  *Acceptance:* raw-hex grep returns only token definitions in `index.css`. *Verify:* raw-hex grep. *Depends:* FE-2.2
- [ ] **FE-2.5 Motion & type floor.** Remove radar scanline and decorative pings; add reduced-motion block; no text below `--fs-xs` (12 px).
  *Acceptance:* `grep -rn "text-\[9px\]\|text-\[10px\]\|animate-ping\|scanline" frontend/src` returns nothing. *Verify:* grep + OS reduced-motion on → nothing animates. *Depends:* FE-2.2
- [ ] **FE-2.6 Contrast check.** *Acceptance:* every text/background pair in use is in the token table with ≥ 4.5:1 (≥ 3:1 for controls). *Verify:* axe colour-contrast rule (FE-1.3) or manual check of each pair. *Depends:* FE-2.4

### FE-3 — Primitives (`frontend/src/ui/`)
- [ ] **FE-3.1 Radix decision.** **ADR needed** (Radix vs hand-rolled). *Acceptance:* ADR accepted. *Verify:* `doc/07-decisions/adr/` status Accepted. *Depends:* —
- [ ] **FE-3.2 Button, IconButton, Card, Badge/Chip, Spinner, Skeleton, Kbd.** *Acceptance:* variants per §3; 44 px targets; focus ring; dark/light. *Verify:* `/dev/ui` gallery manual check + lint clean. *Depends:* FE-2.x
- [ ] **FE-3.3 Dialog, Popover/Tooltip, Menu/Select, Tabs.** *Acceptance:* focus trap, Esc, focus return, arrow keys, ARIA roles. *Verify:* keyboard-only walkthrough of each in `/dev/ui`; axe clean. *Depends:* FE-3.1
- [ ] **FE-3.4 Toast + LiveRegion, EmptyState, ErrorState.** *Acceptance:* polite/assertive regions announce in NVDA/VoiceOver. *Verify:* screen reader manual check (record which reader). *Depends:* FE-3.2
- [ ] **FE-3.5 CitationChip, VerificationRibbon, ProgressSteps, DataTable, Timeline, TierBadge, ApprovalCard, CommandPalette, ThemeToggle, LocaleSwitcher.** *Acceptance:* each renders all states from §3/§5 from fixtures. *Verify:* `/dev/ui` + unit tests (FE-1.2). *Depends:* FE-3.3
- [ ] **FE-3.6 Migrate modals.** `UniversalDocumentManager`, `PromptInspectorModal`, `VisualDiagramCard` lightbox use `ui/Dialog`; `AircraftSelector` uses `ui/Select`; document cards use `ui/Card interactive`. Old shells kept until parity, then removed with a note.
  *Acceptance:* audit a11y items 2–4 fixed. *Verify:* keyboard-only test; axe. *Depends:* FE-3.3

### FE-4 — Typed stream client
- [ ] **FE-4.1 `lib/sse.ts`.** Spec-compliant parser, typed events (§7.1), legacy-frame adapter behind `LEGACY_SSE`.
  *Acceptance:* unit tests cover multi-line data, CRLF, no-space `data:`, legacy frames, unknown events ignored. *Verify:* `npm test`. *Depends:* FE-1.2
- [ ] **FE-4.2 `lib/api.ts`.** Base URL from `VITE_API_BASE` (default `/api`), error normalisation, single fetch wrapper.
  *Acceptance:* all components call through it (no raw `fetch('/api…')`). *Verify:* `grep -rn "fetch('/api" frontend/src` returns nothing outside `lib/`. *Depends:* —
- [ ] **FE-4.3 Rewire `useChat`.** Uses `lib/sse.ts`; state per message: tokens, findings, critic, activity, approval, artifacts, continuation; legacy path still works against today's backend.
  *Acceptance:* today's `/api/chat/stream` answers still render; fixture typed stream renders citations/ribbon. *Verify:* manual against backend + fixture test. *Depends:* FE-4.1

### FE-5 — App shell
- [ ] **FE-5.1 Layout.** 3/2/1-pane responsive shell with bottom tabs on mobile; resizable splitter; remove `select-none` (`App.jsx:56`) and fixed `w-[45%]` (`ChatPanel.jsx:100`).
  *Acceptance:* usable at 360/768/1280 px. *Verify:* DevTools device toolbar at each width. *Depends:* FE-3.2
- [ ] **FE-5.2 Top bar.** Workspace switcher (shows "Default workspace" until ⏳ API), command palette, TierBadge, status with reason, theme, locale, user menu; overflow on mobile.
  *Acceptance:* status shows the real error reason instead of bare "Offline"; nothing hidden on mobile. *Verify:* stop backend → reason appears. *Depends:* FE-3.5, FE-4.2
- [ ] **FE-5.3 Routes.** Hash routes from §4.3 (tiny router, or React Router — **ADR needed** if chosen).
  *Acceptance:* deep link `#/c/:id` restores the view; back button works. *Verify:* manual. *Depends:* FE-5.1
- [ ] **FE-5.4 Polling.** Replace 4 s infinite `/api/model/status` polling (`TopBar.jsx:27,36`) with `/api/health` polling with backoff and pause when tab hidden.
  *Acceptance:* no requests while tab hidden. *Verify:* DevTools Network with tab in background. *Depends:* FE-4.2

### FE-6 — Chat screen (§5.1)
- [ ] **FE-6.1 Message layout + states.** Empty (kit prompts, not fighter prompts `ChatPanel.jsx:92-97`), optimistic send, streaming caret, error card with retry, aborted.
  *Acceptance:* every state reachable and rendered per §5.1. *Verify:* fixtures + manual. *Depends:* FE-4.3, FE-5.1
- [ ] **FE-6.2 Inline citations.** CitationChips from `finding` events (legacy: one page chip from `[PAGE_REF]`), popover, open in artifact panel, `[`/`]` navigation.
  *Acceptance:* §5.1 acceptance for citations. *Verify:* fixture typed stream; keyboard nav. *Depends:* FE-3.5, FE-7.1
- [ ] **FE-6.3 Verification ribbon.** "Unverified" by default; updates on `critic` final.
  *Acceptance:* never shows Verified without a `critic` PASS event. *Verify:* unit test with and without critic events. *Depends:* FE-3.5
- [ ] **FE-6.4 Composer.** Labelled textarea, IME-safe Enter, attach (opens upload), mic (local ASR when available), `/` focus.
  *Acceptance:* a11y item 1 and 15 fixed. *Verify:* keyboard + IME (e.g. Hindi/Japanese input method) manual. *Depends:* FE-3.2
- [ ] **FE-6.5 Feedback, copy, continuation, contradiction callout.** 👍/👎 calls ⏳ feedback endpoint (hidden until it exists), copy, "Suggested next" only when `continuation.proposal` is non-null.
  *Acceptance:* no feedback buttons shown when the endpoint is absent. *Verify:* manual against today's backend. *Depends:* FE-4.3

### FE-7 — Artifact panel (§5.2)
- [ ] **FE-7.1 Source tab.** react-pdf text layer on (`PdfViewer.jsx:222-223`), find, highlight from `source_ref`, scoped keyboard (`PdfViewer.jsx:70-83`), clear the highlight timer (`PdfViewer.jsx:47`).
  *Acceptance:* `#page=N` jump + highlight; arrow keys don't hijack chat scrolling. *Verify:* manual. *Depends:* FE-5.1
- [ ] **FE-7.2 Table source view.** Rows view for `#rows=a-b` (⏳ rows endpoint → "Preview not available yet").
  *Acceptance:* honest placeholder until the endpoint exists. *Verify:* manual. *Depends:* FE-7.1
- [ ] **FE-7.3 Artifacts + provenance + versions.** ⏳ artifacts API; until then "Document generation arrives with the Execution agent (Phase 1.9)".
  *Acceptance:* no fake artifacts. *Verify:* manual. *Depends:* backend 1.9
- [ ] **FE-7.4 Diff tab.** Word-level diff between artifact versions or two documents (pure JS diff — **ADR needed** if a library is added).
  *Acceptance:* side-by-side ≥1280, stacked on mobile. *Verify:* fixture. *Depends:* FE-7.3

### FE-8 — Upload & files (§5.3)
- [ ] **FE-8.1 Upload dialog.** Drag/paste/browse, classification + category + name fields wired (fixes `UniversalDocumentManager.jsx:21-23`), client size check, per-file rows.
  *Acceptance:* fields reach the backend form data; oversize file rejected client-side. *Verify:* DevTools request payload. *Depends:* FE-3.3
- [ ] **FE-8.2 Progress stages.** `ProgressSteps` from ⏳ `ingest_progress` / jobs API; today a single honest indeterminate step.
  *Acceptance:* no invented stages. *Verify:* manual against today's backend. *Depends:* FE-8.1, backend 1.4
- [ ] **FE-8.3 Files view.** `#/files` list with empty/loading/error states (fixes `UniversalDocumentManager.jsx:172`), filter chips with `aria-pressed`.
  *Acceptance:* §5.3 states. *Verify:* manual + axe. *Depends:* FE-5.3

### FE-9 — Activity, tasks, approvals, tier
- [ ] **FE-9.1 Timeline.** `ui/Timeline` fed by `plan` + `agent_activity` + `critic`; lanes, parallel rows, escalation arrows, plain/technical toggle, table fallback; replaces `AgentActivityHUD.jsx` (kept until parity).
  *Acceptance:* §5.5 acceptance; legacy frames show "model: not reported". *Verify:* fixture of the RCA stream from `doc/03-architecture/MULTI-SLM-ARCHITECTURE.md` §10.5 renders correctly. *Depends:* FE-4.3, FE-3.5
- [ ] **FE-9.2 TierBadge + unavailable agents.** Reads `/api/health` `hardware`/`agents`; popover with reasons; "Not available on this device" rows.
  *Acceptance:* badge hidden (not faked) when the backend lacks `hardware`. *Verify:* today's backend → no badge; fixture `cpu_lite` → "Lite mode · CPU". *Depends:* backend 0.4b / QW11
- [ ] **FE-9.3 Task history rail.** ⏳ tasks API; until then session-only list labelled "History isn't saved yet"; status pills = `ExecutionStatus`.
  *Acceptance:* §5.4. *Verify:* manual. *Depends:* FE-5.1
- [ ] **FE-9.4 Local voice.** Mic uses ⏳ `POST /api/asr`; Web Speech only in dev with a visible "uses cloud speech" warning.
  *Acceptance:* production build makes no Web Speech calls. *Verify:* `grep -rn "SpeechRecognition" frontend/dist` after a production build returns nothing (or only behind the dev flag). *Depends:* backend ASR (3.8)
- [ ] **FE-9.5 Approval card.** Renders `approval` events; approve/deny/edit via ⏳ approve endpoint; permission and policy-pending states.
  *Acceptance:* §5.6. *Verify:* fixture + manual once backend 1.9 exists. *Depends:* FE-3.5, backend interrupt

### FE-10 — Admin, settings, onboarding
- [ ] **FE-10.1 Admin shell + role gate.** `#/admin/*` visible only to ADMIN (auth ⏳; until then dev flag).
  *Acceptance:* non-admin sees the 403 page. *Verify:* manual with flag off/on. *Depends:* FE-5.3
- [ ] **FE-10.2 Hardware & models widgets.** From `/api/health` (`hardware`, `models`), VRAM or CPU/RAM per tier.
  *Acceptance:* values only from backend; planned fields show "Not available yet". *Verify:* manual. *Depends:* FE-9.2
- [ ] **FE-10.3 Audit, metrics, evals, traces tabs.** DataTable with filters/export; traces tab uses `/api/prompts/inspect` only once the backend enforces ADMIN.
  *Acceptance:* per-widget error isolation. *Verify:* kill one endpoint (fixture) → other widgets still render. *Depends:* FE-3.5, backend 1.12/3.11
- [ ] **FE-10.4 Settings.** Theme, density, motion, language, voice, shortcuts, about.
  *Acceptance:* each setting persists and applies. *Verify:* manual reload. *Depends:* FE-2.3, FE-11.1
- [ ] **FE-10.5 Onboarding.** First-run card with kit choice, tier expectation, missing-model blocking card.
  *Acceptance:* §5.9. *Verify:* clear storage → onboarding appears; stop Ollama → blocking card names missing models. *Depends:* FE-9.2

### FE-11 — i18n, RTL, accessibility pass, performance, handoff
- [ ] **FE-11.1 i18n.** i18next setup, extract all strings (copy table §1.4), `en` complete. **ADR needed.**
  *Acceptance:* no hard-coded user-facing strings in JSX. *Verify:* lint rule or grep for JSX text literals; manual spot check. *Depends:* ADR
- [ ] **FE-11.2 RTL.** Logical utilities everywhere; `ar` pseudo-locale.
  *Acceptance:* layout mirrors correctly except the timeline axis. *Verify:* Playwright screenshot in `dir="rtl"`. *Depends:* FE-11.1
- [ ] **FE-11.3 Indic.** `hi` (and one Dravidian script, e.g. `ta`) with Noto subsets, line-height, `Intl` numbers.
  *Acceptance:* no clipped glyphs in buttons/chips. *Verify:* screenshots at 360 px and 1280 px. *Depends:* FE-11.1
- [ ] **FE-11.4 Full a11y pass.** All 15 items in §6.3 closed.
  *Acceptance:* axe: zero AA violations on the 5 key screens; keyboard-only completion of chat → upload → approve; NVDA or VoiceOver pass recorded. *Verify:* `npx playwright test` + manual log in `doc/01-status/PROJECT_STATE.md`. *Depends:* FE-6–10
- [ ] **FE-11.5 Performance.** Code-split admin and PDF viewer; thumbnails by URL not inline base64 in the stream (backend change, coordinate); virtualise long chats/tables if needed.
  *Acceptance:* initial JS (gzip) recorded and lower than today's `dist/assets/index-*.js` baseline; Lighthouse performance and a11y ≥ 90/95 on chat. *Verify:* `npm run build` size output + Lighthouse (local, no upload). *Depends:* FE-5–10
- [ ] **FE-11.6 Handoff docs.** Update this file's boxes, add light/dark/mobile/RTL screenshots to `doc/screenshots/`, note any removed legacy components in `doc/01-status/PROJECT_STATE.md`.
  *Acceptance:* screenshots for the 5 key screens × light/dark. *Verify:* files present; reviewer sign-off. *Depends:* FE-11.4

---

## 9. Definition of done

A frontend item is done when:
1. Its walkthrough box's *Acceptance* is met and its *Verify* step was run in the same session, with the result recorded (build output, test command and counts, or the manual check performed).
2. It passes `.claude/skills/aeromind-frontend/references/checklist.md` — egress, no untrusted HTML, no invented values, tokens only, light + dark, WCAG AA, responsive, i18n, all states.
3. It works against **today's** backend (legacy stream) or shows an honest "not available yet" state for planned endpoints — never a mock in the real app.
4. No new npm dependency was added without an accepted ADR.
5. Existing components were adapted or wrapped; any removal is listed in the PR/checkpoint and `doc/01-status/PROJECT_STATE.md`.
