#!/usr/bin/env python3
"""Sanitise the live OpenAPI spec for partner-facing kit publication.

The ClawDog Calculator-Constellation REST API's live `openapi.json` is generated
by FastAPI directly from the implementation. The implementation's docstrings
carry development-internal references — phase numbers, thread numbers,
mutation IDs, internal file paths, source-of-record links to internal canon.
Those references are useful to the LodgeiT Labs engineering team but noisy to
partner developers consuming the spec to generate clients.

This script transforms the raw live spec into the partner-facing snapshot by:

1. Applying a hand-curated override table that replaces schema + path
   description fields with partner-facing copy. The overrides preserve all
   statute citations and field-usage guidance.
2. Running a regex pass that strips known internal-marker patterns from any
   description that the override table didn't cover.
3. Self-checking the output for residual leaks; exits non-zero if any of the
   known leak patterns survive.

The structural shape (paths, methods, parameters, types, required fields,
constraints, enums) is preserved byte-for-byte. Client generation against the
sanitised snapshot produces a semantically identical client to one generated
against the live spec.

This script is shipped in the kit so partners can see exactly how the snapshot
is produced — the transform is auditable. The patterns it strips are
referenced literally here because that is what makes detection work; their
presence in this script does not propagate them into the published snapshot.
"""
import json
import re
import sys

import argparse
from pathlib import Path

DEFAULT_INPUT = Path(__file__).parent / "clawdog-calculator-api.raw.json"
DEFAULT_OUTPUT = Path(__file__).parent / "clawdog-calculator-api.openapi.json"

# Patterns to strip from description fields (replace with "" or sanitised text)
# Each tuple: (regex pattern, replacement). Applied in order.
SANITISERS = [
    # GitHub Brain repo URLs in info.description — strip the URL but keep canon
    # reference names.
    (
        r"\[CLAWDOG/109\]\(https://github\.com/futureWA/clawdog-brain/[^\)]+\)",
        "the Calculator-Constellation architectural canon (CLAWDOG/109)",
    ),
    (
        r"\[CLAWDOG/110\]\(https://github\.com/futureWA/clawdog-brain/[^\)]+\)",
        "the Outsource-Boundary canon (CLAWDOG/110)",
    ),
    (
        r"https://github\.com/futureWA/clawdog-brain/[^\s\)\]]+",
        "[LodgeiT Labs internal canon]",
    ),
    # Brain phase + mc nomenclature (drop entirely, the spec doesn't need
    # internal phase references at all)
    (r"\(\s*Phase 3[abc](?:\.\d+)?(?:\.[A-Z])?\s*(?:Cut [A-Z])?\)", ""),
    (r"\bPhase 3[abc](?:\.\d+)?(?:\.[A-Z])?\s*(?:Cut [A-Z])?\s*[—\-]\s*", ""),
    (r"\bPhase 3[abc](?:\.\d+)?(?:\.[A-Z])?\s*(?:Cut [A-Z])?", ""),
    (r"\(\s*Phase 2[a-z]\s*\)", ""),
    (r"\bPhase 2[a-z]\s*[—\-]\s*", ""),
    (r"\bPhase 2[a-z]\s+", ""),
    (r"\bmut-\d{4}-\d{2}-\d{2}-mc\d+\b", ""),
    # OT thread numbers (banked forward concerns) — strip entire parenthetical
    # (Lesson #N strict-validation), (OT #N), (OT #N Rung N mc07)
    (r"\s*\([^()]*\bOT #\d+[^()]*\)", ""),
    (r"\s*\([^()]*\bLesson #\d+[^()]*\)", ""),
    (r"\s*per OT #\d+[^.]*\.", "."),
    (r"\bOT #\d+\b", ""),
    (r"\bLesson #\d+\b", ""),
    # mut IDs banked into descriptions
    (r"\bmut-\d{4}-\d{2}-\d{2}-[a-z0-9-]+\b", ""),
    # NOTE blocks with internal date forensics
    (r"NOTE \(mut-[^)]*\):\s*", "NOTE: "),
    # Internal file/predicate paths
    (r"`api/routes/calculators\.py`", "the API route registry"),
    (r"`_CALC_INPUT_MODEL_REST`", "the per-URN input-model registry"),
    (r"FBT_Engine\.pl L\d+", "the FBT engine source"),
    (r"`app/server/depreciation_server\.pl::handle_audit`", "the depreciation audit handler"),
    # Internal verification dates
    (r"verified\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2} UTC", "verified"),
    (r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?\s*UTC", ""),
    # Internal cross-references
    (r"per (?:Andrew|ClawDog)\s+\(\d{4}-\d{2}-\d{2}[^)]*\)", "per design"),
    (r"per (?:Andrew|ClawDog)\b", "per design"),
    # Brain canon node references (CLAWDOG/NNN) — keep generic "architectural canon"
    (r"CLAWDOG/\d{3}(?:\.\d+)?(?:\s*§[\d.]+)?", "the architectural canon"),
    # Strict-validation parenthetical refs
    (r"strict-validation\s*\(\s*the architectural canon\s*\)", "strict-validation"),
    # SBRM_RATE_TABLE internal paths
    (
        r"\(SBRM_RATE_TABLE/[^)]+\)",
        "(see the period-scoped rate-table fact-nodes for the variance threshold)",
    ),
    # Standing Rule numbers — strip the "(Standing Rule #N)" decoration
    (r"\s*per Standing Rule #\d+\s*\([^)]*\)", ""),
    (r"\s*per Standing Rule #\d+", ""),
    (r"\s*\(Standing Rule #\d+[^)]*\)", ""),
    (r"\bStanding Rule #\d+\b", "the rate-table discipline"),
    # mut anchors that mention specific dates in descriptive prose
    (r"\(.*?\b\d{4}-\d{2}-\d{2}\b.*?\)", ""),
    # Collapse "Input for Cut A — bare math" style artefacts
    (r"\bCut [A-Z]\s*[—\-]\s*bare math[^.]*\.", ""),
    (r"\bCut [A-Z]\s*[—\-]\s*", ""),
    # Collapse leftover "Input for the " → "Input for the "
    (r"\bInput for the \.", "Input."),
    (r"Input for \.", "Input."),
    (r"Input for the\b", "Input for the"),
    # "Input for Car Statutory Formula" — leave as-is
    # Collapse double spaces and tidy
    (r"\s+\.", "."),
    (r"\s+,", ","),
    (r" {2,}", " "),
    # Strip "the architectural canon §X.X" sequences
    (r"the architectural canon §[\d.]+", "the architectural canon"),
]


def sanitise_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    out = text
    for pattern, repl in SANITISERS:
        out = re.sub(pattern, repl, out)
    # Tidy: trim trailing whitespace on lines + collapse multi-newlines.
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# Hand-curated, partner-facing schema descriptions. These OVERRIDE the live
# substrate's internal-forensics descriptions. Keep statute citations + field-
# usage guidance; drop internal phase / forensic / forward-concern references.
SCHEMA_DESCRIPTIONS = {
    "FBTCarOperatingCostInput": (
        "Input for the FBT Car Operating-Cost method (FBTAA Division 2 ss.10–10A).\n\n"
        "Field names are camelCase on the wire. `businessUsePercentage` is on a "
        "0–100 scale. `acquisitionCost` (chained-DV walk) and `openingDepreciatedValue` "
        "(legacy single-year primitive) are mutually exclusive — supply exactly one. "
        "`daysHeldInFBTYear` is required only for in-FY-acquisition chained-DV cases."
    ),
    "FBTLoanInput": (
        "Input for the FBT Loan Fringe Benefit method (FBTAA Division 4 ss.16–19; Type 2 only).\n\n"
        "`fbtBenchmarkInterestAmount` is the dollar amount (not the rate); the rate is applied "
        "upstream by the caller against `originalLoanAmount` if supplied."
    ),
    "FBTDebtWaiverInput": (
        "Input for the FBT Debt Waiver Fringe Benefit method (FBTAA s.16; Type 2 only)."
    ),
    "FBTExpensePaymentInput": (
        "Input for the standard FBT Expense Payment Fringe Benefit method "
        "(FBTAA Division 5 ss.20–24)."
    ),
    "FBTExpensePaymentInHouseInput": (
        "Input for the in-house FBT Expense Payment Fringe Benefit method "
        "(FBTAA s.62 in-house benefit cap applies)."
    ),
    "FBTPropertyInput": (
        "Input for the standard FBT Property Fringe Benefit method "
        "(FBTAA Division 7 ss.40–44)."
    ),
    "FBTPropertyInHouseInput": (
        "Input for the in-house FBT Property Fringe Benefit method "
        "(FBTAA s.62 in-house benefit cap applies)."
    ),
    "FBTResidualInput": (
        "Input for the standard FBT Residual Fringe Benefit method "
        "(FBTAA Division 12 ss.45–52)."
    ),
    "FBTResidualInHouseInput": (
        "Input for the in-house FBT Residual Fringe Benefit method "
        "(FBTAA s.62 in-house benefit cap applies)."
    ),
    "FBTHousingInput": (
        "Input for the Non-Remote FBT Housing Fringe Benefit method "
        "(FBTAA s.26(1)(c) + s.26(2)(b)).\n\n"
        "`indexationFactor` is period-scoped per s.26(2)(b); FY2026 published State "
        "rates span 0.988 (TAS) to 1.100 (WA). Out-of-range values reset to 1.0 "
        "(the legacy clamp under-indexes WA's 1.100; partners targeting WA-resident "
        "employees should supply 1.0 explicitly to bypass)."
    ),
    "FBTLafhaInput": (
        "Input for the FBT Living-Away-From-Home Allowance method "
        "(FBTAA s.31; always Type 2 per ATO TR 96/9).\n\n"
        "`exemptFoodComponent` is the pre-computed scalar; the TD 2025/2 composition "
        "lookup is a caller-side concern."
    ),
    "FBTBoardInput": (
        "Input for the FBT Board Fringe Benefit method (FBTAA s.36; Type 2 only)."
    ),
    "FBTTebeInput": (
        "Input for the FBT Tax-Exempt Body Entertainment method "
        "(FBTAA Subdivision B of Division 10 ss.38–39).\n\n"
        "50/50-split method is a caller-side concern; supply the post-50/50 totals "
        "and the engine sums."
    ),
    "FBTCarParkingActualInput": (
        "Input for the FBT Car Parking Actual method (FBTAA Division 10A; simple-sum)."
    ),
    "FBTCarParkingStatutory228Input": (
        "Input for the FBT Car Parking 228-Day Statutory Formula method (FBTAA s.39FA)."
    ),
    "FBTCarParkingRegister12WkInput": (
        "Input for the FBT Car Parking 12-Week Register method (FBTAA s.39GB)."
    ),
    "FBTMealEntertainment5050Input": (
        "Input for the FBT Meal Entertainment 50/50 Split method "
        "(FBTAA s.37CA; Division 9A)."
    ),
    "FBTMealEntertainmentRegister12WkInput": (
        "Input for the FBT Meal Entertainment 12-Week Register method "
        "(FBTAA s.37CB; Division 9A). `registerPercentage` is required."
    ),
    "FBTCarStatutoryFormulaInput": (
        "Input for the FBT Car Statutory Formula method "
        "(FBTAA s.9; rate-table-fed).\n\n"
        "Consumes the FY2026 statutory-fraction + days-in-year rate-table fact-nodes; "
        "the engine throws `missing_rate(...)` if absent."
    ),
    "DepreciationAuditInput": (
        "Input for the Depreciation Audit endpoint.\n\n"
        "Carries a `transitionDate`, a `method` discriminator, and an `assetsToAudit` batch. "
        "`method` is constrained to `primecost` (straight-line) or `dvmethod` "
        "(diminishing value); the engine default is `primecost`."
    ),
    "DepreciationAuditAssetInput": (
        "One asset row in a depreciation-audit batch.\n\n"
        "Fields are atom-pure carriers of identity; the engine uses `assetName` "
        "via its Tier-1 classifier to resolve effective-life category."
    ),
    "CalculatorListing": (
        "One entry in the calculator-discovery listing returned by GET /v1/calculators."
    ),
    "CalculatorInvocationResponse": (
        "Standard wire shape for any calculator invocation response. Carries the "
        "computed `taxable_value`, the algebraic `trace`, a `manifest` of consumed "
        "rate-table sources (with `content_hash` provenance), and an `advisory` block."
    ),
    "AdvisoryBlock": (
        "Compliance advisory block. Surfaces a disclaimer, whether a registered tax agent "
        "is required, the statutory basis for that requirement, and the jurisdiction."
    ),
    "Manifest": (
        "Manifest of rate-table sources consumed during a calculation. Each entry "
        "carries the source URI and the source's `content_hash` for provenance."
    ),
    "ManifestRateTableEntry": (
        "One entry in the manifest's `rate_table_uris` block. Carries the source URI "
        "and its `content_hash` for provenance."
    ),
}

# Hand-curated path/operation descriptions.
PATH_DESCRIPTIONS = {
    ("/v1/calculators", "get"): (
        "Return the manifest of calculators available through this REST surface, "
        "with per-calculator metadata (URN, label, supported periods, input schema reference, jurisdiction)."
    ),
    ("/v1/calculators/{calc_uri}/{period_uri}", "post"): (
        "Invoke a calculator for the given URN-encoded period. URL-encode the colons "
        "in the URN if your client doesn't auto-encode. Request body matches the "
        "calculator's declared input schema (see `input_schema_ref` from the discovery "
        "response). Response carries the computed result, algebraic trace, manifest of "
        "consumed rate-table sources, and an advisory block."
    ),
    ("/v1/calculators/depreciation/audit/{period_uri}", "post"): (
        "Specialised invoke for the depreciation-audit calculator. Distinct from the "
        "general invoke endpoint because the audit takes a list of assets in a single call."
    ),
    ("/v1/rates/{period_uri}", "get"): (
        "List the statutory rate-table fact-nodes for a period. Returns a JSON object "
        "mapping rate IDs to values + per-rate `content_hash` for provenance."
    ),
    ("/v1/rates/{period_uri}/{rate_id}", "get"): (
        "Return a single rate-table fact-node body plus its `content_hash`."
    ),
    ("/mcp", "post"): (
        "Single MCP JSON-RPC 2.0 entry point. POST a JSON-RPC envelope; receive a "
        "JSON-RPC result or structured error. Supported methods: `tools/list`, "
        "`tools/call`, `resources/list`, `resources/read`. Per MCP spec 2025-06-18."
    ),
    ("/healthz", "get"): (
        "Internal liveness probe used by Cloud Run startup/liveness. "
        "External public traffic to this path is intercepted by Google's edge layer "
        "and returns a generic 404 HTML page; for partner-facing liveness checks, "
        "probe `/v1/calculators` or `/livez` instead."
    ),
    ("/livez", "get"): (
        "Public-traffic liveness probe. Mirror of `/healthz` at a non-reserved path."
    ),
}


def apply_overrides(spec):
    schemas = spec.get("components", {}).get("schemas", {})
    for name, desc in SCHEMA_DESCRIPTIONS.items():
        if name in schemas:
            schemas[name]["description"] = desc
    paths = spec.get("paths", {})
    for (path, method), desc in PATH_DESCRIPTIONS.items():
        if path in paths and method in paths[path]:
            paths[path][method]["description"] = desc


def walk(node, path=""):
    """Recursively sanitise description-shaped strings."""
    if isinstance(node, dict):
        for k, v in node.items():
            new_path = f"{path}.{k}" if path else k
            if k in ("description", "summary", "title") and isinstance(v, str):
                sanitised = sanitise_text(v)
                if sanitised != v:
                    node[k] = sanitised
            else:
                walk(v, new_path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            walk(item, f"{path}[{i}]")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sanitise a raw OpenAPI spec dump from the calc-api into the "
            "partner-facing kit snapshot. Strips internal forensic references "
            "(thread numbers, mutation IDs, phase nomenclature, file paths) "
            "and applies hand-curated partner-facing descriptions over schema + "
            "path documentation. The structural shape (types, required fields, "
            "constraints) is preserved byte-for-byte."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=(
            f"Raw spec input (default: {DEFAULT_INPUT.name} in the same directory). "
            "Fetch with: curl -s https://fbt-calculator-api-8340695160.australia-southeast1.run.app/openapi.json -o <input>"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Sanitised output (default: {DEFAULT_OUTPUT.name} in the same directory).",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        spec = json.load(f)

    apply_overrides(spec)
    walk(spec)

    # Also override info.title/summary/description to clean partner-facing copy.
    info = spec.get("info", {})
    info["title"] = "ClawDog Calculator-Constellation REST API"
    info["summary"] = (
        "Public REST + MCP surface over the LodgeiT Labs calculator pool. "
        "Discover and invoke 20 SBRM-vocabulary deterministic calculators "
        "(Australian Fringe Benefits Tax, Depreciation) from any HTTP/JSON-RPC client."
    )
    info["description"] = (
        "Integration target for partner developers consuming the LodgeiT Labs "
        "calculator constellation. Each calculator is a statute-bound deterministic "
        "reasoner identified by URN (e.g. `urn:sbrm:calculator:fbt:car-operating-cost`); "
        "invocation pairs a calculator URN with a domain-prefixed period URN "
        "(e.g. `urn:sbrm:period:fbt:fy2026`). The response carries the computed "
        "result, the algebraic trace, a manifest of consumed rate-table sources "
        "(with `content_hash` provenance), and an advisory block surfacing "
        "compliance hints.\n\n"
        "See the `clawdog-calculator-api-integration-kit` for partner-facing docs, "
        "runnable examples, and client-regeneration commands."
    )

    with open(args.output, "w") as f:
        json.dump(spec, f, ensure_ascii=False, separators=(",", ":"))

    # Re-scan output for known-leak patterns to confirm clean.
    with open(args.output) as f:
        out_text = f.read()

    leaks_found = []
    for pattern in [
        r"OT #\d+",
        r"Lesson #\d+",
        r"mut-\d{4}-\d{2}-\d{2}",
        r"Phase 3[abc]",
        r"Phase 2[a-z]",
        r"clawdog-brain",
        r"futureWA",
        r"CLAWDOG/\d{3}",
        r"FBT_Engine\.pl",
        r"api/routes/calculators\.py",
        r"_CALC_INPUT_MODEL_REST",
        r"Standing Rule #\d+",
    ]:
        matches = re.findall(pattern, out_text)
        if matches:
            leaks_found.append((pattern, len(matches), matches[:3]))

    if leaks_found:
        print("❌ Residual leaks found:")
        for p, n, samples in leaks_found:
            print(f"  {p}: {n} hits, e.g. {samples}")
        return 1
    print(f"✅ Sanitised → {args.output}")
    print(f"   Size: {len(out_text)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
