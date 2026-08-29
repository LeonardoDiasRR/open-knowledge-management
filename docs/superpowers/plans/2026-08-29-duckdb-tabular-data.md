# DuckDB Tabular Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic DuckDB storage and wiki guidance for tabular files and tabular data extracted from ordinary documents.

**Architecture:** Keep the agent-facing behavior in `SKILL.md`, the ingest reference, `README.md`, and the generated `AGENTS.md` template. Add one Python helper that owns DuckDB writes, supported-file parsing, identifier sanitization, provenance, source reconstruction, previews, and read-only queries. The agent keeps responsibility for document interpretation and approval of document-derived datasets.

**Tech Stack:** Python 3, DuckDB Python package, `openpyxl` for XLSX inspection including formula detection, Python standard library `csv`/`unittest`/`pathlib`, Markdown, YAML frontmatter.

## Global Constraints

- Database path: `<wiki-root>/database/data.duckdb`.
- One database contains tables derived from all sources.
- CSV/TSV and genuinely tabular XLSX content are persisted without approval; the agent shows the result afterward, including the first five rows and the wiki page.
- Tables or tabulatable text extracted from ordinary documents require approval before persistence. The proposal includes the schema and first five rows.
- A source produces one table per logical dataset. An Excel workbook produces one table per tabular worksheet.
- Reingesting a source reconstructs only the tables owned by that source and does not duplicate rows or affect other sources.
- Data access is exclusively through natural-language requests handled by the agent.
- Each data row includes `source_id`, `source_page`, and `source_section`; Excel rows additionally include `source_sheet`.
- Ambiguous values remain text when possible and become `NULL` only when they cannot be determined. Every such decision is recorded in the source page.
- Cells whose values are produced by formulas or aggregations are not persisted in DuckDB. Only their input columns are stored; calculations are performed at query time.
- Formula definitions and their equivalent DuckDB SQL are documented only in the source page, not in the database or its catalog.
- The original source under `raw/` is immutable.
- No SQL CLI or database UI is added for users; the agent is the only query interface.
- The helper accepts source paths only after the source has been copied under the configured wiki `raw/` directory.

---

## File Map

- `requirements.txt`: runtime and test dependencies for the helper.
- `scripts/tabular.py`: the deterministic parser, DuckDB persistence layer, catalog manager, preview generator, source rebuild operation, and read-only query entry point.
- `SKILL.md`: agent decision matrix, configuration, ingest/query rules, provenance and formula rules.
- `references/ingest-workflow.md`: step-by-step operational workflow for direct tabular files and document-derived candidates.
- `README.md`: user-facing capability summary, wiki layout, dependency installation, and agent-query usage.
- `scripts/scaffold.py`: self-contained `AGENTS.md` template carrying the tabular rules into new wikis.
- `tests/test_tabular.py`: helper tests covering parsing, formulas, persistence, provenance, rebuilds, transactions, and read-only queries.
- `tests/test_skill_contract.py`: static contract checks ensuring the agent instructions and generated template mention the required behavior.

The work is intentionally kept in one helper and existing documentation files. No separate service, database server, wiki table directory, migration framework, or user SQL interface is introduced.

## Phase 1: Dependency Contract

> **Execution:** Executed by 1 independent subagent. This phase must finish before Phase 2.

### Task 1: Declare Runtime Dependencies

**Files:**
- Create: `requirements.txt`

**Interfaces:**
- Produces installable packages `duckdb>=1.0,<2` and `openpyxl>=3.1,<4` for the helper and tests.
- Does not add a CLI framework, pandas, or a second database driver.

- [ ] **Step 1: Write the dependency file**

Create exactly:

```text
duckdb>=1.0,<2
openpyxl>=3.1,<4
```

- [ ] **Step 2: Verify the dependency file is parseable**

Run:

```powershell
python -m pip install --dry-run -r requirements.txt
```

Expected: pip resolves both packages without reporting malformed requirement syntax. If the environment does not support `--dry-run`, run `python -m pip install -r requirements.txt` and record the result.

- [ ] **Step 3: Commit**

```powershell
git add requirements.txt
git commit -m "build: declare DuckDB tabular dependencies"
```

## Phase 2: Deterministic Data Helper

> **Execution:** Executed by 1 independent subagent. MUST run after Phase 1. This phase must finish before Phase 3.

### Task 2: Implement Tabular Storage Helper

**Files:**
- Create: `scripts/tabular.py`

**Interfaces:**
- Produces the following public types and functions for later documentation and tests:

```python
@dataclass(frozen=True)
class FormulaDefinition:
    column: str
    formula: str
    inputs: tuple[str, ...]
    sql: str | None

@dataclass
class Dataset:
    name: str
    columns: list[str]
    rows: list[dict[str, object]]
    source_page: int | None = None
    source_section: str | None = None
    source_sheet: str | None = None
    formulas: list[FormulaDefinition] = field(default_factory=list)

@dataclass(frozen=True)
class TableManifest:
    table_name: str
    dataset_name: str
    row_count: int
    columns: list[tuple[str, str]]
    sample: list[dict[str, object]]

def sanitize_identifier(value: str) -> str: ...
def load_tabular_file(path: Path, source_id: str) -> list[Dataset]: ...
def persist_source(
    db_path: Path,
    source_id: str,
    source_resource: Path,
    summary_page: str,
    datasets: Sequence[Dataset],
) -> list[TableManifest]: ...
def rebuild_source(
    db_path: Path,
    source_id: str,
    source_resource: Path,
    summary_page: str,
    datasets: Sequence[Dataset],
) -> list[TableManifest]: ...
def query_read_only(
    db_path: Path,
    sql: str,
    parameters: Sequence[object] = (),
) -> list[dict[str, object]]: ...
```

- `load_tabular_file` reads `.csv`, `.tsv`, and `.xlsx`. CSV/TSV produce one dataset. XLSX produces one dataset per worksheet that has a header row and at least one data row; non-tabular worksheets are omitted.
- `persist_source` is used for a new source. `rebuild_source` is used for a source already present in `_openkm_sources`; both write the source and all owned tables in one transaction. The caller invokes these only after the approval policy has been applied.
- `Dataset.formulas` is returned for wiki documentation only. Formula definitions and cached formula values must never be inserted into `_openkm_sources`, `_openkm_tables`, or data tables.
- `query_read_only` rejects write statements and opens DuckDB in read-only mode. It supports `SELECT`, read-only `WITH`, `DESCRIBE`, and `SHOW` statements and returns rows keyed by result-column name.

- [ ] **Step 1: Write the failing smoke check**

Before implementing the module, run:

```powershell
python -c "from pathlib import Path; import scripts.tabular as t; assert t.sanitize_identifier('Área 1 (Notas)') == 'area_1_notas'"
```

Expected: FAIL because `scripts/tabular.py` does not yet exist.

- [ ] **Step 2: Implement imports, dataclasses, and identifier sanitization**

Use `from __future__ import annotations`, `Path`, `csv`, `json`, `re`, `sqlite`-free standard-library code, `unicodedata`, `dataclasses`, and DuckDB. `sanitize_identifier` must:

```python
def sanitize_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_value).strip("_").lower()
    slug = slug or "unnamed"
    if slug[0].isdigit():
        slug = "col_" + slug
    return slug
```

When sanitizing a list of identifiers, append `_2`, `_3`, and so on for collisions in source order. Never use an unsanitized table or column identifier in SQL.

- [ ] **Step 3: Implement CSV and TSV loading**

Use `csv.Sniffer` only as a fallback; `.tsv` defaults to a tab delimiter and `.csv` defaults to a comma. Read UTF-8 with `utf-8-sig`, use the first non-empty row as headers, preserve original headers in the `Dataset.columns` list, and create row dictionaries keyed by original headers. Empty fields become `None`; values that cannot be safely inferred remain strings. Do not treat a cell beginning with `=` as a formula in CSV/TSV because the format does not carry formula metadata.

Return `[]` for a file with no header and no data. Raise a descriptive `ValueError` for an inconsistent row width instead of silently shifting cells.

- [ ] **Step 4: Implement XLSX worksheet loading and formula exclusion**

Use `openpyxl.load_workbook(path, read_only=False, data_only=False)` so formula expressions are available. For each worksheet:

1. Find the first non-empty row and use it as headers.
2. Treat later rows with at least one non-empty cell as data.
3. Mark a column as formula-derived if any non-empty cell in that column has `cell.data_type == "f"`.
4. Exclude the formula-derived column and all cached formula results from `Dataset.columns` and `Dataset.rows`.
5. Keep non-formula input columns and their values.
6. Add a `FormulaDefinition` for every excluded formula column. Preserve the original formula text, list the input headers referenced by simple cell references, and produce an equivalent SQL expression for direct arithmetic and `SUM`, `AVERAGE`, and standard-deviation formulas. Use `sql=None` if safe translation is not possible.
7. Set `Dataset.source_sheet` to the original worksheet title.

A worksheet counts as non-tabular when it has no header plus data rows. Ignore it without creating a table. Do not store the formula result even when `openpyxl` exposes a cached value.

- [ ] **Step 5: Implement type inference and provenance injection**

Implement a small `_infer_type(values)` helper with these rules:

- all non-null booleans -> `BOOLEAN`;
- all non-null integers -> `BIGINT`;
- all non-null numbers -> `DOUBLE`;
- all non-null values parsed as ISO dates -> `DATE`;
- otherwise -> `VARCHAR`.

Do not infer numbers from strings containing leading zeroes or identifiers. Keep mixed columns as `VARCHAR`. During persistence, inject these columns into every row without allowing source data to override them:

```text
source_id       VARCHAR
source_page     BIGINT NULL
source_section  VARCHAR NULL
source_sheet    VARCHAR NULL
```

`source_id` comes from the function argument. `source_page`, `source_section`, and `source_sheet` come from the dataset metadata. Preserve `None` for inapplicable values.

- [ ] **Step 6: Implement catalog creation and deterministic table names**

Create the database parent directory and DuckDB file on demand. Create these internal tables:

```sql
CREATE TABLE IF NOT EXISTS _openkm_sources (
    source_id VARCHAR PRIMARY KEY,
    source_resource VARCHAR NOT NULL,
    summary_page VARCHAR NOT NULL,
    content_checksum VARCHAR NOT NULL,
    ingested_at TIMESTAMP NOT NULL,
    extraction_status VARCHAR NOT NULL
)
```

```sql
CREATE TABLE IF NOT EXISTS _openkm_tables (
    table_name VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    dataset_name VARCHAR NOT NULL,
    schema_json VARCHAR NOT NULL,
    row_count BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
)
```

Generate table names as `<source_slug>__<dataset_slug>`, using stable collision suffixes. The source slug comes from `source_id`; the dataset slug comes from `Dataset.name`. Record only sanitized names and schema metadata in `_openkm_tables`; never store formula definitions there. Calculate the source checksum from the raw source bytes.

- [ ] **Step 7: Implement transactional persistence and source rebuild**

Within one transaction:

1. Ensure catalog tables exist.
2. For a new source, reject an existing `source_id` with a clear error and direct the caller to `rebuild_source`.
3. For a rebuild, query `_openkm_tables` for the `source_id`, drop only those quoted table identifiers, and delete that source's catalog rows.
4. Create each data table with sanitized columns plus the four provenance columns.
5. Insert rows using parameterized `executemany` calls.
6. Insert source/table catalog rows and return `TableManifest` values whose samples contain at most the first five rows in source order.
7. Commit only after every dataset succeeds; rollback on any exception and re-raise an error that includes the source identifier.

Do not use `DROP SCHEMA`, delete other source catalog rows, or interpolate row values into SQL. Quote only identifiers that have already passed sanitization.

- [ ] **Step 8: Implement read-only query execution**

Reject SQL containing statement keywords that can mutate state (`INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`, `ALTER`, `COPY`, `ATTACH`, `INSTALL`, `LOAD`, `EXPORT`, `VACUUM`, or `PRAGMA`) and reject multiple statements. Open the database with `duckdb.connect(str(db_path), read_only=True)`, bind `parameters`, and return dictionaries from `cursor.description` and fetched rows. Convert DuckDB values only as needed for JSON output; do not alter stored data.

- [ ] **Step 9: Add a command-line entry point for the agent**

Implement `argparse` subcommands with JSON output:

```text
python scripts/tabular.py inspect-file --source-id ID --file RAW_FILE
python scripts/tabular.py persist-json --db DB --source-id ID --source-resource RAW_FILE --summary-page PAGE --input MANIFEST_JSON
python scripts/tabular.py rebuild-json --db DB --source-id ID --source-resource RAW_FILE --summary-page PAGE --input MANIFEST_JSON
python scripts/tabular.py query --db DB --sql SQL [--parameter VALUE ...]
```

`inspect-file` loads a direct CSV/TSV/XLSX source and prints dataset manifests, five-row samples, and formula definitions without writing DuckDB. `persist-json` and `rebuild-json` accept the approved document dataset manifest and call the matching persistence function. The JSON format must contain `source_id` and a `datasets` array whose dataset objects use the dataclass field names. Never include formula definitions in SQL writes. Exit nonzero and print a useful error to stderr for missing files, invalid JSON, unsupported extensions, invalid source paths, or failed transactions.

- [ ] **Step 10: Run the helper syntax and smoke checks**

Run:

```powershell
python -m py_compile scripts/tabular.py
python -c "from pathlib import Path; import scripts.tabular as t; assert t.sanitize_identifier('Área 1 (Notas)') == 'area_1_notas'; assert t.sanitize_identifier('') == 'unnamed'"
```

Expected: both commands exit with code 0.

- [ ] **Step 11: Commit**

```powershell
git add scripts/tabular.py
git commit -m "feat: add DuckDB tabular storage helper"
```

## Phase 3: Agent Contract and Documentation

> **Execution:** Executed by 4 independent subagents in parallel, one subagent per task, no ordering between tasks. MUST run after Phase 2.

### Task 3: Update Skill Rules

**Files:**
- Modify: `SKILL.md`

**Interfaces:**
- Consumes the helper CLI contract from Task 2.
- Produces the agent rules that decide automatic direct-file persistence versus approval-gated document extraction, invoke the helper, update the source page, and answer queries through the helper.

- [ ] **Step 1: Add database configuration to the existing configuration section**

State that the database is always `<wiki-root>/database/data.duckdb`, is created on demand, and is derived data separate from immutable `raw/`. Do not add a second persisted configuration key because the path is fixed relative to `wiki_root`.

- [ ] **Step 2: Extend the decision matrix and folder structure**

Add tabular-file ingestion and agent data query behavior to the decision matrix. Document `database/` as the derived DuckDB location, not as a Markdown wiki section. Keep the existing `wiki/sources/` location for the source page and preserve all existing OKF directories and reserved names.

- [ ] **Step 3: Replace the ingest procedure with the approved tabular flow**

Add exact rules:

- read the source completely and copy it to `raw/` before helper calls;
- auto-persist genuinely tabular CSV, TSV, and XLSX files without approval;
- create one table per XLSX tabular worksheet;
- inspect ordinary documents for visual tables and tabulatable text;
- show proposed schema and first five rows and require explicit approval for document-derived candidates;
- reconstruct only the source-owned tables on reingestion;
- exclude formula-derived columns, keep input columns, and document the original formulas plus equivalent DuckDB SQL only in the source page;
- record `source_id`, `source_page`, `source_section`, and applicable `source_sheet` on every row;
- update the Source Summary, indexes, and newest-first logs.

- [ ] **Step 4: Add agent query and failure rules**

Require the agent to locate the source page/catalog first, call `query` read-only, preserve source context in answers, and link the source page. State that missing DuckDB support, unsupported formats, malformed input, rejected proposals, and transaction failures must be reported without claiming data was saved.

- [ ] **Step 5: Verify the contract text**

Run:

```powershell
python -c "from pathlib import Path; p=Path('SKILL.md').read_text(encoding='utf-8'); required=['database/data.duckdb','source_page','source_section','source_sheet','first five rows','formula']; assert all(x in p for x in required)"
```

Expected: exit code 0.

- [ ] **Step 6: Commit**

```powershell
git add SKILL.md
git commit -m "docs: define DuckDB behavior in the skill"
```

### Task 4: Update Ingest Workflow Reference

**Files:**
- Modify: `references/ingest-workflow.md`

**Interfaces:**
- Consumes the helper input/output contract from Task 2 and the policy from the approved design.
- Produces an operational workflow that an agent can follow without inferring approval, provenance, formula, or reingestion behavior.

- [ ] **Step 1: Add direct tabular file workflow**

Document the sequence: read and copy to `raw/`, call `inspect-file`, verify tabularity, persist automatically with `persist-json` or the direct helper path, show the first five rows, and update the source page/index/log. State that non-tabular CSV/XLSX follows ordinary document candidate analysis instead of automatic persistence.

- [ ] **Step 2: Add document candidate workflow**

Document explicit visual table detection and inferred tabulatable text detection. Require the proposal to show logical dataset names, original columns, inferred types, row count estimate, provenance fields, caveats, and exactly the first five rows before asking for approval. Call `persist-json` only after approval; do not create a table after rejection.

- [ ] **Step 3: Add formula and data-quality rules**

State that formula result cells and aggregate cells are excluded from DuckDB, input columns remain, and the Source Summary records formula text and equivalent SQL. State that ambiguous values stay text or become `NULL` with a caveat, and no value may be invented.

- [ ] **Step 4: Add reingestion, error, and example sections**

Document source-owned rebuilds, transaction rollback, raw immutability, and read-only agent queries. Include a compact UERR PDF example with logical datasets such as `resultado_final_vestibular`, columns for course/shift/registration/name/scores/rank/category, and page/section provenance. Make clear that the PDF-derived proposal waits for approval.

- [ ] **Step 5: Verify the reference**

Run:

```powershell
python -c "from pathlib import Path; p=Path('references/ingest-workflow.md').read_text(encoding='utf-8'); required=['persist-json','first five rows','source_page','source_section','formula','approval']; assert all(x in p for x in required)"
```

Expected: exit code 0.

- [ ] **Step 6: Commit**

```powershell
git add references/ingest-workflow.md
git commit -m "docs: document tabular ingest workflow"
```

### Task 5: Update README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes the fixed path and access policy from the spec.
- Produces concise user-facing documentation; it must not promise a SQL CLI or a separate table-page directory.

- [ ] **Step 1: Add DuckDB to the capability table**

Describe automatic CSV/TSV/XLSX persistence, approval-gated extraction from PDFs and other documents, one table per logical dataset/worksheet, row provenance, formula exclusion, and agent-only querying.

- [ ] **Step 2: Update the directory tree**

Add `database/data.duckdb` as derived data under the wiki root. Keep `raw/` immutable and `wiki/sources/` as the location of source-summary pages. Explicitly state that no `wiki/tables/` directory is created.

- [ ] **Step 3: Add dependency and usage instructions**

Document `python -m pip install -r requirements.txt` for the helper environment. Explain that a user asks the agent natural-language questions; the agent queries DuckDB and links the source page. Do not provide a user SQL command.

- [ ] **Step 4: Verify the README**

Run:

```powershell
python -c "from pathlib import Path; p=Path('README.md').read_text(encoding='utf-8'); required=['data.duckdb','raw/','wiki/sources/','formula','natural-language']; assert all(x in p for x in required)"
```

Expected: exit code 0.

- [ ] **Step 5: Commit**

```powershell
git add README.md
git commit -m "docs: describe DuckDB tabular data support"
```

### Task 6: Update Generated AGENTS Template

**Files:**
- Modify: `scripts/scaffold.py`

**Interfaces:**
- Consumes the same helper contract as Task 2.
- Produces fresh/adopted wiki `AGENTS.md` content with the tabular rules while preserving existing scaffold behavior and never creating a database during scaffold.

- [ ] **Step 1: Extend the architecture template**

Add `database/data.duckdb` as derived data and preserve `raw/` immutability. State that tabular source pages remain in `wiki/sources/`.

- [ ] **Step 2: Extend the generated ingest rules**

Add automatic CSV/TSV/XLSX behavior, one table per logical dataset or worksheet, ordinary-document approval, first-five-row proposals, provenance columns, formula-derived column exclusion, formula SQL documentation in the source page only, and source-owned reingestion.

- [ ] **Step 3: Extend generated query and error rules**

State that the agent is the only query interface and that helper failures, unsupported formats, and rejected proposals must not be reported as successful writes. Keep the current adopt-mode and index/log rules unchanged.

- [ ] **Step 4: Verify fresh and adopt scaffolds**

Run:

```powershell
$root = Join-Path $env:TEMP ('openkm-tabular-scaffold-' + [guid]::NewGuid())
python scripts/scaffold.py --root $root
python -c "from pathlib import Path; import sys; p=Path(sys.argv[1])/'AGENTS.md'; t=p.read_text(encoding='utf-8'); required=['data.duckdb','first five rows','source_page','formula']; assert all(x in t for x in required)" $root
Remove-Item -LiteralPath $root -Recurse -Force
```

Expected: scaffold succeeds, generated `AGENTS.md` contains all required rules, and no `database/data.duckdb` is created by scaffold alone.

- [ ] **Step 5: Commit**

```powershell
git add scripts/scaffold.py
git commit -m "docs: propagate tabular rules to wiki agents"
```

## Phase 4: Automated Tests

> **Execution:** Executed by 2 independent subagents in parallel, one subagent per task, no ordering between tasks. MUST run after Phase 3.

### Task 7: Test Helper Behavior

**Files:**
- Create: `tests/test_tabular.py`

**Interfaces:**
- Consumes the public functions and dataclasses from `scripts/tabular.py` exactly as defined in Task 2.
- Produces executable `unittest` coverage for the persistence contract.

- [ ] **Step 1: Create test setup helpers**

Create a `unittest.TestCase` using `TemporaryDirectory`, write source files under `<temp>/raw/`, and use `<temp>/database/data.duckdb`. Import `Dataset`, `FormulaDefinition`, `load_tabular_file`, `persist_source`, `rebuild_source`, `query_read_only`, and `sanitize_identifier`.

- [ ] **Step 2: Add identifier and CSV tests**

Include these concrete tests:

```python
def test_sanitize_identifier_and_collisions(self):
    self.assertEqual(sanitize_identifier("Área 1 (Notas)"), "area_1_notas")
    self.assertEqual(sanitize_identifier(""), "unnamed")

def test_load_csv_preserves_rows_and_empty_values(self):
    path = self.raw / "scores.csv"
    path.write_text("Name,Code,Value\nAna,0012,\n", encoding="utf-8")
    datasets = load_tabular_file(path, "scores")
    self.assertEqual(datasets[0].columns, ["Name", "Code", "Value"])
    self.assertEqual(datasets[0].rows[0]["Code"], "0012")
    self.assertIsNone(datasets[0].rows[0]["Value"])
```

- [ ] **Step 3: Add XLSX and formula tests**

Create a workbook with `openpyxl`, one tabular worksheet and one empty worksheet. Put `=SUM(B2:C2)` in a `Total` column and assert:

```python
datasets = load_tabular_file(workbook, "book")
self.assertEqual([d.source_sheet for d in datasets], ["Results"])
self.assertNotIn("Total", datasets[0].columns)
self.assertNotIn("Total", datasets[0].rows[0])
self.assertEqual(datasets[0].formulas[0].formula, "=SUM(B2:C2)")
self.assertIsNotNone(datasets[0].formulas[0].sql)
```

Also assert that the empty worksheet creates no dataset. The test must never use the cached formula result as a persisted value.

- [ ] **Step 4: Add persistence, provenance, and preview tests**

Persist two `Dataset` instances from one source and assert that:

- the database exists at `database/data.duckdb`;
- `_openkm_sources` contains one source;
- `_openkm_tables` contains two owned tables;
- each data table includes the four provenance columns;
- `source_id`, page, section, and sheet values are present on every row;
- each returned manifest has at most five sample rows;
- the formula definition is absent from every DuckDB catalog/data table.

- [ ] **Step 5: Add rebuild and isolation tests**

Persist source `one`, persist source `two`, then rebuild `one` with changed rows. Query catalog and data tables and assert that source `one` has only the new rows and source `two` still has its original rows. Assert that table count does not increase after repeated rebuilds.

- [ ] **Step 6: Add rollback and read-only query tests**

Construct a dataset that fails during table insertion after one valid dataset and assert that the source has no newly committed catalog/data rows. Assert that `query_read_only` returns rows for a `SELECT`, accepts bound parameters, and raises `ValueError` for `INSERT`, `CREATE`, and multiple statements.

- [ ] **Step 7: Run the test file**

Run:

```powershell
python -m unittest -v tests.test_tabular
```

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 8: Commit**

```powershell
git add tests/test_tabular.py
git commit -m "test: cover DuckDB tabular persistence"
```

### Task 8: Test Documentation Contract

**Files:**
- Create: `tests/test_skill_contract.py`

**Interfaces:**
- Consumes the text of `SKILL.md`, `references/ingest-workflow.md`, `README.md`, and the `AGENTS_MD` constant in `scripts/scaffold.py`.
- Produces static tests for requirements that are intentionally expressed as agent instructions rather than runtime code.

- [ ] **Step 1: Add a shared required-term assertion**

Implement a helper that reads each file as UTF-8 and asserts all required terms exist. Use explicit terms, not a vague snapshot:

```python
COMMON = [
    "database/data.duckdb",
    "first five rows",
    "source_page",
    "source_section",
    "formula",
]
```

- [ ] **Step 2: Test automatic direct-file behavior**

Assert that the skill/reference/README text contains `CSV`, `TSV`, `XLSX`, and `without approval` or equivalent wording. Assert that the workflow contains `persist-json` and `inspect-file`.

- [ ] **Step 3: Test approval and formula behavior**

Assert that the skill/reference/template mention approval for ordinary documents, exclusion of formula-derived values/columns, retaining input columns, and equivalent DuckDB SQL in the source page. Assert that at least one document says formula metadata is not stored in DuckDB.

- [ ] **Step 4: Test wiki and access behavior**

Assert that README and skill text mention `wiki/sources/`, immutable `raw/`, natural-language agent queries, and no user SQL interface. Assert that `scripts/scaffold.py` still contains `--adopt` and `write_if_missing`.

- [ ] **Step 5: Run the documentation tests**

Run:

```powershell
python -m unittest -v tests.test_skill_contract
```

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_skill_contract.py
git commit -m "test: verify tabular skill documentation contract"
```

## Final Verification

After Phase 4, the orchestrator runs this checklist. It is not a task or phase because it modifies no file and exists only as the final verification gate for Tasks 1-8.

- [ ] **Step 1: Run all Python tests**

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: zero failures and zero errors.

- [ ] **Step 2: Run syntax checks**

```powershell
python -m py_compile scripts/scaffold.py scripts/tabular.py tests/test_tabular.py tests/test_skill_contract.py
```

Expected: exit code 0 and no traceback.

- [ ] **Step 3: Check whitespace and inspect the final diff**

```powershell
git diff --check origin/main...HEAD
git status --short --branch
git log --oneline -10
```

Expected: no whitespace errors; only intended implementation files and commits are present; no generated `data.duckdb` or temporary wiki is tracked.

- [ ] **Step 4: Run the direct-file acceptance scenario**

Run this self-contained PowerShell scenario, then remove its temporary directory:

```powershell
$root = Join-Path $env:TEMP ('openkm-csv-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path (Join-Path $root 'raw') -Force | Out-Null
@"
Name,Code,Value
Ana,0012,10
Bruno,0013,20
Carla,0014,30
Diego,0015,40
Eva,0016,50
Fabio,0017,60
"@ | Set-Content -LiteralPath (Join-Path $root 'raw/scores.csv') -Encoding utf8
python scripts/tabular.py inspect-file --source-id scores --file (Join-Path $root 'raw/scores.csv')
Remove-Item -LiteralPath $root -Recurse -Force
```

Expected: inspection succeeds, reports one dataset and at most five sample rows, and does not create a database before persistence.

- [ ] **Step 5: Run the formula acceptance scenario**

Run the following Python scenario and inspect its assertions:

```powershell
$root = Join-Path $env:TEMP ('openkm-xlsx-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path (Join-Path $root 'raw') -Force | Out-Null
$env:OPENKM_TEST_ROOT = $root
$script = @'
import os
from pathlib import Path
from openpyxl import Workbook
from scripts.tabular import load_tabular_file

path = Path(os.environ["OPENKM_TEST_ROOT"]) / "raw" / "formula.xlsx"
book = Workbook()
sheet = book.active
sheet.title = "Results"
sheet.append(["A", "B", "Total"])
sheet.append([2, 3, "=SUM(A2:B2)"])
book.save(path)
datasets = load_tabular_file(path, "formula")
assert datasets[0].columns == ["A", "B"]
assert "Total" not in datasets[0].rows[0]
assert datasets[0].formulas[0].formula == "=SUM(A2:B2)"
assert datasets[0].formulas[0].sql is not None
'@
python -c $script
Remove-Item -LiteralPath $root -Recurse -Force
Remove-Item Env:OPENKM_TEST_ROOT
```

Expected: the formula column is absent from the dataset and its cached result is never read as data; the formula and a safe SQL equivalent are available for the wiki page.

- [ ] **Step 6: Run the UERR document acceptance checklist**

Using the supplied parsed PDF text as the fixture, manually verify that the agent workflow proposes the explicit name/code table and logical vestibular result datasets, displays five rows, includes page/section provenance, documents ambiguous values without invention, and waits for approval before calling `persist-json`. This scenario must not write a table before approval.

- [ ] **Step 7: Final status check**

```powershell
git status --short --branch
```

Expected: clean worktree with no untracked database or temporary files.
