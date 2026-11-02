# Learning with an Obsidian vault

DeepTutor can use a local Obsidian vault as the evidence for a conversation,
show the original notes beside chat, and prepare learning-note drafts from
materials. Obsidian remains the primary editor and storage location.

## Connect and ask

1. Open Knowledge Center, create a knowledge base, and choose Link existing →
   Obsidian. Enter the absolute vault directory visible to the backend.
2. Select that knowledge base in the chat resource picker. New chat sessions
   must select it too unless the resource-reuse preference retains it.
3. Ask a question such as “Explain the assumptions in my PBR notes and show
   the related rendering-equation sections.”
4. Click a cited note or section to open its preview beside the answer. The
   preview shows properties, safe local images and related note links. Open in
   Obsidian opens the original file in the desktop application.

Search uses weighted titles, aliases, tags and body terms. Existing root-prefixed
wikilinks are supported: `MyVault/Topic/Note` falls back to `Topic/Note` only when
the original explicit path does not exist. Ambiguous names require an explicit
vault-relative path. Relations include body wikilinks and frontmatter `related`.
This is live retrieval; no embedding service or copied vector index is required.

Sources are issued after actual note reads. A cited note that has changed since
the read is labelled accordingly; the preview shows its current contents. The
assistant should distinguish note evidence, supplemental explanation and claims
that still require verification. Read the source and assess technical conclusions.

## Convert materials into learning notes

With an Obsidian knowledge base selected, choose **Materials to notes** above
the chat composer:

1. Upload a UTF-8 Markdown/text file or a text-based PDF, or enter a public
   webpage URL. Extraction does not make a model request.
2. Review/edit the extracted source text. The UI flags truncation. Empty,
   scanned or encrypted PDFs need text extraction/OCR/unlocking first; this
   version does not claim to read their contents.
3. Choose **Prepare learning note**. This prefills a message in the normal
   composer. Read it, adjust the instruction if needed, then send it.
4. The selected model reads related notes and prepares a draft following the
   vault's metadata conventions. The source text is sent to that configured
   model as part of the message.
5. Open the draft link in the answer. Review its destination, Markdown and
   properties, use Preview, then explicitly choose **Save to vault**.

Creating, appending and setting properties through Obsidian tools all stage
drafts. They cannot save directly. New files refuse to overwrite existing
files. Existing-note drafts refuse to save after the underlying note changes;
read the updated note and prepare another draft. Repeating a successful save
does not duplicate an append. Property drafts preserve existing note prose.
Draft state is private to the current account and content workspace, outside
the Obsidian vault. Removing a connected KB removes the pointer, not the vault.

## Limits and troubleshooting

- Local materials: up to 20 MB; extracted/source text is bounded. Webpage
  fetching uses the existing public-address checks and may not work with
  login-required sites or pages rendered entirely by JavaScript.
- The Obsidian browser supports Markdown notes and local image assets. PDF
  material extraction is separate from indexing or displaying all vault PDFs.
- Internal vault directories and paths outside the selected vault are refused.
- If a source or draft cannot be found, check its originating account/workspace
  and that the KB still points to the same vault. Links carry their original
  workspace scope.
- If save fails, keep the editable draft open. Correct the path/permissions or
  create a fresh draft if the original note changed. No successful-save message
  should appear until the backend confirms it.
- To use desktop opening, Obsidian must be installed and its URI handler enabled.

## Developer verification

Run the Obsidian capability/retrieval, service and API tests with isolated
fixture vaults, and the `obsidian-learning` frontend tests. Use a temporary vault
for browser write acceptance. Real user-vault acceptance should be read-only;
compare its Markdown hashes before and after verification.
