# Ingest workflow

Turn a source (local document, PDF, image, or web research) into wiki pages.
Drives the INGEST operation referenced from SKILL.md.

## Steps (exact)

1. **Read the source completely** (document, PDF, image, transcript, or web
   research fetched from the web).
2. **Discuss key takeaways** — surface the main claims with the user before
   committing pages.
3. **Preserve the original** under `raw/`. It is **immutable**: read it, never
   modify it. For a URL source, optionally save a copy of the raw content.
4. **Create a Source Summary page** in `wiki/sources/`:
   - `type: Source Summary`
   - title, source metadata (file name, URL, retrieved date), key claims,
     and a structured summary.
   - `resource` → the `raw/` copy path (or the URL).
   - Record `sources` + `generated` + `verified` provenance fields.
5. **Identify entities and concepts** mentioned. For each:
   - Page exists → **update** it with the new information, noting this source
     in its `sources` list (do not lose the previous source).
   - Page doesn't exist → create it, as `type: Entity` or `type: Concept` in
     the matching subdirectory.
6. **Add `[[wikilinks]]`** between all related pages.
7. **Update indexes** — the per-directory `index.md` of every directory you
   added or edited a page in, and the root `index.md`.
8. **Log** — append a newest-first entry to the relevant `log.md` (root and
   applicable per-directory). OKF logs are newest-first; insert at the top of
   the newest date group (or start a new `## YYYY-MM-DD` group).

## Example source-summary frontmatter

```yaml
---
type: Source Summary
title: Q2 Sales Report 2026
description: Quarterly sales figures, all channels.
resource: raw/sales/2026-q2-report.pdf
tags: [sales, finance]
sources:
  - id: /raw/sales/2026-q2-report.pdf
    resource: /raw/sales/2026-q2-report.pdf
    title: 2026 Q2 Sales Report
generated: { by: openkm/1.0.0, at: 2026-08-26T00:00:00-04:00 }
---
```

## Pitfalls

- Keep source-summary pages **factual**. Interpretation belongs in concept and
  synthesis pages.
- When a new source **contradicts** an existing page, update the page and note
  **both** sources (rule 6). Never silently discard the old claim.
- For PDFs/images: use the `document-processing` umbrella tools (pymupdf,
  marker-pdf, markitdown) or OCR; verbatim extraction is preferred.
- Web research: fetch the README/README via `curl` raw, or the GitHub API for
  metadata. Save a copy under `raw/`.
