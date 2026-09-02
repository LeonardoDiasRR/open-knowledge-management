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
        return None


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
        year = int(match.group(3))
        return _outcome(_build(int(match.group(1)), month, year, None, None, None, None, None), False)

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
        return "telefone"
    return None
