# From reference to a customer deployment

This document is a scoping aid. It records work omitted from this small reference and the evidence a customer implementation should supply before acceptance.

| Area | Reference behavior | Required customer-specific work and evidence |
|---|---|---|
| Identity and approval | Reviewer label and decision in a local object | Authenticate users, enforce reviewer permissions and separation of duties, protect review records, bind decisions to the exact proposal, and test rejected/expired/revoked approval paths. |
| Enquiry interpretation | Two deterministic key-value fields | Define supported email/attachment formats and languages. If a model is used, select an agreed provider, validate structured outputs and evaluate representative examples, adversarial content and human escalation. |
| Pricing | Fixed synthetic EUR catalogue | Integrate an authoritative pricing source; define taxes, freight, discounts, customer terms, validity and sign-off. Recheck commercial values before any external offer. |
| System integration | Local SQLite simulation | Use approved CRM/ERP APIs and credentials; map identifiers and statuses; test duplicate delivery, partial failures, reconciliation and compensating actions against a sandbox. |
| Data protection | Synthetic local files | Agree on data categories, destinations, access, retention, deletion and supplier responsibilities; implement and verify the agreed controls. No compliance conclusion follows from this reference. |
| Security operations | No external service or accounts | Assess deployment threats; protect secrets and network access; scan dependencies; define vulnerability handling and incident ownership. |
| Observability | Local committed audit events and a scenario report | Add protected operational logs for successes and failures, redaction, metrics, alerts and an incident investigation path. |
| Reliability | Local atomic transaction and explicit retry | Define business-specific error budgets, timeout and retry policy, retry limits, dead-letter handling, restore procedures and recovery exercises. |
| Delivery acceptance | Synthetic controls | Agree on real representative test cases, quality thresholds, pricing invariants, review duties, rollback triggers, business baselines and acceptance owners. |
| Commercial support | No promised response window | Agree on operating ownership, support hours, incident priorities, change scope, hosting/model costs and handover terms. |

## A bounded pilot

A reasonable first pilot covers one workflow, a defined product subset and one agreed downstream system. Start in shadow mode: prepare drafts and compare them with the existing process without sending quotations or modifying production records. Move to reviewed execution only after the business owner signs off the test cases, approval path and recovery procedure.

Measure processing time and manual effort separately from cash savings. Include review time, exceptions, implementation effort, ongoing model/hosting fees and maintenance. This repository provides no measured customer outcome.
