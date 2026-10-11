"""Load the UN Security Council Consolidated List -- docs/design/asco-orchestrator.md §3.1.

The loader parses bytes it is handed and never fetches: what the gate screens against is
exactly the file operations downloaded, dated by the list's own `dateGenerated`.
"""

from datetime import datetime

from lxml import etree
from ubunturemit_asco.guardrails.entry import SanctionsListSource, StaticSanctionsScreener

UN_LIST_NAME = "UN Security Council Consolidated List"
_NAME_PARTS = ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")


class SanctionsListFormatError(ValueError):
    """The document is not a UN consolidated list this loader can read."""


def _text(element: etree._Element, tag: str) -> str:
    return " ".join((element.findtext(tag) or "").split())


def _names(root: etree._Element) -> list[str]:
    names: list[str] = []
    for person in root.iterfind("INDIVIDUALS/INDIVIDUAL"):
        names.append(" ".join(p for p in (_text(person, t) for t in _NAME_PARTS) if p))
        names.append(_text(person, "NAME_ORIGINAL_SCRIPT"))
        names.extend(_text(alias, "ALIAS_NAME") for alias in person.iterfind("INDIVIDUAL_ALIAS"))
    for entity in root.iterfind("ENTITIES/ENTITY"):
        names.append(_text(entity, "FIRST_NAME"))
        names.append(_text(entity, "NAME_ORIGINAL_SCRIPT"))
        names.extend(_text(alias, "ALIAS_NAME") for alias in entity.iterfind("ENTITY_ALIAS"))
    return [n for n in names if n]


def load_un_consolidated_list(document: bytes) -> StaticSanctionsScreener:
    """Build a screener from the consolidated list XML.

    Raises SanctionsListFormatError for anything that is not the list, or has no
    `dateGenerated`; EmptySanctionsListError (from the screener) if it names no one.
    """
    # Hardened: the file comes from outside the institution, so no entity expansion
    # and no network access while parsing.
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(document, parser)
    except etree.XMLSyntaxError as err:
        raise SanctionsListFormatError(f"Not well-formed XML: {err}") from err
    if root.tag != "CONSOLIDATED_LIST":
        raise SanctionsListFormatError(f"Root element is <{root.tag}>, not <CONSOLIDATED_LIST>.")

    generated = root.get("dateGenerated")
    if not generated:
        raise SanctionsListFormatError("The list has no dateGenerated; its date is unknown.")
    try:
        published = datetime.fromisoformat(generated).date()
    except ValueError as err:
        raise SanctionsListFormatError(f"Unreadable dateGenerated '{generated}'.") from err

    return StaticSanctionsScreener(
        source=SanctionsListSource(name=UN_LIST_NAME, published=published),
        sanctioned_names=_names(root),
    )
