# DuckDB Tabular Data Design

## Status

Approved during brainstorming on 2026-08-29.

## Context

OpenKM is a self-contained agent skill for ingesting sources into an OKF-formatted Markdown wiki. Its current ingest flow preserves raw sources and creates source-summary, entity, concept, and synthesis pages, but it does not persist tabular data in a queryable database.

The feature adds DuckDB storage for tabular files and tabular data identified inside documents. The supplied UERR vestibular PDF is an acceptance example: it contains an explicit table and several logical result lists that can be represented as tabular data.

## Goals

- Store tabular data from all sources in one DuckDB database per wiki.
- Automatically persist genuinely tabular CSV, TSV, XLSX, and other formats explicitly supported by the helper.
- Detect explicit tables and tabulatable text in ordinary documents, propose the result, and require approval before persistence.
- Create or update a wiki page describing each persisted dataset and how the agent can query it.
- Preserve row-level provenance and make reingestion idempotent.
- Keep original sources immutable and retain the existing OKF ingest behavior.

## Non-goals

- Exposing a SQL CLI or database UI to the user.
- Making the DuckDB file itself a wiki page or replacing Markdown source summaries.
- Automatically interpreting ambiguous data as fact.
- Building a general-purpose ETL platform or a remote database service.

## Decisions

- Database path: `<wiki-root>/database/data.duckdb`.
- One database contains tables derived from all sources.
- CSV/TSV and genuinely tabular XLSX content are persisted without approval; the agent shows the result afterward, including the first five rows and the wiki page. Unsupported formats receive an explicit failure status rather than being silently skipped.
- Tables or tabulatable text extracted from ordinary documents require approval before persistence. The proposal includes the schema and first five rows.
- A source produces one table per logical dataset. An Excel workbook produces one table per tabular worksheet.
- Reingesting a source reconstructs only the tables owned by that source and does not duplicate rows or affect other sources.
- Data access is exclusively through natural-language requests handled by the agent.
- Each data row includes `source_id`, `source_page`, and `source_section`; Excel rows additionally include `source_sheet`.
- Ambiguous values remain text when possible and become `NULL` only when they cannot be determined. Every such decision is recorded in the source page.
- Cells whose values are produced by formulas or aggregations are not persisted in DuckDB. Only their input columns are stored; calculations are performed at query time.
- Formula definitions and their equivalent DuckDB SQL are documented only in the source page, not in the database or its catalog.

## Architecture

The implementation has two layers:

1. **Skill contract**
   - `SKILL.md` defines detection, approval, persistence, query, provenance, and wiki-update rules.
   - `references/ingest-workflow.md` defines the detailed ingest sequence and examples.
   - `README.md` documents the capability and dependency.
   - The `AGENTS.md` template in `scripts/scaffold.py` carries the same rules into newly created wikis.

2. **Deterministic helper**
   - A Python helper using DuckDB performs supported-format loading, table creation/reconstruction, identifier sanitization, metadata updates, five-row sampling, and agent queries.
   - The agent remains responsible for reading documents, deciding logical datasets, interpreting extracted content, and obtaining approval where required.
   - The helper is the only component that writes derived tabular data.

The database is created on demand. `raw/` remains the immutable source area; `database/` contains only derived data. The existing Markdown source-summary page remains the user-facing description of the dataset.

## Ingest Flow

1. Read the source completely and preserve the original under `raw/`.
2. Identify whether the source is a supported tabular file or an ordinary document.
3. For a supported tabular file:
   - verify that the content is tabular;
   - detect formula-derived columns and exclude their cached results from the persisted schema;
   - create one table per tabular worksheet or logical tabular set;
   - persist automatically;
   - show the first five rows and the created or updated source page.
4. For an ordinary document:
   - identify visual tables;
   - identify lists or prose that can be represented as columns and rows;
   - group candidates into logical datasets;
   - present the proposed schema and first five rows;
   - persist only after explicit user approval.
5. Write the accepted dataset in a transaction.
6. Create or update the `Source Summary` page with the database path, table inventory, schema, row count, five-row sample, provenance, extraction status, and caveats.
7. Update affected indexes and newest-first logs according to the existing OKF rules.

If the user rejects a proposed extraction, the source remains available as normal text and no derived data table is created. The refusal and status are recorded in the source page or ingest log.

## Database Model

The helper maintains two internal catalog tables:

- `_openkm_sources`: source identifier, source-summary page, raw resource, content checksum, ingest timestamp, and extraction status.
- `_openkm_tables`: physical table name, owning source identifier, logical dataset or worksheet, schema description, row count, and update timestamp.

Internal catalog names are reserved and must not be generated for user datasets.

Data table names follow:

```text
<source_slug>__<dataset_slug>
```

For Excel, the dataset slug is the sanitized worksheet name. For document extraction, it is the sanitized logical dataset name. Names and column identifiers use a deterministic SQL-safe sanitization rule; collisions receive stable suffixes. The wiki page preserves original worksheet and column labels.

Each data table contains the extracted columns plus:

| Column | Type | Meaning |
|---|---|---|
| `source_id` | text | Stable source identifier |
| `source_page` | nullable integer | Original page number when applicable |
| `source_section` | nullable text | Original section or logical location |
| `source_sheet` | nullable text | Excel worksheet when applicable |

The helper infers types only when safe. Codes and identifiers that could lose leading zeroes remain text. Mixed or uncertain values remain text rather than being silently coerced.

### Formula-derived Values

When the source exposes a formula, the helper stores the input columns but excludes the formula column and its cached result from the data table. This applies to row formulas and aggregate formulas such as `SUM`, `AVERAGE`, and standard deviation calculations. The source page records the original formula, the excluded column, the input columns, and an equivalent DuckDB SQL expression or query for the agent to execute on demand.

Formula metadata is not written to `_openkm_sources`, `_openkm_tables`, or any user data table. If a formula cannot be translated safely, its result is still excluded and the page records that no equivalent query was generated rather than storing the derived value.

## Reingestion and Transactions

The source checksum and catalog ownership determine whether a source is new or being reingested. On reingestion, the helper removes and rebuilds only that source's derived tables and catalog entries in one transaction. A failed operation rolls back all database changes, leaving other sources untouched.

The raw source is never modified or deleted. A successful reingestion updates the existing source page rather than creating an unnecessary duplicate page.

## Agent Queries

Users ask questions in natural language. The agent locates the relevant source page and catalog entry, asks the helper to execute a read-only query against the appropriate table, and responds with the result plus a link to the source page. The agent must not expose a SQL interface as a new user-facing feature.

Queries must preserve source context when returning records, especially for data extracted from multi-page documents. Query failures, missing tables, and unavailable dependencies are reported plainly without claiming success.

## Wiki Page Contract

Each source page that produces tabular data includes:

- source metadata and raw-resource link;
- extraction status and whether approval was required;
- logical dataset and table inventory;
- original labels and sanitized table/column names;
- row counts and data types;
- the first five rows;
- provenance column definitions;
- extraction caveats, ambiguous fields, and `NULL` decisions;
- excluded formula-derived columns, their original formulas, and equivalent DuckDB SQL queries;
- instructions stating that the data is accessed by asking the agent questions;
- links to related wiki pages using `[[wikilinks]]`.

The page remains factual. Interpretations and analyses derived from the tables belong in synthesis pages, consistent with the existing ingest rules.

## Errors and Safety

- Unsupported formats, malformed workbooks, missing DuckDB support, and unreadable files produce an explicit failure status.
- A failed write cannot leave a partially populated dataset.
- A non-tabular CSV or Excel file is not automatically persisted; it follows ordinary document candidate analysis.
- No values are invented. Original text is preserved where possible, otherwise the value is `NULL` with a documented caveat.
- Table and column identifiers are sanitized, and data values are bound rather than interpolated into SQL.
- The helper accepts only source paths belonging to the configured wiki and its raw area.
- No table is created merely to represent an empty or rejected candidate.

## Testing and Acceptance

Use Python's standard `unittest` framework with temporary wiki roots and DuckDB fixtures. Cover:

- automatic CSV/TSV ingestion;
- Excel workbooks with multiple tabular and non-tabular worksheets;
- identifier sanitization, accents, symbols, and collisions;
- type inference, mixed values, `NULL`, and leading-zero identifiers;
- formula columns excluded from DuckDB while input columns remain queryable;
- formula definitions documented in the wiki with equivalent SQL and no formula metadata in DuckDB;
- row-level provenance;
- source reingestion without duplication;
- preservation of unrelated sources;
- transaction rollback after failure;
- approval required for document-derived candidates;
- rejection without a derived table;
- read-only agent queries and useful error reporting;
- source-page inventory, sample, caveat, index, and log updates.

The UERR PDF scenario must result in proposals that recognize the explicit name/code table and the logical vestibular result datasets. The proposal must show a schema and five rows, retain page and section provenance, and wait for approval before writing document-derived data.

## Files in Scope

- `SKILL.md`
- `references/ingest-workflow.md`
- `README.md`
- `scripts/scaffold.py`
- a new Python DuckDB helper and its tests
- this design document

No changes are required to the existing wiki content because `data/config.json` currently has no configured wiki root.
