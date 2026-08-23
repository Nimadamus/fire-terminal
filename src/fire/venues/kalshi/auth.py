"""Request signing, from injected customer credentials.

Credential injection rule, enforced by construction: `RequestSigner` takes a
`Credentials` object as an argument. This module never reads a file path, an
environment variable, a config file or a bundled key. If the caller has no
credentials there is no signer, and with no signer there is no request.

The private key is parsed once into an in memory key object. The PEM text is
not retained on the signer, so it cannot be reached from a traceback or a
diagnostic dump of this object.
"""
from __future__ import annotations

import base64
import time
from typing import Optional

from fire.config.credentials import Credentials
from fire.core.errors import CredentialsInvalid


class RequestSigner:
    """Signs one request at a time. Thread safe: holds no per request state."""

    def __init__(self, credentials: Credentials) -> None:
        try:
            from cryptography.hazmat.primitives import serialization
            self._key = serialization.load_pem_private_key(
                credentials.private_key_pem.encode(), password=None)
        except Exception as exc:
            raise CredentialsInvalid(
                "The saved private key could not be read."
            ) from exc
        self._key_id = credentials.key_id
        # deliberately no reference to the PEM text kept

    @property
    def key_id(self) -> str:
        return self._key_id

    def __repr__(self) -> str:
        tail = self._key_id[-4:] if len(self._key_id) >= 4 else ""
        return f"RequestSigner(key_id='...{tail}')"

    def _sign(self, message: bytes) -> str:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        signature = self._key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()

    def headers(self, method: str, signing_path: str,
                timestamp_ms: Optional[int] = None) -> dict[str, str]:
        """Auth headers for one request.

        The signed message is timestamp + method + path, which is the scheme
        the exchange documents publicly.
        """
        ts = str(timestamp_ms if timestamp_ms is not None
                 else int(time.time() * 1000))
        message = (ts + method.upper() + signing_path).encode()
        return {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-SIGNATURE": self._sign(message),
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


def signer_from_store(store) -> RequestSigner:
    """Build a signer from whatever the customer saved. Never from a file."""
    from fire.core.errors import SetupIncomplete
    credentials = store.load()
    if credentials is None:
        raise SetupIncomplete("No exchange credentials are saved on this computer.")
    return RequestSigner(credentials)
