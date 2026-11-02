# Obsidian learning assistant

Approved scope (2026-11-03): adapt DeepTutor's existing chat for professional TA
questions grounded in the user's vault, inspectable note citations, and conversion
of Markdown, text PDFs and webpages into reviewed learning notes.

The configured vault is `D:/MyDataBase/TA`, a standalone vault. Preserve its note
layout and frontmatter (`type`, `status`, `source`, `topics`, `tags`, `aliases`,
`related`). No bulk rewriting of existing notes. Existing TA-prefixed references
must work without changing the files. Model-generated work is a draft until an
explicit UI save. Enforce this at the server/tool boundary, not just in prompts.

Use the existing live-vault integration, not a second corpus or embedding service.
Rank lexical matches across titles, aliases, tags and body; resolve related links
and backlinks. Cite actual reads using server-issued reference IDs, with heading
location and an Obsidian URI. Preview within chat and provide a direct-link page.
The Obsidian tool surface may explicitly include the existing safe web-fetch tool
for learning materials. Uploaded material text is untrusted source data.

New API contract (all routes access-check the current user's KB; identifiers are
opaque and state is scoped to the current account/workspace, outside the vault):

- `GET /api/obsidian/sources/{id}` -> NotePreview.
- `GET /api/obsidian/note?kb=...&note=...&heading=...` -> NotePreview.
- `GET /api/obsidian/asset?kb=...&path=...` -> allowed image bytes inside vault.
- `GET /api/obsidian/drafts/{id}` -> NoteDraft.
- `POST /api/obsidian/drafts/{id}/save` JSON `{path,content,properties}` -> NoteDraft
  with status saved and note_href. Create must be exclusive; append/property must
  check the original note digest and refuse stale drafts. Repeat save is idempotent.
- `POST /api/obsidian/material` multipart `file` -> Material.
- `POST /api/obsidian/material/url` JSON `{url}` -> Material (reuse safe web fetch).

NotePreview: `{kb,path,body,frontmatter,heading,obsidian_uri,links,changed?}`;
links is `[{label,href}]` using `/obsidian?kb=...&note=...`.
NoteDraft: `{id,kb,path,content,properties,mode,status,preview_href,note_href?}`;
mode is create/append/property, status pending/saved. Pending content is editable.
Material: `{text,source,title,truncated}`. Bound file sizes and text lengths; reject
scanned/empty PDFs with an actionable error, never fabricate their content.

Citation URLs: `/obsidian?source=<id>&heading=<encoded heading>` from actual reads.
Draft URLs: `/obsidian?draft=<id>`. Direct note navigation:
`/obsidian?kb=<ref>&note=<vault relative path>&heading=<heading>`.

The read tool returns `references: [{title,href,heading}]` for the note/sections.
Existing create/append/property tools stage drafts instead of writing the vault;
they return the draft preview URL and explicitly pending status. Capability
injects a server-owned `_vault_ref` as well as `_vault_path`; save rechecks write
access and binding to that same vault. Root paths and properties are untrusted.

Frontend: intercept these same-origin relative links in MarkdownRenderer, open a
right-side preview with loading/error/retry, heading focus and Open in Obsidian.
Render safe local images and navigable wikilinks. Pending drafts show editable
path/body/properties, Preview and explicit Save; a failed save retains edits.
Add a Materials-to-notes action next to the existing chat composer for a selected
Obsidian KB. Extract upload/URL, show source text, and prefill (never auto-send) a
learning-note instruction into the normal composer. The normal chat model then
reads relevant vault notes and stages a draft using existing tools.

Professional answer guidance: distinguish vault evidence, supplementary model
explanations and uncertain claims; cover relevant rendering stages, coordinate
spaces, equations, implementation, artist inputs, performance and verification.
Never force irrelevant sections or claim that retrieval trains a model.

Validation: isolated fixture vaults for mutation tests; real TA is read-only smoke
data. Verify source/draft permissions, escape/symlink rejection, duplicate titles,
Unicode paths, chapter links, stale drafts and repeat save. Verify rendered chat
link preview, material prefill and save with temporary fixture data. No real model
call without usable user configuration; report that boundary honestly.
