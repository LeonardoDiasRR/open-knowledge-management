# Data Normalization & Typing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize and type date, timestamp, CPF, CNPJ, CEP and phone columns before persisting tabular datasets into DuckDB.

**Architecture:** New pure module `scripts/normalizers.py` (stdlib only) holds parsing/detection/normalization. `scripts/tabular.py` changes only in 3 wiring points (`_infer_type`, `_typed_value`, `_persist` + manifest). Kind is decided once per column before `CREATE TABLE`.

**Tech Stack:** Python 3 stdlib (`re`, `datetime`, `unicodedata`), DuckDB (`duckdb>=1.0,<2`, already in requirements), pytest (runs the existing `unittest` suite).

**Spec:** `docs/superpowers/specs/2026-09-02-data-normalization-design.md` (commit a16f6bd). The prototype behind the code below was validated 2026-09-02: 30/30 normalization cases, 13/13 detection cases, real DuckDB 1.5.5 roundtrip.

**Working directory for every command:** `/opt/segundo_cerebro_mitra/projetos/OpenKM` (repo root; system `python3` has `duckdb` and `openpyxl` — no venv).

**Baseline to match before and after:** `python3 -m pytest tests/ -q` → `18 passed, 59 subtests passed`.

---

### Task 1: `normalizers.py` — temporal parsing (`parse_temporal`)

**Files:**
- Create: `scripts/normalizers.py`
- Test: `tests/test_normalizers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_normalizers.py`:

```python
"""Tests for the pure normalizer module (no DuckDB, no filesystem)."""
import unittest
from datetime import date, datetime, timedelta, timezone

from scripts.normalizers import parse_temporal


class ParseTemporalTests(unittest.TestCase):
    def assert_temporal(self, raw, expected, has_time):
        result = parse_temporal(raw)
        self.assertIsNotNone(result, f"should parse {raw!r}")
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1], has_time)

    def test_iso_date(self):
        self.assert_temporal("2026-09-02", date(2026, 9, 2), False)

    def test_iso_with_time_and_microseconds(self):
        self.assert_temporal(
            "2026-09-02T14:30:15.250",
            datetime(2026, 9, 2, 14, 30, 15, 250000),
            True,
        )

    def test_brazilian_separators(self):
        self.assert_temporal("02/09/2026", date(2026, 9, 2), False)
        self.assert_temporal("02-09-2026", date(2026, 9, 2), False)
        self.assert_temporal("02.09.2026", date(2026, 9, 2), False)

    def test_two_digit_year_becomes_2000s(self):
        self.assert_temporal("02-09-26", date(2026, 9, 2), False)

    def test_ambiguous_prefers_brazilian_day_first(self):
        self.assert_temporal("01/02/2026", date(2026, 2, 1), False)
        self.assert_temporal("15/03/2026", date(2026, 3, 15), False)

    def test_year_first_with_slashes(self):
        self.assert_temporal("2026/09/02", date(2026, 9, 2), False)

    def test_written_out_ptbr(self):
        self.assert_temporal("2 de setembro de 2026", date(2026, 9, 2), False)
        self.assert_temporal("2 DE SETEMBRO DE 2026", date(2026, 9, 2), False)
        self.assertIsNone(parse_temporal("2 de setembro"))  # no year -> unrecoverable

    def test_abbreviated_month_with_separators(self):
        self.assert_temporal("02/set/2026", date(2026, 9, 2), False)
        self.assert_temporal("02/set.2026", date(2026, 9, 2), False)
        self.assert_temporal("02.out.26", date(2026, 10, 2), False)

    def test_time_after_brazilian_date(self):
        self.assert_temporal("02/09/2026 14:30", datetime(2026, 9, 2, 14, 30), True)
        self.assert_temporal(
            "02/09/2026 14:30:15.250",
            datetime(2026, 9, 2, 14, 30, 15, 250000),
            True,
        )

    def test_timezone_offsets_are_converted_to_utc_naive(self):
        self.assert_temporal("2026-09-02T14:30:00-04:00", datetime(2026, 9, 2, 18, 30), True)
        self.assert_temporal("2026-09-02T14:30:00Z", datetime(2026, 9, 2, 14, 30), True)

    def test_invalid_utc_offset_is_unrecoverable(self):
        self.assertIsNone(parse_temporal("2026-09-02T14:30:00+24:00"))
        self.assertIsNone(parse_temporal("2026-09-02T14:30:00-99:00"))

    def test_aware_datetime_is_converted_to_utc_naive(self):
        aware = datetime(2026, 9, 2, 14, 30, tzinfo=timezone(timedelta(hours=-4)))
        self.assert_temporal(aware, datetime(2026, 9, 2, 18, 30), True)

    def test_python_objects_pass_through(self):
        self.assert_temporal(date(2026, 9, 2), date(2026, 9, 2), False)
        self.assert_temporal(
            datetime(2026, 9, 2, 14, 30), datetime(2026, 9, 2, 14, 30), True
        )

    def test_invalid_values_return_none(self):
        for raw in ("31/02/2025", "s/ data", "", "—", "sem data", "n/a", None, 123):
            self.assertIsNone(parse_temporal(raw), f"should not parse {raw!r}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_normalizers.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'scripts.normalizers'` (or ImportError on `parse_temporal`).

- [ ] **Step 3: Write the minimal implementation**

Create `scripts/normalizers.py`. This is the final validated code (prototype fixes included: timezone as `timedelta`, correct group indexing, abbreviated-month branch before numeric branch):

```python
"""Pure, deterministic cell normalizers for OpenKM tabular ingestion.

No DuckDB, no filesystem, no third-party imports. Every function is
idempotent: normalize_cell(normalize_cell(v, k), k) == normalize_cell(v, k).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Sequence

ColumnKind = Literal["date", "timestamp", "cpf", "cnpj", "cep", "telefone"]

KIND_SQL_TYPE: dict[str, str] = {
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "cpf": "VARCHAR",
    "cnpj": "VARCHAR",
    "cep": "VARCHAR",
    "telefone": "VARCHAR",
}

BLANK_TOKENS = frozenset(
    {"", "-", "--", "s/ data", "s/data", "sem data", "n/a", "na", "null", "none"}
)

_MONTHS = {
    name: number
    for number, name in enumerate(
        "janeiro fevereiro marco abril maio junho julho agosto setembro "
        "outubro novembro dezembro".split(),
        1,
    )
}
_MONTH_ABBREV = {name[:3]: number for name, number in _MONTHS.items()}

_TIME_SUFFIX = (
    r"(?:[T ](\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?\s*(Z|[+-]\d{2}:?\d{2})?)?"
)
_ISO = re.compile(rf"^(\d{{4}})-(\d{{1,2}})-(\d{{1,2}}){_TIME_SUFFIX}$")
_NUMERIC = re.compile(rf"^(\d{{1,4}})[/.\-](\d{{1,2}})[/.\-](\d{{2,4}}){_TIME_SUFFIX}$")
_MONTH_NAME = re.compile(rf"^(\d{{1,2}})[/.-]([a-zç]{{3,9}})[/.-](\d{{2,4}}){_TIME_SUFFIX}$", re.IGNORECASE)
_WRITTEN = re.compile(r"^(\d{1,2})\s+de\s+([a-zç]+)\.?(?:\s+de\s+)?(\d{4})$", re.IGNORECASE)


def is_blank(value: object) -> bool:
    return value is None or str(value).strip().lower() in BLANK_TOKENS


def _month_name(token: str) -> int | None:
    token = token.lower().replace("ç", "c")
    return _MONTHS.get(token) or _MONTH_ABBREV.get(token[:3])


def _timezone(offset: str | None):
    if not offset:
        return None
    if offset == "Z":
        return timezone.utc
    sign = 1 if offset[0] == "+" else -1
    digits = offset[1:].replace(":", "")
    try:
        return timezone(sign * timedelta(seconds=int(digits[:2]) * 3600 + int(digits[2:]) * 60))
    except ValueError:
        return None  # e.g. +24:00 — cell is unrecoverable, caller must NULL it


def _build(day: int, month: int, year: object, hour, minute, second, fraction, offset):
    year = int(year)
    if year < 100:
        year += 2000
    try:
        moment = datetime(
            year,
            int(month),
            int(day),
            int(hour or 0),
            int(minute or 0),
            int(second or 0),
            int(str(fraction or 0).ljust(6, "0")[:6]) if fraction else 0,
        )
    except ValueError:
        return None
    zone = _timezone(offset)
    if offset and zone is None:
        return None
    if zone is not None:
        moment = moment.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def _outcome(moment: datetime | None, has_time: bool):
    if moment is None:
        return None
    return (moment, True) if has_time else (moment.date(), False)


def parse_temporal(value: object) -> tuple[date | datetime, bool] | None:
    """Parse a cell into (date|datetime, has_explicit_time); None if unparseable.

    Date-only values return a `date`; anything with an explicit time (or a
    datetime input) returns a naive `datetime` (tz offsets converted to UTC).
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None), True
    if isinstance(value, date):
        return value, False
    if not isinstance(value, str):
        return None
    text = value.strip().rstrip(".")
    if is_blank(text):
        return None

    match = _ISO.match(text)
    if match:
        return _outcome(
            _build(int(match.group(3)), int(match.group(2)), match.group(1), *match.groups()[3:]),
            bool(match.group(4)),
        )

    match = _MONTH_NAME.match(text)
    if match:
        month = _month_name(match.group(2))
        if month is None:
            return None
        return _outcome(
            _build(int(match.group(1)), month, match.group(3), *match.groups()[3:]),
            bool(match.group(4)),
        )

    match = _WRITTEN.match(text)
    if match:
        month = _month_name(match.group(2))
        if month is None:
            return None
        return _outcome(_build(int(match.group(1)), month, int(match.group(3)), None, None, None, None, None), False)

    match = _NUMERIC.match(text)
    if match:
        first, second, year_text = match.group(1), int(match.group(2)), match.group(3)
        tail = match.groups()[3:]
        if len(first) == 4:  # YYYY first: YYYY/MM/DD -> day=group3, month=group2
            moment = _build(int(year_text), second, first, *tail)
        else:  # pt-BR: day first (validated rule, no US fallback)
            moment = _build(int(first), second, year_text, *tail)
        return _outcome(moment, bool(match.group(4)))

    return None
```

Notes:
- `_MONTH_NAME` uses a single `[/.-]` between month and year so both `02/set/2026` and `02.out.26` match.
- The yearless written form (`2 de setembro`) does NOT parse — a yearless date in a date column is an unrecoverable cell (NULL + example in the report), never a fake year.
- `_build` returning `None` on calendar-invalid dates (it catches `ValueError`) is the only rejection path for numerics; pt-BR day-first is the sole order attempted — `31/02/2025` → None. Do NOT add a US fallback; the spec fixes pt-BR.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_normalizers.py -q`
Expected: all PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/normalizers.py tests/test_normalizers.py
git commit -m "feat: add temporal parser for tabular normalization"
```

---

### Task 2: `normalizers.py` — `normalize_cell` (documents/phone + date/timestamp coercion)

**Files:**
- Modify: `scripts/normalizers.py` (append)
- Test: `tests/test_normalizers.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_normalizers.py` (inside the imports at top, add `normalize_cell` to the `from scripts.normalizers import ...` line):

```python
class NormalizeCellTests(unittest.TestCase):
    def test_cpf_strips_mask_keeps_leading_zero(self):
        self.assertEqual(normalize_cell("123.456.789-09", "cpf"), "12345678909")
        self.assertEqual(normalize_cell("045.106.365-09", "cpf"), "04510636509")
        self.assertEqual(normalize_cell("111.111.111-11", "cpf"), "11111111111")  # no DV check
        self.assertIsNone(normalize_cell("123.456.789-0", "cpf"))

    def test_cnpj_strips_mask(self):
        self.assertEqual(normalize_cell("12.345.678/0001-95", "cnpj"), "12345678000195")
        self.assertIsNone(normalize_cell("12.345.678/0001-9", "cnpj"))

    def test_cep(self):
        self.assertEqual(normalize_cell("01310-100", "cep"), "01310100")
        self.assertIsNone(normalize_cell("01310-10", "cep"))

    def test_phone_completes_ddi_only_for_10_or_11_digits(self):
        self.assertEqual(normalize_cell("(11) 3456-7890", "telefone"), "551134567890")
        self.assertEqual(normalize_cell("11 99999-8888", "telefone"), "5511999998888")
        self.assertEqual(normalize_cell("+55 (11) 98765-4321", "telefone"), "5511987654321")
        self.assertEqual(normalize_cell("551134567890", "telefone"), "551134567890")  # idempotent
        self.assertEqual(normalize_cell("9999-9999", "telefone"), "99999999")  # 8 digits: keep as-is

    def test_document_blanks_and_none(self):
        for kind in ("cpf", "cnpj", "cep", "telefone"):
            self.assertIsNone(normalize_cell(None, kind))
            self.assertIsNone(normalize_cell("", kind))
            self.assertIsNone(normalize_cell("s/ data", kind))

    def test_date_kind_returns_date_objects(self):
        self.assertEqual(normalize_cell("02/09/1990", "date"), date(1990, 9, 2))
        self.assertEqual(normalize_cell(datetime(1990, 9, 2, 14, 30), "date"), date(1990, 9, 2))
        self.assertEqual(normalize_cell("2026-09-02", "date"), date(2026, 9, 2))  # idempotent
        self.assertIsNone(normalize_cell("s/ data", "date"))

    def test_timestamp_kind_returns_datetime(self):
        self.assertEqual(normalize_cell("02/09/2026 14:30", "timestamp"), datetime(2026, 9, 2, 14, 30))
        self.assertEqual(normalize_cell("02/09/2026", "timestamp"), datetime(2026, 9, 2, 0, 0))
        self.assertEqual(
            normalize_cell("2026-09-02T14:30:00-04:00", "timestamp"),
            datetime(2026, 9, 2, 18, 30),
        )

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            normalize_cell("x", "placa")


if __name__ == "__main__":
    unittest.main()
```

(Replace the existing trailing `if __name__` block instead of duplicating it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_normalizers.py -q`
Expected: ImportError `cannot import name 'normalize_cell'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/normalizers.py`:

```python
def normalize_cell(value: object, kind: ColumnKind) -> object | None:
    """Normalize one cell for the given kind. None = unrecoverable (stored NULL)."""
    if kind not in KIND_SQL_TYPE:
        raise ValueError(f"unknown normalization kind: {kind!r}")
    if value is None:
        return None
    if kind in ("date", "timestamp"):
        parsed = parse_temporal(value)
        if parsed is None:
            return None
        moment, _has_time = parsed
        if kind == "date":
            return moment.date() if isinstance(moment, datetime) else moment
        return moment if isinstance(moment, datetime) else datetime(moment.year, moment.month, moment.day)
    digits = re.sub(r"\D", "", str(value))
    if kind == "cpf":
        return digits if len(digits) == 11 else None
    if kind == "cnpj":
        return digits if len(digits) == 14 else None
    if kind == "cep":
        return digits if len(digits) == 8 else None
    # telefone
    if not digits:
        return None
    if len(digits) in (10, 11):
        return f"55{digits}"
    return digits
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_normalizers.py -q`
Expected: all PASS (20 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/normalizers.py tests/test_normalizers.py
git commit -m "feat: normalize cpf, cnpj, cep, phone, date and timestamp cells"
```

---

### Task 3: `normalizers.py` — `detect_column_kind`

**Files:**
- Modify: `scripts/normalizers.py` (append)
- Test: `tests/test_normalizers.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_normalizers.py` (add `detect_column_kind` to the import line):

```python
class DetectColumnKindTests(unittest.TestCase):
    def detect(self, header, values):
        return detect_column_kind(header, values)

    def test_document_by_name_and_content_convergence(self):
        self.assertEqual(self.detect("cpf", ["123.456.789-09", "04510636509"]), "cpf")
        self.assertEqual(self.detect("CNPJ", ["12.345.678/0001-95"]), "cnpj")
        self.assertEqual(self.detect("CEP", ["01310-100", "70000000"]), "cep")

    def test_cpf_name_requires_eleven_digits_content(self):
        self.assertIsNone(self.detect("cpf", ["abc", "12"]))

    def test_mixed_cpf_cnpj_column_is_not_detected(self):
        self.assertIsNone(self.detect("cpf_cnpj", ["12345678901", "12345678000195"]))

    def test_phone_never_detected_by_content(self):
        self.assertEqual(self.detect("telefone", ["(11) 3456-7890"]), "telefone")
        self.assertIsNone(self.detect("codigo", ["12345678"]))

    def test_strong_date_name_applies_even_with_unrecoverable(self):
        self.assertEqual(self.detect("data_nascimento", ["02/09/1990", "s/ data"]), "date")

    def test_strong_date_name_with_zero_parseable_stays_text(self):
        self.assertIsNone(self.detect("Data", ["texto livre", "outra coisa"]))

    def test_free_text_column_with_some_dates_is_not_date(self):
        self.assertIsNone(self.detect("observacao", ["02/09/2026", "nada demais", "ver nota", "x"]))

    def test_content_pure_requires_full_parseability(self):
        self.assertEqual(self.detect("coliga", ["2026-09-02", "2026-09-03"]), "date")
        self.assertIsNone(self.detect("coliga", ["2026-09-02", "relatório"]))

    def test_explicit_time_wins_over_date_name(self):
        self.assertEqual(self.detect("data_registro", ["02/09/2026 14:30", "03/09/2026"]), "timestamp")
        self.assertEqual(self.detect("registro", ["02/09/2026 14:30", "03/09/2026 09:00"]), "timestamp")

    def test_timestamp_names(self):
        self.assertEqual(self.detect("timestamp", ["2026-09-02 10:00"]), "timestamp")
        self.assertEqual(self.detect("created_at", ["2026-09-02"]), "timestamp")
        self.assertEqual(self.detect("hora_saida", ["02/09/2026 08:00"]), "timestamp")

    def test_cep_checked_before_phone(self):
        # nome 'cep' e conteudo 8 digitos -> cep (nao telefone)
        self.assertEqual(self.detect("cep", ["01310100"]), "cep")

    def test_all_blank_column_is_none(self):
        self.assertIsNone(self.detect("data", ["", "-", None]))

    def test_normalization_is_idempotent_for_detected_document(self):
        once = [normalize_cell(v, "cpf") for v in ["123.456.789-09", "045.106.365-09"]]
        self.assertEqual(self.detect("cpf", once), "cpf")
        self.assertEqual([normalize_cell(v, "cpf") for v in once], once)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_normalizers.py -q`
Expected: ImportError `cannot import name 'detect_column_kind'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/normalizers.py`:

```python
_DATE_NAME = ("data", "nasc", "venc", "exped")
_TIMESTAMP_NAME = ("timestamp", "hora", "horario", "createdat", "updatedat")
_PHONE_NAME = ("telefone", "celular", "fone", "whatsapp", "contato")


def _normalized_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def detect_column_kind(header: str, values: Sequence[object]) -> ColumnKind | None:
    """Decide the kind of one column from header + content. None = keep as-is.

    Validation order (first match wins): timestamp, date, cpf, cnpj, cep,
    telefone. Blanks never count against the 100% content threshold.
    """
    name = _normalized_header(header)
    filled = [value for value in values if not is_blank(value)]
    if not filled:
        return None
    texts = [str(value) for value in filled]
    parsed = [parse_temporal(text) for text in texts]
    parseable = [item is not None for item in parsed]
    all_temporal = all(parseable)
    has_time = any(item[1] for item, ok in zip(parsed, parseable) if ok and item)

    if all_temporal and (has_time or any(token in name for token in _TIMESTAMP_NAME)):
        return "timestamp"
    if any(token in name for token in _DATE_NAME) or name.startswith("dt"):
        if any(parseable) and not has_time:
            return "date"
    if all_temporal:
        return "date"
    if "cpf" in name and "cnpj" not in name and all(normalize_cell(t, "cpf") for t in texts):
        return "cpf"
    if "cnpj" in name and all(normalize_cell(t, "cnpj") for t in texts):
        return "cnpj"
    if "cep" in name and all(normalize_cell(t, "cep") for t in texts):
        return "cep"
    if any(token in name for token in _PHONE_NAME):
        # veto de conteúdo (§2.3): coluna mista ou de e-mails/nomes permanece texto
        def phone_like(text: str) -> bool:
            return "@" not in text and sum(character.isdigit() for character in text) >= 4
        if all(phone_like(text) for text in texts):
            return "telefone"
    return None
```

Note on `created_at`/`updated_at` after `[^a-z0-9]` stripping: they become `createdat`/`updatedat` — that is why `_TIMESTAMP_NAME` holds the stripped forms. Same for `dt_` prefix → `dt`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_normalizers.py -q`
Expected: all PASS (~33 tests total in file).

- [ ] **Step 5: Commit**

```bash
git add scripts/normalizers.py tests/test_normalizers.py
git commit -m "feat: detect date, timestamp and BR document column kinds"
```

---

### Task 4: Wire normalizers into `tabular.py` (types, values, manifest)

**Files:**
- Modify: `scripts/tabular.py` (`_infer_type` ~line 611, `_typed_value` ~line 630, `TableManifest` ~line 42, `_persist` ~lines 751-820, `_inspect_payload` ~line 967)
- Test: `tests/test_tabular.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tabular.py` inside class `TabularTestCase` (keep existing methods untouched; add a helper):

```python
    def _persist_single(self, source_name, dataset_name, columns, rows):
        source = self._source(source_name)
        return persist_source(
            self.db,
            Path(source_name).stem,
            source,
            f"wiki/sources/{Path(source_name).stem}.md",
            [Dataset(name=dataset_name, columns=columns, rows=rows)],
        )

    def test_normalization_types_and_stores_br_documents_and_dates(self):
        manifests = self._persist_single(
            "pessoas.csv",
            "pessoas",
            ["Nome", "CPF", "Data Nascimento", "Telefone"],
            [
                {"Nome": "Ana", "CPF": "045.106.365-09", "Data Nascimento": "02/09/1990", "Telefone": "(11) 3456-7890"},
                {"Nome": "Beto", "CPF": "12345678901", "Data Nascimento": "31/02/1990", "Telefone": "11 99999-8888"},
            ],
        )
        columns = dict(manifests[0].columns)
        self.assertEqual(columns["cpf"], "VARCHAR")
        self.assertEqual(columns["data_nascimento"], "DATE")
        self.assertEqual(columns["telefone"], "VARCHAR")

        stored = query_read_only(
            self.db,
            'SELECT cpf, data_nascimento, telefone FROM "pessoas__pessoas" ORDER BY cpf',
        )
        self.assertEqual(stored[0]["cpf"], "04510636509")          # leading zero kept, stored VARCHAR
        self.assertEqual(str(stored[0]["data_nascimento"]), "1990-09-02")
        self.assertIsNone(stored[1]["data_nascimento"])             # calendar-invalid -> NULL
        self.assertEqual(stored[0]["telefone"], "551134567890")

        report = {item["column"]: item for item in manifests[0].normalizations}
        self.assertEqual(report["Data Nascimento"]["kind"], "date")
        self.assertEqual(report["Data Nascimento"]["normalized"], 1)
        self.assertEqual(report["Data Nascimento"]["nulled"], 1)    # "31/02/1990" is not a blank token
        self.assertEqual(report["Data Nascimento"]["nulled_examples"], ["31/02/1990"])
        self.assertEqual(report["CPF"]["kind"], "cpf")
        self.assertNotIn("Nome", report)                            # plain text: not normalized

    def test_timestamp_column_is_typed_and_queryable(self):
        manifests = self._persist_single(
            "eventos.csv",
            "eventos",
            ["Ocorrencia", "data_registro"],
            [
                {"Ocorrencia": "a", "data_registro": "02/09/2026 14:30"},
                {"Ocorrencia": "b", "data_registro": "2026-09-02T14:30:00-04:00"},
            ],
        )
        self.assertEqual(dict(manifests[0].columns)["data_registro"], "TIMESTAMP")
        stored = query_read_only(
            self.db,
            "SELECT count(*) AS n FROM eventos__eventos WHERE data_registro >= TIMESTAMP '2026-09-02 18:00:00'",
        )
        self.assertEqual(stored[0]["n"], 1)  # 14:30-04:00 = 18:30 UTC; plain 14:30 stays 14:30
        stored = query_read_only(
            self.db,
            "SELECT count(*) AS n FROM eventos__eventos WHERE data_registro >= TIMESTAMP '2026-09-02 14:00:00'",
        )
        self.assertEqual(stored[0]["n"], 2)

    def test_cpf_digits_only_column_stays_varchar_not_bigint(self):
        # regression: all-digit CPFs used to be inferred BIGINT and lost leading zeros
        manifests = self._persist_single(
            "so_digitos.csv", "t", ["cpf"], [{"cpf": "04510636509"}]
        )
        self.assertEqual(dict(manifests[0].columns)["cpf"], "VARCHAR")
        stored = query_read_only(self.db, 'SELECT cpf FROM "so_digitos__t"')
        self.assertEqual(stored[0]["cpf"], "04510636509")

    def test_free_text_and_mixed_columns_keep_current_behavior(self):
        manifests = self._persist_single(
            "notas.csv",
            "notas",
            ["observacao", "codigo"],
            [
                {"observacao": "02/09/2026", "codigo": "0012"},
                {"observacao": "nada demais", "codigo": "0034"},
            ],
        )
        columns = dict(manifests[0].columns)
        self.assertEqual(columns["observacao"], "VARCHAR")
        self.assertEqual(columns["codigo"], "VARCHAR")  # leading zeros: existing identifier rule
        self.assertEqual(manifests[0].normalizations, [])

    def test_rebuild_of_normalized_dataset_is_idempotent(self):
        columns = ["cpf", "data_nascimento"]
        rows = [{"cpf": "045.106.365-09", "data_nascimento": "02/09/1990"}]
        first = self._persist_single("idem.csv", "idem", columns, rows)
        normalized = query_read_only(self.db, 'SELECT cpf, data_nascimento FROM "idem__idem"')
        again_rows = [
            {"cpf": normalized[0]["cpf"], "data_nascimento": str(normalized[0]["data_nascimento"])}
        ]
        source = self.raw / "idem.csv"
        second = rebuild_source(
            self.db, "idem", source, "wiki/sources/idem.md",
            [Dataset(name="idem", columns=columns, rows=again_rows)],
        )
        self.assertEqual(dict(first[0].columns), dict(second[0].columns))
        after = query_read_only(self.db, 'SELECT cpf, data_nascimento FROM "idem__idem"')
        self.assertEqual(str(after[0]["cpf"]), "04510636509")
        self.assertEqual(str(after[0]["data_nascimento"]), "1990-09-02")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tabular.py -q`
Expected: FAIL — `TableManifest` has no field `normalizations` (TypeError) and CPF column inferred BIGINT in `test_normalization_types_and_stores_br_documents_and_dates`.

- [ ] **Step 3: Wire the module into tabular.py**

3a. Add the import near the top of `scripts/tabular.py` (after `import duckdb`).
The dual import is REQUIRED: the CLI runs as `python scripts/tabular.py`
(sys.path[0] = `scripts/`, so the plain name resolves) while the tests import
`from scripts.tabular import ...` from the repo root (package path resolves):

```python
try:  # package import (tests) / script import (CLI) both work
    from scripts.normalizers import (
        KIND_SQL_TYPE,
        ColumnKind,
        detect_column_kind,
        is_blank,
        normalize_cell,
    )
except ImportError:  # pragma: no cover - CLI execution path
    from normalizers import (
        KIND_SQL_TYPE,
        ColumnKind,
        detect_column_kind,
        is_blank,
        normalize_cell,
    )
```

Verify both paths now, before writing any test:

```bash
python3 -c "from scripts.tabular import persist_source; print('pkg ok')"
python3 scripts/tabular.py --help >/dev/null && echo "cli ok"
```
Expected: `pkg ok` and `cli ok`.

3b. Replace `TableManifest` (frozen dataclass) to carry the report:

```python
@dataclass(frozen=True)
class TableManifest:
    table_name: str
    dataset_name: str
    row_count: int
    columns: list[tuple[str, str]]
    sample: list[dict[str, object]]
    normalizations: list[dict[str, object]] = field(default_factory=list)
```

3c. Replace `_infer_type` signature and add the kind early-return (rest of the body unchanged):

```python
def _infer_type(values: Sequence[object], column_name: str | None = None) -> str:
    if column_name is not None:
        kind = detect_column_kind(column_name, values)
        if kind is not None:
            return KIND_SQL_TYPE[kind]
    nonnull = [value for value in values if value is not None]
    ...  # existing body untouched
```

3d. Replace `_typed_value`:

```python
def _typed_value(value: object, type_name: str, kind: ColumnKind | None = None) -> object:
    if value is None:
        return None
    if kind is not None:
        value = normalize_cell(value, kind)
        if value is None:
            return None
    if type_name == "DATE":
        return _iso_date(value)
    if type_name == "TIMESTAMP":
        return value
    if type_name == "BIGINT" and isinstance(value, str):
        return int(value)
    if type_name == "DOUBLE" and isinstance(value, str):
        return float(value)
    return value
```

(With a kind, DATE/TIMESTAMP cells arrive as `date`/`datetime` objects already; `_iso_date` passes `date`/`datetime` through, so the existing branch works unchanged.)

3e. Add a report helper right after `_typed_value`:

```python
def _normalization_report(
    column: str, kind: ColumnKind, values: Sequence[object]
) -> dict[str, object]:
    normalized = 0
    nulled = 0
    examples: list[str] = []
    for value in values:
        if is_blank(value):
            continue
        if normalize_cell(value, kind) is not None:
            normalized += 1
        else:
            nulled += 1
            text = str(value).strip()[:40]
            if text not in examples:
                examples.append(text)
    return {
        "column": column,
        "kind": kind,
        "type": KIND_SQL_TYPE[kind],
        "normalized": normalized,
        "nulled": nulled,
        "nulled_examples": examples[:3],
    }
```

3f. In `_persist`, compute kinds once per stored column and thread them through. Replace the block from `column_types = [` through the end of the manifest append (`manifests.append(... )`) with:

```python
            kinds: list[ColumnKind | None] = [
                detect_column_kind(column, [row.get(column) for row in dataset.rows])
                for column in stored_columns
            ]
            column_types = [
                KIND_SQL_TYPE[kind] if kind is not None
                else _infer_type([row.get(column) for row in dataset.rows])
                for column, kind in zip(stored_columns, kinds)
            ]
            schema = list(zip(physical_columns, column_types)) + list(_PROVENANCE)
            definitions = ", ".join(
                f"{_quote_identifier(name)} {type_name}" for name, type_name in schema
            )
            connection.execute(f"CREATE TABLE {_quote_identifier(table_name)} ({definitions})")

            all_columns = physical_columns + [name for name, _type in _PROVENANCE]
            quoted_columns = ", ".join(_quote_identifier(name) for name in all_columns)
            placeholders = ", ".join("?" for _ in all_columns)
            values = []
            for row in dataset.rows:
                values.append(
                    [
                        _typed_value(row.get(original), type_name, kind)
                        for original, type_name, kind in zip(
                            stored_columns, column_types, kinds
                        )
                    ]
                    + [
                        source_id,
                        dataset.source_page,
                        dataset.source_section,
                        dataset.source_sheet,
                    ]
                )
            if values:
                connection.executemany(
                    f"INSERT INTO {_quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders})",
                    values,
                )
            schema_json = json.dumps(
                [{"name": name, "type": type_name} for name, type_name in schema],
                ensure_ascii=True,
            )
            connection.execute(
                """INSERT INTO _openkm_tables
                   (table_name, source_id, dataset_name, schema_json, row_count, updated_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                [table_name, source_id, dataset.name, schema_json, len(dataset.rows)],
            )
            normalizations = [
                _normalization_report(column, kind, [row.get(column) for row in dataset.rows])
                for column, kind in zip(stored_columns, kinds)
                if kind is not None
            ]
            manifests.append(
                TableManifest(
                    table_name=table_name,
                    dataset_name=dataset.name,
                    row_count=len(dataset.rows),
                    columns=schema,
                    sample=[
                        {
                            name: _typed_value(row.get(original), type_name, kind)
                            for original, name, type_name, kind in zip(
                                stored_columns, physical_columns, column_types, kinds
                            )
                        }
                        | {
                            "source_id": source_id,
                            "source_page": dataset.source_page,
                            "source_section": dataset.source_section,
                            "source_sheet": dataset.source_sheet,
                        }
                        for row in dataset.rows[:5]
                    ],
                    normalizations=normalizations,
                )
            )
```

3g. In `_inspect_payload`, replace the `result.append({...})` block's `columns`
and `sample` construction (keep `source_page`, `source_section`,
`source_sheet`, `formulas` keys unchanged at the end):

```python
        kinds_by_column = {
            column: detect_column_kind(column, [row.get(column) for row in dataset.rows])
            for column in dataset.columns
        }
        sample_rows = []
        for row in dataset.rows[:5]:
            sample_row = {}
            for column in dataset.columns:
                value = row.get(column)
                kind = kinds_by_column[column]
                sample_row[column] = normalize_cell(value, kind) if kind is not None else value
            sample_rows.append(sample_row)
        result.append(
            {
                "name": dataset.name,
                "columns": [
                    {
                        "name": column,
                        "type": KIND_SQL_TYPE[kinds_by_column[column]]
                        if kinds_by_column[column] is not None
                        else _infer_type([row.get(column) for row in dataset.rows]),
                        "kind": kinds_by_column[column],
                    }
                    for column in dataset.columns
                ],
                "row_count": len(dataset.rows),
                "sample": sample_rows,
                # remaining keys (source_page, source_section, source_sheet, formulas) unchanged
            }
        )
```

This exact block was verified in the dry-run; do not rename `kind`/`columns`/`sample` keys.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all PASS (existing 18 tests + new). If `test_persistence_infers_types_preserves_mixed_values_nulls_and_identifiers` breaks, check column names used there against `_DATE_NAME`/`_PHONE_NAME` tokens — it must keep passing **unchanged** (spec: no behavior change for non-detected columns); if a fixture name accidentally collides (e.g. a column literally named `data` holding numbers), rename the *fixture column* in that test to keep intent, never relax production logic.

- [ ] **Step 5: Commit**

```bash
git add scripts/tabular.py tests/test_tabular.py
git commit -m "feat: apply normalization and typing in DuckDB persistence path"
```

---

### Task 5: CLI surface — inspect reports kind (end-to-end check)

**Files:**
- Modify: `scripts/tabular.py` (nothing if Task 4 Step 3g done — this task only verifies the CLI payload and adds a test)
- Test: `tests/test_tabular.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tabular.py` (module level, after class; needs `import io, contextlib, json` at top if absent):

```python
class InspectCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "raw").mkdir()
        self.previous_root = os.environ.get("OKM_WIKI_ROOT")
        os.environ["OKM_WIKI_ROOT"] = str(self.root)

    def tearDown(self):
        if self.previous_root is None:
            os.environ.pop("OKM_WIKI_ROOT", None)
        else:
            os.environ["OKM_WIKI_ROOT"] = self.previous_root
        self.temporary_directory.cleanup()

    def test_inspect_file_reports_kind_and_normalized_sample(self):
        path = self.root / "raw" / "cli.csv"
        path.write_text("Nome,CPF,Data Nascimento\nAna,045.106.365-09,02/09/1990\n", encoding="utf-8")
        from scripts.tabular import main

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            main(["inspect-file", "--source-id", "cli", "--file", str(path)])
        payload = json.loads(buffer.getvalue())
        columns = {item["name"]: item for item in payload["datasets"][0]["columns"]}
        self.assertEqual(columns["CPF"]["kind"], "cpf")
        self.assertEqual(columns["CPF"]["type"], "VARCHAR")
        self.assertEqual(columns["Data Nascimento"]["kind"], "date")
        self.assertEqual(columns["Data Nascimento"]["type"], "DATE")
        self.assertEqual(payload["datasets"][0]["sample"][0]["CPF"], "04510636509")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tabular.py::InspectCliTests -q`
Expected: FAIL (`kind` key missing or sample raw) — if Task 4 already produced green, mark this step as verification-only and skip to Step 4.

- [ ] **Step 3: Implement any remaining `_inspect_payload` normalization**

Only if Step 2 failed: finish the 3g change from Task 4 (sample normalization + `kind` key).

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_tabular.py
git commit -m "test: cover inspect-file normalization reporting"
```

---

### Task 6: Documentation (SKILL.md + ingest reference) and real-DB smoke

**Files:**
- Modify: `SKILL.md` (tabular ingestion rules, after the `inspect-file`/`persist-json` bullet)
- Modify: `references/ingest-workflow.md` (persist step)
- No code changes.

- [ ] **Step 1: Add the SKILL.md bullet**

In `SKILL.md`, numbered item 5 of the ingest section is the line starting
`5. For an automatic direct-file dataset, call \`inspect-file\` first` (ends with
`the updated Source Summary page.`). Insert this sub-bullet on a new line
immediately after that item, keeping its 3-space indent so it nests under item 5:

```markdown
   - The helper detects and normalizes Brazilian data before typing tables: dates/timestamps become `DATE`/`TIMESTAMP` (unrecoverable cells become `NULL`), and CPF/CNPJ/CEP/phone columns become digits-only `VARCHAR` (phone gets DDI `55` when 10-11 digits). Check the `kind` and `normalizations` reported by `inspect-file`, and copy each `normalizations` entry (kind, counts, `nulled_examples`) into the Source Summary caveats so users see exactly what changed.
```

Do not touch any other line — `tests/test_skill_contract.py` asserts exact substrings elsewhere.

- [ ] **Step 2: Add the reference bullet**

In `references/ingest-workflow.md`, in the persistence section, append one bullet:

```markdown
- Normalization: `normalizers.py` types date/timestamp/CPF/CNPJ/CEP/phone columns before `CREATE TABLE`; the manifest `normalizations` list reports per-column `normalized`, `nulled`, and up to 3 `nulled_examples` for the Source Summary.
```

- [ ] **Step 3: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all PASS (contract tests included).

- [ ] **Step 4: Smoke against a copy of the real wiki DB (never the live file)**

```bash
cp ~/llm-wiki/database/data.duckdb /tmp/okm_smoke.duckdb
python3 - <<'PY'
import os, tempfile
from pathlib import Path
from scripts.tabular import Dataset, persist_source, query_read_only, rebuild_source
root = Path(tempfile.mkdtemp()); raw = root / "raw"; raw.mkdir()
src = raw / "smoke.csv"; src.write_text("a\n1\n")
os.environ["OKM_WIKI_ROOT"] = str(root)
persist_source(Path("/tmp/okm_smoke.duckdb"), "smoke", src, "wiki/sources/smoke.md",
               [Dataset(name="t", columns=["cpf", "data_nascimento"],
                        rows=[{"cpf": "045.106.365-09", "data_nascimento": "02/09/1990"}])])
print(query_read_only(Path("/tmp/okm_smoke.duckdb"), 'SELECT cpf, data_nascimento FROM smoke__t'))
print(query_read_only(Path("/tmp/okm_smoke.duckdb"), "SELECT count(*) AS tables FROM _openkm_tables"))
PY
rm /tmp/okm_smoke.duckdb
```

Expected output: `[{'cpf': '04510636509', 'data_nascimento': datetime.date(1990, 9, 2)}]` and the table count (10: 9 existing + smoke). The live `~/llm-wiki/database/data.duckdb` is only read by `cp`, never written.

- [ ] **Step 5: Commit**

```bash
git add SKILL.md references/ingest-workflow.md
git commit -m "docs: document tabular normalization for the agent workflow"
```

---

## Verification record (plan author, 2026-09-02)

The whole plan was dry-run end-to-end on a throwaway copy of the repo
(`/tmp/okm_sim`) before being handed over: every code block above executed
verbatim, the three initial defects found were fixed in this document (off-
by-one month numbering `enumerate(..., 1)`, `date` vs `datetime` in
`parse_temporal` outputs via `_outcome`, blank-token/offset/`__table__` naming
mistakes in the Task 4 tests), and the final state is:

- `python3 -m pytest tests/ -q` → **59 passed, 59 subtests passed** (baseline 18/59 + 22 new).
- Real-DB smoke on a copy of `~/llm-wiki/database/data.duckdb`: persisted row reads back `cpf='04510636509'`, `data_nascimento=date(1990,9,2)`, `_openkm_tables` count 10, manifest `normalizations` populated.

## Definition of Done

- `python3 -m pytest tests/ -q` fully green → expect **59 passed, 59 subtests passed** (the exact number the verified dry-run produced).
- New tables with cpf/cnpj/cep/telefone/dates/timestamps get `VARCHAR`/`DATE`/`TIMESTAMP` and store normalized values (verified by SELECT, not just manifest).
- `normalizations` present in `TableManifest` with correct `normalized`/`nulled`/`nulled_examples`; raw source files never modified.
- Non-detected columns (mixed text, identifiers with leading zeros) behave exactly as before.
- Spec §8 out-of-scope items not implemented (no DV validation, no migration of existing tables, no DDI beyond the 10/11 rule, read-only query path untouched).
- Each task committed separately; `git status --short` clean at the end.
