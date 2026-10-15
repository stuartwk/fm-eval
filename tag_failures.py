"""Tags every failed attempt in one or more results files with a failure
category, using heuristics over the compiler and test output, then prints
counts per run config and per tier.

Tags are heuristic. Spot-check them before relying on the counts; run with
--show TAG to print examples of one tag.

Usage: .venv/bin/python tag_failures.py results/A.jsonl [results/B.jsonl ...] [--show TAG]
"""

import argparse
import json
import re
from collections import Counter, defaultdict

from harness import compile_errors, fixture_dir, load_tasks


def fixture_names(task):
    """Top-level names defined anywhere in the task's fixture (Python)."""
    import ast
    names = set()
    for path in fixture_dir(task).glob("*.py"):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names

# Standard library packages the fixtures use, for telling import errors
# apart from hallucinated identifiers.
STDLIB = {"fmt", "strings", "strconv", "sort", "slices", "sync", "errors", "time", "json",
          "http", "httptest", "reflect", "testing", "os", "maps", "bytes", "io"}

TAG_ORDER = [
    "context overflow", "guardrail refusal", "model error (other)",
    "syntax", "copied context", "hallucinated API", "return-value misuse",
    "type error (other)", "import error",
    "broke existing code", "route not registered", "convention miss", "logic error",
    "weak tests", "wrong test expectations",
]


def tag(task, r):
    """Returns (primary tag, set of all tags) for a failed attempt record."""
    status = r["status"]
    if status == "model_error":
        et = r.get("error_type") or ""
        if "ContextWindow" in et:
            return "context overflow", {"context overflow"}
        if "Guardrail" in et or "Refusal" in et:
            return "guardrail refusal", {"guardrail refusal"}
        return "model error (other)", {"model error (other)"}
    if status == "merge_fail":
        return "syntax", {"syntax"}
    if status == "missed_mutant":
        return "weak tests", {"weak tests"}
    if status == "fail_on_correct":
        return "wrong test expectations", {"wrong test expectations"}

    log = r.get("log_tail") or ""
    tags = set()
    if task["lang"] == "python":
        return python_tag(task, status, log)
    if status == "build_fail":
        for _, _, msg in compile_errors(task, log):
            if re.search(r"syntax error|expected |not terminated|missing ','|illegal character", msg):
                tags.add("syntax")
            elif "redeclared in this block" in msg or "already declared" in msg:
                tags.add("copied context")
            elif "imported and not used" in msg:
                tags.add("import error")
            elif m := re.match(r"undefined: (\w+)$", msg):
                tags.add("import error" if m.group(1) in STDLIB else "hallucinated API")
            elif re.search(r"has no field or method|cannot call|undefined: \w+\.", msg):
                tags.add("hallucinated API")
            elif re.search(r"assignment mismatch|multiple-value|mismatched types \w+ and untyped nil", msg):
                tags.add("return-value misuse")
            else:
                tags.add("type error (other)")
        if not tags:
            tags.add("syntax")
    else:  # test_fail or timeout
        failing = set(re.findall(r"--- FAIL: (\w+)", log))
        hidden = {f for f in failing if f.startswith("TestHidden")}
        existing = failing - hidden
        if existing:
            # The fixture's own tests fail: existing behavior was removed or
            # broken (in full mode, usually deleted routes or handlers).
            tags.add("broke existing code")
        elif "404 page not found" in log or re.search(r"status = 404, want [^4]|status = 404, want 4[^0]|status = 404, want 400", log):
            # An unexpected 404 from the hidden test usually means the new
            # route was never registered (or another route caught the path).
            tags.add("route not registered")
        if re.search(r"want code \"\w+\" message|error code = |message \"", log) and not tags:
            tags.add("convention miss")
        if not tags:
            tags.add("logic error")
    primary = min(tags, key=TAG_ORDER.index)
    return primary, tags


PY_STDLIB_NAMES = STDLIB | {"dataclass", "dataclasses", "field", "partial", "threading", "re", "asdict"}


def python_tag(task, status, log):
    """Python version of tag(): errors surface as exceptions, either at
    import time (build_fail) or while a test runs (test_fail)."""
    tags = set()
    for _, _, msg in compile_errors(task, log):
        kind, _, detail = msg.partition(": ")
        if kind in ("SyntaxError", "IndentationError"):
            tags.add("syntax")
        elif kind == "NameError":
            name = re.search(r"name '(\w+)'", detail)
            known = PY_STDLIB_NAMES | set(fixture_names(task))
            tags.add("import error" if name and name.group(1) in known else "hallucinated API")
        elif kind == "ImportError" and (m := re.search(r"cannot import name '(\w+)' from '(\w+)'", detail)) \
                and m.group(2) + ".py" == task["target"]:
            # Another module imports a name the model removed from the target.
            tags.add("broke existing code")
        elif kind in ("AttributeError", "ImportError", "ModuleNotFoundError"):
            tags.add("hallucinated API")
        elif kind == "TypeError":
            tags.add("type error (other)")
    if status == "build_fail" and not tags:
        tags.add("syntax")
    if not tags:
        failing = set(re.findall(r"^(?:FAIL|ERROR): \w+ \((\w+)\.", log, re.M))
        if any(not m.startswith("test_hidden") for m in failing):
            tags.add("broke existing code")
        elif "404 page not found" in log or re.search(r"AssertionError: 404 != (?!404)", log):
            tags.add("route not registered")
        elif re.search(r"'code'|'message'|not found'", log):
            tags.add("convention miss")
        else:
            tags.add("logic error")
    return min(tags, key=TAG_ORDER.index), tags


def config_name(hdr):
    lang = ",".join(sorted({t.split("-")[0] for t in hdr.get("tasks", [])})) or "?"
    skills = hdr.get("skill") or []
    if isinstance(skills, str):
        skills = [skills]
    skill = "+".join(s.split("/")[-1].removesuffix(".md") for s in skills) or "no skill"
    fmt = hdr.get("edit_format", "full")
    merge = f"/{hdr.get('merge')}" if fmt != "full" and hdr.get("merge") else ""
    return f"{lang}: {fmt}{merge}/{skill}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--show", help="print examples of this tag")
    args = ap.parse_args()
    tasks = {t["id"]: t for t in load_tasks()}

    by_config = defaultdict(Counter)
    by_tier = defaultdict(Counter)
    totals = defaultdict(lambda: [0, 0])
    shown = 0
    for path in args.files:
        hdr = {}
        for line in open(path):
            r = json.loads(line)
            if r["type"] == "run":
                hdr = r
                continue
            if r["type"] != "attempt" or r.get("attempt", 1) != 1:
                continue
            cfg = config_name(hdr)
            totals[cfg][1] += 1
            if r["status"] == "pass":
                totals[cfg][0] += 1
                continue
            primary, all_tags = tag(tasks[r["task"]], r)
            by_config[cfg][primary] += 1
            by_tier[(cfg, r["tier"])][primary] += 1
            if args.show and primary == args.show and shown < 5:
                shown += 1
                print(f"--- {r['task']} run {r['run']} ({cfg}) all tags: {sorted(all_tags)}")
                print("\n".join(r["log_tail"].splitlines()[-8:]), "\n")

    for cfg, counts in by_config.items():
        p, n = totals[cfg]
        print(f"\n=== {cfg}: pass@1 {p}/{n} ({p / n:.0%}), {n - p} failures")
        for t in TAG_ORDER:
            if counts[t]:
                print(f"  {counts[t]:3d}  {t}")
        for tier in ["easy", "medium", "test"]:
            c = by_tier[(cfg, tier)]
            if c:
                print(f"    {tier:6s}: " + ", ".join(f"{t} {c[t]}" for t in TAG_ORDER if c[t]))


if __name__ == "__main__":
    main()
