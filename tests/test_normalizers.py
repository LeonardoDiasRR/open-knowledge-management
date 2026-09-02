"""Tests for the pure normalizer module (no DuckDB, no filesystem)."""
import unittest
from datetime import date, datetime, timedelta, timezone

from scripts.normalizers import detect_column_kind, normalize_cell, parse_temporal


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

    def test_python_objects_pass_through(self):
        self.assert_temporal(date(2026, 9, 2), date(2026, 9, 2), False)
        self.assert_temporal(
            datetime(2026, 9, 2, 14, 30), datetime(2026, 9, 2, 14, 30), True
        )

    def test_invalid_values_return_none(self):
        for raw in ("31/02/2025", "s/ data", "", "—", "sem data", "n/a", None, 123):
            self.assertIsNone(parse_temporal(raw), f"should not parse {raw!r}")

    def test_invalid_utc_offset_is_unrecoverable(self):
        self.assertIsNone(parse_temporal("2026-09-02T14:30:00+24:00"))
        self.assertIsNone(parse_temporal("2026-09-02T14:30:00-99:00"))

    def test_aware_datetime_is_converted_to_utc_naive(self):
        aware = datetime(2026, 9, 2, 14, 30, tzinfo=timezone(timedelta(hours=-4)))
        self.assert_temporal(aware, datetime(2026, 9, 2, 18, 30), True)


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
