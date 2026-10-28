"""Run reproducible synthetic control scenarios and write local evidence artifacts."""

import argparse
import html
import json
import platform
import shutil
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from workflow import LocalCRM, WorkflowError, build_draft, load_catalogue, record_review


ROOT = Path(__file__).resolve().parent


def expect_code(action, expected):
    try:
        action()
    except WorkflowError as error:
        if error.code != expected:
            raise AssertionError("Expected %s; observed %s" % (expected, error.code)) from error
        return {"error_code": error.code, "message": str(error)}
    raise AssertionError("Expected rejection: " + expected)


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    catalogue = load_catalogue(ROOT / "examples" / "catalogue.json")
    inquiries = json.loads((ROOT / "examples" / "inquiries.json").read_text(encoding="utf-8"))
    rows = []

    def scenario(identifier, title, action):
        try:
            observed = action()
            rows.append({"id": identifier, "title": title, "passed": True, "observed": observed})
        except Exception as error:
            rows.append({"id": identifier, "title": title, "passed": False, "observed": {"error": str(error)}})

    with tempfile.TemporaryDirectory(prefix="unireverse-synthetic-") as scratch:
        database = Path(scratch) / "crm-demo.sqlite3"
        crm = LocalCRM(database)
        draft = build_draft(inquiries[0], catalogue)
        approval = record_review(draft, "SCRIPTED_SYNTHETIC_REVIEWER", "approve")

        def happy():
            result = crm.handoff(inquiries[0], draft, approval, catalogue)
            assert draft.total == "1500.00"
            assert crm.count_handoffs() == 1
            return {"draft_total": draft.total, "currency": draft.currency, **asdict(result)}

        scenario("S01", "Approved synthetic draft reaches local CRM simulation", happy)
        scenario("S02", "Missing quantity requires clarification", lambda: expect_code(lambda: build_draft(inquiries[1], catalogue), "missing_quantity"))
        scenario("S03", "Unknown SKU is rejected", lambda: expect_code(lambda: build_draft(inquiries[2], catalogue), "unknown_sku"))
        scenario("S04", "Negative quantity is rejected", lambda: expect_code(lambda: build_draft(inquiries[3], catalogue), "invalid_quantity"))

        def injection():
            suspicious = build_draft(inquiries[4], catalogue)
            assert suspicious.unit_price == "12.50"
            assert suspicious.total == "1500.00"
            blocked = expect_code(lambda: crm.handoff(inquiries[4], suspicious, None, catalogue), "approval_required")
            return {"catalogue_price_preserved": True, "free_text_instructions_ignored": True, **blocked}

        scenario("S05", "Untrusted text cannot set price or bypass review", injection)

        def no_approval():
            unsigned = build_draft(inquiries[5], catalogue)
            return expect_code(lambda: crm.handoff(inquiries[5], unsigned, None, catalogue), "approval_required")

        scenario("S06", "Handoff without approval is blocked", no_approval)

        def changed_draft():
            original = build_draft(inquiries[6], catalogue)
            reviewed = record_review(original, "SCRIPTED_SYNTHETIC_REVIEWER", "approve")
            changed = replace(original, total="0.00")
            return expect_code(lambda: crm.handoff(inquiries[6], changed, reviewed, catalogue), "approval_version_mismatch")

        scenario("S07", "An edit invalidates the earlier approval", changed_draft)

        def replay():
            before = crm.count_handoffs()
            result = crm.handoff(inquiries[0], draft, approval, catalogue)
            assert result.replayed and crm.count_handoffs() == before
            return {"records_before": before, "records_after": crm.count_handoffs(), **asdict(result)}

        scenario("S08", "Repeated handoff returns the existing record", replay)

        def retry():
            retry_draft = build_draft(inquiries[7], catalogue)
            reviewed = record_review(retry_draft, "SCRIPTED_SYNTHETIC_REVIEWER", "approve")
            before = crm.count_handoffs()
            failure = expect_code(
                lambda: crm.handoff(inquiries[7], retry_draft, reviewed, catalogue, simulate_failure_after_insert=True),
                "simulated_transient_failure",
            )
            after_failure = crm.count_handoffs()
            assert after_failure == before
            result = crm.handoff(inquiries[7], retry_draft, reviewed, catalogue)
            assert crm.count_handoffs() == before + 1 and not result.replayed
            return {"injected_failure": failure["error_code"], "records_before": before, "records_after_failure": after_failure, "records_after_retry": crm.count_handoffs()}

        scenario("S09", "Transaction rolls back and a later explicit retry succeeds", retry)

        def conflicting_replay():
            changed = dict(inquiries[0], message="SKU: BRKT-100\nQuantity: 121")
            new_draft = build_draft(changed, catalogue)
            reviewed = record_review(new_draft, "SCRIPTED_SYNTHETIC_REVIEWER", "approve")
            return expect_code(lambda: crm.handoff(changed, new_draft, reviewed, catalogue), "inquiry_conflict")

        scenario("S10", "A changed draft cannot overwrite a committed inquiry", conflicting_replay)

        def rejected_review():
            original = build_draft(inquiries[5], catalogue)
            rejected = record_review(original, "SCRIPTED_SYNTHETIC_REVIEWER", "reject")
            return expect_code(lambda: crm.handoff(inquiries[5], original, rejected, catalogue), "approval_required")

        scenario("S11", "A negative review decision prevents handoff", rejected_review)

        passed = sum(row["passed"] for row in rows)
        report = {
            "title": "UniReverseAI | Synthetic sales workflow control report",
            "scope": "Local rule-based parsing, version-bound review contract and SQLite simulation. Scripted review decisions; no human authentication, model call, live integration or customer data.",
            "runtime": "Python " + platform.python_version(),
            "dataset": "examples/inquiries.json",
            "catalogue_version": catalogue["version"],
            "summary": {"passed": passed, "total": len(rows), "local_crm_records": crm.count_handoffs(), "external_messages_sent": 0},
            "scenarios": rows,
            "audit_events": crm.audit_events(),
        }
        shutil.copyfile(database, output / "crm-demo.sqlite3")
    (output / "run-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "example-draft.json").write_text(json.dumps({"draft": asdict(draft), "version_hash": draft.version_hash}, indent=2) + "\n", encoding="utf-8")
    (output / "scripted-review.json").write_text(json.dumps(asdict(approval), indent=2) + "\n", encoding="utf-8")
    markdown = ["# " + report["title"], "", report["scope"], "", "**%d / %d synthetic control scenarios passed.** This is not a model accuracy or customer performance benchmark." % (passed, len(rows)), "", "| ID | Scenario | Result |", "|---|---|---|"]
    markdown.extend("| %s | %s | %s |" % (row["id"], row["title"], "PASS" if row["passed"] else "FAIL") for row in rows)
    markdown.extend(["", "Local CRM records: %d. External messages sent: 0." % report["summary"]["local_crm_records"], "", "See `run-report.json` for individual observations and committed audit events.", ""])
    (output / "run-report.md").write_text("\n".join(markdown), encoding="utf-8")
    table = "".join("<tr><td>%s</td><td>%s</td><td class='%s'>%s</td></tr>" % (html.escape(row["id"]), html.escape(row["title"]), "pass" if row["passed"] else "fail", "PASS" if row["passed"] else "FAIL") for row in rows)
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Synthetic workflow report | UniReverseAI</title>
<style>body{margin:0;background:#f6f5f1;color:#1d1d1b;font:16px/1.6 system-ui,sans-serif}main{max-width:980px;margin:auto;padding:64px 24px}small{letter-spacing:.13em;text-transform:uppercase}h1{font-size:clamp(32px,6vw,58px);line-height:1.07;max-width:780px;font-weight:550;letter-spacing:-.04em}p{max-width:780px;color:#555}strong{color:#1d1d1b}.score{font-size:48px;letter-spacing:-.04em;border-top:1px solid #ccc;padding-top:24px;margin-top:36px}table{width:100%%;border-collapse:collapse;margin:24px 0}td,th{text-align:left;padding:15px 10px;border-bottom:1px solid #d8d6cf}th{font-size:12px;text-transform:uppercase;letter-spacing:.08em}.pass{color:#276743}.fail{color:#a12626}code{font-size:14px}footer{margin-top:40px;font-size:13px;color:#666}</style>
<main><small>UniReverseAI / Public reference implementation</small><h1>Review the controls.<br>Inspect the evidence.</h1><p>%s</p><div class="score">%s / %s <span style="font-size:18px">synthetic scenarios passed</span></div><p>These results test the included deterministic examples. They do not measure language-model quality, production reliability or business savings.</p><table><thead><tr><th>ID</th><th>Control scenario</th><th>Result</th></tr></thead><tbody>%s</tbody></table><p><strong>%s local CRM records. Zero external messages.</strong> Inspect <code>run-report.json</code>, <code>example-draft.json</code> and <code>crm-demo.sqlite3</code> alongside this report.</p><footer>Run locally with Python standard library. Synthetic products, buyers, prices and review decisions.</footer></main></html>""" % (html.escape(report["scope"]), passed, len(rows), table, report["summary"]["local_crm_records"])
    (output / "run-report.html").write_text(page, encoding="utf-8")
    print("Synthetic control scenarios: %d/%d passed" % (passed, len(rows)))
    print("Local records: %d | External messages: 0" % report["summary"]["local_crm_records"])
    print("Evidence: " + str(output.resolve() / "run-report.html"))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts", help="Directory for local generated evidence (default: artifacts/).")
    args = parser.parse_args()
    raise SystemExit(run(args.output_dir))
