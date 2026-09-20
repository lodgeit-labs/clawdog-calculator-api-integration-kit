// ClawDog Calculator-Constellation REST API — C# .NET 8 module discovery + filtering.
//
// Demonstrates GET /v1/modules and GET /v1/calculators?module=<uri> (added after
// clawdog-calculator-api PR #46). Uses HttpClient + System.Text.Json.
// No third-party dependencies beyond the .NET 8 BCL.
//
// Usage:
//     dotnet run --project DiscoverModules.csproj
//
// Environment variables:
//     CLAWDOG_CALC_API_URL    Base URL (default: production Cloud Run URL).
//     CLAWDOG_CALC_TIMEOUT    Per-request timeout in seconds (default: 30).

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

Console.WriteLine($"Base URL: {baseUrl}\n");

using var http = new HttpClient
{
    BaseAddress = new Uri(baseUrl),
    Timeout = TimeSpan.FromSeconds(timeoutSeconds),
};
http.DefaultRequestHeaders.Accept.Add(
    new System.Net.Http.Headers.MediaTypeWithQualityHeaderValue("application/json")
);

// ---- Step 1: GET /v1/modules ----
Console.WriteLine("=== Step 1 — GET /v1/modules ===");
var modules = await http.GetFromJsonAsync<JsonArray>("/v1/modules");
Console.WriteLine($"Discovered {modules?.Count} modules.\n");

if (modules is not null)
{
    foreach (var m in modules)
    {
        if (m is null) continue;
        var calcsList = m["calculators"] as JsonArray;
        var firstThree = calcsList?.Take(3)
            .Select(c => c?.ToString().Split(':').Last())
            .Where(s => s is not null);
        var calcsPreview = firstThree is not null
            ? string.Join(", ", firstThree) + (calcsList?.Count > 3 ? "…" : "")
            : "";
        
        Console.WriteLine($"  • {m["module_uri"]}");
        Console.WriteLine($"      label:        {m["label"]}");
        Console.WriteLine($"      jurisdiction: {m["jurisdiction"]}");
        Console.WriteLine($"      calculators:  {calcsList?.Count} ({calcsPreview})");
        Console.WriteLine();
    }
}

// ---- Step 2: GET /v1/calculators?module=urn:sbrm:module:fbt ----
const string ModuleUri = "urn:sbrm:module:fbt";
Console.WriteLine($"=== Step 2 — GET /v1/calculators?module={ModuleUri} ===");
var fbtCalcs = await http.GetFromJsonAsync<JsonArray>(
    $"/v1/calculators?module={ModuleUri}"
);
Console.WriteLine($"FBT calculators: {fbtCalcs?.Count}\n");

if (fbtCalcs is not null)
{
    foreach (var c in fbtCalcs)
    {
        if (c is null) continue;
        var calcUri = c["calc_uri"]?.ToString();
        var selectionKind = c["selection"]?["kind"]?.ToString() ?? "?";
        Console.WriteLine($"  {calcUri} — {selectionKind}");
    }
}

Console.WriteLine("\n=== Done ===");
Console.WriteLine("\nSelecting a calculator:");
Console.WriteLine("  Pick in three steps. Module (fbt, div7a or depreciation). Benefit");
Console.WriteLine("  type is a fact — establish it from what actually happened, testing");
Console.WriteLine("  the specific FBT types in resolution order before residual. Method:");
Console.WriteLine("  where a benefit type has more than one valuation method the");
Console.WriteLine("  selection.kind is election or statutory_default — the method is the");
Console.WriteLine("  employer's choice, not yours. Compute every method in the group the");
Console.WriteLine("  records support, present them side by side with the election");
Console.WriteLine("  provision, and let the employer choose. Never pick the method for them.");

return 0;
