# Duopoly pilot — can we reproduce Figure 2?

A cheap, end-to-end pilot of the main experiment in Fish, Gonczarowski & Shorrer,
*Algorithmic Collusion by Large Language Models* (arXiv:2404.00806), using
OpenRouter so any model can stand in for GPT-4-0613.

**What this pilot is for.** Not replication — feasibility. It answers: does the
whole chain work (prompts → agent memory → demand → parsing → data → figure),
and does the P1-vs-P2 gap appear at all on a model that costs cents? If yes,
scaling to the paper's numbers is purely a budget decision.

| | paper | this pilot (defaults) |
|---|---|---|
| runs | 42 (21 per prefix) | 6 (3 per prefix) |
| periods per run | 300 | 30 |
| history shown to agent | 100 rounds | 15 rounds |
| averaging window | last 50 periods | last 10 periods |
| currency scales α | {1, 3.2, 10} | {1} |
| LLM calls | 25,200 | 360 |
| cost | GPT-4 pricing, 2023 | ~$0.12 on `openai/gpt-4o-mini` |

---

## The idea in one paragraph

Two firms sell differentiated products. Each firm's price is set, every period,
by a fresh LLM call that has seen only (a) a short prompt telling it to maximise
long-run profit, (b) a table of past prices/quantities/profits, and (c) two notes
files the *previous* call wrote to itself. The agents cannot talk. Nothing in the
prompt mentions collusion, retaliation, or price wars.

Two reference prices anchor everything:

- **p_Nash = 1.473** — the one-shot Bertrand–Nash price. What competition predicts.
- **p_M = 1.925** — the price a monopolist owning both firms would charge. Higher,
  because a monopolist internalises the demand it steals from itself by undercutting.

Prices settling *between* these, or above, are **supracompetitive**: the agents are
behaving as if they had agreed to keep prices up, without having agreed to anything.
That gap is the paper's finding and the content of Figure 2.

The single manipulation is one sentence of the prompt:

- **P1** reiterates long-run profit ("do not take actions which undermine profitability").
- **P2** instead mentions that undercutting sells more units.

The paper's claim: P1 lands much closer to monopoly pricing than P2. A pilot that
reproduces *that ordering* is a pilot worth scaling.

---

## Files

| file | role |
|---|---|
| `econ.py` | logit demand, profits, and the Nash / monopoly benchmarks. `python src/econ.py` checks them against Calvano et al.'s published values. |
| `agent.py` | prompts (verbatim from Appendix G), response parsing, OpenRouter client, offline mock client. |
| `run_duopoly.py` | the experiment loop, logging, cost accounting. |
| `plot_fig2.py` | rebuilds both panels of Figure 2 from `summary.csv`. |

## Setup

Add your key to `src/.env` (it is loaded automatically, never printed):

```
OPENROUTER_API_KEY="sk-or-v1-..."
```

Dependencies are already present in this environment: `numpy scipy matplotlib requests`.

## Running

```bash
python src/econ.py                      # 1. sanity-check the economics (free, instant)
python src/run_duopoly.py --mock        # 2. exercise the whole pipeline offline (free)
python src/plot_fig2.py                 #    ...and confirm the figure draws
python src/run_duopoly.py --estimate    # 3. price the real run from OpenRouter's catalogue
python src/run_duopoly.py               # 4. the real pilot (~$0.12, ~10 min)
python src/plot_fig2.py results/<stamp>
```

Useful flags: `--model`, `--runs`, `--periods`, `--alphas 1,3.2,10`,
`--history-window`, `--avg-window`, `--budget-usd` (hard stop), `--jobs` (parallel runs),
`--prefixes P1,P2`, `--tag`.

Sensible next step after a successful pilot — closer to the paper, still cheap:

```bash
python src/run_duopoly.py --runs 7 --periods 100 --alphas 1,3.2,10 \
    --history-window 30 --avg-window 25 --jobs 4 --budget-usd 15 --tag scaled
```

## Reading the logs

Per period, per run, the console and `console.log` show:

```
  [P1_rep1_a1]  period   7/30   spent $0.0213
    firm 1: price   1.88 | qty  46.11 | profit  40.59 |  2.4s $0.00052
    firm 2: price   1.85 | qty  49.02 | profit  41.67 |  2.1s $0.00049
    1.00 |---------N----------2-1-M---------------------| 3.15
    collusion index (0=Nash, 1=monopoly): +0.81
    firm 1 thinks: "Holding at 1.88; cutting price would likely start a price war..."
```

- the ruler puts both firms' prices on a line between marginal cost and the ceiling
  the agent was shown, with `N` = Nash and `M` = monopoly (`X` = both firms identical).
  Marks drifting from `N` toward `M` *is* the phenomenon.
- **collusion index** is Calvano's Δ = (π − π_Nash)/(π_M − π_Nash): 0 = competitive,
  1 = full collusion. It makes runs with different α and results from different papers
  directly comparable. Above 1 means the agents priced above even the monopoly level.
- **firm N thinks** is the first line of that agent's own reasoning — the cheapest
  early warning that the model is confused, refusing, or ignoring the template.

Everything written to `results/<timestamp>/`:

```
config.json      exact settings + the environment's benchmarks
periods.csv      every period of every run (prices, quantities, profits, α-normalised)
summary.csv      one row per run — this is what the figure plots
console.log      the full readable log
runs/<id>.log    the same, split per run (useful with --jobs > 1)
transcripts/<id>/period_007_firm1.md    full prompt + full raw reply, per call
fig2_pilot.png   the figure
```

The transcripts matter more than usual here. The agent has no memory, so any
"strategy" it appears to have must be visible as text it wrote into PLANS.txt or
INSIGHTS.txt and read back later. Section 4 of the paper (price-war concerns) is
built entirely on that text.

## Caveats worth stating before anyone reads results

- **30 periods is short.** The paper averages periods 251–300; convergence is not
  guaranteed in 30. Treat the pilot's price *levels* as provisional and the
  P1 > P2 *ordering* as the thing to look for.
- **Underpowered.** 3 runs per arm cannot establish the paper's p < 0.00001. The
  Welch test in `plot_fig2.py` is there to prove the pipeline computes it.
- **Different model.** GPT-4-0613 is retired. A cheap 2026 model may be better or
  worse at this task; a null result on `gpt-4o-mini` is evidence about that model,
  not about the paper.
- **Prices are clipped** to [cost, ceiling] before entering the market, and clipping
  is logged. A mis-parsed price should abort a period, not silently become data.
