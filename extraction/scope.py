from urllib.parse import urlsplit

from extraction.registry import Extractors
from extraction.sources import Source


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


class Scope:
    def __init__(self, source: Source, extractors: Extractors) -> None:
        self._source = source
        self._extractors = extractors
        self._starts = [source.sitemap] if source.sitemap else list(source.urls)
        self._scopes = set(self._starts)
        self._adapter_urls = {extractors.fetch_url(url) for url in source.urls}

    def redirected(self, url: str, final_url: str) -> None:
        if url in self._starts:
            self._scopes.add(final_url)

    def includes(self, url: str) -> bool:
        if self._extractors.adapter_for(url):
            return self._extractors.fetch_url(url) in self._adapter_urls
        return any(_in_scope(url, scope, self._source.allow) for scope in self._scopes)
