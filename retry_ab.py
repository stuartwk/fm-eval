"""Compares retry styles on identical starting failures.

Takes every first attempt from the given results files, applies the current
harness to it (merge, repair, wiring, using the run's own config), and keeps
the ones that still fail. For each retry style it then runs up to
MAX_ATTEMPTS - 1 retries from that same failure, with the same harness
applied to every retry. Only the feedback differs between styles, so the
rescue rates are directly comparable.

Usage:
    .venv/bin/python -u retry_ab.py results/A.jsonl [results/B.jsonl ...]
        [--styles fresh,diagnostic] [--edit-format full_merge] [--limit N]

--edit-format overrides the runs' recorded edit format (for example to use
full_merge on runs recorded as full, which send identical prompts).
"""

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import apple_fm_sdk as fm

from harness import ROOT, diagnose, generated_api, grade, load_tasks, repair
from run_eval import MAX_ATTEMPTS, clean_output, run_attempt, wire


def skill_text(skills, task):
    if isinstance(skills, str):
        skills = [skills]
    parts = [generated_api(task) if s == "auto" else Path(s).read_text() for s in skills or []]
    return "\n".join(parts) or None


async def load_seeds(model, paths, edit_override):
    """First attempts that still fail after the current harness."""
    tasks = {t["id"]: t for t in load_tasks() + load_tasks(heldout=True)}
    seeds = []
    for path in paths:
        hdr = {}
        for line in open(path):
            r = json.loads(line)
            if r["type"] == "run":
                hdr = r
                continue
            if r["type"] != "attempt" or r["attempt"] != 1 or not r.get("output"):
                continue
            task = tasks[r["task"]]
            ef = edit_override or hdr.get("edit_format", "full")
            merge = hdr.get("merge", "additive")
            content, _ = await asyncio.to_thread(repair, task, clean_output(r["output"])[0], ef, merge)
            if content is None:
                continue  # unparseable even after repair: nothing to diagnose
            content, _ = await wire(model, task, content)
            result = await asyncio.to_thread(grade, task, content)
            if result["status"] == "pass":
                continue
            seeds.append({"source": path, "run": r["run"], "task": task, "content": content, "result": result,
                          "edit_format": ef, "merge": merge, "skill": skill_text(hdr.get("skill"), task)})
    return seeds


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--styles", default="fresh,diagnostic")
    ap.add_argument("--edit-format")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    styles = args.styles.split(",")

    model = fm.SystemLanguageModel()
    options = fm.GenerationOptions()
    seeds = await load_seeds(model, args.files, args.edit_format)
    if args.limit:
        seeds = seeds[:args.limit]
    out_path = ROOT / "results" / f"retry-ab-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    print(f"{len(seeds)} seeds x {len(styles)} styles, logging to {out_path.relative_to(ROOT)}")

    rescued = defaultdict(list)  # style -> [(task id, attempt or None)]
    with open(out_path, "w") as f:
        f.write(json.dumps({"type": "run", "started": datetime.now().isoformat(), "seeds": len(seeds),
                            "styles": styles, "sources": args.files, "edit_format": args.edit_format}) + "\n")
        for i, seed in enumerate(seeds):
            task = seed["task"]
            for style in styles:
                previous = (seed["content"], seed["result"])
                passed = None
                for attempt in range(2, MAX_ATTEMPTS + 1):
                    rec, graded, result = await run_attempt(
                        model, options, task, (seed["skill"], previous, style), "plain", False,
                        seed["edit_format"], seed["merge"], use_repair=True, use_wire=True)
                    rec.update(seed=i, attempt=attempt, seed_status=seed["result"]["status"],
                               has_diagnosis=bool(diagnose(task, previous[0], previous[1])))
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    if result is None:
                        break
                    if rec["status"] == "pass":
                        passed = attempt
                        break
                    previous = (graded, result)
                rescued[style].append((task["id"], passed))
                if style == styles[0]:
                    seed["diagnosed"] = bool(diagnose(task, seed["content"], seed["result"]))
                print(f"seed {i:2d} {task['id']:30s} {seed['result']['status']:15s} {style:10s} -> "
                      f"{'rescued@' + str(passed) if passed else 'not rescued'}")

    print("\n=== Rescue rate by retry style ===")
    for style in styles:
        rs = rescued[style]
        print(f"{style:10s} {sum(1 for _, p in rs if p)}/{len(rs)}")
    diagnosed = [s.get("diagnosed") for s in seeds]
    print(f"\nSeeds with a diagnosis: {sum(diagnosed)}/{len(seeds)}. Rescues on those:")
    for style in styles:
        rs = [p for (_, p), d in zip(rescued[style], diagnosed) if d]
        print(f"{style:10s} {sum(1 for p in rs if p)}/{len(rs)}")
    print("\nPer task (rescues / seeds):")
    for tid in sorted({s["task"]["id"] for s in seeds}):
        row = "  ".join(f"{st}={sum(1 for t, p in rescued[st] if t == tid and p)}/"
                        f"{sum(1 for t, _ in rescued[st] if t == tid)}" for st in styles)
        print(f"  {tid:30s} {row}")


if __name__ == "__main__":
    asyncio.run(main())
