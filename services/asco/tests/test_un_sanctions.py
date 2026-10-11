"""Tests for the UN consolidated list loader (T075) -- asco-orchestrator.md §3.1.

The fixture mirrors the published file's structure (verified 2026-10-10) with fictional
names: no real listed person appears in this repository's tests.
"""

from datetime import date

import pytest
from ubunturemit_asco import EmptySanctionsListError
from ubunturemit_asco.guardrails.un_sanctions import (
    UN_LIST_NAME,
    SanctionsListFormatError,
    load_un_consolidated_list,
)

FIXTURE = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<CONSOLIDATED_LIST dateGenerated="2026-10-10T23:00:02.187Z">
  <INDIVIDUALS>
    <INDIVIDUAL>
      <DATAID>1</DATAID>
      <FIRST_NAME>FICTIONAL</FIRST_NAME>
      <SECOND_NAME>PERSON</SECOND_NAME>
      <THIRD_NAME>ONE</THIRD_NAME>
      <NAME_ORIGINAL_SCRIPT>\xd0\xa4\xd0\xb8\xd0\xba\xd1\x86\xd0\xb8\xd1\x8f</NAME_ORIGINAL_SCRIPT>
      <INDIVIDUAL_ALIAS>
        <QUALITY>Good</QUALITY><ALIAS_NAME>Good Alias</ALIAS_NAME>
      </INDIVIDUAL_ALIAS>
      <INDIVIDUAL_ALIAS><QUALITY>Low</QUALITY><ALIAS_NAME>Weak Alias</ALIAS_NAME></INDIVIDUAL_ALIAS>
      <INDIVIDUAL_ALIAS><QUALITY/><ALIAS_NAME/></INDIVIDUAL_ALIAS>
    </INDIVIDUAL>
  </INDIVIDUALS>
  <ENTITIES>
    <ENTITY>
      <DATAID>2</DATAID>
      <FIRST_NAME>FICTIONAL   TRADING CO</FIRST_NAME>
      <ENTITY_ALIAS><QUALITY>a.k.a.</QUALITY><ALIAS_NAME>FTC Holdings</ALIAS_NAME></ENTITY_ALIAS>
      <ENTITY_ALIAS>
        <QUALITY>f.k.a.</QUALITY><ALIAS_NAME>Old Fictional Name</ALIAS_NAME>
      </ENTITY_ALIAS>
    </ENTITY>
  </ENTITIES>
</CONSOLIDATED_LIST>
"""


def test_source_is_the_un_list_dated_by_its_own_generation_date() -> None:
    screener = load_un_consolidated_list(FIXTURE)
    assert screener.source.name == UN_LIST_NAME
    assert screener.source.published == date(2026, 10, 10)


@pytest.mark.parametrize(
    "name",
    [
        "Fictional Person One",  # name parts joined
        "fictional  person   one",  # case and spacing do not matter
        "Фикция",  # original script
        "Good Alias",
        "Weak Alias",  # a Low-quality alias still matches
        "Fictional Trading Co",  # entity, internal whitespace collapsed
        "FTC Holdings",
        "Old Fictional Name",  # formerly-known-as
    ],
)
def test_every_listed_name_and_alias_is_screened(name: str) -> None:
    assert load_un_consolidated_list(FIXTURE).is_sanctioned(name)


def test_an_unlisted_name_is_clear() -> None:
    assert not load_un_consolidated_list(FIXTURE).is_sanctioned("Kwame Mensah")


def test_a_list_without_a_date_is_refused() -> None:
    undated = FIXTURE.replace(b' dateGenerated="2026-10-10T23:00:02.187Z"', b"")
    with pytest.raises(SanctionsListFormatError, match="dateGenerated"):
        load_un_consolidated_list(undated)


def test_a_different_document_is_refused() -> None:
    with pytest.raises(SanctionsListFormatError, match="CONSOLIDATED_LIST"):
        load_un_consolidated_list(b"<Document/>")
    with pytest.raises(SanctionsListFormatError, match="well-formed"):
        load_un_consolidated_list(b"<CONSOLIDATED_LIST")


def test_a_list_naming_no_one_is_refused() -> None:
    empty = (
        b'<CONSOLIDATED_LIST dateGenerated="2026-10-10T00:00:00Z">'
        b"<INDIVIDUALS/></CONSOLIDATED_LIST>"
    )
    with pytest.raises(EmptySanctionsListError):
        load_un_consolidated_list(empty)


def test_external_entities_are_never_resolved(tmp_path) -> None:  # noqa: ANN001
    """The file comes from outside: an entity pointing at a local file must not be read."""
    secret = tmp_path / "secret.txt"
    secret.write_text("LEAKED SECRET NAME")
    hostile = (
        f'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY x SYSTEM "file://{secret}">]>'
        '<CONSOLIDATED_LIST dateGenerated="2026-10-10T00:00:00Z"><ENTITIES><ENTITY>'
        "<FIRST_NAME>&x;</FIRST_NAME></ENTITY><ENTITY><FIRST_NAME>Real Entry</FIRST_NAME>"
        "</ENTITY></ENTITIES></CONSOLIDATED_LIST>"
    ).encode()
    screener = load_un_consolidated_list(hostile)
    assert not screener.is_sanctioned("LEAKED SECRET NAME")
    assert screener.is_sanctioned("Real Entry")
