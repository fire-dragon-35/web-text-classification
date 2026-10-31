from typing import Any

from pydantic import TypeAdapter

from classification.models import Term

TERMS = TypeAdapter(list[Term])


class GenericTaxonomy:
    name = "generic"

    @classmethod
    def matches(cls, data: dict[str, Any]) -> bool:
        return False

    @classmethod
    def terms(cls, data: dict[str, Any]) -> list[Term]:
        return TERMS.validate_python(data.get("terms"))
