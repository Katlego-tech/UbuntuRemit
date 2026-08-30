"""Tests for the gate's markup checker -- T009.

The checker's whole value is that it fires on broken markup and stays silent on
correct markup. HTML5 lets a dozen elements omit their end tag, so the second
half is the harder half: a checker that flags `<ul><li>a<li>b</ul>` is worse than
no checker, because people learn to ignore it.

Every "silent" case below is therefore a real HTML5 allowance, not a convenience.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from check_markup import Finding, check_markup, main

REPO_ROOT = Path(__file__).resolve().parent.parent


def findings_for(tmp_path: Path, markup: str) -> list[Finding]:
    page = tmp_path / "page.html"
    page.write_text(markup, encoding="utf-8")
    return check_markup(page)


def messages(found: list[Finding]) -> str:
    return " | ".join(f.message for f in found)


class TestWellFormedMarkupIsSilent:
    def test_a_minimal_document_has_no_findings(self, tmp_path):
        assert findings_for(tmp_path, "<!DOCTYPE html>\n<html><body><p>hi</p></body></html>") == []

    def test_void_elements_need_no_end_tag(self, tmp_path):
        markup = "<html><body><img src='a.png'><br><hr><input name='x'></body></html>"
        assert findings_for(tmp_path, markup) == []

    def test_void_elements_may_be_written_xhtml_style(self, tmp_path):
        # The frozen Stitch export writes <meta .../> and <link .../> this way.
        markup = (
            '<html><head><meta charset="utf-8"/><link href="a.css" rel="stylesheet"/></head></html>'
        )
        assert findings_for(tmp_path, markup) == []

    def test_list_items_may_omit_their_end_tag(self, tmp_path):
        assert findings_for(tmp_path, "<ul><li>one<li>two</ul>") == []

    def test_table_cells_and_rows_may_omit_their_end_tags(self, tmp_path):
        markup = "<table><tr><td>a<td>b<tr><td>c<td>d</table>"
        assert findings_for(tmp_path, markup) == []

    def test_a_paragraph_is_closed_by_a_following_block(self, tmp_path):
        assert findings_for(tmp_path, "<div><p>one<p>two<ul><li>x</ul></div>") == []

    def test_a_block_element_inside_a_paragraph_closes_it(self, tmp_path):
        # No explicit </p>, so nothing is stray -- this is the common shape and
        # it must stay silent.
        assert findings_for(tmp_path, "<body><p>one<div>two</div></body>") == []

    def test_html_head_and_body_end_tags_are_optional(self, tmp_path):
        assert findings_for(tmp_path, "<html><head><title>t</title><body><p>x") == []

    def test_defined_character_references_pass(self, tmp_path):
        # The three the export actually uses.
        assert findings_for(tmp_path, "<p>ZA&ndash;KE &mdash; a &lt; b</p>") == []


class TestUnclosedAndStrayTags:
    def test_an_unclosed_div_is_reported_at_its_opening_line(self, tmp_path):
        found = findings_for(
            tmp_path, "<html>\n<body>\n<div class='card'>\n<p>x</p>\n</body>\n</html>"
        )
        assert len(found) == 1
        assert found[0].line == 3
        assert "div" in found[0].message

    def test_an_unclosed_element_at_end_of_file_is_reported(self, tmp_path):
        found = findings_for(tmp_path, "<div><span>text")
        assert [f.message.split()[0] for f in found] == ["<span>", "<div>"] or len(found) == 2
        assert "span" in messages(found)
        assert "div" in messages(found)

    def test_a_stray_end_tag_is_reported(self, tmp_path):
        found = findings_for(tmp_path, "<div>x</div></section>")
        assert len(found) == 1
        assert "section" in found[0].message

    def test_crossed_nesting_is_reported(self, tmp_path):
        found = findings_for(tmp_path, "<div><span>x</div></span>")
        assert "span" in messages(found)

    def test_a_paragraph_end_tag_after_a_block_is_stray(self, tmp_path):
        # <div> closes the <p>, so the </p> that follows </div> is not a match:
        # a browser turns it into an extra empty paragraph in the DOM. This is
        # the case that makes _P_CLOSERS load-bearing rather than decorative.
        found = findings_for(tmp_path, "<body><p>one<div>two</div></p></body>")
        assert len(found) == 1
        assert "</p>" in found[0].message

    def test_a_void_block_element_also_closes_a_paragraph(self, tmp_path):
        found = findings_for(tmp_path, "<body><p>one<hr></p></body>")
        assert len(found) == 1
        assert "</p>" in found[0].message

    def test_an_end_tag_on_a_void_element_is_reported(self, tmp_path):
        found = findings_for(tmp_path, "<p>a<br></br>b</p>")
        assert len(found) == 1
        # The diagnosis has to name the actual cause. Falling through to the
        # generic "closes nothing" message would still fail the gate, but it
        # sends the reader looking for a missing <br> that was never possible.
        assert "void" in found[0].message


class TestSelfClosingSyntax:
    def test_a_self_closed_non_void_element_is_reported(self, tmp_path):
        # HTML ignores the slash: <div/> opens a div, it does not close one.
        found = findings_for(tmp_path, "<body><div/><p>after</p></body>")
        assert len(found) == 1
        assert "div" in found[0].message

    def test_self_closing_is_legal_inside_foreign_content(self, tmp_path):
        markup = '<svg viewBox="0 0 1 1"><path d="M0 0"/><circle r="1"/></svg>'
        assert findings_for(tmp_path, markup) == []

    def test_foreign_elements_still_have_to_be_closed(self, tmp_path):
        found = findings_for(tmp_path, "<svg><g><path d='M0 0'/></svg>")
        assert "g" in messages(found)


class TestCharacterReferences:
    def test_an_undefined_named_reference_is_reported(self, tmp_path):
        # &mdsh; does not fail to parse -- it renders as the literal text
        # "&mdsh;" on the page, which is why a parser alone will not catch it.
        found = findings_for(tmp_path, "<p>Ripple &mdsh; est. 3.2s</p>")
        assert len(found) == 1
        assert "mdsh" in found[0].message

    def test_an_undefined_reference_in_an_attribute_is_reported(self, tmp_path):
        found = findings_for(tmp_path, '<a href="x.html?a=1&amps;b=2">x</a>')
        assert len(found) == 1
        assert "amps" in found[0].message

    def test_a_bare_ampersand_is_not_treated_as_a_reference(self, tmp_path):
        # No semicolon, so HTML5 renders it as text. Not this checker's business.
        assert findings_for(tmp_path, "<p>Tom &amp; Jerry, AT&T</p>") == []

    def test_script_content_is_raw_text_not_markup(self, tmp_path):
        # An ampersand inside <script> is JavaScript, never a character
        # reference -- and a `<` in a comparison is not a tag.
        markup = "<script>\nif (a &foo; b) { x = 1 < 2; }\n</script>"
        assert findings_for(tmp_path, markup) == []


class TestTheRealPages:
    """The regression anchor: the pages the gate actually guards."""

    def test_every_page_in_apps_web_is_well_formed(self):
        pages = sorted((REPO_ROOT / "apps" / "web").glob("*.html"))
        assert pages, "apps/web has no pages -- the export is missing"
        problems = {p.name: [str(f) for f in check_markup(p)] for p in pages}
        assert {name: v for name, v in problems.items() if v} == {}


class TestCommandLine:
    def test_exit_code_is_zero_when_every_page_is_clean(self, tmp_path, capsys):
        page = tmp_path / "ok.html"
        page.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")
        assert main([str(page)]) == 0

    def test_exit_code_is_one_and_the_finding_is_printed(self, tmp_path, capsys):
        page = tmp_path / "bad.html"
        page.write_text("<html><body><div>\n</body></html>", encoding="utf-8")
        assert main([str(page)]) == 1
        assert "div" in capsys.readouterr().out

    def test_a_missing_file_is_an_error_not_a_pass(self, tmp_path):
        assert main([str(tmp_path / "nope.html")]) == 1

    def test_no_paths_at_all_is_an_error_not_a_pass(self):
        # A gate that reports green because it was handed nothing is the
        # failure scripts/gate.sh exists to make impossible.
        assert main([]) == 1


def test_findings_render_as_path_line_column_message(tmp_path):
    found = findings_for(tmp_path, "<div>\n")
    assert len(found) == 1
    rendered = str(found[0])
    assert rendered.startswith(str(tmp_path / "page.html") + ":1:1: ")


@pytest.mark.parametrize(
    "tag",
    [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    ],
)
def test_every_html5_void_element_is_known(tmp_path, tag):
    assert findings_for(tmp_path, f"<div><{tag}></div>") == []
