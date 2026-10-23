"""Tool-calling agent: the model edits the target through tools instead of
writing the file in one reply.

The prompt holds the instruction, the generated API sheet, the conventions
skill, and (for modify tasks) the current target file. The model has two
tools:

- lookup(name): the full source of a declaration in the codebase.
- write_code(code): Go declarations to add to the target or replace in it.
  The harness merges them into its working copy (additive merge), applies
  the mechanical repairs (braces, imports, unused variables), compiles, and
  runs the fixture's existing tests, then replies with the result: compiler
  errors with the offending source line, failing existing tests, or that
  everything passes.

State lives in the harness, not in the transcript: each write merges into
the working copy, so a correct declaration stays put while another is
fixed, and a context overflow ends the session without losing the work.
Hidden tests are never run during the session. Afterwards the working copy
is graded like the best config (with wire if it fails).

Usage: .venv/bin/python tool_agent.py [--runs 3] [--task ID] [--heldout]
"""

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import apple_fm_sdk as fm

from best_of_n import seed_text

from focused_ab import extract
from harness import (ROOT, TEST_TIMEOUT, balance_braces, blank_unused, compile_errors, compile_only, fixture_dir, fixup,
                     generated_api, grade, load_tasks, merge_into, read_fixture, run_tests, summarize_failure)
from run_eval import GEN_TIMEOUT, clean_output, wire

MAX_WRITES = 6
MAX_REQUESTS = 6

INSTRUCTIONS = """You are an expert Go developer making a change to an existing codebase (package shop).
You change the code only by calling write_code. Before you call a function or method from the
codebase, check its exact signature in the API reference, and call lookup to read an existing
declaration you want to imitate. After each write_code, read the result: if it reports errors, call
write_code again with corrected versions of the declarations involved. Once it compiles, call
try_request to send requests to your endpoint (or one that uses your change) and compare each
response with what the task asks for, including error cases; fix the code if a response is wrong.
When the code compiles, the existing tests pass, and the responses match the task, reply DONE."""


@fm.generable("Lookup arguments")
class LookupArgs:
    name: str = fm.guide("Name of a function, method, type, or constant in the codebase, e.g. handleGetUser")


@fm.generable("Code to write")
class WriteArgs:
    code: str = fm.guide("Complete Go top-level declarations (functions, methods, types, constants), plus an "
                         "import block if needed. A declaration with an existing name replaces it.")


def param_types(params):
    """Types of a Go parameter list, e.g. "id, name string" -> ["string", "string"]."""
    types, pending = [], 0
    for part in [p.strip() for p in params.split(",") if p.strip()]:
        bits = part.split(None, 1)
        if len(bits) == 1 and re.fullmatch(r"\w+", bits[0]):
            pending += 1  # a name whose type comes later
            continue
        typ = bits[-1]
        types += [typ] * (pending + 1)
        pending = 0
    return types


def has_method(src, recv, name, types, ret):
    for m in re.finditer(rf"func \(\w+ \*{recv}\) {name}\(([^()]*)\)\s*([^{{]*)\{{", src):
        if param_types(m.group(1)) == types and " ".join(m.group(2).split()) == ret:
            return True
    return False


def requirements(task):
    """Checks spelled out in the request: methods with their receiver,
    parameter and result types, and routes with the handler they point to.
    Returns [(description, check(src) -> bool)]."""
    text = " ".join(task["instruction"].split())
    reqs = []
    for m in re.finditer(r"\b([A-Za-z]\w*)\(([^()]*)\)\s*(\([^()]*\)|\[\]\w+|\*?\w+)?(?: method to (\w+))?", text):
        name, params, ret, recv = m.group(1), m.group(2), (m.group(3) or "").strip(), m.group(4)
        if not (recv or re.search(r"\bmethod $", text[:m.start()])):
            continue
        if not re.fullmatch(r"\(.*\)|\[\]\w+|\*?[A-Z]\w*|bool|int|string|error", ret):
            ret = ""  # an English word after the signature
        recv = recv or "Server"
        sig = f"{name}({params}) {ret}".strip()
        types = param_types(params)
        reqs.append((f"method {sig} on *{recv}, declared as func (... *{recv}) {sig}",
                     lambda src, recv=recv, name=name, types=types, ret=ret: has_method(src, recv, name, types, ret)))
    for method, path, handler in re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/\S+)\s*->\s*(\w+)", text):
        pat = rf'mux\.HandleFunc\("{method} {re.escape(path)}",\s*s\.{handler}\)'
        reqs.append((f'route registered as mux.HandleFunc("{method} {path}", s.{handler})',
                     lambda src, pat=pat: re.search(pat, src) is not None))
        reqs.append((f"handler func (s *Server) {handler}(w http.ResponseWriter, r *http.Request)",
                     lambda src, h=handler: has_method(src, "Server", h, ["http.ResponseWriter", "*http.Request"], "")))
    return reqs


@fm.generable("Request arguments")
class RequestArgs:
    method: str = fm.guide("HTTP method: GET, POST, or DELETE")
    path: str = fm.guide("Path and query string, e.g. /users/usr_000001")
    body: str = fm.guide("JSON request body for POST, empty otherwise")
    expect_status: int = fm.guide("The status code the task says this request must return")
    expect_ids: list[str] = fm.guide("For a successful response: exactly the IDs from the test data (like "
                                     "ord_000001) the task says the response must contain. Empty for errors.")
    expect_in_body: str = fm.guide("Optional: an exact JSON fragment the body must contain, like "
                                   "\"code\":\"not_found\" or \"total\":1; empty if none")


TRY_TEST = """package shop

import (
\t"net/http"
\t"net/http/httptest"
\t"strings"
\t"testing"
)

func TestZZTryRequest(t *testing.T) {
\ts := newTestServer(t)
\tmux := http.NewServeMux()
{routes}
\treq := httptest.NewRequest({method}, {path}, strings.NewReader({body}))
\trec := httptest.NewRecorder()
\tmux.ServeHTTP(rec, req)
\tt.Logf("ZZSTATUS %d", rec.Code)
\tt.Logf("ZZBODY %s", rec.Body.String())
}
"""


class Agent:
    def __init__(self, task):
        self.task = task
        self.working = read_fixture(task, task["target"]) or "package shop\n"
        self.status = "no_write"
        self.calls = []
        self.writes = 0
        self.reqs = requirements(task)
        self.requests = 0
        self.mismatches = 0
        self.state_path = None

    def save(self, **extra):
        """Writes the session state to disk after every tool call, so a crash
        of the SDK process loses nothing."""
        if self.state_path:
            state = {"working": self.working, "status": self.status, "calls": self.calls, "writes": self.writes,
                     "requests": self.requests, "mismatches": self.mismatches, **extra}
            Path(self.state_path).write_text(json.dumps(state))

    def files(self):
        return sorted(p.name for p in fixture_dir(self.task).glob("*.go") if not p.name.endswith("_test.go"))

    def lookup(self, name):
        name = name.strip().split(".")[-1].removeprefix("s.")
        hits = []
        for f in self.files():
            src = self.working if f == self.task["target"] else read_fixture(self.task, f)
            try:
                hits.append(f"// from {f}\n" + extract(src, name))
            except (StopIteration, ValueError):
                continue
        return "\n\n".join(hits[:2]) if hits else f"No declaration named {name} in the codebase."

    def write(self, code):
        if self.writes >= MAX_WRITES:
            return "Write limit reached. Reply with DONE."
        self.writes += 1
        text, _ = clean_output(code)
        text, _ = balance_braces(text)
        merged, err = merge_into(self.task, self.working, text, "additive")
        if merged is None:
            return f"Not saved: the code could not be parsed as Go declarations.\n{err}"
        for _ in range(3):
            merged = fixup(self.task, merged) or merged
            status, log = compile_only(self.task, merged)
            if status == "pass":
                break
            merged, n = blank_unused(merged, [e for e in compile_errors(self.task, log)
                                              if Path(e[0]).name == self.task["target"]])
            if not n:
                break
        self.working = merged
        if status != "pass":
            self.status = "build_fail"
            return "Saved, but the package does not compile:\n" + self.compile_report(log)
        with tempfile.TemporaryDirectory(prefix="fmeval-agent-") as tmp:
            work = Path(tmp) / "repo"
            shutil.copytree(fixture_dir(self.task), work)
            (work / self.task["target"]).write_text(merged)
            status, log = run_tests(self.task, work)
        self.status = status
        unmet = [d for d, ok in self.reqs if not ok(merged)]
        if status == "pass" and unmet:
            self.status = "unmet"
            return ("Saved. The package compiles and the existing tests pass, but the request asks for things "
                    "the code does not have yet:\n" + "\n".join(f"- {d}" for d in unmet))
        if status == "pass":
            return "Saved. The package compiles and the existing tests pass."
        return "Saved, but existing tests fail:\n" + summarize_failure(self.task, {"status": status, "log_tail": log,
                                                                                  "full_log": log})

    def try_request(self, method, path, body, expect_status=None, expect_in_body="", expect_ids=()):
        if self.requests >= MAX_REQUESTS:
            return "Request limit reached."
        self.requests += 1
        path = path.strip()
        if not path.startswith("/"):
            return "The path must start with /."
        if compile_only(self.task, self.working)[0] != "pass":
            return "The code does not compile yet; fix it with write_code first."
        # Every routes method, including new ones the model has not wired into Server.Routes.
        srcs = [read_fixture(self.task, f) for f in self.files() if f != self.task["target"]] + [self.working]
        routes = sorted({n for src in srcs for n in re.findall(r"func \(\w+ \*Server\) (\w+Routes)\(\w+ \*http\.ServeMux\)", src)})
        test = (TRY_TEST.replace("{routes}", "\n".join(f"\ts.{r}(mux)" for r in routes))
                .replace("{method}", json.dumps(method)).replace("{path}", json.dumps(path))
                .replace("{body}", json.dumps(body if method == "POST" else "")))
        with tempfile.TemporaryDirectory(prefix="fmeval-try-") as tmp:
            work = Path(tmp) / "repo"
            shutil.copytree(fixture_dir(self.task), work)
            (work / self.task["target"]).write_text(self.working)
            (work / "zz_try_test.go").write_text(test)
            proc = subprocess.run(["go", "test", "-count=1", "-v", "-run", "^TestZZTryRequest$", "."], cwd=work,
                                  capture_output=True, text=True, timeout=TEST_TIMEOUT)
        log = proc.stdout + proc.stderr
        if m := re.search(r"panic: (.*)", log):
            return f"{method} {path}: the handler panicked: {m.group(1)[:200]}"
        status = re.search(r"ZZSTATUS (\d+)", log)
        body_out = re.search(r"ZZBODY (.*)", log)
        if not status:
            return "The request could not be run:\n" + log[-500:]
        text = body_out.group(1).strip() if body_out else ""
        got = f"{method} {path} -> status {status.group(1)}\nbody: {text[:600]}"
        wrong = []
        if expect_status and int(status.group(1)) != expect_status:
            wrong.append(f"you expected status {expect_status} but got {status.group(1)}")
        expect_ids = sorted({i.strip() for i in expect_ids or () if re.fullmatch(r"[a-z]{3}_\d{6}", i.strip())})
        if expect_ids and text.startswith('{"data"'):
            got_ids = sorted(set(re.findall(r'"id":"([a-z]{3}_\d{6})"', text)))
            if got_ids != expect_ids:
                extra = [i for i in got_ids if i not in expect_ids]
                missing = [i for i in expect_ids if i not in got_ids]
                msg = f"you expected the IDs {', '.join(expect_ids)} but the response has {', '.join(got_ids) or 'none'}"
                for i in extra[:2]:  # show what the unexpected items look like
                    if m := re.search(r'\{"id":"' + i + r'"[^{}]*', text):
                        msg += f"; unexpected item: {m.group(0)[:160]}"
                if missing:
                    msg += f"; missing: {', '.join(missing)}"
                wrong.append(msg)
        # Free-text guesses are noise; only JSON-looking fragments are checked.
        if expect_in_body and '"' in expect_in_body and \
                "".join(expect_in_body.split()) not in "".join(text.split()):
            wrong.append(f"you expected the body to contain {expect_in_body} but it does not")
        if wrong:
            self.mismatches += 1
            return (got + "\nMISMATCH: " + "; ".join(wrong) + ". If your expectation follows the task, the code "
                    "is wrong: fix it with write_code and try again.")
        return got + "\nThis matches your expectation."

    def compile_report(self, log):
        lines = self.working.splitlines()
        out = []
        for f, n, msg in compile_errors(self.task, log)[:8]:
            if Path(f).name == self.task["target"] and 0 < n <= len(lines):
                out.append(f"- {msg}\n  in: {lines[n - 1].strip()}")
            else:
                out.append(f"- {Path(f).name} line {n}: {msg}")
        return "\n".join(out) or log[-800:]


def _value(args, key, typ, default):
    try:
        return args.value(typ, for_property=key)
    except Exception:
        return default


def tools_for(agent):
    class Lookup(fm.Tool):
        name = "lookup"
        description = "Returns the full Go source of a declaration in the codebase."

        @property
        def arguments_schema(self):
            return LookupArgs.generation_schema()

        async def call(self, args):
            name = args.value(str, for_property="name")
            out = await asyncio.to_thread(agent.lookup, name)
            agent.calls.append({"tool": "lookup", "name": name, "result": out})
            agent.save()
            return out

    class WriteCode(fm.Tool):
        name = "write_code"
        description = (f"Adds Go declarations to {agent.task['target']} or replaces existing ones with the same "
                       "name, then compiles and runs the existing tests and reports the result.")

        @property
        def arguments_schema(self):
            return WriteArgs.generation_schema()

        async def call(self, args):
            code = args.value(str, for_property="code")
            out = await asyncio.to_thread(agent.write, code)
            agent.calls.append({"tool": "write_code", "code": code, "result": out})
            agent.save()
            return out

    class TryRequest(fm.Tool):
        name = "try_request"
        description = ("Sends one HTTP request to a fresh server running the current code, seeded with the test "
                       "data, and returns the status code and response body.")

        @property
        def arguments_schema(self):
            return RequestArgs.generation_schema()

        async def call(self, args):
            method = args.value(str, for_property="method")
            path = args.value(str, for_property="path")
            opt = lambda key, typ, default: _value(args, key, typ, default)
            body, status = opt("body", str, ""), opt("expect_status", int, None)
            contains, ids = opt("expect_in_body", str, ""), opt("expect_ids", list, [])
            out = await asyncio.to_thread(agent.try_request, method, path, body, status, contains, ids)
            agent.calls.append({"tool": "try_request", "name": f"{method} {path} {body}".strip(),
                                "expect": [status, contains, ids], "result": out})
            agent.save()
            return out

    return [Lookup(), WriteCode(), TryRequest()]


def build_prompt(task, conventions, context=True, resume=None):
    parts = [f"## Task\n{task['instruction'].strip()}\n"]
    if context:
        for f in task["context"]:
            if f != task["target"]:
                parts.append(f"## Existing file {f}\n{read_fixture(task, f)}")
    parts += ["## API reference (package shop)\n" + generated_api(task), conventions,
              "## Test data (every try_request starts from a server seeded with this)\n" + seed_text()]
    reqs = requirements(task)
    if reqs:
        parts.append("## Checklist (write_code checks these)\n" + "\n".join(f"- {d}" for d, _ in reqs))
    current = read_fixture(task, task["target"])
    if resume and resume["working"] != (current or "package shop\n"):
        parts.append(f"## Current {task['target']} (your work so far)\n{resume['working']}")
        parts.append("## Where you left off\n" + resume["notes"] + "\nContinue by calling write_code or try_request.")
    elif current is None:
        parts.append(f"{task['target']} does not exist yet. Create it by calling write_code.")
    else:
        parts.append(f"## Current {task['target']}\n{current}\nEdit it by calling write_code.")
    return "\n".join(parts)


def unrouted(result):
    """A request no route matched (the model probed an endpoint that does
    not exist); it says nothing about the code under change."""
    return "body: 404 page not found" in result or "-> status 405" in result


def handoff_notes(state, tried):
    """A short summary for the next session: where the code stands, the
    request mismatches still open, and errors already run into. tried
    carries the errors across sessions and is updated in place."""
    calls = state.get("calls", [])
    writes = [c for c in calls if c["tool"] == "write_code"]
    lines = []
    if writes:
        lines.append("Last write_code result: " + "\n".join(writes[-1]["result"].splitlines()[:4]))
    latest = {c["name"]: c["result"] for c in calls if c["tool"] == "try_request"}
    mism = [f"- {r.splitlines()[0]}: {r.split('MISMATCH: ', 1)[1].split('. If your', 1)[0]}"
            for r in latest.values() if "MISMATCH" in r and not unrouted(r)]
    if mism:
        lines.append("Requests that did not match the task the last time you tried them:\n" + "\n".join(mism[:3]))
    for c in writes:
        if not c["result"].endswith("tests pass."):
            first = next((l for l in c["result"].splitlines()[1:] if l.startswith("- ")), "")
            if first and first not in tried:
                tried.append(first)
    if tried:
        lines.append("Errors earlier writes ran into (do not repeat them):\n" + "\n".join(tried[-4:]))
    return "\n".join(lines) or "No progress yet."


def session_done(state):
    """A session's work is finished when the code passes the harness checks
    and the last routed request the model tried matched its expectation."""
    requests = [c for c in state.get("calls", []) if c["tool"] == "try_request" and not unrouted(c["result"])]
    return state.get("status") == "pass" and not (requests and "MISMATCH" in requests[-1]["result"])


async def child(task_id, heldout, no_context, state_path, resume_path=None):
    """One agent session, run in its own process: the SDK segfaults now and
    then during tool-calling sessions."""
    task = next(t for t in load_tasks("go", heldout=heldout) if t["id"] == task_id)
    conventions = (ROOT / "skills" / "go-shop-conventions.md").read_text()
    agent = Agent(task)
    resume = json.loads(Path(resume_path).read_text()) if resume_path else None
    if resume:
        agent.working = resume["working"]
    agent.state_path = state_path
    agent.save(error="crashed before the first tool call")
    # Keep references to the model and tools: the session does not, and the
    # SDK segfaults when a tool it calls back into has been garbage collected.
    model, tools = fm.SystemLanguageModel(), tools_for(agent)
    session = fm.LanguageModelSession(instructions=INSTRUCTIONS, model=model, tools=tools)
    reply, err = None, None
    try:
        reply = await asyncio.wait_for(session.respond(build_prompt(task, conventions, not no_context, resume)),
                                       GEN_TIMEOUT)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]
    agent.save(reply=reply, error=err)


def run_session(task, args, resume=None):
    with tempfile.TemporaryDirectory(prefix="fmeval-agent-state-") as tmp:
        state_path = Path(tmp) / "state.json"
        cmd = [sys.executable, __file__, "--child", task["id"], "--state", str(state_path)]
        if resume:
            (Path(tmp) / "resume.json").write_text(json.dumps(resume))
            cmd += ["--resume", str(Path(tmp) / "resume.json")]
        cmd += ["--heldout"] * args.heldout + ["--no-context"] * args.no_context
        t0 = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=GEN_TIMEOUT + 300)
        secs = round(time.monotonic() - t0, 2)
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if proc.returncode != 0:
        state["error"] = f"crash (exit {proc.returncode}) after {len(state.get('calls', []))} tool calls"
    return state, secs


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--task")
    ap.add_argument("--heldout", action="store_true")
    ap.add_argument("--no-context", action="store_true", help="leave the task's context files out of the prompt")
    ap.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--state", help=argparse.SUPPRESS)
    ap.add_argument("--resume", help=argparse.SUPPRESS)
    ap.add_argument("--sessions", type=int, default=1,
                    help="restart with a handoff summary up to this many sessions per attempt")
    args = ap.parse_args()
    if args.child:
        return await child(args.child, args.heldout, args.no_context, args.state, args.resume)
    model = fm.SystemLanguageModel()
    ok, reason = model.is_available()
    if not ok:
        raise SystemExit(f"model unavailable: {reason}")
    conventions = (ROOT / "skills" / "go-shop-conventions.md").read_text()
    tasks = [t for t in load_tasks("go", heldout=args.heldout) if t["tier"] != "test"
             and (not args.task or t["id"] == args.task)]
    out = ROOT / "results" / f"agent-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    log = open(out, "w")
    log.write(json.dumps({"type": "run", "started": datetime.now().isoformat(), "runs": args.runs,
                          "tasks": [t["id"] for t in tasks], "sampling": "default", "max_writes": MAX_WRITES, "sessions": args.sessions,
                          "tools": ["lookup", "write_code", "try_request"],
                          "prompt": "instruction + " + ("" if args.no_context else "context + ")
                          + "auto + conventions + seed + checklist + target"})
              + "\n")
    passes = 0
    for task in tasks:
        prompt = build_prompt(task, conventions, not args.no_context)
        tokens = await model.token_count(prompt)
        for run in range(1, args.runs + 1):
            sessions, resume, wrote, secs, notes, tried = [], None, False, 0.0, [], []
            for _ in range(args.sessions):
                state, t = await asyncio.to_thread(run_session, task, args, resume)
                secs += t
                sessions.append(state)
                wrote = wrote or bool(state.get("writes"))
                if session_done(state) or "working" not in state:
                    break
                resume = {"working": state["working"],
                          "notes": handoff_notes(state, tried)}
                notes.append(resume["notes"])
            secs = round(secs, 2)
            calls = [c for st in sessions for c in st.get("calls", []) + [{"tool": "restart", "result": ""}]][:-1]
            err = "; ".join(st["error"] for st in sessions if st.get("error")) or None
            state = {**sessions[-1], "writes": sum(st.get("writes", 0) for st in sessions),
                     "requests": sum(st.get("requests", 0) for st in sessions),
                     "mismatches": sum(st.get("mismatches", 0) for st in sessions)}
            content = state["working"] if wrote else None
            result = grade(task, content) if content else {"status": "no_write", "log_tail": ""}
            wiring = []
            if content and result["status"] not in ("pass",):
                wired, wiring = await wire(model, task, content)
                if wired != content:
                    content, result = wired, grade(task, wired)
            passes += result["status"] == "pass"
            rec = {"type": "attempt", "task": task["id"], "run": run, "prompt_tokens": tokens, "gen_seconds": secs,
                   "status": result["status"], "session_status": state.get("status"), "writes": state.get("writes", 0),
                   "lookups": sum(c["tool"] == "lookup" for c in calls),
                   "restarts": len(sessions) - 1, "requests": state.get("requests", 0),
                   "mismatches": state.get("mismatches", 0),
                   "error": err, "reply": state.get("reply"), "calls": calls, "sessions": len(sessions),
                   "handoffs": notes, "wiring": wiring, "graded": content, "log_tail": result["log_tail"]}
            log.write(json.dumps(rec) + "\n")
            log.flush()
            trail = " ".join("|" if c["tool"] == "restart" else "L" if c["tool"] == "lookup" else ("R!" if "MISMATCH" in c["result"] else "R") if c["tool"] == "try_request" else "w+" if c["result"].endswith("tests pass.") else
                             "w?" if "asks for things" in c["result"] else "w-" for c in calls)
            print(f"{task['id']:32s} run {run} {tokens:5d} tok {secs:6.1f}s  {result['status']:10s} s{len(sessions)} "
                  f"[{trail}]{'  ERR ' + err[:60] if err else ''}", flush=True)
    n = len(tasks) * args.runs
    print(f"\npass@1 {passes}/{n}  ->  {out.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
