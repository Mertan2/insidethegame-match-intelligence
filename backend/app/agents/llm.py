"""LLM client abstraction.

`LLMClient.complete()` is the narrow transport seam: `FoundryLLM` targets a chat model
deployed in Microsoft Foundry (Azure OpenAI-compatible endpoint), `NullLLM` means no
model, and tests plug in fakes. `LLMChatClient` adapts any `LLMClient` into a Microsoft
Agent Framework chat client, so each agent runs as an Agent Framework `Agent` with its
own instructions while the transport stays swappable. With no model configured every
agent falls back to its deterministic template, so the whole app runs offline.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import httpx
from agent_framework import BaseChatClient, ChatResponse, Message
from agent_framework._tools import FunctionInvocationLayer


class LLMClient(Protocol):
    available: bool

    async def complete(self, system: str, prompt: str, max_tokens: int = 300, json_mode: bool = False) -> str: ...


class NullLLM:
    """No model configured: agents use their template path."""

    available = False

    async def complete(self, system: str, prompt: str, max_tokens: int = 300, json_mode: bool = False) -> str:
        raise RuntimeError("No LLM configured")


class FoundryLLM:
    """Chat completions against a Foundry / Azure OpenAI deployment."""

    available = True

    def __init__(self, endpoint: str, api_key: str, deployment: str, api_version: str = "2024-10-21"):
        self.deployment = deployment
        self.url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions"
        self.params = {"api-version": api_version}
        self.headers = {"api-key": api_key}
        self._client = httpx.AsyncClient(timeout=10.0)
        self._reasoning_model = False  # set once the deployment rejects max_tokens/temperature

    def _body(self, system: str, prompt: str, max_tokens: int, json_mode: bool = False) -> dict[str, Any]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        body: dict[str, Any] = {"messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}  # the model must return valid JSON
        if self._reasoning_model:
            # Reasoning models spend completion tokens on thinking first, so give them headroom.
            return {**body, "max_completion_tokens": max_tokens * 8}
        return {**body, "max_tokens": max_tokens, "temperature": 0.7}

    async def complete(self, system: str, prompt: str, max_tokens: int = 300, json_mode: bool = False) -> str:
        body = self._body(system, prompt, max_tokens, json_mode)
        resp = await self._client.post(self.url, params=self.params, headers=self.headers, json=body)
        if resp.status_code == 400 and not self._reasoning_model and "unsupported" in resp.text.lower():
            self._reasoning_model = True
            body = self._body(system, prompt, max_tokens, json_mode)
            resp = await self._client.post(self.url, params=self.params, headers=self.headers, json=body)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content")
        if not content:
            raise ValueError("Empty completion")
        return content.strip()

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_tokens: int = 400) -> dict[str, Any]:
        """One chat-completions turn with function calling; returns the assistant message
        (with `tool_calls` when the model wants data)."""
        body: dict[str, Any] = {"messages": messages, "tools": tools, "tool_choice": "auto"}
        if self._reasoning_model:
            body["max_completion_tokens"] = max_tokens * 8
        else:
            body.update(max_tokens=max_tokens, temperature=0.4)
        resp = await self._client.post(self.url, params=self.params, headers=self.headers, json=body, timeout=20.0)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]


class LLMChatClient(FunctionInvocationLayer, BaseChatClient):
    """Microsoft Agent Framework chat client backed by an `LLMClient` transport.

    The agent's instructions arrive as `options["instructions"]` (or system messages); the
    remaining messages form the prompt. `max_tokens` is passed through from the run options.
    """

    OTEL_PROVIDER_NAME = "azure.ai.openai"

    def __init__(self, llm: LLMClient, **kwargs: Any):
        super().__init__(**kwargs)
        self.llm = llm

    async def _inner_get_response(
        self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **kwargs: Any
    ) -> ChatResponse:
        if stream:
            raise NotImplementedError("LLMChatClient does not stream")
        system = [str(options.get("instructions") or "")] + [m.text for m in messages if m.role == "system"]
        prompt = "\n".join(m.text for m in messages if m.role != "system")
        extra = {"json_mode": True} if options.get("json_mode") else {}  # only JSON agents need the newer signature
        text = await self.llm.complete("\n".join(s for s in system if s), prompt, int(options.get("max_tokens") or 300), **extra)
        return ChatResponse(messages=[Message(role="assistant", contents=[text])])


def get_llm() -> LLMClient:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if endpoint and key and deployment:
        return FoundryLLM(endpoint, key, deployment, os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))
    return NullLLM()
