import asyncio
import json
from types import SimpleNamespace

import httpx

from services.agent.connectivity import ConnectivityManager
from services.agent.diagnosis import ClaudeDiagnosisProvider, OllamaDiagnosisProvider

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


class FakeClaude:
    def __init__(self, answer=None, stop_reason="end_turn", error=None):
        self.calls = []
        self.answer, self.stop_reason, self.error = answer or ANSWER, stop_reason, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=json.dumps(self.answer))])


def offline_ollama():
    def fail(request):
        raise httpx.ConnectError("Ollama unavailable", request=request)
    return OllamaDiagnosisProvider(transport=httpx.MockTransport(fail))


def test_claude_answers_when_online():
    fake = FakeClaude()
    result = asyncio.run(ClaudeDiagnosisProvider(offline_ollama(), client=fake).explain([FINDING]))
    assert result.provider == "claude" and result.headline == ANSWER["headline"]
    assert result.recommended_action_id == "stop_demo_workload"
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["output_config"]["effort"] == "low"
    assert call["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in call["betas"]


def test_falls_back_to_local_on_error_or_refusal():
    for fake in (FakeClaude(error=RuntimeError("no internet")), FakeClaude(stop_reason="refusal"),
                 FakeClaude(answer={**ANSWER, "explanation": "Run netsh winsock reset now"})):
        result = asyncio.run(ClaudeDiagnosisProvider(offline_ollama(), client=fake).explain([FINDING]))
        assert result.provider == "rules"


def test_skips_claude_when_offline():
    async def verify():
        manager = ConnectivityManager(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
        try:
            report = await manager.simulate_cloud(True)
            fake = FakeClaude()
            result = await ClaudeDiagnosisProvider(offline_ollama(), client=fake).explain([FINDING], network=report)
            assert result.provider == "rules" and fake.calls == []
        finally:
            await manager.close()
    asyncio.run(verify())
