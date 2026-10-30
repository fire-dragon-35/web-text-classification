import io

import pypdf

from extraction.models import FetchResult, Page, Section
from extraction.website import MIN_CHARS, Website

PAGE_BREAK = "\f"
EXTRACTOR = f"pypdf {pypdf.__version__}"


class Pdf(Website):
    content_types = ("application/pdf",)

    def links(self, fetch: FetchResult) -> list[str]:
        return []

    def extract(self, fetch: FetchResult) -> Page:
        reader = pypdf.PdfReader(io.BytesIO(fetch.body))
        text = PAGE_BREAK.join(page.extract_text().strip() for page in reader.pages)
        metadata = reader.metadata
        modified = metadata and (metadata.modification_date or metadata.creation_date)
        warnings = [f"too little text: {len(text)} chars"] if len(text) < MIN_CHARS else []
        return Page(
            title=(metadata and metadata.title) or "",
            page_date=modified.date() if modified else None,
            text=text,
            extractor=EXTRACTOR,
            warnings=warnings,
        )

    def sections(self, page: Page) -> list[Section]:
        texts = [(number, text) for number, text in enumerate(page.text.split(PAGE_BREAK), start=1) if text]
        return [
            Section(ordinal=ordinal, heading=f"page {number}", level=1, text=text)
            for ordinal, (number, text) in enumerate(texts)
        ]
