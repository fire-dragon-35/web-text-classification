from collections.abc import Iterable
from urllib.parse import urlsplit

from extraction.adapters import website_for
from extraction.sources import Source
from extraction.website import Website


def scope_prefix(path: str) -> str:
    directory, _, name = path.rpartition("/")
    return f"{path}/" if name and "." not in name else f"{directory}/"


def in_scope(url: str, scope: str, allow: list[str]) -> bool:
    target, origin = urlsplit(url), urlsplit(scope)
    if target.netloc != origin.netloc:
        return False
    if allow:
        return target.path.startswith(tuple(allow))
    return f"{target.path}/".startswith(scope_prefix(origin.path))


def start_scopes(source: Source) -> list[str]:
    return [source.sitemap] if source.sitemap else list(source.urls)


def includes(source: Source, url: str, scopes: Iterable[str]) -> bool:
    website = Website()
    if website_for(url, website, source.adapter) is not website:
        return url in {website_for(start, website, source.adapter).fetch_url(start) for start in source.urls}
    return any(in_scope(url, scope, source.allow) for scope in scopes)
