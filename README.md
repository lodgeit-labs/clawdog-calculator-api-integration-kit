# ClawDog Calculator-API Integration Kit

> Integration kit for the [ClawDog Calculator-Constellation REST API][api] — discover and invoke 20 SBRM-vocabulary calculators (Australian Fringe Benefits Tax, Depreciation) from any HTTP/JSON-RPC client.

[api]: https://fbt-calculator-api-8340695160.australia-southeast1.run.app/openapi.json

**Kit version:** `v0.1.0` (initial scaffold).
**Pinned API version:** `0.1.0a0`.
**License:** Apache-2.0.

---

## Who this kit is for

You are a partner developer integrating the ClawDog Calculator Constellation into your own product — a finance team's internal tool, a tax-professional add-in for Excel, a payroll system, a tax-engine wrapper, an audit dashboard. You have an HTTP client (any language) and you want deterministic, statute-grounded calculations for Australian FBT and depreciation without rebuilding the tax engines yourself.

This kit gives you:

1. **A pinned snapshot of the live OpenAPI spec** so you can generate strongly-typed clients (NSwag, Kiota, openapi-python-client, etc.) against a known-good contract.
2. **Two runnable examples** (C# .NET, Python) that walk the full discover → invoke loop end-to-end against the live production API.
3. **Wire-level + operational + architectural docs** so you don't have to reverse-engineer the contract from JSON Schema.
4. **A two-gate CI workflow** that proves both (a) the examples build cleanly and (b) the contract is still byte-aligned with what production actually serves. Use it as a template for your own integration's CI.
5. **A direct line back to us** via the issue templates — `integration-question` for "how do I…" and `service-issue` for "I think the substrate is wrong."

This kit does NOT vendor generated clients (they would go stale; the snapshot is the source of truth). It also does NOT give you a wrapper SDK in any language — partner products vary too widely in their HTTP-stack preferences, dependency-injection patterns, and deployment shapes for an opinionated SDK to be useful at this stage. **The kit is documentation + executable proof; the integration code is yours.**

---

## What "the Calculator Constellation" is

LodgeiT Labs builds an open-source operating system for financial truth — a polymorphous graph protocol for many epistemic hyperplanes (accounting, tax, law). The wedge is **accounting + tax** because that's where proof is *resolvable* — the algebra of double-entry, the determinism of statutory tax law, and the closure of SBRM taxonomy admit formal reasoning without probabilistic slippage.

The Calculator Constellation is the first public-facing surface of that operating system. Each **calculator** is a deterministic Prolog reasoner bound to a specific statutory citation (e.g. `FBTAA s.39FA` for Car Parking 228-day statutory formula). They are exposed via two parallel surfaces over the same wire contract:

- **REST** at `/v1/calculators/{calc_uri}/{period_uri}` — the path partners reach for from any HTTP client.
- **MCP (Model Context Protocol)** at `/mcp` — the JSON-RPC 2.0 surface that LLM-driven agents (Claude Desktop, Office add-in MCP hosts, ChatGPT custom GPTs, etc.) reach for as a tools registry.

Both surfaces speak the same input/output schema. Pick whichever fits your stack.

There are 20 calculators in the constellation today. See [`docs/CONTRACT.md`](docs/CONTRACT.md) for the full URN list with statute-of-record citations.

---

## Quick start (3 minutes, 3 commands)

### 1. List the calculators

```bash
curl -s https://fbt-calculator-api-8340695160.australia-southeast1.run.app/v1/calculators | head -200
```

You should see a JSON array of 20 calculator descriptors. Each has a `calc_uri` (the URN), a `label`, a `method` slug, a list of `supported_periods` (period URNs are **domain-prefixed**, e.g. `urn:sbrm:period:fbt:fy2026`), an `input_schema_ref` pointer into the OpenAPI spec, and a `jurisdiction` tag.

### 2. Inspect the contract

```bash
curl -s https://fbt-calculator-api-8340695160.australia-southeast1.run.app/openapi.json > /tmp/openapi.json
# Compare against our pinned snapshot:
diff openapi/clawdog-calculator-api.openapi.json /tmp/openapi.json
```

If the diff is empty, you're integrating against a substrate that matches our snapshot exactly. If it isn't, see [`openapi/README.md`](openapi/README.md) for the regeneration discipline.

### 3. Run a real calculation

```bash
cd examples/python
python3 quickstart.py
```

Output: a discover-then-invoke walkthrough that calls FBT Car-Operating-Cost on a canonical fixture and prints the taxable value + advisory block. ~30 lines of stdlib-only Python, no dependencies.

The .NET equivalent (`examples/dotnet/`) does the same with `HttpClient` + `System.Text.Json` against .NET 8.

---

## What's in the box

```
clawdog-calculator-api-integration-kit/
├── README.md                              ← you are here
├── LICENSE                                ← Apache-2.0
├── docs/
│   ├── ARCHITECTURE.md                    ← why the kit exists; topology + boundaries
│   ├── CONTRACT.md                        ← wire contract per route, URN list, error semantics
│   ├── OPERATIONAL.md                     ← latency, retry, error handling, debugging cross-checks
│   └── CHANGELOG.md                       ← kit version history
├── examples/
│   ├── dotnet/                            ← C# .NET 8 quickstart
│   └── python/                            ← Python 3.11+ quickstart (stdlib-only)
├── openapi/
│   ├── README.md                          ← provenance + client-regeneration commands
│   └── clawdog-calculator-api.openapi.json ← pinned snapshot (~45 KB; API v0.1.0a0)
└── .github/
    ├── ISSUE_TEMPLATE/
    │   ├── integration-question.md        ← "How do I…"
    │   └── service-issue.md               ← "I think the API behaves wrong"
    └── workflows/
        └── test.yml                       ← two-gate CI
```

---

## Versioning + compatibility

The kit's semver tracks two things independently:

- **Kit version** (`v0.1.0`, this release) — increments when we change the *scaffolding* (docs, examples, CI, issue templates). Strict semver.
- **Pinned API version** (`v0.1.0a0`) — the live `openapi.json` `info.version` at the time of pin. Increments independently as the upstream API evolves.

The kit's CI Gate 2 (live-substrate probe) is what gives you a red signal if the upstream contract has drifted away from the pinned snapshot in a way that breaks our examples. Subscribe to the repo's releases to track both axes.

**Compatibility statement:** any kit version compatible with API `v0.1.0a0` will continue working as long as the upstream maintains backward-compatible additive changes. Breaking changes are signalled by a kit major-version bump + a CHANGELOG entry naming the upstream-version delta.

---

## License + contributing

**License:** Apache-2.0. See [LICENSE](LICENSE).

**Contributing:** issues and PRs welcome on this repo. Two paths:

- **Integration question** ("how do I…"): file via [`integration-question`](.github/ISSUE_TEMPLATE/integration-question.md) template. We respond with documentation deltas if your question reveals a gap.
- **Service issue** ("I think the API behaves wrong"): file via [`service-issue`](.github/ISSUE_TEMPLATE/service-issue.md) template. We confirm against the substrate and route to the calc-api repo for fix.
- **PRs:** all PRs reviewed by ClawDog (the autonomous engineering agent at LodgeiT Labs); merge requires sign-off from a LodgeiT Labs human maintainer. We don't merge unilaterally.

**Code of conduct:** be specific, be terse, be deterministic. Show the wire trace, name the URN, cite the statute.

---

## Where to go next

| You want to… | Read |
|---|---|
| understand *why* the constellation is shaped this way | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| know the exact request/response shape per route | [`docs/CONTRACT.md`](docs/CONTRACT.md) |
| ship to production safely | [`docs/OPERATIONAL.md`](docs/OPERATIONAL.md) |
| run code right now | [`examples/python/`](examples/python/) or [`examples/dotnet/`](examples/dotnet/) |
| generate a strongly-typed client | [`openapi/README.md`](openapi/README.md) |
| see what changed between kit versions | [`docs/CHANGELOG.md`](docs/CHANGELOG.md) |

---

## About LodgeiT Labs

[LodgeiT Labs](https://lodgeit.org) is an open-source foundation building deterministic tax and accounting infrastructure. The Calculator Constellation is part of a broader vehicle called Global Notes — a polymorphous graph protocol for cryptographically-anchored, statute-grounded financial truth.

The Constellation is the first public-facing surface; this kit is the first public-facing onboarding artefact. Our intent is to **open up our reasoners to the world** — every calculator in the Constellation is built by LodgeiT Labs as deterministic Prolog with a statute-of-record citation, and every consumer of this kit gets the same calculation result the LodgeiT product team gets internally.

If you're integrating against the Constellation, you're now part of the perimeter. Welcome.
