---
name: openkm
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
| Persist a genuinely tabular CSV, TSV, or XLSX source | **Ingest** with automatic DuckDB persistence (below) |
| Extract a table or tabulatable text from an ordinary document | **Ingest** with explicit approval before DuckDB persistence (below) |
| Ask a question against the wiki | **Query** |
| Ask a question requiring tabular data | **Query** through the agent's read-only DuckDB helper (below) |
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
- Derived tabular data always lives at **`<wiki-root>/database/data.duckdb`**. Create the `database/` directory and DuckDB file on demand; do not add a second persisted configuration key for this fixed relative path.
- `database/data.duckdb` is derived data separate from the immutable `raw/` area. Keep the Markdown Source Summary in `wiki/sources/` as the user-facing source description and record the table inventory there.

## Folder structure

The wiki root is a directory of Markdown files with YAML frontmatter. Every `wiki/*` subdirectory carries its own `index.md` and `log.md` (OKF §8/§9). Scaffold exactly:

```
<wiki-root>/
├── AGENTS.md            # Governing rules (self-contained copy, see Init)
├── index.md             # Root index (OKF §8)
├── log.md               # Root log, newest-first (OKF §9)
├── raw/                 # Immutable source materials (never modified)
├── database/             # Derived data, created on demand
│   └── data.duckdb       # DuckDB tables for persisted tabular datasets
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

`database/` is a derived-data location, not a Markdown wiki section. Do not create a `wiki/tables/` directory. Keep `wiki/sources/` for one Source Summary page per ingested source, and preserve all other OKF directories and reserved names.

Reserved names: `index.md` and `log.md` are reserved and MUST NOT be used for concept/entity/source pages (OKF §3.1).

## Init — first run

Ask where to store the wiki, then **fresh scaffold** or **adopt** depending on
the target. **Prefer `scripts/scaffold.py <--root> [--adopt]` when the `scripts/`
directory is present.** If it is absent (e.g. `hermes skills install` copied only
`SKILL.md`), do the equivalent with your file tools.

1. Ask the user for the **full absolute path** of the root directory. If they
   don't give one, propose a sensible default and wait for confirmation. Do not
   guess silently.
2. Inspect the target:
   - **Missing OR empty** → fresh scaffold: create the structure and skeleton
     files exactly as in "Folder structure", including a self-contained
     `AGENTS.md`.
   - **Exists with content** → **adopt** it (reuse an existing knowledge base):
     - Create **only** the directories that are missing (`raw/`, `output/`, and
       any `wiki/*` sections). **Never overwrite** existing files.
     - If the target already has its own `AGENTS.md`, **keep it** and defer to
       its conventions (it takes precedence over this skill's generic rules
       for that wiki, exactly like any project's governing file).
     - Only write this skill's `index.md`/`log.md` skeletons for directories
       that are missing them; leave existing ones untouched.
     - If the existing content isn't obviously OKF-structured, first **survey
       it** (list files, read an `index.md`/`AGENTS.md` if present) so you
       understand the layout before touching anything.
3. Write `data/config.json` with the chosen root (safe on adopt — it's a pointer).
4. Report what was created (fresh) or only added/missing (adopt), and tell the
   user the wiki is ready and whether it was fresh or adopted.

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
generated: { by: openkm/1.0.0, at: 2026-08-26T00:00:00-04:00 }
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
3. Save a copy of the original under `raw/` before calling any tabular helper (immutable — never modify sources; read freely). Helpers accept source paths only from the configured wiki's `raw/` directory.
4. Classify the source:
   - A genuinely tabular CSV or TSV is persisted automatically without approval.
   - A genuinely tabular XLSX is persisted automatically without approval, with one table for each tabular worksheet. Ignore worksheets without a header and data rows.
   - A non-tabular CSV/XLSX and every ordinary document are inspected for explicit visual tables and text that can be represented as columns and rows. Group results into logical datasets; do not automatically persist them.
5. For an automatic direct-file dataset, call `inspect-file` first and verify tabularity, then persist to `<wiki-root>/database/data.duckdb` with the helper's `persist-json` operation. Create one table per logical dataset, and one per tabular worksheet for XLSX. After success, show the first five rows and the updated Source Summary page.
   - The helper detects and normalizes Brazilian data before typing tables: dates/timestamps become `DATE`/`TIMESTAMP` (unrecoverable cells become `NULL`), and CPF/CNPJ/CEP/phone columns become digits-only `VARCHAR` (phone gets DDI `55` when 10-11 digits). Check the `kind` and `normalizations` reported by `inspect-file`, and copy each `normalizations` entry (kind, counts, `nulled_examples`) into the Source Summary caveats so users see exactly what changed.
   - A strong column name can trigger typing from sparse content (e.g. any `data*` column with at least one parseable value becomes `DATE`). Before persisting document-derived datasets, verify `kind` on every `data*`/`dt*` column of SEI-style numbering or internal-code sources — those codes must stay `VARCHAR`; if `inspect-file` reports a wrong `kind`, rename the column in the proposed dataset or flag it in the approval message.
   6. For an ordinary-document candidate, propose each logical dataset before writing it. Show the original column labels, inferred schema/types, estimated row count, provenance fields, caveats, and exactly the first five rows, then require explicit user approval. Each approved ordinary-document logical dataset becomes exactly one DuckDB table, just as each tabular worksheet does. Do not call `persist-json` before approval; if rejected, create no derived table and record the rejection/status in the Source Summary or ingest log.
7. On reingestion, use the helper's `rebuild-json` operation to reconstruct only the tables owned by that `source_id`; never duplicate rows or affect another source's tables. Writes are transactional.
   8. Exclude formula-derived values and aggregate columns from persisted data, including cached formula results. Retain their input columns and perform calculations at query time. Document the original formula, excluded column, input columns, and any equivalent DuckDB SQL only in the Source Summary page; when safe translation is unavailable, document that no equivalent query was generated. Never store formula definitions or derived values in DuckDB catalog or data tables.
9. Add `source_id`, `source_page`, `source_section`, and applicable `source_sheet` to every persisted row. Preserve `None`/`NULL` when a provenance field does not apply. Keep ambiguous values as text when possible; use `NULL` only when the value cannot be determined and record the caveat in the Source Summary.
10. Create or update a **Source Summary** page in `wiki/sources/` with title, source metadata, key claims, structured summary, raw resource, tabular extraction status, table inventory, schema, row count, first five rows, provenance, formula notes, and caveats. Record `resource` pointing at the `raw/` copy and provenance fields.
11. Identify all entities and concepts mentioned. For each:
   - If a page exists: update it with the new info, noting this source in `sources`.
   - Else: create it in the right subdirectory (`entities/` or `concepts/`).
12. Link pages with `[[wikilinks]]`, including a link to the Source Summary when answering about persisted data.
13. Update the **per-directory `index.md`** for every directory you added/edited a page in, and the **root `index.md`**.
14. Append a newest-first entry to `log.md` (root and per-directory as appropriate): `## YYYY-MM-DD | operation` then a one-line description. OKF logs are **newest-first**, so new entries go at the top of their date group.

### Query (answering questions)

1. Read the root `index.md` to find relevant pages; then the per-directory indexes.
2. Read the relevant pages.
3. If the question requires persisted tabular data, locate the relevant Source Summary and catalog entry first, then use the helper's read-only query operation against `<wiki-root>/database/data.duckdb`. The agent may formulate the internal SQL and use `python scripts/tabular.py query --db <wiki-root>/database/data.duckdb --sql <read-only-query> [--parameter VALUE ...]`; users ask natural-language questions and are never given a SQL CLI or database UI.
4. Preserve `source_id`, `source_page`, `source_section`, and applicable `source_sheet` context in the answer, and link the Source Summary with `[[wikilinks]]`.
5. Synthesize an answer with `[[wikilink]]` citations.
6. If the answer produces a durable artifact, offer to save it as a page in `wiki/synthesis/`.
7. If you save one, update index and log.

### Tabular failures and safety

- Report missing DuckDB support, unsupported formats, non-tabular input, unreadable sources, malformed CSV/TSV/XLSX input, missing tables, rejected proposals, unsafe/write queries, and transaction failures plainly. Never claim that data was saved when inspection or persistence failed.
- A failed persistence or rebuild must leave no partial dataset. The helper rolls back the transaction; other source-owned tables remain untouched. The raw source remains immutable.
- Only the agent may query DuckDB, and only through the helper's read-only query operation. Do not add or expose a user SQL interface.
- Do not invent values. Preserve source text where possible; otherwise use `NULL` and document the ambiguity in the Source Summary.

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
