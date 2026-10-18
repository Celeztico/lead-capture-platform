# Decision 001: Authentication Approach

## Status
Accepted

## Date
2026-10-18

## Context
The Lead-Capture Platform requires authentication for workspace management APIs. The authentication mechanism must be selected before implementing any protected endpoints. The chosen approach must support:
- Stateless verification (no server-side session store required for MVP)
- Workspace-scoped authorization
- Token revocation/expiry
- Secure credential storage

## Options Considered

### Option A: JWT Bearer Tokens (Stateless)
- **Pros:** No server-side session store, scales horizontally, self-contained claims, standard libraries
- **Cons:** Cannot revoke before expiry without additional infrastructure (blocklist), token size

### Option B: Session Cookies (Server-side)
- **Pros:** Immediate revocation, smaller client payload, CSRF protection possible
- **Cons:** Requires session store (Redis/DB), CSRF complexity, harder to scale

### Option C: API Keys (Long-lived)
- **Pros:** Simple for machine-to-machine
- **Cons:** Not suitable for user login flows, rotation complexity

## Decision
Use **JWT Bearer Tokens (HS256)** with the following parameters:
- Algorithm: HS256 (symmetric, shared secret)
- Access token expiry: 30 minutes
- Claims: `sub` (user_id), `workspace_id`, `role`, `exp`, `iat`
- Refresh token: Not implemented in MVP (re-login required)
- Token storage: Client-side (localStorage/cookie), sent via `Authorization: Bearer <token>`
- Secret: `SECRET_KEY` from environment (min 32 chars)
- Revocation: Not supported in MVP (short expiry mitigates risk)

## Consequences
- **Positive:** Simple implementation, no session store needed, works with mobile/SPA clients
- **Negative:** Cannot force logout before token expiry; mitigated by 30-min expiry
- **Risk:** Token leakage = full access until expiry; use HTTPS only in production

## Implementation Notes
- Use `python-jose[cryptography]` for encoding/decoding
- Create `app/core/security.py` with `create_access_token()` and `verify_token()`
- Add `get_current_user` FastAPI dependency in `app/api/deps.py`
- All `/api/v1/*` endpoints require valid token
- Public endpoints (`/public/*`, `/widget/*`, `/health/*`) remain unauthenticated

## Related Documents
- `docs/architecture.md` §4.1, §4.2
- `docs/api_contracts.md` §2.4
- `docs/security_spec.md` §4.1, §4.2
- `docs/domain_models.md` §4.1