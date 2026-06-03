// ClawDog Calculator-Constellation REST API — C# .NET 8 quickstart.
//
// A complete discover-then-invoke walkthrough using HttpClient + System.Text.Json.
// No third-party dependencies beyond the .NET 8 BCL. Runs against the live
// production API by default; override with the CLAWDOG_CALC_API_URL environment
// variable to point at a different deployment.
//
// Usage:
//     dotnet run
//
// Environment variables:
//     CLAWDOG_CALC_API_URL    Base URL (default: production Cloud Run URL).
//     CLAWDOG_CALC_TIMEOUT    Per-request timeout in seconds (default: 30).
//     CLAWDOG_CALC_RETRIES    Max retries on 5xx (default: 3).

using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;

const string DEFAULT_BASE_URL =
    "https://fbt-calculator-api-8340695160.australia-southeast1.run.app";

string baseUrl =
    Environment.GetEnvironmentVariable("CLAWDOG_CALC_API_URL") ?? DEFAULT_BASE_URL;
int timeoutSeconds = int.TryParse(
    Environment.GetEnvironmentVariable("CLAWDOG_CALC_TIMEOUT"),
    out var t
) ? t : 30;
int maxRetries = int.TryParse(
    Environment.GetEnvironmentVariable("CLAWDOG_CALC_RETRIES"),
    out var r
) ? r : 3;

Console.WriteLine($"Base URL: {baseUrl}\n");

using var http = new HttpClient
{
    BaseAddress = new Uri(baseUrl),
    Timeout = TimeSpan.FromSeconds(timeoutSeconds),
};
http.DefaultRequestHeaders.Accept.Add(
    new System.Net.Http.Headers.MediaTypeWithQualityHeaderValue("application/json")
);

// ---- Step 1: Discover ----
Console.WriteLine("=== Step 1 — GET /v1/calculators ===");
var calcs = await RetryAsync(
    () => http.GetFromJsonAsync<JsonArray>("/v1/calculators"),
    maxRetries
);
Console.WriteLine($"Discovered {calcs?.Count} calculators.\n");

if (calcs is not null)
{
    foreach (var c in calcs.Take(5))
    {
        if (c is null) continue;
        Console.WriteLine($"  • {c["calc_uri"]}");
        Console.WriteLine($"      label:      {c["label"]}");
        Console.WriteLine($"      method:     {c["method"]}");
        Console.WriteLine($"      periods:    {c["supported_periods"]}");
        Console.WriteLine($"      input ref:  {c["input_schema_ref"]}");
    }
    if (calcs.Count > 5)
    {
        Console.WriteLine($"  … and {calcs.Count - 5} more.\n");
    }
    else
    {
        Console.WriteLine();
    }
}

// ---- Step 2: Invoke FBT Car-Operating-Cost ----
const string CalcUri = "urn:sbrm:calculator:fbt:car-operating-cost";
// Period URNs are domain-prefixed: urn:sbrm:period:<domain>:<period_id>.
// For FBT, the domain is "fbt"; the FY2026 period URN is therefore:
const string PeriodUri = "urn:sbrm:period:fbt:fy2026";

Console.WriteLine(
    $"=== Step 2 — POST /v1/calculators/{CalcUri}/{PeriodUri} ==="
);

// A canonical fixture for FBT Car-Operating-Cost. Note the camelCase JSON field
// names + that businessUsePercentage is on a 0–100 scale (not 0–1).
// acquisitionCost and openingDepreciatedValue are mutually exclusive — we
// choose the chained-DV walk path (acquisitionCost + acquisitionDate).
// See FBTCarOperatingCostInput schema in ../../openapi/clawdog-calculator-api.openapi.json.
var fixture = new
{
    businessUsePercentage = 65,
    formOfFinance = "owned",
    fuelRepairsServicing = 8000.00,
    registrationInsurance = 2000.00,
    employeeContribution = 0.00,
    daysHeldInFBTYear = 366,
    acquisitionCost = 45000.00,
    acquisitionDate = "2024-04-01",
};

Console.WriteLine(
    $"Request body: {JsonSerializer.Serialize(fixture, new JsonSerializerOptions { WriteIndented = true })}\n"
);

try
{
    var response = await RetryAsync(async () =>
    {
        var httpResp = await http.PostAsJsonAsync(
            $"/v1/calculators/{CalcUri}/{PeriodUri}",
            fixture
        );
        httpResp.EnsureSuccessStatusCode();
        var json = await httpResp.Content.ReadAsStringAsync();
        return JsonNode.Parse(json);
    }, maxRetries);

    Console.WriteLine("Response:");
    Console.WriteLine(
        response?.ToJsonString(new JsonSerializerOptions { WriteIndented = true })
    );

    if (response?["advisory"] is JsonNode advisory)
    {
        Console.WriteLine($"\n  Advisory block present: {advisory.ToJsonString()}");
    }
}
catch (HttpRequestException ex) when (ex.StatusCode is HttpStatusCode statusCode)
{
    Console.WriteLine($"\n⚠ POST returned HTTP {(int)statusCode}.");
    Console.WriteLine(ex.Message);
    Console.WriteLine(
        "\nThis is expected if the FBT Car-Operating-Cost input schema has "
        + "additional required fields beyond the minimal fixture above. Inspect "
        + "the OpenAPI schema FBTCarOperatingCostInput in "
        + "../../openapi/clawdog-calculator-api.openapi.json for the full field set."
    );
}

Console.WriteLine("\n=== Done ===");
return 0;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static async Task<T?> RetryAsync<T>(Func<Task<T?>> op, int maxRetries)
{
    var random = new Random();
    Exception? last = null;
    for (int attempt = 0; attempt <= maxRetries; attempt++)
    {
        try
        {
            return await op();
        }
        catch (HttpRequestException ex)
            when (ex.StatusCode is HttpStatusCode code
                  && (int)code >= 500
                  && (int)code < 600
                  && attempt < maxRetries)
        {
            var delaySeconds =
                Math.Pow(2, attempt) * 0.5
                + random.NextDouble() * Math.Pow(2, attempt) * 0.5;
            Console.Error.WriteLine(
                $"  ⚠ HTTP {(int)code}; retry {attempt + 1}/{maxRetries} in {delaySeconds:F2}s"
            );
            await Task.Delay(TimeSpan.FromSeconds(delaySeconds));
            last = ex;
        }
    }
    if (last is not null) throw last;
    return default;
}
