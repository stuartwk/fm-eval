"""Best-of-n with model-written checks.

For each task the model writes a few HTTP checks as guided JSON (request,
expected status, expected error code); the harness turns them into a Go
test file, so the model never writes test code. Then n candidates are
generated with the best full-file config (full_merge + auto + conventions +
repair + wire). Each candidate is scored without the hidden tests: it must
compile and keep the fixture's own tests passing, and among those the one
passing the most checks is picked. Only then are the hidden tests used, to
grade the pick.

Reported per task: the pick, the expected pass rate of one random
candidate (plain pass@1), and whether any candidate passed (the ceiling for
selection). Check accuracy is measured against the reference solution.

Usage: .venv/bin/python best_of_n.py [--n 5] [--runs 3] [--task ID] [--all] [--heldout]
"""

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import apple_fm_sdk as fm

from harness import ROOT, TEST_TIMEOUT, fixture_dir, generated_api, load_tasks, read_fixture
from run_eval import run_attempt

# Tasks the recipes do not cover, so they rely on free generation.
FALLBACK_TASKS = ["go-health-handler", "go-order-cancel", "go-order-create-stock-check", "go-order-get",
                  "go-product-store-adjust-stock", "go-products-paginate", "go-review-handlers",
                  "go-review-store-delete", "go-user-lookup-by-email", "go-user-orders-handler",
                  "go-user-store-update-name"]

CHECK_INSTRUCTIONS = "You write test cases for HTTP endpoints. Answer only with the requested structure."

CHECK_PROMPT = """## Change request
{instruction}

## Test server
Every check runs against a fresh server seeded with this data:
{seed}

Existing routes: {routes}
Success responses look like {{"data": ...}}. Error responses look like
{{"error": {{"code": "...", "message": "..."}}}} with these codes: {codes}.

## Your job
Write 3 to 6 checks that pass only if the change request is implemented
correctly. Each check is one HTTP request against the seeded server and the
status code (and, for errors, the error code) the response must have. Use
IDs and values from the seed data. body is a JSON string for POST requests
and empty otherwise. expect_error_code is none for successful responses."""


def seed_text():
    src = (ROOT / "fixtures" / "go" / "helpers_test.go").read_text()
    m = re.search(r"// newTestServer returns.*?:\n((?://.*\n)+)", src)
    return "\n".join(l.removeprefix("//").strip() for l in m.group(1).splitlines() if l.strip("/ "))


def check_schema(codes):
    item = {"type": "object", "title": "Check", "additionalProperties": False,
            "x-order": ["method", "path", "body", "expect_status", "expect_error_code"],
            "required": ["method", "path", "body", "expect_status", "expect_error_code"],
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "DELETE"]},
                "path": {"type": "string", "description": "path and query string, e.g. /users/usr_000001"},
                "body": {"type": "string"},
                "expect_status": {"type": "string", "enum": ["200", "201", "204", "400", "404", "409", "422"]},
                "expect_error_code": {"type": "string", "enum": ["none", *codes]},
            }}
    return {"type": "object", "title": "Checks", "additionalProperties": False, "x-order": ["checks"],
            "required": ["checks"], "properties": {"checks": {"type": "array", "items": item}}}


async def write_checks(model, task, options):
    respond = (ROOT / "fixtures" / "go" / "respond.go").read_text()
    codes = re.findall(r'^\tcode\w+\s+=\s+"(\w+)"', respond, re.M)
    routes = sorted({r for p in fixture_dir(task).glob("*.go")
                     for r in re.findall(r'mux\.HandleFunc\("([A-Z]+ [^"]+)"', p.read_text())})
    prompt = CHECK_PROMPT.format(instruction=task["instruction"].strip(), seed=seed_text(),
                                 routes=", ".join(routes), codes=", ".join(codes))
    session = fm.LanguageModelSession(instructions=CHECK_INSTRUCTIONS, model=model)
    r = await asyncio.wait_for(session.respond(prompt, json_schema=check_schema(codes), options=options), 180)
    checks = []
    for c in json.loads(r.to_json())["checks"]:
        path = quote(c["path"].strip(), safe="/?=&%_-.~")
        if path.startswith("/"):
            checks.append({**c, "path": path})
    return checks


def check_tests(checks):
    """Go test file with one test per check."""
    out = ["package shop", "", "import \"testing\"", ""]
    for i, c in enumerate(checks):
        body = json.dumps(c["body"] if c["method"] == "POST" else "")
        out += [f"func TestSelfCheck{i}(t *testing.T) {{",
                "\tdefer func() {", "\t\tif r := recover(); r != nil {", "\t\t\tt.Fatalf(\"panic: %v\", r)", "\t\t}",
                "\t}()",
                "\ts := newTestServer(t)",
                f"\trec := doRequest(t, s, {json.dumps(c['method'])}, {json.dumps(c['path'])}, {body})",
                f"\tif rec.Code != {c['expect_status']} {{",
                f"\t\tt.Fatalf(\"status = %d, want {c['expect_status']}\", rec.Code)", "\t}"]
        if c["expect_error_code"] != "none":
            out += [f"\tif got := errorCode(t, rec); got != {json.dumps(c['expect_error_code'])} {{",
                    f"\t\tt.Fatalf(\"error code = %q, want {c['expect_error_code']}\", got)", "\t}"]
        out += ["}", ""]
    return "\n".join(out)


def score(task, content, checks):
    """Selection score without hidden tests: None if the candidate does not
    compile or breaks an existing test, else the number of checks passed."""
    with tempfile.TemporaryDirectory(prefix="fmeval-bon-") as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(fixture_dir(task), work)
        (work / task["target"]).write_text(content)
        (work / "zz_selfcheck_test.go").write_text(check_tests(checks))
        try:
            proc = subprocess.run(["go", "test", "-count=1", "-v", "./..."], cwd=work, capture_output=True,
                                  text=True, timeout=TEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            return None
    log = proc.stdout + proc.stderr
    if "[build failed]" in log or "[setup failed]" in log:
        return None
    failed = set(re.findall(r"--- FAIL: (\w+)", log))
    if any(not f.startswith("TestSelfCheck") for f in failed):
        return None
    return len(set(re.findall(r"--- PASS: (TestSelfCheck\d+)", log)))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--task")
    ap.add_argument("--all", action="store_true", help="all non-test tasks, not only those recipes miss")
    ap.add_argument("--heldout", action="store_true")
    args = ap.parse_args()
    model = fm.SystemLanguageModel()
    ok, reason = model.is_available()
    if not ok:
        raise SystemExit(f"model unavailable: {reason}")
    options = fm.GenerationOptions()
    tasks = [t for t in load_tasks("go", heldout=args.heldout) if t["tier"] != "test"
             and (args.all or args.heldout or t["id"] in FALLBACK_TASKS) and (not args.task or t["id"] == args.task)]
    conventions = (ROOT / "skills" / "go-shop-conventions.md").read_text()
    out = ROOT / "results" / f"bestofn-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    log = open(out, "w")
    log.write(json.dumps({"type": "run", "started": datetime.now().isoformat(), "n": args.n, "runs": args.runs,
                          "tasks": [t["id"] for t in tasks], "sampling": "default",
                          "candidates": "full_merge additive + auto + conventions + repair + wire"}) + "\n")
    totals = {"pick": 0, "random": 0.0, "any": 0, "rows": 0}
    for task in tasks:
        skill = generated_api(task) + "\n" + conventions
        solution = (ROOT / "solutions" / "go" / task["id"] / task["target"]).read_text()
        for run in range(1, args.runs + 1):
            try:
                checks = await write_checks(model, task, options)
            except Exception as e:
                checks = []
                print(f"  checks failed: {type(e).__name__}: {e}")
            check_acc = score(task, solution, checks) if checks else None
            cands = []
            for i in range(args.n):
                rec, content, result = await run_attempt(model, options, task, (skill, None, "first"), "plain",
                                                         False, "full_merge", "additive", True, True)
                hidden = result["status"] if result else "model_error"
                sc = score(task, content, checks) if content else None
                cands.append({"i": i, "hidden": hidden, "score": sc, "gen_seconds": rec["gen_seconds"],
                              "output": rec.get("output")})
            ok_cands = [c for c in cands if c["score"] is not None]
            pick = max(ok_cands, key=lambda c: c["score"]) if ok_cands else cands[0]  # first wins ties
            passed = [c["hidden"] == "pass" for c in cands]
            row = {"type": "task", "task": task["id"], "run": run, "checks": checks,
                   "checks_passed_by_solution": check_acc, "candidates": cands, "pick": pick["i"],
                   "pick_passed": pick["hidden"] == "pass", "random_rate": sum(passed) / len(passed),
                   "any_passed": any(passed)}
            log.write(json.dumps(row) + "\n")
            log.flush()
            totals["pick"] += row["pick_passed"]
            totals["random"] += row["random_rate"]
            totals["any"] += row["any_passed"]
            totals["rows"] += 1
            print(f"{task['id']:32s} run {run}  checks {len(checks)} (solution passes {check_acc})  "
                  f"scores {[c['score'] for c in cands]}  hidden {''.join('P' if p else '.' for p in passed)}  "
                  f"pick {pick['i']} -> {'pass' if row['pick_passed'] else 'fail'}", flush=True)
    n = totals["rows"]
    print(f"\npicked: {totals['pick']}/{n}   one random candidate: {totals['random']:.1f}/{n}   "
          f"any of {args.n}: {totals['any']}/{n}  ->  {out.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
