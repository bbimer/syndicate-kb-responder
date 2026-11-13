"""Async DeepSeek v4.1 client with prefix caching and telemetry."""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
from openai import AsyncOpenAI

from config.settings import settings
from src.generator.prompts import (
    STATIC_SYSTEM_PREFIX,
    build_hook_prompt,
    build_shield_prompt,
    build_followup_prompt,
    build_counter_prompt
)


@dataclass
class GenerationResult:
    text: str
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_sec: float
    cost_usd: float

    def format_telemetry(self) -> str:
        return (
            f"Tokens: {self.prompt_tokens} (cached: {self.cached_tokens}) prompt + "
            f"{self.completion_tokens} completion | Cost: ${self.cost_usd:.6f} | "
            f"Latency: {self.latency_sec:.2f}s"
        )


class DeepSeekClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ):
        self.api_key = api_key or settings.api_key
        self.base_url = base_url or settings.deepseek_base_url
        self.model = model or settings.deepseek_model
        self.max_tokens = max_tokens or settings.max_tokens
        self.temperature = temperature or settings.temperature

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _calc_cost(self, prompt_tokens: int, cached_tokens: int, completion_tokens: int) -> float:
        """DeepSeek v4.1 / Chat pricing:

        Input: $0.14 / 1M ($0.00000014)
        Cached Input: $0.014 / 1M ($0.000000014)
        Output: $0.28 / 1M ($0.00000028)
        """
        uncached_prompt = max(0, prompt_tokens - cached_tokens)
        cost = (
            uncached_prompt * 0.00000014 +
            cached_tokens * 0.000000014 +
            completion_tokens * 0.00000028
        )
        return cost

    async def generate(self, user_prompt: str, max_tokens: Optional[int] = None) -> GenerationResult:
        """Executes a single completion with cached prefix system prompt."""
        t0 = time.perf_counter()
        effective_max_tokens = max_tokens or self.max_tokens

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": STATIC_SYSTEM_PREFIX},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=effective_max_tokens,
            temperature=self.temperature
        )
        latency = time.perf_counter() - t0

        choice = response.choices[0]
        text = choice.message.content or ""

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else (prompt_tokens + completion_tokens)

        # Check prompt caching details if available
        cached_tokens = 0
        if usage and hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
            cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

        cost = self._calc_cost(prompt_tokens, cached_tokens, completion_tokens)

        return GenerationResult(
            text=text.strip(),
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_sec=latency,
            cost_usd=cost
        )

    async def generate_hook(self, quote_sample: str, context: Dict[str, Any]) -> GenerationResult:
        prompt = build_hook_prompt(quote_sample, context)
        return await self.generate(prompt, max_tokens=450)

    async def generate_shield(
        self,
        incoming_text: str,
        context: Dict[str, Any],
        stage: str = "In_DM",
        deposit_est: str = "500_2000"
    ) -> GenerationResult:
        prompt = build_shield_prompt(incoming_text, context, stage=stage, deposit_est=deposit_est)
        return await self.generate(prompt, max_tokens=220)

    async def generate_followup(
        self,
        thread_context: str,
        last_our_message: str,
        lead_reply: str,
        context: Dict[str, Any]
    ) -> GenerationResult:
        prompt = build_followup_prompt(thread_context, last_our_message, lead_reply, context)
        return await self.generate(prompt, max_tokens=450)

    async def generate_counter(
        self,
        dialogue_history: list[dict[str, str]],
        new_reply: str,
        context: Dict[str, Any],
        deposit_est: str = "500_2000"
    ) -> GenerationResult:
        prompt = build_counter_prompt(dialogue_history, new_reply, context, deposit_est=deposit_est)
        return await self.generate(prompt, max_tokens=450)
