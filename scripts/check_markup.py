#!/usr/bin/env python3
"""Structural markup check for `apps/web` -- the second half of T009.

`scripts/gate.sh` already proves every internal `href` resolves to a file that
exists. This proves the other half of that task: that each page is structurally
well formed. A page whose tags do not nest is a page whose layout is whatever
the browser's error recovery decides it is, and that is not a design anyone
approved -- which matters more here than usual, because `apps/web` is a frozen
export whose only other test is a human holding it beside a PNG.

What it asserts:

  * every element whose end tag HTML5 makes mandatory is closed, in order;
  * no end tag closes something that was never opened;
  * no void element (`<br>`, `<img>`, ...) is given an end tag;
  * outside foreign content, no non-void element is written XHTML-style as
    `<div/>` -- HTML ignores that slash, so the element opens and then swallows
    the rest of the document;
  * every named character reference is one HTML5 defines. `&mdsh;` does not
    fail to parse; it renders as the literal text "&mdsh;" on a settlement
    screen, which is exactly the class of defect a parser alone misses.

What it does not assert: attribute validity, the content model (a `<div>` inside
a `<p>` passes here and is illegal HTML5), or anything about accessibility --
that is T026, and it needs a browser. This needs only the standard library,
which is why it can live in the gate and run on every push.

The hard part is silence on correct markup. HTML5 lets a dozen elements omit
their end tag, and a checker that flags `<ul><li>a<li>b</ul>` teaches people to
ignore it. `_OPTIONAL_END` and `_P_CLOSERS` encode those rules.

Usage:
    python3 scripts/check_markup.py apps/web/*.html

Exit 0 = every file parsed and nested correctly. Exit 1 = at least one finding,
printed as `path:line:column: message`, or no readable file was given at all.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from html.entities import html5
from html.parser import HTMLParser
from pathlib import Path

# Void elements have no content and no end tag. `keygen` and `param` are
# obsolete but still parse as void, so they are listed rather than left to
# surprise whoever maintains an older page.
_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "keygen",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

# Roots of foreign content. Inside these the HTML rules above do not apply:
# nothing is void, nothing auto-closes, and `<path/>` is the normal spelling.
_FOREIGN = frozenset({"svg", "math"})

# Elements HTML5 permits you to leave unclosed. Finding one still open when its
# parent closes -- or at end of file -- is legal markup, not a finding.
_OPTIONAL_END = frozenset(
    {
        "html",
        "head",
        "body",
        "p",
        "li",
        "dt",
        "dd",
        "option",
        "optgroup",
        "caption",
        "colgroup",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "rt",
        "rp",
    }
)

# The start tags that implicitly close an open `<p>`. This is the only implicit
# close this checker needs to model, and the reason is worth stating: HTML5's
# other omitted-end-tag rules (`<li>` closed by `<li>`, `<td>` by `<td>`, and so
# on) only ever close elements that are themselves in `_OPTIONAL_END`, so
# whether they are popped early or late is unobservable to a checker that does
# not validate the content model -- the finding set is identical either way.
# `<p>` is different: it is closed by block elements whose own end tags are
# mandatory, so modelling it decides whether `</div>` looks matched or stray.
_P_CLOSERS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "details",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "search",
        "section",
        "table",
        "ul",
    }
)

# A named reference that survived HTMLParser's own unescaping of an attribute
# value is, by definition, one HTML5 does not define.
_NAMED_REF = re.compile(r"&([a-zA-Z][a-zA-Z0-9]*);")


@dataclass(frozen=True)
class Finding:
    """One defect, addressed the way an editor jumps to it."""

    path: Path
    line: int
    column: int  # 1-based, to match every compiler and editor
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}: {self.message}"


class _StructureParser(HTMLParser):
    """Tracks the open-element stack and records where it goes wrong.

    `convert_charrefs=False` is deliberate: with the default, character
    references in text are silently resolved and never reported, so an
    undefined one would be invisible here.
    """

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__(convert_charrefs=False)
        self.path = path
        self.lines = lines
        self.findings: list[Finding] = []
        # (tag, line, column) for each element still open.
        self.stack: list[tuple[str, int, int]] = []
        self.foreign_depth = 0

    # -- recording ---------------------------------------------------------
    def _add(self, line: int, column: int, message: str) -> None:
        self.findings.append(Finding(self.path, line, column + 1, message))

    def _here(self) -> tuple[int, int]:
        return self.getpos()

    # -- structure ---------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check_attribute_refs(attrs)
        if not self.foreign_depth:
            self._close_open_paragraph(tag)
            # A void element opens nothing, so it never joins the stack -- but it
            # can still close a paragraph (`<hr>` does), which is why this comes
            # after the line above rather than before it.
            if tag in _VOID:
                return
        line, column = self._here()
        self.stack.append((tag, line, column))
        if tag in _FOREIGN:
            self.foreign_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check_attribute_refs(attrs)
        if self.foreign_depth:
            # `<path/>` is how SVG is written. Nothing to say about it.
            return
        self._close_open_paragraph(tag)
        if tag in _VOID:
            return
        line, column = self._here()
        # Reported once and then treated as a complete element, so one stray
        # slash produces one finding rather than a cascade of unclosed parents.
        self._add(
            line,
            column,
            f"<{tag}/> is not self-closing in HTML -- the slash is ignored and "
            f"<{tag}> stays open. Write <{tag}></{tag}>.",
        )

    def handle_endtag(self, tag: str) -> None:
        line, column = self._here()

        if not self.foreign_depth and tag in _VOID:
            self._add(line, column, f"</{tag}> closes a void element, which has no end tag")
            return

        depth = self._innermost(tag)
        if depth is None:
            self._add(line, column, f"</{tag}> closes nothing -- no <{tag}> is open here")
            return

        for open_tag, open_line, open_column in reversed(self.stack[depth + 1 :]):
            if self.foreign_depth or open_tag not in _OPTIONAL_END:
                self._add(
                    open_line,
                    open_column,
                    f"<{open_tag}> is never closed -- </{tag}> on line {line} closes its parent",
                )
        del self.stack[depth:]
        self.foreign_depth = sum(1 for open_tag, _, _ in self.stack if open_tag in _FOREIGN)

    def _innermost(self, tag: str) -> int | None:
        for depth in range(len(self.stack) - 1, -1, -1):
            if self.stack[depth][0] == tag:
                return depth
        return None

    def _close_open_paragraph(self, tag: str) -> None:
        """Apply HTML5's one implicit close that changes what counts as matched."""
        while self.stack and self.stack[-1][0] == "p" and tag in _P_CLOSERS:
            self.stack.pop()

    # -- character references ---------------------------------------------
    def handle_entityref(self, name: str) -> None:
        line, column = self._here()
        text = self.lines[line - 1] if 0 < line <= len(self.lines) else ""
        after = column + 1 + len(name)
        if text[after : after + 1] != ";":
            # `AT&T` -- no semicolon, so HTML5 renders it as text and there is
            # no reference here to judge.
            return
        if f"{name};" not in html5:
            self._add(line, column, f"&{name}; is not a character reference HTML5 defines")

    def _check_attribute_refs(self, attrs: list[tuple[str, str | None]]) -> None:
        line, column = self._here()
        for attr, value in attrs:
            if value is None:
                continue
            # HTMLParser has already unescaped every reference it recognises,
            # so anything still in this shape is undefined.
            for match in _NAMED_REF.finditer(value):
                self._add(
                    line,
                    column,
                    f'&{match.group(1)}; in {attr}="..." is not a character '
                    "reference HTML5 defines",
                )

    # -- end of file -------------------------------------------------------
    def unclosed(self) -> None:
        for tag, line, column in reversed(self.stack):
            if tag not in _OPTIONAL_END:
                self._add(line, column, f"<{tag}> is never closed")


def check_markup(path: Path) -> list[Finding]:
    """Parse one HTML file and return every structural finding, in file order."""
    source = path.read_text(encoding="utf-8")
    parser = _StructureParser(path, source.splitlines())
    parser.feed(source)
    parser.close()
    parser.unclosed()
    return sorted(parser.findings, key=lambda f: (f.line, f.column, f.message))


def main(argv: list[str]) -> int:
    if not argv:
        print("check_markup: no files given -- nothing was checked, so nothing passed.")
        return 1

    findings: list[Finding] = []
    unreadable = 0
    for name in argv:
        path = Path(name)
        try:
            findings.extend(check_markup(path))
        except OSError as exc:
            print(f"{path}: cannot be read -- {exc.strerror}")
            unreadable += 1

    for finding in findings:
        print(finding)

    if findings or unreadable:
        print(
            f"   {len(findings)} markup finding(s) across {len(argv)} file(s)"
            f"{f', {unreadable} unreadable' if unreadable else ''}."
        )
        return 1

    print(f"   clean ({len(argv)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
