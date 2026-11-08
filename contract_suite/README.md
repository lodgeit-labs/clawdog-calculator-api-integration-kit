# Constellation contract suite

A black-box suite that **discovers** every calculator on the live gateway and
checks each one against the published contract (`llms.txt`, `rounding.html`,
`publish.html`). It runs in GitHub Actions on every PR, daily, and on manual
trigger (`workflow_dispatch`). It makes live calls, so it runs in Actions, not
from a developer host that cannot reach the gateway.

## What it does

1. **Discovery (no hard-coded list).** `GET /v1/calculators` + `GET /openapi.json`,
   matching each calculator to its input schema through the schema's
   `x-calc-uri` extension. Fails if the count disagrees with `/v1/modules`, or if
   a discovered calculator has no fixture. A new module must bring its fixture.

2. **Fixtures.**
   - `fixtures/valid_inputs.json` — one minimal valid body per calculator URN
     (all 23). The anchored calculators use the verified bodies from
     `ClawDog_Share/live-examples-2026-11-08/LIVE_EXAMPLES.md`.
   - `fixtures/refusals.json` — one documented refusal per module where one
     exists (FBT out-of-cohort, Div 7A both names, depreciation pool, HP weekly),
     using the bodies Argon used (`argon_constellation_report_2026-11-08.md` §3).

3. **Probes per calculator:** (a) valid call (200; money/rates are strings — no
   non-integer JSON numbers; `manifest.rate_table_uris[]` each has `uri` +
   `content_hash` + `hash_algorithm`; `manifest.rounding_policy` present;
   `advisory.disclaimer` present); (b) byte-identical repeat; (c) half-cent on the
   first `x-money` field (keeping its JSON type) → 422 `money_not_cent_quantised`
   with `loc = ["body", …, <field>]`; (d) missing first required field (other than
   `period_uri`) → 422 naming it, or `N/A` when the schema has no required fields
   (FBT board); (e) unknown period `fy1999` → 404; (f) documented refusal → 400
   with `refusal_class` + `refusal_payload` + `engine` (= module) + `message`;
   (g) every `x-mutually-exclusive` pair → 422 `mutually_exclusive_inputs`;
   (h) unknown field where `additionalProperties: false` → 422 naming it;
   (i) MCP: `initialize` succeeds, `tools/list` count == calculator count, each
   valid fixture's `tools/call` `structuredContent` equals the REST body, and the
   half-cent case gives `isError: true`.

4. **Independent anchors** (assertions from hand arithmetic / the ATO, never the
   engine): FBT statutory 8603.71; Div 7A FY2025 13801.18, FY2026 13615.68;
   depreciation `/range` range_dep 2000.00 / opening 8000.00 / closing 6000.00;
   HP Scania totals.interest 32531.91, rounding_residual 0.05.

## Etiquette

One request at a time, at least 0.3 s apart; a `User-Agent` naming the kit; base
URL from `CLAWDOG_CALC_API_URL` (default public gateway); no credentials.

## Output

A Markdown summary (`--summary`, default `contract-summary.md`) is written and
appended to `$GITHUB_STEP_SUMMARY`: one row per calculator, columns (a)–(i),
`✓`/`✗`/`N/A`, plus a failures section carrying the request and response for each
`✗`. The job exits non-zero on any `✗`.

## Run it

```bash
# against the default public gateway
python3 contract_suite/contract_suite.py --summary contract-summary.md

# against another deployment
CLAWDOG_CALC_API_URL=https://… python3 contract_suite/contract_suite.py
```

The live `/openapi.json` carries `x-calc-uri`, `x-money` and
`x-mutually-exclusive`; the committed OpenAPI snapshot (`openapi/`) strips them,
so the suite reads the **live** spec, not the snapshot.

— ClawDog
