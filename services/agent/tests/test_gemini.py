import asyncio
import json

import httpx

from services.agent.connectivity import ConnectivityManager
from services.agent.diagnosis import GeminiDiagnosisProvider, OllamaDiagnosisProvider

FINDING = {
    "category": "workload", "severity": "warning", "title": "Background workload using CPU",
    "evidence": "itor's temporary workload is using CPU.", "potential_impact": "Your work apps may be slower.",
    "limitations": "The exact effect on your work was not measured.", "recommended_action_ids": ["stop_demo_workload"],
}
ANSWER = {
    "headline": "A background task is slowing your PC", "explanation": "A temporary task is using the processor.",
    "possible_causes": ["The itor demo task is still running."], "potential_impact": "Apps may feel slow.",
    "recommended_action_id": "stop_demo_workload", "uncertainty": "Call quality was not tested.",
}


def gemini_reply(answer=None, finish="STOP", blocked=False, status=200):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "quota"}})
        if blocked:
            return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})
        text = json.dumps(answer or ANSWER)
        return httpx.Response(200, json={"candidates": [
            {"content": {"role": "model", "parts": [{"text": "thinking...", "thought": True}, {"text": text}]},
             "finishReason": finish}]})
    return httpx.MockTransport(handler), calls


def offline_ollama():
    def fail(request):
        raise httpx.ConnectError("Ollama unavailable", request=request)
    return OllamaDiagnosisProvider(transport=httpx.MockTransport(fail))


def provider(transport, key="test-key"):
    return GeminiDiagnosisProvider(offline_ollama(), api_key=key, transport=transport)


def test_gemini_answers_when_online():
    transport, calls = gemini_reply()
    result = asyncio.run(provider(transport).explain([FINDING]))
    assert result.provider == "gemini" and result.headline == ANSWER["headline"]
    assert result.recommended_action_id == "stop_demo_workload"
    request = calls[0]
    assert request.url.path == "/v1beta/models/gemini-3.5-flash-lite:generateContent"
    assert request.headers["x-goog-api-key"] == "test-key"
    body = json.loads(request.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in body["generationConfig"]


def test_falls_back_to_local_on_problems():
    for transport, _ in (gemini_reply(status=429), gemini_reply(blocked=True), gemini_reply(finish="SAFETY"),
                         gemini_reply(answer={**ANSWER, "explanation": "Run netsh winsock reset now"})):
        assert asyncio.run(provider(transport).explain([FINDING])).provider == "rules"


def test_no_key_means_no_call():
    transport, calls = gemini_reply()
    assert asyncio.run(provider(transport, key="").explain([FINDING])).provider == "rules"
    assert calls == []


def test_skips_gemini_when_offline():
    async def verify():
        manager = ConnectivityManager(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
        try:
            report = await manager.simulate_cloud(True)
            transport, calls = gemini_reply()
            result = await provider(transport).explain([FINDING], network=report)
            assert result.provider == "rules" and calls == []
        finally:
            await manager.close()
    asyncio.run(verify())
