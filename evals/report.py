"""Rebuild Figure 2 from Inspect `.eval` logs.

    python evals/report.py                        # every duopoly log in logs/
    python evals/report.py --model gpt-4o-mini    # when logs/ holds >1 model
    python evals/report.py --tag full300          # label the output folder
    python evals/report.py logs/2026-*-P1-rep1-a1_*.eval   # specific logs

Output lands in `results/<log-timestamp>-<tag>/`, the same shape the old harness
used (`results/20260921-232625-full300`), so old and new sit side by side and
sort together.  The timestamp is the log's, not the render's -- see
`output_folder`.

The importer writes one log per market, so the across-run comparison -- which
is what Figure 2 *is* -- happens here, by reading the whole directory back.

Why the figure is rebuilt from logs rather than from a CSV the run wrote: the
log is the primary artefact.  Anything derived from it (a CSV, a figure, a
slide) can be regenerated at any time, and if two figures disagree you can tell
which one is stale.  The old `summary.csv` is still produced, into the output
folder, because `plot_fig2.py` and the LaTeX deck both read it -- but it is now
a *derivative* of the log, not a parallel source of truth.

The drawing itself is not reimplemented: `src/plot_fig2.py` already renders
both panels and runs the Welch test, and is imported unchanged.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "src"))

from inspect_ai.log import list_eval_logs, read_eval_log  # noqa: E402

import plot_fig2  # noqa: E402

# The columns summary.csv has always had, in the order it had them, so that
# anything already reading that file keeps working.
COLUMNS = [
    "run_id", "prefix", "rep", "alpha", "seed", "periods_completed", "avg_window",
    "price1", "price2", "profit1", "profit2", "profit_sum", "profit_diff",
    "p_nash", "p_monopoly", "profit_nash_per_firm", "profit_monopoly_total",
    "collusion_index", "llm_calls", "llm_retries", "cost_usd", "stopped_reason",
]


def rows_from_log(source) -> list[dict]:
    """One row per sample -- i.e. per market.

    `source` is a path or an `EvalLogInfo` from `list_eval_logs`; the latter
    carries a URI ("file:/D:/...") that must be handed to `read_eval_log`
    intact rather than pushed through `Path`.  Events and messages are excluded
    because a 300-period log is mostly model calls and we only want the scores.
    """
    log = read_eval_log(source, exclude_fields={"events", "messages"})
    if log.eval.task != "duopoly" or not log.samples:
        return []

    rows = []
    for sample in log.samples:
        scores = sample.scores or {}
        ci = scores.get("collusion_index")
        if ci is None or ci.metadata is None:
            continue
        md = ci.metadata
        sm = sample.metadata or {}
        usage = sample.model_usage or {}
        cost = sum(u.total_cost or 0.0 for u in usage.values())
        rows.append({
            "run_id": str(sample.id),
            "prefix": sm.get("prefix", ""),
            "rep": sm.get("rep", 0),
            "alpha": sm.get("alpha", 1.0),
            "seed": sm.get("seed", 0),
            "periods_completed": md.get("periods_completed", 0),
            "avg_window": md.get("avg_window", 0),
            "price1": md["price1"], "price2": md["price2"],
            "profit1": md["profit1"], "profit2": md["profit2"],
            "profit_sum": md["profit_sum"], "profit_diff": md["profit_diff"],
            "p_nash": md["p_nash"], "p_monopoly": md["p_monopoly"],
            "profit_nash_per_firm": md["profit_nash_per_firm"],
            "profit_monopoly_total": md["profit_monopoly_total"],
            "collusion_index": float(ci.value),
            "llm_calls": sm.get("llm_calls_recorded", 0),
            "llm_retries": md.get("template_retries", 0),
            "cost_usd": sm.get("cost_usd_recorded", cost),
            "stopped_reason": md.get("stopped_reason", ""),
            "_model": log.eval.model,
            "_created": log.eval.created,
        })
    return rows


def output_folder(rows: list[dict], model: str, tag: str) -> Path:
    """`results/<stamp>-<tag>`, the same shape the old harness used.

    The stamp is the *log's* creation time, not the moment the figure was drawn.
    That means the folder names the run rather than the render: re-running this
    script on the same logs overwrites one folder instead of littering a new one
    each time, and the folder sorts next to the original `results/<stamp>-<tag>`
    tree it replaces.
    """
    created = min(r["_created"] for r in rows)
    stamp = datetime.fromisoformat(created).strftime("%Y%m%d-%H%M%S")
    if not tag:
        # e.g. "openrouter/openai/gpt-4o-mini" -> "gpt-4o-mini"
        tag = re.sub(r"[^A-Za-z0-9.-]+", "-", model.split("/")[-1]).strip("-")
    return REPO / "results" / (f"{stamp}-{tag}" if tag else stamp)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="*", help="specific .eval files (default: all in --log-dir)")
    ap.add_argument("--log-dir", default=str(REPO / "logs"))
    ap.add_argument("--out", default=None,
                    help="folder for summary.csv and the figure "
                         "(default: results/<log-timestamp>-<tag>)")
    ap.add_argument("--tag", default="",
                    help="label appended to the output folder "
                         "(default: the model name, e.g. gpt-4o-mini)")
    ap.add_argument("--model", default=None,
                    help="only use logs from this model (substring match). "
                         "Required when the log directory holds more than one.")
    args = ap.parse_args()

    if args.logs:
        sources = [Path(p) for p in args.logs]
    else:
        # For a local directory, glob it with pathlib rather than going through
        # `list_eval_logs`.  That helper returns file:// URIs, and on Windows a
        # URI for a path on a different drive than the working directory comes
        # back with the drive letter stripped ("file:/C:/..." -> "\Users\..."),
        # which then fails to open.  Paths do not have that problem.  Remote log
        # stores (s3://, gs://) have no local directory, so they still go
        # through the helper.
        local = Path(args.log_dir)
        if local.is_dir():
            sources = sorted(local.glob("*.eval")) + sorted(local.glob("*.json"))
        else:
            sources = list(list_eval_logs(args.log_dir))
    if not sources:
        sys.exit(f"No .eval logs found in {args.log_dir}. "
                 f"Run: inspect eval evals/duopoly.py --model openrouter/openai/gpt-4o-mini")

    rows: list[dict] = []
    for src in sorted(sources, key=lambda s: str(getattr(s, "name", s))):
        rows.extend(rows_from_log(src))
    if not rows:
        sys.exit("No duopoly samples with scores found in those logs.")

    # ---- refuse to average across models.
    #
    # Run ids are (prefix, rep, alpha) and nothing else, so a mock smoke test
    # dropped into the same directory produces a "P1_rep1_a1" that collides
    # with the real one.  Silently letting the last writer win turns a stray
    # 30-second offline run into a change in the headline number, with no
    # visible error -- exactly the failure mode an eval is supposed to prevent.
    # So: one model per report, and duplicates are named rather than resolved.
    if args.model:
        rows = [r for r in rows if args.model in r["_model"]]
        if not rows:
            sys.exit(f"No logs matched --model {args.model!r}.")
    models = sorted({r["_model"] for r in rows})
    if len(models) > 1:
        counts = {m: sum(1 for r in rows if r["_model"] == m) for m in models}
        sys.exit(
            "These logs come from more than one model, and mixing them would "
            "silently corrupt the figure:\n"
            + "".join(f"  {m}  ({n} markets)\n" for m, n in counts.items())
            + f"\nPick one, e.g.:  python {Path(__file__).name} --model {models[0]}"
        )
    model = models[0]

    by_id: dict[str, list[dict]] = {}
    for r in rows:
        by_id.setdefault(r["run_id"], []).append(r)
    dupes = {k: v for k, v in by_id.items() if len(v) > 1}
    if dupes:
        sys.exit(
            "The same market appears in more than one log:\n"
            + "".join(f"  {k} x{len(v)}\n" for k, v in sorted(dupes.items()))
            + "\nRe-scoring should replace a log, not sit beside it. Remove the "
              "stale copies, or pass the logs you want explicitly."
        )
    rows = sorted((v[0] for v in by_id.values()),
                  key=lambda r: (r["prefix"], r["run_id"]))

    # Name the folder before stripping the bookkeeping keys it is derived from.
    out = Path(args.out) if args.out else output_folder(rows, model, args.tag)
    for r in rows:
        r.pop("_model", None)
        r.pop("_created", None)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in COLUMNS} for r in rows)

    print(f"Read {len(sources)} log(s) -> {len(rows)} markets")
    plot_fig2.print_table(rows)
    note = f", {rows[0]['periods_completed']:.0f} periods, model {model}"
    plot_fig2.make_figure(rows, out, note)
    # A second copy without the redundant suptitle, for dropping into slides.
    plot_fig2.make_figure(rows, out, suptitle=False, out_name="fig2_pilot_slide")
    print(f"\nsummary.csv and figures: {out}")


if __name__ == "__main__":
    main()
