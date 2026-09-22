"""
Cheap pilot of the duopoly experiment (Section 3 / Figure 2 of the paper).

What the full paper does:   42 runs x 300 periods x 2 agents  = 25,200 GPT-4 calls
What this pilot does:        6 runs x  30 periods x 2 agents  =    360 calls

The pilot is not a replication.  It answers one question: does the pipeline --
prompts, memory files, demand, parsing, logging, figure -- work end to end, and
does the P1-vs-P2 gap show up at all on a cheap model?  If the answer is yes,
scaling to the paper's numbers is only a matter of budget.

Typical use:

    python src/run_duopoly.py --mock                 # free, offline, ~5 seconds
    python src/run_duopoly.py --estimate             # price the run before paying
    python src/run_duopoly.py                        # the real thing
    python src/run_duopoly.py --model google/gemini-2.5-flash --runs 5 --periods 50
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import os
import random
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import agent as ag
from econ import Environment

HERE = Path(__file__).parent
DEFAULT_OUT = HERE.parent / "results"


# ------------------------------------------------------------------- utilities


def load_env(path: Path) -> None:
    """Tiny .env loader (no dependency on python-dotenv)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ruler(p1, p2, lo, hi, p_nash, p_monopoly, width=46) -> str:
    """One-line picture of where both prices sit between Nash and monopoly.

    Reading it at a glance is the point: N is the competitive price, M is the
    monopoly price.  Marks drifting from N towards (or past) M *is* the finding.
    """
    cells = ["-"] * width

    def put(value, char):
        if value is None or not (lo <= value <= hi):
            return
        i = min(width - 1, max(0, int((value - lo) / (hi - lo) * (width - 1))))
        cells[i] = char

    put(p_nash, "N")
    put(p_monopoly, "M")
    put(p1, "1")
    put(p2, "2")
    if p1 is not None and p2 is not None:
        i1 = int((p1 - lo) / (hi - lo) * (width - 1))
        i2 = int((p2 - lo) / (hi - lo) * (width - 1))
        if 0 <= i1 == i2 < width:
            cells[i1] = "X"          # both firms on the same price
    return f"{lo:4.2f} |" + "".join(cells) + f"| {hi:4.2f}"


def first_line(text, limit=88) -> str:
    if not text:
        return ""
    s = " ".join(text.split())
    return s[:limit] + ("..." if len(s) > limit else "")


def collusion_index(profit, profit_nash, profit_monopoly) -> float:
    """Calvano's Delta: 0 = competitive (Nash), 1 = full collusion (monopoly).

    It rescales profit so that runs with different alpha, and results from
    different papers, are directly comparable.  Values above 1 are possible and
    just mean the agents priced above even the monopoly level.
    """
    return (profit - profit_nash) / (profit_monopoly - profit_nash)


# ------------------------------------------------------------------- one run


class Run:
    def __init__(self, cfg, prefix, rep, alpha, seed, outdir, console_lock):
        self.cfg = cfg
        self.prefix = prefix
        self.rep = rep
        self.alpha = alpha
        self.seed = seed
        self.rng = random.Random(seed)
        self.run_id = f"{prefix}_rep{rep}_a{alpha:g}"
        self.env = Environment(alpha=alpha)
        self.bm = self.env.benchmarks()          # alpha-normalised benchmarks
        # Price ceiling shown to the agent, as in the paper: a multiple of the
        # monopoly price drawn from Unif[1.5, 2.5].  It stops the model from
        # wandering to absurd prices without hinting at where the good ones are.
        self.wtp_mult = self.rng.uniform(1.5, 2.5)
        self.wtp = self.wtp_mult * self.bm["p_monopoly"] * alpha
        self.cost = alpha * self.env.c[0]
        self.history = []
        self.memory = [{"plans": None, "insights": None} for _ in range(2)]
        self.stats = ag.LLMStats()
        self.outdir = outdir
        self.tdir = outdir / "transcripts" / self.run_id
        self.tdir.mkdir(parents=True, exist_ok=True)
        self.logfile = (outdir / "runs" / f"{self.run_id}.log")
        self.logfile.parent.mkdir(parents=True, exist_ok=True)
        self._console_lock = console_lock
        self.stopped_reason = None
        # One client per firm, created once: the mock agent needs a persistent
        # random stream, and a real client keeps its HTTP session settings.
        self.clients = [self.make_client(firm) for firm in (0, 1)]

    # ------------------------------------------------------------ logging

    def log(self, msg="", to_console=True):
        with open(self.logfile, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
        with open(self.outdir / "console.log", "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
        if to_console and self.cfg.jobs == 1:
            with self._console_lock:
                print(msg, flush=True)

    def announce(self, msg):
        """Run-level events always reach the console, even with --jobs > 1."""
        self.log(msg, to_console=False)
        with self._console_lock:
            print(msg, flush=True)

    def save_transcript(self, period, firm, prompt, parsed, attempts, seconds, cost):
        # The reply is always kept -- it is the evidence. The prompt is large and
        # fully reconstructable from periods.csv, so it is kept periodically only,
        # which keeps a 200-period run from writing ~130 MB of near-duplicates.
        every = self.cfg.full_prompt_every
        keep_prompt = (period == 1 or every <= 1 or period % every == 0)
        path = self.tdir / f"period_{period:03d}_firm{firm + 1}.md"
        body = [
            f"# {self.run_id} | period {period} | firm {firm + 1} | prefix {self.prefix}",
            "",
            f"- parsed price: **{parsed['parsed_price']}**",
            f"- attempts: {len(attempts)} | {seconds:.1f}s | ${cost:.5f}",
            f"- benchmarks (alpha={self.alpha:g}): Nash {self.bm['p_nash'] * self.alpha:.2f}, "
            f"monopoly {self.bm['p_monopoly'] * self.alpha:.2f}, ceiling shown {self.wtp:.2f}",
            "",
            "## PROMPT SENT",
            "",
            *(["```text", prompt, "```"] if keep_prompt else
              [f"_(omitted: identical in structure to period "
               f"{max(1, period - period % every) if every > 1 else 1}; "
               f"the market-history block is reproducible from periods.csv. "
               f"Use --full-prompt-every 1 to keep every prompt.)_",
               "",
               "Memory the agent was given this period:",
               "",
               "```text",
               "PLANS.txt:\n" + (self.memory[firm]["plans"] or "(empty)") +
               "\n\nINSIGHTS.txt:\n" + (self.memory[firm]["insights"] or "(empty)"),
               "```"]),
            "",
            "## RAW RESPONSE",
            "",
            "```text",
            parsed["raw"],
            "```",
            "",
        ]
        path.write_text("\n".join(body), encoding="utf-8")

    # ------------------------------------------------------------ the loop

    def make_client(self, firm):
        if self.cfg.mock:
            return ag.MockClient(seed=self.seed * 10 + firm)
        return ag.OpenRouterClient(
            model=self.cfg.model,
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_tokens,
        )

    def ask(self, firm, period):
        client = self.clients[firm]
        market = ag.format_market_data(self.history, firm, self.cfg.history_window)
        prompt = ag.build_prompt(
            self.prefix, self.cost, self.wtp,
            self.memory[firm]["plans"], self.memory[firm]["insights"], market,
        )
        t0 = time.time()
        parsed, stats, attempts = client.complete(prompt)
        self.save_transcript(period, firm, prompt, parsed, attempts,
                             time.time() - t0, stats.cost_usd)
        return parsed, stats, attempts

    def execute(self, budget_tracker):
        b, a = self.bm, self.alpha
        self.announce(
            f"\n=== RUN {self.run_id} === prefix {self.prefix}, alpha {a:g}, seed {self.seed}\n"
            f"    agent is told: cost ${self.cost:.2f}, ceiling ${self.wtp:.2f} "
            f"(= {self.wtp_mult:.2f} x monopoly price)\n"
            f"    benchmarks in these units: Nash ${b['p_nash'] * a:.2f}, "
            f"monopoly ${b['p_monopoly'] * a:.2f}"
        )

        for period in range(1, self.cfg.periods + 1):
            if budget_tracker.exceeded():
                self.stopped_reason = "budget"
                self.announce(f"    [{self.run_id}] stopping at period {period}: budget reached")
                break

            # Both agents decide simultaneously, on last period's information.
            with cf.ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(self.ask, firm, period): firm for firm in (0, 1)}
                results = {}
                for fut in cf.as_completed(futures):
                    firm = futures[fut]
                    try:
                        results[firm] = fut.result()
                    except Exception as exc:
                        self.stopped_reason = f"firm {firm + 1} failed: {exc}"
                        results[firm] = None

            if any(v is None for v in results.values()):
                self.announce(f"    [{self.run_id}] ABORTED at period {period}: {self.stopped_reason}")
                break

            prices, seconds, costs = [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]
            notes = ["", ""]
            for firm, (parsed, stats, attempts) in results.items():
                # Keep the price inside the bounds the agent was given, so a
                # stray parse cannot corrupt the market.  Clipping is logged.
                raw_price = parsed["parsed_price"]
                price = min(max(raw_price, self.cost), self.wtp)
                if abs(price - raw_price) > 1e-9:
                    self.log(f"    [clip] firm {firm + 1} asked {raw_price} -> {price}")
                prices[firm] = price
                seconds[firm] = stats.seconds
                costs[firm] = stats.cost_usd
                notes[firm] = first_line(parsed.get("thoughts"))
                self.memory[firm] = {"plans": parsed.get("plans"),
                                     "insights": parsed.get("insights")}
                self.stats.add(stats)
                budget_tracker.add(stats.cost_usd)

            q = self.env.quantities(prices)
            pi = self.env.profits(prices)
            self.history.append({
                "period": period,
                "prices": [float(x) for x in prices],
                "quantities": [float(x) for x in q],
                "profits": [float(x) for x in pi],
            })

            # ---- the human-readable per-period block
            self.log(
                f"\n  [{self.run_id}]  period {period:>3}/{self.cfg.periods}"
                f"   spent ${budget_tracker.total:.4f}"
            )
            for firm in (0, 1):
                self.log(
                    f"    firm {firm + 1}: price {prices[firm] / a:6.2f}"
                    f" | qty {q[firm]:6.2f} | profit {pi[firm] / a:6.2f}"
                    f" | {seconds[firm]:4.1f}s ${costs[firm]:.5f}"
                )
            self.log("    " + ruler(prices[0] / a, prices[1] / a,
                                    self.cost / a, self.wtp / a,
                                    b["p_nash"], b["p_monopoly"]))
            delta = collusion_index(pi.sum() / a / 2,
                                    b["profit_nash_per_firm"],
                                    b["profit_monopoly_total"] / 2)
            self.log(f"    collusion index (0=Nash, 1=monopoly): {delta:+.2f}")
            if notes[0]:
                self.log(f'    firm 1 thinks: "{notes[0]}"')
            if notes[1]:
                self.log(f'    firm 2 thinks: "{notes[1]}"')

        return self.summarise()

    # ------------------------------------------------------------ summary

    def summarise(self):
        a, b = self.alpha, self.bm
        w = min(self.cfg.avg_window, len(self.history))
        if w == 0:
            return None
        tail = self.history[-w:]
        p1 = sum(h["prices"][0] for h in tail) / w / a
        p2 = sum(h["prices"][1] for h in tail) / w / a
        pi1 = sum(h["profits"][0] for h in tail) / w / a
        pi2 = sum(h["profits"][1] for h in tail) / w / a
        row = {
            "run_id": self.run_id,
            "prefix": self.prefix,
            "rep": self.rep,
            "alpha": a,
            "seed": self.seed,
            "periods_completed": len(self.history),
            "avg_window": w,
            "price1": p1, "price2": p2,
            "profit1": pi1, "profit2": pi2,
            "profit_sum": pi1 + pi2,
            "profit_diff": pi1 - pi2,
            "p_nash": b["p_nash"], "p_monopoly": b["p_monopoly"],
            "profit_nash_per_firm": b["profit_nash_per_firm"],
            "profit_monopoly_total": b["profit_monopoly_total"],
            "collusion_index": collusion_index(
                (pi1 + pi2) / 2, b["profit_nash_per_firm"],
                b["profit_monopoly_total"] / 2),
            "llm_calls": self.stats.calls,
            "llm_retries": self.stats.retries,
            "cost_usd": self.stats.cost_usd,
            "stopped_reason": self.stopped_reason or "",
        }
        self.announce(
            f"    --> {self.run_id}: last {w} periods, prices {p1:.2f}/{p2:.2f} "
            f"(Nash {b['p_nash']:.2f}, monopoly {b['p_monopoly']:.2f}), "
            f"profit sum {pi1 + pi2:.1f} of {b['profit_monopoly_total']:.1f} max, "
            f"index {row['collusion_index']:+.2f}, cost ${self.stats.cost_usd:.4f}"
        )
        return row


class Budget:
    def __init__(self, limit):
        self.limit = limit
        self.total = 0.0
        self._lock = threading.Lock()

    def add(self, amount):
        with self._lock:
            self.total += amount

    def exceeded(self):
        return self.limit is not None and self.total >= self.limit


# ---------------------------------------------------------------- estimation


def estimate(cfg):
    """Price the experiment before running it, using OpenRouter's model catalogue."""
    import requests

    n_runs = len(cfg.prefixes) * cfg.runs * len(cfg.alphas)
    n_calls = n_runs * cfg.periods * 2
    # A prompt is roughly 500 tokens of boilerplate plus ~45 per history row.
    in_tok = n_calls * (500 + 45 * min(cfg.history_window, cfg.periods) * 0.6)
    out_tok = n_calls * 350

    print(f"Planned pilot:")
    print(f"  prefixes           {cfg.prefixes}")
    print(f"  runs per prefix    {cfg.runs} x alphas {cfg.alphas}  -> {n_runs} runs")
    print(f"  periods per run    {cfg.periods}  (paper: 300)")
    print(f"  LLM calls          {n_calls}  (paper: 25,200)")
    print(f"  rough tokens       {in_tok / 1e6:.2f}M in, {out_tok / 1e6:.2f}M out")

    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
        models = {m["id"]: m for m in r.json()["data"]}
    except Exception as exc:
        print(f"\n(could not fetch OpenRouter prices: {exc})")
        return
    m = models.get(cfg.model)
    if m is None:
        print(f"\nModel '{cfg.model}' not found on OpenRouter. Close matches:")
        key = cfg.model.split("/")[-1][:6]
        for mid in sorted(models):
            if key in mid:
                print("   ", mid)
        return
    pin = float(m["pricing"]["prompt"])
    pout = float(m["pricing"]["completion"])
    cost = in_tok * pin + out_tok * pout
    print(f"\n  model              {cfg.model}")
    print(f"  price              ${pin * 1e6:.3f}/M in, ${pout * 1e6:.3f}/M out")
    print(f"  ESTIMATED COST     ${cost:.3f}   (full paper scale would be "
          f"~${cost * 25200 / max(n_calls, 1):.2f} on this model)")
    print("\nThis is an estimate; the run reports actual billed cost from OpenRouter.")


# --------------------------------------------------------------------- main


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="openai/gpt-4o-mini",
                   help="OpenRouter model id (default: %(default)s)")
    p.add_argument("--prefixes", default="P1,P2", help="prompt prefixes to compare")
    p.add_argument("--runs", type=int, default=3, help="runs per prefix per alpha")
    p.add_argument("--periods", type=int, default=30, help="periods per run (paper: 300)")
    p.add_argument("--alphas", default="1", help="currency scales, e.g. 1,3.2,10")
    p.add_argument("--history-window", type=int, default=15,
                   help="rounds of history shown to the agent (paper: 100)")
    p.add_argument("--avg-window", type=int, default=10,
                   help="final periods averaged for the figure (paper: 50)")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=1200)
    p.add_argument("--budget-usd", type=float, default=2.0,
                   help="stop once this much has been spent (0 = no limit)")
    p.add_argument("--jobs", type=int, default=1, help="runs executed in parallel")
    p.add_argument("--full-prompt-every", type=int, default=10,
                   help="keep the full prompt in the transcript every N periods "
                        "(replies are always kept in full; 1 = keep every prompt)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--mock", action="store_true", help="offline fake agent, no API calls")
    p.add_argument("--estimate", action="store_true", help="price the run and exit")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--tag", default="", help="label appended to the output folder")
    cfg = p.parse_args()

    cfg.prefixes = [s.strip() for s in cfg.prefixes.split(",") if s.strip()]
    cfg.alphas = [float(s) for s in cfg.alphas.split(",") if s.strip()]
    if cfg.budget_usd == 0:
        cfg.budget_usd = None

    load_env(HERE / ".env")

    if cfg.estimate:
        estimate(cfg)
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}{'-' + cfg.tag if cfg.tag else ''}{'-mock' if cfg.mock else ''}"
    outdir = Path(cfg.out) / name
    outdir.mkdir(parents=True, exist_ok=True)

    env0 = Environment(alpha=1.0)
    meta = {"config": vars(cfg) | {"out": str(outdir)},
            "environment": env0.describe(),
            "started": stamp}
    (outdir / "config.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Output folder: {outdir}")
    print(f"Model: {'MOCK (offline, free)' if cfg.mock else cfg.model}   "
          f"budget: {'none' if cfg.budget_usd is None else f'${cfg.budget_usd:.2f}'}")
    print(f"Environment: Nash price {env0.benchmarks()['p_nash']:.4f}, "
          f"monopoly price {env0.benchmarks()['p_monopoly']:.4f}, "
          f"monopoly total profit {env0.benchmarks()['profit_monopoly_total']:.2f}")

    budget = Budget(cfg.budget_usd)
    console_lock = threading.Lock()
    jobs = []
    s = cfg.seed
    for prefix in cfg.prefixes:
        for alpha in cfg.alphas:
            for rep in range(1, cfg.runs + 1):
                s += 1
                jobs.append(Run(cfg, prefix, rep, alpha, s, outdir, console_lock))

    t0 = time.time()
    rows = []
    if cfg.jobs > 1:
        with cf.ThreadPoolExecutor(max_workers=cfg.jobs) as pool:
            for row in pool.map(lambda r: r.execute(budget), jobs):
                if row:
                    rows.append(row)
    else:
        for run in jobs:
            row = run.execute(budget)
            if row:
                rows.append(row)

    if rows:
        with open(outdir / "summary.csv", "w", newline="", encoding="utf-8") as fh:
            wtr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            wtr.writeheader()
            wtr.writerows(rows)

    period_rows = []
    for run in jobs:
        for h in run.history:
            period_rows.append({
                "run_id": run.run_id, "prefix": run.prefix, "alpha": run.alpha,
                "period": h["period"],
                "price1": h["prices"][0] / run.alpha, "price2": h["prices"][1] / run.alpha,
                "qty1": h["quantities"][0], "qty2": h["quantities"][1],
                "profit1": h["profits"][0] / run.alpha, "profit2": h["profits"][1] / run.alpha,
            })
    if period_rows:
        with open(outdir / "periods.csv", "w", newline="", encoding="utf-8") as fh:
            wtr = csv.DictWriter(fh, fieldnames=list(period_rows[0].keys()))
            wtr.writeheader()
            wtr.writerows(period_rows)

    print("\n" + "=" * 78)
    print(f"DONE in {time.time() - t0:.0f}s | actual spend ${budget.total:.4f} "
          f"| {sum(r['llm_calls'] for r in rows)} LLM calls "
          f"| {sum(r['llm_retries'] for r in rows)} retries")
    for prefix in cfg.prefixes:
        sub = [r for r in rows if r["prefix"] == prefix]
        if not sub:
            continue
        mp = sum(r["price1"] + r["price2"] for r in sub) / (2 * len(sub))
        mi = sum(r["collusion_index"] for r in sub) / len(sub)
        print(f"  {prefix}: {len(sub)} runs | mean price {mp:.3f} "
              f"| mean collusion index {mi:+.3f}")
    print(f"\nData:        {outdir / 'summary.csv'}")
    print(f"Transcripts: {outdir / 'transcripts'}")
    print(f"Next:        python src/plot_fig2.py \"{outdir}\"")
    print("=" * 78)


if __name__ == "__main__":
    main()
