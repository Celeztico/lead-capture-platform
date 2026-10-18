# Decision 003: Geolocation Provider Fallback

## Status
Accepted

## Date
2026-10-18

## Context
The platform must enrich submissions with approximate location data using a provider fallback chain (Provider A → Provider B). Enrichment must not block or fail the core submission persistence.

## Options Considered

### Option A: ipapi.co → ipinfo.io (Free Tiers)
- **ipapi.co:** 1000 req/day free, HTTPS, JSON, includes country/city/lat-long
- **ipinfo.io:** 50k req/month free, HTTPS, JSON, similar data
- **Pros:** Free tiers sufficient for demo, no API key required for basic use, well-documented
- **Cons:** Rate limits on free tiers, no SLA

### Option B: ipgeolocation.io → ipapi.is
- **Pros:** Alternative providers
- **Cons:** Less familiar, varying free tier limits

### Option C: MaxMind GeoIP2 (Self-hosted)
- **Pros:** No external calls, no rate limits
- **Cons:** Database updates, larger container, licensing for GeoLite2

## Decision
Use **ipapi.co (Provider A) → ipinfo.io (Provider B)** with the following parameters:

### Provider A: ipapi.co
- Base URL: `https://ipapi.co/{ip}/json/`
- Timeout: 2 seconds connect, 2 seconds read
- No API key for basic tier (1000/day)
- Response fields: `country_code`, `country_name`, `region`, `city`, `latitude`, `longitude`

### Provider B: ipinfo.io
- Base URL: `https://ipinfo.io/{ip}/json`
- Timeout: 2 seconds connect, 2 seconds read
- No API key for basic tier (50k/month)
- Response fields: `country`, `region`, `city`, `loc` (lat,long)

### Fallback Logic
1. Extract client IP from request (direct connection or trusted proxy header `X-Forwarded-For`)
2. Call Provider A with timeout
3. If Provider A fails (timeout, non-2xx, invalid JSON, missing required fields) → call Provider B
4. If Provider B fails → store submission without geo data
5. On success: store `country_code`, `country_name`, `region`, `city`, `lat`, `lng` in submission enrichment fields

### Failure Handling
- Both providers down → submission still succeeds, enrichment fields remain null
- Log sanitized failure (provider name, error category, no IP/response body)
- Enrichment runs asynchronously via background job (see Decision 005)

## Consequences
- **Positive:** Free tiers adequate for demo, simple HTTP APIs, clear fallback chain
- **Negative:** Rate limits on free tiers; IP privacy considerations
- **Mitigation:** Cache results per IP (optional future), minimal data sent (IP only)

## Implementation Notes
- Create `app/services/geo.py` with `GeoProvider` protocol and two implementations
- Use `httpx.AsyncClient` with timeout config
- Make providers injectable for tests (FastAPI dependency override)
- Background worker calls enrichment after submission commit
- Store enrichment in `submissions` table: `country_code`, `country_name`, `region`, `city`, `latitude`, `longitude`, `enrichment_status`

## Related Documents
- `docs/architecture.md` §4.3, §4.4
- `docs/api_contracts.md` §2.4
- `docs/security_spec.md` §10.1
- `docs/submission_flow.md` §4, Stage 8
- `docs/event_spec.md` §5.1