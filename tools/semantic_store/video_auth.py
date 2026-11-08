"""Offline OIDC access-token verifier for the QualityRAG video read-only MCP.

Does not implement an OAuth authorization server, login, refresh tokens,
dynamic discovery or JWKS fetching. Public keys and source ACLs are
operator-provisioned local files. Accepts only signed RS256 access JWTs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SOURCE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
MAX_CONFIG_BYTES = 128 * 1024


class TokenAccessError(ValueError):
    pass


def _read_json(path):
    if not isinstance(path, str) or not path:
        raise TokenAccessError("Auth configuration file missing")
    file = Path(path).expanduser().resolve(strict=True)
    if not file.is_file() or file.stat().st_size > MAX_CONFIG_BYTES:
        raise TokenAccessError("Invalid auth configuration file")
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise TokenAccessError("Invalid JSON auth configuration") from exc


class TokenVerifier:
    def __init__(self, *, issuer, audience, jwks_file, acl_file, operator_source_ids):
        if not isinstance(issuer, str) or not issuer.startswith("https://") or len(issuer)>512:
            raise TokenAccessError("HTTPS issuer required")
        if not isinstance(audience, str) or not audience or len(audience)>256:
            raise TokenAccessError("Audience required")
        self.issuer, self.audience = issuer, audience
        self.operator_source_ids = frozenset(operator_source_ids)
        jwks = _read_json(jwks_file)
        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise TokenAccessError("Valid JWKS file required")
        self.public_keys = {}
        for k in jwks["keys"]:
            if not isinstance(k, dict) or k.get("kty") != "RSA" or k.get("alg") not in (None,"RS256") or k.get("use") not in (None,"sig"):
                raise TokenAccessError("Only RSA signature keys are supported")
            kid=k.get("kid")
            if not isinstance(kid,str) or not 1<=len(kid)<=128 or kid in self.public_keys:
                raise TokenAccessError("JWKS key IDs must be unique and nonempty")
            self.public_keys[kid]=k
        if not 1<=len(self.public_keys)<=16:
            raise TokenAccessError("JWKS must contain 1-16 approved keys")
        acl=_read_json(acl_file)
        if not isinstance(acl,dict) or not isinstance(acl.get("subjects"),dict):
            raise TokenAccessError("Subjects ACL map required")
        self.acl={}
        for sub,ids in acl["subjects"].items():
            if not isinstance(sub,str) or not 1<=len(sub)<=200 or not isinstance(ids,list) or len(ids)>1000:
                raise TokenAccessError("Invalid subject ACL")
            if len(ids)!=len(set(ids)) or any(not isinstance(x,str) or SOURCE_ID.fullmatch(x) is None for x in ids):
                raise TokenAccessError("Invalid source ACL")
            self.acl[sub]=frozenset(ids)

    def authorize(self, token):
        if not isinstance(token,str) or not 10<=len(token)<=8192:
            raise TokenAccessError("Invalid bearer JWT")
        try:
            import jwt
            header=jwt.get_unverified_header(token)
            if header.get("alg")!="RS256" or header.get("typ","JWT") not in ("JWT","at+jwt"):
                raise TokenAccessError("Unsupported token signing profile")
            kid=header.get("kid")
            key_data=self.public_keys.get(kid)
            if key_data is None:
                raise TokenAccessError("Unknown key ID")
            key=jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
            claims=jwt.decode(token,key=key,algorithms=["RS256"],
                issuer=self.issuer,audience=self.audience,leeway=30,
                options={"require":["exp","iat","iss","aud","sub"]})
        except TokenAccessError:
            raise
        except (ValueError,TypeError,KeyError,ImportError,Exception) as exc:
            raise TokenAccessError("Invalid or expired access token") from exc
        sub=claims.get("sub")
        if not isinstance(sub,str) or not 1<=len(sub)<=200:
            raise TokenAccessError("Invalid token subject")
        scopes=claims.get("scope","")
        if not isinstance(scopes,str) or "video:read" not in scopes.split():
            raise TokenAccessError("Token missing video:read scope")
        return {"principal":sub,
                "source_ids":self.operator_source_ids & self.acl.get(sub,frozenset()),
                "token_type":"EXTERNALLY_ISSUED_SIGNED_JWT"}
