"""Edit recipes: the model fills in a form, the harness writes the code.

Each recipe is one common kind of edit with a code template in the
fixture's conventions. The model answers two guided questions: which recipe
fits the request (or none), then the recipe's slots. Every slot that names
code is an enum built from the codebase, so it can only name things that
exist. The harness checks the slots, renders the template, and inserts it.

The harness then describes the filled-in edit in plain English and asks a
yes/no question: does this match the request? Tasks routed to none, edits
that cannot be applied, and edits not confirmed fall back to the best full-file config
(results/20261005-203213.jsonl regraded with repair + wire), so the
combined score compares directly with it.

Go only. Usage: .venv/bin/python recipes.py [--runs 3] [--task ID] [--greedy]
       [--heldout --fallback results/<best config run on the held-out tasks>.jsonl]
"""

import argparse
import asyncio
import json
import re
import time
from datetime import datetime

import apple_fm_sdk as fm

from harness import ROOT, fixture_dir, grade, load_tasks, read_fixture, repair

# ---------------------------------------------------------------- codebase facts


def func_body(src, name):
    """(start, end) line indexes of top-level func name, or None."""
    lines = src.splitlines()
    head = re.compile(rf"^func (\([^)]*\) )?{name}\(")
    start = next((i for i, l in enumerate(lines) if head.match(l)), None)
    if start is None:
        return None
    end = next(j for j in range(start, len(lines)) if lines[j] == "}")
    return start, end


def facts(task):
    """Names the recipes can offer, read from the fixture with regexes."""
    files = {p.name: p.read_text() for p in sorted(fixture_dir(task).glob("*.go")) if not p.name.endswith("_test.go")}
    structs = {}
    for src in files.values():
        for m in re.finditer(r"^type (\w+) struct \{\n(.*?)^\}", src, re.M | re.S):
            structs[m.group(1)] = dict(re.findall(r"^\t(\w+)\s+([\w\[\]\*\.]+)", m.group(2), re.M))
    stores = {}  # store type -> (item type, file, Server field)
    server_fields = {t: f for f, t in re.findall(r"^\t(\w+)\s+\*(\w+Store)$", files["server.go"], re.M)}
    for name, src in files.items():
        for st, item in re.findall(r"^type (\w+Store) struct \{.*?items\s+map\[string\](\w+)", src, re.M | re.S):
            stores[st] = (item, name, server_fields.get(st))
    codes = dict(re.findall(r"^\t(code\w+)\s+=\s+\"(\w+)\"", files["respond.go"], re.M))
    routes = {r for src in files.values() for r in re.findall(r'mux\.HandleFunc\("([A-Z]+ [^"]+)"', src)}
    target = read_fixture(task, task["target"]) or ""
    handlers = re.findall(r"^func \(s \*Server\) (handle\w+)\(", target, re.M)
    list_handlers, create_handlers = {}, {}
    lines = target.splitlines()
    for h in handlers:
        a, b = func_body(target, h)
        body = "\n".join(lines[a:b + 1])
        if m := re.search(r"s\.(\w+)\.List\(\)", body):
            store = next(st for st, v in stores.items() if v[2] == m.group(1))
            list_handlers[h] = store
        if (m := re.search(r"var req (\w+)", body)) and "decodeBody(r, &req)" in body:
            create_handlers[h] = m.group(1)
    return {"structs": structs, "stores": stores, "codes": codes, "routes": routes, "list_handlers": list_handlers,
            "create_handlers": create_handlers}


# ---------------------------------------------------------------- checks against the request
# Slots must agree with what the request states. These checks read only the
# request text and the codebase, never the hidden tests.


def mentions(instruction, value):
    return re.search(rf"(?<![\w]){re.escape(value)}(?![\w])", instruction, re.I) is not None


def named_routes(instruction):
    return {f"{m} {p.rstrip('.,;:)')}".split("?")[0]
            for m, p in re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/\S+)", instruction)}


def code_choices(task, f):
    """Error code constants, narrowed to the ones the request names if it names any."""
    named = [c for c, v in f["codes"].items() if mentions(task["instruction"], v)]
    return named or list(f["codes"])


def require_mentioned(task, value, what):
    if not mentions(task["instruction"], value):
        raise RecipeError(f"{what} {value!r} is not in the request")


def clean_param(value):
    return value.strip().lstrip("?").rstrip("=").strip()


def struct_text(f, name):
    return f"type {name} struct {{ " + "; ".join(f"{k} {v}" for k, v in f["structs"][name].items()) + " }"


def enum(values):
    return {"type": "string", "enum": sorted(set(values))}


def obj(title, props):
    return {"type": "object", "title": title, "additionalProperties": False, "x-order": list(props),
            "required": list(props), "properties": props}


class RecipeError(Exception):
    """The slots do not describe a valid edit."""


def go_literal(value, typ):
    if typ == "string":
        return json.dumps(value)
    if not re.fullmatch(r"-?\d+", value.strip()):
        raise RecipeError(f"{value!r} is not a number for a {typ} field")
    return value.strip()


def insert_lines(content, at, new_lines):
    lines = content.splitlines()
    return "\n".join(lines[:at] + new_lines + lines[at:]) + "\n"


# ---------------------------------------------------------------- recipes


class StoreFilterMethod:
    name = "store_filter_method"
    summary = "Add a method to a store that returns the items whose field equals a given value, sorted by ID."

    def applies(self, task, f):
        return any(v[1] == task["target"] for v in f["stores"].values())

    def schema(self, task, f):
        stores = [st for st, v in f["stores"].items() if v[1] == task["target"]]
        fields = [f"{f['stores'][st][0]}.{k}" for st in stores for k in f["structs"][f["stores"][st][0]]]
        return obj("StoreFilterMethod", {
            "store": enum(stores),
            "method": {"type": "string", "description": "name of the new method, e.g. ListByX"},
            "param": {"type": "string", "description": "name of the method's parameter"},
            "field": enum(fields),
        })

    def context(self, task, f):
        stores = [st for st, v in f["stores"].items() if v[1] == task["target"]]
        return "\n".join(struct_text(f, f["stores"][st][0]) for st in stores)

    def apply(self, task, f, s, content):
        store = s["store"]
        item = f["stores"][store][0]
        typ, field = s["field"].split(".")
        if typ != item:
            raise RecipeError(f"{s['field']} is not a field of {item}")
        if f["structs"][item][field] != "string":
            raise RecipeError(f"{s['field']} is not a string")
        method, param = s["method"].strip(), s["param"].strip()
        if not re.fullmatch(r"[A-Z]\w*", method) or not re.fullmatch(r"[a-z]\w*", param):
            raise RecipeError(f"bad names {method!r} {param!r}")
        require_mentioned(task, method, "method")
        # A signature spelled out in the request must match the one this recipe writes.
        if m := re.search(rf"\b{method}\(([^)]*)\)\s*(\([^)]*\)|[\w\[\]\*]+)?", task["instruction"]):
            params, ret = m.group(1).split(","), (m.group(2) or "").strip()
            if len(params) != 1 or not params[0].strip().endswith("string"):
                raise RecipeError(f"request asks for {method}({m.group(1)})")
            if ret and ret != f"[]{item}":
                raise RecipeError(f"request asks {method} to return {ret}")
        code = f"""
// {method} returns the {item.lower()}s whose {field} is {param}, sorted by ID.
func (st *{store}) {method}({param} string) []{item} {{
	st.mu.RLock()
	defer st.mu.RUnlock()
	out := []{item}{{}}
	for _, it := range st.items {{
		if it.{field} == {param} {{
			out = append(out, it)
		}}
	}}
	slices.SortFunc(out, func(a, b {item}) int {{ return strings.Compare(a.ID, b.ID) }})
	return out
}}
"""
        return content.rstrip("\n") + "\n" + code

    def describe(self, s):
        item = s["field"].split(".")[0]
        return (f"Add a new method {s['store']}.{s['method']}({s['param']} string) that returns every {item} "
                f"whose {s['field'].split('.')[1]} equals {s['param']}, sorted by ID. Nothing else changes.")


class ListQueryFilter:
    name = "list_query_filter"
    changes_existing_endpoint = True
    summary = "Let an existing list endpoint filter its results by an optional query parameter."

    def applies(self, task, f):
        return bool(f["list_handlers"])

    def schema(self, task, f):
        items = {f["stores"][st][0] for st in f["list_handlers"].values()}
        return obj("ListQueryFilter", {
            "handler": enum(f["list_handlers"]),
            "param": {"type": "string", "description": "the query parameter name"},
            "field": enum(f"{t}.{k}" for t in items for k in f["structs"][t]),
            "match": {"type": "string", "enum": ["field_equals_param", "param_is_true_or_false"],
                      "description": "field_equals_param keeps items whose field equals the parameter value; "
                                     "param_is_true_or_false: the parameter is true or false and selects items "
                                     "for which a condition on the field holds, or does not hold"},
            "allowed_values": {"type": "array", "items": {"type": "string"},
                               "description": "for field_equals_param: the only accepted parameter values"},
            "condition_op": {"type": "string", "enum": [">", ">=", "==", "!=", "<", "<="],
                             "description": "for param_is_true_or_false: the condition that true selects"},
            "condition_value": {"type": "string", "description": "for param_is_true_or_false"},
            "invalid_error_code": enum(code_choices(task, f)),
        })

    def context(self, task, f):
        items = {f["stores"][st][0] for st in f["list_handlers"].values()}
        return "\n".join(struct_text(f, t) for t in sorted(items))

    def apply(self, task, f, s, content):
        handler = s["handler"]
        store = f["list_handlers"][handler]
        item, _, sfield = f["stores"][store]
        typ, field = s["field"].split(".")
        if typ != item:
            raise RecipeError(f"{s['field']} is not a field of {item}")
        ftype = f["structs"][item][field]
        param = clean_param(s["param"])
        if not re.fullmatch(r"\w+", param):
            raise RecipeError(f"bad param {param!r}")
        require_mentioned(task, param, "query parameter")
        code = s["invalid_error_code"]
        if code not in code_choices(task, f):
            raise RecipeError(f"{code} is not the error code the request names")
        if s["match"] == "field_equals_param":
            if ftype != "string":
                raise RecipeError(f"{s['field']} is not a string")
            allowed = [v.strip() for v in s["allowed_values"] if v.strip()]
            for v in allowed:
                require_mentioned(task, v, "allowed value")
            check = []
            if allowed:
                cond = " && ".join(f"v != {json.dumps(v)}" for v in allowed)
                check = [f"\tif {cond} {{",
                         f"\t\twriteError(w, http.StatusBadRequest, {code}, \"{param} must be one of {', '.join(allowed)}\")",
                         "\t\treturn", "\t}"]
            keep = f"it.{field} == v"
        else:
            require_mentioned(task, "true", "value")
            require_mentioned(task, "false", "value")
            check = ["\tif v != \"true\" && v != \"false\" {",
                     f"\t\twriteError(w, http.StatusBadRequest, {code}, \"{param} must be true or false\")",
                     "\t\treturn", "\t}", "\twant := v == \"true\""]
            keep = f"(it.{field} {s['condition_op']} {go_literal(s['condition_value'], ftype)}) == want"
        lines = content.splitlines()
        a, b = func_body(content, handler)
        call = f"s.{sfield}.List()"
        at = next(i for i in range(a, b) if call in lines[i])
        var = sfield if not re.search(rf"\b{sfield}\b", "\n".join(lines[a:b])) else "all"
        indent = re.match(r"\t*", lines[at]).group(0)
        block = [f"{var} := {call}", f"if v := r.URL.Query().Get(\"{param}\"); v != \"\" {{",
                 *check, f"\tfiltered := []{item}{{}}", f"\tfor _, it := range {var} {{", f"\t\tif {keep} {{",
                 "\t\t\tfiltered = append(filtered, it)", "\t\t}", "\t}", f"\t{var} = filtered", "}"]
        lines[at] = lines[at].replace(call, var)
        return insert_lines("\n".join(lines), at, [indent + l for l in block])

    def describe(self, s):
        item, field = s["field"].split(".")
        s = {**s, "param": clean_param(s["param"])}
        if s["match"] == "field_equals_param":
            allowed = [v for v in s["allowed_values"] if v.strip()]
            check = f" It must be one of {', '.join(allowed)}, otherwise respond 400 with {s['invalid_error_code']}." \
                if allowed else ""
            keep = f"only {item}s whose {field} equals the parameter value are returned"
        else:
            check = f" It must be true or false, otherwise respond 400 with {s['invalid_error_code']}."
            cond = f"{field} {s['condition_op']} {s['condition_value']}"
            keep = f"true returns only {item}s with {cond}, false returns only {item}s without it"
        return (f"In the existing list endpoint {s['handler']}, read an optional query parameter ?{s['param']}=."
                f"{check} When it is present, {keep}. Without the parameter the endpoint behaves as before. "
                "No new endpoint or route is added.")


class NormalizeRequestField:
    name = "normalize_request_field"
    changes_existing_endpoint = True
    summary = "Normalize a field of a request body (trim whitespace, change case) before it is validated and stored."
    TRANSFORMS = {"trim_space": "strings.TrimSpace", "lowercase": "strings.ToLower", "uppercase": "strings.ToUpper"}

    def applies(self, task, f):
        return bool(f["create_handlers"])

    def schema(self, task, f):
        return obj("NormalizeRequestField", {
            "handler": enum(f["create_handlers"]),
            "field": enum(f"{t}.{k}" for t in set(f["create_handlers"].values()) for k in f["structs"][t]),
            "transforms": {"type": "array", "items": {"type": "string", "enum": list(self.TRANSFORMS)},
                           "description": "applied in this order"},
        })

    def context(self, task, f):
        return "\n".join(struct_text(f, t) for t in sorted(set(f["create_handlers"].values())))

    def apply(self, task, f, s, content):
        handler = s["handler"]
        typ, field = s["field"].split(".")
        if typ != f["create_handlers"][handler]:
            raise RecipeError(f"{s['field']} is not decoded by {handler}")
        if f["structs"][typ][field] != "string":
            raise RecipeError(f"{s['field']} is not a string")
        if not s["transforms"]:
            raise RecipeError("no transforms")
        expr = f"req.{field}"
        for t in dict.fromkeys(s["transforms"]):
            expr = f"{self.TRANSFORMS[t]}({expr})"
        lines = content.splitlines()
        a, b = func_body(content, handler)
        dec = next(i for i in range(a, b) if "decodeBody(r, &req)" in lines[i])
        end = next(i for i in range(dec, b) if lines[i] == "\t}")
        return insert_lines(content, end + 1, [f"\treq.{field} = {expr}"])

    def describe(self, s):
        steps = " then ".join(t.replace("_", " ") for t in s["transforms"])
        return (f"In {s['handler']}, right after decoding the request body, normalize req.{s['field'].split('.')[1]} "
                f"({steps}) before it is validated and stored. Nothing else changes.")


RECIPES = [StoreFilterMethod(), ListQueryFilter(), NormalizeRequestField()]

# ---------------------------------------------------------------- model questions

INSTRUCTIONS = "You classify and describe code changes in a Go codebase. Answer only with the requested structure."

ROUTE_PROMPT = """## Change request
{instruction}

## Kinds of change
{kinds}

Which kind of change is this request? If none fits exactly, answer none."""

SLOT_PROMPT = """## Change request
{instruction}

## Relevant types
{context}

Describe this change ({summary}) by filling in every field. Use only what the request says."""

CONFIRM_PROMPT = """## Change request
{instruction}

## Proposed change
{description}

Does the proposed change do everything the change request asks for, and nothing else? Answer yes only if it
matches the request completely."""


async def ask(model, prompt, schema, options):
    session = fm.LanguageModelSession(instructions=INSTRUCTIONS, model=model)
    r = await asyncio.wait_for(session.respond(prompt, json_schema=schema, options=options), 120)
    return json.loads(r.to_json())


async def run_recipe(model, task, options, confirm=True):
    """Returns a record: route, slots, status, and the edited file."""
    f = facts(task)
    rec = {"route": "none", "slots": None, "error": None, "content": None}
    usable = [r for r in RECIPES if r.applies(task, f)]
    if new := named_routes(task["instruction"]) - f["routes"]:
        # The request adds an endpoint, so it is not a change to an existing one.
        usable = [r for r in usable if not getattr(r, "changes_existing_endpoint", False)]
        rec["skipped"] = f"request names new routes {sorted(new)}"
    if not usable:
        rec["error"] = "no recipe applies to this target"
        return rec
    kinds = "\n".join(f"- {r.name}: {r.summary}" for r in usable) + "\n- none: anything else"
    schema = obj("Route", {"kind": enum([r.name for r in usable] + ["none"])})
    rec["route"] = (await ask(model, ROUTE_PROMPT.format(instruction=task["instruction"].strip(), kinds=kinds),
                              schema, options))["kind"]
    if rec["route"] == "none":
        return rec
    recipe = next(r for r in usable if r.name == rec["route"])
    prompt = SLOT_PROMPT.format(instruction=task["instruction"].strip(), context=recipe.context(task, f),
                                summary=recipe.summary)
    rec["slots"] = await ask(model, prompt, recipe.schema(task, f), options)
    try:
        edited = recipe.apply(task, f, rec["slots"], read_fixture(task, task["target"]) or "")
        rec["description"] = recipe.describe(rec["slots"])
    except (RecipeError, StopIteration, KeyError, ValueError) as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        return rec
    if confirm:
        prompt = CONFIRM_PROMPT.format(instruction=task["instruction"].strip(), description=rec["description"])
        rec["confirmed"] = (await ask(model, prompt, obj("Verdict", {"answer": enum(["yes", "no"])}),
                                      options))["answer"]
        if rec["confirmed"] != "yes":
            rec["error"] = "not confirmed"
            return rec
    rec["content"], _ = repair(task, edited, "full")  # goimports
    return rec


# ---------------------------------------------------------------- runner


async def fallback_results(model, src):
    """(task, run) -> passed, for the best full-file config after repair + wire."""
    from retry_ab import load_seeds
    failed = {(s["task"]["id"], s["run"]) for s in await load_seeds(model, [src], None)}
    runs = {(r["task"], r["run"]) for r in map(json.loads, open(ROOT / src))
            if r["type"] == "attempt" and r["attempt"] == 1}
    return {k: k not in failed for k in runs}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--task")
    ap.add_argument("--greedy", action="store_true")
    ap.add_argument("--heldout", action="store_true", help="run the held-out tasks instead")
    ap.add_argument("--fallback", default="results/20261005-203213.jsonl",
                    help="run_eval results of the best full-file config on the same tasks")
    ap.add_argument("--no-confirm", action="store_true", help="skip the yes/no confirmation step")
    args = ap.parse_args()
    model = fm.SystemLanguageModel()
    ok, reason = model.is_available()
    if not ok:
        raise SystemExit(f"model unavailable: {reason}")
    options = fm.GenerationOptions(sampling=fm.SamplingMode.greedy()) if args.greedy else fm.GenerationOptions()
    tasks = [t for t in load_tasks("go", heldout=args.heldout) if t["tier"] != "test" and (not args.task or t["id"] == args.task)]
    print("regrading the fallback config...", flush=True)
    fallback = await fallback_results(model, args.fallback)
    out = ROOT / "results" / f"recipes-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    log = open(out, "w")
    log.write(json.dumps({"type": "run", "started": datetime.now().isoformat(), "runs": args.runs,
                          "tasks": [t["id"] for t in tasks], "sampling": "greedy" if args.greedy else "default",
                          "recipes": [r.name for r in RECIPES],
                          "confirm": not args.no_confirm, "fallback": args.fallback}) + "\n")
    rows = []
    for task in tasks:
        for run in range(1, args.runs + 1):
            t0 = time.monotonic()
            try:
                rec = await run_recipe(model, task, options, confirm=not args.no_confirm)
            except Exception as e:
                rec = {"route": "model_error", "slots": None, "error": f"{type(e).__name__}: {e}", "content": None}
            if rec["content"] is not None:
                result = grade(task, rec["content"])
                status, log_tail = result["status"], result["log_tail"]
            else:  # no recipe, or it could not be applied or was not confirmed: free generation
                status, log_tail = "fallback", rec["error"] or ""
            passed = fallback.get((task["id"], run), False) if status == "fallback" else status == "pass"
            rows.append((task["id"], rec["route"], status, passed, fallback.get((task["id"], run), False)))
            print(f"{task['id']:32s} run {run} {rec['route']:24s} {rec.get('confirmed', '-'):4s} "
                  f"{status:10s} pass={passed}  {rec['error'] or ''}", flush=True)
            log.write(json.dumps({"type": "attempt", "task": task["id"], "run": run, **rec, "status": status,
                                  "passed": passed, "fallback_passed": fallback.get((task["id"], run), False),
                                  "seconds": round(time.monotonic() - t0, 2), "log_tail": log_tail}) + "\n")
            log.flush()
    routed = [r for r in rows if r[2] != "fallback"]
    print(f"\nrouted to a recipe: {len(routed)}/{len(rows)}, passed {sum(r[3] for r in routed)}"
          f" (best config on the same runs: {sum(r[4] for r in routed)})")
    print(f"combined pass@1 on non-test tasks: {sum(r[3] for r in rows)}/{len(rows)}"
          f" (best config: {sum(r[4] for r in rows)}/{len(rows)})  ->  {out.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
