import logging
from collections import deque
from collections.abc import Iterator
from enum import StrEnum
from typing import NamedTuple
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import lxml.etree
import requests

from db import Storage
from extraction.adapters import ADAPTERS, ADAPTERS_BY_NAME
from extraction.http import USER_AGENT, Http
from extraction.models import FetchResult
from extraction.pdf import Pdf
from extraction.sources import Follow, Source
from extraction.website import Website

logger = logging.getLogger(__name__)

ROBOTS_DENIED_STATUSES = (401, 403)

PDF = Pdf()


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


PDF_SUFFIX = ".pdf"


def website_for(url: str, default: Website, adapter: str | None = None) -> Website:
    if adapter:
        return ADAPTERS_BY_NAME[adapter]()
    return next((candidate() for candidate in ADAPTERS if candidate.matches(url)), default)


def _followed(link: str, follow: Follow | None) -> bool:
    return follow == Follow.ALL or (follow == Follow.PDF and urlsplit(link).path.lower().endswith(PDF_SUFFIX))


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
            except requests.RequestException as error:
                parser.parse([])
                parser.disallow_all = error.response is not None and error.response.status_code in ROBOTS_DENIED_STATUSES
            self._parsers[origin] = parser
        return self._parsers[origin].can_fetch(USER_AGENT, url)


def _scope_prefix(path: str) -> str:
    directory, _, name = path.rpartition("/")
    return f"{path}/" if name and "." not in name else f"{directory}/"


def _in_scope(url: str, scope: str, allow: list[str]) -> bool:
    target, origin = urlsplit(url), urlsplit(scope)
    if target.netloc != origin.netloc:
        return False
    if allow:
        return target.path.startswith(tuple(allow))
    return f"{target.path}/".startswith(_scope_prefix(origin.path))


def _sitemap_urls(http: Http, robots: _Robots, url: str, seen: set[str]) -> list[str]:
    if url in seen or not robots.allows(url):
        return []
    seen.add(url)
    root = lxml.etree.fromstring(http.text(url).encode())
    locs = [loc.text.strip() for loc in root.iter("{*}loc") if loc.text]
    if lxml.etree.QName(root).localname == "sitemapindex":
        return [page for loc in locs for page in _sitemap_urls(http, robots, loc, seen)]
    return locs


def _sitemap_pages(http: Http, robots: _Robots, sitemap: str, allow: list[str], max_pages: int) -> list[str]:
    pages = set(_sitemap_urls(http, robots, sitemap, set()))
    allowed = [url for url in pages if not allow or urlsplit(url).path.startswith(tuple(allow))]
    return sorted(allowed)[:max_pages]


def _failure(error: requests.RequestException) -> str:
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return f"HTTP {error.response.status_code}"
    return type(error).__name__


def _store(storage: Storage, source_id: str, website: Website, url: str, fetch: FetchResult) -> Result:
    latest = storage.latest(fetch.url)
    if latest and latest[0] == fetch.raw_sha256:
        return Result(url, Outcome.UNCHANGED)
    page = website.extract(fetch)
    sections = website.sections(page)
    storage.save(source_id, fetch, page, sections)
    if latest and latest[1] == page.text_sha256:
        return Result(url, Outcome.UNCHANGED)
    if page.warnings:
        return Result(url, Outcome.FLAGGED, "; ".join(page.warnings))
    return Result(url, Outcome.STORED, f"{len(sections)} section{'' if len(sections) == 1 else 's'}")


def crawl(http: Http, storage: Storage, source: Source) -> Iterator[Result]:
    website = Website(source.selector, tuple(source.exclude))
    robots = _Robots(http)
    if source.sitemap:
        try:
            queue = deque(_sitemap_pages(http, robots, source.sitemap, source.allow, source.max_pages))
        except requests.RequestException as error:
            yield Result(source.sitemap, Outcome.FAILED, _failure(error))
            return
        except lxml.etree.XMLSyntaxError as error:
            yield Result(source.sitemap, Outcome.FAILED, f"{type(error).__name__}: {error}")
            return
    else:
        queue = deque(source.urls)
    seen = {website_for(url, website, source.adapter).fetch_url(url) for url in queue}
    scopes = {source.sitemap: source.sitemap} if source.sitemap else {url: url for url in queue}
    fetched = 0
    while queue and fetched < source.max_pages:
        url = queue.popleft()
        site = website_for(url, website, source.adapter)
        if not robots.allows(site.fetch_url(url)):
            yield Result(url, Outcome.DISALLOWED)
            continue
        fetched += 1
        try:
            fetch = http.fetch(site.fetch_url(url), site.content_types + Pdf.content_types)
        except requests.RequestException as error:
            yield Result(url, Outcome.FAILED, _failure(error))
            continue
        seen.add(fetch.final_url)
        if url in scopes:
            scopes[url] = fetch.final_url
        handler = PDF if fetch.content_type.startswith(Pdf.content_types) else site
        if not fetch.content_type.startswith(handler.content_types):
            yield Result(url, Outcome.SKIPPED, fetch.content_type)
            continue
        try:
            result = _store(storage, source.id, handler, url, fetch)
            links = handler.links(fetch) if source.follow != Follow.NONE else []
        except Exception as error:
            logger.info("Failed to process %s", url, exc_info=True)
            yield Result(url, Outcome.FAILED, f"{type(error).__name__}: {error}")
            continue
        yield result
        for link in links:
            if not _followed(link, source.follow):
                continue
            key = website_for(link, website, source.adapter).fetch_url(link)
            if key not in seen and any(_in_scope(link, scope, source.allow) for scope in scopes.values()):
                seen.add(key)
                queue.append(link)
