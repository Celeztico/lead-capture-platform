# Decision 002: Spam Control — Honeypot Field

## Status
Accepted

## Date
2026-10-18

## Context
The public submission endpoint must have at least one demonstrable spam-prevention technique. The technique should be low-friction for legitimate users, not require external dependencies, and be testable.

## Options Considered

### Option A: Honeypot Field (Hidden Form Field)
- **Pros:** Zero friction for humans, no external dependencies, simple to implement/test, catches basic bots
- **Cons:** Sophisticated bots can detect and bypass; not a complete solution alone

### Option B: CAPTCHA (reCAPTCHA/hCaptcha)
- **Pros:** Stronger bot detection
- **Cons:** External dependency, privacy concerns, user friction, API keys required, not free for high volume

### Option C: Rate Limiting Only
- **Pros:** Already required for abuse control
- **Cons:** Doesn't distinguish bots from humans, not a "spam prevention technique" per se

### Option D: Content Analysis (Akismet-style)
- **Pros:** Catches content-based spam
- **Cons:** External dependency, latency, cost, privacy

## Decision
Implement a **Honeypot Field** as the primary spam control for the internship MVP:
- Field name: `website_url` (common bot target)
- Rendered as hidden via CSS (`display: none`) and `tabindex="-1"` `autocomplete="off"`
- Legitimate users won't see/fill it; bots often fill all fields
- Server-side check: if `website_url` is present and non-empty → reject with `400 SPAM_DETECTED`
- Error response: Generic message, no details about honeypot

## Consequences
- **Positive:** Zero user friction, no external dependencies, trivial to test deterministically
- **Negative:** Only catches naive bots; sophisticated scrapers will bypass
- **Mitigation:** Combined with rate limiting, payload validation, and field limits for defense in depth

## Implementation Notes
- Add `website_url` to widget configuration schema as internal/honeypot field (not rendered in public config)
- Widget JS: render hidden input with `name="website_url"`, `style="display:none"`, `tabindex="-1"`, `autocomplete="off"`
- Submission service: check `data.get("website_url")` — if truthy, reject before persistence
- Test: submit with `website_url: "http://spam.com"` → expect `400` with code `SPAM_DETECTED`

## Related Documents
- `docs/architecture.md` §4.3, §5.1
- `docs/api_contracts.md` §9
- `docs/security_spec.md` §6.2
- `docs/submission_flow.md` §5, Stage 5
- `docs/widget_contract.md` §6.1