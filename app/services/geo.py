from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import get_settings


@dataclass
class GeoResult:
    country_code: str | None = None
    country_name: str | None = None
    region: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class GeoProvider(ABC):
    @abstractmethod
    async def lookup(self, ip: str) -> GeoResult | None:
        pass


class IpapiProvider(GeoProvider):
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.geo_provider_a_url.rstrip("/")
        self.timeout = httpx.Timeout(self.settings.geo_request_timeout_seconds)

    async def lookup(self, ip: str) -> GeoResult | None:
        url = f"{self.base_url}/{ip}/json/"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                data = response.json()
                if data.get("error"):
                    return None
                return GeoResult(
                    country_code=data.get("country_code"),
                    country_name=data.get("country_name"),
                    region=data.get("region"),
                    city=data.get("city"),
                    latitude=data.get("latitude"),
                    longitude=data.get("longitude"),
                )
        except Exception:
            return None


class IpinfoProvider(GeoProvider):
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.geo_provider_b_url.rstrip("/")
        self.timeout = httpx.Timeout(self.settings.geo_request_timeout_seconds)

    async def lookup(self, ip: str) -> GeoResult | None:
        url = f"{self.base_url}/{ip}/json"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                data = response.json()
                loc = data.get("loc", "")
                lat, lng = None, None
                if loc:
                    parts = loc.split(",")
                    if len(parts) == 2:
                        lat = float(parts[0])
                        lng = float(parts[1])
                return GeoResult(
                    country_code=data.get("country"),
                    country_name=data.get("country"),
                    region=data.get("region"),
                    city=data.get("city"),
                    latitude=lat,
                    longitude=lng,
                )
        except Exception:
            return None


async def enrich_submission(
    ip: str,
    provider_a: GeoProvider | None = None,
    provider_b: GeoProvider | None = None,
) -> GeoResult | None:
    """
    Try provider A first, then provider B as fallback.
    Returns GeoResult if either succeeds, None if both fail.
    """
    provider_a = provider_a or IpapiProvider()
    provider_b = provider_b or IpinfoProvider()

    result = await provider_a.lookup(ip)
    if result and result.country_code:
        return result

    result = await provider_b.lookup(ip)
    if result and result.country_code:
        return result

    return None
