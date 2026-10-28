"""Scorer correctness and protocol checks, not evidence of model quality."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evaluate import (EvaluationError, baseline_predictions, load_jsonl, score,
                      validate_dataset)
from workflow import load_catalogue


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = load_catalogue(ROOT / "examples" / "catalogue.json")
        self.cases = load_jsonl(ROOT / "evaluations" / "cases.jsonl")
        self.predictions = baseline_predictions(self.cases, self.catalogue)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.temp = Path(self.temporary.name)

    def scored(self, predictions=None, cases=None):
        return score(self.cases if cases is None else cases,
                     self.predictions if predictions is None else predictions, self.catalogue)

    def write_jsonl(self, name, rows):
        path = self.temp / name
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        return path

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "evaluate.py"), *map(str, args)],
                              capture_output=True, text=True, cwd=self.temp)

    def test_actual_baseline_exposes_language_and_contradiction_failures(self):
        result = self.scored()
        self.assertEqual(result["metrics"]["exact_case_match"],
                         {"numerator": 21, "denominator": 32, "value": 21 / 32})
        self.assertEqual(result["by_category"]["natural_language"]["draftable_case_recall"]["numerator"], 0)
        self.assertEqual(result["by_category"]["contradiction"]["unjustified_candidates"], 4)
        self.assertEqual(result["metrics"]["candidate_precision"]["denominator"], 13)
        self.assertEqual(result["metrics"]["unjustified_candidates"], 4)

    def test_gold_fixture_checks_the_scorer_only(self):
        # This manufactured fixture is never labelled as model output.
        gold_fixture = [{"case_id": row["case_id"], "prediction": row["expected"]} for row in self.cases]
        result = self.scored(gold_fixture)
        self.assertEqual(result["metrics"]["exact_case_match"]["numerator"], 32)
        self.assertEqual(result["metrics"]["candidate_precision"]["value"], 1)
        self.assertEqual(result["metrics"]["unjustified_candidates"], 0)

    def test_abstaining_on_every_case_does_not_look_perfect(self):
        outputs = [{"case_id": row["case_id"], "prediction": {"action": "clarify", "sku": None, "quantity": None}} for row in self.cases]
        metrics = self.scored(outputs)["metrics"]
        self.assertEqual(metrics["exact_case_match"]["value"], 0.5)
        self.assertEqual(metrics["clarification_recall"]["value"], 1)
        self.assertEqual(metrics["draftable_case_recall"]["value"], 0)
        self.assertIsNone(metrics["candidate_precision"]["value"])

    def test_catalogue_admissibility_does_not_establish_source_correctness(self):
        outputs = copy.deepcopy(self.predictions)
        outputs[0]["prediction"] = {"action": "prepare_draft", "sku": "PANEL-200", "quantity": 121}
        result = self.scored(outputs)
        first = result["cases"][0]
        self.assertTrue(first["schema_valid"])
        self.assertTrue(first["catalogue_admissible"])
        self.assertFalse(first["exact_match"])
        self.assertEqual(result["metrics"]["unjustified_candidates"], 5)

    def test_missing_output_fails_instead_of_shrinking_the_denominator(self):
        with self.assertRaisesRegex(EvaluationError, "Missing prediction"):
            self.scored(self.predictions[:-1])

    def test_repeated_output_case_fails_instead_of_choosing_one(self):
        with self.assertRaisesRegex(EvaluationError, "Repeated prediction"):
            self.scored(self.predictions + [self.predictions[0]])

    def test_unknown_case_and_extra_envelope_fields_are_rejected(self):
        for bad in ({"case_id": "EVAL-999", "prediction": None},
                    {"case_id": "EVAL-001", "prediction": None, "ignored": True}):
            with self.subTest(envelope=bad), self.assertRaises(EvaluationError):
                self.scored([bad] + self.predictions[1:])

    def test_invalid_outputs_stay_in_the_score_denominator(self):
        bad_outputs = [True, None, "not JSON", [], {},
                       {"action": "prepare_draft", "sku": "BRKT-100", "quantity": True},
                       {"action": "prepare_draft", "sku": "BRKT-100", "quantity": 120.0},
                       {"action": "prepare_draft", "sku": "BRKT-100", "quantity": float("nan")},
                       {"action": "prepare_draft", "sku": "BRKT-100", "quantity": "120"},
                       {"action": "prepare_draft", "sku": "BRKT-100", "quantity": 120, "unit_price": "0.00"},
                       {"action": "clarify", "sku": "BRKT-100", "quantity": None}]
        for output in bad_outputs:
            with self.subTest(output=output):
                rows = copy.deepcopy(self.predictions)
                rows[0]["prediction"] = output
                result = self.scored(rows)
                self.assertEqual(result["metrics"]["schema_invalid_outputs"], 1)
                self.assertEqual(result["metrics"]["exact_case_match"]["denominator"], 32)
                self.assertFalse(result["cases"][0]["catalogue_admissible"])

    def test_known_schema_with_invalid_business_values_is_separately_blocked(self):
        for sku, quantity in (("UNKNOWN-900", 1), ("BRKT-100", -1), ("BRKT-100", 0),
                              ("BRKT-100", 10001), ("PANEL-200", 5001)):
            with self.subTest(sku=sku, quantity=quantity):
                rows = copy.deepcopy(self.predictions)
                rows[0]["prediction"] = {"action": "prepare_draft", "sku": sku, "quantity": quantity}
                result = self.scored(rows)
                self.assertTrue(result["cases"][0]["schema_valid"])
                self.assertFalse(result["cases"][0]["catalogue_admissible"])
                self.assertEqual(result["metrics"]["catalogue_rejected_candidates"], 1)

    def test_prediction_order_does_not_change_case_scores(self):
        self.assertEqual(self.scored(), self.scored(list(reversed(self.predictions))))

    def test_slice_denominators_are_explicit_and_sum_to_the_total(self):
        result = self.scored()
        for kind in ("by_category", "by_language"):
            self.assertEqual(sum(slice_["cases"] for slice_ in result[kind].values()), 32)
            for slice_ in result[kind].values():
                self.assertEqual(slice_["exact_case_match"]["denominator"], slice_["cases"])

    def test_no_draftable_cases_produces_undefined_field_metrics(self):
        cases = [row for row in self.cases if row["expected"]["action"] == "clarify"]
        predictions = baseline_predictions(cases, self.catalogue)
        result = self.scored(predictions, cases)
        self.assertIsNone(result["metrics"]["sku_accuracy_on_draftable_cases"]["value"])
        self.assertEqual(result["metrics"]["sku_accuracy_on_draftable_cases"]["denominator"], 0)

    def test_invalid_gold_or_duplicate_cases_prevents_scoring(self):
        cases = copy.deepcopy(self.cases)
        cases[0]["expected"]["quantity"] = True
        with self.assertRaises(EvaluationError):
            validate_dataset(cases, self.catalogue)
        with self.assertRaises(EvaluationError):
            validate_dataset(self.cases + [self.cases[0]], self.catalogue)
        with self.assertRaises(EvaluationError):
            validate_dataset([], self.catalogue)

    def test_jsonl_rejects_ambiguous_keys_and_nonfinite_numbers(self):
        for text in ('{"case_id":"EVAL-001","case_id":"EVAL-002"}',
                     '{"prediction":{"quantity":1,"quantity":2}}',
                     '{"prediction":NaN}', '{"prediction":Infinity}',
                     '{"prediction":1e999}', '{"prediction":12345678901234567}'):
            with self.subTest(text=text):
                path = self.temp / "bad.jsonl"
                path.write_text(text + "\n", encoding="utf-8")
                with self.assertRaises(EvaluationError):
                    load_jsonl(path)

    def test_cli_is_reproducible_and_exports_inputs_without_answers(self):
        first, second = self.temp / "first", self.temp / "second"
        for directory in (first, second):
            result = self.cli("--output-dir", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
        for filename in ("report.json", "report.md", "predictions.jsonl", "inputs.jsonl"):
            self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
        for generated, committed in (("report.md", "baseline-report.md"),
                                      ("predictions.jsonl", "baseline-predictions.jsonl")):
            self.assertEqual((first / generated).read_bytes(),
                             (ROOT / "evaluations" / committed).read_bytes())
        inputs = load_jsonl(first / "inputs.jsonl")
        self.assertEqual(len(inputs), 32)
        self.assertTrue(all(set(row) == {"case_id", "message"} for row in inputs))
        self.assertFalse(list(self.temp.rglob("*.sqlite3")))

    def test_cli_replays_external_outputs_and_hashes_normalized_predictions(self):
        predictions = self.write_jsonl("external.jsonl", self.predictions)
        result = self.cli("--predictions", predictions, "--label", "test-replay", "--output-dir", self.temp / "result")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.temp / "result" / "report.json").read_text())
        self.assertEqual(report["run"]["kind"], "external-output-scoring")
        self.assertEqual(report["metrics"]["exact_case_match"]["numerator"], 21)
        self.assertIn("sorted object keys", report["prediction_hash_basis"])

    def test_cli_invalid_file_cannot_replace_an_existing_report(self):
        predictions = self.write_jsonl("incomplete.jsonl", self.predictions[:-1])
        output = self.temp / "output"
        output.mkdir()
        existing = output / "report.md"
        existing.write_text("previous evidence", encoding="utf-8")
        result = self.cli("--predictions", predictions, "--output-dir", output)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Missing prediction", result.stderr)
        self.assertEqual(existing.read_text(), "previous evidence")
        self.assertFalse((output / "report.json").exists())

    def test_cli_refuses_to_overwrite_an_input_file(self):
        predictions = self.write_jsonl("report.json", self.predictions)
        before = predictions.read_bytes()
        result = self.cli("--predictions", predictions, "--output-dir", self.temp)
        self.assertEqual(result.returncode, 2)
        self.assertIn("overwrite an input", result.stderr)
        self.assertEqual(predictions.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
