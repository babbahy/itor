"""Explanations: Claude when online, the local model (Ollama) offline, simple rules as the last backup."""
from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
import json
import re
from typing import Annotated, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .connectivity import ConnectivityReport, ServiceState, local_model_name, normalize_local_ollama


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
ActionId = Literal["stop_demo_workload"]
Question = Literal["internet", "adapter", "dns", "offline", "blocked", "nexthink", "workload"]


class ModelExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: ShortText
    explanation: ShortText
    possible_causes: list[ShortText] = Field(max_length=3)
    potential_impact: ShortText
    recommended_action_id: ActionId | None
    uncertainty: ShortText


class DiagnosisResult(ModelExplanation):
    status: Literal["complete", "fallback"]
    provider: Literal["claude", "ollama", "rules"]
    model: str | None = None
    observed_facts: list[str] = Field(default_factory=list)
    safe_steps: list[str] = Field(default_factory=list)
    action_explanation: str
    verification_advice: str


class DiagnosisProvider(Protocol):
    async def explain(
        self, findings: Sequence[Mapping[str, object]], *,
        question: str | None = None, network: ConnectivityReport | None = None,
    ) -> DiagnosisResult: ...


def question_intent(question: str | None) -> Question | None:
    """Classify supported questions without including the user's text in a prompt."""
    if not question:
        return None
    text = question.casefold().strip()[:600]
    if "nexthink" in text:
        return "nexthink"
    if "dns" in text or "resolver" in text:
        return "dns"
    if "wi-fi" in text or "wifi" in text or "adapter" in text or "airplane" in text:
        return "adapter"
    if "still use" in text or "offline" in text or "itor" in text:
        return "offline"
    if "internet" in text or "connect" in text or "network" in text:
        return "internet"
    if "blocked" in text or "stuck" in text or "can't work" in text or "cannot work" in text:
        return "blocked"
    if any(term in text for term in ("cpu", "workload", "memory", "disk", "slow", "lag", "performance")):
        return "workload"
    return None


def sanitized_findings(findings: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Only project evidence produced by the readiness engine, never raw snapshots."""
    sanitized: list[dict[str, object]] = []
    for finding in findings[:12]:
        summary: dict[str, object] = {}
        for key in ("category", "severity", "title", "evidence", "potential_impact", "limitations"):
            value = finding.get(key)
            if isinstance(value, str):
                summary[key] = value[:400]
            elif isinstance(value, list):
                summary[key] = [item[:200] for item in value[:4] if isinstance(item, str)]
        window = finding.get("window_seconds")
        if isinstance(window, (int, float)) and not isinstance(window, bool) and 0 <= window <= 3600:
            summary["window_seconds"] = window
        actions = finding.get("recommended_action_ids", ())
        if isinstance(actions, (tuple, list)) and "stop_demo_workload" in actions:
            summary["approved_action_ids"] = ["stop_demo_workload"]
        sanitized.append(summary)
    return sanitized


def network_observations(network: ConnectivityReport) -> dict[str, dict[str, str]]:
    return {
        key: {
            "state": observation.state.value,
            "observation": observation.explanation,
        }
        for key in ("network_interface", "gateway", "dns_resolver", "dns", "internet", "nexthink", "nexthink_auth")
        if (observation := getattr(network, key))
    }


def factual_list(value: object) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


QUESTION_GUIDANCE: dict[Question, tuple[str, str, str]] = {
    "adapter": (
        "Review the network adapter",
        "The adapter check looks for an active interface with an IP address. It cannot identify the selected Wi-Fi network.",
        "Check Wi-Fi, airplane mode, and whether the expected network is selected in your system settings.",
    ),
    "dns": (
        "Review the DNS check",
        "A DNS failure can come from the resolver, the route to it, or the test name. The result does not identify which one.",
        "Run the connection investigation for a permitted test, then contact IT if name resolution continues to fail.",
    ),
    "internet": (
        "Investigate the connection",
        "The adapter, resolver, and approved HTTPS endpoint measure different parts of the connection. One endpoint cannot establish wider service availability.",
        "Confirm the expected network is selected and review any VPN status in your system settings.",
    ),
    "nexthink": (
        "Review the Nexthink connection",
        "Device connectivity, tenant reachability, and tenant authentication are checked separately.",
        "Contact IT if an authorized tenant integration reports an authentication error or remains unreachable.",
    ),
    "offline": (
        "Local help is still available",
        "itor keeps working on this device without internet. It keeps counting your time and can explain problems with a local model.",
        "Click \"I'm blocked\" so this time is counted as lost because of tools, then follow the steps itor suggests.",
    ),
    "blocked": (
        "You are blocked by a tool",
        "itor counts this time as lost because of tools, not as idle time.",
        "Click \"I'm blocked\" while you wait, then ask itor about your internet or your PC.",
    ),
    "workload": (
        "Review the device checks",
        "Resource checks use recent CPU readings and current memory and disk measurements. The findings show any conditions the checks detected.",
        "Run a new PC check for updated readings.",
    ),
}


def network_causes(network: ConnectivityReport, intent: Question) -> list[str]:
    if network.simulated_cloud_outage and intent in ("internet", "offline", "nexthink"):
        return ["The demo is simulating a cloud outage. The device network is unchanged."]
    if intent in ("adapter", "internet") and network.network_interface.state == ServiceState.DISCONNECTED:
        return ["An adapter may be disabled, disconnected, or still waiting for an IP address."]
    if intent in ("dns", "internet") and network.dns.state == ServiceState.UNREACHABLE:
        return ["The resolver, its network path, or the approved test hostname may be unavailable."]
    if intent == "internet" and network.internet.state == ServiceState.UNREACHABLE:
        return ["The approved endpoint or the connection to it may be unavailable."]
    return []


class RulesBasedDiagnosisProvider:
    async def explain(
        self, findings: Sequence[Mapping[str, object]], *,
        question: str | None = None, network: ConnectivityReport | None = None,
    ) -> DiagnosisResult:
        safe = sanitized_findings(findings)
        intent = question_intent(question)
        controlled = next((item for item in safe if item.get("approved_action_ids")), None)
        evidence = [fact for item in safe for fact in factual_list(item.get("evidence"))]
        action: ActionId | None = "stop_demo_workload" if controlled else None
        top = controlled or (safe[0] if safe else {})
        headline = str(top.get("title") or "Review the current device checks")
        explanation = (factual_list(top.get("evidence")) or [
            "No issue was supplied for explanation. Run a PC check to see which device checks have completed."
        ])[0]
        impact = (factual_list(top.get("potential_impact")) or ["The exact effect on your work was not measured."])[0]
        uncertainty = (factual_list(top.get("limitations")) or [
            "These checks cover the local measurements shown. Audio and video call quality were not tested."
        ])[0]
        causes: list[str] = []
        safe_steps: list[str] = []
        if network and (intent in ("adapter", "dns", "internet", "nexthink", "offline", "blocked") or network.offline_rescue):
            if intent != "workload":
                evidence.extend(value["observation"] for value in network_observations(network).values())
            if network.offline_rescue and not top and intent is None:
                intent = "internet"
        if intent:
            headline, explanation, guidance = QUESTION_GUIDANCE[intent]
            safe_steps.append(guidance)
            if intent == "nexthink" and network:
                explanation = network.nexthink.explanation
                if network.nexthink.state == ServiceState.NOT_CONFIGURED:
                    safe_steps.clear()
            if network:
                causes = network_causes(network, intent)
        elif question:
            headline = "Ask about a supported readiness check"
            explanation = "Try a question about the adapter, DNS, internet, Nexthink, being blocked, or device load."
        return DiagnosisResult(
            status="complete", provider="rules", headline=headline, explanation=explanation,
            observed_facts=evidence, possible_causes=causes, potential_impact=impact, safe_steps=safe_steps,
            recommended_action_id=action,
            action_explanation="With approval, itor stops only the temporary workload it created." if action else
            "No local corrective action is available for this result.",
            uncertainty=uncertainty,
            verification_advice="itor checks that the workload exited and collects fresh metrics." if action else
            "Run the PC check again to refresh the measurements.",
        )


system_prompt = (
    "You are itor's helper. You explain device and network problems to an employee in plain, simple words. "
    "The JSON observations are the only evidence. Briefly describe what the checks mean and the likely impact on their work. Phrase possible causes as possibilities. "
    "Do not invent measurements, readings, states, personal details, Wi-Fi identities, or successful fixes. "
    "Do not repeat or invent numeric measurements. Do not include shell commands, scripts, links, or passwords. "
    "For network issues, suggest only safe manual checks in system settings, through IT, or through itor. "
    "Never suggest resetting adapters, changing DNS/firewall settings, or terminating VPNs or other apps. "
    "Use the approved local action ID only when listed, otherwise return null. "
    "Write concise plain text fields using the supplied JSON schema."
)

# Generated interpretations cannot introduce unsupported numerical facts or links.
unsafe_prose = re.compile(
    r"\d|https?://|www\.|-EncodedCommand|\b(?:sudo|killall|taskkill|netsh|systemctl|"
    r"ipconfig|ifconfig|iptables|powershell|curl|wget|bash|chmod|regedit)\b"
    r"|\b(?:reset|disable|modify|terminate|turn off)\b.{0,30}"
    r"\b(?:wi-fi|wifi|adapter|vpn|dns|firewall|security|antivirus)\b",
    re.IGNORECASE,
)


class OllamaDiagnosisProvider:
    def __init__(
        self, *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3.5:4b",
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = normalize_local_ollama(base_url)
        self.model = local_model_name(model)
        self.timeout = max(float(timeout), 0.1)
        self.transport = transport
        self.rules = RulesBasedDiagnosisProvider()
        self._inference = asyncio.Lock()

    @property
    def is_loading(self) -> bool:
        return self._inference.locked()

    async def explain(
        self, findings: Sequence[Mapping[str, object]], *,
        question: str | None = None, network: ConnectivityReport | None = None,
    ) -> DiagnosisResult:
        baseline = await self.rules.explain(findings, question=question, network=network)
        intent = question_intent(question)
        if (question and not intent) or (not findings and not intent and not (network and network.offline_rescue)):
            return baseline
        fallback = baseline.model_copy(update={"status": "fallback"})
        if self._inference.locked() or (network and network.ollama.state in (
            ServiceState.UNREACHABLE, ServiceState.DISCONNECTED, ServiceState.DEGRADED,
        )):
            return fallback

        schema = ModelExplanation.model_json_schema()
        evidence: dict[str, object] = {"findings": sanitized_findings(findings), "question_topic": intent}
        if network and (intent not in (None, "workload") or network.offline_rescue):
            evidence["network_checks"] = network_observations(network)
            evidence["simulated_cloud_outage"] = network.simulated_cloud_outage
        prompt = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps({"observations": evidence, "output_schema": schema})},
            ],
            "stream": False,
            "think": False,
            "format": schema,
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 440},
        }
        async with self._inference:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 2)),
                    follow_redirects=False, trust_env=False, transport=self.transport,
                ) as client:
                    response = await asyncio.wait_for(
                        client.post(f"{self.base_url}/api/chat", json=prompt), self.timeout,
                    )
                response.raise_for_status()
                payload = response.json()
                if payload["done"] is not True or payload.get("done_reason") == "length":
                    return fallback
                content = payload["message"]["content"]
                if not isinstance(content, str) or len(content) > 20_000:
                    return fallback
                model_answer = ModelExplanation.model_validate_json(content)
            except (httpx.HTTPError, TimeoutError, asyncio.TimeoutError, ValueError, KeyError, TypeError, AttributeError):
                return fallback
        if model_answer.recommended_action_id not in (None, baseline.recommended_action_id):
            return fallback
        prose = (
            model_answer.headline, model_answer.explanation, *model_answer.possible_causes,
            model_answer.potential_impact, model_answer.uncertainty,
        )
        if any(unsafe_prose.search(field) for field in prose):
            return fallback
        return DiagnosisResult(
            **model_answer.model_dump(exclude={"recommended_action_id"}), status="complete",
            provider="ollama", model=self.model, observed_facts=baseline.observed_facts,
            safe_steps=baseline.safe_steps,
            recommended_action_id=baseline.recommended_action_id,
            action_explanation=baseline.action_explanation, verification_advice=baseline.verification_advice,
        )


# Plain JSON schema for Claude's structured output (length limits are checked after, by ModelExplanation).
CLAUDE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "explanation": {"type": "string"},
        "possible_causes": {"type": "array", "items": {"type": "string"}},
        "potential_impact": {"type": "string"},
        "recommended_action_id": {"anyOf": [{"type": "string", "enum": ["stop_demo_workload"]}, {"type": "null"}]},
        "uncertainty": {"type": "string"},
    },
    "required": ["headline", "explanation", "possible_causes", "potential_impact", "recommended_action_id", "uncertainty"],
    "additionalProperties": False,
}


class ClaudeDiagnosisProvider:
    """Uses Claude when internet works and an API key is set. Otherwise hands over to the local model."""

    def __init__(self, local: OllamaDiagnosisProvider, *, model: str = "claude-opus-5-5",
                 timeout: float = 25.0, client: object | None = None):
        self.local = local
        self.model = model
        self.timeout = timeout
        self._client = client

    @property
    def is_loading(self) -> bool:
        return self.local.is_loading

    @property
    def enabled(self) -> bool:
        return self._client is not None or bool(os.getenv("ANTHROPIC_API_KEY"))

    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(timeout=self.timeout, max_retries=0)
        return self._client

    @staticmethod
    def online(network: ConnectivityReport | None) -> bool:
        if network is None:
            return True
        if network.simulated_cloud_outage or network.offline_rescue:
            return False
        return network.internet.state not in (ServiceState.DISCONNECTED, ServiceState.UNREACHABLE) and             network.network_interface.state != ServiceState.DISCONNECTED

    async def explain(
        self, findings: Sequence[Mapping[str, object]], *,
        question: str | None = None, network: ConnectivityReport | None = None,
    ) -> DiagnosisResult:
        if not self.enabled or not self.online(network):
            return await self.local.explain(findings, question=question, network=network)
        baseline = await self.local.rules.explain(findings, question=question, network=network)
        intent = question_intent(question)
        evidence: dict[str, object] = {"findings": sanitized_findings(findings), "question_topic": intent,
                                       "question": (question or "")[:400] or None}
        if network:
            evidence["network_checks"] = network_observations(network)
        try:
            response = await self.client().beta.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": json.dumps({"observations": evidence})}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": CLAUDE_SCHEMA}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if response.stop_reason != "end_turn":  # refusal, max_tokens, ...
                raise ValueError(f"Claude stopped: {response.stop_reason}")
            text = next(block.text for block in response.content if block.type == "text")
            answer = ModelExplanation.model_validate_json(text)
        except Exception:  # Any problem (no internet, bad key, refusal, bad JSON): use the local model instead.
            return await self.local.explain(findings, question=question, network=network)
        if answer.recommended_action_id not in (None, baseline.recommended_action_id):
            return await self.local.explain(findings, question=question, network=network)
        prose = (answer.headline, answer.explanation, *answer.possible_causes, answer.potential_impact, answer.uncertainty)
        if any(unsafe_prose.search(field) for field in prose):
            return await self.local.explain(findings, question=question, network=network)
        return DiagnosisResult(
            **answer.model_dump(exclude={"recommended_action_id"}), status="complete",
            provider="claude", model=self.model, observed_facts=baseline.observed_facts,
            safe_steps=baseline.safe_steps,
            recommended_action_id=baseline.recommended_action_id,
            action_explanation=baseline.action_explanation, verification_advice=baseline.verification_advice,
        )
