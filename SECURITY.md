# Security and data handling

This reference is intended for local inspection with the included synthetic data. It is not a hosted service and makes no network calls.

## Reporting

For a suspected security issue, use the contact route on [unireverseai.com](https://unireverseai.com). Describe the affected file, a minimal synthetic reproduction and the expected boundary. Do not post credentials, customer data or private system details in a public issue. No security response time is promised for this reference.

## Local data

- Inputs in `examples/` are invented. Use synthetic data when reproducing issues.
- Generated artifacts include draft and review data in a local SQLite file. They remain until the operator removes them.
- Review labels are not authenticated identities. Database events are not tamper-proof audit records.
- A draft digest detects changed content; it does not authenticate the reviewer or secure a compromised environment.
- Pricing rules and business permissions must stay outside untrusted customer text.

Read [`docs/production-gap.md`](docs/production-gap.md) before considering a client deployment.
