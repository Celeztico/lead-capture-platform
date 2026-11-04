"""Unit tests for geo enrichment provider fallback."""

from app.services.geo import GeoProvider, GeoResult, enrich_submission


class FakeProvider(GeoProvider):
    def __init__(self, result: GeoResult | None):
        self.result = result
        self.calls: list[str] = []

    async def lookup(self, ip: str) -> GeoResult | None:
        self.calls.append(ip)
        return self.result


class TestEnrichSubmissionFallback:
    async def test_provider_a_success_skips_provider_b(self):
        a = FakeProvider(GeoResult(country_code="US"))
        b = FakeProvider(GeoResult(country_code="GB"))
        result = await enrich_submission("203.0.113.9", provider_a=a, provider_b=b)
        assert result is not None
        assert result.country_code == "US"
        assert a.calls == ["203.0.113.9"]
        assert b.calls == []

    async def test_provider_a_failure_falls_back_to_b(self):
        a = FakeProvider(None)
        b = FakeProvider(GeoResult(country_code="GB"))
        result = await enrich_submission("203.0.113.9", provider_a=a, provider_b=b)
        assert result is not None
        assert result.country_code == "GB"
        assert a.calls == ["203.0.113.9"]
        assert b.calls == ["203.0.113.9"]

    async def test_provider_a_without_country_falls_back_to_b(self):
        # A responds but with no usable country → treated as failure
        a = FakeProvider(GeoResult(country_code=None))
        b = FakeProvider(GeoResult(country_code="DE"))
        result = await enrich_submission("203.0.113.9", provider_a=a, provider_b=b)
        assert result is not None
        assert result.country_code == "DE"
        assert b.calls == ["203.0.113.9"]

    async def test_both_providers_fail_returns_none(self):
        a = FakeProvider(None)
        b = FakeProvider(GeoResult(country_code=None))
        result = await enrich_submission("203.0.113.9", provider_a=a, provider_b=b)
        assert result is None
        assert a.calls and b.calls

    async def test_captured_ip_is_forwarded_to_providers(self):
        a = FakeProvider(GeoResult(country_code="FR"))
        b = FakeProvider(None)
        await enrich_submission("198.51.100.7", provider_a=a, provider_b=b)
        assert a.calls == ["198.51.100.7"]
