import re
from datetime import date
from urllib.parse import urldefrag, urljoin

import lxml.html
import trafilatura

from extraction.extractor import MIN_CHARS, Extractor
from extraction.models import FetchResult, Page, Section

HEADING = re.compile(r"^\\?(#{1,6}) +(.+?) *#*$", re.MULTILINE)
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
CHARSET = re.compile(r"charset=\"?([\w-]+)", re.IGNORECASE)


def _tree(fetch: FetchResult) -> lxml.html.HtmlElement:
    charset = CHARSET.search(fetch.content_type)
    parser = lxml.html.HTMLParser(encoding=charset[1]) if charset else None
    return lxml.html.fromstring(fetch.body, parser=parser)


def _markdown(html: str) -> str:
    return trafilatura.extract(html, output_format="markdown", include_tables=True, favor_recall=True) or ""


def _headings_as_paragraphs(html: str) -> str:
    tree = lxml.html.fromstring(html)
    for heading in list(tree.iter(*HEADING_TAGS)):
        paragraph = lxml.html.Element("p")
        paragraph.text = "#" * int(heading.tag[1]) + " " + " ".join(heading.text_content().split())
        paragraph.tail = heading.tail
        heading.getparent().replace(heading, paragraph)
    return lxml.html.tostring(tree, encoding="unicode")


def _split(text: str, title: str) -> list[Section]:
    found: list[Section] = []
    heading, level, start = title, 1, 0
    for match in HEADING.finditer(text):
        _append_section(found, heading, level, text[start : match.start()])
        heading, level, start = match[2], len(match[1]), match.end()
    _append_section(found, heading, level, text[start:])
    return found


def _append_section(found: list[Section], heading: str, level: int, text: str) -> None:
    if text := text.strip():
        found.append(Section(ordinal=len(found), heading=heading, level=level, text=text))


def _section_words(text: str, title: str) -> int:
    return sum(len(section.heading.split()) + len(section.text.split()) for section in _split(text, title))


def _with_most_headings(text: str, with_headings: str, title: str) -> str:
    more_headings = len(HEADING.findall(with_headings)) > len(HEADING.findall(text))
    no_text_lost = _section_words(with_headings, title) >= _section_words(text, title)
    return with_headings if more_headings and no_text_lost else text


def _absolute(href: str, base: str) -> str | None:
    try:
        return urldefrag(urljoin(base, href.strip())).url
    except ValueError:
        return None


class Html(Extractor):
    content_types = ("text/html", "application/xhtml+xml")

    def __init__(self, selector: str | None = None, exclude_selectors: tuple[str, ...] = ()) -> None:
        self._selector = selector
        self._exclude_selectors = exclude_selectors

    def links(self, fetch: FetchResult) -> list[str]:
        hrefs = (_absolute(anchor.get("href", ""), fetch.final_url) for anchor in _tree(fetch).iter("a"))
        return [href for href in hrefs if href and href.startswith(("http://", "https://"))]

    def extract(self, fetch: FetchResult) -> Page:
        warnings: list[str] = []
        tree = _tree(fetch)
        metadata = trafilatura.extract_metadata(lxml.html.tostring(tree, encoding="unicode"))
        for exclude in self._exclude_selectors:
            for element in tree.cssselect(exclude):
                element.drop_tree()
        html = lxml.html.tostring(tree, encoding="unicode")
        if self._selector:
            selected = tree.cssselect(self._selector)
            if selected:
                html = "<html><body><article>{}</article></body></html>".format(
                    "".join(lxml.html.tostring(element, encoding="unicode") for element in selected)
                )
            else:
                warnings.append(f"selector matched nothing: {self._selector}")
        title = (metadata and metadata.title) or ""
        text = _with_most_headings(_markdown(html), _markdown(_headings_as_paragraphs(html)), title)
        if len(text) < MIN_CHARS:
            warnings.append(f"too little text: {len(text)} chars")
        extractor = f"trafilatura {trafilatura.__version__}"
        if self._selector:
            extractor = f"selector:{self._selector} + {extractor}"
        return Page(
            title=title,
            page_date=date.fromisoformat(metadata.date) if metadata and metadata.date else None,
            text=text,
            extractor=extractor,
            warnings=warnings,
        )

    def sections(self, page: Page) -> list[Section]:
        return _split(page.text, page.title)
