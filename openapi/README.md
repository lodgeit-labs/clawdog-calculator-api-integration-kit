# OpenAPI Snapshot

This directory holds a **pinned snapshot** of the live ClawDog Calculator-Constellation REST API OpenAPI spec. Partner integrations generate strongly-typed clients against this snapshot, not against the live URL directly.

## Why pin

Pinning the spec rather than fetching it at integration-build time gives you:

- **Reproducibility:** your build produces the same client every time, regardless of upstream deploys.
- **Drift detection:** when we refresh this snapshot, the diff against your last-built client is the spec change. If your CI rebuilds the client on every pin update, you see breaking changes at PR-review time, not at deploy time.
- **Offline build:** your build doesn't need network access to the production API at compile time.

## Snapshot provenance

| Field | Value |
|---|---|
| Source URL | `https://fbt-calculator-api-8340695160.australia-southeast1.run.app/openapi.json` |
| Pinned at | 2026-06-03 |
| Pinned `info.version` | `0.1.0a0` |
| File size | ~45 KB |
| Paths | 8 |
| Calculator URNs | 20 |
| Schemas | ~30 components |

## Refreshing the snapshot

The published snapshot is a **sanitised** view of the live API's `openapi.json`. Internal forensic references (development phase numbers, mutation IDs, internal thread numbers, internal file paths) are stripped, and the schema/path descriptions are replaced with partner-facing copy that preserves all statute citations and field-usage guidance.

The structural shape (paths, methods, parameters, types, required fields, constraints, enums) is preserved byte-for-byte across the live spec and the sanitised snapshot. Client generation against either produces semantically identical clients.

To regenerate the snapshot:

```bash
# 1. Fetch the raw live spec
curl -s https://fbt-calculator-api-8340695160.australia-southeast1.run.app/openapi.json \
  > openapi/clawdog-calculator-api.raw.json

# 2. Sanitise into the published snapshot
python3 openapi/sanitise.py

# 3. Discard the raw spec (not committed to the kit)
rm openapi/clawdog-calculator-api.raw.json
```

The `sanitise.py` script applies (a) a regex pass that strips known internal markers + (b) a hand-curated override table that replaces schema + path descriptions with partner-facing copy. Both are visible in the script for transparency.

If the live spec's structural shape has changed (new path, new schema, removed field), bump:

- `docs/CHANGELOG.md` (add an entry under a new kit version).
- `README.md` (the "Pinned API version" line).
- This file (the "Pinned `info.version`" row above).
- `sanitise.py` (extend the override table to cover new schemas).
- The examples (if a removed field broke them).
- The CI workflow (if a new structural constraint needs probing).

## Generating strongly-typed clients

The OpenAPI ecosystem has mature generators in every major language. Pick whichever fits your stack.

### .NET — NSwag

```bash
dotnet tool install -g NSwag.ConsoleCore
nswag openapi2csclient \
  /input:openapi/clawdog-calculator-api.openapi.json \
  /classname:ClawDogCalculatorApiClient \
  /namespace:LodgeitLabs.ClawDog.CalculatorApi \
  /output:generated/dotnet/ClawDogCalculatorApiClient.cs
```

### .NET — Kiota (Microsoft)

```bash
kiota generate \
  --openapi openapi/clawdog-calculator-api.openapi.json \
  --language csharp \
  --class-name ClawDogCalculatorApiClient \
  --namespace-name LodgeitLabs.ClawDog.CalculatorApi \
  --output ./generated/dotnet-kiota
```

### Python — openapi-python-client

```bash
pip install openapi-python-client
openapi-python-client generate \
  --path openapi/clawdog-calculator-api.openapi.json \
  --config <(echo "package_name_override: clawdog_calculator_api_client")
```

### TypeScript — openapi-typescript

```bash
npx openapi-typescript openapi/clawdog-calculator-api.openapi.json \
  -o generated/typescript/clawdog-calculator-api.d.ts
```

### Java — openapi-generator

```bash
openapi-generator-cli generate \
  -i openapi/clawdog-calculator-api.openapi.json \
  -g java \
  -o generated/java \
  --api-package org.lodgeitlabs.clawdog.calculatorapi.api \
  --model-package org.lodgeitlabs.clawdog.calculatorapi.model
```

### Other languages

See [https://openapi-generator.tech/docs/generators](https://openapi-generator.tech/docs/generators) for the full list of supported languages.

## What we don't vendor

The `generated/` directory is `.gitignore`d. We do not vendor generated clients into this kit because:

1. They go stale relative to the snapshot if a developer regenerates and commits without bumping the kit version.
2. They balloon the repo size for code that's deterministically reproducible from the pinned snapshot.
3. They couple this kit to specific generator versions, which evolve independently.

**Your integration repo** is welcome to vendor generated clients (it's your code, your build); we just don't vendor them here.

## Sanitiser provenance

The `sanitise.py` script in this directory is the canonical transform from the raw live spec into the published partner snapshot. It does two passes:

1. **Regex sanitiser** — strips known internal-marker patterns (thread numbers, mutation IDs, phase numbers, internal file paths, internal Lesson/Standing-Rule references, internal verification dates) from description fields.
2. **Hand-curated overrides** — replaces schema + path descriptions with partner-facing copy that preserves all statute citations and field-usage guidance. The override table is the source of truth for the descriptions in the published snapshot.

A self-check pass at the end of the script verifies that no known-leak pattern survives in the output; the script fails (exit 1) if any do. This is the same discipline applied by the kit's CI.

## Validating the snapshot

The snapshot is a standard OpenAPI 3.x JSON document. You can validate it with:

```bash
# Using swagger-cli (npm)
npx @apidevtools/swagger-cli validate openapi/clawdog-calculator-api.openapi.json

# Using openapi-spec-validator (Python)
pip install openapi-spec-validator
openapi-spec-validator openapi/clawdog-calculator-api.openapi.json
```

The kit's CI runs `swagger-cli validate` on every push.
