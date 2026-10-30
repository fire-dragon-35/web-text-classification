import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from extraction.models import FetchResult, sha256
from extraction.website import Website

USER_AGENT = "web-text-classification/0.1 (contact: fire-dragon-35@proton.me)"
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1
RETRY_STATUSES = (429, 500, 502, 503, 504)

logger = logging.getLogger(__name__)


class Http:
    def __init__(self, requests_per_second: float = 1) -> None:
        self._interval = 1 / requests_per_second
        self._next_slot: dict[str, float] = {}
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        retry = Retry(
            total=MAX_ATTEMPTS - 1,
            backoff_factor=BACKOFF_SECONDS,
            status_forcelist=RETRY_STATUSES,
            raise_on_status=False,
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session.mount("http://", HTTPAdapter(max_retries=retry))

    def text(self, url: str) -> str:
        with self._open(url) as response:
            return response.text

    def fetch(self, website: Website, url: str) -> FetchResult:
        fetch_url = website.fetch_url(url)
        fetched_at = datetime.now(UTC)
        with self._open(fetch_url) as response:
            content_type = response.headers.get("content-type", "")
            body = response.content if content_type.startswith(website.content_types) else b""
        return FetchResult(
            url=fetch_url,
            final_url=response.url,
            status=response.status_code,
            content_type=content_type,
            fetched_at=fetched_at,
            raw_sha256=sha256(body),
            body=body,
        )

    def _open(self, url: str) -> requests.Response:
        target = urlsplit(url)
        self._wait_turn(target.netloc)
        started = time.monotonic()
        response = self._session.get(url, timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS), stream=True)
        logger.info(
            "GET %s%s -> %s %s in %.0f ms",
            target.netloc,
            target.path,
            response.status_code,
            response.headers.get("content-type", ""),
            (time.monotonic() - started) * 1000,
        )
        if not response.ok:
            response.close()
        response.raise_for_status()
        return response

    def _wait_turn(self, host: str) -> None:
        now = time.monotonic()
        slot = max(now, self._next_slot.get(host, now))
        self._next_slot[host] = slot + self._interval
        time.sleep(slot - now)
