"""Regrades every recorded output in a results file with the current
cleanup and grading code. Used when a harness bug is fixed after a run.
Note: attempts after a falsely failed one cannot be recovered, because the
retry prompt depended on the old result.

Usage: .venv/bin/python regrade.py results/<file>.jsonl
"""

import json
import sys

from harness import apply_edit, grade, load_tasks
from run_eval import clean_output


def main():
    tasks = {t["id"]: t for t in load_tasks()}
    for line in open(sys.argv[1]):
        r = json.loads(line)
        if r["type"] != "attempt" or r["output"] is None:
            continue
        task = tasks[r["task"]]
        content, err = apply_edit(task, clean_output(r["output"])[0], r.get("edit_format", "full"),
                                  r.get("merge", "replace"))
        new = "merge_fail" if err is not None else grade(task, content)["status"]
        flag = "" if new == r["status"] else "   <-- changed"
        print(f"run {r['run']} {r['task']:22s} a{r['attempt']} {r['status']:14s} -> {new}{flag}")


if __name__ == "__main__":
    main()
