"""Verify Supabase JWTs with disk-cached JWKS. LAN/localhost bypass.

ponytail: Pi has PyJWT 1.7 without ES256 JWK support; verify P-256 signatures
via cryptography directly. Fall back to /auth/v1/user via curl if needed.
"""
from __future__ import absolute_import

import base64
import json
import logging
import os
import time

import jwt

from supabase_client import JWKS_PATH, _config, _http, fetch_jwks

LAN_PREFIXES = (
    '127.',
    '10.',
    '192.168.',
    '::1',
    'localhost',
)

# token -> (expires_at_monotonic, claims)
_token_cache = {}


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
    header_user = req.headers.get('X-PiHome-User')
    if header_user:
        return header_user

    auth = req.headers.get('Authorization') or ''
    if not auth.startswith('Bearer '):
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
    return claims.get('email') or (claims.get('user_metadata') or {}).get('email')


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


def _b64url_decode(data):
    if isinstance(data, bytes):
        data = data.decode('ascii')
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _verify_es256(token, jwks):
    """Verify ES256 JWT with cryptography (works on PyJWT 1.7 / crypto 3.x)."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError('bad jwt')
    header = json.loads(_b64url_decode(parts[0]))
    kid = header.get('kid')
    jwk = None
    for candidate in jwks.get('keys', []):
        if candidate.get('kty') != 'EC':
            continue
        if kid is None or candidate.get('kid') == kid:
            jwk = candidate
            break
    if jwk is None:
        raise ValueError('no EC jwk for kid=%s' % kid)

    x = int.from_bytes(_b64url_decode(jwk['x']), 'big')
    y = int.from_bytes(_b64url_decode(jwk['y']), 'big')
    pub = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key(default_backend())

    signing_input = ('%s.%s' % (parts[0], parts[1])).encode('ascii')
    sig = _b64url_decode(parts[2])
    if len(sig) != 64:
        raise ValueError('bad es256 sig length')
    der = encode_dss_signature(
        int.from_bytes(sig[:32], 'big'),
        int.from_bytes(sig[32:], 'big'),
    )
    pub.verify(der, signing_input, ec.ECDSA(hashes.SHA256()))

    claims = json.loads(_b64url_decode(parts[1]))
    now = int(time.time())
    if claims.get('exp') and now > int(claims['exp']) + 30:
        raise ValueError('token expired')
    return claims


def _verify_via_supabase(token):
    """Network fallback: ask Supabase who this token is (curl under eventlet)."""
    cfg = _config()
    url = cfg.get('url', '').rstrip('/') + '/auth/v1/user'
    key = cfg.get('anon_key') or cfg.get('service_role_key')
    status, text = _http(
        'GET',
        url,
        {
            'Authorization': 'Bearer ' + token,
            'apikey': key,
        },
        timeout=5,
    )
    if status != 200:
        raise ValueError('supabase user %s %s' % (status, text[:120]))
    data = json.loads(text)
    return {
        'email': data.get('email'),
        'sub': data.get('id'),
        'user_metadata': data.get('user_metadata') or {},
    }


def verify_bearer(token):
    if not token:
        return None
    cached = _token_cache.get(token)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    claims = None
    try:
        if not os.path.exists(JWKS_PATH):
            fetch_jwks(force=True)
        jwks = fetch_jwks(force=False)
        claims = _verify_es256(token, jwks)
    except Exception as e:
        logging.warning('jwt local verify failed: %s', e)
        try:
            fetch_jwks(force=True)
            claims = _verify_es256(token, fetch_jwks(force=False))
        except Exception as e2:
            logging.warning('jwt local verify retry failed: %s', e2)
            try:
                claims = _verify_via_supabase(token)
            except Exception as e3:
                logging.warning('jwt supabase verify failed: %s', e3)
                return None

    # Cache until near exp (cap 5 min)
    ttl = 300
    exp = claims.get('exp')
    if exp:
        ttl = max(30, min(300, int(exp) - int(time.time())))
    _token_cache[token] = (time.monotonic() + ttl, claims)
    if len(_token_cache) > 64:
        # ponytail: drop oldest-ish entries
        for k in list(_token_cache.keys())[:16]:
            _token_cache.pop(k, None)
    return claims
