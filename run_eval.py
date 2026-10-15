"""Runs coding tasks against Apple's on-device Foundation Model and grades them.

Usage:
    .venv/bin/python run_eval.py [--lang go] [--task ID] [--runs N]
                                 [--greedy | --temperature T]
                                 [--guardrails default|permissive]
                                 [--output plain|guided]
                                 [--retry-style full|annotated|fresh|diagnostic|patch] [--fixup]
                                 [--attempts N] [--edit-format full|full_merge|symbol]
                                 [--merge replace|additive] [--repair] [--wire]
                                 [--skill path/to/skill.md | --skill auto]...

Output modes: "plain" asks for the file as plain text and cleans it up.
"guided" uses a @fm.generable class with one content field. On SDK 0.2.1,
guided generation of a full source file runs away until the context
window overflows (found 2026-10-05), so plain is the default.

Retry styles (what attempts 2 and 3 see):
  full       previous attempt plus the raw tail of the test output (baseline)
  annotated  error summary first, then the previous attempt with the failing
             lines marked inline
  fresh      the original prompt again plus the error summary; the previous
             code is not shown, so it cannot be copied
  diagnostic fresh plus harness.diagnose: likely causes and the codebase
             facts to fix them (real signatures, usage examples, where names
             are defined, unregistered or dropped routes, broken tests)
  patch      the previous attempt plus summary and diagnosis; the model returns
             only the declarations to change, which are merged into the
             previous attempt so correct parts cannot be re-broken

Every attempt is also graded after running the language's fixer (goimports
for Go), recorded as fixup_status, and after harness.repair (brace
balancing, imports, unused variables), recorded as repair_status. --fixup
or --repair makes that version the one that gets graded and fed back, as a
real harness would do.

--wire finds handlers that nothing references, restores their original
route if the file had one, and otherwise asks the model a tiny guided
question for the route (a choice among routes the request names, when it
names any) and inserts the registration line.

Edit formats: "full" asks for the whole target file. "full_merge" asks for
the whole file but merges it into the existing one with tools/gomerge, so
declarations the model dropped are kept. "symbol" asks, for modify tasks
only, for just the declarations being added or changed and merges them.
New files are always written in full. --merge additive (the default) also
keeps existing lines in registration-style functions such as orderRoutes.
"""

import argparse
import asyncio
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import apple_fm_sdk as fm

from harness import (ROOT, WIRING, apply_edit, compile_errors, diagnose, fixup, generated_api, grade, load_tasks, merge_into,
                     read_fixture, repair, routes_function, summarize_failure, unwired_handlers, wire_handler)

MAX_ATTEMPTS = 3
GEN_TIMEOUT = 300  # seconds per generation
OUTPUT_RESERVE = 1500  # tokens kept free for the model's answer

LANG_NAMES = {"go": "Go", "python": "Python", "typescript": "TypeScript", "swift": "Swift", "rust": "Rust"}

INSTRUCTIONS = """You are an expert {lang} developer making a change to an existing codebase.
Follow the conventions of the code you are shown exactly: helpers, naming, error handling, and structure.
Only use functions, types, and constants that appear in the code you are shown or in the {lang} standard library.
Respond with the complete contents of the target file, exactly as it should be saved to disk.
Do not wrap it in markdown code fences and do not add any explanation."""


@fm.generable("The route a handler should be registered under")
class RouteChoice:
    # Regex guides raise UnsupportedGuideError on SDK 0.2.1, so the method is
    # an enumerated choice and the path is free text.
    method: str = fm.guide("HTTP method", anyOf=["GET", "POST", "PUT", "PATCH", "DELETE"])
    path: str = fm.guide("Path pattern starting with /, for example /orders/{id}")


ROUTE_QUESTION = """## Task
{instruction}

## Routes registered in {target}
{routes}

## Handler that is not registered yet
{handler_src}

Which route (HTTP method and path pattern) should {handler} be registered under?"""


async def ask_route(model, task, content, handler):
    """Asks, in a fresh session with guided generation, which route pattern
    an unwired handler belongs to. Returns the pattern or None."""
    w = harness_wiring(task)
    fn = routes_function(task, content)
    m = re.search(rf"^(?:func \(s \*Server\) |def ){handler}\(.*?(?=^\S)", content + "\nX", re.M | re.S)
    prompt = ROUTE_QUESTION.format(instruction=task["instruction"].strip(), target=task["target"],
                                   routes=fn[1].rstrip() if fn else "(none)", handler=handler,
                                   handler_src=(m.group(0).rstrip() if m else handler)[:1500])
    session = fm.LanguageModelSession(model=model)
    greedy = fm.GenerationOptions(sampling=fm.SamplingMode.greedy())
    # If the request names routes, the answer must be one of them.
    named = sorted({f"{m_} {p.rstrip('.,;:)')}".split("?")[0]
                    for m_, p in re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/\S+)", task["instruction"])})
    try:
        if named:
            schema = {"type": "object", "title": "Route", "x-order": ["pattern"], "additionalProperties": False,
                      "required": ["pattern"], "properties": {"pattern": {"type": "string", "enum": named}}}
            r = await asyncio.wait_for(session.respond(prompt, json_schema=schema, options=greedy), 60)
            return json.loads(r.to_json())["pattern"]
        r = await asyncio.wait_for(session.respond(prompt, generating=RouteChoice, options=greedy), 60)
        path = r.path.strip().split()[0] if r.path.strip() else ""
        return f"{r.method} {path}" if path.startswith("/") else None
    except Exception:
        return None


async def wire(model, task, content):
    """Registers every unwired handler in content. Returns (content, notes)."""
    notes = []
    if content is None or routes_function(task, content) is None:
        return content, notes
    # Routes the original file registered are restored as they were; only
    # handlers that did not exist before get the route question.
    original = read_fixture(task, task["target"]) or ""
    known = {h: p for p, h in ((r.group(1), r.group(2)) for r in WIRING[task["lang"]]["registered"].finditer(original))}
    for handler in unwired_handlers(task, content):
        if handler in known:
            content, note = wire_handler(task, content, handler, known[handler], repoint=False)
            if note:
                notes.append("restored " + note.split(" ", 1)[1])
            continue
        pattern = await ask_route(model, task, content, handler)
        if not pattern:
            notes.append(f"no route for {handler}")
            continue
        content, note = wire_handler(task, content, handler, pattern)
        if note:
            notes.append(note)
    return content, notes


@fm.generable("A single source file")
class SourceFile:
    content: str = fm.guide("The complete contents of the target file")


# ---------------------------------------------------------------- prompts


def harness_wiring(task):
    return WIRING.get(task["lang"])


def file_block(path, text):
    return f"=== {path} ===\n{text.rstrip()}\n=== end {path} ===\n"


def annotate(task, content, result):
    """Marks lines of the target that have compiler errors with a trailing comment."""
    marks = {}
    for f, n, msg in compile_errors(task, result.get("full_log", result["log_tail"])):
        if Path(f).name == task["target"]:
            marks.setdefault(n, []).append(msg)
    lines = content.rstrip("\n").split("\n")
    for n, msgs in marks.items():
        if 1 <= n <= len(lines):
            lines[n - 1] += "  // <-- ERROR: " + "; ".join(msgs)
    return "\n".join(lines)


PATCH_INSTRUCTION = (
    "Fix the problems above. Respond with only the complete top-level declarations (functions, "
    "types, or constants) in {target} that must change, plus an import block if you need new "
    "imports. Do not repeat declarations that are already correct; they are kept exactly as they are.\n"
)

SYMBOL_INSTRUCTION = (
    "Respond with only the top-level declarations you are adding or changing (complete "
    "functions, types, or constants), plus an import block if you need imports. Do not repeat "
    "declarations you are not changing; they are kept exactly as they are. To change an existing "
    "function, write out its complete new version.\n"
)


def build_prompt(task, context_paths, skill, previous=None, style="full", edit_format="full"):
    """Assembles the prompt. previous is (content, grade result) from the last
    attempt, or None for the first attempt."""
    parts = []
    if skill:
        parts.append(skill.rstrip() + "\n")
    parts.append(f"## Task\n{task['instruction'].strip()}\n")
    if context_paths:
        parts.append("## Existing code for reference\n")
        parts += [file_block(p, read_fixture(task, p)) for p in context_paths]
    current = read_fixture(task, task["target"])
    target = task["target"]

    if previous is None or style in ("fresh", "diagnostic"):
        if current is not None:
            parts.append(f"## Current contents of {target} (the file you are changing)\n")
            parts.append(file_block(target, current))
        if previous is not None:
            parts.append(f"## An earlier attempt at this task failed\n{summarize_failure(task, previous[1])}\n")
            if style == "diagnostic":
                diagnosis = diagnose(task, previous[0], previous[1])
                if diagnosis:
                    parts.append("## Diagnosis\n" + "\n".join(diagnosis) + "\n")
            parts.append("Write the file again, avoiding these problems.\n")
        if current is not None and edit_format == "symbol":
            parts.append(SYMBOL_INSTRUCTION)
        elif current is not None:
            parts.append(f"Respond with the full updated {target}, keeping all existing code that the task does not ask you to change.\n")
        else:
            parts.append(f"## Target\nRespond with the full contents of the new file {target}.\n")
        return "\n".join(parts)

    content, result = previous
    if style == "patch":
        parts.append(f"## Current version of {target} (your previous attempt)\n")
        parts.append(file_block(target, content))
        parts.append(f"## Problems with it\n{summarize_failure(task, result)}\n")
        diagnosis = diagnose(task, content, result)
        if diagnosis:
            parts.append("## Diagnosis\n" + "\n".join(diagnosis) + "\n")
        parts.append(PATCH_INSTRUCTION.format(target=target))
        return "\n".join(parts)
    if style == "annotated":
        parts.append(f"## Problems with your previous attempt\n{summarize_failure(task, result)}\n")
        parts.append(f"## Your previous attempt at {target} (errors marked with // <-- ERROR)\n")
        parts.append(file_block(target, annotate(task, content, result)))
        parts.append(f"Fix every problem listed above. Respond with the full corrected {target}, "
                     "without the ERROR markers.\n")
    else:  # full
        parts.append(f"## Your previous attempt at {target}\n")
        parts.append(file_block(target, content))
        parts.append(f"## Test output for that attempt\n{result['log_tail'].strip()}\n")
        parts.append(f"Fix the problems shown above and respond with the full corrected {target}.\n")
    return "\n".join(parts)


async def fit_prompt(model, task, skill, previous, style="full", edit_format="full"):
    """Builds the prompt, dropping context files from the end until it fits.
    Returns (prompt, tokens, context_paths_used)."""
    budget = model.context_size - OUTPUT_RESERVE
    instr_tokens = await model.token_count(instructions=INSTRUCTIONS.format(lang=LANG_NAMES[task["lang"]]))
    paths = list(task["context"])
    while True:
        prompt = build_prompt(task, paths, skill, previous, style, edit_format)
        tokens = await model.token_count(prompt) + instr_tokens
        if tokens <= budget or not paths:
            return prompt, tokens, paths
        paths.pop()


def clean_output(text):
    """Removes wrappers the model adds around the file: markdown code fences
    and the "=== path ===" delimiters used in the prompt, in any combination
    at the start or end. Returns (content, list of what was removed)."""
    lines = text.strip("\n").split("\n")
    removed = set()
    changed = True
    while changed and lines:
        changed = False
        for idx in (0, -1):
            line = lines[idx].strip() if lines else ""
            kind = None
            if line.startswith("```"):
                kind = "fence"
            elif line.startswith("=== ") and line.endswith(" ==="):
                kind = "delimiter"
            elif line == "":
                kind = "blank"
            if kind:
                lines.pop(idx)
                if kind != "blank":
                    removed.add(kind)
                changed = True
                break
    return "\n".join(lines) + "\n", sorted(removed)


# ---------------------------------------------------------------- model


async def generate(model, task, prompt, options, output_mode):
    """Single model call in a fresh session. Returns (content, error_type, error_msg)."""
    session = fm.LanguageModelSession(
        instructions=INSTRUCTIONS.format(lang=LANG_NAMES[task["lang"]]), model=model
    )
    try:
        if output_mode == "guided":
            result = await asyncio.wait_for(
                session.respond(prompt, generating=SourceFile, options=options), GEN_TIMEOUT
            )
            return result.content, None, None
        text = await asyncio.wait_for(session.respond(prompt, options=options), GEN_TIMEOUT)
        return text, None, None
    except asyncio.TimeoutError:
        return None, "GenerationTimeout", f"no response after {GEN_TIMEOUT}s"
    except fm.FoundationModelsError as e:
        return None, type(e).__name__, str(e)
    except Exception as e:  # keep the run going, but record what happened
        return None, type(e).__name__, str(e)


# ---------------------------------------------------------------- run


def environment(args, model):
    sw = subprocess.run(["sw_vers"], capture_output=True, text=True).stdout
    os_info = dict(line.split(":\t", 1) for line in sw.strip().splitlines() if ":\t" in line)
    return {
        "os": {k: v.strip() for k, v in os_info.items()},
        "machine": platform.machine(),
        "sdk_version": importlib.metadata.version("apple-fm-sdk"),
        "context_size": model.context_size,
        "sampling": "greedy" if args.greedy else "default",
        "temperature": args.temperature,
        "guardrails": args.guardrails,
        "output_mode": args.output,
        "skill": args.skill,
        "retry_style": args.retry_style,
        "fixup": args.fixup,
        "repair": args.repair,
        "wire": args.wire,
        "edit_format": args.edit_format,
        "merge": args.merge,
        "max_attempts": args.attempts,
    }


async def run_attempt(model, options, task, prompt_args, output_mode, use_fixup, edit_format="full",
                      merge="additive", use_repair=False, use_wire=False):
    """Generates and grades one attempt. prompt_args = (skill, previous, style).
    Returns (record, graded content, grade result); the result is None on a model error."""
    skill, previous, style = prompt_args
    if edit_format == "symbol" and style in ("full", "annotated"):  # diagnostic builds on fresh
        style = "fresh"  # the other styles show a previous full file, which does not apply
    prompt, prompt_tokens, ctx_used = await fit_prompt(model, task, skill, previous, style, edit_format)
    t0 = time.monotonic()
    raw, err_type, err_msg = await generate(model, task, prompt, options, output_mode)
    rec = {
        "type": "attempt", "task": task["id"], "lang": task["lang"], "tier": task["tier"],
        "kind": task["kind"], "retry_style": style, "edit_format": edit_format, "merge": merge, "prompt_tokens": prompt_tokens,
        "prompt_chars": len(prompt), "context_used": ctx_used,
        "gen_seconds": round(time.monotonic() - t0, 2), "prompt": prompt,
    }
    if raw is None:
        rec.update(status="model_error", error_type=err_type, error=err_msg, output=None, log_tail="")
        return rec, None, None

    text, removed = clean_output(raw)
    merge_fail = lambda err: {"status": "merge_fail", "log_tail": err, "full_log": err}
    if style == "patch" and previous is not None:
        # The reply holds only changed declarations: merge it into the
        # previous attempt, then treat the result as a whole file.
        patched, err = await asyncio.to_thread(merge_into, task, previous[0], text, merge)
        if patched is None:
            rec.update(status="merge_fail", raw_status="merge_fail", fixup_status="merge_fail",
                       repair_status="merge_fail", output=raw, cleanup=removed,
                       output_tokens=await model.token_count(raw), log_tail=err)
            return rec, previous[0], merge_fail(err)
        text, edit_format = patched, "full"

    # Raw: the output as the model wrote it (merged, for merge formats).
    content, merge_err = await asyncio.to_thread(apply_edit, task, text, edit_format, merge)
    if merge_err is None:
        raw_result = await asyncio.to_thread(grade, task, content)
        fixed = await asyncio.to_thread(fixup, task, content)
        fix_result = raw_result if fixed is None or fixed == content else await asyncio.to_thread(grade, task, fixed)
    else:
        raw_result = fix_result = merge_fail(merge_err)
        fixed = None

    # Repaired: mechanical repairs first, so output that did not parse can
    # still be merged and graded.
    repaired, notes = await asyncio.to_thread(repair, task, text, edit_format, merge)
    if repaired is None:
        rep_result = merge_fail(merge_err or "repaired output could not be merged")
    elif repaired == content:
        rep_result = raw_result
    else:
        rep_result = await asyncio.to_thread(grade, task, repaired)

    if use_repair and repaired is not None:
        graded, result = repaired, rep_result
    elif use_fixup and fixed is not None:
        graded, result = fixed, fix_result
    else:
        graded, result = (content if content is not None else text), raw_result

    # Wiring: register handlers the model wrote but never wired in.
    wiring, prewire_status = [], result["status"]
    if use_wire and result["status"] != "pass" and result["status"] != "merge_fail":
        wired, wiring = await wire(model, task, graded)
        if wired != graded:
            graded, result = wired, await asyncio.to_thread(grade, task, wired)
    rec.update(
        status=result["status"], raw_status=raw_result["status"], fixup_status=fix_result["status"],
        repair_status=rep_result["status"], repairs=notes, prewire_status=prewire_status, wiring=wiring,
        fixup_changed=fixed is not None and fixed != content,
        output=raw, cleanup=removed, output_tokens=await model.token_count(raw),
        log_tail=result["log_tail"], mutants=result.get("mutants"),
        merged=content if content is not None and content != text else None,
    )
    return rec, graded, result


async def run_task(model, options, task, run_idx, skill, args, log):
    """Returns (passed_at, fixup_passed_at): the attempt number that passed,
    graded as configured and after the fixer, or None."""
    previous = None
    passed_at = fixup_passed_at = None
    for attempt in range(1, args.attempts + 1):
        style = args.retry_style if attempt > 1 else "first"
        rec, content, result = await run_attempt(
            model, options, task, (skill, previous, style), args.output, args.fixup, args.edit_format, args.merge, args.repair,
            args.wire)
        rec.update(run=run_idx, attempt=attempt)
        log(rec)
        if result is None:
            print(f"  attempt {attempt}: model_error {rec['error_type']} ({rec['prompt_tokens']} prompt tokens)")
            # Retrying after a model error rarely helps, except for a timeout.
            if rec["error_type"] != "GenerationTimeout":
                break
            continue
        fx = "" if rec["fixup_status"] == rec["raw_status"] else f"  [after fixer: {rec['fixup_status']}]"
        print(f"  attempt {attempt}: {rec['status']}{fx}  ({rec['prompt_tokens']} in, {rec['output_tokens']} out, {rec['gen_seconds']}s)")
        if fixup_passed_at is None and rec["fixup_status"] == "pass":
            fixup_passed_at = attempt
        if rec["status"] == "pass":
            passed_at = attempt
            break
        previous = (content, result)
    return passed_at, fixup_passed_at


def summarize(outcomes, fixup_used):
    """outcomes: list of (lang, task_id, passed_at, fixup_passed_at)."""
    by_lang = defaultdict(list)
    for lang, _, p, fp in outcomes:
        by_lang[lang].append((p, fp))
    graded_as = "with fixer or repair" if fixup_used else "raw"
    print(f"\n=== Summary (graded {graded_as}) ===")
    for lang, results in by_lang.items():
        n = len(results)
        p1 = sum(1 for p, _ in results if p == 1)
        pf = sum(1 for p, _ in results if p is not None)
        print(f"{lang}: pass@1 {p1}/{n} ({p1 / n:.0%})   pass-with-feedback {pf}/{n} ({pf / n:.0%})")
        if not fixup_used:
            f1 = sum(1 for _, fp in results if fp == 1)
            print(f"{lang}: pass@1 after fixer {f1}/{n} ({f1 / n:.0%})")
    print("\nPer task:")
    per_task = defaultdict(list)
    for _, tid, p, _ in outcomes:
        per_task[tid].append("fail" if p is None else f"pass@{p}")
    for tid, rs in per_task.items():
        print(f"  {tid:28s} {' '.join(rs)}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang")
    ap.add_argument("--task")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--greedy", action="store_true")
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--guardrails", choices=["default", "permissive"], default="default")
    ap.add_argument("--output", choices=["plain", "guided"], default="plain")
    ap.add_argument("--retry-style", choices=["full", "annotated", "fresh", "diagnostic", "patch"], default="fresh")
    ap.add_argument("--fixup", action="store_true")
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--wire", action="store_true", help="register handlers the model wrote but did not wire in")
    ap.add_argument("--edit-format", choices=["full", "full_merge", "symbol"], default="full")
    ap.add_argument("--merge", choices=["replace", "additive"], default="additive")
    ap.add_argument("--attempts", type=int, default=MAX_ATTEMPTS, help="max attempts per task (1 = no retries)")
    ap.add_argument("--skill", action="append", default=[],
                    help="skill file to prepend, or 'auto' for a generated API reference; repeatable")
    args = ap.parse_args()

    guardrails = (fm.SystemLanguageModelGuardrails.PERMISSIVE_CONTENT_TRANSFORMATIONS
                  if args.guardrails == "permissive" else fm.SystemLanguageModelGuardrails.DEFAULT)
    model = fm.SystemLanguageModel(guardrails=guardrails)
    available, reason = model.is_available()
    if not available:
        sys.exit(f"Model not available: {reason}")

    options = fm.GenerationOptions(
        sampling=fm.SamplingMode.greedy() if args.greedy else None,
        temperature=args.temperature,
    )
    static_skills = [Path(p).read_text() for p in args.skill if p != "auto"]
    tasks = load_tasks(args.lang, args.task)
    if not tasks:
        sys.exit("No tasks matched.")

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    with open(out_path, "w") as f:
        def log(rec):
            f.write(json.dumps(rec) + "\n")
            f.flush()

        env = environment(args, model)
        log({"type": "run", "started": datetime.now().isoformat(), "tasks": [t["id"] for t in tasks],
             "runs": args.runs, **env})
        print(f"Logging to {out_path.relative_to(ROOT)}  (sampling={env['sampling']}, output={args.output}, retry={args.retry_style}, fixup={args.fixup}, edit={args.edit_format})")

        outcomes = []
        for run_idx in range(1, args.runs + 1):
            for task in tasks:
                print(f"[run {run_idx}/{args.runs}] {task['id']}")
                parts = ([generated_api(task)] if "auto" in args.skill else []) + static_skills
                task_skill = "\n".join(parts) or None
                passed_at, fixup_passed_at = await run_task(model, options, task, run_idx, task_skill, args, log)
                log({"type": "task", "task": task["id"], "lang": task["lang"], "run": run_idx,
                     "passed_at": passed_at, "fixup_passed_at": fixup_passed_at})
                outcomes.append((task["lang"], task["id"], passed_at, fixup_passed_at))

    summarize(outcomes, args.fixup or args.repair)


if __name__ == "__main__":
    asyncio.run(main())
