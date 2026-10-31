import logging
from collections import deque
from collections.abc import Iterator
from enum import StrEnum
from typing import NamedTuple
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import lxml.etree
import requests

from db import PageStore
from extraction.extractor import Extractor
from extraction.http import USER_AGENT, Http
from extraction.models import FetchResult
from extraction.registry import Extractors
from extraction.scope import Scope
from extraction.sources import Follow, Source

logger = logging.getLogger(__name__)

ROBOTS_DENIED_STATUSES = (401, 403)
PDF_SUFFIX = ".pdf"


class CrawlOutcome(StrEnum):
    STORED = "stored"
    UNCHANGED = "unchanged"
    FLAGGED = "flagged"
    SKIPPED = "skipped"
    FAILED = "failed"
    DISALLOWED = "disallowed"


class CrawlResult(NamedTuple):
    url: str
    outcome: CrawlOutcome
    detail: str = ""


class Robots:
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
            except requests.RequestException as error:
                parser.parse([])
                parser.disallow_all = error.response is not None and error.response.status_code in ROBOTS_DENIED_STATUSES
            self._parsers[origin] = parser
        return self._parsers[origin].can_fetch(USER_AGENT, url)


def _failure(error: requests.RequestException) -> str:
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return f"HTTP {error.response.status_code}"
    return type(error).__name__


class Crawler:
    def __init__(self, http: Http, robots: Robots, pages: PageStore, source: Source) -> None:
        self._http = http
        self._robots = robots
        self._pages = pages
        self._source = source
        self._extractors = Extractors(source)
        self._scope = Scope(source, self._extractors)
        self._queue: deque[str] = deque()
        self._seen: set[str] = set()

    def crawl(self) -> Iterator[CrawlResult]:
        try:
            self._queue.extend(self._sitemap_pages() if self._source.sitemap else self._source.urls)
        except requests.RequestException as error:
            yield CrawlResult(self._source.sitemap or "", CrawlOutcome.FAILED, _failure(error))
            return
        except lxml.etree.XMLSyntaxError as error:
            yield CrawlResult(self._source.sitemap or "", CrawlOutcome.FAILED, f"{type(error).__name__}: {error}")
            return
        self._seen.update(self._extractors.fetch_url(url) for url in self._queue)
        fetched = 0
        while self._queue and fetched < self._source.max_pages:
            url = self._queue.popleft()
            fetch_url = self._extractors.fetch_url(url)
            if not self._robots.allows(fetch_url):
                yield CrawlResult(url, CrawlOutcome.DISALLOWED)
                continue
            fetched += 1
            yield self._visit(url, fetch_url)

    def _sitemap_pages(self) -> list[str]:
        pages = set(self._sitemap_urls(self._source.sitemap or "", set()))
        allow = tuple(self._source.allow)
        allowed = [url for url in pages if not allow or urlsplit(url).path.startswith(allow)]
        return sorted(allowed)[: self._source.max_pages]

    def _sitemap_urls(self, url: str, seen: set[str]) -> list[str]:
        if url in seen or not self._robots.allows(url):
            return []
        seen.add(url)
        root = lxml.etree.fromstring(self._http.text(url).encode())
        locs = [loc.text.strip() for loc in root.iter("{*}loc") if loc.text]
        if lxml.etree.QName(root).localname == "sitemapindex":
            return [page for loc in locs for page in self._sitemap_urls(loc, seen)]
        return locs

    def _visit(self, url: str, fetch_url: str) -> CrawlResult:
        try:
            fetch = self._http.fetch(fetch_url, self._extractors.content_types(url))
        except requests.RequestException as error:
            return CrawlResult(url, CrawlOutcome.FAILED, _failure(error))
        self._seen.add(fetch.final_url)
        self._scope.redirected(url, fetch.final_url)
        extractor = self._extractors.select(url, fetch.content_type)
        if extractor is None:
            return CrawlResult(url, CrawlOutcome.SKIPPED, fetch.content_type)
        try:
            result = self._store(extractor, url, fetch)
            if self._source.follow != Follow.NONE:
                self._enqueue(extractor.links(fetch))
        except Exception as error:
            logger.info("Failed to process %s", url, exc_info=True)
            return CrawlResult(url, CrawlOutcome.FAILED, f"{type(error).__name__}: {error}")
        return result

    def _store(self, extractor: Extractor, url: str, fetch: FetchResult) -> CrawlResult:
        latest = self._pages.latest(fetch.url)
        if latest and latest[0] == fetch.raw_sha256:
            return CrawlResult(url, CrawlOutcome.UNCHANGED)
        page = extractor.extract(fetch)
        if latest and latest[1] == page.text_sha256:
            return CrawlResult(url, CrawlOutcome.UNCHANGED)
        sections = extractor.sections(page)
        self._pages.save(self._source.id, fetch, page, sections)
        if page.warnings:
            return CrawlResult(url, CrawlOutcome.FLAGGED, "; ".join(page.warnings))
        return CrawlResult(url, CrawlOutcome.STORED, f"{len(sections)} section{'' if len(sections) == 1 else 's'}")

    def _enqueue(self, links: list[str]) -> None:
        for link in links:
            if not self._followed(link):
                continue
            key = self._extractors.fetch_url(link)
            if key not in self._seen and self._scope.includes(link):
                self._seen.add(key)
                self._queue.append(link)

    def _followed(self, link: str) -> bool:
        follow = self._source.follow
        return follow == Follow.ALL or (follow == Follow.PDF and urlsplit(link).path.lower().endswith(PDF_SUFFIX))
