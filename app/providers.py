import json
import logging
import os
from dataclasses import dataclass

import litellm

logger = logging.getLogger(__name__)

@dataclass
class ToolCall:
    id: str
    name: str
    input: dict

@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str  # "tool_use" or end

def _resolve_model() -> str:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    model = os.getenv("LLM_MODEL", "claude-sonnet-5")
    if provider == "openrouter":
         return f"openrouter/{model}"
    return model

def _to_litellm_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]

async def create(*, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
    model = _resolve_model()
    logger.info("Calling LLM: model=%s", model)
    response = await litellm.acompletion(
        model = model,
        messages = [{"role": "system", "content": system}, *messages],
        tools = _to_litellm_tools(tools),
    )

    message = response.choices[0].message
    text = message.content or ""
    raw_tool_calls = message.tool_calls or []
    tool_calls = [
        ToolCall(id = tc.id, name = tc.function.name, input = json.loads(tc.function.arguments))
        for tc in raw_tool_calls
    ]

    stop_reason = "tool_use" if tool_calls else "end"
    return LLMResponse(text=text, tool_calls=tool_calls, stop_reason=stop_reason)
    