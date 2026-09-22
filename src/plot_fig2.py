"""
Rebuild Figure 2 of the paper from a pilot run.

    python src/plot_fig2.py results/<folder>

Left panel -- Pricing behaviour.
    One point per run: firm 1's average price against firm 2's.  Because the two
    firms are symmetric, points near the 45-degree line mean the two agents
    settled on the *same* price without ever talking.  The red dashed cross is
    the Bertrand-Nash price (what competition predicts) and the green dotted
    cross is the monopoly price.  Points in the upper-right region are the
    result: supracompetitive prices, reached autonomously.

Right panel -- Profits earned.
    Same runs, re-plotted as (profit difference, profit sum).  This rotation is
    what makes the panel readable: the vertical axis is total harm to consumers
    (industry profit), the horizontal axis is how that profit split between the
    two firms.  A point high up and near x = 0 means "both firms did well, and
    equally well" -- the signature of sustained tacit collusion rather than one
    agent simply beating the other.
    The two red dashed lines are the Nash isoprofit lines: on the left line firm
    1 earns exactly its Nash profit, on the right line firm 2 does.  Their V
    shape encloses the region where BOTH firms beat competition.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

STYLE = {
    # Blue squares for P1, orange triangles for P2, as in the paper.
    "P1": {"color": "#1f4e9c", "marker": "s", "label": "P1 vs. P1"},
    "P2": {"color": "#e07b1f", "marker": "^", "label": "P2 vs. P2"},
    "P0": {"color": "#4c9c4c", "marker": "o", "label": "P0 vs. P0"},
}
NASH_KW = {"color": "#cc2222", "linestyle": "--", "linewidth": 1.2, "zorder": 1}
MONO_KW = {"color": "#22aa55", "linestyle": ":", "linewidth": 1.6, "zorder": 1}


def load(folder: Path):
    path = folder / "summary.csv"
    if not path.exists():
        sys.exit(f"No summary.csv in {folder} -- run src/run_duopoly.py first.")
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k, v in r.items():
            if k not in ("run_id", "prefix", "stopped_reason"):
                try:
                    r[k] = float(v)
                except (TypeError, ValueError):
                    pass
    return rows


def make_figure(rows, folder: Path, title_note="", suptitle=True, out_name="fig2_pilot"):
    p_nash = rows[0]["p_nash"]
    p_mono = rows[0]["p_monopoly"]
    pi_nash = rows[0]["profit_nash_per_firm"]
    pi_mono_total = rows[0]["profit_monopoly_total"]
    prefixes = [p for p in ("P1", "P2", "P0") if any(r["prefix"] == p for r in rows)]

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13, 5.6))

    # ------------------------------------------------------------ left panel
    prices = [r["price1"] for r in rows] + [r["price2"] for r in rows]
    lo = min(prices + [p_nash]) - 0.12
    hi = max(prices + [p_mono]) + 0.12
    axL.plot([lo, hi], [lo, hi], color="0.85", linewidth=1, zorder=0)
    for v in (p_nash,):
        axL.axvline(v, **NASH_KW)
        axL.axhline(v, **NASH_KW)
    for v in (p_mono,):
        axL.axvline(v, **MONO_KW)
        axL.axhline(v, **MONO_KW)
    for pref in prefixes:
        sub = [r for r in rows if r["prefix"] == pref]
        axL.scatter([r["price1"] for r in sub], [r["price2"] for r in sub],
                    s=62, alpha=0.85, edgecolors="white", linewidths=0.6,
                    zorder=3, **STYLE[pref])
    axL.set_xlim(lo, hi)
    axL.set_ylim(lo, hi)
    axL.set_xlabel("Firm 1 average price (final periods)")
    axL.set_ylabel("Firm 2 average price (final periods)")
    axL.set_title("Pricing behaviour")
    axL.legend(loc="lower right", frameon=False)
    for v, name, kw in ((p_nash, "$p^{Nash}$", NASH_KW), (p_mono, "$p^{M}$", MONO_KW)):
        axL.annotate(name, xy=(v, hi), xytext=(v + 0.01, hi - 0.06),
                     color=kw["color"], fontsize=11)

    # ----------------------------------------------------------- right panel
    diffs = [r["profit_diff"] for r in rows]
    sums = [r["profit_sum"] for r in rows]
    dlim = max(6.0, max(abs(d) for d in diffs) * 1.25)
    slo = min(sums + [2 * pi_nash]) - 5
    shi = max(sums + [pi_mono_total]) + 5

    # Nash isoprofit lines in (diff, sum) coordinates:
    #   profit1 = (sum + diff)/2 = pi_nash  ->  sum = 2*pi_nash - diff
    #   profit2 = (sum - diff)/2 = pi_nash  ->  sum = 2*pi_nash + diff
    xs = [-dlim, dlim]
    axR.plot(xs, [2 * pi_nash - x for x in xs], **NASH_KW)
    axR.plot(xs, [2 * pi_nash + x for x in xs], **NASH_KW)
    axR.axhline(pi_mono_total, **MONO_KW)
    for pref in prefixes:
        sub = [r for r in rows if r["prefix"] == pref]
        axR.scatter([r["profit_diff"] for r in sub], [r["profit_sum"] for r in sub],
                    s=62, alpha=0.85, edgecolors="white", linewidths=0.6,
                    zorder=3, **STYLE[pref])
    axR.set_xlim(-dlim, dlim)
    axR.set_ylim(slo, shi)
    axR.set_xlabel(r"Average difference in profits  $\pi_1 - \pi_2$")
    axR.set_ylabel(r"Average sum of profits  $\pi_1 + \pi_2$")
    axR.set_title("Profits earned")
    axR.legend(loc="lower right", frameon=False)
    box = {"boxstyle": "square,pad=0.15", "facecolor": "white", "edgecolor": "none"}
    axR.annotate(r"$\pi_1 = $Nash", xy=(0.02, 0.55), xycoords="axes fraction",
                 color=NASH_KW["color"], fontsize=10, bbox=box)
    axR.annotate(r"$\pi_2 = $Nash", xy=(0.83, 0.55), xycoords="axes fraction",
                 color=NASH_KW["color"], fontsize=10, bbox=box)
    axR.annotate(r"$\pi^{M}$", xy=(-dlim * 0.95, pi_mono_total + 0.6),
                 color=MONO_KW["color"], fontsize=11, bbox=box)

    for ax in (axL, axR):
        ax.grid(alpha=0.18, linewidth=0.6)
        ax.set_axisbelow(True)

    if suptitle:
        fig.suptitle(f"Duopoly pilot: {len(rows)} runs{title_note}", fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
    else:
        # For a slide, the deck's frame title already says what this is.
        fig.tight_layout()

    out = folder / f"{out_name}.png"
    fig.savefig(out, dpi=170)
    fig.savefig(folder / f"{out_name}.pdf")
    print(f"Wrote {out}")
    return out


def print_table(rows):
    print("\nPer-run summary (all values normalised by alpha):")
    print(f"  {'run':<18} {'price1':>7} {'price2':>7} {'profit1':>8} {'profit2':>8} "
          f"{'sum':>7} {'index':>7}")
    for r in sorted(rows, key=lambda r: (r["prefix"], r["run_id"])):
        print(f"  {r['run_id']:<18} {r['price1']:>7.2f} {r['price2']:>7.2f} "
              f"{r['profit1']:>8.2f} {r['profit2']:>8.2f} {r['profit_sum']:>7.1f} "
              f"{r['collusion_index']:>+7.2f}")

    print(f"\n  Benchmarks: Nash price {rows[0]['p_nash']:.3f}, "
          f"monopoly price {rows[0]['p_monopoly']:.3f}, "
          f"Nash profit/firm {rows[0]['profit_nash_per_firm']:.2f}, "
          f"monopoly total {rows[0]['profit_monopoly_total']:.2f}")

    by = {}
    for r in rows:
        by.setdefault(r["prefix"], []).append(r)
    print("\nBy prompt prefix:")
    for pref, sub in sorted(by.items()):
        mp = sum(r["price1"] + r["price2"] for r in sub) / (2 * len(sub))
        mi = sum(r["collusion_index"] for r in sub) / len(sub)
        print(f"  {pref}: n={len(sub):>2}  mean price {mp:.3f}  "
              f"mean collusion index {mi:+.3f}")

    if {"P1", "P2"} <= by.keys():
        try:
            from scipy import stats
            # One firm per run, as in the paper, to avoid double-counting a run.
            a = [r["price1"] for r in by["P1"]]
            b = [r["price2"] for r in by["P2"]]
            t, p = stats.ttest_ind(a, b, equal_var=False)
            print(f"\n  P1 vs P2 price difference: {sum(a)/len(a) - sum(b)/len(b):+.3f} "
                  f"(Welch t = {t:.2f}, p = {p:.2e}, n = {len(a)} vs {len(b)})")
            if min(len(a), len(b)) < 7:
                print("  Few runs per arm -- this test is underpowered; read it as a "
                      "check that the\n  pipeline computes it, not as evidence.")
            else:
                print(f"  The paper uses 21 runs per arm and reports p < 0.00001 for "
                      f"this comparison.")
        except ImportError:
            pass


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if folder is None:
        results = Path(__file__).parent.parent / "results"
        candidates = sorted(p for p in results.glob("*") if (p / "summary.csv").exists())
        if not candidates:
            sys.exit("No results folders found. Run: python src/run_duopoly.py --mock")
        folder = candidates[-1]
        print(f"(no folder given; using latest: {folder})")
    rows = load(folder)
    note = ""
    cfg = folder / "config.json"
    if cfg.exists():
        import json
        c = json.loads(cfg.read_text(encoding="utf-8"))["config"]
        note = (f", {c['periods']} periods, model "
                f"{'MOCK' if c['mock'] else c['model']}")
    print_table(rows)
    make_figure(rows, folder, note)
    # A second copy without the redundant suptitle, for dropping into slides.
    make_figure(rows, folder, suptitle=False, out_name="fig2_pilot_slide")


if __name__ == "__main__":
    main()
