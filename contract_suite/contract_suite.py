#!/usr/bin/env python3
"""
Constellation contract suite — black-box.

Discovers every calculator on the live gateway and checks each against the
published contract (llms.txt, rounding.html, publish.html). No hard-coded
calculator list: the URN set comes from GET /v1/calculators, matched to input
schemas in GET /openapi.json via the schema's ``x-calc-uri`` extension.

Probes per calculator: (a) valid call, (b) byte-identical repeat, (c) half-cent,
(d) missing required field, (e) unknown period, (f) documented refusal,
(g) mutually-exclusive pair, (h) unknown field, (i) MCP parity. Plus independent
hand/ATO anchors (step 4) that never come from the engine.

Etiquette: one request at a time, >= 0.3 s apart; a kit User-Agent; base URL from
CLAWDOG_CALC_API_URL (default public gateway); no credentials.

Output: a Markdown summary (one row per calculator, columns (a)-(i), check/x/N-A)
written to --summary and appended to $GITHUB_STEP_SUMMARY, plus a failures
section with request+response for each x. Exit 1 on any x.

Standard library only.

— ClawDog
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = (
    "https://fbt-calculator-api-8340695160.australia-southeast1.run.app"
)
BASE_URL = os.environ.get("CLAWDOG_CALC_API_URL", DEFAULT_BASE_URL).rstrip("/")
TIMEOUT = float(os.environ.get("CLAWDOG_CALC_TIMEOUT", "30"))
MAX_RETRIES = int(os.environ.get("CLAWDOG_CALC_RETRIES", "5"))
MIN_INTERVAL = float(os.environ.get("CLAWDOG_CALC_MIN_INTERVAL", "0.3"))
USER_AGENT = "clawdog-calculator-api-integration-kit/contract-suite (+https://github.com/lodgeit-labs/clawdog-calculator-api-integration-kit)"

KIT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = KIT_ROOT / "fixtures"

EXPECTED_ROUNDING_POLICY = "lodgeit-rounding-1.0"

# Independent anchors (step 4). These are assertions from hand arithmetic / the
# ATO, NOT read back from the engine. field path -> expected decimal string.
ANCHORS = {
    "urn:sbrm:calculator:fbt:car-statutory-formula": {"fbt_payable": "8603.71"},
    "urn:sbrm:calculator:div7a:at": {
        # keyed by period because the same URN is anchored in two years
        "__by_period__": {
            "urn:sbrm:period:div7a:fy2025": {"statutory_myr": "13801.18"},
            "urn:sbrm:period:div7a:fy2026": {"statutory_myr": "13615.68"},
        }
    },
    "urn:sbrm:calculator:depreciation:range": {
        "range_dep": "2000.00", "opening_wdv": "8000.00", "closing_wdv": "6000.00"
    },
    "urn:sbrm:calculator:hp:schedule": {
        "totals.interest": "32531.91", "totals.rounding_residual": "0.05"
    },
}

_last_request_ts = 0.0


def _throttle():
    global _last_request_ts
    now = time.monotonic()
    wait = MIN_INTERVAL - (now - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def request(method, path, body=None):
    """One throttled HTTP call with retry-with-jitter on 5xx. (status, obj)."""
    import random
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        _throttle()
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                try:
                    return resp.status, json.loads(raw)
                except ValueError:
                    return resp.status, {"_raw": raw.decode("utf-8", "replace")}
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600 and attempt < MAX_RETRIES:
                delay = min((2 ** attempt) * 0.2 + random.uniform(0, 0.5), 10.0)
                time.sleep(delay)
                continue
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(min((2 ** attempt) * 0.2 + random.uniform(0, 0.5), 10.0))
                continue
            return None, {"transport_error": str(e)}
    return None, {"transport_error": str(last_exc)}


def raw_bytes(method, path, body=None):
    """Return the raw response body bytes (for byte-identical repeat check)."""
    import random
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(MAX_RETRIES + 1):
        _throttle()
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600 and attempt < MAX_RETRIES:
                time.sleep(min((2 ** attempt) * 0.2 + random.uniform(0, 0.5), 10.0))
                continue
            return e.code, None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < MAX_RETRIES:
                time.sleep(min((2 ** attempt) * 0.2 + random.uniform(0, 0.5), 10.0))
                continue
            return None, None
    return None, None


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

def discover():
    """Return (calculators, schemas_by_uri, modules). Raises on count mismatch."""
    status, calcs = request("GET", "/v1/calculators")
    if status != 200 or not isinstance(calcs, list):
        raise SystemExit(f"discovery failed: GET /v1/calculators -> {status}")
    status, spec = request("GET", "/openapi.json")
    if status != 200 or not isinstance(spec, dict):
        raise SystemExit(f"discovery failed: GET /openapi.json -> {status}")
    status, modules = request("GET", "/v1/modules")
    if status != 200 or not isinstance(modules, list):
        raise SystemExit(f"discovery failed: GET /v1/modules -> {status}")

    # Map each input schema to its calc_uri via x-calc-uri.
    all_schemas = spec.get("components", {}).get("schemas", {})
    schemas_by_uri = {}
    for name, schema in all_schemas.items():
        cu = schema.get("x-calc-uri")
        if cu:
            schemas_by_uri[cu] = {"name": name, "schema": schema}

    # Count agreement across /v1/calculators and /v1/modules.
    module_calc_count = sum(len(m.get("calculators", [])) for m in modules)
    if module_calc_count != len(calcs):
        raise SystemExit(
            f"count mismatch: /v1/calculators={len(calcs)} vs "
            f"sum(/v1/modules[].calculators)={module_calc_count}"
        )
    return calcs, schemas_by_uri, modules, all_schemas


# --------------------------------------------------------------------------
# Schema helpers
# --------------------------------------------------------------------------

def resolved_input_schema(entry, spec):
    return entry["schema"]


def _prop_is_money(prop):
    if not isinstance(prop, dict):
        return False
    if prop.get("x-money") is True:
        return True
    for branch in prop.get("anyOf", []) + prop.get("oneOf", []):
        if isinstance(branch, dict) and branch.get("x-money") is True:
            return True
    return False


def _deref(prop, all_schemas):
    """Resolve a single $ref (direct or inside allOf) to its target schema."""
    ref = prop.get("$ref")
    if not ref:
        for sub in prop.get("allOf", []):
            if isinstance(sub, dict) and sub.get("$ref"):
                ref = sub["$ref"]
                break
    if ref and ref.startswith("#/components/schemas/"):
        return all_schemas.get(ref.split("/")[-1])
    return None


def x_money_fields(schema, all_schemas=None, _prefix="", _seen=None):
    """Return DOTTED paths of every x-money field, walking nested objects and
    $ref targets (e.g. 'asset.cost'). all_schemas enables $ref resolution."""
    all_schemas = all_schemas or {}
    _seen = _seen or set()
    out = []
    for fname, prop in (schema.get("properties", {})).items():
        if not isinstance(prop, dict):
            continue
        path = _prefix + fname
        if _prop_is_money(prop):
            out.append(path)
        # nested inline object
        if prop.get("type") == "object" and prop.get("properties"):
            out += x_money_fields(prop, all_schemas, path + ".", _seen)
        # $ref / allOf-$ref target
        target = _deref(prop, all_schemas)
        if target is not None:
            key = id(target)
            if key not in _seen:
                _seen = _seen | {key}
                out += x_money_fields(target, all_schemas, path + ".", _seen)
    return out


def required_fields(schema):
    return list(schema.get("required", []))


def mutually_exclusive_pairs(schema):
    """Return de-duplicated unordered {A,B} pairs. x-mutually-exclusive is a
    LIST (schema-level: list of pairs; property-level: list of sibling names
    that are mutually exclusive with this property). A-B and B-A collapse."""
    pairs = []
    xme = schema.get("x-mutually-exclusive")
    if isinstance(xme, list):
        for item in xme:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                pairs.append([item[0], item[1]])
    # property-level: value is a LIST of sibling field names.
    for fname, prop in (schema.get("properties", {})).items():
        if not isinstance(prop, dict):
            continue
        other = prop.get("x-mutually-exclusive")
        if isinstance(other, str):
            pairs.append([fname, other])
        elif isinstance(other, (list, tuple)):
            for sib in other:
                if isinstance(sib, str):
                    pairs.append([fname, sib])
    seen, uniq = set(), []
    for a, b in pairs:
        key = tuple(sorted((a, b)))
        if key not in seen:
            seen.add(key)
            uniq.append([a, b])
    return uniq


def additional_properties_false(schema):
    return schema.get("additionalProperties") is False


def period_module(calc_uri):
    # urn:sbrm:calculator:<module>:<method>
    return calc_uri.split(":")[3]


# --------------------------------------------------------------------------
# JSON-number scan (money/rates must be strings on the wire)
# --------------------------------------------------------------------------

def non_integer_json_numbers(obj, path="$"):
    """Return paths of any non-integer JSON number literal in the body."""
    bad = []
    if isinstance(obj, float):
        bad.append(path)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, int):
        pass
    elif isinstance(obj, dict):
        for k, v in obj.items():
            bad += non_integer_json_numbers(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad += non_integer_json_numbers(v, f"{path}[{i}]")
    return bad


def dotted_get(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


# --------------------------------------------------------------------------
# Invocation path + body construction
# --------------------------------------------------------------------------

def invoke_path(calc_uri, period_uri):
    module = period_module(calc_uri)
    if calc_uri == "urn:sbrm:calculator:hp:schedule":
        return "/v1/calculators/hp/schedule"
    if calc_uri == "urn:sbrm:calculator:div7a:at":
        return f"/v1/calculators/div7a/at/{period_uri}"
    if calc_uri == "urn:sbrm:calculator:depreciation:at":
        return f"/v1/calculators/depreciation/at/{period_uri}"
    if calc_uri == "urn:sbrm:calculator:depreciation:range":
        return f"/v1/calculators/depreciation/range/{period_uri}"
    return f"/v1/calculators/{calc_uri}/{period_uri}"


def set_field(body, field, value):
    """Set a (possibly nested a.b) field on a shallow copy of body."""
    import copy
    b = copy.deepcopy(body)
    parts = field.split(".")
    cur = b
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    return b


# --------------------------------------------------------------------------
# Per-calculator probes
# --------------------------------------------------------------------------

RESULT_SYMBOLS = {"pass": "✓", "fail": "✗", "na": "N/A"}


class Probe:
    def __init__(self, name):
        self.name = name
        self.status = "na"
        self.detail = ""
        self.request = None
        self.response = None

    def set(self, status, detail="", req=None, resp=None):
        self.status = status
        self.detail = detail
        if req is not None:
            self.request = req
        if resp is not None:
            self.response = resp
        return self


def probe_a_valid(calc_uri, path, body):
    p = Probe("a")
    status, obj = request("POST", path, body)
    p.request = {"path": path, "body": body}
    p.response = obj
    if status != 200:
        return p.set("fail", f"expected 200, got {status}")
    problems = []
    bad = non_integer_json_numbers(obj)
    if bad:
        problems.append(f"non-integer JSON numbers at: {', '.join(bad[:5])}")
    manifest = obj.get("manifest") if isinstance(obj, dict) else None
    if not isinstance(manifest, dict):
        problems.append("manifest missing")
    else:
        for e in manifest.get("rate_table_uris", []):
            if not all(k in e for k in ("uri", "content_hash", "hash_algorithm")):
                problems.append("rate_table_uris entry missing uri/content_hash/hash_algorithm")
                break
        if "rounding_policy" not in manifest:
            problems.append("manifest.rounding_policy missing")
    adv = obj.get("advisory") if isinstance(obj, dict) else None
    if not isinstance(adv, dict) or "disclaimer" not in adv:
        problems.append("advisory.disclaimer missing")
    if problems:
        return p.set("fail", "; ".join(problems))
    return p.set("pass")


def probe_b_repeat(path, body):
    p = Probe("b")
    s1, r1 = raw_bytes("POST", path, body)
    s2, r2 = raw_bytes("POST", path, body)
    p.request = {"path": path, "body": body}
    if s1 != 200 or s2 != 200:
        return p.set("fail", f"non-200 on repeat ({s1}/{s2})")
    if r1 != r2:
        p.response = {"first_len": len(r1 or b""), "second_len": len(r2 or b"")}
        return p.set("fail", "repeat body not byte-identical")
    return p.set("pass")


def _dotted_get_body(body, dotted):
    cur = body
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None, False
    return cur, True


def _halfcent_value(current):
    """Produce a half-cent value KEEPING the field's JSON type, so the probe
    tests quantisation, not a type error. number 45000 -> 45000.005;
    string '10000.00' -> '10000.005'."""
    if isinstance(current, str):
        # replace the fractional part with a 3-dp half-cent; fall back to append
        if "." in current:
            whole = current.split(".")[0]
        else:
            whole = current or "0"
        return f"{whole}.005"
    # numbers (int or float) -> a non-cent-quantised float
    base = 0
    try:
        base = int(float(current))
    except (TypeError, ValueError):
        base = 0
    return base + 0.005


def probe_c_halfcent(calc_uri, path, body, schema, all_schemas):
    p = Probe("c")
    money = x_money_fields(schema, all_schemas)
    if not money:
        return p.set("na", "no x-money field in schema")
    field = money[0]  # dotted path, e.g. 'asset.cost'
    current, present = _dotted_get_body(body, field)
    if not present:
        # seed the field so the type is well-defined; prefer string for nested
        # money that the fixture didn't carry, else a number.
        current = "0.00"
    bad_value = _halfcent_value(current)
    bad_body = set_field(body, field, bad_value)
    status, obj = request("POST", path, bad_body)
    p.request = {"path": path, "body": bad_body, "money_field": field}
    p.response = obj
    if status != 422:
        return p.set("fail", f"expected 422, got {status} (field {field})")
    detail = obj.get("detail") if isinstance(obj, dict) else None
    if not isinstance(detail, list):
        return p.set("fail", "422 detail not a list")
    expected_loc = ["body"] + field.split(".")
    for e in detail:
        if e.get("type") == "money_not_cent_quantised":
            loc = e.get("loc") or []
            if list(loc) == expected_loc:
                return p.set("pass")
            # tolerate the engine omitting intermediate object segments but
            # still require body-prefix + the leaf field name
            if loc and loc[0] == "body" and loc[-1] == field.split(".")[-1]:
                return p.set("pass")
            return p.set("fail", f"money_not_cent_quantised loc={loc}, expected {expected_loc}")
    return p.set("fail", "no money_not_cent_quantised in 422 detail")


def probe_d_missing_required(path, body, schema):
    p = Probe("d")
    req = [f for f in required_fields(schema) if f != "period_uri"]
    if not req:
        return p.set("na", "schema has no required fields")
    field = req[0]
    import copy
    bad = copy.deepcopy(body)
    bad.pop(field, None)
    status, obj = request("POST", path, bad)
    p.request = {"path": path, "body": bad, "dropped": field}
    p.response = obj
    if status != 422:
        return p.set("fail", f"expected 422, got {status}")
    blob = json.dumps(obj)
    if field in blob:
        return p.set("pass")
    return p.set("fail", f"422 did not name dropped field '{field}'")


def probe_e_unknown_period(calc_uri, body):
    p = Probe("e")
    module = period_module(calc_uri)
    bogus = f"urn:sbrm:period:{module}:fy1999"
    path = invoke_path(calc_uri, bogus)
    status, obj = request("POST", path, body)
    p.request = {"path": path, "body": body}
    p.response = obj
    if status == 404:
        return p.set("pass")
    return p.set("fail", f"expected 404, got {status}")


def probe_f_refusal(refusal):
    p = Probe("f")
    path = invoke_path(refusal["calc_uri"], refusal.get("period_uri"))
    status, obj = request("POST", path, refusal["body"])
    p.request = {"path": path, "body": refusal["body"], "name": refusal["name"]}
    p.response = obj
    exp = refusal["expect"]
    if status != exp["status"]:
        return p.set("fail", f"expected {exp['status']}, got {status}")
    detail = obj.get("detail") if isinstance(obj, dict) else None
    if not isinstance(detail, dict):
        return p.set("fail", "400 detail is not an object (refusal_class not top-level)")
    probs = []
    if detail.get("refusal_class") != exp["refusal_class"]:
        probs.append(f"refusal_class={detail.get('refusal_class')!r} != {exp['refusal_class']!r}")
    if "refusal_payload" not in detail:
        probs.append("refusal_payload missing")
    if detail.get("engine") != exp["engine"]:
        probs.append(f"engine={detail.get('engine')!r} != {exp['engine']!r}")
    if "message" not in detail:
        probs.append("message missing")
    if probs:
        return p.set("fail", "; ".join(probs))
    return p.set("pass")


def probe_g_mutex(calc_uri, path, body, schema):
    p = Probe("g")
    pairs = mutually_exclusive_pairs(schema)
    if not pairs:
        return p.set("na", "no x-mutually-exclusive pair")
    a, b = pairs[0][0], pairs[0][1]
    import copy
    bad = copy.deepcopy(body)
    # give both members a plausible numeric value
    bad[a] = 50000
    bad[b] = 35000
    status, obj = request("POST", path, bad)
    p.request = {"path": path, "body": bad, "pair": [a, b]}
    p.response = obj
    if status != 422:
        return p.set("fail", f"expected 422, got {status}")
    blob = json.dumps(obj)
    if "mutually_exclusive_inputs" in blob:
        return p.set("pass")
    return p.set("fail", "422 without mutually_exclusive_inputs")


def probe_h_unknown_field(path, body, schema):
    p = Probe("h")
    if not additional_properties_false(schema):
        return p.set("na", "additionalProperties not false")
    bad = dict(body)
    bad["zz_unknown"] = 1
    status, obj = request("POST", path, bad)
    p.request = {"path": path, "body": bad}
    p.response = obj
    if status != 422:
        return p.set("fail", f"expected 422, got {status}")
    if "zz_unknown" in json.dumps(obj):
        return p.set("pass")
    return p.set("fail", "422 did not name unknown field zz_unknown")


# --------------------------------------------------------------------------
# MCP (probe i) — run once, parity-checked per calculator
# --------------------------------------------------------------------------

def mcp_rpc(method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return request("POST", "/mcp", body)


def tool_name_for(calc_uri):
    # tools are named by the URN's method-ish slug; the kit resolves via tools/list
    return None


def run_mcp(calcs, fixtures, periods, tool_names):
    """Returns dict calc_uri -> ('pass'|'fail'|'na', detail) for probe (i),
    plus a top-level MCP summary."""
    results = {}
    top = {}
    # initialize
    s, obj = mcp_rpc("initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "contract-suite", "version": "1.0"}})
    top["initialize"] = (s == 200 and isinstance(obj, dict) and "result" in obj)
    mcp_rpc("notifications/initialized")
    # tools/list
    s, obj = mcp_rpc("tools/list", id_=2)
    tools = (obj or {}).get("result", {}).get("tools", []) if isinstance(obj, dict) else []
    top["tools_count"] = len(tools)
    top["tools_count_matches"] = (len(tools) == len(calcs))
    # map calc_uri -> tool name via the tool's annotations/_meta if present,
    # else fall back to the provided tool_names map.
    name_by_uri = dict(tool_names)
    for t in tools:
        meta = t.get("_meta") or {}
        cu = meta.get("calc_uri") or t.get("x-calc-uri")
        if cu:
            name_by_uri[cu] = t["name"]
    # per-calculator parity: tools/call structuredContent == REST body
    for cu in calcs:
        fx = fixtures.get(cu)
        if not fx:
            results[cu] = ("na", "no fixture")
            continue
        period = periods.get(cu)
        args = dict(fx["body"])
        if period and cu not in ("urn:sbrm:calculator:hp:schedule",):
            args.setdefault("period_uri", period)
        tname = name_by_uri.get(cu)
        if not tname:
            results[cu] = ("fail", "no MCP tool mapped to this calc_uri")
            continue
        s, obj = mcp_rpc("tools/call", {"name": tname, "arguments": args}, id_=3)
        res = (obj or {}).get("result") if isinstance(obj, dict) else None
        if not isinstance(res, dict):
            results[cu] = ("fail", f"tools/call no result (status {s})")
            continue
        sc = res.get("structuredContent")
        # REST body for comparison
        rpath = invoke_path(cu, period)
        rstatus, rbody = request("POST", rpath, fx["body"])
        if rstatus != 200:
            results[cu] = ("na", f"REST not 200 ({rstatus}); parity not applicable")
            continue
        if sc == rbody:
            results[cu] = ("pass", "")
        else:
            results[cu] = ("fail", "structuredContent != REST body")
    # half-cent → isError
    top["halfcent_isError"] = None
    hc_uri = "urn:sbrm:calculator:fbt:car-statutory-formula"
    if hc_uri in name_by_uri:
        args = {"baseValue": 45000.005, "accessories": 5000, "daysAvailable": 365,
                "employeeContribution": 1200, "fbtType": "Type 1"}
        s, obj = mcp_rpc("tools/call", {"name": name_by_uri[hc_uri], "arguments": args}, id_=4)
        res = (obj or {}).get("result") if isinstance(obj, dict) else None
        top["halfcent_isError"] = bool(res and res.get("isError") is True)
    return results, top, name_by_uri


# --------------------------------------------------------------------------
# Anchors (step 4)
# --------------------------------------------------------------------------

def check_anchors(calc_uri, period_uri, body200):
    """Return (ok, messages[]) for the independent anchors on this calc/period."""
    spec = ANCHORS.get(calc_uri)
    if not spec:
        return True, []
    msgs, ok = [], True
    if "__by_period__" in spec:
        spec = spec["__by_period__"].get(period_uri, {})
    for field, expected in spec.items():
        got = dotted_get(body200, field)
        if str(got) != str(expected):
            ok = False
            msgs.append(f"anchor {calc_uri} {field}={got!r} != {expected!r}")
    return ok, msgs


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

COLUMNS = ["a", "b", "c", "d", "e", "f", "g", "h", "i"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default="contract-summary.md")
    args = ap.parse_args()

    calcs_meta, schemas_by_uri, modules, all_schemas = discover()
    calc_uris = [c["calc_uri"] for c in calcs_meta]
    period_by_uri = {}
    for c in calcs_meta:
        sp = c.get("supported_periods") or []
        period_by_uri[c["calc_uri"]] = sp[0] if sp else None

    fixtures = json.loads((FIXTURES_DIR / "valid_inputs.json").read_text())
    fixtures = {k: v for k, v in fixtures.items() if not k.startswith("_")}
    refusals = json.loads((FIXTURES_DIR / "refusals.json").read_text())["refusals"]

    # Discovery gate: every discovered calculator must have a fixture.
    missing_fixtures = [u for u in calc_uris if u not in fixtures]
    missing_schema = [u for u in calc_uris if u not in schemas_by_uri]

    # Pin the fixture period override where supplied.
    for u, fx in fixtures.items():
        if fx.get("period_uri"):
            period_by_uri.setdefault(u, fx["period_uri"])
            if not period_by_uri.get(u):
                period_by_uri[u] = fx["period_uri"]

    rows = {}
    failures = []
    anchor_failures = []

    for cu in calc_uris:
        probes = {c: Probe(c).set("na", "not run") for c in COLUMNS}
        fx = fixtures.get(cu)
        schema = schemas_by_uri.get(cu, {}).get("schema", {})
        period = period_by_uri.get(cu)
        path = invoke_path(cu, period)

        if fx:
            body = fx["body"]
            pa = probe_a_valid(cu, path, body)
            probes["a"] = pa
            if pa.status == "pass":
                # anchors on the 200 body
                ok, msgs = check_anchors(cu, period, pa.response)
                if not ok:
                    anchor_failures.extend(msgs)
            probes["b"] = probe_b_repeat(path, body)
            probes["c"] = probe_c_halfcent(cu, path, body, schema, all_schemas)
            probes["d"] = probe_d_missing_required(path, body, schema)
            probes["e"] = probe_e_unknown_period(cu, body)
            probes["g"] = probe_g_mutex(cu, path, body, schema)
            probes["h"] = probe_h_unknown_field(path, body, schema)
        # (f) refusals handled below; (i) MCP handled below
        rows[cu] = probes

    # (f) refusals — attach to the refusal's calc_uri (first refusal per calc)
    for r in refusals:
        p = probe_f_refusal(r)
        cu = r["calc_uri"]
        if cu in rows:
            # keep the strictest (a fail dominates a pass) if multiple refusals
            existing = rows[cu]["f"]
            if existing.status != "fail":
                rows[cu]["f"] = p
                rows[cu].setdefault("_f_extra", [])
        if p.status == "fail":
            failures.append((cu, "f", p, r["name"]))

    # (i) MCP
    mcp_results, mcp_top, _ = run_mcp(calc_uris, fixtures, period_by_uri, {})
    for cu in calc_uris:
        st, det = mcp_results.get(cu, ("na", "not run"))
        pi = Probe("i").set(st, det)
        rows[cu]["i"] = pi

    # collect per-cell failures
    for cu in calc_uris:
        for col in COLUMNS:
            if col == "f":
                continue
            p = rows[cu][col]
            if p.status == "fail":
                failures.append((cu, col, p, ""))

    # ---- render summary ----
    lines = []
    lines.append("# Constellation contract suite")
    lines.append("")
    lines.append(f"Base URL: `{BASE_URL}`")
    lines.append(f"Discovered calculators: **{len(calc_uris)}**; modules: "
                 f"**{len(modules)}**; schemas matched via `x-calc-uri`: "
                 f"**{len(schemas_by_uri)}**")
    lines.append(f"MCP: initialize {'✓' if mcp_top.get('initialize') else '✗'}; "
                 f"tools/list count {mcp_top.get('tools_count')} "
                 f"({'✓ matches' if mcp_top.get('tools_count_matches') else '✗ mismatch'}); "
                 f"half-cent isError {'✓' if mcp_top.get('halfcent_isError') else '✗'}")
    lines.append("")
    if missing_schema:
        lines.append(f"**✗ discovered calculators with no x-calc-uri schema:** {', '.join(missing_schema)}")
    if missing_fixtures:
        lines.append(f"**✗ discovered calculators with no fixture:** {', '.join(missing_fixtures)}")
    lines.append("")
    lines.append("| calculator | " + " | ".join(f"({c})" for c in COLUMNS) + " |")
    lines.append("|---|" + "---|" * len(COLUMNS))
    na_d_list = []
    for cu in calc_uris:
        cells = []
        for col in COLUMNS:
            st = rows[cu][col].status
            cells.append(RESULT_SYMBOLS.get(st, "?"))
            if col == "d" and st == "na":
                na_d_list.append(cu)
        short = cu.replace("urn:sbrm:calculator:", "")
        lines.append(f"| `{short}` | " + " | ".join(cells) + " |")
    lines.append("")

    # columns legend
    lines.append("Columns: (a) valid call · (b) byte-identical repeat · (c) half-cent "
                 "→422 · (d) missing required →422 · (e) unknown period →404 · "
                 "(f) documented refusal →400 · (g) mutually-exclusive →422 · "
                 "(h) unknown field →422 · (i) MCP parity.")
    lines.append("")
    if na_d_list:
        lines.append("**(d) N/A — schema has no required fields:** "
                     + ", ".join(f"`{u.split(':')[-1]}`" for u in na_d_list))
        lines.append("")

    # anchors
    lines.append("## Independent anchors (step 4)")
    if anchor_failures:
        lines.append("**✗ anchor mismatches:**")
        for m in anchor_failures:
            lines.append(f"- {m}")
    else:
        lines.append("✓ all independent anchors held "
                     "(fbt 8603.71; div7a 13801.18 / 13615.68; depreciation "
                     "2000.00/8000.00/6000.00; hp 32531.91 / residual 0.05).")
    lines.append("")

    # failures section
    all_fail_cells = [(cu, col, p, extra) for (cu, col, p, extra) in failures]
    total_fail = len(all_fail_cells) + len(anchor_failures) + len(missing_fixtures) + len(missing_schema)
    if all_fail_cells:
        lines.append("## Failures")
        for cu, col, p, extra in all_fail_cells:
            short = cu.replace("urn:sbrm:calculator:", "")
            lines.append(f"### ✗ `{short}` ({col}) {extra}".rstrip())
            lines.append(f"- {p.detail}")
            if p.request is not None:
                lines.append("```json")
                lines.append("// request\n" + json.dumps(p.request, indent=2))
                lines.append("```")
            if p.response is not None:
                lines.append("```json")
                lines.append("// response\n" + json.dumps(p.response, indent=2)[:4000])
                lines.append("```")
        lines.append("")

    summary = "\n".join(lines)
    Path(args.summary).write_text(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as f:
            f.write(summary + "\n")
    print(summary)

    # overall MCP gates count as failures too
    mcp_fail = (not mcp_top.get("initialize")
                or not mcp_top.get("tools_count_matches")
                or not mcp_top.get("halfcent_isError"))
    if total_fail > 0 or mcp_fail:
        print(f"\nRESULT: FAIL — {total_fail} failing cell(s)"
              + ("; MCP top-level gate failed" if mcp_fail else ""),
              file=sys.stderr)
        sys.exit(1)
    print("\nRESULT: PASS — every calculator met the contract.", file=sys.stderr)


if __name__ == "__main__":
    main()
