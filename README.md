# Sales Workflow Reference

[![Synthetic reference checks](https://github.com/UniReverseAI/sales-workflow-reference/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/UniReverseAI/sales-workflow-reference/actions/workflows/checks.yml)

### From enquiry to reviewed handoff.

A small, inspectable reference implementation from **UniReverseAI**. It takes a synthetic sales enquiry, extracts two structured fields, prepares a catalogue-priced draft, checks a decision bound to that draft's exact version, and writes an idempotent handoff to a local SQLite CRM simulation.

The interesting part is what happens when the input is incomplete, a draft changes after review, or a transaction fails. Those behaviors are executable, not just described in an architecture diagram.

**Implementation scope:** Python standard library, deterministic rules, scripted review decisions and a local database. No language model, live CRM/ERP, authenticated human reviewer or outbound messaging is connected. All buyers, products and prices are invented.

## Inspect it in five minutes

1. Read the [actual interpretation baseline](evaluations/baseline-report.md): the existing parser matches **21/32** synthetic cases and proposes **four unjustified candidates** when free text conflicts with otherwise valid structured fields. No candidate is approved or handed off by the scorer. This is a visible limitation of the parser, not a model score.
2. Inspect the [dataset card](evaluations/DATASET_CARD.md) and [evaluation protocol](docs/evaluation.md): public English/German/Chinese development cases, explicit labels, denominators and a provider-neutral output format.
3. Run the control demo below, then review the [production gap](docs/production-gap.md). Passing transaction/review checks does not make the parser suitable for natural customer enquiries.

For the commercial delivery path, see the [buyer's guide](https://github.com/UniReverseAI/delivery-playbook) and [AI value assessment](https://github.com/UniReverseAI/ai-value-assessment).

## Run the evidence

Requires Python **3.9 or later** with its standard `sqlite3` module. No packages, API keys, accounts or network access are needed.

```sh
python3 demo.py
python3 evaluate.py
python3 -m unittest discover -s tests -v
```

Open `artifacts/run-report.html` after running the demo. The same folder contains a machine-readable report, a Markdown report, an example draft, a scripted review record and the resulting local database. Generated artifacts are excluded from version control.

The included scenario suite contains **11 synthetic control scenarios**. Tests cover invalid quantities, non-finite/ambiguous JSON, type-changing drafts and scorer/protocol behavior. Re-run the commands to check the current source. A passing result describes these particular checks; it is not a language-model accuracy score or a production reliability claim.

The separate scorer writes `artifacts/evaluation/report.md`, `report.json`, `predictions.jsonl` and answer-free `inputs.jsonl`. It accepts complete externally generated predictions without calling a provider. See [how to reproduce or score a run](docs/evaluation.md). GitHub Actions publishes the scoring report in its job summary and provides temporary evidence artifacts; inspect the actual run for results and availability.

## Inspect the flow

```text
Synthetic enquiry
    ↓
Strict SKU / Quantity line parser
    ↓
Required fields, known SKU and bounded whole-number quantity
    ↓
Catalogue-priced draft + source hash + version hash
    ↓
Explicit review decision for this exact draft
    ↓
Recheck version, source and current catalogue
    ↓
Transactional, idempotent handoff to SQLite simulation
```

The parser expects lines such as:

```text
Please prepare a draft for review.
SKU: BRKT-100
Quantity: 120
```

With the included synthetic catalogue, this produces a **EUR 1,500.00 draft** at EUR 12.50 per item. It does not send an offer or create an order. Taxes, freight, discounts, customer-specific prices and commercial terms are outside the example.

## Controls you can check

| Trigger | Expected behavior | Evidence |
|---|---|---|
| Quantity is missing or the SKU is unknown | Return a clarification/validation error; no handoff | Demo S02–S04; validation tests |
| Customer text requests a zero price or bypassed approval | Ignore the instruction text; use the trusted catalogue and require review | Demo S05; free-text boundary test |
| Review is absent or negative | Block handoff | Demo S06 and S11 |
| Any draft field changes after review | Invalidate the earlier decision | Demo S07; version test |
| A caller approves a manipulated price | Rebuild from source and catalogue; reject the inconsistent draft | Source validation test |
| Identical handoff is retried with unchanged source and catalogue | Return the original record instead of duplicating it | Demo S08; idempotency test |
| Transaction fails after insertion and before commit | Roll back the insertion; an explicit retry can succeed | Demo S09; rollback test |
| A different draft reuses a committed enquiry ID | Reject the conflict; keep the existing record | Demo S10; conflict test |

The untrusted-text check concerns the deterministic parser only. It does **not** demonstrate that a language model is resistant to prompt injection.

Every handoff attempt revalidates the supplied source and current catalogue before checking for a replay. If the catalogue changes, an old draft is rejected even if it was previously committed; the original record remains intact. A customer integration must agree how to reconcile historical outcomes after business-rule changes.

## Where to look

| File | Review focus |
|---|---|
| [`workflow.py`](workflow.py) | Parsing, exact decimal pricing, version checks and database transaction |
| [`demo.py`](demo.py) | Scripted scenario runner and evidence generation |
| [`evaluate.py`](evaluate.py) | Offline scoring of SKU/quantity extraction and abstentions, including external predictions |
| [`evaluations/`](evaluations/) | Public synthetic development set, actual parser outputs and reproducible baseline report |
| [`examples/`](examples/) | Small synthetic enquiry set and catalogue |
| [`tests/test_workflow.py`](tests/test_workflow.py) | Executable checks for boundaries and failure behavior |
| [`docs/architecture.md`](docs/architecture.md) | Data flow, trust boundaries and storage |
| [`docs/acceptance.md`](docs/acceptance.md) | Reviewer acceptance procedure and scenario coverage |
| [`docs/evaluation.md`](docs/evaluation.md) | Quality metrics, invalid-output handling, denominators and evaluation boundaries |
| [`docs/production-gap.md`](docs/production-gap.md) | Work still required before any customer deployment |

## What this reference is useful for

Use it to inspect how we structure a bounded workflow, separate customer input from business policy, make review decisions version-specific and test recovery behavior. It can also support a technical discussion about a client's sales-to-production workflow.

It does not establish the team's customer history, a deployed product, any claimed savings, legal compliance or availability commitments. Those require their own evidence and an agreed customer scope.

The review record is an ordinary local object. Its reviewer label is **not authenticated**, and a SHA-256 digest is a change-detection mechanism, not a digital signature. A local caller can construct a positive review record; this reference does not protect against that caller or a compromised environment. Production review requires identity, permissions, access controls and an approval record protected from unauthorized changes.

## Security, support and rights

Read [`SECURITY.md`](SECURITY.md) for reporting and data-handling guidance. This is an inspectable reference, with no promised production support or response window. See [`LICENSE`](LICENSE) for rights; no general open-source license is granted.

Discuss a workflow with [Eric@unireverseai.com](mailto:Eric@unireverseai.com). The company website at unireverseai.com is in preparation.
