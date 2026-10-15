"""Task loading and grading. Shared by run_eval.py and verify_tasks.py.

Nothing here talks to the model.
"""

import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent
TEST_TIMEOUT = 120  # seconds per test_cmd invocation
LOG_TAIL = 1500  # chars of test output kept for logs and retry prompts

# Markers that mean the code did not compile, as opposed to a test failing.
BUILD_FAIL_MARKERS = {
    "go": ["[build failed]", "[setup failed]"],
    # unittest reports modules that fail to import (SyntaxError, NameError at
    # import time, ImportError) as _FailedTest.
    "python": ["unittest.loader._FailedTest", "SyntaxError:", "IndentationError:"],
}

# Fixers a real harness would run on model output before testing. Each reads
# the file on stdin and writes the fixed file to stdout.
FIXERS = {
    "go": [shutil.which("goimports") or str(Path.home() / "go/bin/goimports")],
}

# Compiler error lines, e.g. "./order_handlers.go:76:8: undefined: s".
COMPILE_ERROR_RE = {
    "go": re.compile(r"^\.?/?([\w./-]+\.go):(\d+):(?:\d+:)?\s*(.*)$"),
}
PY_FRAME_RE = re.compile(r'File "([^"]+\.py)", line (\d+)')
PY_EXC_RE = re.compile(r"^(\w+(?:Error|Exception)|SyntaxError|IndentationError): (.*)$")
MAX_ERROR_LINES = 12

# Tools that merge a snippet of declarations into an existing file, for
# --edit-format symbol. Built on first use.
MERGERS = {
    "go": {"dir": ROOT / "tools" / "gomerge", "bin": "gomerge", "build": ["go", "build", "-o", "gomerge", "."],
           "glob": "*.go"},
}


def load_tasks(lang=None, task_id=None):
    tasks = []
    for path in sorted((ROOT / "tasks").glob("*/*.toml")):
        with open(path, "rb") as f:
            t = tomllib.load(f)
        if lang and t["lang"] != lang:
            continue
        if task_id and t["id"] != task_id:
            continue
        tasks.append(t)
    return tasks


def fixture_dir(task):
    return ROOT / "fixtures" / task["lang"]


def hidden_dir(task):
    return ROOT / "hidden" / task["lang"]


def read_fixture(task, rel):
    """Returns a fixture file's text, or None if it does not exist."""
    p = fixture_dir(task) / rel
    return p.read_text() if p.exists() else None


def run_tests(task, workdir, cmd=None):
    """Runs test_cmd (or cmd) in workdir. Returns (status, log) where status
    is one of pass, build_fail, test_fail, timeout."""
    try:
        proc = subprocess.run(
            cmd or task["test_cmd"], cwd=workdir, capture_output=True, text=True, timeout=TEST_TIMEOUT
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return "timeout", out
    log = proc.stdout + proc.stderr
    if proc.returncode == 0:
        return "pass", log
    if any(m in log for m in BUILD_FAIL_MARKERS.get(task["lang"], [])):
        return "build_fail", log
    return "test_fail", log


def fixup(task, content):
    """Runs the language's fixer (e.g. goimports) on content. Returns the
    fixed content, or None if there is no fixer or it failed (for example
    because the file does not parse)."""
    cmd = FIXERS.get(task["lang"])
    if not cmd or not Path(cmd[0]).exists():
        return None
    proc = subprocess.run(cmd, input=content, capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def python_merge(task, base, snippet, merge="additive"):
    """Python version of tools/gomerge: merges the top-level declarations in
    snippet into base. Same name replaces, new names append, imports are
    unioned, everything else in base is kept. Declarations that duplicate a
    name defined in another fixture module are dropped. With merge="additive",
    functions whose bodies are only call statements (e.g. user_routes) keep
    every base call and append new ones. Returns (merged, error)."""
    import ast
    try:
        btree, stree = ast.parse(base), ast.parse(snippet)
    except SyntaxError as e:
        return None, f"snippet: {e}"
    elsewhere = set(fixture_exports(task))
    blines, slines = base.split("\n"), snippet.split("\n")

    def decl_name(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return node.name
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
        return None

    def span(node):
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        return start, node.end_lineno

    def calls_only(node):
        return isinstance(node, ast.FunctionDef) and node.body and all(
            isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) for st in node.body)

    def src(lines, node):
        a, b = span(node)
        return "\n".join(lines[a - 1:b])

    base_decls = {decl_name(n): n for n in btree.body if decl_name(n)}
    replacements, appended = [], []
    for node in stree.body:
        name = decl_name(node)
        if not name or (name in elsewhere and name not in base_decls):
            continue
        text = src(slines, node)
        if name in base_decls:
            bnode = base_decls[name]
            if merge == "additive" and calls_only(bnode) and calls_only(node):
                # Keep every base call; a snippet call with the same callee and
                # first argument (e.g. the same route) replaces it, others append.
                def key(st):
                    c = st.value
                    return ast.unparse(c.func) + "|" + (ast.unparse(c.args[0]) if c.args else "")
                def text_of(st):
                    return "\n".join(slines[st.lineno - 1:st.end_lineno]).strip()
                snip = {key(st): st for st in node.body}
                indent = " " * bnode.body[0].col_offset
                lines_out = []
                for st in bnode.body:
                    k = key(st)
                    lines_out.append(text_of(snip.pop(k)) if k in snip and ast.unparse(snip[k]) != ast.unparse(st)
                                     else "\n".join(blines[st.lineno - 1:st.end_lineno]).strip())
                    snip.pop(k, None)
                lines_out += [text_of(st) for st in node.body if key(st) in snip]
                header = "\n".join(blines[span(bnode)[0] - 1:bnode.body[0].lineno - 1])
                text = header + "\n" + "\n".join(indent + l for l in lines_out)
            replacements.append((span(bnode), text))
        else:
            appended.append(text)

    # New imports go after the base's last import.
    have_imports = {ast.unparse(n) for n in btree.body if isinstance(n, (ast.Import, ast.ImportFrom))}
    new_imports = [ast.unparse(n) for n in stree.body
                   if isinstance(n, (ast.Import, ast.ImportFrom)) and ast.unparse(n) not in have_imports]
    last_import = max((n.end_lineno for n in btree.body if isinstance(n, (ast.Import, ast.ImportFrom))), default=0)

    out = list(blines)
    for (a, b), text in sorted(replacements, reverse=True):
        out[a - 1:b] = text.split("\n")
    if new_imports:
        # Replacements happen after imports, so last_import is still valid.
        out[last_import:last_import] = list(dict.fromkeys(new_imports))
    merged = "\n".join(out).rstrip("\n") + "\n"
    for text in appended:
        merged += "\n\n" + text + "\n"
    try:
        ast.parse(merged)
    except SyntaxError as e:
        return None, f"merged file: {e}"
    return merged, None


def apply_edit(task, text, edit_format, merge="additive"):
    """Turns cleaned model output into the full target file.

    full: the output is the file. symbol: for modify tasks, the output holds
    only added or changed declarations, merged into the existing target.
    full_merge: the model writes the whole file, but the harness merges it
    into the existing target like a snippet, so dropped declarations survive.
    merge="additive" also keeps existing lines of registration-style
    functions (see tools/gomerge). New files are always written in full.
    Declarations that duplicate a symbol defined in another package file are
    dropped by the merger. Returns (content, error); error is a message when
    the output could not be merged."""
    current = read_fixture(task, task["target"])
    if edit_format == "full" or current is None:
        return text, None
    return merge_into(task, current, text, merge)


def merge_into(task, base, snippet, merge="additive"):
    """Merges snippet's declarations into base (any version of the target,
    for example a previous attempt). Returns (content, error)."""
    if task["lang"] == "python":
        return python_merge(task, base, snippet, merge)
    if task["lang"] not in MERGERS:
        return snippet, None  # no merger for this language yet: treated as full
    m = MERGERS[task["lang"]]
    binary = m["dir"] / m["bin"]
    if not binary.exists():
        subprocess.run(m["build"], cwd=m["dir"], check=True)
    others = [str(p) for p in sorted(fixture_dir(task).glob(m["glob"])) if p.name != task["target"]]
    with tempfile.TemporaryDirectory() as tmp:
        base_path, snippet_path = Path(tmp) / task["target"], Path(tmp) / "snippet"
        base_path.write_text(base)
        snippet_path.write_text(snippet)
        flags = ["-additive"] if merge == "additive" else []
        proc = subprocess.run([str(binary), *flags, str(base_path), str(snippet_path), *others],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        return None, proc.stderr.strip()
    return proc.stdout, None


API_GENERATORS = {
    "go": {"dir": ROOT / "tools" / "goapi", "bin": "goapi", "build": ["go", "build", "-o", "goapi", "."]},
}


def generated_api(task):
    """Returns a generated API reference for the task's fixture (signatures,
    types, constants, doc comment first lines), skipping the target file."""
    g = API_GENERATORS[task["lang"]]
    binary = g["dir"] / g["bin"]
    if not binary.exists():
        subprocess.run(g["build"], cwd=g["dir"], check=True)
    proc = subprocess.run([str(binary), "-skip", task["target"], str(fixture_dir(task))],
                          capture_output=True, text=True, check=True)
    return proc.stdout


# ---------------------------------------------------------------- repair
#
# Mechanical repairs a harness can apply without the model: close braces the
# model forgot, fix imports, and blank out unused variables. They only use
# the fixture and the model's output, never the hidden tests.

GO_TOPLEVEL = re.compile(r"^(func|type|var|const)\b")


def balance_braces(text):
    """Closes braces left open before a new top-level Go declaration or at the
    end of the file. Skips strings, runes, and comments. Returns (text, n_added)."""
    lines = text.split("\n")
    out, depth, added = [], 0, 0
    in_block_comment = False
    for line in lines:
        if depth > 0 and not in_block_comment and GO_TOPLEVEL.match(line):
            # Insert the closing braces above any doc comment for this declaration.
            k = len(out)
            while k > 0 and out[k - 1].startswith("//"):
                k -= 1
            out[k:k] = ["}"] * depth
            added += depth
            depth = 0
        out.append(line)
        i, quote = 0, None
        while i < len(line):
            c = line[i]
            if in_block_comment:
                if line.startswith("*/", i):
                    in_block_comment = False
                    i += 1
            elif quote:
                if c == "\\" and quote != "`":
                    i += 1
                elif c == quote:
                    quote = None
            elif line.startswith("//", i):
                break
            elif line.startswith("/*", i):
                in_block_comment = True
                i += 1
            elif c in "\"'`":
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth = max(0, depth - 1)
            i += 1
        if quote == "`":
            quote = None  # raw strings can span lines; good enough for repair
    if depth > 0:
        while out and out[-1].strip() == "":
            out.pop()
        out += ["}"] * depth + [""]
        added += depth
    return "\n".join(out), added


UNUSED_RE = re.compile(r"declared and not used: (\w+)")


def blank_unused(content, errors):
    """Replaces unused variables reported by the compiler with _ on their line."""
    lines = content.split("\n")
    changed = 0
    for _, n, msg in errors:
        m = UNUSED_RE.search(msg)
        if not m or not (1 <= n <= len(lines)):
            continue
        name, line = m.group(1), lines[n - 1]
        new = re.sub(rf"\bfor {name}, ", "for _, ", line, count=1)
        new = re.sub(rf"\bfor (\w+), {name} :=", r"for \1, _ :=", new, count=1) if new == line else new
        if new == line:
            new = re.sub(rf"^(\s*){name} := ", r"\1_ = ", line, count=1)
        if new == line:
            new = re.sub(rf"\b{name}(\s*,\s*\w+\s*:=)", r"_\1", line, count=1)
        if new == line:
            new = re.sub(rf"(\w+\s*,\s*){name}(\s*:=)", r"\1_\2", line, count=1)
        if new != line:
            lines[n - 1] = new
            changed += 1
    return "\n".join(lines), changed


def compile_only(task, content):
    """Compiles the fixture with content as the target, without hidden tests.
    Returns (status, log); status is pass or build_fail."""
    with tempfile.TemporaryDirectory(prefix="fmeval-repair-") as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(fixture_dir(task), work)
        (work / task["target"]).write_text(content)
        proc = subprocess.run(["go", "test", "-count=1", "-run", "^$", "./..."], cwd=work,
                              capture_output=True, text=True, timeout=TEST_TIMEOUT)
    log = proc.stdout + proc.stderr
    return ("pass" if proc.returncode == 0 else "build_fail"), log


# Common standard-library names and where they come from, for the Python
# import fixer.
PY_STDLIB_IMPORTS = {
    "dataclass": "from dataclasses import dataclass", "field": "from dataclasses import field",
    "dataclasses": "import dataclasses", "partial": "from functools import partial",
    "json": "import json", "re": "import re", "threading": "import threading",
    "unittest": "import unittest",
}


def fixture_exports(task):
    """Maps each top-level name defined in a non-test fixture module (other
    than the target) to its module. Names defined in several modules are
    left out, since the right import would be ambiguous."""
    import ast
    owners = {}
    for path in sorted(fixture_dir(task).glob("*.py")):
        if path.name.startswith("test_") or path.name == task["target"]:
            continue
        for node in ast.parse(path.read_text()).body:
            names = []
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            for n in names:
                owners.setdefault(n, set()).add(path.stem)
    return {n: next(iter(m)) for n, m in owners.items() if len(m) == 1}


def python_fix_imports(task, text):
    """Adds imports for names the file uses but never binds, when the name
    is defined by exactly one fixture module or is a known stdlib name.
    Returns (text, names added). Leaves unparseable text unchanged."""
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text, []
    bound, used = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            (used if isinstance(node.ctx, ast.Load) else bound).add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    exports = fixture_exports(task)
    missing = sorted(n for n in used - bound if n in exports or n in PY_STDLIB_IMPORTS)
    if not missing:
        return text, []
    lines = [PY_STDLIB_IMPORTS[n] if n in PY_STDLIB_IMPORTS else f"from {exports[n]} import {n}" for n in missing]
    # Insert after the module docstring and existing imports.
    body = tree.body
    insert_at = 0
    for i, node in enumerate(body):
        if isinstance(node, (ast.Import, ast.ImportFrom)) or (
                i == 0 and isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant)):
            insert_at = node.end_lineno
    src = text.split("\n")
    src[insert_at:insert_at] = lines
    return "\n".join(src), missing


def repair(task, text, edit_format="full", merge="additive"):
    """Applies mechanical repairs to cleaned model output and returns
    (content, notes) where content is the full target file (or None if it
    could not be merged) and notes lists the repairs applied."""
    notes = []
    if task["lang"] == "python":
        text, added = python_fix_imports(task, text)
        if added:
            notes.append("imports:" + ",".join(added))
        content, err = apply_edit(task, text, edit_format, merge)
        return content, notes
    if task["lang"] != "go":
        content, err = apply_edit(task, text, edit_format, merge)
        return content, notes
    text, n = balance_braces(text)
    if n:
        notes.append(f"braces+{n}")
    content, err = apply_edit(task, text, edit_format, merge)
    if err is not None:
        return None, notes
    for _ in range(3):
        fixed = fixup(task, content)
        if fixed is not None and fixed != content:
            content = fixed
            if "imports" not in notes:
                notes.append("imports")
        status, log = compile_only(task, content)
        if status == "pass":
            break
        content, n = blank_unused(content, [e for e in compile_errors(task, log) if Path(e[0]).name == task["target"]])
        if not n:
            break
        notes.append(f"unused-{n}")
    return content, notes


def python_errors(log):
    """Returns [(file, line, "Type: message")] for each traceback in a unittest
    log, using the innermost frame in a fixture file (not the stdlib)."""
    out = []
    frame = None
    for line in log.splitlines():
        t = line.strip()
        m = PY_FRAME_RE.search(t)
        if m and "/lib/python" not in m.group(1):
            frame = (Path(m.group(1)).name, int(m.group(2)))
            continue
        e = PY_EXC_RE.match(t)
        if e and frame:
            item = (frame[0], frame[1], f"{e.group(1)}: {e.group(2)}")
            if item not in out:
                out.append(item)
            frame = None
    return out


# ---------------------------------------------------------------- wiring
#
# Small models write new handlers but often do not register them. The
# harness finds handlers nothing references, asks the model (separately, with
# a tiny guided-generation question) which route each belongs to, and inserts
# the registration line itself.

WIRING = {
    "go": {
        "handler": re.compile(r"^func \(s \*Server\) (handle\w+)\(", re.M),
        "routes": re.compile(r"^func \(s \*Server\) (\w+Routes)\(mux \*http\.ServeMux\) \{\n(.*?)^\}", re.M | re.S),
        "line": '\tmux.HandleFunc("{pattern}", s.{handler})',
        "registered": re.compile(r'mux\.HandleFunc\("([^"]+)", s\.(\w+)\)'),
    },
    "python": {
        "handler": re.compile(r"^def (handle_\w+)\(s, req\)", re.M),
        "routes": re.compile(r"^def (\w+_routes)\(s, router\):\n((?:[ \t]+.*\n?|\n)*)", re.M),
        "line": '    router.handle("{pattern}", partial({handler}, s))',
        "registered": re.compile(r'router\.handle\("([^"]+)", partial\((\w+), s\)\)'),
    },
}


def unwired_handlers(task, content):
    """Handler functions defined in content whose names appear nowhere else."""
    w = WIRING.get(task["lang"])
    if not w or content is None:
        return []
    out = []
    for m in w["handler"].finditer(content):
        name = m.group(1)
        if len(re.findall(rf"\b{name}\b", content)) == 1:
            out.append(name)
    return out


def routes_function(task, content):
    """Returns (name, body) of the routes function in content, or None."""
    m = WIRING[task["lang"]]["routes"].search(content)
    return (m.group(1), m.group(2)) if m else None


def wire_handler(task, content, handler, pattern, repoint=True):
    """Registers handler under pattern in the routes function. If pattern is
    already registered, that line is re-pointed to handler (unless repoint is
    False or the registered handler is one the original file used). Returns
    (content, note) or (content, None) when nothing was changed."""
    w = WIRING[task["lang"]]
    m = w["routes"].search(content)
    if not m:
        return content, None
    body = m.group(2)
    original = read_fixture(task, task["target"]) or ""
    for r in w["registered"].finditer(body):
        if r.group(1) == pattern:
            if not repoint or re.search(rf"\b{r.group(2)}\b", original):
                return content, None
            new_body = body.replace(r.group(0), r.group(0).replace(r.group(2), handler, 1), 1)
            return content[:m.start(2)] + new_body + content[m.end(2):], f"repointed {pattern} -> {handler}"
    line = w["line"].format(pattern=pattern, handler=handler)
    lines = body.rstrip("\n").split("\n")
    # Insert after the last registration line (or at the end of the body).
    idx = max((i for i, l in enumerate(lines) if w["registered"].search(l)), default=len(lines) - 1)
    lines.insert(idx + 1, line)
    new_body = "\n".join(lines) + "\n"
    if task["lang"] == "python" and body.endswith("\n\n"):
        new_body += "\n"
    return content[:m.start(2)] + new_body + content[m.end(2):], f"wired {pattern} -> {handler}"


def compile_errors(task, log):
    """Returns [(file, line, message)] for compiler errors in a test log. For
    Python, these are the import-time errors (and any other tracebacks)."""
    if task["lang"] == "python":
        return python_errors(log)
    pat = COMPILE_ERROR_RE[task["lang"]]
    out = []
    for line in log.splitlines():
        m = pat.match(line.strip())
        if m and (m.group(1), int(m.group(2)), m.group(3)) not in out:
            out.append((m.group(1), int(m.group(2)), m.group(3)))
    return out


def summarize_failure(task, result):
    """Turns a grade() result into a short, plain-language error summary for
    a retry prompt: compiler errors, failing assertions, or for test-writing
    tasks what went wrong with the tests."""
    status, log = result["status"], result.get("full_log", result["log_tail"])
    if status == "merge_fail":
        return f"Your response could not be parsed as {task['lang']} declarations:\n{log.strip()}"
    if status == "timeout":
        return "The tests did not finish within the time limit (possible infinite loop or deadlock)."
    if status == "build_fail":
        errs = compile_errors(task, log)[:MAX_ERROR_LINES]
        if errs:
            return "The code does not compile:\n" + "\n".join(f"- {f} line {n}: {msg}" for f, n, msg in errs)
        return "The code does not compile:\n" + log[-LOG_TAIL:]
    if status == "missed_mutant":
        replaced = ", ".join(sorted({m["replaces"] for m in task.get("mutants", [])}))
        return (f"Your tests all passed even when {replaced} was replaced by a deliberately broken "
                "version, so they miss a real bug. Make the assertions stricter.")
    if task["lang"] == "python":
        heads = [l.strip() for l in log.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
        errs = [f"- {f} line {n}: {msg}" for f, n, msg in python_errors(log)]
        head = ("Your tests fail against the correct implementation, so some expected values are wrong:"
                if status == "fail_on_correct" else "Some tests fail:")
        return head + "\n" + "\n".join((heads + errs)[:MAX_ERROR_LINES * 2] or [log[-LOG_TAIL:]])
    # test_fail or fail_on_correct: keep FAIL lines and the assertion lines under them.
    keep = []
    for line in log.splitlines():
        t = line.strip()
        if t.startswith("--- FAIL") or re.match(r"^[\w.-]+_test\.go:\d+:", t) or t.startswith("body:"):
            if t not in keep:
                keep.append(t)
    head = ("Your tests fail against the correct implementation, so some expected values are wrong:"
            if status == "fail_on_correct" else "Some tests fail:")
    return head + "\n" + "\n".join(keep[:MAX_ERROR_LINES * 2] or [log[-LOG_TAIL:]])


# ---------------------------------------------------------------- diagnosis
#
# Turns a failure into likely causes plus the codebase facts needed to fix
# them (real signatures, a real usage line, where a name is defined, which
# routes or existing tests broke). Used by the "diagnostic" retry style. It
# reads the fixture and the test output, never hidden test source.


def _signatures(task):
    """Returns {name: [signature lines]} and {type: [member signature lines]}
    for the fixture's non-test source."""
    import ast
    by_name, by_type = {}, {}
    if task["lang"] == "go":
        for path in sorted(fixture_dir(task).glob("*.go")):
            if path.name.endswith("_test.go"):
                continue
            src = path.read_text()
            for m in re.finditer(r"^func (?:\(\w+ \*?(\w+)\) )?(\w+)(.*?)\s*\{$", src, re.M):
                sig = m.group(0)[:-1].rstrip()
                by_name.setdefault(m.group(2), []).append(sig)
                if m.group(1):
                    by_type.setdefault(m.group(1), []).append(sig)
            for m in re.finditer(r"^type (\w+) struct \{(.*?)^\}", src, re.M | re.S):
                fields = "; ".join(" ".join(l.split()[:2]) for l in m.group(2).strip().splitlines() if l.strip())
                by_name.setdefault(m.group(1), []).append(f"type {m.group(1)} struct {{ {fields} }}")
                by_type.setdefault(m.group(1), []).insert(0, f"fields: {fields}")
    else:
        for path in sorted(fixture_dir(task).glob("*.py")):
            if path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text())
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    by_name.setdefault(node.name, []).append(f"{path.stem}.{node.name}({ast.unparse(node.args)})")
                elif isinstance(node, ast.ClassDef):
                    members = []
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                            sig = f"{node.name}.{item.name}({ast.unparse(item.args)})"
                            members.append(sig)
                            by_name.setdefault(item.name, []).append(sig)
                        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            members.append(f"{node.name}.{item.target.id}: {ast.unparse(item.annotation)}")
                    if node.name == "Server":
                        init = next((i for i in node.body if isinstance(i, ast.FunctionDef) and i.name == "__init__"), None)
                        for st in (init.body if init else []):
                            if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Attribute):
                                members.append(f"s.{st.targets[0].attr} = {ast.unparse(st.value)}")
                    by_type[node.name] = members
                    by_name.setdefault(node.name, []).append(f"class {node.name} (module {path.stem})")
    return by_name, by_type


def _usage(task, name):
    """A real call of name from the fixture source, or None."""
    ext = "*.go" if task["lang"] == "go" else "*.py"
    for path in sorted(fixture_dir(task).glob(ext)):
        if path.name.endswith("_test.go") or path.name.startswith("test_"):
            continue
        for line in path.read_text().splitlines():
            t = line.strip()
            if re.search(rf"[.\s(=]{name}\(", " " + t) and not t.startswith(("func ", "def ")):
                return f"{path.name}: {t}"
    return None


def _facts(task, name, sigs):
    out = [f"  {s}" for s in sigs.get(name, [])[:3]]
    use = _usage(task, name)
    if use:
        out.append(f"  example from {use}")
    return out


def diagnose(task, content, result):
    """Returns a list of diagnosis lines (causes plus facts) for a failed
    attempt, or [] when nothing specific was found."""
    by_name, by_type = _signatures(task)
    log = result.get("full_log", result.get("log_tail", ""))
    status = result["status"]
    out, seen = [], set()

    def add(key, lines):
        if key not in seen:
            seen.add(key)
            out.extend(lines)

    for f, n, msg in compile_errors(task, log):
        if task["lang"] == "go":
            if m := re.search(r"type \*?(\w+)(?:\[\w+\])? has no field or method (\w+)", msg):
                add(("members", m.group(1)), [f"- {m.group(1)} has no {m.group(2)}. Its real fields and methods are:"]
                    + [f"  {x}" for x in by_type.get(m.group(1), [])[:8]])
            elif m := re.search(r"(?:multiple-value |but )([\w.\[\]]+?)(?:\(| returns)", msg):
                fn = re.sub(r"\[.*\]", "", m.group(1)).split(".")[-1]
                add(("sig", fn), [f"- Line {n}: {fn} returns a different number of values than you used. Its signature:"]
                    + _facts(task, fn, by_name))
            elif m := re.search(r"mismatched types (\w+) and untyped nil", msg):
                add(("nil", m.group(1)), [f"- Line {n}: a {m.group(1)} is compared with nil. Functions here that can "
                                          f"fail return (value, bool): check the bool (ok), not an error."])
            elif m := re.search(r"^(\w+) redeclared in this block", msg):
                where = next((x[0] for x in compile_errors(task, log)
                              if f"other declaration of {m.group(1)}" in x[2]), None)
                add(("redecl", m.group(1)), [f"- {m.group(1)} already exists in the package"
                                             + (f" ({where})" if where else "") + ". Delete your copy and use it."])
            elif m := re.search(r"cannot use (\S+) \((?:variable|value) of type (\[\]\w+)\) as int value", msg):
                add(("len", m.group(1)), [f"- Line {n}: {m.group(1)} is a list ({m.group(2)}), not a count. Use len(...)."])
            elif m := re.search(r"cannot use .* as (\w+) value in map literal", msg):
                add(("map", m.group(1)), [f"- Line {n}: your map's values must all be {m.group(1)}, but you mix types. "
                                          "Use a struct with one typed field per value instead of a map."])
            elif m := re.match(r"undefined: (\w+)$", msg):
                if m.group(1) in by_name:
                    add(("undef", m.group(1)), [f"- {m.group(1)} exists:"] + _facts(task, m.group(1), by_name))
                elif not m.group(1)[0].islower() or m.group(1) not in STDLIB_GO_PACKAGES:
                    add(("undef", m.group(1)), [f"- {m.group(1)} does not exist in this codebase. Use only the helpers "
                                                "listed in the reference."])
        else:
            kind, _, detail = msg.partition(": ")
            if kind == "AttributeError" and (m := re.search(r"'(\w+)' object has no attribute '(\w+)'", detail)):
                add(("members", m.group(1)), [f"- {m.group(1)} has no attribute {m.group(2)}. Its real members are:"]
                    + [f"  {x}" for x in by_type.get(m.group(1), [])[:10]])
            elif kind == "NameError" and (m := re.search(r"name '(\w+)'", detail)):
                owner = fixture_exports(task).get(m.group(1))
                add(("undef", m.group(1)), [f"- {m.group(1)} is not imported. It is defined in module {owner}: "
                                            f"add `from {owner} import {m.group(1)}`."] if owner else
                    [f"- {m.group(1)} does not exist in this codebase."])
            elif kind == "ImportError" and (m := re.search(r"cannot import name '(\w+)' from '(\w+)'", detail)):
                names = sorted(n for n, mod in fixture_exports(task).items() if mod == m.group(2) and not n.startswith("_"))
                add(("import", m.group(1)), [f"- Module {m.group(2)} has no {m.group(1)}. It defines: {', '.join(names[:20])}. "
                                             f"If you meant to write {m.group(1)} yourself, define it in {task['target']}."])
            elif kind == "TypeError" and (m := re.search(r"(\w+)\(\) (?:missing|takes|got)", detail)):
                add(("sig", m.group(1)), [f"- {m.group(1)} was called with the wrong arguments. Its signature:"]
                    + _facts(task, m.group(1), by_name))

    if status in ("test_fail", "fail_on_correct") and content is not None:
        w = WIRING.get(task["lang"])
        original = read_fixture(task, task["target"]) or ""
        if w:
            before = {r.group(1) for r in w["registered"].finditer(original)}
            after = {r.group(1) for r in w["registered"].finditer(content)}
            if before - after:
                add("dropped", [f"- Your file no longer registers these existing routes: {', '.join(sorted(before - after))}. "
                                "Keep every existing registration."])
            unwired = unwired_handlers(task, content)
            if unwired:
                add("unwired", [f"- {', '.join(unwired)} is defined but never registered in the routes function, so "
                                "requests to it return 404."])
            elif "404" in log and not before - after:
                add("404", ["- Some requests return 404 because no registered route matches them. Check the "
                            "route patterns you registered."])
        hidden = Path(task.get("hidden_test", "")).stem
        if task["lang"] == "go":
            broken = sorted({t for t in re.findall(r"--- FAIL: (Test\w+)", log) if not t.startswith("TestHidden")})
        else:
            broken = sorted({m for m in re.findall(r"^(?:FAIL|ERROR): \w+ \((\w+)\.", log, re.M) if m != hidden})
        if broken and status == "test_fail":
            add("broken", [f"- You changed existing behavior: these existing tests now fail: {', '.join(broken)}. "
                           "Keep existing behavior unchanged unless the task asks for a change."])
    if status == "fail_on_correct":
        add("expect", ["- The implementation is correct; your expected values are wrong. Where a failure shows the "
                       "actual value (got X / first value of A != B), that is the true result: use it."])
    return out


STDLIB_GO_PACKAGES = {"fmt", "strings", "strconv", "sort", "slices", "sync", "errors", "time", "json", "http",
                      "httptest", "testing"}


def grade(task, content):
    """Grades content as the task's target file.

    content=None leaves the fixture's target untouched (or absent for
    new_file tasks), which verify_tasks.py uses as the baseline.

    Returns a dict with status (pass, build_fail, test_fail, timeout, or for
    test-writing tasks also fail_on_correct and missed_mutant), log_tail, and
    for test-writing tasks a per-mutant breakdown.
    """
    with tempfile.TemporaryDirectory(prefix=f"fmeval-{task['id']}-") as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(fixture_dir(task), work, ignore=shutil.ignore_patterns("__pycache__"))
        if content is not None:
            (work / task["target"]).write_text(content)
        if task.get("hidden_test"):
            shutil.copy(hidden_dir(task) / task["hidden_test"], work / task["hidden_test"])

        status, log = run_tests(task, work)
        if task["tier"] != "test":
            return {"status": status, "log_tail": log[-LOG_TAIL:], "full_log": log}

        # Test-writing: must pass on the correct code first.
        if status != "pass":
            if status == "test_fail":
                status = "fail_on_correct"
            return {"status": status, "log_tail": log[-LOG_TAIL:], "full_log": log, "mutants": {}}

        mutants = {}
        first_miss_log = ""
        for m in task["mutants"]:
            target = work / m["replaces"]
            original = target.read_text()
            shutil.copy(hidden_dir(task) / m["file"], target)
            # mutant_test_cmd restricts the run to the model's tests when the
            # existing tests would catch the mutant on their own.
            m_status, m_log = run_tests(task, work, task.get("mutant_test_cmd"))
            target.write_text(original)
            # Only an assertion failure counts as catching the mutant.
            caught = m_status == "test_fail"
            mutants[Path(m["file"]).name] = "caught" if caught else m_status
            if not caught and not first_miss_log:
                first_miss_log = f"With {Path(m['file']).name} in place of {m['replaces']}: {m_status}\n{m_log}"
        all_caught = all(v == "caught" for v in mutants.values())
        return {
            "status": "pass" if all_caught else "missed_mutant",
            "log_tail": (log if all_caught else first_miss_log)[-LOG_TAIL:],
            "mutants": mutants,
        }
