"""One command for the whole pipeline: run the eval, then rebuild Figure 2.

    python evals/run.py --mock                     # free, offline, ~30 seconds
    python evals/run.py                            # the pilot (~$0.12)
    python evals/run.py --runs 7 --periods 100 --alphas 1,3.2,10 \
        --history-window 30 --avg-window 25 --max-connections 20

`inspect eval evals/duopoly.py -T runs=7 ...` does the same thing and is the
canonical way to drive an Inspect task.  This wrapper exists for two reasons.

1. It keeps the flag names the old harness used (`--runs`, `--periods`,
   `--alphas`, `--mock`), so the commands in the paper notes and in the slide
   deck still mean something.  Every flag maps onto exactly one `-T` parameter
   and the mapping is printed with `--dry-run`, so this stays a convenience and
   never becomes a second source of truth about what the experiment is.

2. It runs the eval through the Python API, which imports the task module
   *before* resolving the model.  That is the one thing the CLI cannot do, and
   it is why `--model duopoly/mock` works here but not there (see
   `mock_provider.mock_model`).

By default it also rebuilds the figure, because a run whose result nobody looked
at is a run that will be repeated.  `--no-report` skips it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from inspect_ai import eval as inspect_eval  # noqa: E402

import report  # noqa: E402
from duopoly import duopoly  # noqa: E402  (also registers duopoly/mock)

DEFAULT_MODEL = "openrouter/openai/gpt-4o-mini"


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # ---- what to run (old harness flag names, one -T parameter each)
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help="Inspect model id (default: %(default)s)")
    p.add_argument("--mock", action="store_true",
                   help="free offline stand-in; no API key, no spend")
    p.add_argument("--prefixes", default="P1,P2", help="prompt prefixes to compare")
    p.add_argument("--runs", type=int, default=3, help="markets per prefix per alpha")
    p.add_argument("--periods", type=int, default=30, help="periods per market (paper: 300)")
    p.add_argument("--alphas", default="1", help="currency scales, e.g. 1,3.2,10")
    p.add_argument("--history-window", type=int, default=15,
                   help="rounds of history shown to the agent (paper: 100)")
    p.add_argument("--avg-window", type=int, default=10,
                   help="final periods averaged by the scorers (paper: 50)")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=1200)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--budget-usd-per-run", type=float, default=None,
                   help="cost cap PER MARKET (Inspect's limits are per sample), "
                        "so the worst case is this times the number of markets")

    # ---- how to run it
    p.add_argument("--max-connections", type=int, default=None,
                   help="concurrent model requests (replaces the old --jobs)")
    p.add_argument("--log-dir", default=str(REPO / "logs"))
    p.add_argument("--tag", default="", help="tag recorded in the log")

    # ---- what to do afterwards
    p.add_argument("--no-report", action="store_true",
                   help="skip rebuilding Figure 2 from the logs")
    p.add_argument("--dry-run", action="store_true",
                   help="print the equivalent `inspect eval` command and exit")
    args = p.parse_args()

    params = dict(
        prefixes=args.prefixes,
        runs=args.runs,
        periods=args.periods,
        alphas=args.alphas,
        history_window=args.history_window,
        avg_window=args.avg_window,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        seed=args.seed,
        max_template_retries=6,
        budget_usd_per_run=args.budget_usd_per_run,
        mock=args.mock,
    )

    n_markets = (len(args.prefixes.split(",")) * args.runs
                 * len(args.alphas.split(",")))
    n_calls = n_markets * args.periods * 2

    if args.dry_run:
        targs = " ".join(f"-T {k}={v}" for k, v in params.items() if v is not None)
        model = "" if args.mock else f" --model {args.model}"
        conn = f" --max-connections {args.max_connections}" if args.max_connections else ""
        print(f"inspect eval evals/duopoly.py{model} {targs}"
              f" --log-dir {args.log_dir}{conn}")
        print(f"\n{n_markets} markets x {args.periods} periods x 2 agents "
              f"= {n_calls} model calls (paper: 25,200)")
        return

    print(f"model      {'MOCK (offline, free)' if args.mock else args.model}")
    print(f"markets    {n_markets}  ({args.prefixes} x {args.runs} runs "
          f"x alphas {args.alphas})")
    print(f"calls      {n_calls}  (paper: 25,200)")
    print(f"logs       {args.log_dir}\n")

    kwargs = {}
    if args.max_connections is not None:
        kwargs["max_connections"] = args.max_connections

    logs = inspect_eval(
        duopoly(**params),
        # The task carries the mock Model itself, so passing a model here too
        # would override it; leave it to the task in that case.
        model=None if args.mock else args.model,
        log_dir=args.log_dir,
        tags=[args.tag] if args.tag else None,
        **kwargs,
    )

    failed = [log for log in logs if log.status != "success"]
    if failed:
        print(f"\n{len(failed)} task(s) did not succeed:")
        for log in failed:
            print(f"  {log.status}: {log.error.message if log.error else ''}")

    if args.no_report:
        print("\n(skipping the figure; run `python evals/report.py` when ready)")
        return

    print("\nRebuilding Figure 2 from the logs...")
    # Name the model we just ran.  The log directory usually holds more than one
    # (a mock smoke test beside a real pilot), and `report.py` refuses to average
    # across models rather than silently mixing them -- so tell it which one.
    model_used = logs[0].eval.model if logs else args.model
    sys.argv = ["report.py", "--log-dir", args.log_dir, "--model", model_used]
    if args.tag:
        sys.argv += ["--tag", args.tag]
    report.main()


if __name__ == "__main__":
    main()
