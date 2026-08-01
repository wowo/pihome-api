"""Verify Supabase JWTs with disk-cached JWKS. LAN/localhost bypass."""
from __future__ import absolute_import

import logging
import os

import jwt

from supabase_client import JWKS_PATH, _config, fetch_jwks

LAN_PREFIXES = (
    '127.',
    '10.',
    '192.168.',
    '::1',
    'localhost',
)


def is_lan_request(req):
    # Prefer Cloudflare / proxy headers only when they claim LAN (rare); else remote_addr.
    addr = (req.headers.get('X-Forwarded-For') or req.remote_addr or '').split(',')[0].strip()
    if not addr:
        return False
    if addr in ('localhost', '::1'):
        return True
    return any(addr.startswith(p) for p in LAN_PREFIXES if p.endswith('.')) or addr.startswith('192.168.')


def get_authenticated_user(req):
    """Return email for history attribution. None when anonymous LAN/cron."""
    # Optional LAN attribution header
    header_user = req.headers.get('X-PiHome-User')
    if header_user:
        return header_user

    auth = req.headers.get('Authorization') or ''
    if not auth.startswith('Bearer '):
        # Legacy CF cookie during transition
        if 'CF_Authorization' in req.cookies:
            try:
                token = jwt.decode(req.cookies.get('CF_Authorization'), options={'verify_signature': False})
                return token.get('email')
            except Exception:
                return None
        return None

    claims = verify_bearer(auth[7:])
    if not claims:
        return None
    return claims.get('email') or claims.get('user_metadata', {}).get('email')


def require_auth(req):
    """Return (ok, error_response_tuple_or_None). LAN/localhost always ok."""
    if is_lan_request(req):
        return True, None
    auth = req.headers.get('Authorization') or ''
    if not auth.startswith('Bearer '):
        return False, ('Unauthorized', 401)
    claims = verify_bearer(auth[7:])
    if not claims:
        return False, ('Unauthorized', 401)
    return True, None


def verify_bearer(token):
    cfg = _config()
    audience = cfg.get('jwt_audience') or 'authenticated'
    issuer = cfg.get('jwt_issuer') or (cfg.get('url', '').rstrip('/') + '/auth/v1')
    try:
        if not os.path.exists(JWKS_PATH):
            fetch_jwks(force=True)
        # PyJWKClient can use file:// or we construct from cached JSON
        jwks = fetch_jwks(force=False)
        from jwt.algorithms import RSAAlgorithm
        header = jwt.get_unverified_header(token)
        kid = header.get('kid')
        key = None
        for jwk in jwks.get('keys', []):
            if jwk.get('kid') == kid or kid is None:
                key = RSAAlgorithm.from_jwk(jwk)
                break
        if key is None and jwks.get('keys'):
            key = RSAAlgorithm.from_jwk(jwks['keys'][0])
        if key is None:
            # Symmetric fallback for legacy JWT secret if configured
            secret = cfg.get('jwt_secret')
            if secret:
                return jwt.decode(token, secret, algorithms=['HS256'], audience=audience, issuer=issuer)
            return None
        return jwt.decode(token, key=key, algorithms=['RS256', 'ES256'], audience=audience, options={'verify_aud': False})
    except Exception as e:
        logging.warning('jwt verify failed: %s', e)
        # Refresh JWKS once on failure (key rotation)
        try:
            fetch_jwks(force=True)
        except Exception:
            pass
        return None
