import logging
from collections import deque
from collections.abc import Iterator
from enum import StrEnum
from typing import NamedTuple
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from extraction.adapters import ADAPTERS
from extraction.http import USER_AGENT, Http
from extraction.models import FetchResult
from extraction.website import Website
from storage import Storage

logger = logging.getLogger(__name__)


class Outcome(StrEnum):
    STORED = "stored"
    UNCHANGED = "unchanged"
    FLAGGED = "flagged"
    SKIPPED = "skipped"
    FAILED = "failed"
    DISALLOWED = "disallowed"


class Result(NamedTuple):
    url: str
    outcome: Outcome
    detail: str = ""


def website_for(url: str, default: Website) -> Website:
    return next((adapter() for adapter in ADAPTERS if adapter.matches(url)), default)


class _Robots:
    def __init__(self, http: Http) -> None:
        self._http = http
        self._parsers: dict[str, RobotFileParser] = {}

    def allows(self, url: str) -> bool:
        target = urlsplit(url)
        origin = f"{target.scheme}://{target.netloc}"
        if origin not in self._parsers:
            parser = RobotFileParser()
            try:
                parser.parse(self._http.text(f"{origin}/robots.txt").splitlines())
            except requests.RequestException:
                parser.parse([])
            self._parsers[origin] = parser
        return self._parsers[origin].can_fetch(USER_AGENT, url)


def _scope_prefix(path: str) -> str:
    directory, _, name = path.rpartition("/")
    return f"{path}/" if name and "." not in name else f"{directory}/"


def _in_scope(url: str, scope: str) -> bool:
    target, origin = urlsplit(url), urlsplit(scope)
    return target.netloc == origin.netloc and f"{target.path}/".startswith(_scope_prefix(origin.path))


def _failure(error: requests.RequestException) -> str:
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return f"HTTP {error.response.status_code}"
    return type(error).__name__


def _store(storage: Storage, website: Website, url: str, fetch: FetchResult) -> Result:
    latest = storage.latest(fetch.url)
    if latest and latest[0] == fetch.raw_sha256:
        return Result(url, Outcome.UNCHANGED)
    page = website.extract(fetch)
    if latest and latest[1] == page.text_sha256:
        return Result(url, Outcome.UNCHANGED)
    sections = website.sections(page)
    storage.save(fetch, page, sections)
    if page.warnings:
        return Result(url, Outcome.FLAGGED, "; ".join(page.warnings))
    return Result(url, Outcome.STORED, f"{len(sections)} section{'' if len(sections) == 1 else 's'}")


def crawl(http: Http, storage: Storage, start: str, website: Website, max_pages: int) -> Iterator[Result]:
    robots = _Robots(http)
    queue = deque([start])
    seen = {website_for(start, website).fetch_url(start)}
    scope = start
    fetched = 0
    while queue and fetched < max_pages:
        url = queue.popleft()
        site = website_for(url, website)
        if not robots.allows(site.fetch_url(url)):
            yield Result(url, Outcome.DISALLOWED)
            continue
        fetched += 1
        try:
            fetch = http.fetch(site, url)
        except requests.RequestException as error:
            yield Result(url, Outcome.FAILED, _failure(error))
            continue
        seen.add(fetch.final_url)
        if url == start:
            scope = fetch.final_url
        if not fetch.content_type.startswith(site.content_types):
            yield Result(url, Outcome.SKIPPED, fetch.content_type)
            continue
        try:
            result = _store(storage, site, url, fetch)
            links = site.links(fetch)
        except Exception as error:
            logger.info("Failed to process %s", url, exc_info=True)
            yield Result(url, Outcome.FAILED, f"{type(error).__name__}: {error}")
            continue
        yield result
        for link in links:
            key = website_for(link, website).fetch_url(link)
            if key not in seen and _in_scope(link, scope):
                seen.add(key)
                queue.append(link)
