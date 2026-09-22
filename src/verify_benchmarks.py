"""
Verify the Nash and monopoly benchmarks three independent ways.

The two numbers p_Nash = 1.4729 and p_M = 1.9250 are the entire measurement
apparatus of the paper: every claim is a position on the interval between them.
They come out of a numerical optimiser in econ.py, and a numerical optimiser is
exactly the kind of thing that can be quietly wrong. So we check them against
(1) symbolic first-order conditions differentiated by sympy, and (2) closed-form
markup formulas derived by hand from those conditions.

THE DERIVATION
--------------
Write the market share of firm i (so that q_i = beta * s_i):

    s_i = exp(u_i) / ( sum_j exp(u_j) + exp(u_0) ),      u_i = (a_i - p_i/alpha) / mu

The logit has two derivative identities that do all the work:

    d s_i / d p_i  = - s_i (1 - s_i) / (alpha mu)        raising my price loses me share
    d s_j / d p_i  = + s_i  s_j      / (alpha mu)        ...and hands some of it to j

NASH.  Firm i maximises its own profit, taking p_{-i} as fixed:

    d/dp_i [ (p_i - alpha c) beta s_i ] = 0
    =>  s_i - (p_i - alpha c) s_i (1 - s_i)/(alpha mu) = 0
    =>  p_i - alpha c = alpha mu / (1 - s_i)                            (*)

MONOPOLY.  One owner maximises the sum, so the term that Nash ignored -- the
share handed to the rival -- now appears with a plus sign:

    d/dp_i [ sum_j (p_j - alpha c) beta s_j ] = 0
    =>  s_i - (p_i - alpha c) s_i(1-s_i)/(alpha mu) + sum_{j!=i} (p_j - alpha c) s_i s_j/(alpha mu) = 0

At a symmetric optimum (p_j = p, s_j = s for all firms):

    1 = (p - alpha c) [ (1 - s) - (n-1)s ] / (alpha mu)
    =>  p - alpha c = alpha mu / (1 - n s) = alpha mu / s_0             (**)

READING (*) AND (**)
--------------------
Both are markups over marginal cost, and they differ only in the denominator:

    Nash markup     = alpha mu / (1 - s_i)     ... 1 - s_i = everyone else, INCLUDING the rival
    Monopoly markup = alpha mu / s_0           ... s_0     = the outside option ONLY

That single substitution is the whole economics of the paper. Under Nash, firm i
treats demand lost to the rival as a real cost of raising its price, so it prices
low. The monopolist owns the rival, so demand moving between the two products is
not a loss at all -- the only thing that genuinely punishes a price rise is the
customer who walks away and buys nothing. Fewer competitors to fear means a
bigger markup, and the gap between the two is precisely the spillover that a
colluding pair would have to internalise without being allowed to merge.

Note what (**) implies: with no outside option (s_0 -> 0) the monopoly price is
unbounded, which is why a_0 has to be in the model at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import sympy as sp

sys.path.insert(0, str(Path(__file__).parent))
from econ import Environment

ENV = Environment()          # a_i = 2, a_0 = 0, mu = 0.25, c = 1, alpha = 1, beta = 100
TOL = 1e-6


def banner(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


# --------------------------------------------------------------- 1. symbolic


def symbolic_check():
    """Differentiate the profit functions with sympy and solve the FOCs exactly.

    Nothing here reuses econ.py's optimiser, so agreement is real evidence and
    not a restatement of the same computation.
    """
    banner("1. SYMBOLIC -- sympy differentiates the profit functions itself")

    p1, p2 = sp.symbols("p1 p2", positive=True)
    a, a0, mu, c, alpha, beta = 2, 0, sp.Rational(1, 4), 1, 1, 100

    def u(p):
        return (a - p / alpha) / mu

    den = sp.exp(u(p1)) + sp.exp(u(p2)) + sp.exp(sp.Rational(a0) / mu)
    q1 = beta * sp.exp(u(p1)) / den
    q2 = beta * sp.exp(u(p2)) / den
    pi1 = (p1 - alpha * c) * q1
    pi2 = (p2 - alpha * c) * q2

    # Nash: each firm differentiates ONLY its own profit, w.r.t. ONLY its own price.
    nash = sp.nsolve([sp.diff(pi1, p1), sp.diff(pi2, p2)], [p1, p2], [1.5, 1.5], prec=25)
    # Monopoly: one owner differentiates the SUM w.r.t. BOTH prices.
    total = pi1 + pi2
    mono = sp.nsolve([sp.diff(total, p1), sp.diff(total, p2)], [p1, p2], [2.0, 2.0], prec=25)

    p_nash_sym, p_mono_sym = float(nash[0]), float(mono[0])
    print(f"  symbolic FOC roots:  p_Nash = {p_nash_sym:.10f}   p_M = {p_mono_sym:.10f}")

    b = ENV.benchmarks()
    print(f"  econ.py optimiser:   p_Nash = {b['p_nash']:.10f}   p_M = {b['p_monopoly']:.10f}")
    ok = (abs(p_nash_sym - b["p_nash"]) < TOL) and (abs(p_mono_sym - b["p_monopoly"]) < TOL)
    print(f"  -> {'AGREE' if ok else 'DISAGREE'}")

    # Second-order check: a root of the FOC could be a minimum or a saddle.
    d2_nash = float(sp.diff(pi1, p1, 2).subs({p1: nash[0], p2: nash[1]}))
    hess = sp.hessian(total, (p1, p2)).subs({p1: mono[0], p2: mono[1]})
    # sympy's exact eigensolver exhausts precision on these near-degenerate
    # entries; the Hessian is numeric by this point, so hand it to numpy.
    eig = sorted(np.linalg.eigvalsh(np.array(hess.evalf(), dtype=float)))
    print(f"\n  second-order conditions (these confirm maxima, not minima):")
    print(f"    Nash     d2(pi_1)/dp_1^2 = {d2_nash:+.4f}   (< 0 required)")
    print(f"    Monopoly Hessian eigenvalues = {eig[0]:+.4f}, {eig[1]:+.4f}   (both < 0 required)")
    ok &= d2_nash < 0 and all(e < 0 for e in eig)
    return ok


# ------------------------------------------------------------ 2. closed form


def closed_form_check():
    """Check the hand-derived markup formulas (*) and (**) from the docstring."""
    banner("2. CLOSED FORM -- the markup formulas derived by hand")

    env, b = ENV, ENV.benchmarks()
    alpha, mu, c = env.alpha, env.mu, env.c[0]
    n = env.n_firms

    pn = np.array([b["p_nash"] * alpha] * n)
    pm = np.array([b["p_monopoly"] * alpha] * n)

    s_nash = env.quantities(pn) / env.beta          # market shares at the Nash prices
    s_mono = env.quantities(pm) / env.beta
    s0_nash, s0_mono = 1 - s_nash.sum(), 1 - s_mono.sum()

    pred_nash = alpha * c + alpha * mu / (1 - s_nash[0])
    pred_mono = alpha * c + alpha * mu / s0_mono

    print(f"  at the Nash prices:      own share s_i = {s_nash[0]:.6f},  outside option s_0 = {s0_nash:.6f}")
    print(f"  at the monopoly prices:  own share s_i = {s_mono[0]:.6f},  outside option s_0 = {s0_mono:.6f}")
    print()
    print(f"  (*)  p_Nash = c + mu/(1 - s_i) = 1 + 0.25/{1 - s_nash[0]:.6f} = {pred_nash:.10f}")
    print(f"       solver                                                  = {b['p_nash']:.10f}")
    print(f"  (**) p_M    = c + mu/s_0       = 1 + 0.25/{s0_mono:.6f} = {pred_mono:.10f}")
    print(f"       solver                                                  = {b['p_monopoly']:.10f}")

    ok = abs(pred_nash - b["p_nash"]) < TOL and abs(pred_mono - b["p_monopoly"]) < TOL
    print(f"  -> {'AGREE' if ok else 'DISAGREE'}")

    print(f"\n  the economics, in one line:")
    print(f"    Nash denominator     1 - s_i = {1 - s_nash[0]:.4f}   (rival {s_nash[1]:.4f} + outside {s0_nash:.4f})")
    print(f"    Monopoly denominator s_0     = {s0_mono:.4f}   (outside option alone)")
    print(f"    -> a smaller denominator is a bigger markup: {mu/s0_mono:.4f} vs {mu/(1-s_nash[0]):.4f}")
    print(f"    The monopolist drops the rival's share from the denominator because it")
    print(f"    owns the rival: demand moving between the two products is not a loss.")
    return ok


# ------------------------------------------------------- 3. brute force / lit


def brute_force_check():
    """Two blunt instruments: a grid search, and the published literature values."""
    banner("3. BRUTE FORCE -- grid search, deviation test, and Calvano's numbers")

    env, b = ENV, ENV.benchmarks()

    # (a) Nash: no unilateral deviation on a fine grid can beat the Nash price.
    pn = np.array([b["p_nash"]] * 2)
    grid = np.linspace(1.0, 4.0, 60001)
    prof = [(env.profits([g, pn[1]])[0]) for g in grid]
    best = grid[int(np.argmax(prof))]
    gain = max(prof) - env.profits(pn)[0]
    print(f"  (a) best unilateral deviation against p_Nash: {best:.5f} "
          f"(Nash price {b['p_nash']:.5f}), profit gain {gain:+.3e}")
    ok = abs(best - b["p_nash"]) < 1e-3 and gain < 1e-6

    # (b) Monopoly: a 2-D grid over joint prices.
    g = np.linspace(1.5, 2.5, 601)
    P1, P2 = np.meshgrid(g, g)
    tot = np.zeros_like(P1)
    for i in range(P1.shape[0]):
        for j in range(P1.shape[1]):
            tot[i, j] = env.profits([P1[i, j], P2[i, j]]).sum()
    idx = np.unravel_index(np.argmax(tot), tot.shape)
    print(f"  (b) 2-D grid maximum of joint profit at ({P1[idx]:.4f}, {P2[idx]:.4f}), "
          f"total {tot[idx]:.4f}  (solver: {b['p_monopoly']:.4f}, {b['profit_monopoly_total']:.4f})")
    ok &= abs(P1[idx] - b["p_monopoly"]) < 2e-3 and abs(tot[idx] - b["profit_monopoly_total"]) < 1e-3

    # (c) The published values Calvano et al. (2020b) report for this calibration.
    lit = Environment(beta=1.0).benchmarks()
    published = {"p_nash": 1.4729, "p_monopoly": 1.9249,
                 "profit_nash_per_firm": 0.2229, "profit_monopoly_total": 0.6750}
    print(f"\n  (c) against Calvano et al. (2020b), alpha = beta = 1:")
    for k, want in published.items():
        good = abs(lit[k] - want) < 1e-3
        ok &= good
        print(f"        {k:24s} ours {lit[k]:8.4f}   published {want:8.4f}   {'OK' if good else 'MISMATCH'}")

    print(f"  -> {'AGREE' if ok else 'DISAGREE'}")
    return ok


def main():
    results = [symbolic_check(), closed_form_check(), brute_force_check()]
    banner("VERDICT")
    names = ["symbolic FOCs (sympy)", "closed-form markups", "brute force + literature"]
    for name, r in zip(names, results):
        print(f"  {name:28s} {'PASS' if r else 'FAIL'}")
    b = ENV.benchmarks()
    print(f"\n  p_Nash = {b['p_nash']:.4f}   p_M = {b['p_monopoly']:.4f}")
    print(f"  pi_Nash/firm = {b['profit_nash_per_firm']:.2f}   pi_M total = {b['profit_monopoly_total']:.2f}")
    print("\n  " + ("ALL THREE METHODS AGREE" if all(results) else "*** SOMETHING IS WRONG ***"))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
