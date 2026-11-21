from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from services.agent.connectivity import ConnectivityManager
from services.agent.diagnosis import OllamaDiagnosisProvider, RulesBasedDiagnosisProvider


FINDING = {
    "id": "test-id",
    "category": "cpu",
    "severity": "warning",
    "title": "Controlled workload is using CPU",
    "evidence": "Controlled workload averaged 48% of one core.",
    "potential_impact": "Less capacity could be available for your meeting.",
    "limitations": "Meeting quality was not measured.",
    "window_seconds": 2,
    "recommended_action_ids": ["stop_demo_workload"],
    "pid": 1234,
    "command_line": "/private/user-secret",
    "unknown_raw_data": "secret contents",
}
VALID = {
    "headline": "A background workload needs attention",
    "explanation": "The Spark Ready workload is using processing resources.",
    "possible_causes": ["The controlled demo workload is active."],
    "potential_impact": "Your meeting app may have less headroom.",
    "recommended_action_id": "stop_demo_workload",
    "uncertainty": "Meeting quality was not measured.",
}


def response_with(content: str):
    return httpx.Response(200, json={"done": True, "message": {"content": content}})


def test_structured_local_explanation_and_privacy_filter():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return response_with(json.dumps(VALID))

    provider = OllamaDiagnosisProvider(transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.explain([FINDING], question="Why is CPU high? Private data: employee@example.com"))
    assert result.provider == "ollama" and result.model == "qwen3.5:4b"
    assert result.recommended_action_id == "stop_demo_workload"
    assert result.observed_facts == [FINDING["evidence"]]
    assert len(requests) == 1
    assert requests[0].url.host == "127.0.0.1"
    body = json.loads(requests[0].content)
    prompt = json.loads(body["messages"][1]["content"])
    assert prompt["observations"]["question_topic"] == "workload"
    assert body["format"]["type"] == "object"
    assert not body["stream"] and not body["think"]
    for private_text in (b"employee@example.com", b"private/user-secret", b"secret contents", b'"pid"', b"test-id"):
        assert private_text not in requests[0].content


@pytest.mark.parametrize("content", [
    "",
    "{}",
    json.dumps({**VALID, "explanation": "CPU is at 95%."}),
    json.dumps({**VALID, "recommended_action_id": "terminate_vpn"}),
    json.dumps({**VALID, "explanation": "Run sudo reboot."}),
    json.dumps({**VALID, "observed_facts": ["Remote support connected."]}),
])
def test_invalid_inference_falls_back_without_changing_facts_or_actions(content):
    provider = OllamaDiagnosisProvider(transport=httpx.MockTransport(lambda _request: response_with(content)))
    result = asyncio.run(provider.explain([FINDING]))
    assert result.provider == "rules"
    assert result.status == "fallback"
    assert result.observed_facts == [FINDING["evidence"]]
    assert result.recommended_action_id == "stop_demo_workload"


def test_model_cannot_offer_an_unavailable_demo_action():
    provider = OllamaDiagnosisProvider(transport=httpx.MockTransport(lambda _: response_with(json.dumps(VALID))))
    result = asyncio.run(provider.explain([{**FINDING, "recommended_action_ids": []}]))
    assert result.provider == "rules"
    assert result.recommended_action_id is None


def test_offline_model_uses_deterministic_explanation():
    def offline(request):
        raise httpx.ConnectError("Ollama unavailable", request=request)

    provider = OllamaDiagnosisProvider(transport=httpx.MockTransport(offline))
    result = asyncio.run(provider.explain([FINDING]))
    assert result.provider == "rules" and result.status == "fallback"
    assert result.headline == FINDING["title"]


def test_network_guidance_keeps_simulation_explicit_and_read_only():
    async def verify():
        manager = ConnectivityManager(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
        try:
            report = await manager.simulate_cloud(True)
            result = await RulesBasedDiagnosisProvider().explain(
                [], network=report, question="Can I still use Spark Ready?",
            )
            assert result.headline == "Local preparation remains available"
            assert any("simulating" in text for text in result.possible_causes)
            assert result.recommended_action_id is None
            assert result.safe_steps
        finally:
            await manager.close()

    asyncio.run(verify())
