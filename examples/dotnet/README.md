# .NET quickstart

Runnable example for the ClawDog Calculator-Constellation REST API using .NET 8 and the BCL.

## Requirements

- .NET 8 SDK (or later). Install per [https://dotnet.microsoft.com/download](https://dotnet.microsoft.com/download).
- No third-party NuGet dependencies — `HttpClient` + `System.Text.Json` (both in the BCL).

## Run

```bash
dotnet run
```

This builds and executes [`Program.cs`](Program.cs), which:

1. `GET /v1/calculators` and prints the first 5 calculator URNs with their metadata.
2. `POST /v1/calculators/urn:sbrm:calculator:fbt:car-operating-cost/urn:sbrm:period:fbt:fy2026` with a canonical fixture for the FBT Car Operating-Cost method.
3. Prints the full response payload (taxable value, statutory algebra trace, manifest of rate-table sources consumed, advisory block).

Expected runtime: ~2–5 seconds (first run includes JIT + build; subsequent `dotnet run` invocations are warmer).

## Customising

| Environment variable | Default | Purpose |
|---|---|---|
| `CLAWDOG_CALC_API_URL` | production Cloud Run URL | Base URL. Override to point at a mock (CI Gate 1) or a different deployment. |
| `CLAWDOG_CALC_TIMEOUT` | `30` | Per-request timeout in seconds. |
| `CLAWDOG_CALC_RETRIES` | `3` | Max retries on 5xx with exponential backoff + jitter. |

## What the example demonstrates

The .NET example mirrors the Python example in [`../python/`](../python/) — same fixture, same URNs, same retry shape. Pick whichever stack matches your integration target.

- **Plain `HttpClient` + `System.Text.Json`.** No third-party libraries; no generated client. If you want a strongly-typed client, see [`../../openapi/README.md`](../../openapi/README.md) for NSwag and Kiota commands.
- **Anonymous-type request bodies.** The `fixture` object is an anonymous type that `System.Text.Json` serialises with the camelCase field names the substrate expects. In production code, you would use generated DTOs from the OpenAPI snapshot.
- **Retry-with-jitter on 5xx.** The `RetryAsync` helper at the bottom of `Program.cs` is a self-contained pattern you can lift into your own integration (or replace with [Polly](https://github.com/App-vNext/Polly) for richer policies).
- **`JsonNode` for the response.** The example uses dynamic JSON traversal for readability; for production, use generated typed DTOs or `JsonSerializer.Deserialize<YourType>(json)`.

## Schema notes for the FBT Car-Operating-Cost fixture

| Field | Why |
|---|---|
| `businessUsePercentage: 65` | Required. 0–100 scale (not 0–1). Clamped server-side. |
| `formOfFinance: "owned"` | Required. One of `owned`, `hire_purchase`, `leased`, `unspecified`. |
| `fuelRepairsServicing`, `registrationInsurance` | Operating-cost components. |
| `employeeContribution: 0.00` | Post-tax employee contribution; reduces taxable value. |
| `daysHeldInFBTYear: 366` | Pro-rates the calculation when the car wasn't held the full year. |
| `acquisitionCost: 45000.00` + `acquisitionDate: "2024-04-01"` | Drives the deemed-depreciation chained-DV walk. Mutually exclusive with `openingDepreciatedValue` (legacy single-year primitive). |

## Next steps

After running this example successfully:

- Read [`../../docs/CONTRACT.md`](../../docs/CONTRACT.md) for the full URN list and per-route schemas.
- Read [`../../docs/OPERATIONAL.md`](../../docs/OPERATIONAL.md) for production retry and backpressure shape.
- See [`../python/`](../python/) for the Python equivalent.
- Generate a strongly-typed client per [`../../openapi/README.md`](../../openapi/README.md).
