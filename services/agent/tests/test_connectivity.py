from __future__ import annotations

import asyncio
from datetime import timedelta
import socket

import httpx
import pytest

from services.agent import connectivity
from services.agent.connectivity import CloudProbeResult, ConnectivityManager, Observation, ServiceState, utc_now


CONNECTED = Observation(ServiceState.CONNECTED, "An active adapter was observed.")


@pytest.fixture(autouse=True)
def stable_local_network(monkeypatch):
    monkeypatch.setattr(connectivity, "check_local_network", lambda: {
        "network_interface": CONNECTED, "gateway": CONNECTED, "dns_resolver": CONNECTED,
    })


def transport_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "qwen3.5:4b"}]})
    return httpx.Response(204)


def test_internet_outage_keeps_ollama_available():
    def handler(request):
        if request.url.path != "/api/tags":
            raise httpx.ConnectError("name unreachable", request=request)
        return transport_handler(request)

    async def verify():
        manager = ConnectivityManager(
            internet_probe_url="https://192.0.2.1/health", transport=httpx.MockTransport(handler),
        )
        try:
            report = await manager.inspect(probe=True)
            assert report.agent.state == report.ollama.state == ServiceState.CONNECTED
            assert report.internet.state == ServiceState.UNREACHABLE
            assert report.offline_rescue
            assert report.internet.last_success_at is None
            assert report.internet.last_checked_at.tzinfo
        finally:
            await manager.close()

    asyncio.run(verify())


def test_available_internet_and_failed_nexthink_are_independent():
    async def cloud():
        return CloudProbeResult(
            Observation(ServiceState.UNREACHABLE, "Tenant test endpoint timed out."),
            Observation(ServiceState.UNKNOWN, "Authentication was unavailable."),
        )

    async def verify():
        manager = ConnectivityManager(
            internet_probe_url="https://192.0.2.1/health", nexthink_probe=cloud,
            transport=httpx.MockTransport(transport_handler),
        )
        try:
            report = await manager.inspect(probe=True)
            assert report.internet.state == ServiceState.CONNECTED
            assert report.nexthink.state == report.nexthink_reachability.state == ServiceState.UNREACHABLE
            assert report.nexthink_auth.state == ServiceState.UNKNOWN
            assert report.offline_rescue
        finally:
            await manager.close()

    asyncio.run(verify())


def test_no_external_probe_or_nexthink_when_unconfigured():
    requests = []

    def handler(request):
        requests.append(request)
        return transport_handler(request)

    async def verify():
        manager = ConnectivityManager(transport=httpx.MockTransport(handler))
        try:
            report = await manager.inspect(probe=True)
            assert [request.url.path for request in requests] == ["/api/tags"]
            assert report.nexthink.state == report.internet.state == report.dns.state == ServiceState.NOT_CONFIGURED
            assert not report.offline_rescue
        finally:
            await manager.close()

    asyncio.run(verify())


def test_dns_failure_does_not_mark_adapter_disconnected(monkeypatch):
    def dns_lookup(*_args, **_kwargs):
        raise socket.gaierror("test DNS failed")

    monkeypatch.setattr(socket, "getaddrinfo", dns_lookup)

    async def verify():
        manager = ConnectivityManager(
            internet_probe_url="https://connectivity.invalid/health",
            transport=httpx.MockTransport(transport_handler),
        )
        try:
            pending = await manager.status()
            assert pending.dns.state == ServiceState.UNKNOWN
            report = await manager.inspect(probe=True)
            assert report.dns.state == ServiceState.UNREACHABLE
            assert report.dns.error_category == "dns_resolution"
            assert report.network_interface.state == ServiceState.CONNECTED
            assert report.internet.state == ServiceState.CONNECTED
            assert not report.offline_rescue
        finally:
            await manager.close()

    asyncio.run(verify())


def test_authentication_errors_preserve_reachability():
    async def cloud():
        request = httpx.Request("GET", "https://example.invalid/health")
        response = httpx.Response(401, request=request)
        response.raise_for_status()
        raise AssertionError("status should have raised")

    def handler(request):
        if request.url.path != "/api/tags":
            return httpx.Response(403)
        return transport_handler(request)

    async def verify():
        manager = ConnectivityManager(
            internet_probe_url="https://192.0.2.1/health", nexthink_probe=cloud,
            transport=httpx.MockTransport(handler),
        )
        try:
            report = await manager.inspect(probe=True)
            assert report.internet.state == ServiceState.DEGRADED
            assert report.nexthink_reachability.state == ServiceState.CONNECTED
            assert report.nexthink.state == report.nexthink_auth.state == ServiceState.AUTHENTICATION_ERROR
            assert not report.offline_rescue
        finally:
            await manager.close()

    asyncio.run(verify())


def test_rate_limited_retries_and_stable_recovery(monkeypatch):
    elapsed = 0
    internet_calls = []
    changes = []
    monkeypatch.setattr(connectivity, "monotonic", lambda: elapsed)

    def handler(request):
        if request.url.path != "/api/tags":
            internet_calls.append(elapsed)
            if len(internet_calls) <= 2:
                raise httpx.ConnectError("offline", request=request)
        return transport_handler(request)

    async def verify():
        nonlocal elapsed
        manager = ConnectivityManager(
            internet_probe_url="https://192.0.2.1/health", transport=httpx.MockTransport(handler),
            probe_interval=30, stability_seconds=5,
            on_change=lambda old, new: changes.append((old.name, old.state, new.state)),
        )
        try:
            assert (await manager.inspect(probe=True)).offline_rescue
            elapsed = 3
            assert (await manager.inspect(probe=True)).offline_rescue
            assert len(internet_calls) == 1
            elapsed = 30
            assert (await manager.inspect(probe=True)).offline_rescue
            assert len(internet_calls) == 2
            elapsed = 60
            recovered = await manager.inspect(probe=True)
            assert recovered.internet.state == ServiceState.CONNECTED
            assert recovered.offline_rescue
            elapsed = 63
            assert (await manager.inspect()).offline_rescue
            elapsed = 65
            result = await manager.inspect()
            assert not result.offline_rescue
            assert result.internet.last_success_at is not None
            assert len([change for change in changes if change[0] == "Internet"]) == 2
            assert len(internet_calls) == 3
        finally:
            await manager.close()

    asyncio.run(verify())


def test_cloud_simulation_preserves_previous_provider_and_labels_stale_data():
    async def cloud():
        return CloudProbeResult(CONNECTED, CONNECTED)

    async def verify():
        manager = ConnectivityManager(
            nexthink_probe=cloud, transport=httpx.MockTransport(transport_handler), stability_seconds=0,
        )
        try:
            first = await manager.inspect(probe=True)
            assert first.nexthink.state == ServiceState.CONNECTED
            assert first.cloud_last_updated_at is None
            retained = utc_now() - timedelta(minutes=1)
            manager.mark_cloud_context_updated(retained)
            outage = await manager.simulate_cloud(True)
            assert outage.offline_rescue and outage.simulated_cloud_outage
            assert outage.nexthink.error_category == "simulated_outage"
            assert outage.ollama.state == outage.network_interface.state == ServiceState.CONNECTED
            assert outage.cloud_last_updated_at == retained and outage.cloud_data_stale
            await manager.simulate_cloud(False)
            restored = await manager.inspect(probe=True)
            assert restored.nexthink.state == ServiceState.CONNECTED
            assert not restored.offline_rescue and not restored.simulated_cloud_outage
            assert restored.cloud_data_stale
            manager.mark_cloud_context_updated(utc_now())
            assert not (await manager.status()).cloud_data_stale
        finally:
            await manager.close()

    asyncio.run(verify())


@pytest.mark.parametrize("base_url", [
    "https://127.0.0.1:11434",
    "http://example.invalid:11434",
    "http://127.0.0.1@example.invalid:11434",
    "http://127.0.0.1:11434/forward",
])
def test_inference_destination_must_be_loopback(base_url):
    with pytest.raises(ValueError, match="loopback"):
        ConnectivityManager(ollama_base_url=base_url)


def test_virtual_and_self_assigned_adapters_do_not_count_as_connected():
    from services.agent.connectivity import counts_as_network
    physical = {"Wi-Fi 2", "Ethernet"}
    assert counts_as_network("Wi-Fi 2", "10.101.0.63", physical)
    assert not counts_as_network("Ethernet 2", "192.168.56.1", physical)       # VirtualBox host-only
    assert not counts_as_network("Ethernet", "169.254.25.169", physical)       # no DHCP: self-assigned
    assert not counts_as_network("Wi-Fi 2", "fe80::a947:e492:c2e1:aee3", physical)
    assert not counts_as_network("vEthernet (WSL)", "172.20.0.1", None)        # unknown list: name rule
    assert counts_as_network("eth0", "192.168.1.20", None)
