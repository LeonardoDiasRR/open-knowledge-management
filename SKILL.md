---
name: open-knowledge-management
description: "Create and manage a personal LLM-Wiki (Karpathy) with files in the Google Open Knowledge Format (OKF). First run asks for the wiki root path, saves it and scaffolds AGENTS.md + structure; then ingests, queries and lints the wiki. Use whenever the user wants to build, maintain or search a markdown wiki / knowledge base / second brain, ingest documents or web research into it, or health-check it."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [knowledge-base, wiki, llm-wiki, okf, note-taking, ingest, research, agent]
    category: note-taking
---

# Open Knowledge Management

Build and maintain a personal, queryable **LLM-Wiki** following [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), with every file in the [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) defined by Google. You are the librarian: you scaffold it on first use, then read sources, compile them into structured OKF pages, and maintain the wiki over time. You follow these rules exactly — never improvise the structure.

## Decision matrix

| Need | Use |
|------|-----|
| User wants to *start* a wiki / second brain | **Init / First run** (below) |
| Process a local file (PDF, image, text) or web research into the wiki | **Ingest** |
| Ask a question against the wiki | **Query** |
| Health-check the wiki (orphans, stale claims, broken refs) | **Lint** |
| Find which wiki root you manage | Read the config (below) |

## Configuration

The wiki root path is persisted in **`data/config.json`** inside this skill's directory:

```json
{ "wiki_root": null }
```

- **Read it** at the start of every operation to resolve the wiki root.
- **Write it** during Init so future runs skip the prompt.
- If `data/config.json` is missing **or** `wiki_root` is `null`, you are on **first run** — do Init.
- If the skill directory is read-only and you cannot write the config, fall back to the environment variable **`OKM_WIKI_ROOT`** (prefer it if set), else fall back to prompting **each operation** until the user also points you at a writable copy. Prefer `OKM_WIKI_ROOT` over prompting when both apply. Never fabricate a path.

## Folder structure

The wiki root is a directory of Markdown files with YAML frontmatter. Every `wiki/*` subdirectory carries its own `index.md` and `log.md` (OKF §8/§9). Scaffold exactly:

```
<wiki-root>/
├── AGENTS.md            # Governing rules (self-contained copy, see Init)
├── index.md             # Root index (OKF §8)
├── log.md               # Root log, newest-first (OKF §9)
├── raw/                 # Immutable source materials (never modified)
├── wiki/
│   ├── index.md         # Lists the four sections
│   ├── log.md
│   ├── sources/         # one summary page per ingested source
│   │   ├── index.md
│   │   └── log.md
│   ├── entities/        # people, organizations, products, tools
│   │   ├── index.md
│   │   └── log.md
│   ├── concepts/        # ideas, frameworks, theories, patterns
│   │   ├── index.md
│   │   └── log.md
│   └── synthesis/       # comparisons, analyses, cross-cutting themes
│       ├── index.md
│       └── log.md
└── output/              # reports, query results, generated artifacts
```

Reserved names: `index.md` and `log.md` are reserved and MUST NOT be used for concept/entity/source pages (OKF §3.1).

## Init — first run

Use a clean, deterministic scaffold. **Prefer `scripts/scaffold.py --root <path>` when the `scripts/` directory is present.** If it is absent (e.g. `hermes skills install` copied only `SKILL.md`), scaffold the tree yourself with your file tools:

1. Ask the user where to store the wiki (**full absolute path** of the root directory). If they don't give one, propose a sensible default (e.g. `~/second-brain` or `~/wiki`) and wait for confirmation. Do not guess silently.
2. Create the folder structure above and the skeleton files.
3. Write a **self-contained `AGENTS.md`** at the root that encodes the full governing rules (this skill's content, compressed to its essentials: the three operations, page format, index/log rules, and the reserved-filenames rule). It must be able to drive the wiki without this skill loaded.
4. Write `data/config.json` with the chosen root.
5. Report the created tree and tell the user the wiki is ready.

The `AGENTS.md` you write MUST include the page format, operations (ingest/query/lint), index/log rules, and the OKF frontmatter field reference from `references/okf-conventions.md` (or from below when references are absent).

## Page format (OKF)

Every page (except `index.md`/`log.md`/`AGENTS.md`) is a concept with **YAML frontmatter** and a **Markdown body**:

```yaml
---
type: Entity                                  # REQUIRED. Source Summary | Entity | Concept | Synthesis
title: Page Name                              # Optional display name
description: One-line summary                 # Recommended
resource: urn:... OR https://...              # Optional canonical URI of the underlying asset
tags: [tag1, tag2]                            # Optional
# Provenance / trust / lifecycle (OKF §5) — optional but encouraged:
sources:
  - id: source-1.somewhere.md                 # stable key used by footnotes
    resource: path/or/url                     # REQUIRED within an entry
    title: Human-readable source label
    author: <producer>/<ver> | human:<id> | process:<id>
    usage_count: 12
    last_modified: 2026-08-26T00:00:00-04:00
generated: { by: open-knowledge-management/1.0.0, at: 2026-08-26T00:00:00-04:00 }
verified:
  - { by: human:owner, at: 2026-08-26T12:00:00-04:00 }
---
```

- `type` is the only always-required key. Choose one per subdirectory: `Source Summary` (sources/), `Entity` (entities/), `Concept` (concepts/), `Synthesis` (synthesis/). You MAY carry OKF example types (`BigQuery Table`, `Metric`, `Playbook`) when describing concrete assets.
- All timestamps are **ISO 8601 with an explicit UTC offset** (e.g. `2026-08-26T08:00:00-04:00`).
- Actor convention: `<producer>/<version>` for agents, `human:<id>` for people, `process:<id>` for automated processes.
- Body: prefer **structural Markdown** (headings, lists, tables, fenced code) — aids both humans and agent retrieval. No required sections.
- Per-claim attribution uses a **footnote whose label is a `sources[].id`**, resolved via the matching `sources` entry (keyed, not positional — survives reordering).
- Use `[[wikilinks]]` for all internal cross-references. When you mention an entity, concept, or source that has its own page, link it.

## Operations

### Ingest (processing a new source)

When the user adds a file to `raw/` or asks you to process a source:

1. Read the source completely (document, PDF, image, or web research).
2. Discuss key takeaways with the user.
3. Save a copy of the original under `raw/` (immutable — never modify sources; read freely).
4. Create a **Source Summary** page in `wiki/sources/` with title, source metadata, key claims, and a structured summary. Record `resource` pointing at the `raw/` copy, and provenance fields.
5. Identify all entities and concepts mentioned. For each:
   - If a page exists: update it with the new info, noting this source in `sources`.
   - Else: create it in the right subdirectory (`entities/` or `concepts/`).
6. Link pages with `[[wikilinks]]`.
7. Update the **per-directory `index.md`** for every directory you added/edited a page in, and the **root `index.md`**.
8. Append a newest-first entry to `log.md` (root and per-directory as appropriate): `## YYYY-MM-DD | operation` then a one-line description. OKF logs are **newest-first**, so new entries go at the top of their date group.

### Query (answering questions)

1. Read the root `index.md` to find relevant pages; then the per-directory indexes.
2. Read the relevant pages.
3. Synthesize an answer with `[[wikilink]]` citations.
4. If the answer produces a durable artifact, offer to save it as a page in `wiki/synthesis/`.
5. If you save one, update index and log.

### Lint (health check)

1. Scan for contradictions between pages.
2. Find stale claims superseded by newer sources.
3. Identify **orphan pages** (no inbound links).
4. Find important concepts mentioned but lacking their own page.
5. Check missing cross-references.
6. Suggest data gaps that could be filled by a web search.
7. Report and offer to fix issues.
8. Log the lint pass (newest-first).

## Rules

1. Never modify files in `raw/`.
2. Always keep `index.md` (root + per-directory) current when pages are created/deleted.
3. Always append to `log.md` (newest-first) on every operation.
4. Use `[[wikilinks]]` for all internal references.
5. Every page has YAML frontmatter with at least `type`, `title`, `description`; record `sources`/`created`/`updated`/`verified` where known.
6. When new info contradicts existing content, update the page and note both sources.
7. Keep source-summary pages factual; save interpretation for concept/synthesis pages.
8. When asked a question, search the wiki first.
9. Prefer updating existing pages over creating new ones.
10. Keep indexes concise — one line per page, under 120 characters per entry.

## References

When you need depth, load these from `references/` (in this repo; may be absent if only `SKILL.md` was installed):

- `references/okf-conventions.md` — full OKF field reference (provenance/trust/lifecycle/attestation).
- `references/ingest-workflow.md` — detailed ingest pipeline with examples.
- `references/query-and-lint-workflow.md` — detailed query and lint procedures.
- `references/karpathy-llm-wiki.md` — conceptual origin and why this pattern exists.