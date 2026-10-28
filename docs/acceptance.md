# Reviewer acceptance procedure

## Run from the repository root

```sh
python3 -m unittest discover -s tests -v
python3 demo.py
```

Both commands must exit with code `0`. The default demo must report `11/11` synthetic scenarios passed and `2` local CRM records. These are fixture-specific acceptance expectations, not a service-level objective or a model benchmark.

## Inspect generated evidence

1. Open `artifacts/run-report.html` or `artifacts/run-report.md`.
2. Inspect `artifacts/run-report.json` for individual observations, blocked action codes and committed audit events.
3. Inspect `artifacts/example-draft.json` and `artifacts/scripted-review.json`. Confirm that the review's `draft_hash` matches the draft's `version_hash`.
4. Inspect the database if desired, using Python's standard library:

   ```sh
   python3 -c "import sqlite3; c=sqlite3.connect('artifacts/crm-demo.sqlite3'); print(c.execute('SELECT inquiry_id, record_id FROM crm_handoffs ORDER BY inquiry_id').fetchall())"
   ```

   Expected enquiry identifiers: `SYN-001` and `SYN-008`. No other synthetic enquiry should have a committed handoff.

## Scenario coverage

| ID | Trigger | Required observation |
|---|---|---|
| S01 | Complete enquiry and positive scripted review | EUR 1,500.00 draft; one local handoff |
| S02 | Missing quantity | `missing_quantity`; no new handoff |
| S03 | Unknown SKU | `unknown_sku`; no new handoff |
| S04 | Negative quantity | `invalid_quantity`; no new handoff |
| S05 | Free text requests price override and bypass | Catalogue price preserved; `approval_required` |
| S06 | No review decision | `approval_required` |
| S07 | Total edited after review | `approval_version_mismatch` |
| S08 | Identical handoff repeated | Same record; `replayed: true`; count unchanged |
| S09 | Failure after insert, then explicit retry | Count unchanged after failure; one new record after retry |
| S10 | Changed draft reuses committed enquiry ID | `inquiry_conflict`; prior record preserved |
| S11 | Negative review decision | `approval_required` |

The workflow tests additionally check decimal arithmetic, duplicate structured fields and catalogue JSON keys, invalid and excessive quantities, boolean/float type-changing edits, non-finite values, directly supplied catalogue objects, source changes, catalogue changes (including attempted replay), a reapproved manipulated price, input bounds and stable canonical hashing. A separate test records the explicit limitation that a locally constructed positive review record is accepted without authenticating a person.

The extraction scorer has its own tests for schema validity, complete case coverage, duplicate/unknown IDs, denominators, abstention, catalogue admissibility and reproducible report snapshots. Run `python3 evaluate.py` for the actual parser's [32-case baseline](../evaluations/baseline-report.md), including the interpretation failures. The scorer exiting successfully means a complete valid run was scored; it does not enforce a deployment quality threshold or establish a model result.

## Review the gaps

Before adapting this code to a client workflow, review [`production-gap.md`](production-gap.md). In particular, the scripted decision path must not be represented as an authenticated human approval system, and this deterministic parser must not be represented as a language-model evaluation.

The CI workflow runs the control suite, demo and extraction scorer on its declared Python versions. A workflow file is not evidence of an actual GitHub Actions run; inspect the current run record, job summary and available report artifacts.
