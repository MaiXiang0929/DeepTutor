# Obsidian Learning Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development. Execute the approved design without additional approval gates.

**Goal:** Ground professional TA answers in inspectable Obsidian notes and turn materials into user-reviewed notes.
**Architecture:** Extend existing live-vault tools; server-issued sources and staged drafts; chat-integrated preview and material preparation.
**Tech Stack:** Python/FastAPI, React/Next.js, existing Markdown and model runtime.
**Spec:** docs-for-dev/OBSIDIAN_LEARNING_DESIGN.md

## Global constraints
- Preserve `D:/MyDataBase/TA`; real-vault tests are read-only.
- No new embedding or model dependency.
- Drafts cannot mutate the vault before explicit save; enforce account/KB scope.
- All filesystem paths stay inside selected vault and skip internal state.

## Review focus
- TA-prefixed, Unicode, heading and duplicate-name links must not point to another note.
- Malicious source links, local asset paths and symlinks cannot escape the vault.
- Read-only grants cannot create drafts that bypass write authorization.
- Stale or repeated saves do not overwrite concurrent user changes.
- Material failures, preview failures and save failures retain user input and explain recovery.

### Task 1: Vault retrieval and graph
Files: vault.py; optional retrieval.py; tests/capabilities/test_obsidian_learning_retrieval.py.
Interfaces: existing read/search/list/links/backlinks signatures remain usable.
- [x] Add failing tests for root-name prefix fallback, aliases, ambiguous basenames,
  weighted multi-term/Chinese retrieval, related properties, safe path boundaries.
- [x] Implement ranked search, graph resolution and compatible references.
- [x] Run new tests plus existing Obsidian capability/backlink tests.

### Task 2: Sources, drafts and material endpoints
Files: new services/obsidian_learning.py and api/routers/obsidian.py;
knowledge router inclusion; capability.py, binding.py, tools.py; tests/api and services.
Interfaces: exact HTTP and tool contracts in design document; reuse Task 1 vault ops.
- [x] Add failing tests for actual-read source references, scoped reads/assets,
  staged tools, create/append/property save, stale/repeat/unauthorized save, material extraction.
- [x] Implement persistent per-user sources/drafts, KB access checks and API routes.
- [x] Stage existing write tools and enrich read tool references; inject `_vault_ref`.
- [x] Run focused backend tests and existing capability regressions.

### Task 3: Chat preview and materials-to-notes
Files: web/lib/obsidian-learning.ts; web/components/obsidian/*;
MarkdownRenderer.tsx; ChatWorkspace.tsx; /obsidian page; locales en/zh;
web/tests/obsidian-learning*.
Interfaces: exact HTTP/URL/response types in design document. Compose via existing
prefillInputRef; selected KB from state.knowledgeBases + kbOptions metadata.
- [x] Add failing tests for URL parsing, note rendering, source preview, editable
  draft save, errors, material upload/URL prefill.
- [x] Implement preview drawer and direct-link fallback, accessible interactions.
- [x] Integrate composer action and same-origin source/draft link handling.
- [x] Run focused unit tests, typecheck and scoped ESLint.

### Task 4: Integration, prompt, setup and verification
Files: obsidian prompts zh/en, guide, API contracts if generation requires it.
- [x] Update professional answering/source trust guidance; allow safe web fetch.
- [x] Verify all task suites together; regenerate/check API contracts if changed.
- [x] Register TA pointer without writing notes, smoke read retrieval and sources.
- [x] Browser verify preview, extraction/prefill and fixture-only draft save.
- [x] Fresh independent final review; fix material findings and repeat affected tests.

## Progress / decisions
- Baseline: 29 existing Obsidian tests passed (2026-11-03).
- Ruling: use the existing checkout on local feature branch feat/obsidian-learning,
  preserving its installed runtime; no separate worktree (would split the running app).
- Ruling: user approved the design and execution; execute continuously in this chat.
- Ruling: source ingestion prepares text for the existing composer/model rather than
  introducing an independent LLM pipeline; user reviews before sending and saving.


## Final verification (2026-11-03)
- Task 1: retrieval/graph implementation complete; fresh review findings fixed with RED/GREEN regressions (linear backlinks, unreadable notes, Windows junctions).
- Task 2: sources/drafts/material API complete; fresh review fixes cover actual workspace state isolation, access/packaging registration, exclusive atomic create and linear preview resolution.
- Task 3: chat preview/material flow complete; review fixes cover ordinary Markdown destinations, spaced images, heading forwarding and learner permissions.
- Task 4: 218 Python tests passed, 1 Windows symlink-privilege skip (real junction test passed); 28 frontend UI tests and 5 Node tests passed. Production build, TypeScript, scoped ESLint/Ruff, i18n, dependency boundaries and generated API checks passed.
- Browser: actual TA note and chapter citations open in a drawer; public webpage extraction prefills but does not send. Temporary-vault draft edited, previewed, saved and verified on disk; temporary KB pointer removed.
- Online: configured model performed 2 real read tools and returned a chapter citation; follow-up staged a pending learning-note draft, successfully opened in UI. The actual TA target file is absent until the user explicitly saves.
- Real-vault integrity: all 79 pre-existing Markdown note hashes unchanged.
- Ruling: keep the completed change on local feat/obsidian-learning; no remote publication or merge is required for this local application.
- Ruling: en/zh UI copy is localized; other catalogs use explicit English fallback entries so existing strict catalog checks remain valid.
