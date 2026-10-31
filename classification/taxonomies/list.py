import logging
from typing import Any

from classification.models import Term
from classification.taxonomies.generic import GenericTaxonomy

logger = logging.getLogger(__name__)

TOP_LEVEL = "00"


def _parent(code: str) -> str:
    prefix, *segments = code.split("-")
    specific = [index for index, segment in enumerate(segments) if segment != TOP_LEVEL]
    if not specific:
        return ""
    segments[specific[-1]] = TOP_LEVEL
    return "-".join((prefix, *segments))


class ListTaxonomy(GenericTaxonomy):
    name = "list"

    @classmethod
    def matches(cls, data: dict[str, Any]) -> bool:
        return data.get("taxonomy") == "LIST"

    @classmethod
    def terms(cls, data: dict[str, Any]) -> list[Term]:
        found: dict[str, Term] = {}
        for entry in data.get("terms") or []:
            term = Term.model_validate(entry | {"parent": _parent(str(entry.get("code", "")))})
            if term.code in found:
                logger.warning("duplicate code %s: keeping %r, dropping %r", term.code, found[term.code].name, term.name)
                continue
            found[term.code] = term
        return list(found.values())
