# Extraction evaluation: deterministic-parser-baseline

**Synthetic, public development set. No customer or production result.**

Run kind: `actual-deterministic-parser-baseline`. No model inference or handoff is performed by this scorer.

Dataset SHA-256: `1bbb5868f52c93325da117a07e88e686339ce4c919c33487f987d3fe93bbf94e`.
Catalogue SHA-256: `e7c8c3ecec55414aa8bb67fa27487337819a4413eceff9c9ec95382e25aaaaba`.
Prediction SHA-256: `5ead2cc93bfb1195dcda1c473b280dbdd1af4bde6ed055f1a9c4f4f00c7dbbc2`.

| Measure | Result |
|---|---:|
| `cases` | 32 |
| `schema_validity` | 32/32 (100.0%) |
| `exact_case_match` | 21/32 (65.6%) |
| `action_accuracy` | 21/32 (65.6%) |
| `sku_accuracy_on_draftable_cases` | 9/16 (56.2%) |
| `quantity_accuracy_on_draftable_cases` | 9/16 (56.2%) |
| `draftable_case_recall` | 9/16 (56.2%) |
| `clarification_recall` | 12/16 (75.0%) |
| `abstention_rate` | 19/32 (59.4%) |
| `candidate_precision` | 9/13 (69.2%) |
| `blocked_case_candidate_rate` | 4/16 (25.0%) |
| `catalogue_admissible_candidates` | 13 |
| `unjustified_candidates` | 4 |
| `schema_invalid_outputs` | 0 |
| `catalogue_rejected_candidates` | 0 |

## Category slices

| Slice | Cases | Exact match | Admissible candidates | Unjustified candidates |
|---|---:|---:|---:|---:|
| ambiguity | 2 | 2/2 (100.0%) | 0 | 0 |
| catalogue_boundary | 6 | 6/6 (100.0%) | 0 | 0 |
| contradiction | 4 | 0/4 (0.0%) | 4 | 4 |
| instruction_text | 3 | 3/3 (100.0%) | 2 | 0 |
| missing_information | 3 | 3/3 (100.0%) | 0 | 0 |
| natural_language | 7 | 0/7 (0.0%) | 0 | 0 |
| structured | 7 | 7/7 (100.0%) | 7 | 0 |

## Language slices

| Slice | Cases | Exact match | Admissible candidates | Unjustified candidates |
|---|---:|---:|---:|---:|
| de | 8 | 5/8 (62.5%) | 3 | 1 |
| en | 15 | 10/15 (66.7%) | 6 | 2 |
| zh | 9 | 6/9 (66.7%) | 4 | 1 |

## Inspect every case

| Case | Category | Gold action | Output action | Exact | Catalogue admissible |
|---|---|---|---|---|---|
| EVAL-001 | structured | prepare_draft | prepare_draft | True | True |
| EVAL-002 | structured | prepare_draft | prepare_draft | True | True |
| EVAL-003 | structured | prepare_draft | prepare_draft | True | True |
| EVAL-004 | structured | prepare_draft | prepare_draft | True | True |
| EVAL-005 | structured | prepare_draft | prepare_draft | True | True |
| EVAL-006 | structured | prepare_draft | prepare_draft | True | True |
| EVAL-007 | structured | prepare_draft | prepare_draft | True | True |
| EVAL-008 | instruction_text | prepare_draft | prepare_draft | True | True |
| EVAL-009 | natural_language | prepare_draft | clarify | False | False |
| EVAL-010 | natural_language | prepare_draft | clarify | False | False |
| EVAL-011 | natural_language | prepare_draft | clarify | False | False |
| EVAL-012 | natural_language | prepare_draft | clarify | False | False |
| EVAL-013 | natural_language | prepare_draft | clarify | False | False |
| EVAL-014 | natural_language | prepare_draft | clarify | False | False |
| EVAL-015 | natural_language | prepare_draft | clarify | False | False |
| EVAL-016 | contradiction | clarify | prepare_draft | False | True |
| EVAL-017 | missing_information | clarify | clarify | True | False |
| EVAL-018 | missing_information | clarify | clarify | True | False |
| EVAL-019 | catalogue_boundary | clarify | clarify | True | False |
| EVAL-020 | catalogue_boundary | clarify | clarify | True | False |
| EVAL-021 | catalogue_boundary | clarify | clarify | True | False |
| EVAL-022 | catalogue_boundary | clarify | clarify | True | False |
| EVAL-023 | catalogue_boundary | clarify | clarify | True | False |
| EVAL-024 | catalogue_boundary | clarify | clarify | True | False |
| EVAL-025 | ambiguity | clarify | clarify | True | False |
| EVAL-026 | ambiguity | clarify | clarify | True | False |
| EVAL-027 | contradiction | clarify | prepare_draft | False | True |
| EVAL-028 | contradiction | clarify | prepare_draft | False | True |
| EVAL-029 | contradiction | clarify | prepare_draft | False | True |
| EVAL-030 | instruction_text | prepare_draft | prepare_draft | True | True |
| EVAL-031 | instruction_text | clarify | clarify | True | False |
| EVAL-032 | missing_information | clarify | clarify | True | False |

## Interpretation

Catalogue admissibility checks known SKU and quantity bounds only. A wrong interpretation can pass those checks. No candidate is sent, approved or handed off.

This small hand-authored set is public, has no holdout split and is not representative of customer traffic. Language/category slices contain very few cases. Do not treat these fractions as deployment accuracy, model safety or prompt-injection resistance.

The parser baseline deliberately remains unchanged. Natural-language misses and contradictory free-text cases expose its boundary. External outputs and their run labels are supplied by the operator; this scorer does not verify which provider or model generated them.
