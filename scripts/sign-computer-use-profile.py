#!/usr/bin/env python3
"""Sign a profile without ever writing its Ed25519 private key into SAG."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.strip() + "=" * (-len(value.strip()) % 4))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path)
    parser.add_argument("--private-key-file", required=True, type=Path)
    arguments = parser.parse_args()
    profile = json.loads(arguments.profile.read_text())
    profile.pop("signature", None)
    canonical = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    key = Ed25519PrivateKey.from_private_bytes(decode(arguments.private_key_file.read_text()))
    signature = base64.urlsafe_b64encode(key.sign(canonical)).decode().rstrip("=")
    print(json.dumps({**profile, "signature": signature}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
