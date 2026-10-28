# Security and data handling

This reference is intended for local inspection with the included synthetic data. It is not a hosted service and makes no network calls.

## Reporting

For a suspected security issue, contact [Eric@unireverseai.com](mailto:Eric@unireverseai.com), the published business contact. Start with the affected file, a minimal synthetic reproduction and the expected boundary. Arrange an appropriate sharing method before transmitting sensitive technical details; do not send credentials or customer data, or post them in a public issue. This is not a dedicated security response service and no response time is promised for the reference.

## Local data

- Inputs in `examples/` are invented. Use synthetic data when reproducing issues.
- Generated artifacts include draft and review data in a local SQLite file. They remain until the operator removes them.
- Review labels are not authenticated identities. Database events are not tamper-proof audit records.
- A draft digest detects changed content; it does not authenticate the reviewer or secure a compromised environment.
- Pricing rules and business permissions must stay outside untrusted customer text.

Read [`docs/production-gap.md`](docs/production-gap.md) before considering a client deployment.
