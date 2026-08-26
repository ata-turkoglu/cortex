import asyncio

import httpx

from app.providers.openai import OpenAIProvider


def test_openai_provider_requires_configuration(monkeypatch):
    monkeypatch.setattr(
        "app.providers.openai.get_settings", lambda: type("S", (), {"openai_api_key": None})()
    )
    monkeypatch.setattr("app.providers.openai.SecretStore.get", lambda *_: None)
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


def test_openai_provider_reads_wire_response_output(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                json={
                    "output": [
                        {"type": "message", "content": [
                            {"type": "output_text", "text": '{"mentions":[]}'},
                        ]}
                    ]
                },
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            )

    monkeypatch.setattr(
        "app.providers.openai.get_settings", lambda: type("S", (), {"openai_api_key": "test"})()
    )
    monkeypatch.setattr("app.providers.openai.httpx.AsyncClient", lambda **_: Client())
    result = asyncio.run(OpenAIProvider().generate("gpt-4.1-mini", "extract", "text"))
    assert result.text == '{"mentions":[]}'


def test_openai_provider_sends_responses_strict_json_schema(monkeypatch):
    request_json = {}
    client_options = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **kwargs):
            request_json.update(kwargs["json"])
            return httpx.Response(
                200,
                json={"id": "response-1", "output_text": '{"state":"resolved"}'},
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            )

    monkeypatch.setattr(
        "app.providers.openai.get_settings", lambda: type("S", (), {"openai_api_key": "test"})()
    )
    monkeypatch.setattr(
        "app.providers.openai.httpx.AsyncClient",
        lambda **kwargs: (client_options.update(kwargs) or Client()),
    )
    result = asyncio.run(
        OpenAIProvider().generate_structured(
            "gpt-5.6-luna",
            "interpret",
            "question",
            schema_name="semantic_understanding_v1",
            json_schema={"type": "object", "additionalProperties": False},
        )
    )
    assert result.request_id == "response-1"
    assert request_json["text"]["format"] == {
        "type": "json_schema",
        "name": "semantic_understanding_v1",
        "strict": True,
        "schema": {"type": "object", "additionalProperties": False},
    }
    assert client_options["trust_env"] is False


def test_openai_provider_lists_models_from_models_api(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "gpt-4.1"},
                        {"id": "text-embedding-3-small"},
                        {"id": "whisper-1"},
                        {"id": "gpt-audio-mini"},
                        {"id": "gpt-image-1"},
                    ]
                },
                request=httpx.Request("GET", "https://api.openai.com/v1/models"),
            )

    monkeypatch.setattr(
        "app.providers.openai.get_settings", lambda: type("S", (), {"openai_api_key": "test"})()
    )
    monkeypatch.setattr("app.providers.openai.httpx.AsyncClient", lambda **_: Client())
    models = asyncio.run(OpenAIProvider().list_models())
    assert [(model.model, model.chat, model.embeddings) for model in models] == [
        ("gpt-4.1", True, False),
        ("text-embedding-3-small", False, True),
    ]
