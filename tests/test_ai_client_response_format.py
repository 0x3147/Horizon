from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.ai.client import OpenAIClient
from src.models import AIConfig, AIProvider


def _response(content: str = "ok"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


def test_openai_client_omits_json_response_format_for_text_completions():
    client = OpenAIClient(AIConfig(provider=AIProvider.OPENAI, model="gpt-4.1-mini", api_key="sk-test"))

    with patch.object(client.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = _response("# Markdown")
        result = asyncio.run(client.complete(system="system", user="user", response_format="text"))

    assert result == "# Markdown"
    assert "response_format" not in mock_create.call_args.kwargs


def test_openai_client_keeps_json_response_format_by_default():
    client = OpenAIClient(AIConfig(provider=AIProvider.OPENAI, model="gpt-4.1-mini", api_key="sk-test"))

    with patch.object(client.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = _response('{"ok": true}')
        asyncio.run(client.complete(system="system", user="user"))

    assert mock_create.call_args.kwargs["response_format"] == {"type": "json_object"}
