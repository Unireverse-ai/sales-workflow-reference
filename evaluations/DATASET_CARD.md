# Dataset card: synthetic enquiry interpretation v1

**Purpose:** make the boundary between a narrow structured-field parser and interpretation of a complete enquiry inspectable. This is a small public development set, not customer data or a held-out benchmark.

## Contents and provenance

[`cases.jsonl`](cases.jsonl) contains 32 hand-authored messages and expected action/SKU/quantity labels. Every buyer context, product, quantity and commercial request is invented. The two product identifiers and allowed quantities come from the [synthetic catalogue](../examples/catalogue.json). No customer records, provider outputs or private business measurements were used to produce the labels.

The set was authored for this reference on 28 October 2026. Labels reflect the policy below; they have not been independently annotated, audited or agreed with a customer. Reviewers can inspect every message and challenge a label by its case ID and rationale. Use synthetic reproductions in public issues.

| Dimension | Count |
|---|---:|
| All cases | 32 |
| Expected draft candidate | 16 |
| Expected clarification | 16 |
| Structured-field messages | 7 |
| Natural-language messages | 7 |
| Contradictions/cancellation | 4 |
| Missing information | 3 |
| Catalogue/quantity boundaries | 6 |
| Repeated-field ambiguity | 2 |
| Instruction-like customer text | 3 |

English, German and Chinese messages are included to expose format/interpretation differences. Their slices are tiny and are not estimates of language coverage. Actual counts and per-case results appear in the generated report; no language has enough examples here to support a deployment claim.

## Annotation policy

A `prepare_draft` label means the complete message unambiguously specifies one known SKU and an integer quantity within that product's limit, without a conflicting instruction about the requested product, quantity or whether to prepare anything. The expected object contains exactly `action`, `sku` and `quantity`.

A `clarify` label abstains from both fields when a required value is absent, a product/quantity is invalid, structured fields are repeated, the message contains an unresolved correction or change, or the request is cancelled. The clarification action is a deliberately broad stop/clarify state; the reference does not implement separate cancellation or rejection queues.

Instruction-like text attempting to change prices, grant approval or send an offer cannot control those actions. Where valid product/quantity information is otherwise unambiguous, the extraction label remains a draft candidate; it does **not** authorize the requested pricing or sending action. A small fixture containing such text does not establish resistance to prompt injection in a model that is not connected here.

The narrow parser intentionally has a different capability boundary: it reads explicit SKU/Quantity lines and ignores other text. It therefore misses natural-language-only messages and cannot reconcile free-text cancellations or corrections. Those mismatches remain in the baseline evidence. The parser has not been tuned to the public gold answers.

## Files and reproducibility

- [`cases.jsonl`](cases.jsonl): messages, categories, language labels and public expected answers.
- [`baseline-predictions.jsonl`](baseline-predictions.jsonl): outputs actually produced by the deterministic parser, with no gold-answer substitution.
- [`baseline-report.md`](baseline-report.md): the reproducible scored result for those outputs.

Run `python3 evaluate.py` from the repository root. Generated `inputs.jsonl` removes the expected labels for use by a separate runner. The answers remain publicly available in this repository, so using that file does not create a secret holdout set. Report fingerprints bind the exact dataset/catalogue bytes and normalized predictions to each result. See [the scoring protocol](../docs/evaluation.md) for the hash definition and metrics.

No model/provider run is included. Gold answers are copied into a fixture in a unit test solely to check the scorer; that test is not an accuracy result and is not the published baseline.

## Exclusions and limitations

The set excludes customer-specific terminology, real correspondence, attachments, images, documents, thread history, multi-item quotes, tax/freight, complex units, authentication and downstream actions. Its balanced label counts and manually selected edge cases do not reflect the frequency of cases in a real inbox. It has no train/test split, independent holdout, inter-annotator agreement or statistical performance guarantee.

Adding a real model requires a separately recorded run and representative data collected with appropriate permission. Tuning on these public examples and then quoting their scores as unseen performance would be misleading. Changing a label, product limit or message changes the evidence; regenerate and review the baseline report when making such changes.
