"""An offline, free stand-in model, registered with Inspect as `duopoly/mock`.

This replaces the old `--mock` flag.  In Inspect the choice of model is not a
flag on the experiment, it is the *model* -- so the honest way to express "run
the whole pipeline with no API calls" is to register a provider and select it
with `--model duopoly/mock`.  Everything downstream (solver, scorers, metrics,
log format, viewer) is then byte-for-byte the same code path as a real run,
which is the entire point of having a mock.

It is NOT a model of LLM behaviour and proves nothing about collusion.  It
anchors near the monopoly price with noise so the figure has something to draw.

Reproducibility note: Inspect memoises one Model object across all samples, so
a single mutable RNG stream would make results depend on scheduling order.  We
instead seed a fresh RNG from a hash of the prompt.  Every distinct prompt gets
its own fixed draw, so the noise is real but the whole eval is deterministic
regardless of how samples interleave.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from inspect_ai.model import (
    ChatMessage,
    GenerateConfig,
    Model,
    ModelAPI,
    ModelOutput,
    ModelUsage,
    get_model,
    modelapi,
)
from inspect_ai.tool import ToolChoice, ToolInfo


def _grab(pattern: str, text: str, default: float) -> float:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else default


class MockDuopolyAPI(ModelAPI):
    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        config: GenerateConfig = GenerateConfig(),
        seed: int = 0,
        **model_args: Any,
    ) -> None:
        super().__init__(model_name, base_url, api_key, [], config)
        self.seed = int(seed)

    async def generate(
        self,
        input: list[ChatMessage],
        tools: list[ToolInfo],
        tool_choice: ToolChoice,
        config: GenerateConfig,
    ) -> ModelOutput:
        prompt = "\n".join(str(m.text) for m in input)
        digest = hashlib.sha256(f"{self.seed}:{prompt}".encode()).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))

        wtp = _grab(r"No customer would pay more than \$(\d+(?:\.\d+)?)", prompt, 4.0)
        cost = _grab(r"cost I pay to produce each unit is \$(\d+(?:\.\d+)?)", prompt, 1.0)
        price = max(cost * 1.05, min(wtp, rng.gauss(1.8 * cost, 0.18 * cost)))

        completion = (
            "My observations and thoughts:\nMock agent; no reasoning performed.\n\n"
            "New content for PLANS.txt:\nMock plan.\n\n"
            "New content for INSIGHTS.txt:\nMock insight.\n\n"
            f"My chosen price:\n{price:.2f}\n"
        )
        output = ModelOutput.from_content(model=self.model_name, content=completion)
        # Rough token counts so the log's usage panel is not misleadingly empty.
        n_in, n_out = len(prompt) // 4, len(completion) // 4
        output.usage = ModelUsage(
            input_tokens=n_in, output_tokens=n_out, total_tokens=n_in + n_out
        )
        return output


@modelapi(name="duopoly")
def duopoly_provider() -> type[ModelAPI]:
    """Registers `duopoly/mock`."""
    return MockDuopolyAPI


def mock_model(seed: int = 0) -> Model:
    """The mock as a ready-to-use `Model`, resolved through Inspect's registry.

    Why a helper instead of `--model duopoly/mock` on the command line: Inspect
    resolves `--model` *before* it imports the task file, so the provider
    registered above is not in the registry yet when the CLI looks for it.  By
    the time the `@task` function runs, the import has happened, so the same
    name resolves fine here.  That keeps `-T mock=true` working from a bare
    checkout -- no `pip install -e .`, no entry-point plumbing.  (Install this
    repo as a package and `--model duopoly/mock` starts working too, because
    the `@modelapi` registration is then discovered at startup.)
    """
    return get_model("duopoly/mock", seed=seed, memoize=False)
