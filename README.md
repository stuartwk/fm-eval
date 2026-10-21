# fm-eval

Can Apple's on-device Foundation Model power a coding agent like Claude Code?

This repo measures how well the on-device model (through Apple's Python SDK,
`apple-fm-sdk`) completes small, realistic coding tasks in an existing
codebase when it is handed ideal ("oracle") context. It was built as a
validation gate before investing in an on-device coding agent harness, so
the numbers and the failure analysis are the point, not the tooling.

## Setup

- 2 small fixture repos (Go and Python), same design: an in-memory shop
  with users, orders, products, reviews, shared JSON helpers, HTTP
  handlers and table-driven tests. Each file is 60 to 150 lines so a target
  plus its context fits in the model's 8192-token window.
- 18 tasks per language (36 total), one TOML file each, across three tiers:
  - easy: mirror an existing handler for a new resource
  - medium: validation, query params, pagination, error cases
  - test-writing: the model writes tests, graded by passing against the
    real code and failing (on an assertion, not a compile error) against
    deliberately broken mutants
- A mix of `new_file` and `modify` tasks. Every task is a single-file edit.
- Grading uses hidden tests the model never sees, and runs the whole
  package's tests, so breaking neighboring code counts as a failure.
- `verify_tasks.py` checks that every hand-written solution passes and every
  untouched fixture fails.

## Results

pass@1 is first attempts only, 18 tasks x 3 runs per language.

| Config | Go | Python |
|---|---|---|
| Baseline (model writes the whole file) | 10/54 (19%) | 16/54 (30%) |
| Plus API cheat sheet ("skill") | 16/54 (30%) | 17/54 (31%) |
| Best harness (merge + skill + repair + wiring) | **23/54 (43%)** | **27/54 (50%)** |
| Best harness plus up to 2 fresh retries | ~27/54 (50%) | ~30/54 (56%) |
| Edit recipes, falling back to the best harness | **33/54 (61%)** | not ported |

### Edit recipes: the model fills in a form, the harness writes the code

For common kinds of edit (a store method that filters by a field, a query
filter on a list endpoint, normalizing a request field) the harness keeps a
code template. The model only answers two guided-generation questions:
which recipe fits the request, and what its slots are (which field, which
allowed values, which error code). Every slot that names code is an enum
built from the codebase. The harness checks the slots against the request
text, renders the template, and falls back to the best full-file config
for anything no recipe covers.

| Go, non-test tasks, 3 runs each | Best harness | Recipes |
|---|---|---|
| Original 15 tasks | 23/45 (51%) | **33/45 (73%)** |
| 9 held-out tasks, written after the recipes were frozen | 8/27 (30%) | **16/27 (59%)** |

- **The model is good at filling slots.** The 4 original tasks it never
  solved by writing code went from 1/12 to 11/12, and applied recipes
  passed 24 of 27 times across both sets.
- **It is bad at picking a recipe and at checking its own answer.**
  Without checks it routed lookalike tasks into the wrong recipe and scored
  worse than the baseline (18/45). Asked yes or no whether a plain-English
  description of the edit matched the request, it approved almost
  everything, including an inverted true/false condition.
- **Deterministic checks fixed routing:** slot values must appear in the
  request, error codes are narrowed to those it names, a signature the
  request spells out must match, and a request that names a new route is
  never treated as a change to an existing endpoint. On the held-out set,
  none of the 3 lookalike tasks got a recipe, and no task scored below
  its fallback.
- The gain is limited to edit kinds with a recipe. Test-writing and new
  files still score 0.

What the model gets wrong (hand-tagged failures on the 9 tasks that fail
in both languages):

- **Wrong use of an API that is right there in context** (21 of 54):
  ignoring Go `(T, bool)` / `(T, error)` returns, attribute names from
  training priors, invented helpers.
- **New code never wired in** (11): a handler is written but its route is
  never registered, or a parallel function is added instead of editing the
  existing one.
- **Misread spec** (9), wrong expected values in tests (3), and dropping
  existing code.
- **New files: 0/18** in every Go config. **Test-writing: 0/27** in Go.
- Adding one line to an existing function (one more route in a list of
  routes) almost never works: the model either drops the old lines or
  writes only the new one.

What helped, and what did not:

- Helped: merging the model's file into the original so dropped
  declarations survive (`full_merge`), a short API reference (removed
  every hallucinated-API failure), mechanical repair (brace balancing,
  imports, unused variables), and restoring routes for handlers nothing
  references (`--wire`).
- Did not help: rich diagnostic feedback on retries, patch-style retries
  (showing the previous attempt anchors the model; 40 of 115 replies were
  near-copies of the broken code), a did-you-mean rename repair (wrong names
  reflect a wrong model of the code, not typos), guided generation of
  whole files (runs away until the context window overflows), and short
  focused prompts holding only the relevant declarations (2/15 vs 0/15 on
  the logic failures: with all the needed information in view, the model
  still misreads what to compute).

**Conclusion:** with oracle context and a lot of harness support, the
model completes roughly half of small single-file edits when it writes the
code. It cannot create new files or write correct tests, and retries do
not converge, because each full rewrite introduces new errors. Its
remaining failures are mostly misreadings of what to compute, which
neither better context nor constrained identifier choices would fix.

Where it is strong is reading a small request and answering narrow, typed
questions about it. Used that way, with the harness owning the code
(templates) and the checking (deterministic checks against the request),
it handles the edit kinds the harness knows with few errors, and the result
held on tasks written after the design was frozen. A coding agent built on
this model would be a library of edit recipes with the model as the layer
that reads the request, not a model that writes code.

`CLAUDE.md` holds the full, dated research log with every finding and the
reasoning behind each harness change. The project was built with Claude
Code, and that file doubled as its working instructions.

## Requirements

- macOS 27 on Apple silicon with Apple Intelligence enabled
- Python 3.11+ with `apple-fm-sdk` 0.2.1
- Go 1.25 (for the Go fixture and the `tools/` helpers, which the harness
  builds on first use)

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python verify_tasks.py      # sanity check the task set
```

## Running

```sh
# baseline, all Go tasks, 3 runs each
.venv/bin/python run_eval.py --lang go --runs 3 --attempts 1

# best Go config
.venv/bin/python run_eval.py --lang go --runs 3 --attempts 1 \
  --edit-format full_merge --skill auto --skill skills/go-shop-conventions.md \
  --repair --wire

# best Python config
.venv/bin/python run_eval.py --lang python --runs 3 --attempts 1 \
  --edit-format full_merge --skill skills/py-shop-api.md --repair --wire
```

```sh
# edit recipes on the 15 non-test Go tasks (falls back to the recorded best config)
.venv/bin/python recipes.py --runs 3

# held-out tasks: best config first, then recipes with it as the fallback
.venv/bin/python run_eval.py --heldout --lang go --runs 3 --attempts 1 \
  --edit-format full_merge --skill auto --skill skills/go-shop-conventions.md \
  --repair --wire
.venv/bin/python recipes.py --heldout --runs 3 --fallback results/<that run>.jsonl
```

Each run writes a timestamped JSONL file to `results/` with every prompt
size, output, status and log tail. The recorded runs behind the numbers
above are committed there.

| Script | Purpose |
|---|---|
| `run_eval.py` | The runner. `--help` lists all options. |
| `harness.py` | Task loading, grading, merge, repair, wiring, diagnosis. |
| `verify_tasks.py` | Checks solutions pass and fixtures fail. |
| `regrade.py` | Regrades recorded outputs after a harness change. |
| `retry_ab.py` | Compares retry styles on the same failed first attempts. |
| `tag_failures.py` | Heuristic failure tags per config and tier. |
| `recipes.py` | Edit recipes: the model routes and fills slots, the harness writes the code. |
| `focused_ab.py` | Logic-failure tasks with a minimal prompt instead of whole files. |
| `tools/goapi` | Generates a compact API reference from a Go package. |
| `tools/gomerge` | Merges a snippet of Go declarations into a file. |

## Layout

```
fixtures/<lang>/    small repo per language (builds, tests pass)
tasks/<lang>/       one TOML per task
tasks/go-heldout/   held-out tasks (--heldout), excluded from the main numbers
hidden/<lang>/      grading tests and mutants, never shown to the model
solutions/<lang>/   hand-written correct target per task
skills/             API cheat sheets prepended with --skill
results/            recorded runs
```

## Not done

TypeScript, Swift and Rust fixtures were planned but not built, as were
slicing strategies for files larger than the context window and a
calibration run against a larger model.
