import json
import re

from extraction.extractor import Adapter
from extraction.models import FetchResult, Page, Section

DOKUMENT_URL = "https://data.riksdagen.se/dokument/sfs-{year}-{number}.json"
EXTRACTOR = "riksdagen-sfs"

SFS_URL = re.compile(r"https?://(?:www\.|data\.)?riksdagen\.se/.*[/_]sfs-(\d{4})-(\d+)")
AMENDED_THROUGH = re.compile(r"t\.o\.m\. SFS (\d{4}:\d+)")
BLOCK_BREAK = re.compile(r"\n\s*\n")
SECTION_START = re.compile(r"(\d+(?: [a-z])? §)\s")
CHAPTER_START = re.compile(r"(?:/[^/]*/ )?(\d+(?: [a-z])?) [Kk]ap\. [A-ZÅÄÖ]")
REPEALED = re.compile(r"\d+(?: [a-z])? §\s+[Hh]ar upphävts")
TRANSITIONAL_PROVISIONS = "Övergångsbestämmelser"
SENTENCE_ENDINGS = (".", ":", ";", ",")


def _clean(text: str) -> str:
    blocks = (" ".join(block.split()) for block in BLOCK_BREAK.split(text))
    return "\n\n".join(block for block in blocks if block)


def _ends_with_heading(blocks: list[str]) -> bool:
    return len(blocks) > 1 and not blocks[-1].endswith(SENTENCE_ENDINGS)


class RiksdagenSFS(Adapter):
    name = "riksdagen"
    content_types = ("application/json",)

    @classmethod
    def matches(cls, url: str) -> bool:
        return SFS_URL.match(url) is not None

    def fetch_url(self, url: str) -> str:
        number = SFS_URL.match(url)
        if not number:
            raise ValueError(f"Not a Riksdagen SFS URL: {url!r}")
        return DOKUMENT_URL.format(year=number[1], number=number[2])

    def extract(self, fetch: FetchResult) -> Page:
        dokument = json.loads(fetch.body)["dokumentstatus"]["dokument"]
        amended = AMENDED_THROUGH.search(dokument.get("subtitel") or "")
        return Page(
            title=dokument["titel"],
            text=_clean(dokument["text"]),
            extractor=EXTRACTOR,
            metadata={"consolidated_through": amended[1]} if amended else {},
        )

    def sections(self, page: Page) -> list[Section]:
        labelled: list[tuple[str, str, list[str]]] = []
        chapter = ""
        heading = page.title
        current: list[str] | None = None
        for block in BLOCK_BREAK.split(page.text):
            if block == TRANSITIONAL_PROVISIONS:
                break
            if chapter_start := CHAPTER_START.match(block):
                chapter = f"{chapter_start[1]} kap. "
                heading = block[chapter_start.start(1) :]
                current = None
            elif section_start := SECTION_START.match(block):
                if current and _ends_with_heading(current):
                    heading = current.pop()
                current = [block]
                labelled.append((chapter + section_start[1], heading, current))
            elif current is None:
                heading = block
            else:
                current.append(block)
        kept = [(ref, heading, blocks) for ref, heading, blocks in labelled if not REPEALED.match(blocks[0])]
        return [
            Section(
                ordinal=ordinal,
                heading=heading,
                level=2 if chapter else 1,
                ref=ref,
                text="\n\n".join(blocks[:-1] if _ends_with_heading(blocks) else blocks),
            )
            for ordinal, (ref, heading, blocks) in enumerate(kept)
        ]
