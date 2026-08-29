import unittest
from pathlib import Path

from scripts.scaffold import AGENTS_MD


ROOT = Path(__file__).resolve().parents[1]
COMMON = [
    "database/data.duckdb",
    "first five rows",
    "source_page",
    "source_section",
    "formula",
]


class DocumentationContractTest(unittest.TestCase):
    def setUp(self):
        self.skill = self._read("SKILL.md")
        self.workflow = self._read("references/ingest-workflow.md")
        self.readme = self._read("README.md")
        self.scaffold = self._read("scripts/scaffold.py")
        self.agents = AGENTS_MD

    @staticmethod
    def _read(relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def _assert_terms(self, text, terms, artifact):
        text = " ".join(text.lower().split())
        for term in terms:
            with self.subTest(artifact=artifact, term=term):
                self.assertIn(term.lower(), text)

    def _assert_phrase(self, text, phrase, artifact):
        normalized = " ".join(text.lower().split())
        self.assertIn(" ".join(phrase.lower().split()), normalized, artifact)

    def test_common_terms_are_present_in_contract_documents(self):
        for artifact, text in (
            ("SKILL.md", self.skill),
            ("references/ingest-workflow.md", self.workflow),
            ("AGENTS_MD", self.agents),
        ):
            self._assert_terms(text, COMMON, artifact)
        self._assert_terms(
            self.readme,
            ["database/data.duckdb", "formula"],
            "README.md",
        )

    def test_direct_tabular_files_are_automatic_and_inspected(self):
        self._assert_phrase(
            self.skill,
            "genuinely tabular CSV or TSV is persisted automatically without approval",
            "SKILL.md",
        )
        self._assert_phrase(
            self.skill,
            "genuinely tabular XLSX is persisted automatically without approval",
            "SKILL.md",
        )
        self._assert_phrase(
            self.workflow,
            "For genuinely tabular CSV, TSV, and XLSX files, persistence is automatic and occurs without approval",
            "references/ingest-workflow.md",
        )
        self._assert_phrase(
            self.readme,
            "Automatically persists tabular CSV, TSV, and XLSX files; PDF and other document extraction requires approval",
            "README.md",
        )
        self._assert_phrase(
            self.agents,
            "For genuinely tabular CSV, TSV, and XLSX sources, persist automatically to the derived `database/data.duckdb` after inspection",
            "AGENTS_MD",
        )
        self._assert_phrase(
            self.agents,
            "Inspect ordinary documents for visual tables and tabulatable text. These candidates are approval-gated: propose the logical dataset, schema, and first five rows, and persist only after explicit approval",
            "AGENTS_MD",
        )
        self._assert_terms(
            self.skill,
            ["inspect-file", "persist-json"],
            "SKILL.md",
        )
        self._assert_terms(
            self.workflow,
            ["inspect-file", "persist-json"],
            "references/ingest-workflow.md",
        )

    def test_ordinary_documents_require_approval(self):
        self._assert_phrase(
            self.skill,
            "extract a table or tabulatable text from an ordinary document | **ingest** with explicit approval before DuckDB persistence",
            "SKILL.md",
        )
        self._assert_phrase(
            self.workflow,
            "Before any derived DuckDB table write, present a proposal for every candidate containing",
            "references/ingest-workflow.md",
        )
        self._assert_phrase(
            self.workflow,
            "Ask for explicit approval of the proposal. Do not call `persist-json`, call a direct persistence helper, or create a table before approval",
            "references/ingest-workflow.md",
        )
        self._assert_phrase(
            self.agents,
            "Inspect ordinary documents for visual tables and tabulatable text. These candidates are approval-gated: propose the logical dataset, schema, and first five rows, and persist only after explicit approval",
            "AGENTS_MD",
        )
        self._assert_phrase(
            self.readme,
            "PDF and other document extraction requires approval",
            "README.md",
        )

    def test_formula_results_are_excluded_but_inputs_remain_queryable(self):
        self._assert_phrase(
            self.skill,
            "Exclude formula-derived values and aggregate columns from persisted data, including cached formula results. Retain their input columns and perform calculations at query time",
            "SKILL.md",
        )
        self._assert_phrase(
            self.readme,
            "excludes formula-derived columns, calculates formulas at query time",
            "README.md",
        )
        self._assert_phrase(
            self.skill,
            "when safe translation is unavailable, document that no equivalent query was generated",
            "SKILL.md",
        )
        self._assert_phrase(
            self.workflow,
            "On XLSX inspection, preserve the original formula text, excluded column, referenced input columns, and an equivalent DuckDB SQL expression when safe. When translation is unsafe, record exactly `no equivalent query was generated`. Put this documentation only in the Source Summary; never write formula definitions or cached formula values to `_openkm_sources`, `_openkm_tables`, or a data table.",
            "references/ingest-workflow.md",
        )
        self._assert_phrase(
            self.agents,
            "Formula metadata is never stored in `_openkm_sources`, `_openkm_tables`, or user data tables.",
            "AGENTS_MD",
        )
        self._assert_phrase(
            self.agents,
            "Formula metadata is never stored in `_openkm_sources`, `_openkm_tables`, or user data tables. This includes formula definitions, original formulas, equivalent DuckDB SQL, and cached formula values; these belong only in the Source Summary.",
            "AGENTS_MD",
        )
        self._assert_phrase(
            self.agents,
            "Every Source Summary must record the original formula and equivalent DuckDB SQL expression",
            "AGENTS_MD",
        )
        self._assert_phrase(
            self.agents,
            "when translation is unsafe, record exactly `no equivalent query was generated`.",
            "AGENTS_MD",
        )
        self._assert_phrase(
            self.skill,
            "Never store formula definitions or derived values in DuckDB catalog or data tables",
            "SKILL.md",
        )
        self._assert_phrase(
            self.skill,
            "Document the original formula, excluded column, input columns, and any equivalent DuckDB SQL only in the Source Summary page",
            "SKILL.md",
        )
    def test_provenance_is_preserved_on_persisted_rows(self):
        for artifact, text in (
            ("SKILL.md", self.skill),
            ("references/ingest-workflow.md", self.workflow),
            ("AGENTS_MD", self.agents),
        ):
            self._assert_terms(
                text,
                ["source_id", "source_page", "source_section", "source_sheet", "provenance"],
                artifact,
            )
        self._assert_terms(self.readme, ["row provenance"], "README.md")

    def test_wiki_access_and_raw_source_rules_are_documented(self):
        for artifact, text in (("SKILL.md", self.skill), ("README.md", self.readme)):
            self._assert_terms(
                text,
                ["wiki/sources/", "raw/", "natural-language"],
                artifact,
            )
            self.assertIn("immutable", text.lower(), artifact)
        for artifact, text in (
            ("SKILL.md", self.skill),
            ("references/ingest-workflow.md", self.workflow),
            ("AGENTS_MD", self.agents),
        ):
            normalized = " ".join(text.lower().split())
            if artifact == "SKILL.md":
                self.assertIn(
                    "users ask natural-language questions and are never given a sql cli or database ui",
                    normalized,
                    artifact,
                )
            elif artifact == "references/ingest-workflow.md":
                self.assertIn(
                    "users query tabular data through natural language only",
                    normalized,
                    artifact,
                )
                self.assertIn(
                    "do not expose a sql cli or database ui as a user-facing feature",
                    normalized,
                    artifact,
                )
            else:
                self.assertIn(
                    "the agent is the only query interface. do not expose a sql cli or database ui to users",
                    normalized,
                    artifact,
                )
        self._assert_phrase(
            self.readme,
            "supports agent-only natural-language access",
            "README.md",
        )
        self._assert_phrase(self.readme, "There is no user SQL interface", "README.md")

    def test_adopt_mode_preserves_existing_scaffold_files(self):
        self._assert_terms(
            self.scaffold,
            ["--adopt", "write_if_missing", "never overwrite", "if path.exists()"],
            "scripts/scaffold.py",
        )


if __name__ == "__main__":
    unittest.main()
