# Operational Guide

> What to know before shipping integration to a real customer. Latency expectations, retry shape, error semantics, debugging cross-checks. Zero surprises in production.

## 1. Latency expectations

The ClawDog Calculator API runs on Google Cloud Run in the `australia-southeast1` (Sydney) region.

| Condition | P50 | P95 (target) |
|---|---|---|
| Warm container, single calc invoke | ~80–150 ms | ~400 ms |
| Cold-start, single calc invoke | ~2–4 s (first request) | ~6 s |
| Discovery (`GET /v1/calculators`) | ~50–100 ms (warm) | ~250 ms |
| MCP `tools/list` | ~80–150 ms (warm) | ~400 ms |
| Depreciation audit (multi-asset batch) | scales ~linear in asset count; expect ~30 ms / asset warm | depends on batch size |

**If your customer is outside the Asia-Pacific region**, add network RTT (typically 200–400 ms US/EU round-trip). For high-volume integrations against a distant region, consider proxying through a region-close cache.

**Cold-start avoidance:** Cloud Run scales to zero by default. If you have a low-volume integration that needs sub-second worst-case, send a `GET /v1/calculators` ping once every 10 minutes during business hours to keep at least one container warm. (We may add an official "keep-warm" recommendation when the service moves to general availability; until then, this is partner-discretion.)

## 2. Backpressure + retry

### The Cloud Run upstream-529 pattern

Under sustained high-cache-hit load (e.g. a partner dashboard refreshing every 5 seconds across many concurrent users), Cloud Run can saturate the upstream concurrency cap and respond with **HTTP 529** ("Site is overloaded"). The substrate is not failing — it's signalling backpressure.

**Recommended retry shape for partner clients:**

| Status | Strategy |
|---|---|
| 503, 529 | Exponential backoff with jitter. Start at 200 ms, double per retry, cap at 10 s, full jitter (Δ ∈ [0, attempt_delay]). Max 5 retries. |
| 500, 502 | Single retry after 500 ms. If still failing, surface to the user as a substrate error and file `service-issue`. |
| 504 (timeout) | Retry once with backoff. Read-only calls (`GET /v1/calculators`, `GET /v1/rates/*`) are idempotent; invoke calls (`POST /v1/calculators/*/*`) are also idempotent (deterministic Prolog over a pure input). |
| 4xx | **Do not retry.** Fix the request. |

### Idempotency

Every invocation is **deterministic** — the same input URN + period + body produces the same output, modulo substrate version changes (which would bump `info.version` in the OpenAPI spec). You can retry any 5xx safely.

### Concurrency caps

The service currently has a per-instance concurrency cap of ~10. Cloud Run scales horizontally; partner-side throttling is rarely necessary, but if you're driving more than ~100 concurrent invokes per second, consider client-side rate limiting to avoid 529 storms.

## 3. Error semantics

See [CONTRACT.md § 4](CONTRACT.md#4-error-semantics) for status-code-by-status-code detail. Operational summary:

- **4xx** = your code has a bug. Fix the request, surface the error to your customer with a meaningful translation.
- **502** = substrate resolver gap. The substrate is up but a resource it depends on isn't loadable (engine bundle missing, rate-table not present). File a `service-issue` if persistent; this is exactly the failure shape our `production-bundle gate` catches in our CI.
- **5xx other** = retry per §2.

## 4. Why our CI probes the live substrate

The kit's CI (`.github/workflows/test.yml`) runs **two gates**:

1. **Gate 1 — hermetic example regression.** Builds the .NET example, runs the Python example against a mocked URL. Catches drift in our example code without depending on Cloud Run.
2. **Gate 2 — live substrate probe.** Runs the Python example against the **live production URL** with three-retry-with-jitter wrapping. Catches drift in the *contract* between our pinned snapshot and what production actually serves.

Gate 2 is deliberately not hermetic. A hermetic green that never touches the real backend is a green that lies — it tells you your mock is consistent with your code, not that your code is consistent with the substrate. We learned this discipline the hard way internally; it's documented in our broader engineering canon as a binding rule.

**Partner recommendation:** mirror Gate 2 in your own CI. Have at least one test in your pipeline that hits the live calc-api (with appropriate timeout + retry) and asserts the response shape matches what your integration expects. If you only run hermetic tests, you'll discover contract drift in production rather than in CI.

## 5. Versioning + deploy cadence

The substrate API version is exposed at `openapi.json#/info/version`. At this kit's pin, it is `0.1.0a0` ("0.1.0 alpha 0" — pre-production alpha).

**Upstream version-bump behaviour:**

- **Patch bumps** (`0.1.0a0` → `0.1.0a1`): backward-compatible additions (new calculator URN, new optional field, new error code). Existing partner integrations continue to work.
- **Minor bumps** (`0.1.0` → `0.2.0`): potentially backward-incompatible additions (new required field, renamed endpoint). Partners should regenerate clients + re-run CI.
- **Major bumps** (`0.x` → `1.0`): public general availability + the auth landing. Partners should plan an integration audit.

To detect a substrate-version-bump, watch:

1. This kit's releases (we refresh the snapshot pin + CHANGELOG on each substrate bump).
2. The substrate's `openapi.json#/info/version` field directly (your CI can poll it).
3. The `lodgeit-labs/clawdog-calculator-api` repo's release tags.

## 6. Debugging sheet-vs-engine divergences

If you build an integration that drives calculations against the calc-api and compares results against a "known-good" reference (a customer's existing parity sheet, an existing C# tax engine, an Excel template), and a divergence surfaces — i.e. your reference says one number, our calculator returns another — there is a canonical cross-check pattern.

**The pattern (used internally during our FBT FY2026 build-out):**

1. Identify the *exact statutory inputs* of the divergent row (every field the calculator declares in its input schema).
2. Drive those *literal* inputs through a known-good reference implementation if one is available. For Australian FBT, the LodgeiT Smart-Excel-Utility C# implementation is the LodgeiT-internal reference.
3. Compare both outputs against the statutory algebra (cite the statute-of-record from CONTRACT.md § 3).
4. The result is almost always one of:
   - **The parity sheet is stale** (it was authored against an older statutory rate or an older version of the inputs). Update the sheet.
   - **Your input mapping is incorrect** (you're passing the wrong field). Fix the integration.
   - **There is a genuine substrate bug.** File `service-issue` with the literal inputs + the divergence + the statutory algebra.

In ~80% of the divergences we've worked through internally, the parity reference was stale. In the other ~20%, the input mapping was wrong. Genuine substrate bugs are rare and we want to hear about them when they happen — that's what `service-issue` is for.

## 7. Issue filing

The `.github/ISSUE_TEMPLATE/` directory has two issue templates:

### `integration-question.md`

Use when:

- You don't understand how to use the kit.
- The docs don't cover your use-case.
- You want to confirm a behaviour before relying on it.
- You want to suggest a doc improvement.

We respond with documentation deltas, code suggestions, or examples. Triages to ClawDog (the LodgeiT Labs autonomous engineering agent); first response typically within a working day.

### `service-issue.md`

Use when:

- You believe the substrate behaves incorrectly.
- A response is missing data you expect.
- An error response is unhelpful or incorrect.
- A calculator returns a value that disagrees with the statute-of-record algebra you've computed independently.

We confirm against the substrate, route to the calc-api repo for fix, and reply with the fix-tracking-issue URL. If the issue is reproducible, expect a fix within a sprint.

**What we need in a `service-issue`:**

- The exact URN + period URN.
- The exact request body (with any PII redacted).
- The exact response received.
- The expected response + the statutory algebra + citation.
- Repro environment (your client language, OS, kit version).

The more deterministic your repro, the faster the fix.

## 8. Privacy + data handling

The calc-api does not log request bodies in a customer-identifiable form. It logs:

- Request method + path (e.g. `POST /v1/calculators/urn:sbrm:calculator:fbt:car-operating-cost/urn:sbrm:period:fy2026`).
- Response status code.
- Latency.

It does not log:

- Request bodies (your customer's tax inputs).
- Response bodies (your customer's calculated tax positions).
- Client IP addresses beyond what Cloud Run captures for routing.

**For your customer data residency:** the substrate runs in `australia-southeast1` (Sydney). All compute happens in-region. If your customer's regulatory framework requires you to know the data path, this is the answer for the substrate side; your client-side path is your responsibility.

**If you need different residency** (EU, US, etc.) for compliance, file an `integration-question` issue with the residency requirement. We may stand up regional deployments in response to documented partner demand.

## 9. What we don't do

For absolute clarity, the substrate **does not**:

- Store any customer state. Every invocation is stateless.
- Send you alerts, emails, or webhooks. You drive integration.
- Provide a customer-facing UI. We give you the engine; you build the UI.
- Speak SOAP, XML, or any non-JSON protocol.
- Run on-premise. The substrate is cloud-hosted only at this stage.

## 10. Where to next

- [CONTRACT.md](CONTRACT.md) — wire shape per route.
- [ARCHITECTURE.md](ARCHITECTURE.md) — design context.
- [`../examples/`](../examples/) — runnable code.
- [CHANGELOG.md](CHANGELOG.md) — kit version history.
