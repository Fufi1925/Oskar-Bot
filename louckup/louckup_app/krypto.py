"""Bot-Token verschluesselt ablegen.

Klartext in der Datenbank waere der denkbar schlechteste Ort dafuer:
jeder, der an die Datei kommt, haette damit jeden eingetragenen Bot
vollstaendig in der Hand. Verschluesselt wird mit demselben Schluessel,
der auch die Sessions signiert (LOUCKUP_SECRET_KEY) — der steht in der
Umgebung und nicht in der Datenbank.

Das ist keine Wunderwaffe: wer den Container und die Umgebung hat, hat
beides. Es verhindert nur den haeufigsten Fall — eine kopierte
Datenbankdatei.
"""

from __future__ import annotations

import base64
import hashlib


class KryptoFehler(RuntimeError):
    """Token konnte nicht ver- oder entschluesselt werden."""


def _fernet(schluessel: str):
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - nur wenn das Paket fehlt
        raise KryptoFehler(
            "Das Paket 'cryptography' fehlt. Es steht in louckup/requirements.txt."
        ) from exc

    if not schluessel:
        raise KryptoFehler("Kein Schluessel gesetzt (LOUCKUP_SECRET_KEY).")
    # Fernet will einen 32-Byte-Key in URL-Base64.
    roh = hashlib.sha256(schluessel.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(roh))


def verschluesseln(text: str, schluessel: str) -> str:
    return _fernet(schluessel).encrypt(text.encode("utf-8")).decode("ascii")


def entschluesseln(geheim: str, schluessel: str) -> str:
    return _fernet(schluessel).decrypt(geheim.encode("ascii")).decode("utf-8")


def maske(token: str) -> str:
    """Nur die letzten vier Zeichen — genug zum Wiedererkennen."""
    if not token:
        return "—"
    if len(token) <= 8:
        return "••••"
    return f"{token[:6]}…{token[-4:]}"
