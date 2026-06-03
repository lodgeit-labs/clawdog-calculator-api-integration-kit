---
name: Service issue
about: "I think the API behaves incorrectly" — substrate-side bug report
title: '[Service] '
labels: ['service-issue', 'bug']
assignees: []
---

## Symptom

A one-sentence description of the observed behaviour. (E.g. "FBT Car-Operating-Cost returns taxable value $X for inputs Y, but the statutory algebra gives $Z.")

## Reproducer

The exact inputs that reproduce the behaviour. **Include all of:**

- **Calculator URN:** `urn:sbrm:calculator:fbt:...`
- **Period URN:** `urn:sbrm:period:fbt:fy2026` (or whichever)
- **Full request body** (with any customer PII redacted; keep the *numeric inputs* literal):

```json
{
  "...": "..."
}
```

- **HTTP response status:** `200` / `4xx` / `5xx`
- **Full response body** (also with PII redacted):

```json
{
  "...": "..."
}
```

## Expected behaviour

What you expected the substrate to return, and why. **Cite the statute-of-record** (e.g. `FBTAA s.9 statutory formula gives: taxable_value = base_value × statutory_fraction × days_held / days_in_year × (1 − rebatable_employee_share)`) and show the algebra step-by-step.

If you've compared against a known-good reference implementation (a parity sheet, a C# tax engine, a published worked example from an ATO publication, an authoritative textbook), cite the reference.

## Cross-checks you've already run

- [ ] Verified the substrate is reachable (`curl /v1/calculators` returns 200).
- [ ] Verified the response is not a 502 (would indicate a resolver-shape mismatch, not a calculation bug).
- [ ] Verified the request body validates against the OpenAPI schema for this calculator.
- [ ] Verified the period URN matches the calculator's `supported_periods`.
- [ ] Re-ran the call against the kit's example fixture to confirm the substrate is otherwise responsive.

## Environment

- Kit version: `vX.Y.Z`
- API version observed (from `openapi.json#/info/version`): `v...`
- Calculator URN
- Period URN
- Approximate time of the failing call (UTC)

## Triage path

Service issues triage to ClawDog (the LodgeiT Labs autonomous engineering agent). If reproducible, ClawDog opens a fix-tracking issue against [`lodgeit-labs/clawdog-calculator-api`](https://github.com/lodgeit-labs/clawdog-calculator-api) and replies here with the link. Fixes typically land within a sprint.

If you suspect the bug is privacy-sensitive (the response leaks something it shouldn't, or the request mishandles PII), please open a private security advisory via the repository's [Security tab](../../security/advisories/new) instead of filing publicly.
