"""Client HTTP per F1 Fantasy, autenticato con il cookie di sessione.

Il login con password e' protetto da Imperva e non e' affidabile da script, quindi
il cookie ``F1_FANTASY_007`` si copia a mano dal browser e si salva come secret
su GitHub. Dura circa cinque giorni: la scadenza e' normale e ha un'eccezione
dedicata (``AuthExpired``) per distinguerla da un guasto dell'API.
"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Mapping

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://fantasy.formula1.com"
COOKIE_NAME = "F1_FANTASY_007"
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/",
    "X-Requested-With": "XMLHttpRequest",
}
RETRY_STATUS = {429, 500, 502, 503, 504}


class FantasyError(RuntimeError):
    """Qualunque errore nel dialogo con l'API."""


class AuthExpired(FantasyError):
    """Cookie mancante, rifiutato o scaduto."""


class NotShared(FantasyError):
    """L'API ha rifiutato questa risorsa (dati di un altro membro non leggibili)."""


class FantasyClient:
    def __init__(
        self,
        token: str,
        guid: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 4,
        sleep=time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token or not guid:
            raise AuthExpired(
                "Credenziali mancanti: imposta i secret F1_FANTASY_TOKEN e F1_USER_GUID."
            )
        self.guid = guid
        self.max_retries = max_retries
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=base_url,
            headers=DEFAULT_HEADERS,
            cookies={COOKIE_NAME: token},
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FantasyClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_raw(self, path: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            if attempt:
                self._sleep(min(2**attempt, 16) * (0.5 + random.random() / 2))
            try:
                response = self._client.get(path)
            except httpx.HTTPError as exc:
                last_error = exc
                continue

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if "login" in location.lower() or "account" in location.lower():
                    raise AuthExpired(f"Rimandato al login ({location}): aggiorna il cookie.")
                last_error = FantasyError(f"Redirect inatteso verso {location}")
                continue
            if response.status_code in (401, 403):
                raise AuthExpired(f"HTTP {response.status_code} su {path}: cookie scaduto o rifiutato.")
            if response.status_code in RETRY_STATUS:
                last_error = FantasyError(f"HTTP {response.status_code} su {path}")
                continue
            if response.status_code >= 400:
                raise FantasyError(f"HTTP {response.status_code} su {path}: {response.text[:200]}")
            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                body = response.text.lstrip()[:200]
                if body.lower().startswith(("<!doctype", "<html")):
                    raise AuthExpired(f"{path} ha restituito HTML invece di JSON: cookie scaduto.") from exc
                raise FantasyError(f"{path}: JSON non valido: {body}") from exc
        raise FantasyError(f"{path}: fallito dopo {self.max_retries} tentativi ({last_error})")

    def get(self, path: str) -> Any:
        return unwrap(self.get_raw(path), path=path)


def unwrap(payload: Any, *, path: str = "") -> Any:
    """Toglie la busta ``{Data: {Value: ...}, Meta: ...}``; un HTTP 200 non basta."""
    if not isinstance(payload, Mapping) or "Data" not in payload:
        return payload
    data = payload.get("Data")
    if data is None:
        meta = payload.get("Meta") or {}
        message = str(meta.get("Message") or meta.get("message") or meta) if isinstance(meta, Mapping) else str(meta)
        lowered = message.lower()
        if any(w in lowered for w in ("login", "session", "token", "unauthor", "expire")):
            raise AuthExpired(f"{path}: {message}")
        if any(w in lowered for w in ("permission", "not allowed", "access")):
            raise NotShared(f"{path}: {message}")
        raise FantasyError(f"{path}: {message or 'nessun dato'}")
    if isinstance(data, Mapping) and "Value" in data:
        return data["Value"]
    return data
