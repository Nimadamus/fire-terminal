"""Customer credential store. Purpose built, nothing reused from internal tooling.

Rules this file exists to enforce:
  * a customer's private key is never written to disk in plaintext
  * FIRE ships with no credentials of any kind
  * the key material lives in memory only for as long as a request needs it
  * nothing here ever reaches a log or a support bundle

Backend on Windows is DPAPI (`CryptProtectData`), which ties the ciphertext to
the logged in Windows account, needs no third party dependency and no master
password from the customer. Other platforms fall back to `keyring` if it is
installed; if neither is available FIRE refuses to save rather than writing
plaintext.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional

from fire.config.paths import credentials_file
from fire.core.errors import CredentialsUnreadable


@dataclass(frozen=True)
class Credentials:
    """What the customer pastes in Setup. `private_key_pem` never leaves memory
    except through the platform secret store."""
    key_id: str
    private_key_pem: str

    def masked(self) -> dict[str, str]:
        tail = self.key_id[-4:] if len(self.key_id) >= 4 else ""
        return {"key_id": f"...{tail}", "private_key_pem": "[redacted]"}

    def __repr__(self) -> str:            # keeps secrets out of tracebacks
        return f"Credentials(key_id='...{self.key_id[-4:]}', private_key_pem='[redacted]')"


# --------------------------------------------------------------------------
# Windows DPAPI
# --------------------------------------------------------------------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _dpapi(fn, data: bytes, entropy: bytes) -> bytes:
    out = _Blob()
    ok = fn(ctypes.byref(_blob(data)), None, ctypes.byref(_blob(entropy)),
            None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


_ENTROPY = b"FIRE.terminal.credentials.v1"


class CredentialStore:
    """Save, load and clear one set of exchange credentials."""

    def available(self) -> bool:
        if sys.platform == "win32":
            return True
        try:
            import keyring  # noqa: F401
            return True
        except Exception:
            return False

    def backend_name(self) -> str:
        if sys.platform == "win32":
            return "Windows DPAPI (per user)"
        try:
            import keyring
            return f"keyring ({keyring.get_keyring().__class__.__name__})"
        except Exception:
            return "none available"

    # -- public API --------------------------------------------------------
    def save(self, creds: Credentials) -> None:
        payload = json.dumps({"key_id": creds.key_id,
                              "private_key_pem": creds.private_key_pem}).encode()
        if sys.platform == "win32":
            enc = _dpapi(ctypes.windll.crypt32.CryptProtectData, payload, _ENTROPY)
            path = credentials_file()
            path.write_bytes(enc)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            return
        try:
            import keyring
            keyring.set_password("FIRE", "exchange", payload.decode())
        except Exception as exc:
            raise CredentialsUnreadable(
                "No secure credential store is available on this system."
            ) from exc

    def load(self) -> Optional[Credentials]:
        if sys.platform == "win32":
            path = credentials_file()
            if not path.exists():
                return None
            try:
                raw = _dpapi(ctypes.windll.crypt32.CryptUnprotectData,
                             path.read_bytes(), _ENTROPY)
            except OSError as exc:
                raise CredentialsUnreadable(
                    "Saved credentials could not be decrypted by this Windows account."
                ) from exc
            d = json.loads(raw)
            return Credentials(d["key_id"], d["private_key_pem"])
        try:
            import keyring
            raw = keyring.get_password("FIRE", "exchange")
            if not raw:
                return None
            d = json.loads(raw)
            return Credentials(d["key_id"], d["private_key_pem"])
        except CredentialsUnreadable:
            raise
        except Exception:
            return None

    def clear(self) -> None:
        if sys.platform == "win32":
            path = credentials_file()
            if path.exists():
                path.unlink()
            return
        try:
            import keyring
            keyring.delete_password("FIRE", "exchange")
        except Exception:
            pass

    def has_credentials(self) -> bool:
        try:
            return self.load() is not None
        except CredentialsUnreadable:
            return True     # they exist, we just cannot read them
