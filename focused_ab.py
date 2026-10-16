"""Focused-prompt experiment: does a short prompt holding only the
declarations a task touches (plus a few relevant ones) fix the logic
failures that full-file prompts produce?

For each task the prompt holds the instruction, the declarations being
changed, and a hand-picked set of related declarations, extracted by name
from the fixture. No API sheet, no whole files. For modify tasks the model
returns only the declarations it adds or changes, which are merged into the
target (symbol mode). Grading then uses the same repair, wire and grade as
the best config (full_merge + auto + conventions + repair + wire).

Usage: .venv/bin/python focused_ab.py [--runs 3] [--task ID]
"""

import argparse
import asyncio
import json
import re
import time
from datetime import datetime

import apple_fm_sdk as fm

from harness import ROOT, apply_edit, grade, load_tasks, read_fixture, repair
from run_eval import GEN_TIMEOUT, clean_output, wire

# task id -> (declarations being changed, related declarations), each as
# (fixture file, name). Methods are named by method name only.
FOCUS = {
    "go-orders-filter-status": (
        [("order_handlers.go", "handleListOrders")],
        [("order_store.go", "orderPending"), ("order_store.go", "Order"), ("order_store.go", "List"),
         ("request.go", "parsePage"), ("request.go", "paginate"),
         ("respond.go", "codeBadJSON"), ("respond.go", "writeError")],
    ),
    "go-products-filter-instock": (
        [("product_handlers.go", "handleListProducts")],
        [("product_store.go", "Product"), ("product_store.go", "List"),
         ("request.go", "parsePage"), ("respond.go", "codeBadJSON"), ("respond.go", "writeError")],
    ),
    "go-user-create-normalize-email": (
        [("user_handlers.go", "handleCreateUser")],
        [("user_handlers.go", "createUserRequest"), ("user_handlers.go", "validate"),
         ("user_store.go", "FindByEmail")],
    ),
    "go-order-store-list-by-user": (
        [],
        [("review_store.go", "ListByProduct"), ("order_store.go", "Order"), ("order_store.go", "OrderStore"),
         ("order_store.go", "List")],
    ),
    "go-health-handler": (
        [],
        [("server.go", "Server"), ("user_handlers.go", "userRoutes"), ("user_handlers.go", "handleGetUser"),
         ("respond.go", "writeJSON"), ("user_store.go", "List"), ("product_store.go", "List"),
         ("order_store.go", "List")],
    ),
}

INSTRUCTIONS = """You are an expert Go developer making a small change to an existing codebase.
Follow the conventions of the code you are shown exactly.
Only use functions, types, and constants that appear in the code you are shown or in the Go standard library.
Do not wrap your answer in markdown code fences and do not add any explanation."""

MODIFY_ASK = ("Respond with only the top-level declarations you are adding or changing (complete functions, "
              "types, or constants), plus an import block if you need new imports. Do not repeat declarations "
              "you are not changing. To change an existing function, write out its complete new version.")


def extract(src, name):
    """Source of the top-level declaration called name (with its doc comment),
    or of the const/var block that contains it."""
    lines = src.splitlines()
    head = re.compile(rf"^(func (\([^)]*\) )?{name}[\[(]|type {name}\b|(const|var) {name}\b)")
    start = next((i for i, l in enumerate(lines) if head.match(l)), None)
    if start is None:  # inside a const ( ... ) block
        member = re.compile(rf"^\t{name}\b")
        i = next(i for i, l in enumerate(lines) if member.match(l))
        start = max(j for j in range(i) if re.match(r"^(const|var) \($", lines[j]))
    end = start
    if lines[start].rstrip().endswith(("{", "(")):
        end = next(j for j in range(start + 1, len(lines)) if lines[j] in ("}", ")"))
    while start > 0 and lines[start - 1].startswith("//"):
        start -= 1
    return "\n".join(lines[start:end + 1])


def focused_prompt(task):
    change, related = FOCUS[task["id"]]
    block = lambda decls: "\n\n".join(f"// from {f}\n{extract(read_fixture(task, f), n)}" for f, n in decls)
    parts = [f"## Task\n{task['instruction'].strip()}\n",
             "## Relevant existing code (package shop)\n" + block(related) + "\n"]
    if task["kind"] == "modify":
        if change:
            parts.append(f"## Code you are changing, in {task['target']}\n" + block(change) + "\n")
        parts.append(MODIFY_ASK)
    else:
        parts.append(f"Respond with the full contents of the new file {task['target']} (package shop).")
    return "\n".join(parts)


async def generate(model, prompt):
    session = fm.LanguageModelSession(instructions=INSTRUCTIONS, model=model)
    try:
        return await asyncio.wait_for(session.respond(prompt), GEN_TIMEOUT), None
    except Exception as e:
        return None, type(e).__name__


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--task")
    args = ap.parse_args()
    model = fm.SystemLanguageModel()
    ok, reason = model.is_available()
    if not ok:
        raise SystemExit(f"model unavailable: {reason}")
    tasks = [t for t in load_tasks("go") if t["id"] in FOCUS and (not args.task or t["id"] == args.task)]
    out = ROOT / "results" / f"focused-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    log = open(out, "w")
    log.write(json.dumps({"type": "run", "started": datetime.now().isoformat(), "runs": args.runs,
                          "tasks": [t["id"] for t in tasks], "sampling": "default",
                          "edit_format": "symbol", "merge": "additive", "repair": True, "wire": True}) + "\n")
    passes = {}
    for task in tasks:
        prompt = focused_prompt(task)
        tokens = await model.token_count(prompt)
        for run in range(1, args.runs + 1):
            t0 = time.monotonic()
            raw, err = await generate(model, prompt)
            rec = {"type": "attempt", "task": task["id"], "run": run, "prompt_tokens": tokens,
                   "gen_seconds": round(time.monotonic() - t0, 2), "prompt": prompt, "output": raw}
            if raw is None:
                rec.update(status="model_error", error_type=err, log_tail="")
            else:
                text, removed = clean_output(raw)
                content, merge_err = apply_edit(task, text, "symbol", "additive")
                raw_status = "merge_fail" if merge_err else grade(task, content)["status"]
                repaired, notes = repair(task, text, "symbol", "additive")
                if repaired is None:
                    result, wiring = {"status": "merge_fail", "log_tail": merge_err or ""}, []
                else:
                    result = grade(task, repaired)
                    wiring = []
                    if result["status"] != "pass":
                        wired, wiring = await wire(model, task, repaired)
                        if wired != repaired:
                            repaired, result = wired, grade(task, wired)
                rec.update(status=result["status"], raw_status=raw_status, repairs=notes, wiring=wiring,
                           cleanup=removed, graded=repaired, log_tail=result["log_tail"])
            passes.setdefault(task["id"], []).append(rec["status"] == "pass")
            print(f"{task['id']:32s} run {run} {tokens:5d} tok {rec['gen_seconds']:5.1f}s  {rec['status']}"
                  f" (raw {rec.get('raw_status', '-')})", flush=True)
            log.write(json.dumps(rec) + "\n")
            log.flush()
    total = sum(sum(v) for v in passes.values())
    n = sum(len(v) for v in passes.values())
    print(f"\npass@1 {total}/{n}  ->  {out.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
