# The duopoly experiment, as an Inspect eval

The same experiment as `src/`, running on [Inspect](https://inspect.aisi.org.uk)
instead of a hand-rolled loop. The economics, the prompts and the parser are
imported unchanged from `src/econ.py` and `src/agent.py` — so if a number moves,
it moved because the model changed, not because the harness did.

```bash
python -m pip install -r requirements.txt
```

---

## The one design decision everything else follows from

**A sample is one market, not one LLM call.**

Inspect's `Sample` is the unit of independence: it is what gets scheduled,
retried, limited, scored, and treated as *one observation* by a metric. Ask what
the independent observation is here and the answer is a whole 300-period market.
The 600 calls inside it are one interacting system — period 251 and period 252
are about as independent as two frames of a film.

Get this wrong and nothing crashes; you just quietly get standard errors that
are too small by roughly `sqrt(600)`, because the metric believed it had 12,600
observations instead of 21 per arm. That is the kind of error an eval framework
cannot catch for you, because it is a claim about the world, not about the code.

Everything else falls out:

| | |
|---|---|
| **Sample** | one market: prefix × α × seed, run for N periods |
| **Solver** | the market loop — two agents price simultaneously, demand turns prices into profits, the result becomes next period's history |
| **Scorer** | the economics after the fact: Calvano's Δ, average price, supracompetitive yes/no |
| **Metric** | `grouped(mean(), "prefix")` — P1 and P2 reported separately, which *is* the paper's claim |

The solver/scorer split is worth one more sentence. The scorers never call a
model: they read the finished market out of `store()`. So `inspect score <log>`
re-scores an old run with a new index, a different averaging window, or a metric
you thought of last week — for free, months later, on tokens you already paid
for. In the old harness that meant re-running the experiment.

---

## What changed, honestly

**Deleted, because the framework already does it.** The `ThreadPoolExecutor`s and
`--jobs` (Inspect schedules samples concurrently under `--max-connections`), the
HTTP retry/backoff loop, cost accounting, the CSV writers, `console.log`,
`runs/*.log`, `transcripts/*.md`, and the `--full-prompt-every` hack that existed
only to stop a 200-period run writing 130 MB of near-duplicate prompts. The
`.eval` file is compressed, so every prompt is kept.

**Kept, because it is ours and not the framework's.** The template-conformance
retry. Inspect retries transport failures; it cannot know that a `200 OK` whose
body ignores the response template is also a failure. The paper retries those
(Appendix B), and so do we — a silently mis-parsed price is a *fabricated data
point*, which is worse than a failed run. Price clipping stays for the same
reason, and is logged when it fires.

**Gained.** `inspect view` replaces three kinds of log file with one browsable
timeline; `inspect eval-retry` resumes a run that died at period 250 instead of
starting over; per-sample cost/token/time limits replace the hand-rolled budget
tracker.

**One real regression.** `--budget-usd` was a *global* stop: the whole experiment
halted once total spend hit the cap. Inspect's limits are **per sample**, so
`-T budget_usd_per_run=0.60` caps each market, and the worst case is that cap
times the number of markets. Check the estimate before launching a big run.

---

## Running it

One command for the whole pipeline — run the eval, then rebuild the figure:

```bash
python evals/run.py --mock                  # free, offline, ~30 seconds
python evals/run.py                         # the pilot (~$0.12)
python evals/run.py --runs 7 --periods 100 --alphas 1,3.2,10     --history-window 30 --avg-window 25 --max-connections 20
python evals/run.py --dry-run               # print the `inspect eval` it would run
```

It keeps the old harness's flag names, so the commands in the paper notes still
mean something, and `--dry-run` prints the exact `inspect eval` equivalent — so
it stays a convenience and never becomes a second source of truth. It also runs
through the Python API, which imports the task *before* resolving the model,
which is why `--model duopoly/mock` works there but not on the CLI.

Or drive the task directly:

```bash
# free, offline, exercises the entire pipeline (no API key, no spend)
inspect eval evals/duopoly.py -T mock=true

# the pilot (~$0.12)
inspect eval evals/duopoly.py --model openrouter/openai/gpt-4o-mini

# closer to the paper
inspect eval evals/duopoly.py --model openrouter/openai/gpt-4o-mini \
    -T runs=7 -T periods=100 -T alphas=1,3.2,10 \
    -T history_window=30 -T avg_window=25 --max-connections 20

inspect view --log-dir logs        # browse
python evals/report.py             # rebuild Figure 2 from the logs
```

Your existing `src/.env` is picked up as-is — no key has to move. Inspect's
OpenRouter provider reads the same `OPENROUTER_API_KEY`.

Task parameters (`-T name=value`): `prefixes`, `runs`, `periods`, `alphas`,
`history_window`, `avg_window`, `temperature`, `max_tokens`, `seed`,
`max_template_retries`, `budget_usd_per_run`, `mock`.

### About `-T mock=true` rather than `--model duopoly/mock`

Inspect resolves `--model` *before* it imports the task file, so a provider
registered inside `mock_provider.py` is not in the registry yet when the CLI
looks for it. Passing the model through the task avoids needing
`pip install -e .` and an entry point for what is meant to be a free smoke test.
(Install this repo as a package and `--model duopoly/mock` starts working too.)

---

## The old `results/` tree

`src/run_duopoly.py` is retired and gated: running it would rebuild the old
`transcripts/*.md`, `runs/*.log` and `console.log` tree alongside the `.eval`
logs, leaving two parallel records of the same experiment that can drift apart.
One record, in one format, is the point of the port — the `.eval` log already
holds every prompt, every reply, the token counts and the cost.

`--estimate` still works, because it only prices a run against OpenRouter's
catalogue and writes nothing. Everything else needs `--allow-retired-harness`,
and the retirement message maps every old flag onto its `-T` equivalent.

The earlier 300-period run's `transcripts/` and `runs/` folders were removed
from the working tree. They remain in git history (commit `61f0113`) and can be
brought back with `git restore` if the raw replies are ever needed again.

## Files

| file | role |
|---|---|
| `duopoly.py` | the eval: dataset, solver, three scorers, grouped metrics, `@task` |
| `run.py` | one command: run the eval, then rebuild Figure 2 |
| `mock_provider.py` | free offline stand-in model (`-T mock=true`) |
| `report.py` | `.eval` logs → `summary.csv` + Figure 2 + Welch test |
| `../src/econ.py` | logit demand, Nash and monopoly benchmarks — imported, not copied |
| `../src/agent.py` | prompts (verbatim from Appendix G) and the parser — imported, not copied |
| `../src/plot_fig2.py` | the figure itself — imported by `report.py`, not reimplemented |

---

## Reading a log

`inspect view --log-dir logs`, open a sample, and each period is a span
containing the two model calls plus an info event with the line the old console
printed:

```
1.00 |---------N----------2-1-M---------------------| 3.15
collusion index (0=Nash, 1=monopoly): +0.81
firm 1 thinks: "Holding at 1.88; cutting price would likely start a price war..."
```

The ruler puts both firms' prices between marginal cost and the ceiling the
agent was shown, with `N` = Nash, `M` = monopoly, `X` = both firms identical.
Marks drifting from `N` toward `M` *is* the phenomenon.

The prompts matter more than usual here. The agent has no memory — each period
is a fresh one-message conversation — so any "strategy" it appears to have must
be visible as text it wrote into `PLANS.txt` or `INSIGHTS.txt` and read back a
period later. Section 4 of the paper is built entirely on that text, and it is
all in the log.

---

## Caveats that survive the port

- **Underpowered at pilot settings.** 3 runs per arm cannot establish the
  paper's p < 0.00001. The Welch test in `report.py` proves the pipeline
  computes it, nothing more.
- **Different model.** GPT-4-0613 is retired. A null result on a cheap 2026
  model is evidence about that model, not about the paper.
- **Short runs converge less.** The paper averages periods 251–300. Treat a
  short run's price *levels* as provisional and the P1 > P2 *ordering* as the
  thing to look for.
