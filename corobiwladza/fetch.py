"""Uprzejme pobieranie: maks. 1 zapytanie na sekundę, surowe odpowiedzi w cache.

Każda odpowiedź trafia do `cache/raw/<sha256(url)>.bin` razem z plikiem
`.meta.json` (adres, data pobrania, typ treści, SHA-256 treści). Drugie
uruchomienie korzysta z cache i nie wysyła zapytań.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import __version__

USER_AGENT = (
    f"CoRobiWladza/{__version__} (+https://corobiwladza.pl; "
    "prototyp niekomercyjny; maks. 1 zapytanie/s)"
)


class FetchError(RuntimeError):
    """Nie udało się pobrać zasobu (lub brak go w cache w trybie offline)."""


@dataclasses.dataclass
class Response:
    url: str
    body: bytes
    sha256: str
    fetched_at: str  # ISO 8601, UTC
    content_type: str
    from_cache: bool
    path: Path

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclasses.dataclass
class Stats:
    network_requests: int = 0
    cache_hits: int = 0
    bytes_downloaded: int = 0
    seconds_waiting: float = 0.0


def build_url(url: str, params: dict | None = None) -> str:
    if not params:
        return url
    return url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)


class Fetcher:
    def __init__(
        self,
        cache_dir: Path,
        min_interval: float = 1.0,
        offline: bool = False,
        timeout: float = 120.0,
    ):
        self.raw_dir = Path(cache_dir) / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.offline = offline
        self.timeout = timeout
        self.stats = Stats()
        self._last_request = 0.0

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.raw_dir / f"{key}.bin", self.raw_dir / f"{key}.meta.json"

    def get(self, url: str, params: dict | None = None) -> Response:
        full = build_url(url, params)
        body_path, meta_path = self._paths(full)
        if body_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text("utf-8"))
            body = body_path.read_bytes()
            if hashlib.sha256(body).hexdigest() != meta["sha256"]:
                raise FetchError(f"Uszkodzony plik w cache dla {full}")
            self.stats.cache_hits += 1
            return Response(full, body, meta["sha256"], meta["fetched_at"],
                             meta["content_type"], True, body_path)
        if self.offline:
            raise FetchError(f"Tryb offline: brak w cache {full}")

        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
            self.stats.seconds_waiting += wait
        req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "")
        except Exception as exc:  # noqa: BLE001 – każdy błąd sieci przerywa pracę
            raise FetchError(f"Błąd pobierania {full}: {exc}") from exc
        finally:
            self._last_request = time.monotonic()
            self.stats.network_requests += 1
        if status != 200:
            raise FetchError(f"HTTP {status} dla {full}")

        sha = hashlib.sha256(body).hexdigest()
        fetched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        body_path.write_bytes(body)
        meta_path.write_text(json.dumps({
            "url": full, "fetched_at": fetched_at, "content_type": ctype,
            "sha256": sha, "bytes": len(body), "user_agent": USER_AGENT,
        }, ensure_ascii=False, indent=1), "utf-8")
        self.stats.bytes_downloaded += len(body)
        return Response(full, body, sha, fetched_at, ctype, False, body_path)
