# Evaluate interpretation separately from workflow controls

The workflow's control tests check pricing, review-version binding and local transaction behavior. They do not measure how well a system understands incoming language. `evaluate.py` adds a separate, offline extraction scoring path.

Start with the [actual baseline report](../evaluations/baseline-report.md) and [dataset card](../evaluations/DATASET_CARD.md). The baseline is the existing deterministic parser, not a language model. On the 32 public synthetic cases it matches 21 exactly, misses seven natural-language requests and proposes four catalogue-valid candidates where a clarification is expected. These are visible limitations, not a production score.

## Reproduce the result

```sh
python3 evaluate.py
python3 -m unittest discover -s tests -v
```

The default run writes these local, ignored files under `artifacts/evaluation/`:

| File | Purpose |
|---|---|
| `report.md` | Measures, denominators, language/category slices and every case result |
| `report.json` | The same evidence, complete predictions and input fingerprints |
| `predictions.jsonl` | Actual outputs from this run |
| `inputs.jsonl` | Case ID and message only, without expected answers |

Use `--output-dir PATH` to select another local destination. Checked-in copies in `evaluations/` let a reviewer inspect the baseline before running anything. Tests check that those copies match a fresh run. GitHub Actions also runs the scorer, adds the Markdown report to its job summary and makes reports available as temporary run artifacts. Inspect the actual run and artifact availability; a workflow file or green test result does not establish extraction quality.

Dataset and catalogue fingerprints hash their exact file bytes. The prediction fingerprint hashes normalized UTF-8 JSONL with sorted object keys, preserved row order and one trailing newline per row; it is not a raw-provider response fingerprint. The JSON report records this hash basis. Reordering rows preserves scores while changing that prediction fingerprint.

## Score outputs produced elsewhere

The scorer makes no model calls. An operator can supply outputs from any provider or from another parser after running that system independently on the answer-free `inputs.jsonl` messages. Record the exact model/version, prompt, decoding settings, date, failures, cost and timing in the separate run record. This tool does not verify that provenance or measure inference latency/cost.

The prediction protocol has one UTF-8 JSONL row for **every** dataset case:

```json
{"case_id":"EVAL-001","prediction":{"action":"prepare_draft","sku":"BRKT-100","quantity":120}}
{"case_id":"EVAL-017","prediction":{"action":"clarify","sku":null,"quantity":null}}
```

These two lines illustrate the protocol only; a two-line file cannot score the 32-case set. A valid complete file is the [committed actual baseline output](../evaluations/baseline-predictions.jsonl). Replay it with:

```sh
python3 evaluate.py --predictions evaluations/baseline-predictions.jsonl --label deterministic-parser-replay --output-dir artifacts/replay
```

For independently obtained model outputs, replace the path and choose a descriptive `--label`. A label is supplied by the operator and does not authenticate a model result.

Only `prepare_draft` and `clarify` actions are supported. Draft candidates require an uppercase SKU identifier and a JSON integer quantity; booleans, floats and numeric strings are invalid. Clarifications require both fields to be null. Extra prediction fields such as price, approval or destination are invalid and cannot affect business policy.

## What the scorer admits and rejects

- Unknown or repeated case IDs, missing cases, extra envelope fields, duplicate JSON keys, non-finite numbers and malformed JSON cause the **whole file** to fail before new reports are written. Cases cannot disappear from the denominator.
- A valid row whose `prediction` has an invalid shape is retained and counted as an invalid output and an incorrect case. A raw text response may be stored as a JSON string in `prediction`; it will count as invalid schema rather than being silently discarded. This is not a measurement of raw-provider JSON syntax failure rates.
- Known schema and business validity are separate checks. The scorer passes candidate SKU/quantity values through the existing catalogue validation path. Unknown SKUs, nonpositive quantities and per-product limits are rejected.
- An admissible candidate has only passed SKU/quantity checks. The original message may have been misunderstood. The scorer does not create a CRM record, approve a draft or call the workflow handoff function.

The scorer's constructed structured message is only a way to reuse existing value checks. It is not a replacement source message or provenance record for a customer draft. An actual model integration needs a source-bound proposal format, authenticated review and a protected action boundary.

## Read the denominators

| Measure | Numerator / denominator |
|---|---|
| Schema validity | Schema-valid outputs / all cases |
| Exact case match | Entire action/SKU/quantity matches the label / all cases |
| Action accuracy | Correct supported action / all cases; invalid schema is incorrect |
| SKU or quantity accuracy | Correct field in a schema-valid draft prediction / gold draftable cases |
| Draftable-case recall | Exactly correct, catalogue-admissible candidates / gold draftable cases |
| Clarification recall | Correct abstentions / gold clarification cases |
| Abstention rate | Schema-valid clarification outputs / all cases |
| Candidate precision | Exactly correct draft candidates / all catalogue-admissible candidates |
| Blocked-case candidate rate | Catalogue-admissible candidates on gold clarification cases / gold clarification cases |

`unjustified_candidates` counts all admitted candidates with the wrong action or fields. It is not a count of actual handoffs or incidents. A zero denominator is displayed as undefined, not as perfect performance. The JSON report includes numerator, denominator and fraction for each rate; category and language slices use their own denominators.

The catalogue check is intentionally insufficient to determine semantic correctness. For example, a syntactically valid BRKT-100 request with a later cancellation still passes the parser's narrow key-value contract. The evaluation labels ask whether preparing a candidate is appropriate for the **whole message**, so that mismatch is exposed rather than hidden. No language/cancellation keyword exceptions have been added to improve this public score.

## Before using natural customer enquiries

Agree the target workflow and annotation policy with its business owner. Collect permitted representative examples, include difficult and rare cases, resolve annotator disagreements and keep an independent held-out set unavailable during tuning. Evaluate supported languages, attachments, contradictions, failures and adversarial content; examine wrong proposals and unnecessary abstentions separately. Agree acceptable error and review-load thresholds for that specific workflow before release.

These public examples are a development aid. Passing unit/control tests, matching synthetic labels or blocking the small instruction-text slice does not establish model safety, prompt-injection resistance or customer readiness. The [production gap](production-gap.md) remains relevant.

## Design references

The distinction between intended-use evidence and generic accuracy follows the contextual approach in [NIST AI RMF: AI Risks and Trustworthiness](https://airc.nist.gov/airmf-resources/airmf/3-sec-characteristics/). Output validation, limited action authority, human approval and adversarial testing are also discussed in [OWASP LLM01: Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/). These references inform the design; this repository makes no certification or conformance claim.
