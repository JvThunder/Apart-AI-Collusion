# Reading plan

Ordered by what pays off most given where this project already stands, not by
topic or chronology.

**What you already own.** You have re-derived the Calvano environment from first
principles (`src/econ.py`, verified three ways), run 20 × 300 periods on
`gpt-4o-mini`, and produced three things that are yours rather than the paper's:

1. **The P2 inversion.** P1 reaches 92% of monopoly profit; P2 collapses *below*
   the competitive price to 1.087 against a unit cost of 1.00. The paper has both
   prompts supracompetitive.
2. **Round-number focality.** 26.6% of P1 prices in periods 251–300 are exactly
   2.00, when the monopoly price is 1.925.
3. **The identification problem.** Table 1's positive coefficient on the rival's
   lagged price cannot separate punishment from best response, because best
   responses slope up at +0.42 here — and the implied long-run response (0.20)
   sits *below* that myopic benchmark.

Everything below is sequenced to turn one of those three into a result.

> Caveat: I have these papers from abstracts and search results, not from reading
> them. Treat the "what to extract" lines as what to look for, not as findings.

---

## Start here — three papers, one afternoon

### 1. Garra (2026), *Mitigating Emergent Collusion in LLM Pricing Agents*
[arXiv:2609.13037](https://arxiv.org/abs/2609.13037) · ~30 min

**Why first.** It is the closest thing to your addendum that exists: an
independent reproduction of Fish et al. on DeepSeek-V3.1, reporting the same
P1 > P2 direction with "less monopoly-like" levels than the GPT-4 original. Read
it before you write anything up, so you know what is already claimed.

**What to extract.** Whether their P2 arm merely prices lower or actually
collapses below Nash as yours did. If it only prices lower, your inversion is a
`gpt-4o-mini` result and worth isolating. If it collapses too, you have a
two-model pattern and a much stronger claim.

**Unlocks.** Decides whether the addendum's headline is "prompt sensitivity is
model-dependent" or "P2 is a competition instruction in disguise."

### 2. Keppo, Li, Tsoukalas & Yuan (2026), *On the Fragility of AI Agent Collusion*
[arXiv:2603.20281](https://arxiv.org/abs/2603.20281) · ~1–2 h

**Why second.** It has already run several experiments your Discussion 6 proposes
— more competing agents, LLM versus Q-learner, model-size asymmetry — and reports
a specific, quantitative fragility frontier (patience heterogeneity cuts price
lift from 22% to 10%; asymmetric data access to 7%).

**What to extract.** Their heterogeneity taxonomy, and the leader-follower
finding: 32B versus 14B does *not* break collusion, it stabilises it through
price leadership. Compare that against your asymmetric P1 runs (one firm at 1.71,
the other at 2.06, profits 45 vs 17) — you may be seeing the same phenomenon
between two *identical* agents, which would be new.

**Unlocks.** Tells you which cells of the n-sweep are already occupied, so your
version tests something unclaimed.

### 3. Eschenbaum, Mellgren & Zahn (2022), *Robust Algorithmic Collusion*
[arXiv:2201.00345](https://arxiv.org/abs/2201.00345) · ~1 h

**Why third.** The rematching result your 1.2 slide is built on. Short, clean, and
pre-LLM, so the mechanism is visible: policies overfit their training rival, and
the breakdown is permanent.

**What to extract.** Precisely *how* they rematch, so your replacement experiment
is comparable rather than merely analogous.

**Unlocks.** The experiment specified on the 1.2 slide — swap firm 2's model at
period 150, three arms (keep memory / wipe memory / no swap). Your prediction is
that LLM collusion survives because the convention lives in the context rather
than the weights. This is the cheapest genuinely novel experiment available to
you, and the harness already supports it.

---

## Then: the thread most likely to become your own paper

### 4. Aharon, La Malfa, Wooldridge & Kraus (2026), *Tacit Coordination of Large Language Models*
[arXiv:2601.22184](https://arxiv.org/abs/2601.22184) · ~1–2 h

**Why this matters most.** This is the paper your round-number result belongs to.
They study focal points in LLMs across 20+ models and find coordination without
communication that often matches or beats humans — but failures on numerical
salience specifically.

**What to extract.** Their focal-point measurement, and whether "numerical common
sense" failures predict *which* number agents land on. Your 2.00 finding is a
focal point appearing in a setting with a well-defined optimum nearby (1.925),
which is a sharper test than an abstract coordination game: coordinating on 2.00
costs the firms almost nothing, so salience wins where the stakes are flat.

**Unlocks.** A concrete study — sweep the monopoly price across runs (vary `a_0`
or `mu` in `econ.py`) so p^M lands at 1.62, 1.925, 2.31, and ask whether agents
track p^M or snap to the nearest round number. That separates optimisation from
salience, cleanly, and nobody has run it in a pricing environment.

### 5. Rippin et al. (2026), *Tool Use Enables Undetectable Steganography in Multi-Agent LLM Systems*
[arXiv:2606.28425](https://arxiv.org/abs/2606.28425) · skim, ~45 min

**Why.** They frame tacit coordination explicitly as a Schelling-point problem and
build metrics for whether independent agents converge on compatible schemes. That
is the same construct as your round-number convergence, measured properly.

**What to extract.** Their coordination metric. Then note your own anti-example:
P2 runs also converge on a focal price (1.00, marginal cost) — but that one is
*competitive*. Salience without collusion is a useful negative control and they
may not have one.

---

## Then: the detection thread, where your critique has teeth

### 6. Bonjour et al. (2022), *Information-Theoretic Approach to Detect Collusion in Multi-Agent Games*
[PMLR v180](https://proceedings.mlr.press/v180/bonjour22a/bonjour22a.pdf) · ~1–2 h

**Why.** The formal machinery for a better detector than a lagged-price
regression: mutual information between agents' actions, with *net influence*
subtracting the maximum influence any other player has, specifically to strip out
game-induced dependence.

**What to extract.** How they construct the null. Their subtraction is the same
move your critique demands — and your version of the null is sharper, because in
this environment you can *simulate* it: myopic best-responders in the same demand
system give an exact no-collusion baseline.

**Unlocks.** The strongest version of your 1.3/1.4 point: run their measure on
your P1 runs, your P2 runs, and a simulated myopic pair. If it cannot separate P1
from the myopic baseline, the identification problem is general rather than a
quirk of Table 1.

### 7. Rose et al. (2026), *Detecting Multi-Agent Collusion Through Multi-Agent Interpretability*
[arXiv:2604.01151](https://arxiv.org/abs/2604.01151) · ~1 h

**Why.** Activation probes aggregated across agents, with a stated transfer
result (1.00 AUROC in-distribution, 0.60–0.86 zero-shot out of it). Fish's
price-war classifier is the same idea one level up, on stated text.

**What to extract.** The distribution-shift numbers. A detector that holds
in-distribution and degrades under shift is exactly the epistemic-uncertainty
problem your lab works on: the interesting question is whether the probe *knows*
when it has left its distribution.

**Unlocks.** The natural EPIC-flavoured project — run the text classifier and an
activation probe on the same transcripts and ask which one is better calibrated
about its own reliability, not which is more accurate.

---

## Then: interventions, read as a group

### 8. Agrawal et al. (2025), *Evaluating LLM Agent Collusion in Double Auctions*
[arXiv:2507.01413](https://arxiv.org/abs/2507.01413) · skim, ~45 min

The communication-channel lever. Fish et al. deliberately removed communication,
so this is the natural complement: coordination scores rise from ~1.8 to ~3.5 when
sellers can message, with no instruction to coordinate.

### 9. Bracale Syrnikov et al. (2026), *Institutional AI: Governing LLM Collusion in Multi-Agent Cournot Markets*
[arXiv:2601.11369](https://arxiv.org/abs/2601.11369) · skim, ~45 min

The payoff/mechanism lever, and a direct statement that declarative prohibitions
fail under optimisation pressure — which is P3's failure, generalised. Read
alongside your own finding that raising the outside option shrinks the collusion
prize by 99% without touching the agent.

### 10. Tomašev et al. (2026)
[arXiv:2512.16856](https://arxiv.org/abs/2512.16856) · skim before the sprint

The sprint's own counterpoint on markets in multi-agent systems. Worth having in
hand so the room has an opposing view to argue against.

---

## Reference, not reading

- **Calvano et al. (2020)**, [10.1257/aer.20190623](https://doi.org/10.1257/aer.20190623)
  — you have already re-derived the environment and matched its published
  benchmarks to four decimals. Read only §IV–V, on the reward-punishment structure
  of the learned strategies, since that is what Fish's §4 is arguing against.
- **Asker, Fershtman & Pakes (2023)** — the "demand slopes downward" information
  effect that Appendix D exists to rule out. Only needed if a reviewer presses on
  whether P1 and P2 differ in information rather than framing.
- **Fish et al. (2025)**, the authors' own follow-up framework for quantifying LLM
  tendencies in economic settings (footnote 42 of the paper). No verified link
  yet; worth finding, because it likely supersedes parts of the addendum.

---

## Two questions to hold throughout

Both come out of your own work, and either one is a paper if it holds up.

1. **What is the no-collusion null?** Bonjour subtracts other players' influence;
   Fish's Table 1 subtracts nothing; Xu reports correlations. In a differentiated
   Bertrand market, competitive agents *already* move together. Every detection
   paper you read should be asked what it compares against.

2. **Where does the policy live?** Q-learning stores it in weights, so rematching
   destroys it. LLM agents store it in context, so a newcomer can read the
   convention off 100 rounds of history. Most cross-paper disagreements in this
   literature may reduce to this distinction.

---

## Still missing links

Cited in the sprint's research questions, not resolved by search — likely in the
Resources tab:

- **Xu et al. (2026)** — correlation between deployments of the same base model;
  temperature as a lever. Closest near-miss was Ballestero, Hosseini, Khanna &
  Shorrer, *Strategic Algorithmic Monoculture* ([arXiv:2604.09502](https://arxiv.org/abs/2604.09502)),
  which is a different paper.
- **Dhanda (2026)** — strongly worded competition instructions pushing prices
  below competitive. Directly relevant: your P2 arm did this by accident.
- **Q. Liu et al. (2026)** — the forfeitable deposit mechanism.
