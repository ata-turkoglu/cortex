import asyncio

import httpx

from app.providers.openai import OpenAIProvider


def test_openai_provider_requires_configuration(monkeypatch):
    monkeypatch.setattr(
        "app.providers.openai.get_settings", lambda: type("S", (), {"openai_api_key": None})()
    )
    try:
        asyncio.run(OpenAIProvider().generate("gpt-5.6-luna", "be grounded", "hello"))
    except RuntimeError as error:
        assert str(error) == "OpenAI is not configured"
    else:
        raise AssertionError("missing credentials must not create a network request")


def test_openai_provider_reads_responses_output_and_usage(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                json={"output_text": "Grounded", "usage": {"input_tokens": 3, "output_tokens": 2}},
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            )

    monkeypatch.setattr(
        "app.providers.openai.get_settings", lambda: type("S", (), {"openai_api_key": "test"})()
    )
    monkeypatch.setattr("app.providers.openai.httpx.AsyncClient", lambda **_: Client())
    result = asyncio.run(OpenAIProvider().generate("gpt-5.6-luna", "be grounded", "hello"))
    assert (result.text, result.input_tokens, result.output_tokens) == ("Grounded", 3, 2)
