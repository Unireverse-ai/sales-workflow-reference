"""Score synthetic extraction outputs offline. No inference, network or handoff."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from workflow import ValidationError, build_draft, load_catalogue, strict_json_loads, validate_catalogue


ROOT = Path(__file__).resolve().parent
MAX_FILE_BYTES = 2_000_000
MAX_CASES = 1000
CASE_ID = re.compile(r"EVAL-[0-9]{3,5}")


class EvaluationError(ValueError):
    """An invalid benchmark or prediction file; no partial score is produced."""


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    with path.open("rb") as source:
        data = source.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise EvaluationError("JSONL file exceeds the two-megabyte limit.")
    try:
        lines = data.decode("utf-8").split("\n")
    except UnicodeDecodeError as error:
        raise EvaluationError("JSONL must use UTF-8.") from error
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if len(line) > 65536:
            raise EvaluationError("JSONL line exceeds the input limit.")
        try:
            row = strict_json_loads(line)
        except (ValueError, RecursionError) as error:
            raise EvaluationError("Invalid JSONL at line %s: %s" % (number, error)) from error
        if not isinstance(row, dict):
            raise EvaluationError("Every JSONL row must be an object.")
        rows.append(row)
        if len(rows) > MAX_CASES:
            raise EvaluationError("The protocol supports at most 1000 cases.")
    if not rows:
        raise EvaluationError("JSONL must contain at least one row.")
    return rows


def prediction_schema_error(prediction: Any):
    if not isinstance(prediction, dict) or set(prediction) != {"action", "sku", "quantity"}:
        return "Prediction must contain exactly action, sku and quantity."
    if prediction["action"] == "clarify":
        if prediction["sku"] is not None or prediction["quantity"] is not None:
            return "A clarification must abstain from both extracted fields."
        return None
    if prediction["action"] != "prepare_draft":
        return "Action must be prepare_draft or clarify."
    sku, quantity = prediction["sku"], prediction["quantity"]
    if not isinstance(sku, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,39}", sku):
        return "SKU must be a bounded uppercase identifier."
    if type(quantity) is not int:
        return "Quantity must be a JSON integer, excluding booleans and floats."
    return None


def candidate_error(case_id, prediction, catalogue):
    """Apply existing catalogue/quantity checks; do not claim source correctness."""
    try:
        build_draft({"inquiry_id": case_id, "buyer_label": "Synthetic evaluation",
                     "message": "SKU: %s\nQuantity: %s" %
                                (prediction["sku"], prediction["quantity"])}, catalogue)
    except ValidationError as error:
        return error.code
    return None


def validate_dataset(rows, catalogue):
    validate_catalogue(catalogue)
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CASES:
        raise EvaluationError("Dataset must contain 1–1000 cases.")
    seen = set()
    for row in rows:
        if set(row) != {"case_id", "language", "category", "message", "expected"}:
            raise EvaluationError("Dataset rows require case_id, language, category, message and expected.")
        case_id = row["case_id"]
        if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id) or case_id in seen:
            raise EvaluationError("Dataset case IDs must be unique EVAL identifiers.")
        seen.add(case_id)
        if not isinstance(row["language"], str) or not re.fullmatch(r"[a-z-]{2,16}", row["language"]):
            raise EvaluationError("Invalid language label.")
        if not isinstance(row["category"], str) or not re.fullmatch(r"[a-z][a-z_-]{1,39}", row["category"]):
            raise EvaluationError("Invalid category label.")
        if not isinstance(row["message"], str) or not row["message"] or len(row["message"]) > 8192:
            raise EvaluationError("Dataset messages must contain 1–8192 characters.")
        expected = row["expected"]
        problem = prediction_schema_error(expected)
        if problem:
            raise EvaluationError("Invalid gold label for %s: %s" % (case_id, problem))
        if expected["action"] == "prepare_draft" and candidate_error(case_id, expected, catalogue):
            raise EvaluationError("Gold draft candidate violates the supplied catalogue: " + case_id)
    return rows


def validate_prediction_envelopes(rows, cases):
    expected_ids = {case["case_id"] for case in cases}
    predictions = {}
    for row in rows:
        if set(row) != {"case_id", "prediction"}:
            raise EvaluationError("Prediction rows require exactly case_id and prediction.")
        case_id = row["case_id"]
        if not isinstance(case_id, str) or case_id not in expected_ids:
            raise EvaluationError("Unknown prediction case ID: " + repr(case_id))
        if case_id in predictions:
            raise EvaluationError("Repeated prediction case ID: " + case_id)
        predictions[case_id] = row["prediction"]
    missing = expected_ids - set(predictions)
    if missing:
        raise EvaluationError("Missing prediction case IDs: " + ", ".join(sorted(missing)))
    return predictions


def baseline_predictions(cases, catalogue):
    """Run the actual workflow parser without giving it gold labels."""
    rows = []
    for case in cases:
        try:
            draft = build_draft({"inquiry_id": case["case_id"], "buyer_label": "Synthetic baseline",
                                 "message": case["message"]}, catalogue)
            prediction = {"action": "prepare_draft", "sku": draft.sku, "quantity": draft.quantity}
        except ValidationError:
            prediction = {"action": "clarify", "sku": None, "quantity": None}
        rows.append({"case_id": case["case_id"], "prediction": prediction})
    return rows


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def aggregate(rows):
    total = len(rows)
    draftable = [row for row in rows if row["expected"]["action"] == "prepare_draft"]
    blocked = [row for row in rows if row["expected"]["action"] == "clarify"]
    admitted = [row for row in rows if row["catalogue_admissible"]]
    exact_drafts = sum(row["exact_match"] and row["catalogue_admissible"] for row in draftable)
    return {
        "cases": total,
        "schema_validity": fraction(sum(row["schema_valid"] for row in rows), total),
        "exact_case_match": fraction(sum(row["exact_match"] for row in rows), total),
        "action_accuracy": fraction(sum(row["schema_valid"] and row["prediction"]["action"] == row["expected"]["action"] for row in rows), total),
        "sku_accuracy_on_draftable_cases": fraction(sum(row["schema_valid"] and row["prediction"]["action"] == "prepare_draft" and row["prediction"]["sku"] == row["expected"]["sku"] for row in draftable), len(draftable)),
        "quantity_accuracy_on_draftable_cases": fraction(sum(row["schema_valid"] and row["prediction"]["action"] == "prepare_draft" and row["prediction"]["quantity"] == row["expected"]["quantity"] for row in draftable), len(draftable)),
        "draftable_case_recall": fraction(exact_drafts, len(draftable)),
        "clarification_recall": fraction(sum(row["exact_match"] for row in blocked), len(blocked)),
        "abstention_rate": fraction(sum(row["schema_valid"] and row["prediction"]["action"] == "clarify" for row in rows), total),
        "candidate_precision": fraction(exact_drafts, len(admitted)),
        "blocked_case_candidate_rate": fraction(sum(row["catalogue_admissible"] for row in blocked), len(blocked)),
        "catalogue_admissible_candidates": len(admitted),
        "unjustified_candidates": sum(not row["exact_match"] for row in admitted),
        "schema_invalid_outputs": sum(not row["schema_valid"] for row in rows),
        "catalogue_rejected_candidates": sum(row["schema_valid"] and row["prediction"]["action"] == "prepare_draft" and not row["catalogue_admissible"] for row in rows),
    }


def score(cases, prediction_rows, catalogue):
    validate_dataset(cases, catalogue)
    predictions = validate_prediction_envelopes(prediction_rows, cases)
    rows = []
    for case in cases:
        prediction = predictions[case["case_id"]]
        schema_error = prediction_schema_error(prediction)
        policy_error = None
        candidate = not schema_error and prediction["action"] == "prepare_draft"
        if candidate:
            policy_error = candidate_error(case["case_id"], prediction, catalogue)
        rows.append({"case_id": case["case_id"], "language": case["language"],
                     "category": case["category"], "expected": case["expected"],
                     "prediction": prediction, "schema_valid": schema_error is None,
                     "schema_error": schema_error, "catalogue_error": policy_error,
                     "catalogue_admissible": bool(candidate and not policy_error),
                     "exact_match": not schema_error and prediction == case["expected"]})
    result = {"metrics": aggregate(rows), "by_category": {}, "by_language": {}, "cases": rows}
    for key, group_key in (("category", "by_category"), ("language", "by_language")):
        for value in sorted({row[key] for row in rows}):
            result[group_key][value] = aggregate([row for row in rows if row[key] == value])
    return result


def ratio_text(value):
    if value["denominator"] == 0:
        return "undefined (0 denominator)"
    return "%s/%s (%.1f%%)" % (value["numerator"], value["denominator"], value["value"] * 100)


def markdown_report(report):
    lines = ["# Extraction evaluation: " + report["run"]["label"], "",
             "**Synthetic, public development set. No customer or production result.**", "",
             "Run kind: `" + report["run"]["kind"] + "`. No model inference or handoff is performed by this scorer.", "",
             "Dataset SHA-256: `" + report["dataset_sha256"] + "`.",
             "Catalogue SHA-256: `" + report["catalogue_sha256"] + "`.",
             "Prediction SHA-256: `" + report["prediction_sha256"] + "`.", "",
             "| Measure | Result |", "|---|---:|"]
    for key, value in report["metrics"].items():
        lines.append("| `%s` | %s |" % (key, ratio_text(value) if isinstance(value, dict) else value))
    for title, group in (("Category slices", "by_category"), ("Language slices", "by_language")):
        lines += ["", "## " + title, "", "| Slice | Cases | Exact match | Admissible candidates | Unjustified candidates |", "|---|---:|---:|---:|---:|"]
        for name, metrics in report[group].items():
            lines.append("| %s | %s | %s | %s | %s |" % (name, metrics["cases"], ratio_text(metrics["exact_case_match"]), metrics["catalogue_admissible_candidates"], metrics["unjustified_candidates"]))
    lines += ["", "## Inspect every case", "", "| Case | Category | Gold action | Output action | Exact | Catalogue admissible |", "|---|---|---|---|---|---|"]
    for row in report["cases"]:
        action = row["prediction"]["action"] if row["schema_valid"] else "invalid schema"
        lines.append("| %s | %s | %s | %s | %s | %s |" % (row["case_id"], row["category"], row["expected"]["action"], action, row["exact_match"], row["catalogue_admissible"]))
    lines += ["", "## Interpretation", "",
              "Catalogue admissibility checks known SKU and quantity bounds only. A wrong interpretation can pass those checks. No candidate is sent, approved or handed off.", "",
              "This small hand-authored set is public, has no holdout split and is not representative of customer traffic. Language/category slices contain very few cases. Do not treat these fractions as deployment accuracy, model safety or prompt-injection resistance.", "",
              "The parser baseline deliberately remains unchanged. Natural-language misses and contradictory free-text cases expose its boundary. External outputs and their run labels are supplied by the operator; this scorer does not verify which provider or model generated them.", ""]
    return "\n".join(lines)


def jsonl_text(rows):
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluations" / "cases.jsonl")
    parser.add_argument("--catalogue", type=Path, default=ROOT / "examples" / "catalogue.json")
    parser.add_argument("--predictions", type=Path, help="JSONL with exactly one output per dataset case")
    parser.add_argument("--label", help="Descriptive run label; not independently verified provenance")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "evaluation")
    args = parser.parse_args(argv)
    try:
        catalogue = load_catalogue(args.catalogue)
        cases = validate_dataset(load_jsonl(args.dataset), catalogue)
        predictions = load_jsonl(args.predictions) if args.predictions else baseline_predictions(cases, catalogue)
        label = args.label or ("external-unverified" if args.predictions else "deterministic-parser-baseline")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,119}", label):
            raise EvaluationError("Run label must be 1–120 plain identifier characters.")
        report = score(cases, predictions, catalogue)
        prediction_text = jsonl_text(predictions)
        report.update({"schema_version": 1,
                       "run": {"kind": "external-output-scoring" if args.predictions else "actual-deterministic-parser-baseline", "label": label},
                       "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                       "catalogue_sha256": hashlib.sha256(args.catalogue.read_bytes()).hexdigest(),
                       "prediction_sha256": hashlib.sha256(prediction_text.encode("utf-8")).hexdigest(),
                       "prediction_hash_basis": "UTF-8 JSONL, sorted object keys, preserved row order, one trailing newline per row"})
        names = ["report.json", "report.md", "predictions.jsonl", "inputs.jsonl"]
        sources = {path.resolve() for path in (args.dataset, args.catalogue, args.predictions) if path}
        if any((args.output_dir / name).resolve() in sources for name in names):
            raise EvaluationError("Output files must not overwrite an input file.")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        (args.output_dir / "report.md").write_text(markdown_report(report), encoding="utf-8")
        (args.output_dir / "predictions.jsonl").write_text(prediction_text, encoding="utf-8")
        (args.output_dir / "inputs.jsonl").write_text(jsonl_text([{"case_id": case["case_id"], "message": case["message"]} for case in cases]), encoding="utf-8")
        print("Scored %s synthetic cases. Exact match: %s." % (len(cases), ratio_text(report["metrics"]["exact_case_match"])))
        print("Reports: " + str(args.output_dir))
        return 0
    except (OSError, EvaluationError, ValidationError) as error:
        print("Evaluation input error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
