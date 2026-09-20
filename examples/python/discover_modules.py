#!/usr/bin/env python3
"""
ClawDog Calculator-Constellation REST API — Module discovery + filtering.

Demonstrates GET /v1/modules and GET /v1/calculators?module=<uri> (added after
clawdog-calculator-api PR #46). Uses only the Python standard library.

Usage:
    python3 discover_modules.py

Environment variables:
    CLAWDOG_CALC_API_URL    Base URL (default: production Cloud Run URL).
    CLAWDOG_CALC_TIMEOUT    Per-request timeout in seconds (default: 30).
"""

import json
import os
import sys
import urllib.request

DEFAULT_BASE_URL = (
    "https://fbt-calculator-api-8340695160.australia-southeast1.run.app"
)
BASE_URL = os.environ.get("CLAWDOG_CALC_API_URL", DEFAULT_BASE_URL)
TIMEOUT = float(os.environ.get("CLAWDOG_CALC_TIMEOUT", "30"))


def http_get(path: str) -> dict | list:
    """GET against the calc-api."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def main() -> int:
    print(f"Base URL: {BASE_URL}\n")

    # ---- Step 1: GET /v1/modules ----
    print("=== Step 1 — GET /v1/modules ===")
    modules = http_get("/v1/modules")
    print(f"Discovered {len(modules)} modules.\n")
    for m in modules:
        print(f"  • {m['module_uri']}")
        print(f"      label:        {m['label']}")
        print(f"      jurisdiction: {m['jurisdiction']}")
        print(f"      calculators:  {len(m['calculators'])} ({', '.join(c.split(':')[-1] for c in m['calculators'][:3])}{'…' if len(m['calculators']) > 3 else ''})")
        print()

    # ---- Step 2: GET /v1/calculators?module=urn:sbrm:module:fbt ----
    module_uri = "urn:sbrm:module:fbt"
    print(f"=== Step 2 — GET /v1/calculators?module={module_uri} ===")
    fbt_calcs = http_get(f"/v1/calculators?module={module_uri}")
    print(f"FBT calculators: {len(fbt_calcs)}\n")
    for c in fbt_calcs:
        calc_name = c['calc_uri'].split(':')[-1]
        selection_kind = c.get('selection', {}).get('kind', '?')
        print(f"  {c['calc_uri']} — {selection_kind}")
    
    print("\n=== Done ===")
    print("\nSelecting a calculator:")
    print("  Pick in three steps. Module (fbt, div7a or depreciation). Benefit")
    print("  type is a fact — establish it from what actually happened, testing")
    print("  the specific FBT types in resolution order before residual. Method:")
    print("  where a benefit type has more than one valuation method the")
    print("  selection.kind is election or statutory_default — the method is the")
    print("  employer's choice, not yours. Compute every method in the group the")
    print("  records support, present them side by side with the election")
    print("  provision, and let the employer choose. Never pick the method for them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
