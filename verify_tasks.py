"""Checks every task before it is used for grading.

For each task:
- the reference solution in solutions/<lang>/<id>/ must pass, and
- the untouched fixture (baseline) must not pass,
so each hidden test is known to measure the gap it was written for.
"""

import argparse
import sys

from harness import ROOT, grade, load_tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang")
    ap.add_argument("--task")
    ap.add_argument("--heldout", action="store_true", help="check the held-out tasks instead")
    args = ap.parse_args()

    ok = True
    for task in load_tasks(args.lang, args.task, args.heldout):
        sol_path = ROOT / "solutions" / task["lang"] / task["id"] / task["target"]
        if not sol_path.exists():
            print(f"FAIL {task['id']}: no solution at {sol_path.relative_to(ROOT)}")
            ok = False
            continue
        sol = grade(task, sol_path.read_text())
        base = grade(task, None)
        good = sol["status"] == "pass" and base["status"] != "pass"
        ok &= good
        print(f"{'ok  ' if good else 'FAIL'} {task['id']}: solution={sol['status']} baseline={base['status']}"
              + (f" mutants={sol['mutants']}" if "mutants" in sol else ""))
        if not good:
            print(sol["log_tail"] if sol["status"] != "pass" else base["log_tail"])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
