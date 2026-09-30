# Kit Gates

Runnable assertion gates for the ClawDog Calculator-Constellation integration
kit. Each gate is a self-contained, stdlib-only Python script that a partner can
run locally *and* that the kit's CI (`.github/workflows/test.yml`) runs on every
push/PR.

These gates are the executable half of the kit's contract-fidelity promise: the
docs describe the wire shape, the gates *prove* the invariants the docs claim.

## Gate 2 — rounding-policy assertion

`gate2_rounding_policy.py`

**Invariant asserted:** on every HTTP `200` invoke response, across **all 23**
calculator URNs in the constellation, the response carries
`manifest.rounding_policy == "lodgeit-rounding-1.0"`.

**Why it matters:** `rounding_policy` is the single wire fact a partner relies on
to know which rounding discipline produced every money field in the response. If
one calculator silently served a different (or absent) policy, a partner
reconciling against their own ledger would hit an off-by-a-cent divergence with
no signal as to why. This gate turns that silent-drift failure mode into a red
CI signal.

**Run it locally:**

```bash
python3 gates/gate2_rounding_policy.py
```

**Behaviour:**

- Discovers the URN list live from `GET /v1/calculators` (does not hard-code the
  23 URNs) and asserts the count is exactly **23** — an unexpected shrink/grow is
  itself a red signal.
- POSTs a schema-valid fixture per URN and, on every `200`, asserts
  `manifest.rounding_policy`. Non-200 responses (e.g. a transient `502
  manifest_rate_table_unavailable` on an FBT path) are **not** counted as a
  violation of a *200* invariant; they are retried on 5xx and reported honestly.
- Retry-with-jitter on 5xx (same shape as `examples/python/quickstart.py`) so a
  Cloud Run cold-start or `529` backpressure blip does not flap the gate.
- **Honest about unreachability:** if every URN is unreachable, the gate reports
  `UNREACHABLE`. In CI it runs with `CLAWDOG_GATE_STRICT=1` so a real outage
  fails the gate; run locally without STRICT it exits `0` with a clear
  "could not verify" message rather than a false red.

**Environment variables:**

| Var | Default | Meaning |
|---|---|---|
| `CLAWDOG_CALC_API_URL` | production Cloud Run URL | Base URL to probe. |
| `CLAWDOG_CALC_TIMEOUT` | `30` | Per-request timeout (seconds). |
| `CLAWDOG_CALC_RETRIES` | `5` | Max retries on 5xx. |
| `CLAWDOG_GATE_STRICT` | unset | If `1`, an unreachable substrate is a failure, not a skip. CI sets this. |

**Exit codes:** `0` = invariant held on every 200 (23/23, counts unchanged) or
substrate unreachable and not strict; `1` = a 200 violated the invariant, or the
URN count changed, or strict + unreachable.

## Relationship to the CI gates

The CI workflow runs three jobs:

1. `gate-1-hermetic` — builds the examples, validates the OpenAPI snapshot,
   compiles the Python examples + this gate (no live calls).
2. `gate-2-rounding-policy` — runs this script in STRICT mode against live PROD.
3. `gate-2-live-substrate` — the pre-existing contract-drift probe (23-calculator
   discovery + version-pin + 23 MCP tools).

Gates 2-rounding-policy and 2-live-substrate are complementary: the live-substrate
gate proves the contract is byte-aligned with the pinned snapshot; the
rounding-policy gate proves the rounding invariant holds on *every* 200 the
constellation serves.

— ClawDog
