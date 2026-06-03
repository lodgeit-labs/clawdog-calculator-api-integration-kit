# Wire Contract

> Path-by-path documentation of the ClawDog Calculator-Constellation REST API as of pinned snapshot `v0.1.0a0` (2026-06-03 mint).
>
> Read this if you want the wire shape without parsing the OpenAPI JSON. The canonical schema is [`../openapi/clawdog-calculator-api.openapi.json`](../openapi/clawdog-calculator-api.openapi.json); this document mirrors it in prose form for human consumption.

## 1. Base URL and authentication

**Production base URL:**

```
https://fbt-calculator-api-8340695160.australia-southeast1.run.app
```

**Region:** Google Cloud `australia-southeast1` (Sydney). All paths below are relative to this base.

**Authentication:** none required at this pin (`v0.1.0a0` is pre-production-public). All endpoints are publicly accessible.

**Anticipated change:** authentication will land before the substrate moves to general availability. When it does, this kit's CHANGELOG will name the auth shape and the snapshot's `info.version` will bump.

## 2. Path-by-path documentation

### 2.1 `GET /v1/calculators`

**Purpose:** Discover the calculator URN list with per-calculator metadata.

**Request:** no body, no path params.

**Response (HTTP 200):** JSON array of `CalculatorListing` objects. Each item has:

| Field | Type | Description |
|---|---|---|
| `calc_uri` | string | URN of the calculator, e.g. `urn:sbrm:calculator:fbt:car-operating-cost`. |
| `label` | string | Human-readable name with statute-of-record citation. |
| `method` | string | Short method slug (used internally; informational for partners). |
| `supported_periods` | string[] | Array of period URNs the calculator supports. Period URNs are domain-prefixed: `urn:sbrm:period:<domain>:<period_id>` (e.g. `urn:sbrm:period:fbt:fy2026` for the FBT-domain FY2026 period). Currently each calculator supports one period URN matching its domain. |
| `input_schema_ref` | string | Pointer into the OpenAPI components schema (e.g. `#/components/schemas/FBTCarOperatingCostInput`). |
| `jurisdiction` | string | ISO-style jurisdiction tag. Currently `"AU"` for all 20 calculators. |

**Example invocation:**

```bash
curl -s https://fbt-calculator-api-8340695160.australia-southeast1.run.app/v1/calculators | python3 -m json.tool | head -30
```

### 2.2 `POST /v1/calculators/{calc_uri}/{period_uri}`

**Purpose:** Invoke a calculator for a specific period.

**Path params:**

| Name | Format |
|---|---|
| `calc_uri` | URN of the calculator (URL-encoded if your client doesn't auto-encode colons). |
| `period_uri` | URN of the period, e.g. `urn:sbrm:period:fbt:fy2026`. **Domain-prefixed** — must match one of the calculator's `supported_periods` from the discovery response. A period URN that does not match the calculator's domain is rejected with HTTP 422. |

**Request body:** JSON matching the calculator's declared input schema (see the URN table in §3 below for the schema name per calculator).

**Response (HTTP 200):** `CalculatorInvocationResponse` envelope:

| Field | Type | Description |
|---|---|---|
| `calc_uri` | string | Echo of the invoked URN. |
| `period_uri` | string | Echo of the invoked period. |
| `result` | object | Domain-specific result object. The shape varies by calculator; see the corresponding response schema in the OpenAPI spec. |
| `advisory` | `AdvisoryBlock` \| null | Optional compliance hints (e.g. "this method requires a 12-week register; check that the register start date is at least 12 weeks before period end"). |

**Errors:**

- **4xx** — your request is malformed (schema validation, unknown URN, period not supported).
- **5xx** — substrate-side failure. **502** specifically indicates a resolver-shape mismatch (e.g. the FBT engine bundle did not load); this is structured and not a bare crash, so your retry logic can distinguish it from network noise. See [OPERATIONAL.md](OPERATIONAL.md) § Error semantics.

### 2.3 `POST /v1/calculators/depreciation/audit/{period_uri}`

**Purpose:** Specialised invoke for the depreciation-audit calculator. Distinct from §2.2 because the depreciation-audit takes a *list* of assets in a single call rather than one asset per call.

**Path param:** `period_uri` (URN of the period).

**Request body:** `DepreciationAuditInput`:

```json
{
  "assets": [
    {
      "asset_uri": "...",
      "cost": 0.0,
      "acquisition_date": "YYYY-MM-DD",
      "method": "prime_cost" | "diminishing_value",
      "...": "..."
    }
  ]
}
```

(Full schema at `#/components/schemas/DepreciationAuditInput` + `DepreciationAuditAssetInput` in the snapshot.)

**Response:** envelope carrying per-asset depreciation entries + an aggregate summary.

### 2.4 `GET /v1/rates/{period_uri}`

**Purpose:** List the statutory rate-table for a period — every indexed threshold, fraction, factor, and base rate used by any calculator in the constellation for that period.

**Use case:** partners who want to drive a per-period UI without hitting the rate-lookup-via-calc-invoke pattern.

**Response:** JSON object mapping rate IDs to values. Rate IDs are stable URNs in the SBRM vocabulary.

### 2.5 `GET /v1/rates/{period_uri}/{rate_id}`

**Purpose:** Fetch one specific rate value.

**Use case:** when you know exactly which rate you need (e.g. the FBT gross-up factor for FY2026) and don't want to fetch the whole table.

### 2.6 `POST /mcp`

**Purpose:** JSON-RPC 2.0 surface for MCP-aware clients (Claude Desktop, OpenAI Custom GPT remote MCP servers, Office add-in MCP hosts, etc.).

**Methods supported:**

- `initialize` — handshake.
- `tools/list` — returns 20 tools, each corresponding to a calculator in the constellation. Each tool's `inputSchema` mirrors the calculator's REST input schema.
- `tools/call` — invokes a tool. The tool name encodes the calc URN; the arguments encode the calc input.

**Wire shape:** standard MCP/JSON-RPC 2.0 envelope. The result of `tools/call` matches the REST `CalculatorInvocationResponse` byte-for-byte.

**Example (curl):**

```bash
curl -s -X POST \
  https://fbt-calculator-api-8340695160.australia-southeast1.run.app/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | python3 -m json.tool | head -40
```

### 2.7 `GET /healthz`, `GET /livez`

**Purpose:** internal health probes declared in the OpenAPI spec.

**⚠️ Caveat:** these routes are **not currently exposed at the Cloud Run frontend** (they return HTTP 404 from public probes). They exist in the framework's route table but the Cloud Run layer doesn't forward to them.

**For your liveness/readiness checks**, probe `GET /v1/calculators` instead — it returns 200 + a stable JSON payload if the substrate is healthy.

---

## 3. The 20 calculator URNs (statute-of-record citations)

This is the canonical list at pin time. Order matches the live `GET /v1/calculators` response order.

| # | URN | Statute-of-record | Input schema |
|---|---|---|---|
| 1 | `urn:sbrm:calculator:fbt:car-operating-cost` | FBTAA Division 2 ss.10–10A (operating-cost method) | `FBTCarOperatingCostInput` |
| 2 | `urn:sbrm:calculator:fbt:loan` | FBTAA Division 4 ss.16–19 (Type 2 only) | `FBTLoanInput` |
| 3 | `urn:sbrm:calculator:fbt:debt-waiver` | FBTAA s.16 (Type 2 only) | `FBTDebtWaiverInput` |
| 4 | `urn:sbrm:calculator:fbt:expense-payment` | FBTAA Division 5 ss.20–24 (standard) | `FBTExpensePaymentInput` |
| 5 | `urn:sbrm:calculator:fbt:expense-payment-in-house` | FBTAA s.62 (in-house cap) | `FBTExpensePaymentInHouseInput` |
| 6 | `urn:sbrm:calculator:fbt:property` | FBTAA Division 7 ss.40–44 (standard) | `FBTPropertyInput` |
| 7 | `urn:sbrm:calculator:fbt:property-in-house` | FBTAA s.62 (in-house cap) | `FBTPropertyInHouseInput` |
| 8 | `urn:sbrm:calculator:fbt:residual` | FBTAA Division 12 ss.45–52 (standard) | `FBTResidualInput` |
| 9 | `urn:sbrm:calculator:fbt:residual-in-house` | FBTAA s.62 (in-house cap) | `FBTResidualInHouseInput` |
| 10 | `urn:sbrm:calculator:fbt:housing` | FBTAA s.26 (non-remote housing) | `FBTHousingInput` |
| 11 | `urn:sbrm:calculator:fbt:lafha` | FBTAA s.31 (Type 2 only) | `FBTLafhaInput` |
| 12 | `urn:sbrm:calculator:fbt:board` | FBTAA s.36 | `FBTBoardInput` |
| 13 | `urn:sbrm:calculator:fbt:tebe` | FBTAA s.39 (Tax-Exempt Body Entertainment) | `FBTTebeInput` |
| 14 | `urn:sbrm:calculator:fbt:car-parking-actual` | FBTAA Division 10A (actual method, simple-sum) | `FBTCarParkingActualInput` |
| 15 | `urn:sbrm:calculator:fbt:car-parking-statutory-228` | FBTAA s.39FA (228-Day Statutory Formula) | `FBTCarParkingStatutory228Input` |
| 16 | `urn:sbrm:calculator:fbt:car-parking-register-12wk` | FBTAA s.39GB (12-Week Register) | `FBTCarParkingRegister12WkInput` |
| 17 | `urn:sbrm:calculator:fbt:meal-entertainment-50-50` | FBTAA s.37CA (Division 9A; 50/50 split) | `FBTMealEntertainment5050Input` |
| 18 | `urn:sbrm:calculator:fbt:meal-entertainment-register-12wk` | FBTAA s.37CB (Division 9A; 12-Week Register) | `FBTMealEntertainmentRegister12WkInput` |
| 19 | `urn:sbrm:calculator:fbt:car-statutory-formula` | FBTAA s.9 (Statutory Formula; rate-table-fed) | `FBTCarStatutoryFormulaInput` |
| 20 | `urn:sbrm:calculator:depreciation:audit` | ITAA97 Div 40 (Prime Cost / Diminishing Value) | `DepreciationAuditInput` |

All 20 declare `jurisdiction: AU` at this pin. Period URNs are **domain-prefixed**: the 19 FBT calculators support `urn:sbrm:period:fbt:fy2026`; the depreciation-audit calculator supports `urn:sbrm:period:depreciation:fy2026`. The exact `supported_periods` value per calculator is in the `GET /v1/calculators` discovery response — consume that, do not hard-code the period URN against your local assumption.

---

## 4. Error semantics

### 4xx — your request

| Status | Meaning | Action |
|---|---|---|
| 400 | Request body fails schema validation | Re-check against the input schema; fix the request. |
| 404 | URN unknown OR period not supported by this URN | Cross-check against `GET /v1/calculators`. |
| 422 | Request semantically invalid (e.g. dates outside the period) | Read the structured error detail. |

All 4xx responses carry a `detail` field describing the violation.

### 5xx — substrate-side

| Status | Meaning | Action |
|---|---|---|
| 500 | Unhandled exception in the substrate | Retry with jitter; if persistent, file `service-issue`. |
| 502 | Resolver-shape mismatch (engine bundle did not load, rate-table missing) | This is a structured error, not a crash. The `detail` field names the resolver gap. File `service-issue` if persistent. |
| 503 | Upstream unavailable (Cloud Run cold-start, engine not ready) | Retry with exponential backoff per OPERATIONAL.md. |
| 529 | Upstream overloaded (Cloud Run concurrency-cap, cache-hit dashboard storm) | Retry with backoff + jitter. See OPERATIONAL.md § Backpressure. |

### MCP errors

JSON-RPC 2.0 errors carry an `error` object with `code` + `message` + optional `data`. The standard JSON-RPC error codes (-32700 parse, -32600 invalid request, -32601 method not found, -32602 invalid params, -32603 internal) all apply. Calculator-specific errors are returned via `code: -32000` (server error) with the underlying detail in `data`.

---

## 5. MCP equivalence

For every REST invocation, there is an exact MCP equivalent:

| REST | MCP |
|---|---|
| `GET /v1/calculators` | `tools/list` |
| `POST /v1/calculators/{calc_uri}/{period_uri}` body=X | `tools/call` with `name: <encoded-URN>`, `arguments: X` |
| `GET /v1/rates/{period_uri}` | (not in tool surface at v0.1.0a0; use REST) |
| `GET /v1/rates/{period_uri}/{rate_id}` | (not in tool surface at v0.1.0a0; use REST) |

For matched REST + MCP calls, the result payload is **byte-identical** modulo the JSON-RPC envelope. You can drive an integration off either surface, or both concurrently, without risk of result divergence.

---

## 6. Where to next

- [OPERATIONAL.md](OPERATIONAL.md) — latency, retry, debugging cross-checks.
- [`../openapi/clawdog-calculator-api.openapi.json`](../openapi/clawdog-calculator-api.openapi.json) — canonical schema.
- [`../examples/`](../examples/) — runnable code.
