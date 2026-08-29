# Ingest workflow

Turn a source (local document, PDF, image, or web research) into wiki pages and,
when approved by these rules, queryable tabular data. This is the detailed
procedure for the INGEST operation referenced from `SKILL.md`.

## Steps (exact)

1. **Read the source completely** (document, PDF, image, transcript, or web
   research fetched from the web). Do not infer rows from a partial read.
2. **Discuss key takeaways** with the user before committing pages. This does
   not replace the explicit data approval required below for derived DuckDB
   table writes. Approval applies to those table writes; Source Summary,
   extraction status, index, and log updates may record pending or rejected
   extraction before approval or after rejection.
3. **Copy the original to `raw/` before calling the tabular helper.** Use the
   configured wiki root and keep the copy immutable: read it, never modify or
   delete it. A URL source may also have a saved raw-content copy.
4. **Create or update a Source Summary page** in `wiki/sources/`:
   - `type: Source Summary`
   - title, source metadata (file name, URL, retrieved date), key claims, and a
     structured summary;
   - `resource` pointing to the `raw/` copy (or the URL);
   - `sources`, `generated`, and `verified` provenance fields;
   - every Source Summary must record the database path `database/data.duckdb`
     when applicable;
   - tabular extraction status, table inventory, schema, row counts, samples,
     provenance, formulas, and caveats when applicable.
5. **Identify entities and concepts** mentioned. For each:
   - Page exists: update it with the new information and add this source to its
     `sources` list without losing previous sources.
   - Page does not exist: create it as `type: Entity` or `type: Concept` in the
     matching subdirectory.
6. **Add `[[wikilinks]]`** between all related pages.
7. **Update indexes**: update the per-directory `index.md` for every directory
   where a page was added or edited, plus the root `index.md`.
8. **Log** a newest-first entry in the relevant `log.md` files (root and
   applicable per-directory). Put new entries at the top of the newest date
   group, or start a new `## YYYY-MM-DD` group.

## Direct tabular files

The database is derived data at `<wiki-root>/database/data.duckdb`; it is not a
wiki section. Set the helper's configured root, then use only the immutable
copy under `<wiki-root>/raw/`:

```powershell
$env:OKM_WIKI_ROOT = '<wiki-root>'
python scripts/tabular.py inspect-file --source-id ID --file <wiki-root>/raw/file.csv
```

`inspect-file` reads a direct `.csv`, `.tsv`, or `.xlsx` source and prints JSON
with datasets, inferred columns and types, row counts, the first five rows, and
formula definitions. It does not create or write DuckDB. Reject the inspection
if the file is missing, malformed, unsupported, or not genuinely tabular.

For genuinely tabular CSV, TSV, and XLSX files, persistence is automatic and
occurs without approval. A CSV/TSV produces one logical dataset and therefore
one table. For an XLSX, each worksheet with a header row and at least one data
row produces one table; each
non-tabular worksheet is omitted. This is one table per logical dataset or
worksheet, not one table for the whole workbook. The normal persistence call
is:

```powershell
python scripts/tabular.py persist-json --db <wiki-root>/database/data.duckdb `
  --source-id ID --source-resource <wiki-root>/raw/file.csv `
  --summary-page wiki/sources/ID.md --input direct-manifest.json
```

The direct-file manifest JSON must contain `source_id` matching `--source-id`
and a `datasets` array whose objects use the helper dataclass field names (`name`,
`columns`, `rows`, `source_page`, `source_section`, `source_sheet`, and
`formulas` as applicable). The direct helper functions
`load_tabular_file`, `persist_source`, and `rebuild_source` are equivalent when
the CLI is not being used. Any manifest used by this direct-file path is a
persistence manifest only; it is not approval-gated. Never pass a source path
outside the configured `raw/` directory.

After automatic persistence, show the result, including exactly the first five
rows in source order (or all available rows when there are fewer than five),
the logical-to-physical table names, schema, row count, and the updated Source
Summary page. Then update indexes and logs.

If a CSV, TSV, or XLSX is not genuinely tabular, do not persist it
automatically. Treat it as an ordinary document and use the candidate workflow
below. Unsupported formats likewise receive an explicit failure status rather
than being silently skipped.

## Ordinary document candidates

For PDFs, images, text documents, and direct files rejected as non-tabular,
inspect the complete source for both of these candidate types:

- **Visual tables:** a rendered or extracted table with explicit rows and
  columns, including repeated headers and page breaks that can be reconciled.
- **Tabulatable text:** repeated records, lists, or prose with stable fields
  that can be represented as rows and columns without inventing values.

Group records into one logical dataset per coherent schema. Before any derived
DuckDB table write, present a proposal for every candidate containing:

- logical dataset name;
- original column labels and the inferred DuckDB-safe types;
- estimated row count;
- `source_id`, `source_page`, `source_section`, and applicable `source_sheet`
  provenance fields;
- extraction caveats, ambiguity and `NULL` decisions; and
- **exactly the first five rows** in source order (or all available rows when
  fewer than five exist).

Ask for explicit approval of the proposal. Do not call `persist-json`, call a
direct persistence helper, or create a table before approval. If the user
rejects the proposal, create no derived table; retain the source as ordinary
document content and record the rejection/status in the Source Summary or
ingest log.

After approval, serialize the approved datasets as
`approved-document-manifest.json` using the manifest contract and call
`persist-json` only. Use `rebuild-json` only for an already persisted
source being intentionally reingested. Show the persisted first five rows and
update the Source Summary, indexes, and newest-first logs.

## Formulas, ambiguity, and provenance

- Exclude formula-result cells and aggregate-result cells from DuckDB. Keep the
  input columns so equivalent calculations can be run at query time.
- On XLSX inspection, preserve the original formula text, excluded column,
  referenced input columns, and an equivalent DuckDB SQL expression when safe.
  When translation is unsafe, record exactly `no equivalent query was generated`.
  Put this documentation only in the Source Summary; never write formula
  definitions or cached formula values to `_openkm_sources`,
  `_openkm_tables`, or a data table.
- Keep codes and identifiers with leading zeroes as text. Keep ambiguous or
  mixed values as text when possible. Use `NULL` only when the value cannot be
  determined, and record the reason as a caveat in the Source Summary. Never
  invent or silently normalize a value.
- Every persisted row carries `source_id`, `source_page`, and
  `source_section`. Excel rows also carry `source_sheet`; use `NULL` for an
  inapplicable provenance field.

## Rebuilds, rollback, and failures

To reingest a source already in the catalog, read and copy the new raw source
without changing the existing raw copy, regenerate the applicable manifest
(`approved-document-manifest.json` for document-derived datasets or a
non-approval-gated direct-file manifest), and
run:

```powershell
python scripts/tabular.py rebuild-json --db <wiki-root>/database/data.duckdb `
  --source-id ID --source-resource <wiki-root>/raw/new-file.csv `
  --summary-page wiki/sources/ID.md --input <manifest>.json
```

`rebuild-json` reconstructs only the tables owned by `source_id`; it removes
their old catalog rows and data tables and then writes the replacement in one
transaction. It must not duplicate rows or affect any other source. Keep the
raw materials immutable and update the existing Source Summary rather than
creating a duplicate page.

Every persistence or rebuild transaction commits only after all datasets and
catalog rows succeed. On any parse, validation, insertion, or dependency
failure, roll back the whole operation, report the error and source ID, and do
not claim that data was saved. Missing files, invalid JSON, unsupported
extensions, invalid raw paths, malformed input, rejected proposals, missing
DuckDB support, and failed transactions all require an explicit failure/status.
Unreadable source files must produce a failure status.

## Agent queries

Users query tabular data through natural language only. First locate the
relevant Source Summary and catalog entry, including the source page and table
inventory. Then use the helper's read-only query command:

```powershell
python scripts/tabular.py query --db <wiki-root>/database/data.duckdb `
  --sql 'SELECT * FROM "source__dataset" WHERE "Code" = ?' --parameter '0012'
```

The helper accepts `SELECT`, read-only `WITH`, `DESCRIBE`, and `SHOW` queries,
binds parameters, rejects mutating or multiple statements, and opens DuckDB in
read-only mode. Preserve the row provenance and source context in the answer,
link the Source Summary page, and report missing tables, unavailable
dependencies, or query failures without claiming success. Do not expose a SQL
CLI or database UI as a user-facing feature.

## UERR PDF example

For the UERR vestibular PDF, read the entire PDF and propose separate logical
datasets rather than treating all extracted text as one table. At minimum, the
proposal should include:

- an explicit name/code dataset with its original name and code columns; and
- a `resultado_final_vestibular` dataset with columns such as `course`, `shift`,
  `registration`, `name`, `scores`, `rank`, and `category` (split score fields
  further only when the source makes that schema clear).

For each dataset, show its inferred schema, row-count estimate, provenance
fields, caveats, and exactly the first five rows. Set `source_page` to the PDF
page and `source_section` to the heading, table label, or logical result-list
section for each row. Preserve any unclear score, rank, category, or code as
text, or use `NULL` with a documented caveat when it cannot be determined; do
not fill gaps from assumptions. This is document-derived data: wait for the
user's explicit approval before calling `persist-json`. A rejection creates no
DuckDB table.

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

- Keep Source Summary pages factual. Interpretation belongs in concept and
  synthesis pages.
- When a new source contradicts an existing page, update the page and note both
  sources. Never silently discard the old claim.
- For PDFs/images, use the `document-processing` umbrella tools (pymupdf,
  marker-pdf, markitdown) or OCR; verbatim extraction is preferred.
- Web research: fetch the README via `curl` raw, or the GitHub API for
  metadata. Save a copy under `raw/`.
