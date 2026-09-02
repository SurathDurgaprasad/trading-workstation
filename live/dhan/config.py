"""Phase 15 §4 — credentials come from environment variables ONLY. Nothing
in this file, or anywhere in live/dhan/, ever hardcodes a client ID, access
token, or secret. .gitignore already excludes .env/.env.*/*.key/*.pem
(added in Phase 13, before any secret existed) -- this module is what
actually reads them at runtime, and only at the point a real Dhan call is
about to be made, never at import time (so importing live.dhan never fails
just because no credentials are configured -- exactly what lets every unit
test in this package run without a real account).
"""

import os
from dataclasses import dataclass

DHAN_CLIENT_ID_ENV = "DHAN_CLIENT_ID"
DHAN_ACCESS_TOKEN_ENV = "DHAN_ACCESS_TOKEN"

DHAN_FEED_WS_URL = "wss://api-feed.dhan.co"
DHAN_REST_BASE_URL = "https://api.dhan.co/v2"


class DhanCredentialsMissingError(RuntimeError):
    """Raised only at the moment a real Dhan call is attempted -- never at
    import time. The message never echoes back any value the caller
    supplied, so a misconfigured env var can't leak a partial secret into
    a log line."""


@dataclass(frozen=True)
class DhanCredentials:
    client_id: str
    access_token: str

    def __repr__(self) -> str:
        # Never let a stray print()/log accidentally dump the token --
        # both fields are masked even in repr/debugger output.
        return "DhanCredentials(client_id='***', access_token='***')"


def load_dhan_credentials() -> DhanCredentials:
    """Reads DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN from the process
    environment. Raises DhanCredentialsMissingError (not a bare KeyError)
    if either is absent -- a clear, specific failure rather than a stack
    trace pointing at os.environ."""
    client_id = os.environ.get(DHAN_CLIENT_ID_ENV)
    access_token = os.environ.get(DHAN_ACCESS_TOKEN_ENV)
    missing = [name for name, value in ((DHAN_CLIENT_ID_ENV, client_id), (DHAN_ACCESS_TOKEN_ENV, access_token)) if not value]
    if missing:
        raise DhanCredentialsMissingError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in your own shell/secret store -- never in source or in .env committed to git. "
            "See .env.example for the variable names (no values)."
        )
    return DhanCredentials(client_id=client_id, access_token=access_token)
