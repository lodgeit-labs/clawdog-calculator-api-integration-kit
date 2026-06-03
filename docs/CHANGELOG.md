# Changelog

All notable changes to this kit will be documented here. Format adapted from [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); kit semver per [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The kit's version tracks the kit's *scaffolding* shape; the pinned API version (`info.version` in the OpenAPI snapshot) tracks the upstream API and is recorded under each kit release.

## [Unreleased]

(Nothing yet.)

## [v0.1.0] — 2026-06-03

**Pinned API version:** `0.1.0a0`.

### Added

- Initial scaffold.
- `README.md` — front door + 3-minute quickstart.
- `docs/ARCHITECTURE.md` — constellation pattern, dual-surface exposure (REST + MCP), topology + boundaries, repository classification, versioning model.
- `docs/CONTRACT.md` — path-by-path wire contract, 20-calculator URN table with statute-of-record citations, error semantics, MCP-equivalence statement.
- `docs/OPERATIONAL.md` — latency expectations, backpressure + retry shape, error semantics, two-gate CI rationale, sheet-vs-engine divergence cross-check pattern, privacy + data handling.
- `docs/CHANGELOG.md` — this file.
- `examples/python/` — stdlib-only Python 3.11+ quickstart (discover → invoke FBT Car-Operating-Cost).
- `examples/dotnet/` — .NET 8 C# quickstart (discover → invoke FBT Car-Operating-Cost) using `HttpClient` + `System.Text.Json`.
- `openapi/clawdog-calculator-api.openapi.json` — pinned snapshot of the live OpenAPI spec at mint time (~45 KB, 8 paths, 20 calculator schemas).
- `openapi/README.md` — provenance + client-regeneration commands for NSwag, Kiota, openapi-python-client.
- `.github/ISSUE_TEMPLATE/integration-question.md` — partner-question issue template.
- `.github/ISSUE_TEMPLATE/service-issue.md` — substrate-bug issue template.
- `.github/workflows/test.yml` — two-gate CI (Gate 1 hermetic example regression + Gate 2 live-substrate probe with retry-with-jitter).
- `LICENSE` — Apache-2.0.
- `.gitignore` — Python + .NET + OS noise.

### Notes

- The kit is published at `lodgeit-labs/clawdog-calculator-api-integration-kit`. Public, MIT/Apache-compatible.
- The pinned API version `0.1.0a0` is pre-production alpha. Partner integrations against this version should expect upstream changes; subscribe to releases of this kit to track them.
- No wrapper SDK at this stage. Partners regenerate strongly-typed clients from the snapshot using their preferred OpenAPI toolchain. See `openapi/README.md`.

[Unreleased]: https://github.com/lodgeit-labs/clawdog-calculator-api-integration-kit/compare/v0.1.0...HEAD
[v0.1.0]: https://github.com/lodgeit-labs/clawdog-calculator-api-integration-kit/releases/tag/v0.1.0
