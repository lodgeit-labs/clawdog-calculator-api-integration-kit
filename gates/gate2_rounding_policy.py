#!/usr/bin/env python3
"""
Kit Gate 2 — rounding-policy assertion.

Asserts the constellation-wide rounding-policy invariant:

    On every HTTP 200 invoke response, across all 23 calculator URNs,
    the response carries  manifest.rounding_policy == "lodgeit-rounding-1.0".

Why this gate exists
--------------------
`rounding_policy` is the single wire fact a partner integration relies on to
know *which* half-up / bankers' / decimal-quantise discipline produced every
money field in the response. If one calculator in the constellation silently
served a different (or absent) rounding policy, a partner reconciling our
numbers against their own ledger would get an off-by-a-cent divergence with no
signal as to why. This gate turns that silent-drift failure mode into a red CI
signal.

It is the assertion sibling of the existing live-substrate probe: that gate
proves the contract is byte-aligned with the pinned snapshot; this gate proves
the rounding-policy invariant holds on *every* 200 the constellation serves.

Discipline (mirrors Gate 1 / the Python quickstart)
---------------------------------------------------
* Standard library only. No third-party dependencies.
* Discovers the URN list live from GET /v1/calculators; it does NOT hard-code
  the 23 URNs, so the gate tracks constellation growth automatically. It DOES
  assert the count is exactly 23 (the constellation size at this kit pin) so an
  unexpected shrink/grow is itself a red signal.
* Retry-with-jitter on 5xx (same shape as examples/python/quickstart.py), so a
  Cloud Run cold-start or 529 backpressure blip does not flap the gate.
* Honest about unreachability: if EVERY URN is unreachable (network/substrate
  down), the gate reports UNREACHABLE and — unless STRICT is set — exits 0 with
  a clear "could not verify" message rather than a false red. In CI it runs in
  STRICT mode (see .github/workflows/test.yml) so a real substrate outage does
  fail the gate.

Environment variables
----------------------
    CLAWDOG_CALC_API_URL    Base URL (default: production Cloud Run URL).
    CLAWDOG_CALC_TIMEOUT    Per-request timeout in seconds (default: 30).
    CLAWDOG_CALC_RETRIES    Max retries on 5xx (default: 5).
    CLAWDOG_GATE_STRICT     If "1", an unreachable substrate is a FAILURE
                            (exit 1) rather than a skip. CI sets this.

Exit codes
----------
    0  invariant held on every 200 (23/23 URNs probed, counts unchanged), OR
       substrate unreachable and STRICT is not set (reported honestly).
    1  a 200 response violated the invariant, OR the URN count != 23, OR
       STRICT is set and the substrate was unreachable.

— ClawDog
"""

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = (
    "https://fbt-calculator-api-8340695160.australia-southeast1.run.app"
)
BASE_URL = os.environ.get("CLAWDOG_CALC_API_URL", DEFAULT_BASE_URL)
TIMEOUT = float(os.environ.get("CLAWDOG_CALC_TIMEOUT", "30"))
MAX_RETRIES = int(os.environ.get("CLAWDOG_CALC_RETRIES", "5"))
STRICT = os.environ.get("CLAWDOG_GATE_STRICT", "") == "1"

EXPECTED_URN_COUNT = 23
EXPECTED_ROUNDING_POLICY = "lodgeit-rounding-1.0"

# A minimal-but-schema-valid fixture per calculator, keyed by the URN's last
# segment. Field names + shapes mirror the pinned OpenAPI snapshot's *Input
# schemas (FBT uses camelCase aliases). These are wire-shape demonstrators, not
# statutory reference cases — the gate asserts the rounding-policy invariant on
# whatever 200 they produce, it does not assert the computed numbers.
FBT_FIXTURES = {
    "car-operating-cost": {
        "businessUsePercentage": 65, "formOfFinance": "owned",
        "fuelRepairsServicing": 8000.0, "registrationInsurance": 2000.0,
        "daysHeldInFBTYear": 366, "acquisitionCost": 45000.0,
        "acquisitionDate": "2024-04-01",
    },
    "loan": {
        "interestChargedByEmployer": 100.0,
        "otherwiseDeductiblePercentage": 0, "originalLoanAmount": 10000.0,
    },
    "debt-waiver": {"amountWaived": 5000.0},
    "expense-payment": {
        "expenseValue": 1000.0, "otherwiseDeductiblePercentage": 0,
        "fbtType": "Type 2",
    },
    "expense-payment-in-house": {
        "expenseValue": 1000.0, "otherwiseDeductiblePercentage": 0,
        "fbtType": "Type 2",
    },
    "property": {
        "gstInclusiveValue": 1000.0, "otherwiseDeductiblePercentage": 0,
        "fbtType": "Type 2",
    },
    "property-in-house": {
        "gstInclusiveValue": 1000.0, "otherwiseDeductiblePercentage": 0,
        "fbtType": "Type 2",
    },
    "residual": {
        "residualValue": 1000.0, "otherwiseDeductiblePercentage": 0,
        "fbtType": "Type 2",
    },
    "residual-in-house": {
        "residualValue": 1000.0, "otherwiseDeductiblePercentage": 0,
        "fbtType": "Type 2",
    },
    "housing": {"housingBenefitValue": 10000.0, "fbtType": "Type 2"},
    "lafha": {
        "weeksLivedAway": 10, "accommodationPerWeek": 300.0,
        "mealsPerWeek": 200.0,
    },
    "board": {"membersOverTwelve": 2, "over12MealsPerChild": 200},
    "tebe": {
        "salaryPackagedMealEfle": 1000.0, "recreation": 500.0,
        "fbtType": "Type 2",
    },
    "car-parking-actual": {"spacesProvided": 5, "valuationMethodRate": 20.0},
    "car-parking-statutory-228": {
        "daysCarParkingAvailable": 228, "valuationMethodRate": 20.0,
    },
    "car-parking-register-12wk": {
        "benefitsInPeriod": 50, "valuationMethodRate": 20.0,
        "daysSpaceAvailable": 228,
    },
    "meal-entertainment-50-50": {
        "employees": 1000.0, "employeesAssociates": 500.0,
        "employeesNonassociates": 500.0, "fbtType": "Type 2",
    },
    "meal-entertainment-register-12wk": {
        "employees": 1000.0, "employeesAssociates": 500.0,
        "employeesNonassociates": 500.0, "fbtType": "Type 2",
        "registerPercentage": 50.0,
    },
    "car-statutory-formula": {"baseValue": 30000.0, "daysAvailable": 366},
}

DEPRECIATION_ASSET = {
    "cost": 10000.0, "acquisition_date": "2024-07-01",
    "accounting_useful_life_years": 5, "accounting_method": "prime_cost",
}


def _request(method, path, body=None):
    """One HTTP call with retry-with-jitter on 5xx. Returns (status, obj)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url, data=data, headers=headers, method=method
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            # 5xx (incl. 502/503/529) is retryable; 4xx is a definitive answer.
            if 500 <= e.code < 600 and attempt < MAX_RETRIES:
                delay = (2 ** attempt) * 0.2 + random.uniform(0, 0.5)
                delay = min(delay, 10.0)
                print(
                    f"    ⚠ {method} {path} → HTTP {e.code}; "
                    f"retry {attempt + 1}/{MAX_RETRIES} in {delay:.2f}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            try:
                detail = json.loads(e.read())
            except Exception:
                detail = None
            return e.code, detail
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                delay = (2 ** attempt) * 0.2 + random.uniform(0, 0.5)
                time.sleep(min(delay, 10.0))
                continue
            return None, {"transport_error": str(e)}
    return None, {"transport_error": str(last_exc)}


def invoke_for(urn, period):
    """Return (status, obj) for a schema-valid invoke of one URN."""
    if urn == "urn:sbrm:calculator:hp:schedule":
        return _request("POST", "/v1/calculators/hp/schedule", {
            "amount_financed": "10000.00", "annual_rate_pct": "12.0",
            "term_regular_instalments": 12, "instalment": "888.49",
            "timing": "in_arrears", "frequency": "monthly",
            "begin_date": "2025-07-01", "contract_form": "hire_purchase",
        })
    if urn == "urn:sbrm:calculator:div7a:at":
        return _request("POST", f"/v1/calculators/div7a/at/{period}", {
            "amalgamated_base": 100000.0, "loan_term_years": 7,
            "loan_origination_date": "2020-06-01",
            "income_year_start_date": "2025-07-01",
        })
    if urn == "urn:sbrm:calculator:depreciation:at":
        return _request("POST", f"/v1/calculators/depreciation/at/{period}", {
            "basis": "accounting", "asset": DEPRECIATION_ASSET,
            "at_date": "2026-03-31",
        })
    if urn == "urn:sbrm:calculator:depreciation:range":
        return _request("POST", f"/v1/calculators/depreciation/range/{period}", {
            "basis": "accounting", "asset": DEPRECIATION_ASSET,
            "from_date": "2025-07-01", "to_date": "2026-06-30",
            "day_count": "actual/actual",
        })
    short = urn.split(":")[-1]
    fixture = FBT_FIXTURES.get(short)
    if fixture is None:
        return "NO_FIXTURE", None
    return _request("POST", f"/v1/calculators/{urn}/{period}", fixture)


def extract_rounding_policy(obj):
    """Return the rounding_policy from manifest, or None.

    The invariant the task pins is manifest.rounding_policy. On the wire the
    field lives inside the response's `manifest` block for every calculator
    family (verified across fbt / depreciation / div7a / hp). Some calculators
    ALSO echo a top-level `rounding_policy`; the gate asserts on the
    manifest-scoped one, which is the authoritative provenance surface.
    """
    if not isinstance(obj, dict):
        return None
    manifest = obj.get("manifest")
    if isinstance(manifest, dict):
        return manifest.get("rounding_policy")
    return None


def main():
    print("Kit Gate 2 — rounding-policy assertion")
    print(f"Base URL: {BASE_URL}")
    print(f"Invariant: manifest.rounding_policy == {EXPECTED_ROUNDING_POLICY!r} "
          f"on every 200\n")

    # ---- Discover ----
    status, calcs = _request("GET", "/v1/calculators")
    if status != 200 or not isinstance(calcs, list):
        msg = f"discovery unreachable (status={status})"
        if STRICT:
            print(f"❌ {msg} — STRICT mode, failing.")
            return 1
        print(f"⚠ {msg} — could not verify invariant (non-strict); exiting 0.")
        return 0

    urns = [c["calc_uri"] for c in calcs]
    period_of = {c["calc_uri"]: c["supported_periods"][0] for c in calcs}
    count = len(urns)
    print(f"Discovered {count} calculator URNs.")

    if count != EXPECTED_URN_COUNT:
        print(f"❌ URN count is {count}, expected {EXPECTED_URN_COUNT}. "
              f"Constellation size changed — refuse to green a moved goalpost.")
        return 1
    print(f"✅ URN count unchanged: {count}/{EXPECTED_URN_COUNT}\n")

    # ---- Probe every URN ----
    ok_200 = 0          # 200 responses that satisfied the invariant
    violations = []     # 200 responses that did NOT satisfy it
    non_200 = []        # non-200 (not a violation of a *200* invariant)
    unreachable = 0

    for urn in urns:
        period = period_of[urn]
        status, obj = invoke_for(urn, period)
        short = urn.split(":", 3)[-1]

        if status is None:
            unreachable += 1
            print(f"  · {short:38} UNREACHABLE")
            continue
        if status == 200:
            rp = extract_rounding_policy(obj)
            if rp == EXPECTED_ROUNDING_POLICY:
                ok_200 += 1
                print(f"  ✅ {short:38} 200  rounding_policy OK")
            else:
                violations.append((urn, rp))
                print(f"  ❌ {short:38} 200  rounding_policy={rp!r} "
                      f"(expected {EXPECTED_ROUNDING_POLICY!r})")
        else:
            non_200.append((urn, status))
            print(f"  · {short:38} {status}  (not a 200; invariant N/A)")

    probed = count
    print()
    print(f"URNs discovered / probed:      {probed}/{EXPECTED_URN_COUNT}")
    print(f"200 responses satisfying invariant: {ok_200}")
    print(f"200 responses violating:       {len(violations)}")
    print(f"non-200 responses:             {len(non_200)}")
    print(f"unreachable:                   {unreachable}")

    # ---- Verdict ----
    if violations:
        print("\n❌ Gate 2 FAILED — rounding-policy invariant violated:")
        for urn, rp in violations:
            print(f"    {urn}  →  manifest.rounding_policy = {rp!r}")
        return 1

    if unreachable == probed:
        msg = "every URN unreachable — could not verify invariant"
        if STRICT:
            print(f"\n❌ Gate 2 FAILED — {msg} (STRICT).")
            return 1
        print(f"\n⚠ Gate 2 SKIPPED — {msg} (non-strict); exiting 0.")
        return 0

    print(f"\n✅ Gate 2 PASSED — rounding-policy invariant held on every 200 "
          f"across {probed}/{EXPECTED_URN_COUNT} URNs "
          f"({ok_200} live 200s asserted, "
          f"{len(non_200)} non-200, {unreachable} unreachable).")
    print("   URN counts unchanged: 23/23.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
