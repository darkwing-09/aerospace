# AeroMind 2.0 — Improvement Proposal (Stage 4)

> **Correction (2026-11-04):** the per-role models in `backend/.env` (`ORCHESTRATOR_MODEL`, `VISION_MODEL`, …) were **never applied**. Nothing calls `load_dotenv`, and they aren't pydantic fields, so every role actually ran on `qwen2.5:3b`. Statements below that "four of six configured models silently fall back" describe the fallback *code path* (`model_service.py:385-390`, removed by QW1), not what ran. See `doc/01-status/PROJECT_STATE.md` → Session 2026-11-04.


**Status**: Proposal. Nothing in it is implemented. **Date**: 2026-11-03.
**Companion docs**: [PROJECT-ANALYSIS.md](PROJECT-ANALYSIS.md) (Stage 1), [adaptation-map.md](adaptation-map.md) (Stage 3), [MULTI-SLM-ARCHITECTURE.md](MULTI-SLM-ARCHITECTURE.md) (the detailed §4.4).
**Authority**: `PROJECT-IMPLEMENTATION-PLAN.md` comes first (plan §3.1). Wherever this proposal goes beyond the plan, the extension is flagged **ADR** or **USER DECISION**. Neither is decided here.

**Rules this proposal follows**
- **Keep what exists.** No existing feature is deleted. The SSE chat, page-synced PDF viewer, agent HUD, RapidOCR fallback, page-render cache, deterministic math engine and the fine-tuned Mistral are wrapped or adapted (plan §3.2).
- **No new major dependency without an ADR.** Every new library is marked `ADR`.
- **Model names are candidates.** Each must be confirmed by the eval harness and a licence review before it is adopted.
- **Measured on this laptop.** Hardware facts come from the dev box: i7-1185G7, Intel Iris Xe iGPU, **no CUDA**, 31 GiB RAM. Throughput figures come from `bench/results/b1_per_model_AS_IS.json`.

---

## 4.1 Make it beautiful (UI/UX)

### 4.1.0 Problems in today's UI (from the Stage 1 audit)
- **No real token system.**
  - The Tailwind palette is only `navy`, `orange`, `slate`, `success`, `danger` and `warning` (`frontend/tailwind.config.js:6-17`).
  - The classes `navy-900`, `navy-750` and `animate-in` are used but never defined, so they do nothing. Examples: `frontend/src/components/MessageBubble.jsx:22`, `AgentActivityHUD.jsx:102`. The plugin they need is missing: `plugins: []` at `tailwind.config.js:20`.
  - Raw hex backgrounds are scattered through the code, e.g. `App.jsx:56` and `PdfViewer.jsx:87`.
- **Dark mode only** (`frontend/src/index.css:5-7`).
- **Contrast failures:**
  - gray-500 on navy-800 is **3.91:1** (needs 4.5:1).
  - White on orange `#e8780a` is **2.95:1**. That pair is used on the primary buttons (`UniversalDocumentManager.jsx:115`, `ChatPanel.jsx:245`).
- **No shared primitives.** The modal shell is copied twice (`UniversalDocumentManager.jsx:94-97`, `PromptInspectorModal.jsx:43-46`).
- **Fixed two-column layout.** The chat panel is `w-[45%] shrink-0` (`ChatPanel.jsx:100`), so phones can't use the app.
- **Fonts load from Google**, which is outbound traffic (egress) on every page load (`frontend/index.html:7-8`).
- **Military and tactical copy** contradicts the de-jargon plan in `FRONTEND.md:31-53`. Examples: `ChatPanel.jsx:121-131`, `useChat.js:56-57`.

### 4.1.1 Design tokens (CSS variables)
Define these tokens on `:root` and `[data-theme="dark"]` in `frontend/src/index.css`. Expose them in `tailwind.config.js` as `colors: { bg: 'var(--bg)', … }`. Tailwind 3.4 is already installed, so this adds no new dependency.

Every ratio below was **computed this session** with the WCAG 2.1 relative-luminance formula.

| Token | Dark | Light | Use | Contrast vs `--bg` (dark / light) |
|---|---|---|---|---|
| `--bg` | `#0D1117` | `#FFFFFF` | app background | — |
| `--surface` | `#161B22` | `#F6F8FA` | panels, cards | — |
| `--surface-raised` | `#21262D` | `#FFFFFF` + shadow | popovers, dialogs | — |
| `--text` | `#E6EDF3` | `#1F2328` | body text | **16.02 / 15.80** |
| `--text-muted` | `#9DA7B3` | `#59636E` | secondary text. Replaces gray-500/600 | **7.76 / 6.11** (on surface: 7.09 / 5.74) |
| `--accent` | `#F59E3D` | `#B45309` | links, focus, brand orange | **8.87 / 5.02** |
| `--on-accent` | `#1A1206` | `#FFFFFF` | text on accent buttons. Replaces white-on-`#e8780a` (2.95) | **8.68 / 5.02** |
| `--accent-hover` | `#F8B26A` | `#9A3F07` | hover state | white on `#9A3F07` = 6.80 |
| `--success` | `#3FB950` | `#1A7F37` | PASS, healthy | 7.45 / 5.08 |
| `--danger` | `#FF7B72` | `#CF222E` | FAIL, errors | 7.51 / 5.36 |
| `--warning` | `#D29922` | `#9A6700` | CAUTION, degraded | 7.50 / 4.87 |
| `--info` | `#79C0FF` | `#0969DA` | citations, info | 9.73 / 5.19 |
| `--border` | `#30363D` | `#D0D7DE` | decorative dividers only | n/a (non-text, decorative) |
| `--border-strong` | `#6E7681` | `#8C959F` | input and control borders (WCAG 1.4.11 needs 3:1) | **4.12 / 3.04** |
| `--focus-ring` | `#F59E3D` | `#B45309` | 2 px outline plus 2 px offset | 8.11 vs surface / 4.72 vs surface |
| `--evidence-observed` | `#3FB950` | `#1A7F37` | citation chip for `observed` | as success |
| `--evidence-retrieved` | `#79C0FF` | `#0969DA` | `retrieved` | as info |
| `--evidence-inferred` | `#D29922` | `#9A6700` | `inferred` | as warning |
| `--evidence-uncertain` | `#FF7B72` | `#CF222E` | `uncertain` | as danger |

**Evidence chips must not rely on colour alone (WCAG 1.4.1).** Each chip also carries an icon and a text label:
- ● observed
- ◆ retrieved
- ▲ inferred
- ? uncertain

**Theme switching**
- The default follows `prefers-color-scheme`.
- A manual toggle is stored in `localStorage` under the key `aeromind.theme`.
- `<html data-theme>` is set before first paint by a tiny inline script in `index.html`, which avoids a flash of the wrong theme.

**Type scale.** Ratio 1.2, base 16 px, set with `rem`. This removes the 46 uses of 9–10 px text that the audit found.

| Token | Size / line height | Use |
|---|---|---|
| `--fs-xs` | 12 / 16 | metadata only. Never smaller than this |
| `--fs-sm` | 14 / 20 | secondary UI |
| `--fs-md` | 16 / 24 | body, chat |
| `--fs-lg` | 19 / 28 | section titles |
| `--fs-xl` | 23 / 32 | page titles |
| `--fs-2xl` | 28 / 36 | empty-state headlines |

**Fonts**
- Inter (UI) and JetBrains Mono (code and numeric tables only, per `FRONTEND.md:143`).
- Self-hosted through `@fontsource/inter` and `@fontsource/jetbrains-mono` (small packages, but still listed in the ADR) or copied into `frontend/public/fonts/`.
- `fonts.googleapis.com` is removed from `index.html:7-8`.
- For Indic scripts: Noto Sans Devanagari, Tamil, Telugu and Bengali, as subset WOFF2 files loaded per locale.

**Spacing.** A 4 px grid: `--space-1` 4, `-2` 8, `-3` 12, `-4` 16, `-5` 24, `-6` 32, `-7` 48, `-8` 64.

**Radius.** `--radius-sm` 4, `-md` 8, `-lg` 12, `-full` 9999.

**Elevation.**
- `--shadow-1`: cards, `0 1px 2px rgb(0 0 0 / .2)`.
- `--shadow-2`: popovers.
- `--shadow-3`: dialogs.
- In dark mode, shadows are paired with a `--surface-raised` tint, because shadows are hard to see on dark backgrounds.

**Motion**
- `--dur-fast` 120 ms, `--dur-base` 200 ms, easing `cubic-bezier(.2,.8,.2,1)`.
- All animation is wrapped in `@media (prefers-reduced-motion: reduce) { animation: none; transition: none; }`.
- This replaces the infinite radar scanline (`index.css:34-44`) and the `animate-ping` decorations (`AgentActivityHUD.jsx:110`).

### 4.1.2 Component library — `frontend/src/ui/`
Plain React with Tailwind and the tokens above. Lucide icons are kept (they are already a dependency, `frontend/package.json`).

**New dependency, ADR required.** `@radix-ui/react-*` primitives (dialog, popover, dropdown-menu, tabs, tooltip, toast, select). These provide focus trapping, Escape-to-close and the ARIA patterns that the audit found missing everywhere. The alternative is to hand-roll the same behaviour, which is cheaper on dependencies but riskier. The ADR should weigh the two.

| Component | Replaces / fixes |
|---|---|
| `Button` (primary, secondary, ghost, danger; sizes sm/md; at least 44 px touch target) | ad hoc orange buttons that fail contrast; `p-1` icon buttons smaller than 44 px (`PdfViewer.jsx:116-161`) |
| `IconButton` (requires `label`) | missing aria-labels |
| `Dialog` (Radix) | 3 modals with no `role="dialog"`, focus trap or Escape handling (`UniversalDocumentManager.jsx:94`, `PromptInspectorModal.jsx:43`, `VisualDiagramCard.jsx:89`) |
| `Popover`, `Menu`, `Select` | `AircraftSelector` dropdown with no keyboard or ARIA support (`AircraftSelector.jsx:32-35,69-92`) |
| `Tabs` | mobile panel switching |
| `Card`, `Badge`, `Chip`, `CitationChip` | ad hoc cards; evidence-tag chips |
| `Toast` + `aria-live` region | `alert()` (`UniversalDocumentManager.jsx:68`) and silent errors |
| `Skeleton`, `Spinner` (one implementation) | 4 duplicated spinners |
| `EmptyState`, `ErrorState` | missing states (see 4.1.4) |
| `ProgressSteps` | ingestion stages |
| `Timeline` | agent-activity view |
| `DataTable` (sortable, virtualised later) | audit and metrics tables |
| `Kbd`, `CommandPalette` | keyboard shortcuts |
| `ThemeToggle`, `LocaleSwitcher`, `TierBadge` | theme, i18n, hardware tier (ADR-0007) |

`StatusBadge.jsx` is dead code (never imported). It is folded into `Badge`, not deleted silently. Its removal is listed in the PR description.

### 4.1.3 Redesigned key screens

**(1) Chat with streaming and inline citations**
- Answer text streams token by token, as it does today.
- Citations come from `evidence_refs` (plan §7.4/§8.10), not from a single `[PAGE_REF]` that the last event overwrites (`useChat.js:218-233`).
  - Each claim gets a numbered `CitationChip` (`[1]`, `[2]`) coloured by evidence tag.
  - Hovering or focusing a chip shows the source name, page or row range, and the snippet.
  - Clicking opens the source in the artifact panel at that location.
- The evidence wording follows plan §8.10. For example, "The uploaded PDF states…" is rendered from the tag, not from prompt style.
- Each answer carries a "Verified by Critic" or "**Unverified**" ribbon. Until the Critic exists (Phase 1), every answer shows "Unverified". This replaces today's always-green "Sources checked ✓" (`EvaluationScorecard.jsx:31-34`).
- Text is selectable: remove `select-none` (`App.jsx:56`).
- Enter sends, Shift+Enter adds a newline. IME-safe: check `e.nativeEvent.isComposing`, which today's handler at `ChatPanel.jsx:77-81` doesn't.
- Bug fix: a send with no document selected currently drops the message silently (`useChat.js:28`). It should go to workspace-wide chat instead.

**(2) Artifact panel.** This is the right pane, a generalisation of today's PDF viewer. It has tabs:
- **Source.** PDF, image or table, opened at the cited location. Turn on the react-pdf text layer, which today is disabled (`PdfViewer.jsx:222-223`), so text can be searched and selected.
- **Artifacts.** Generated docx, xlsx and pptx files and charts, with a version list (v1, v2, …) and a provenance drawer showing the task, agent chain, evidence and model plus version.
- **Diff.** Compare two versions, or two documents (4.2).

**(3) Upload with ingestion progress**
- Drag and drop, a file picker, and paste.
- Each file gets a `ProgressSteps` row: Uploaded → Scanned (malware and malformed-file checks) → Detected type → Extracted (N units) → Chunked → Embedded → Indexed. Progress comes from `GET /api/jobs/{id}` or SSE (plan §8.15).
- Failures are shown per file with the `ExtractionError.error_code`, e.g. "CORRUPTED_PDF — page 4 unreadable".
- Classification level and workspace are chosen at upload. Today the category and name inputs are never rendered (`UniversalDocumentManager.jsx:21-23`).

**(4) Task history.** A left rail, grouped by workspace, then conversation, then task. Each entry shows a status pill (RUNNING, WAITING_FOR_USER, APPROVAL_REQUIRED, COMPLETED, FAILED, CANCELLED), duration, and Resume or Cancel actions (`/api/tasks/{id}/cancel`).

**(5) Agent-activity timeline.** This upgrades `AgentActivityHUD.jsx`.
- A vertical timeline or swimlane, one row per subtask in the DAG.
- Each row shows: agent, capability tag, the **model actually served** and its version, hardware tier, queue wait, TTFT, duration, tokens, retries and escalations, and the Critic verdict.
- Rows that ran in parallel are drawn side by side.
- Escalations are drawn as an arrow from the small model to the larger one, with the reason, e.g. "schema invalid".
- The data comes from typed SSE `event: agent_activity` frames, replacing the in-band `[AGENT_STATUS:…]` strings (`agent_orchestrator.py:185`).
- A "plain language" toggle keeps the jargon-free labels that `FRONTEND.md` asks for.

**(6) Approval prompts.** An inline card in the chat for the `APPROVAL_REQUIRED` state. It shows:
- what will happen (the tool, the target, a diff or preview),
- why approval is needed (risk level, document-originated content),
- **Approve**, **Deny** and **Edit and approve** actions.

The approver's identity and authority come from the policy, which is an open plan question (§12.4). The card shows "approval authority: pending policy" until that is decided.

**(7) Admin dashboards** (ADMIN role)
- **Audit.** A filterable table of AuditEvents (workspace, user, event_type, failure_category, time). Drilling in reconstructs the trail REQUEST → PLAN → AGENT_DISPATCH → TOOL_CALL → EVALUATION → RESPONSE, with export to JSONL or CEF.
- **Metrics.** Task completion rate, % of claims with valid evidence, Critic pass rate per agent and model, escalation rate, p50/p95 latency per task type, and feedback 👍/👎.
- **Model health.** Each registry entry shows: status (healthy, degraded or open circuit), last check, failover count, version hash, and loaded-or-cold state (Ollama `/api/ps`).
- **GPU/VRAM.** Per device: total, used, and per model resident. CPU and RAM on `cpu_lite`.
- **Hardware tier.** The `TierBadge` shows the detected tier, the probe output and any override (`AEROMIND_HW_TIER`). It is also visible in the top bar for every user.

### 4.1.4 Polish: micro-interactions and states

**Micro-interactions**
- A caret shows while streaming.
- Citation chips fade in as their claims arrive.
- Optimistic user bubble.
- Copy button on answers and code blocks.
- 👍/👎 with an optional note, which calls `POST /api/tasks/{id}/feedback`.
- Subtle success flash when an ingestion step completes.
- Everything respects reduced-motion.

**Empty, loading and error states for every screen**

| Screen | Empty | Loading | Error |
|---|---|---|---|
| Chat | Workspace welcome with 4 **domain-neutral** starter prompts from the active starter kit, replacing the hardcoded fighter prompts (`ChatPanel.jsx:92-97`) | streaming skeleton plus timeline | inline error card with retry. Today a stream without `[DONE]` locks the input forever (`useChat.js:296-298`) |
| Documents | "No documents in this workspace — drop files here" | list skeleton | per-file error code. Today the list has no empty or error state (`UniversalDocumentManager.jsx:172`) |
| Artifact panel | "Select a citation or artifact" | page skeleton | load error without exposing the server path. Today `PdfViewer.jsx:197` prints `backend/pdfs/{id}.pdf` |
| Task history | "No tasks yet" | rail skeleton | "History unavailable — retry" |
| Admin | "No events match filters" | table skeleton | per-widget error, so the rest of the dashboard still renders |
| Model status | — | — | "Model service offline — N models unreachable". Today errors are swallowed and the top bar just says "Offline" (`TopBar.jsx:32`) |
| Voice | mic hidden when unsupported. Today the button is shown but does nothing (`VoiceController.jsx:85`) | "Listening…" with `aria-live` | permission denied or ASR failure message |

**Keyboard shortcuts.** A `?` overlay lists them all.

| Keys | Action |
|---|---|
| `Ctrl/⌘ K` | Command palette (switch workspace, document, task, or theme) |
| `/` | Focus chat input |
| `Enter` / `Shift+Enter` | Send / newline (IME-safe) |
| `Esc` | Close dialog or popover; stop streaming (with confirmation) |
| `Ctrl/⌘ U` | Upload |
| `Alt+1 / 2 / 3` | Focus chat / artifact panel / task history |
| `[` / `]` | Previous / next cited source |
| `Ctrl/⌘ .` | Toggle agent-activity timeline |
| `A` / `D` (approval card focused) | Approve / deny |
| `?` | Shortcut help |

The global arrow-key capture in `PdfViewer.jsx:70-83` breaks scrolling everywhere. It is scoped to the focused PDF region instead.

### 4.1.5 Accessibility (WCAG 2.1 AA): fixes mapped to audit findings

| # | Finding | Fix | WCAG |
|---|---|---|---|
| 1 | Chat textarea has no label (`ChatPanel.jsx:222-228`) | visible or `sr-only` `<label>` | 1.3.1, 4.1.2 |
| 2 | Modals have no dialog semantics, trap, Escape or focus return | `ui/Dialog` (Radix) | 2.1.2, 2.4.3, 4.1.2 |
| 3 | Dropdown has no ARIA or keyboard support (`AircraftSelector.jsx:32-92`) | `ui/Select` / `Menu` | 2.1.1, 4.1.2 |
| 4 | Clickable `div` document cards (`UniversalDocumentManager.jsx:175-177`) | `<button>` or `role=button` plus a key handler | 2.1.1 |
| 5 | No `aria-pressed` / `aria-current` on filters and traces | add them | 4.1.2 |
| 6 | No `aria-live` anywhere | polite live region for streamed answer completion and agent status; assertive for errors | 4.1.3 |
| 7 | Focus styles removed (`outline-none`) | `:focus-visible` ring using `--focus-ring` | 2.4.7 |
| 8 | Global arrow-key `preventDefault` (`PdfViewer.jsx:70-83`) | scope it to the viewer | 2.1.1 |
| 9 | `select-none` on the whole app (`App.jsx:56`) | remove | 1.3.1 (usability) |
| 10 | Contrast failures (3.91, 2.95, 2.54, 2.50) | new token pairs in 4.1.1 | 1.4.3, 1.4.11 |
| 11 | Infinite animations, no reduced-motion handling | wrap animations | 2.3.3 (AAA guidance), 2.2.2 |
| 12 | Touch targets under 44 px | Button sizes | 2.5.5 (AAA guidance) / 2.5.8 (2.2 AA, 24 px) |
| 13 | Generic alt text "Page N thumb" (`VisualDiagramCard.jsx:53,60,142`) | alt = document title + page + top heading | 1.1.1 |
| 14 | Glyph-only state (▴▾ ↵) | text label plus `aria-expanded` | 1.1.1 |
| 15 | Enter-to-send breaks IME | `isComposing` guard | 3.3.x (usability for CJK/Indic input) |

**Verification**
- `eslint-plugin-jsx-a11y` (dev dependency, lint only; recorded in the dev-tooling ADR).
- `@axe-core/playwright` run on the 5 key screens in CI.
- A manual pass with NVDA and VoiceOver before each release.

### 4.1.6 Responsive and mobile layout

| Breakpoint | Layout |
|---|---|
| ≥1280 px | 3 panes: task rail (collapsible), chat, artifact panel (resizable splitter that remembers its width) |
| 768–1279 px | 2 panes: chat and artifact panel; task rail becomes a drawer |
| <768 px | single column with a bottom tab bar (Chat · Sources · Activity · Tasks). Citation tap opens a bottom sheet with the source |

- Fixed sizes are replaced with fluid ones: `w-[45%]` (`ChatPanel.jsx:100`), `h-[88vh]` (`UniversalDocumentManager.jsx:95`), `w-72` popovers.
- Controls hidden on mobile today (`TopBar.jsx:83,94`) move into an overflow menu.

### 4.1.7 Internationalisation (i18n), RTL and Indic languages
- **Library.** `i18next` + `react-i18next` (ADR). Messages live in `frontend/src/locales/<lng>/*.json`, loaded per namespace.
- **Copy.** All hardcoded English strings are extracted. This also completes the de-jargon copy table in `FRONTEND.md:31-53`.
- **RTL.** `dir` is set on `<html>` from the locale (ar, ur, he). Tailwind classes move to logical properties: `ms-*`/`me-*`, `ps-*`/`pe-*`, `start-*`/`end-*`, `text-start`. Directional icons such as chevrons and send are mirrored.
- **Indic.** hi, bn, ta, te, mr, gu, kn, ml.
  - Noto font subsets per script.
  - Line height raised to 1.6 for scripts with stacked glyphs.
  - Hyphenation off.
  - Number formatting via `Intl.NumberFormat` (lakh/crore grouping for en-IN and hi-IN).
- **Voice.** Today `lang` is fixed to `en-US` (`VoiceController.jsx:31`) and audio goes through the browser Web Speech API, which can send it to vendor clouds. It is replaced by local Whisper / faster-whisper ASR on the backend (plan §8.16). Whisper large-v3 and turbo support Hindi, Tamil and other Indic languages; quality must be measured per language. IndicTrans2 is the candidate for translation (ADR).
- **Model side.** The Main Agent replies in the user's locale. Retrieval stays cross-lingual through a multilingual embedding model (bge-m3 is the candidate; see §4.4, ADR, and open question §12.7).

### 4.1.8 Before and after wireframes (top 5 screens)

**1. Chat, before** (`App.jsx:56-89`, `ChatPanel.jsx:100`)
```
┌ TopBar: AeroMind ▾[MiG-21bis]   ● Offline   ⚙ ─────────────────────────────┐
├──────────── chat 45% ────────────┬────────────── PDF viewer 55% ───────────┤
│ "Suggested Tactical Inquiries"   │                                          │
│  ▸ afterburner fuel burn…        │          [ page 1 of 330 ]               │
│ ┌ HUD: Mission Commander SLM ┐   │                                          │
│ └ (radar scanline animation) ┘   │                                          │
│ 🤖 answer…  [Page 242]            │                                          │
│ Scorecard: Faithful 78% ✓ Safe ✓ │  (fixed split, no mobile, no light mode) │
│ [ textarea, no label ]   🎤 SEND  │                                          │
└──────────────────────────────────┴──────────────────────────────────────────┘
```

**1. Chat, after**
```
┌ ☰  Workspace: Plant-A Maintenance ▾   ⌘K Search      [Lite mode · CPU] ◐ 👤 ┐
├ Tasks ─────┬──────────────── Conversation ──────────┬── Sources │ Artifacts ─┤
│ ● RCA P-104│ You: Did pump P-104 fail before the    │ inspection_03.pdf p.4  │
│ ○ Shift HO │      seal replacement?                  │ ┌──────────────────┐   │
│ ○ SOP chk  │ AeroMind: The inspection report states │ │ …seal weeping at │   │
│            │ seal weeping on 14 Aug [1]●, and the    │ │  drive end… ▒▒▒▒ │◀─[1]
│            │ maintenance log records replacement on  │ └──────────────────┘   │
│            │ 15 Aug [2]● (rows 212–214). Based on    │ maint_log.csv r212-214 │
│            │ the available evidence the failure      │                        │
│            │ preceded replacement [3]▲.              │                        │
│            │ ✔ Verified by Critic · 3 sources        │                        │
│            │ Suggested next: compare P-105 history?  │                        │
│            │ ┌ Ask anything… (/ to focus) ──── 🎤 ➤ ┐│                        │
└────────────┴────────────────────────────────────────┴────────────────────────┘
 ● observed  ◆ retrieved  ▲ inferred  ? uncertain   (icon + colour + label)
```

**2. Upload, before.** A modal with only a file picker. Every upload is sent as `AIRCRAFT_MANUAL` (`UniversalDocumentManager.jsx:21-23,59-66`), always labelled "RAG INDEXED" (`:234-236`).

**2. Upload, after**
```
┌ Add files to “Plant-A Maintenance” ─────────────────────────────── ✕ ┐
│  ⇪ Drop files or browse      Classification: [INTERNAL ▾]            │
│ inspection_01.pdf  ✔Upload ✔Scan ✔Detect(text PDF) ✔Extract 42u ◐Embed │
│ scan_02.pdf        ✔Upload ✔Scan ✔Detect(scanned) ◐OCR p3/7            │
│ maint_log.csv      ✔Upload ✔Scan ✔Detect ✔Extract 61u ✔Embed ✔Indexed │
│ note.m4a           ✔Upload ✔Scan ◐ASR 00:42/02:10                     │
│ broken.pdf         ✖ CORRUPTED_PDF — 0 pages readable   [details]     │
│                                             [Run in background] [Done]│
└───────────────────────────────────────────────────────────────────────┘
```

**3. Agent activity, before.** The HUD has 5 fixed stages and decorative animation. A "dispatcher" lights 3 nodes at once (`AgentActivityHUD.jsx:40-46,95-97`). It shows the *configured* model name, not the model actually served (`agent_orchestrator.py:185`).

**3. Agent activity, after**
```
┌ Activity · task t_7f2 · tier gpu_high ─────────────── 38.4 s ─ ⏸ ✕ ┐
│ 0s    5s    10s   15s   20s   25s   30s   35s                       │
│ ▇▇ classify (deterministic)                                         │
│   ▇▇▇▇▇ extract×3 (pdf_text/RapidOCR)  ▇▇▇▇▇▇ asr (faster-whisper)   │
│        ▇▇▇▇ entities  qwen3-4b · 1.2s TTFT · schema ✔                │
│             ▇▇▇▇▇▇ vision qwen3-vl-8b ║ ▇▇▇▇▇ data_analysis coder-7b │
│                    ▇▇▇ correlation → CORROBORATES 0.86               │
│                       ▇▇▇▇▇ draft qwen3-8b ✖Critic ─▶ qwen3-32b ✔    │
│                                  ▇▇ critic gemma-3-12b PASS           │
│ Escalations: 1 (draft: 2 UNSUPPORTED claims) · Retries: 0 · Tokens 9.1k│
└───────────────────────────────────────────────────────────────────────┘
```

**4. Approval, before.** Doesn't exist. No interrupt or approval state anywhere (`agent_orchestrator.py`).

**4. Approval, after**
```
┌ ⚠ Approval required ──────────────────────────────────────────────┐
│ Action: write_docx → artifacts/RCA_P-104_v1.docx (new, 6 pages)    │
│ Why: factual deliverable · 2 claims inferred · requested by doc     │
│ Evidence: 9 refs (7 observed, 2 inferred)      [Preview ▸] [Diff ▸] │
│ Approver policy: pending (plan §12.4)                               │
│                    [Deny (D)]  [Edit & approve]  [Approve (A)]      │
└─────────────────────────────────────────────────────────────────────┘
```

**5. Admin, before.** The only "admin" view is the Prompt Inspector. Anyone can open it from Settings, and it exposes every trace with no access check (`PromptInspectorModal.jsx:179`, `main.py:298-304`).

**5. Admin, after** (ADMIN only)
```
┌ Admin ─ [Audit] [Metrics] [Models] [Hardware] [Agents] [Prompts] ─────┐
│ Hardware: tier gpu_high (RTX-class 24 GB) · override: none            │
│ VRAM ███████████████░░░░░ 15.8/24 GB  qwen3-8b 5.6 · bge-m3 1.2 · …   │
│ Models   name            status   p50 TTFT  tok/s  ver      circuit    │
│          qwen3-8b-q4     ● ok     410 ms    48     sha:9c1… closed    │
│          qwen3-vl-8b     ○ cold   —         —      sha:41a… closed    │
│          gemma-3-12b     ▲ slow   2.1 s     19     sha:77e… half-open │
│ Audit    [workspace ▾][event ▾][failure ▾][from–to]   Export JSONL|CEF │
│          12:04 SECURITY_CHECK GATEWAY_REJECTED ws=B user=u17 …        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4.2 New features, ranked by value against effort

**Scales.** Value runs 1–5: user impact for regulated enterprises. Effort runs S (≤3 days), M (≤2 weeks), L (≤6 weeks), XL (>6 weeks). Rank is value ÷ effort, adjusted for dependencies.

| Rank | Feature | Value | Effort | Depends on | Plan phase | Notes |
|---|---|---|---|---|---|---|
| 1 | Multi-turn workspaces (persistent conversations, files and decisions scoped to a workspace) | 5 | M | workspace_id everywhere (0.4), SQLite (ADR), Memory (3.6) | 1.11 → 3.6 | Today the client re-sends the last 6 turns (`model_service.py:162`) and there is no workspace |
| 2 | OCR for scans and handwriting | 5 | S–M | EvidenceUnit (0.4), extractor 1.3 | 1.3 | RapidOCR already exists (`visual_rag_service.py:114-125`). Wire it in properly and tag low-confidence text `uncertain`. Handwriting needs the VLM fallback (quality must be measured) |
| 3 | Feedback loops (👍/👎 + note) | 4 | S | `/tasks/{id}/feedback`, audit | 1.12 | Feeds eval and Optimization |
| 4 | Report, xlsx and pptx generation with citations | 5 | M | Critic gate (1.10), tool registry, `write_*` (1.9) | 1.9 | python-docx is already installed; openpyxl too; python-pptx needs an ADR |
| 5 | Templates and SOP-driven workflows | 5 | M | planner templates, kits (4.3) | 1.10 → 3 | e.g. RCA, shift handover, SOP compliance |
| 6 | Cross-document correlation ("does the spreadsheet match the PDF?") | 5 | L | EvidenceUnit, entity resolution (3.2), graph (3.1) | 3.4 | Must pass the negative control (§11.9) |
| 7 | Document comparison and diff | 4 | M | EvidenceUnit structure, artifact versions | 1.9 → 3 | Text diff plus table-cell diff plus clause alignment |
| 8 | Evaluation dashboard | 4 | M | eval harness (0.6, 3.11) | 3.11 | Reuses `bench/` |
| 9 | Admin console (models, agents, prompts, permissions) | 4 | L | registry, `agents.yaml`, RBAC (3.10) | 3 → 4 | Read-only first. Edits go through the proposals queue |
| 10 | Notifications (in-app, then email or intranet) | 3 | S–M | background jobs (§7.14) | 3 | In-app first; email needs a connector |
| 11 | Voice input (local ASR) | 3 | M | ASR extractor 3.8 | 3.8 / 4.5 | Replaces Web Speech egress. Voice *output* is open question §12.5 |
| 12 | Scheduled and recurring tasks | 3 | M | job queue (ADR), approvals | 3 → 5 | e.g. daily shift-handover digest |
| 13 | Natural-language-to-SQL connector | 4 | L | connector interface §7.13, sandbox, read-only DB role | 3.9 | Allowlisted schemas, read-only, results cited by query hash |
| 14 | Email, wiki or ticketing connector | 4 | L | §7.13, IdP (§12.1), first-connector decision (§12.10) | 3.9 | **USER DECISION**: which connector |
| 15 | Sharing and collaboration | 3 | L | RBAC with a real IdP (3.10) | 4 | Blocked until the IdP is decided |
| 16 | Plugin SDK for tools and connectors | 3 | XL | stable ToolSpec and connector ABC, signing | 5 | Plan §3.6 warns against premature plugin systems. Build only once two or more third-party tools are requested |

---

## 4.3 Make it better for industries

**What every vertical shares**
- Workspace partitioning.
- Classification levels (§12.8).
- An append-only audit trail with a CEF export for the SIEM.
- Zero egress (no outbound traffic).
- Evidence-tagged answers.
- Approval-gated writes.

| Vertical | Concrete use cases | Data types / connectors | Compliance & regulation | Domain agents / tools |
|---|---|---|---|---|
| **Manufacturing & process plants** (refineries, power, oil & gas) | Maintenance-log Q&A; **equipment entity resolution** ("Pump 104" = "P-104" = "P104-A"); P&ID diagram understanding (tags, line numbers, valve states); incident & **RCA** drafting (5-Whys, fishbone); **shift handover summaries**; SOP and permit-to-work compliance checks; MOC (management-of-change) impact search | PDFs (scanned inspection reports), P&ID PDF/TIFF/DWG exports, CMMS/EAM exports (SAP PM, Maximo) as CSV/XLSX, historian time-series (PI/OSIsoft) CSV, shift logs, audio notes from the field | **IEC 62443** (OT zone/conduit separation: the platform sits in the IT/DMZ zone, read-only OT data via a data diode/export), ISO 27001, OISD/PNGRB (India), OSHA PSM 1910.119 (US), data residency | `equipment_resolver` (tag grammar per site + §8.4 resolver), `pid_tag_extractor` (OCR + VLM + tag regex, every tag `uncertain` until confirmed), `rca_template` (Execution), `handover_summarizer`, `sop_checker` (step-by-step conformance with evidence per step), time-series anomaly tool (sandboxed pandas) |
| **Defence & PSUs** | Technical-manual Q&A (AeroMind's current domain); MRO procedures; tender/RFP analysis; spares and logistics reconciliation; lessons-learned search | Manuals (PDF), illustrated parts catalogues, maintenance records, tender documents, inventory XLSX | Air-gapped by default, national classification schemes (**USER DECISION** §12.8), ISO 27001, CERT-In guidance (India), DPDP for personnel data, data residency, supply-chain integrity (signed model weights) | `procedure_extractor` (numbered steps + WARNING/CAUTION preserved as structured blocks, not detected by regex as today, `MessageBubble.jsx:132-147`), deterministic `units_calculator` (the existing `AvionicsMathEngine`, fixed to never invent defaults), `tender_clause_extractor`, `parts_crossref` (P/N entity resolution) |
| **Government** | File noting / note-sheet drafting; RTI response drafting with citations; policy and circular comparison; grievance triage; multilingual citizen correspondence | Scanned files (OCR, Indic scripts), circulars/gazettes (PDF), e-Office exports, email | DPDP Act 2023, MeitY cloud/data-localisation guidance, ISO 27001, records-retention rules (§12.13), accessibility (GIGW / WCAG) | `noting_drafter`, `circular_diff` (document diff, 4.2 #7), translation via IndicTrans2 (ADR), deterministic `pii_redactor` before any summary leaves a workspace |
| **BFSI** | KYC/credit-file review; policy/claims document analysis; regulatory-circular impact (RBI/SEBI/IRDAI); audit-ready evidence packs; reconciliation (statement vs ledger) | PDFs/scans, XLSX/CSV ledgers, core-banking SQL (read-only), email | SOC 2, ISO 27001, PCI DSS (if card data is present; keep it out of scope by design), RBI IT/outsourcing directions, DPDP/GDPR, model-risk governance (documented eval + versioning, plan §8.14) | `reconciler` (cross-document correlation with numeric match, §8.11), NL→SQL (read-only role), `circular_impact_mapper`, `pii_redactor`, `evidence_pack_exporter` (zip of cited sources + audit trail hash) |
| **Healthcare & pharma** | SOP/GMP deviation investigations (CAPA); batch-record review; clinical-protocol Q&A; pharmacovigilance case triage; regulatory submission cross-checks | Batch records (scanned), SOPs, LIMS/QMS exports, CSV assay data, de-identified clinical text | **HIPAA** (PHI), 21 CFR Part 11 (electronic records, audit trail, e-signatures on approvals), EU GMP Annex 11, GDPR/DPDP, ISO 27001 | `deviation_rca` (shares the RCA template), `batch_record_checker` (step/limit conformance), `phi_detector` (deterministic first), Part 11 e-signature on approval gate (needs IdP, §12.1) |
| **Legal** | Contract and tender analysis (obligations, renewal dates, liability caps); clause comparison against a playbook; due-diligence data rooms; citation-checked memo drafting | DOCX/PDF contracts, scanned agreements, email threads | Privilege/confidentiality (strict workspace isolation, ethical walls = workspace ACLs), GDPR/DPDP, ISO 27001, retention/legal hold (§12.13) | `clause_extractor` → structured obligations table, `playbook_diff`, `redline_drafter` (write tool, approval-gated), `date_obligation_calendar` |
| **Logistics** | Shipment exception analysis; invoice vs PO vs delivery-note three-way match; carrier contract Q&A; incident reports | CSV/XLSX manifests, scanned delivery notes, EDI exports, email | ISO 27001, SOC 2, customs data rules, DPDP/GDPR | `three_way_matcher` (correlation + numeric tolerance), `manifest_analyzer` (sandboxed pandas), document OCR |

### 4.3.1 Air-gapped deployment packaging
The plan requires local-ready code from day one and an offline transfer procedure (§8.19, §14). The procedure itself is open question §12.11, a **USER DECISION**.

Each release produces a `release/aeromind-<ver>-<tier>.tar` bundle built on a connected build host:

| Component | Contents | Integrity |
|---|---|---|
| `wheelhouse/` | `pip download -r requirements.lock --platform …` for every Python dependency (pinned, hash-checked: `--require-hashes`) | per-wheel sha256 in `requirements.lock` |
| `npm-cache/` or prebuilt `frontend/dist/` | the built SPA (the dev server is not needed offline), fonts self-hosted | sha256 in the manifest |
| `images/` | `docker save` of api, worker, qdrant, ollama (or vllm), postgres (later) at **pinned tags** (pitfall §11.20) | image digest list |
| `models/` | Ollama blobs (`~/.ollama/models/blobs/sha256-*`) + manifests for the tier's models; HF safetensors for the fine-tuned Mistral (`backend/models/`) and embedder/reranker | `MODELS.sha256` + recorded in `config/models.yaml` `version:` |
| `config/` | `models.yaml`, `agents.yaml`, `hardware_profiles.yaml`, `thresholds.yaml`, `deploy/zero_egress.env` | in the manifest |
| `MANIFEST.json` + `MANIFEST.json.sig` | file list, sizes, sha256, build commit, SBOM (CycloneDX) | signed with an offline release key (cosign or minisign; **ADR**) |
| `install.sh` | verify signature → verify every hash → `docker load` → place blobs → `docker compose up` on an `internal: true` network with a separate ingress network (plan §14.1, pitfall §11.20) | refuses to install on any mismatch |
| `verify.sh` | re-hash installed models and images, run the no-egress self-test (socket guard + attempted outbound connections must fail), print the hardware tier | the output is the install record |

The installer **rejects** `*:cloud` Ollama tags and any `local:` registry entry pointing at a non-loopback or non-allowlisted host. These are real egress paths on this machine today: `glm-5.1:cloud` and `kimi-k2.5:cloud` show up in `ollama list`.

### 4.3.2 Per-industry starter kits
```
kits/
  aviation_mro/          # kit #1 — preserves AeroMind's current domain
    prompts/             # versioned YAML (plan §8.7), e.g. procedure_answer.yaml
    templates/           # docx/xlsx templates: task card, defect report
    fixtures/            # synthetic/sanitised only: manual excerpt, scanned task card,
                         #   parts CSV, audio defect note; + ground_truth.json
    eval/                # gold Q&A (verified:true, source_page set), negative controls
    kit.yaml             # starter prompts for the chat empty state, entity grammars,
                         #   enabled tools, default classification
  process_plant/  defence_psu/  government/  bfsi/  healthcare_pharma/  legal/  logistics/
```

**Aviation MRO kit**
- It absorbs today's hardcoded domain content:
  - the fighter-specific prompt branch (`model_service.py:159,182-191`)
  - the suggested questions (`ChatPanel.jsx:92-97`)
  - `AIRCRAFT_REGISTRY` (`pdf_service.py:19-32`)
  - the math engine's aviation formulas (`agent_orchestrator.py:31-143`)
  - the domain DAG templates (`orchestrator_planner.py:18-134`)
- Nothing is deleted. It is moved behind `kit.yaml` once the user agrees to generalise (conflict C2).
- **Licence warning.** `mig21bis.pdf` is byte-identical to "DCS MiG-21bis Guide.pdf", which is probably a third-party game manual. It must not ship in a kit until its licence is confirmed (**USER DECISION**).
- `bench/gold.jsonl` (50 questions, all `verified:false`) is the seed for `kits/aviation_mro/eval/` after human verification.

---

## 4.4 Multi-SLM subagent architecture (executive summary)

**The full design is in [MULTI-SLM-ARCHITECTURE.md](MULTI-SLM-ARCHITECTURE.md).** It covers the registry schema, task decomposition, routing, cascade, scheduling, contracts, failover, the worked RCA example and observability.

**In one paragraph**
- **Decomposition.** The Main Agent (a LangGraph planner node; ADR-0003) turns a task into a persisted DAG of `SubTask`s. Each subtask declares a required capability tag, Pydantic input and output schemas, `depends_on`, a retry budget and a maximum model tier.
- **Routing.** The router (`config/models.yaml`, extended under ADR-0005) works through these filters in order:
  1. capability match
  2. endpoint health and circuit-breaker state
  3. VRAM or RAM fit on the **detected hardware tier** (ADR-0007)
  4. `rank`, which places the smallest model first

  Quality and latency are used as tiebreakers only after the eval harness and bench have measured them (plan §8.2).
- **Cascade.** Each subtask runs on the smallest capable SLM first. It escalates one tier only when schema validation fails, the Critic returns FAIL or NEEDS_REVISION, or confidence is below a configured threshold. Escalation is limited by `escalation.max_hops`, and every hop is audited as `MODEL_ESCALATION`.
- **Parallelism.** Independent subtasks run concurrently under a VRAM-weighted semaphore. Hot models (planner, embedder, reranker) stay pinned with Ollama `keep_alive`; the rest are cold and swapped in.
- **Contract and verification.** Results move as `AgentMessage`s with `evidence_refs` and a confidence value. A cross-family Critic verifies each subtask and then the final synthesis.

**Agent ↔ SLM mapping.** Every name is a **candidate**: confirm it with the eval harness and a licence review before adopting it. The dev-laptop column was **verified installed** this session. The 24 GB column is an **assumption**, because there is no GPU on this machine to test it.

| Agent / capability | Dev laptop (CPU, installed) | 24 GB GPU MVP | Multi-GPU production |
|---|---|---|---|
| Main, planning/drafting | qwen3:4b-instruct-2507 (candidate) | Qwen3-8B Q4 (candidate) | Qwen3-32B AWQ on vLLM (candidate) |
| Coding | qwen2.5-coder:1.5b (candidate) | Qwen2.5-Coder-7B (candidate) | Qwen3-Coder-30B-A3B (candidate) |
| Retrieval | nomic-embed-text (candidate) | **bge-m3 everywhere** + bge-reranker-v2-m3 (candidates). bge-m3 is multilingual, including Indic, and avoids re-ingestion; see §12.7 | same as MVP |
| Data analysis | coder model + pandas sandbox; SQL via the coder model (candidate) | same pattern | same pattern |
| Multimodal | qwen3-vl:2b + RapidOCR + faster-whisper small (candidates) | Qwen3-VL-8B + RapidOCR/PaddleOCR + faster-whisper large-v3-turbo (candidates) | Qwen2.5-VL-32B/72B-class (candidate) |
| Critic (different family from the producer) | gemma4:e4b, slow (candidate) | Gemma-3-12B Q4 (candidate) | Gemma-3-27B / Mistral-Small-24B (candidates) |
| Correlation | — | planner model + embeddings + deterministic resolver | same pattern |
| Memory | deterministic | deterministic | deterministic |
| Optimization | — | the largest local model, offline batch | the largest local model, offline batch |
| Classification | deterministic → qwen3 1.7B (candidate) | deterministic → qwen3 1.7B (candidate) | deterministic → qwen3 1.7B (candidate) |
| Translation | — | IndicTrans2 (candidate; ADR) | IndicTrans2 (candidate; ADR) |

**Hardware tiers.** The tier is detected at backend startup by `backend/router/hardware_probe.py` and can be overridden with `AEROMIND_HW_TIER` (ADR-0007). Every model listed is a **candidate**.

| Tier | Detected when | Agents enabled | Parallel LLM calls / plan depth | Models (candidates) |
|---|---|---|---|---|
| `cpu_lite` | x86, no CUDA/ROCm/Metal (this i7 / Iris Xe box) | Main (planner and drafter share one model), Retrieval, Data Analysis (deterministic math/pandas first), Multimodal limited to OCR (VL only when the user asks), Critic, Memory. Off: Correlation, Optimization, ColPali, video | 1 / 3 | qwen3:4b-instruct-2507, qwen2.5-coder:1.5b, qwen3-vl:2b (lazy), qwen2.5:3b as critic. All already installed |
| `gpu_standard` | NVIDIA/AMD with 8–16 GB | everything above + Coding + VL on by default | 2 / 5 | Qwen3-8B Q4, Qwen2.5-Coder-7B, Qwen3-VL-4B/8B, Gemma-3-12B critic (swapped in cold) |
| `gpu_high` | one GPU ≥ 24 GB | the full plan roster + Correlation + ColPali | 3 / 6 | the "24 GB MVP" column |
| `gpu_multi` | two or more GPUs, or server class | full roster + Optimization, vLLM per GPU | VRAM-scheduled / 6 | the "production" column |
| `apple_full` | Apple Silicon (Metal; ColPali on `mps`) | full roster, full-quality mode | 3 / 6 | Qwen3-32B Q4 or 14B (by memory), Qwen3-VL-8B, Qwen2.5-Coder-14B, Gemma-3-27B critic |

**Tier invariants (each one tested)**
1. Tiers never turn off safety: the deterministic Critic, permissions, audit and the egress guard always run.
2. The **embedding model is the same in every tier**, so an index built on one device can be used on another.
3. Every tier either covers each enabled agent's capability or reports it as `pending_capabilities`.
4. There are no `if tier ==` branches in agent code.

**USER DECISION.** For Macs, the recommendation is that "full quality" scales model *size* by unified memory: ≥48 GB → 32B-class, 24–36 GB → 14B-class, ≤16 GB → 8B-class with a visible warning.

---

## 4.5 And much more

### 4.5.1 Performance
- **Remove double generation.** Today `client.post` runs a full non-streamed generation *before* the streamed call, purely to detect a 404 (`model_service.py:380-396`). That roughly doubles every LLM call. The fix is to check existence once through `/api/show` (cached) and then make only the streamed call.
- **Context window.** Use the registry's `max_context` instead of the hardcoded `num_ctx: 2048` (`model_service.py:373`), which silently truncates the up to 9,000 characters of context assembled at `agent_orchestrator.py:356`.
- **Token budget enforced in code** (plan §8.6) with the served model's tokenizer, replacing `[:3000]` character slices.
- **Embedding cache** keyed by `sha256(text)+embedder_version`. **Page-render cache** keyed by `sha256(file)+page+dpi`; today's cache is keyed by doc_id only, so re-uploading under the same stem serves stale images (`visual_rag_service.py:37-55`).
- **Open the PDF once per request.** Stop reopening it per page in the synthesis loop (`agent_orchestrator.py:346-354`).
- **Streaming.** Use typed SSE frames (`event: token|agent_activity|citation|eval|error|done`) with JSON `data:`, replacing in-band string tags that need fragile parsing (`useChat.js:95-257`) and can be spoofed by model output. Send heartbeat comments every 15 s.
- **Cold start.**
  - At lifespan: hardware probe, then warm up the tier's hot models (a 1-token generation each) and the embedder.
  - Report `ready` only after warm-up.
  - Move the `mig21bis` full-document indexing at startup (`main.py:42-46`) to a background job with progress.
- **Ollama tuning per tier:** `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_KEEP_ALIVE`. Replace `num_thread: 8` with physical cores (`model_service.py:372`); this laptop has 8 logical / 4 physical.

### 4.5.2 Security hardening (beyond the plan's threat model, §8.13)
- **Fix now** (quick wins):
  - Upload path traversal: the client filename is joined directly onto the destination (`universal_ingestion_service.py:99-105`, `main.py:172`). Replace it with server-generated ids and a realpath allowlist (pitfall §11.16).
  - Limits: maximum upload size, maximum zip depth, file count and expanded bytes (zip-bomb guard). `_process_zip` recurses with no bound (`ingestion_adapter.py:253-264`).
  - MIME sniffing that rejects polyglots.
  - Escape text before reportlab `Paragraph`: DOCX text is passed in as markup (`ingestion_adapter.py:366`).
- **HTTP**
  - Strict CORS allowlist, replacing `*` with credentials (`main.py:59-65`).
  - A CSP of `default-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'`.
  - `X-Content-Type-Options`, `Referrer-Policy: no-referrer`.
- **Markdown rendering.** Override `img` and `a` in `MessageBubble.jsx`'s `markdownComponents` so only same-origin or `data:` images load and links are allowlisted. Today `![](https://…)` in model output loads arbitrary outside URLs, which is an exfiltration path through injected document text.
- **Egress, in depth**
  - A socket guard in tests (plan §10.2).
  - Docker `internal: true`.
  - Registry validation that rejects `:cloud` tags and non-allowlisted hosts.
  - LangSmith disabled under the local profile (ADR-0006). Today `langsmith_service.py:89-98` uploads query and response whenever a key is set.
  - Fonts self-hosted.
  - Web Speech replaced with local ASR.
  - `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` in `deploy/zero_egress.env`. Note that `model_service.py:118-144` and `colpali_retrieval_service.py:124` would otherwise download.
- **Supply chain**
  - Pinned and hash-locked requirements (the current file is mostly `>=`, `backend/requirements.txt:8-28`).
  - npm `package-lock.json` respected via `npm ci`.
  - A CycloneDX SBOM.
  - A signed release manifest.
  - Model weight hashes checked at load, not only at install.
- **Secrets.** Keep `.env` out of git: `backend/.env` is tracked today (its values are currently empty). Use `.env.example` only, and later a Vault-class store (plan §8.13).
- **Data hygiene.** Uploaded files that look personal, plus Qdrant DBs and traces, are committed in git (`backend/data_repository/uploads/`). Untrack them and decide whether to rewrite history (**USER DECISION**).
- **Model-output trust.** Treat the model's output as untrusted for any `tool_call` argument (Pydantic validation, allowlisted paths). Rate-limit approvals to prevent click-through fatigue.
- **Trace privacy.** `/api/prompts/inspect` exposes every user's queries with no authentication (`main.py:298-304`). Restrict it to ADMIN plus workspace scope, and store hashes in audit `details` (plan §7.8).

### 4.5.3 Observability (OpenTelemetry)
- **Instrumentation** (ADR-0006). Use `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi` + `-httpx`.
- **Span tree.** `task` → `node:<graph node>` → `agent:<name>` → `model_call` / `tool_call`.
- **Span attributes:**
  - `workspace_id`, `task_id`
  - `capability`, `model.name`, `model.version`
  - `hw.tier`
  - `tokens.in` / `tokens.out`, `ttft_ms`
  - `escalated`, `critic.verdict`
- **Export** goes over OTLP to a **local** collector only. A Jaeger or Tempo plus Prometheus plus Grafana stack ships in the air-gap bundle, and there is no SaaS exporter in the production build ("exclude, don't disable", plan §2).
- **AuditEvent (§7.8) stays the legal record.** OTel is for operations. Audit is append-only, while OTel can be sampled.

### 4.5.4 Developer experience
- **One environment.** Today `backend/venv` cannot run the app, because it lacks qdrant_client, colpali_engine, reportlab and pytest, while system Python has everything. Settle on a single locked environment.
  - Recommended: `uv` with `uv.lock`. Alternative: pip-tools `requirements.lock`. **ADR.**
- **One command to start:**
  - `make dev` runs `uv sync && npm ci && ollama pull <tier models> && uvicorn … & vite`.
  - `docker compose -f deploy/docker-compose.dev.yml up` for the containerised path.
- **Seed data.** `make seed` loads `kits/aviation_mro/fixtures` into a `demo` workspace. Tests must stop writing into the tracked `backend/data_repository/` (today `test_ingestion_adapter.py:17,35,49` do), and use `tmp_path` fixtures instead.
- **Typed SDK.** FastAPI's OpenAPI → `openapi-typescript` → `frontend/src/api/types.ts` plus a thin fetch client. Pydantic models on every route; today `/api/documents/upload` returns untyped dicts.
- **Linting.** `ruff` (Python) and `eslint` + `eslint-plugin-jsx-a11y` + `prettier` (frontend). Add `vitest` for hooks such as `useChat` stream parsing, and Playwright for 5 E2E flows. These are dev-only dependencies, still recorded in an ADR.
- **CI gates**, required on every PR:
  1. `pytest tests/unit tests/integration`
  2. `tests/adversarial`, including `test_no_egress.py` (socket guard), prompt injection, privilege escalation and memory scoping (plan §10.2)
  3. a wiring test asserting that every subsystem is invoked on a representative task (pitfall §11.6)
  4. a registry validator: `hf` capabilities ⊆ `local`, no `:cloud`, every tier covers every enabled agent
  5. a frontend build plus axe
  6. an eval regression gate: no metric drops by more than X versus `main`
- **Benchmark fixes.** Repoint `bench/b4_router_accuracy.py` at the real router; today it tests a stale regex copy (`b4_router_accuracy.py:44-78,130`). B10 must not hardcode `air_gapped: True` (`b10_sovereignty.py:176`), and its secret-preview field must be removed (`:85`).

### 4.5.5 Evaluation harness and regression tracking
- **Layout.** `eval/fixtures/<kit>/…` with `ground_truth.json` (plan 0.6), plus `eval/harness.py` running fixtures through the **real graph** with `WORKBENCH_ENV` and `AEROMIND_HW_TIER` set.
- **Metrics** (plan §10.4):
  - task completion
  - % of claims with valid evidence
  - routing accuracy (against the real router)
  - recovery rate under fault injection
  - TTFT and end-to-end p50/p95
  - correlation precision and recall, including negative controls
  - follow-up proposal relevance
  - and, new here: **per-model, per-capability quality**, which is what fills `quality:` in `models.yaml` (MULTI-SLM-ARCHITECTURE.md)
- **Tracking.** Results go to `eval/results/<date>_<commit>_<tier>.json`, plus a markdown diff against the last `main` run posted in CI and an evaluation dashboard (4.2 #8).
- **Replace the fake scorecard.** The heuristic in `evaluation_service.py` floors faithfulness at 78 (`:50`) and marks non-emergency answers `VERIFIED_SAFE` (`:70`). It must either be relabelled "heuristic, unverified" or replaced by Critic output. It must never display invented defaults; the frontend currently uses 85/95 when a score is missing (`EvaluationScorecard.jsx:17-18`).

### 4.5.6 Cost and hardware sizing
**Measured on this laptop** (B1, CPU-only, `bench/results/b1_per_model_AS_IS.json`):

| Model | Cold load (median) | Warm TTFT | Generation | Ollama RSS | 200-token answer |
|---|---|---|---|---|---|
| qwen2.5:3b | 2.08 s | 0.55 s | **9.11 tok/s** | 2.2 GB | ~29 s total (median) |
| gemma4:e4b | 5.19 s | 0.67 s | **5.06 tok/s** | 10.3 GB | ~49 s total (median) |

**What this implies on `cpu_lite`**
- A plan with 3 sequential LLM calls (plan, draft, critic) at 300–500 output tokens takes **1.5–3 minutes**. Today's code doubles that through the double-generation bug.
- Hence: parallelism of 1, deterministic-first steps, the smallest models, and long tasks sent to the background with visible progress (plan §1.4 latency NFR).
- Open question §12.9, the latency ceiling, decides whether `cpu_lite` is acceptable for anything beyond demos.

**Sizing arithmetic for the other tiers**

These are **estimates** and must be re-measured per plan 2.4 and 4.3.
- **VRAM per model** ≈ params × bits/8 × 1.2, plus the KV cache. The KV cache ≈ 2 × layers × kv_heads × head_dim × ctx × 2 bytes.
  - Qwen3-8B at Q4 ≈ 5–6 GB, plus ~1–2 GB KV at 16k context.
- **24 GB tier**, hot set: planner 8B (~6 GB) + bge-m3 (~1.2 GB) + reranker (~1.1 GB) ≈ 8.5 GB. That leaves ~13 GB for one cold model at a time: VL-8B (~6–7 GB) *or* Gemma-3-12B critic (~8 GB) *or* Coder-7B (~5 GB).
  - Expect roughly 40–80 tok/s for 8B Q4 on a 24 GB consumer GPU. This is **unmeasured**.
- **Production.** Size from measured concurrent load (plan 5.1). The plan says not to procure hardware before MVP usage data (§8.19, §12.6).
- **Cost model.** CapEx (GPU hosts) + power + ops FTE, compared with the shadow-AI risk (plan §1.1). The eval dashboard reports tokens and GPU-seconds per task type, giving a cost per task.

### 4.5.7 Optimization Agent (human-reviewed self-improvement)
- **Schedule.** Weekly batch (plan 5.2).
- **Reads:** the audit log, eval results, feedback, escalation stats and Critic failure reasons.
- **Writes only** to `proposals` (a table plus a UI queue). Each proposal is a **diff** against `config/*.yaml` or `config/prompts/*.yaml`, with:
  - its evidence (metrics before, expected effect)
  - a risk note
  - an auto-generated eval run on a shadow config
- **Examples:**
  - "Raise `escalation.min_confidence` for `extraction` from 0.6 to 0.7: 14% of Critic FAILs were low-confidence extractions that passed schema."
  - "Promote qwen3-vl-8b over qwen2.5-vl-7b for `vision`: +6 pts on the fixture set, −20% latency."
  - "Lower the continuation threshold: 41% 👎 on proposals."
- **Review.** An ADMIN accepts or rejects in the UI. Accepting creates a versioned config commit. A test proves no proposal bypasses the queue (plan 5.2 acceptance).

### 4.5.8 Additional ideas
1. **Honest UI until the work is real.** Until the Critic is wired in, show every answer as "Unverified" and every heuristic score as "heuristic". Today the UI shows "VERIFIED_SAFE", "RAG INDEXED" and a "Flight Safety & SOP Protocol Validator" that never runs (`agent_orchestrator.py:406-427`, `UniversalDocumentManager.jsx:234-236`). Showing false assurance in a safety domain is the single biggest trust risk in the product today.
2. **Deterministic tools refuse rather than guess.** The math engine must return "insufficient inputs: fuel quantity, burn rate" instead of using defaults (2800 kg, 58 kg/min; `agent_orchestrator.py:92-98`). This is a general rule for every calculator tool in every kit.
3. **Provenance-first page viewer.** Every citation deep-links to a bounding box, using `PageSectionLocation.bounding_box` from §7.5 and PyMuPDF's `search_for` to highlight the quoted span.
4. **Fixture-first development.** Write the positive *and* negative fixture before each agent or tool (plan §11.9/10). `bench/gold.jsonl` becomes verified ground truth with `source_page` filled in.
5. **Hardware-tier simulation in CI.** Run the integration suite under `AEROMIND_HW_TIER=cpu_lite` and `gpu_high` (with mocked endpoints) so that capability coverage and degradation messages are tested for every tier.
6. **Repository hygiene as a first-class task.** Untrack the ~9,959 `node_modules` files, `dist`, `__pycache__`, `.env`, the Qdrant DB, traces and uploads, and extend `.gitignore`. Today's clones are large, and they carry personal data.
7. **Model "probation".** A newly onboarded model serves 0% of traffic and runs in shadow mode against the eval set plus a 5% replay of real (permitted) tasks. It is promoted only by human approval through the model-refresh process (plan 5.5).
8. **Per-workspace "data passport".** A one-page export listing what was ingested, its classification, who accessed it, and which models touched it. This supports DPDP/GDPR access requests and audits.

---

## 4.6 Prioritized roadmap

**Effort scale.** S ≈ 1–3 days, M ≈ 1–2 weeks, L ≈ 3–6 weeks. These are single-engineer estimates and are not yet validated.

**Approval rule.** Every row needs the user's go-ahead at its stage checkpoint (plan §3.3). The "ADR / decision" column flags the extra approvals required.

### Stage A: Quick wins (after Stage 4 approval; each is small and wraps the existing code rather than rewriting it)

| ID | Item | Effort | Depends on | Risks | Acceptance criteria | ADR / decision? |
|---|---|---|---|---|---|---|
| QW1 | Fail-closed model resolution: no silent fallback (`model_service.py:385-390`); typed `error` SSE event; missing model reported as `MODEL_FAILURE` | S | — | Users see more errors at first. That is correct behaviour | Test: configured model absent → `error` event naming the model; no tokens from another model; response never marked verified | No (implements plan §11.5) |
| QW2 | Remove the double generation in the Ollama path (`model_service.py:380-396`); use `num_ctx` from config | S | — | Behaviour change for 404 detection | Test with a mocked Ollama: exactly 1 `/api/generate` call per stream; B1 rerun shows ~½ wall time for the same prompt | No |
| QW3 | Upload hardening: server-generated names + realpath allowlist, size limit, zip depth/count/bytes limits, reportlab escaping | S | — | May reject some legitimate large files (configurable) | Red-team tests: `../` filename, absolute path, nested zip bomb, symlinked member → rejected; legitimate fixtures still ingest | No (plan §11.16) |
| QW4 | Honest scorecard/verifier labelling: remove the floors (`evaluation_service.py:50`), drop "VERIFIED_SAFE", stop the frontend inventing defaults (`EvaluationScorecard.jsx:17-18`), rename the validator status to "not yet verified" | S | — | Scores look worse | Test: empty response → no score above 0 for faithfulness; UI shows "Unverified" | **USER DECISION** (visible product change) |
| QW5 | Math engine refuses rather than guessing; unit-aware parsing ("5 minutes" ≠ 5 m) | S | — | Fewer "answers" | Tests: queries without inputs → "insufficient inputs"; existing 3 math tests still pass | No |
| QW6 | Real text embeddings via the router `embedding` capability (`nomic-embed-text` installed; bge-m3 pending), deterministic ids; ColPali opt-in only | M | QW7, ADR-0004 | **Expensive to reverse** (re-ingestion) | Same query across 3 processes → identical top-k (today it differs every time); known-answer fixture in top-3 | **ADR-0004 + USER DECISION §12.7** |
| QW7 | One locked Python environment (`uv` or pip-tools), `pytest.ini`, `pytest-asyncio`, tests use `tmp_path` | S | — | Version drift reveals breakage | Baseline rerun recorded: same 8 pass; the async test runs (it may still fail honestly on Ollama); no writes to tracked paths | **ADR** (lockfile tool) |
| QW8 | Repo hygiene: untrack node_modules, dist, pycache, `.env`, data_repository, uploads; extend `.gitignore` | S | user decision | History still contains the files unless rewritten | `git ls-files` count drops from 10,167 to ≈200; app still runs from a fresh clone + `make seed` | **USER DECISION** (history rewrite? personal PDFs? DCS licence) |
| QW9 | Zero-egress basics: LangSmith off under local, self-hosted fonts, Markdown img/link allowlist, CORS allowlist, CSP | S | — | Loses cloud traces in dev | `test_no_egress.py` socket guard passes for chat and ingest; no request to fonts.googleapis.com in a Playwright run | **ADR-0006 + USER DECISION C5** |
| QW10 | Frontend bugs: null-document send (`useChat.js:28`), voice teardown (`VoiceController.jsx:82`), stuck stream (`useChat.js:296`), inline code (`MessageBubble.jsx:164-172`), upload fields | S | — | — | vitest/Playwright: each bug reproduced before the fix and passing after | No |
| QW11 | Hardware probe + tier selection at startup (`backend/router/hardware_probe.py`, `config/hardware_profiles.yaml`); `AGENT_MODEL_MAP` becomes the `cpu_lite` fallback; `/api/health` reports the tier; UI `TierBadge` | S–M | QW1 | Wrong detection on unusual hardware → override env var | Unit tests on mocked probes (i7 with no GPU → `cpu_lite`; 24 GB NVIDIA → `gpu_high`; M3 Max 64 GB → `apple_full`; M1 8 GB → `apple_full` with an 8B-class warning); real run on this laptop reports `cpu_lite` | **ADR-0007 + USER DECISION** (Mac sizing, UI override) |

### Stage B: Phase 0, foundations (plan §9)

| ID | Item | Effort | Depends on | Risks | Acceptance criteria | ADR / decision? |
|---|---|---|---|---|---|---|
| 0.1 | Scope decisions: local-only vs dual profile; air-gap vs isolated network | S | user | Blocks Phase 2 | Recorded in ADR-0001 status | **USER DECISION C1, §12.2** |
| 0.2 | Requirements authority | S | — | — | ADR-0002 filed | ADR-0002 |
| 0.3 | Pinned installs + import check + `doc/installed-versions.txt` | S | QW7 | Dependency conflicts (torch/transformers majors drifted) | Import check passes; freeze recorded | — |
| 0.4 | Contracts §7.1–7.6, §7.8 in `backend/` packages (`router/`, `orchestration/`, `ingestion/evidence_unit.py`, `tools/registry.py`, `observability/audit.py`); `config/` at the **repo root** (a `backend/config/` package would shadow `backend/config.py`) | M | 0.3 | Load-bearing abstractions | Plan 0.4 tests: default resolution, separate code vs reasoning resolution, unknown capability raises, `local` ⊇ `hf`, EvidenceUnit `to_dict` round-trip, **no `:cloud`/non-loopback in `local`** | ADR-0005 (registry fields) |
| 0.4b | Hardware tiers wired into `ModelRouter(environment, hw_tier)` + per-tier `agents.yaml` | M | 0.4, QW11 | Config sprawl | Every tier resolves every enabled capability; disabled agents → `pending_capabilities`; no tier branches in agent code (grep test) | ADR-0007 |
| 0.5 | Minimal LangGraph graph (classify → coding \| draft→critic) + CLI; Docker sandbox | M | 0.4 | Docker is present here; the CPU model is slow | Plan 0.5 verbatim: prime-number task has `exit_code=0` from the sandbox; draft task passes Critic or is flagged | ADR-0003 (**USER DECISION C6**) |
| 0.6 | Fixture corpus v0 + ground truth (aviation MRO kit + process-plant sample) | M | — | Synthetic realism | `eval/fixtures/` + `ground_truth.json`; gold questions verified | — |
| 0.7 | Reclassify every risk in `doc/01-status/PROJECT_STATE.md` | S | 0.1–0.6 | — | Each risk is verified working / confirmed broken / unknown with a reason | — |

### Stage C: MVP (plan Phase 1) and UI foundation

| ID | Item | Effort | Depends on | Risks | Acceptance criteria | ADR / decision? |
|---|---|---|---|---|---|---|
| 1.1 | Qdrant workspace-payload collection (existing embedded client wrapped, not replaced) | S | 0.4, QW6 | Schema hard to reverse | Payload indexes; schema reviewed by the user before bulk ingest | ADR-0004 |
| 1.2–1.3 | Native PDF-text + scanned/OCR extractors → EvidenceUnit (the PDF-render path is kept for the viewer) | M | 0.4 | OCR quality | Plan 1.2/1.3 criteria on real fixtures | **USER DECISION C3** |
| 1.4–1.5 | Ingestion pipeline + `search_knowledge_base` (workspace + clearance filter) | M | 1.1–1.3 | Tenant holes (§11.3) | Workspace B never sees A, tested from the graph entry point | §12.8 classification levels |
| 1.6–1.9 | Multimodal, Retrieval, Data Analysis and Execution agents; versioned `write_docx` | L | 1.4 | VLM slow on `cpu_lite` | Plan 1.6–1.9 criteria; CSV answers cite row ranges (fixes the 15-row truncation) | python-pptx ADR if needed |
| 1.10 | Planner + **DAG dispatcher** + Critic + synthesis; cascade/escalation v0 (rank order, `max_hops=1`) | L | 1.6–1.9 | Over-decomposition | Node-trace tests for 4 scenarios; escalation audited; template output never PASSes | ADR (SubTask fields, MODEL_ESCALATION) |
| 1.11–1.12 | Session memory; audit events for every call | M | 1.10 | — | Plan criteria; trail reconstructable | SQLite ADR |
| UI-1 | Tokens, themes, `src/ui/` primitives, typed SSE client, citations, approval card, upload progress | L | QW9, QW10, 1.10 (events) | Radix dependency | axe: zero AA violations on 5 screens; Lighthouse a11y ≥ 95 | **ADR** (Radix, i18next, fontsource) |

### Stage D: V1 (plan Phases 2–3)

| ID | Item | Effort | Depends on | Risks | Acceptance criteria | ADR / decision? |
|---|---|---|---|---|---|---|
| 2.1–2.4 | Local parity per tier: hashes, fixture diff, tool-calling parity, latency per tier | M | Stage C | Quantization regressions | Diff table per tier; p50/p95 recorded (dev-labelled) | Quality trade-off: **USER** |
| 2.5 | Firewall plus a no-egress CI check | S | 0.1 | — | Socket guard and isolated-network tests pass | §12.2 |
| 2.6 | Health, failover, circuit breaker in `router.get()` | S | 0.4 | — | Primary down → next rank, `MODEL_FAILOVER` audited | — |
| 3.1–3.5 | Graph store, entity-resolution spike (P-104), edges, Correlation Agent with negative control | L | Stage C | ER false positives | Precision/recall floors asserted; negative control passes through the general mechanism | Graph ADR; ER false-positive acceptance: **USER** |
| 3.6–3.7 | Persistent scoped memory; continuation node | M | 1.11 | Spammy follow-ups | Adversarial scoping test; propose vs silent both pass | — |
| 3.8 | Local ASR (replaces Web Speech) | M | 0.4 | Indic quality | Transcript within tolerance per language fixture | ASR ADR; §12.5 |
| 3.9 | First connector | L | §12.10 | Credentials | Plan 3.9 criteria | **USER §12.10** |
| 3.10 | RBAC against a real IdP | L | §12.1 | **BLOCKED** | Plan 3.10 | **USER §12.1** |
| 3.11–3.12 | Eval metrics + dashboard; reranker + hybrid retrieval | M | Stage C | — | Retrieval at or above the Phase 1 baseline, with numbers | Reranker ADR |
| UI-2 | Agent-activity timeline, task history, admin console (read-only), i18n + RTL + Indic | L | 3.11, UI-1 | Translation QA | Timeline shows the served model, tier and escalations; RTL screenshot tests | — |

### Stage E: Hardening (plan Phase 4)

| ID | Item | Effort | Depends on | Risks | Acceptance criteria | ADR / decision? |
|---|---|---|---|---|---|---|
| 4.1a–c | Egress re-test, injection suite (PDF, CSV cell, HTML, OCR text), privilege escalation via chaining | M | Stage D | — | 100% blocked; injected action not performed; denial logged | — |
| 4.2 | Fault injection (model timeout, vector store down, corrupt upload, Critic loop over budget, …) | M | Stage D | — | Each produces its documented recovery | — |
| 4.3 | Load and latency on production-class hardware, **per tier** | M | hardware | No hardware yet | p50/p95/p99 recorded, not estimated | §12.6, §12.9 |
| 4.4 | OpenTelemetry → local collector, dashboards, alerts | M | 1.12 | — | Live traces; alert fires on an injected failure | ADR-0006 |
| 4.5 | Video and voice-output review | S | usage data | — | Decision recorded | §12.5, §12.12 |
| 4.6 | Security review sign-off + air-gap bundle dry run (`install.sh` / `verify.sh` on a disconnected VM) | M | 4.1–4.4 | — | Signed review; bundle installs offline with all hashes verified | §12.11 |

### Stage F: Production (plan Phase 5)

| ID | Item | Effort | Depends on | Risks | Acceptance criteria | ADR / decision? |
|---|---|---|---|---|---|---|
| 5.1 | Scale serving from Phase 4 data (vLLM per GPU on `gpu_multi`) | L | 4.3 | — | Capacity plan matches measured load | Hardware: **USER** |
| 5.2 | Optimization Agent → proposals queue | M | 3.11 | Unsafe auto-edits | At least 1 proposal reviewed; bypass test passes | — |
| 5.3 | More connectors, driven by pilot usage | L each | 3.9 | — | Each passes 3.9 criteria | **USER** |
| 5.4 | Single-department pilot against a manual baseline, plus starter kit #2 (process plant) | L | 4.6 go | — | Measured time savings; zero egress violations | Go/no-go: **USER** |
| 5.5 | Model refresh with probation/shadow mode | M | eval harness | — | One real new model processed within the SLA | — |
| 5.6 | Quarterly architecture review | ongoing | — | — | First review held on schedule | — |

**Items that need an ADR:**
- 0001–0007 (drafted as Proposed).
- The lockfile tool.
- Radix, i18next and fontsource.
- python-pptx.
- SQLite/Postgres.
- The graph store.
- The OCR engine (RapidOCR is already used, so this formalises it).
- The ASR engine.
- The embedding model.
- The reranker.
- The queue.
- The release signing tool.
- The new contract fields (SubTask, MODEL_ESCALATION, HARDWARE_PROFILE_SELECTED).

**Items that need a decision from you:**
- C1–C8.
- Plan §12.1–12.13.
- QW4 visible scoring change.
- QW8 history rewrite, personal PDFs and the DCS manual licence.
- Mac sizing and tier override.

---

## Top 10 recommended changes
1. **Stop the false assurance (QW4 + QW1).** Today the UI reports "VERIFIED_SAFE", scores of at least 78%, and a safety validator that never runs (`evaluation_service.py:50,70`, `agent_orchestrator.py:406-427`), and failed models are silently swapped for another. In a safety-critical domain, a confident wrong answer is worse than no answer.
2. **Replace the random retrieval with real embeddings (QW6 → 1.1).** Fallback vectors seeded by the salted `hash()` gave a different top-5 for the same query in each of 3 processes. Grounding, citations and every downstream agent depend on retrieval that works.
3. **Close the upload path traversal and the egress leaks (QW3 + QW9).** A client filename can write outside the upload directory, and LangSmith, Google Fonts, Web Speech, Markdown images and `:cloud` Ollama tags all leave the machine. Zero egress is the product's core promise (plan §1.4).
4. **Introduce `config/models.yaml` + `ModelRouter` with capability tags (0.4).** `AGENT_MODEL_MAP` routes by role name, four of the six configured models aren't installed, and vision is detected by a substring of the model name. Everything in §4.4 (cascade, tiers, failover) needs this abstraction.
5. **Add device-aware hardware tiers (QW11 → 0.4b).** This laptop has no GPU and gets 5–9 tok/s. The same code must run lean on an i7, use bigger models on a GPU and run at full quality on a Mac, without branching in agent code.
6. **Execute the plan DAG with a real Critic gate (0.5 → 1.10).** The DAG is emitted to the UI but never executed (`agent_orchestrator.py:209-211`), and the planner ignores its SLM. Verification and parallelism are the platform's differentiator.
7. **Adopt the structure-preserving EvidenceUnit ingestion, and keep the PDF viewer path (1.2–1.5).** CSV and XLSX are truncated to 10–15 rows and table search is effectively dead (`ingestion_adapter.py:145,180`, `universal_ingestion_service.py:232-237`). Correct citations and correlation need tables to stay tables.
8. **Add workspace scoping and authentication to every store and route (0.4 → 1.5 → 3.10).** There is no tenant concept, no authentication, CORS is `*`, and traces from every user are readable. Multi-tenant leakage blocks any real deployment.
9. **One locked environment, tests isolated from tracked data, and a cleaned-up repo (QW7 + QW8).** The venv can't run the app, the tests write into git-tracked directories, and around 10,000 vendor files plus personal PDFs are committed. Reproducibility is a precondition for every "test passed" claim (plan §3.5).
10. **Design-system and accessibility rebuild with typed SSE (UI-1).** There are contrast failures (2.95:1 on primary buttons), no dialog semantics, no mobile layout and fragile in-band stream tags. Users won't adopt anything clunkier than ChatGPT (plan §1.2), and WCAG AA is needed for government and enterprise buyers.
