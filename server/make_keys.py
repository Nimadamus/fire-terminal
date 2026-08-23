"""Generate the signing key pair for the licence service.

Run this ONCE. Put the private key in the service environment as
FIRE_SIGNING_KEY and the public key into src/fire/version.py as
LICENCE_PUBLIC_KEY.

The private key never goes in the repository, never goes in a build, and never
leaves the server. If it leaks, anyone can mint themselves a subscription, so
treat it exactly like a payment credential.

    python server/make_keys.py
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode("ascii")
    raw_public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_b64 = base64.urlsafe_b64encode(raw_public).decode("ascii").rstrip("=")

    print("=" * 72)
    print("PRIVATE KEY. Service environment only, as FIRE_SIGNING_KEY.")
    print("Newlines may be written as \n if your host needs a single line.")
    print("=" * 72)
    print(pem)
    print("=" * 72)
    print("PUBLIC KEY. Paste into src/fire/version.py as LICENCE_PUBLIC_KEY.")
    print("=" * 72)
    print(public_b64)


if __name__ == "__main__":
    main()
