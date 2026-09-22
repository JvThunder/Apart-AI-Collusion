"""
Economic environment for the duopoly pilot.

This is the Calvano et al. (2020b) logit-demand Bertrand environment, exactly as
described in Section 2.1 of Fish, Gonczarowski & Shorrer, "Algorithmic Collusion
by Large Language Models".

Demand for firm i, given prices p_1..p_n:

                 exp( (a_i - p_i/alpha) / mu )
    q_i = beta * ------------------------------------------------
                 sum_j exp( (a_j - p_j/alpha) / mu ) + exp(a_0/mu)

    pi_i = (p_i - alpha * c_i) * q_i

Reading the parts:
  * a_i   vertical quality of product i  (higher a_i -> more demand at same price)
  * a_0   the outside option ("buy nothing"); it is the only reason total demand
          is not constant, i.e. the only reason the two firms jointly care about
          the price level rather than only about who is cheaper
  * mu    horizontal differentiation.  mu -> 0 turns the logit into a hard argmax
          (textbook Bertrand, price = cost).  Larger mu means customers care less
          about price differences, so each firm keeps some demand even when it is
          the expensive one -- that is what leaves room for prices above cost.
  * alpha currency unit, beta quantity unit.  Neither changes the economics; they
          exist only because an LLM is *not* unit-neutral (it reads "$1.50" and
          "80.4 units" differently from "$0.15" and "0.804 units").

Two benchmarks matter for the figure:
  p_Nash  the one-shot Bertrand-Nash price: each firm best-responds to the other.
          This is the competitive benchmark -- what non-colluding firms should do.
  p_M     the price a single monopolist owning both firms would set on both goods.
          It is higher, because the monopolist internalises the demand it steals
          from itself when it undercuts.

Anything strictly between them is "supracompetitive": higher than competition
predicts, without anyone having been told to collude.  That gap is the whole
finding of the paper, and the y-axis of the figure we are trying to reproduce.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
from scipy.optimize import minimize, minimize_scalar


@dataclass(frozen=True)
class Environment:
    """Calvano-style logit duopoly.  Defaults are the paper's main specification."""

    n_firms: int = 2
    a: tuple = (2.0, 2.0)   # vertical quality per firm
    a0: float = 0.0         # outside option
    mu: float = 0.25        # horizontal differentiation
    c: tuple = (1.0, 1.0)   # marginal cost, in units of alpha
    alpha: float = 1.0      # currency scale
    beta: float = 100.0     # quantity scale

    # ---------------------------------------------------------------- demand

    def quantities(self, prices) -> np.ndarray:
        p = np.asarray(prices, dtype=float)
        util = (np.asarray(self.a) - p / self.alpha) / self.mu
        # subtract the max before exponentiating: same ratio, no overflow
        m = max(util.max(), self.a0 / self.mu)
        num = np.exp(util - m)
        den = num.sum() + np.exp(self.a0 / self.mu - m)
        return self.beta * num / den

    def profits(self, prices) -> np.ndarray:
        p = np.asarray(prices, dtype=float)
        return (p - self.alpha * np.asarray(self.c)) * self.quantities(p)

    # ------------------------------------------------------------ benchmarks

    def best_response(self, i: int, prices) -> float:
        """Price that maximises firm i's profit holding the rivals' prices fixed."""
        p = np.asarray(prices, dtype=float).copy()

        def neg(pi):
            p[i] = pi
            return -self.profits(p)[i]

        lo, hi = self.alpha * self.c[i], self.alpha * 10.0
        return float(minimize_scalar(neg, bounds=(lo, hi), method="bounded").x)

    def nash_prices(self, tol: float = 1e-10, max_iter: int = 1000) -> np.ndarray:
        """One-shot Bertrand-Nash prices, by iterating best responses to a fixed point.

        A fixed point of "everyone best-responds" *is* a Nash equilibrium, by
        definition.  In this environment the best-response map is a contraction,
        so simply iterating it converges; no equilibrium-selection worries.
        """
        p = np.array([self.alpha * ci * 2.0 for ci in self.c])
        for _ in range(max_iter):
            p_new = np.array([self.best_response(i, p) for i in range(self.n_firms)])
            if np.max(np.abs(p_new - p)) < tol:
                return p_new
            p = p_new
        raise RuntimeError("Nash iteration did not converge")

    def monopoly_prices(self) -> np.ndarray:
        """Prices a single owner of both firms would set, maximising total profit."""
        x0 = np.array([self.alpha * 2.0] * self.n_firms)
        res = minimize(
            lambda p: -self.profits(p).sum(),
            x0,
            bounds=[(self.alpha * ci, self.alpha * 10.0) for ci in self.c],
            method="L-BFGS-B",
            options={"ftol": 1e-14, "gtol": 1e-12},
        )
        return res.x

    # -------------------------------------------------------------- summary

    def benchmarks(self) -> dict:
        """Everything the figure needs, in alpha-normalised units (alpha = 1 terms)."""
        pn, pm = self.nash_prices(), self.monopoly_prices()
        return {
            "p_nash": float(pn[0] / self.alpha),
            "p_monopoly": float(pm[0] / self.alpha),
            "profit_nash_per_firm": float(self.profits(pn)[0] / self.alpha),
            "profit_monopoly_total": float(self.profits(pm).sum() / self.alpha),
        }

    def describe(self) -> dict:
        d = asdict(self)
        d.update(self.benchmarks())
        return d


def _self_test() -> None:
    """Check our environment against the numbers Calvano et al. (2020b) report.

    With a_i = 2, a_0 = 0, mu = 0.25, c = 1 (and alpha = beta = 1) the literature
    values are p_Nash = 1.4729, p_M = 1.9249, and per-firm profits 0.2229 (Nash)
    and 0.3375 (monopoly).  If this passes, the environment is right, and any
    later surprise is about the LLMs and not about our demand curve.
    """
    env = Environment(beta=1.0)
    b = env.benchmarks()
    expected = {
        "p_nash": 1.4729,
        "p_monopoly": 1.9249,
        "profit_nash_per_firm": 0.2229,
        "profit_monopoly_total": 2 * 0.3375,
    }
    print("Calvano benchmark check (alpha = beta = 1):")
    ok = True
    for k, want in expected.items():
        got = b[k]
        good = abs(got - want) < 1e-3
        ok &= good
        print(f"  {k:24s} ours = {got:8.4f}   paper = {want:8.4f}   {'OK' if good else 'MISMATCH'}")

    # alpha/beta really are pure units: normalised benchmarks must not move.
    scaled = Environment(alpha=3.2, beta=100.0).benchmarks()
    for k in ("p_nash", "p_monopoly"):
        good = abs(scaled[k] - b[k]) < 1e-6
        ok &= good
        print(f"  scale-invariance {k:12s} alpha=3.2 -> {scaled[k]:8.4f}   {'OK' if good else 'MISMATCH'}")

    env100 = Environment()
    b100 = env100.benchmarks()
    print(f"\nPilot environment (alpha=1, beta=100), the units the LLM actually sees:")
    print(f"  p_Nash                = {b100['p_nash']:.4f}")
    print(f"  p_Monopoly            = {b100['p_monopoly']:.4f}")
    print(f"  profit_Nash  per firm = {b100['profit_nash_per_firm']:.2f}")
    print(f"  profit_Monop  total   = {b100['profit_monopoly_total']:.2f}")
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))


if __name__ == "__main__":
    _self_test()
