#!/usr/bin/env python3
"""Structural validator for JS/JSX — a small mode machine, since no JS parser is
available in this sandbox.

Why a mode machine and not regexes: in JSX, a quote means different things in
different places. Inside JS code `'` opens a string; inside JSX *text*
("each recipient's language") it is just an apostrophe. A naive scanner blanks
from that apostrophe to the next quote and silently swallows braces, producing
bogus "unclosed {" errors. So we track three modes:

  CODE  normal JS: comments, strings, template literals, regex, brackets
  TAG   inside <... > : attribute strings are real strings, {..} enters CODE
  TEXT  JSX children: quotes are literal text, {..} enters CODE, <..> are tags

Checks reported:
  * bracket balance  ( ) [ ] { }
  * JSX tag nesting  <Foo>..</Foo>, <Foo />, fragments <>..</>

Exit 0 = clean. Validated against known-good files in the repo first.
"""
import re
import sys

HTML = {
    "div", "span", "p", "a", "button", "select", "option", "input", "textarea", "label",
    "table", "thead", "tbody", "tr", "th", "td", "ul", "ol", "li", "h1", "h2", "h3", "h4",
    "h5", "h6", "section", "header", "footer", "nav", "main", "aside", "form", "pre", "code",
    "img", "br", "hr", "strong", "em", "small", "b", "i", "u", "s", "svg", "path", "g",
    "circle", "rect", "line", "polyline", "polygon", "text", "tspan", "defs", "use",
    "figure", "figcaption", "canvas", "iframe", "video", "audio", "source", "track",
    "caption", "colgroup", "col", "fieldset", "legend", "dl", "dt", "dd", "blockquote",
    "hgroup", "details", "summary", "picture", "meta", "link", "style", "title",
}
VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed",
        "source", "track", "wbr"}
NAME_CH = re.compile(r"[A-Za-z0-9_.$:-]")
# a '/' right after one of these is a regex literal, not division
REGEX_PREV = set("(,=:[!&|?{};+-*%~^<>\n")


def line_of(src, idx):
    return src.count("\n", 0, idx) + 1


def qualifies(name):
    """Is this a JSX element name (vs. a less-than comparison)?"""
    if name == "":
        return True  # fragment <>
    base = name.split(".")[0]
    return base[:1].isupper() or name in HTML


def scan(src, path):
    errs = []
    n = len(src)
    brackets = []          # (char, idx, is_mode_boundary)
    tags = []              # (name, idx)
    modes = ["CODE"]
    i = 0
    last_sig = "\n"        # last significant CODE char, for regex detection

    def read_name(j):
        k = j
        while k < n and NAME_CH.match(src[k]):
            k += 1
        return src[j:k], k

    while i < n:
        mode = modes[-1]
        c = src[i]

        # ---------------- CODE ------------------------------------------------
        if mode == "CODE":
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                while i < n and src[i] != "\n":
                    i += 1
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                i += 2
                while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                    i += 1
                i += 2
                continue
            if c == "/" and last_sig in REGEX_PREV:
                # regex literal: skip to unescaped closing '/', honouring [...]
                i += 1
                in_class = False
                while i < n:
                    if src[i] == "\\":
                        i += 2
                        continue
                    if src[i] == "[":
                        in_class = True
                    elif src[i] == "]":
                        in_class = False
                    elif src[i] == "/" and not in_class:
                        break
                    elif src[i] == "\n":
                        break  # not a regex after all; bail out safely
                    i += 1
                i += 1
                last_sig = "/"
                continue
            if c in "'\"":
                q = c
                i += 1
                while i < n and src[i] != q:
                    i += 2 if src[i] == "\\" else 1
                i += 1
                last_sig = "x"
                continue
            if c == "`":
                i += 1
                while i < n and src[i] != "`":
                    if src[i] == "\\":
                        i += 2
                        continue
                    if src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                        d = 0
                        i += 2
                        while i < n:
                            if src[i] == "{":
                                d += 1
                            elif src[i] == "}":
                                if d == 0:
                                    break
                                d -= 1
                            elif src[i] in "'\"":
                                q2 = src[i]
                                i += 1
                                while i < n and src[i] != q2:
                                    i += 2 if src[i] == "\\" else 1
                            i += 1
                        i += 1
                        continue
                    i += 1
                i += 1
                last_sig = "x"
                continue
            if c in "([{":
                brackets.append((c, i, False))
                last_sig = c
                i += 1
                continue
            if c in ")]}":
                want = {")": "(", "]": "[", "}": "{"}[c]
                if not brackets:
                    errs.append(f"{path}:{line_of(src, i)}: stray '{c}'")
                else:
                    o, oi, boundary = brackets.pop()
                    if o != want:
                        errs.append(f"{path}:{line_of(src, i)}: '{c}' closes '{o}' from line {line_of(src, oi)}")
                    elif boundary:
                        modes.pop()   # leaving a JSX expression container
                last_sig = c
                i += 1
                continue
            if c == "<":
                name, j = read_name(i + 1)
                if qualifies(name) and not (name == "" and (j >= n or src[j] != ">")):
                    modes.append("TAG")
                    tags.append((name, i))
                    i = j
                    continue
                last_sig = "<"
                i += 1
                continue
            if not c.isspace():
                last_sig = c
            i += 1
            continue

        # ---------------- TAG -------------------------------------------------
        if mode == "TAG":
            if c in "'\"":
                q = c
                i += 1
                while i < n and src[i] != q:
                    i += 2 if src[i] == "\\" else 1
                i += 1
                continue
            if c == "{":
                brackets.append(("{", i, True))
                modes.append("CODE")
                last_sig = "{"
                i += 1
                continue
            if c == "/" and i + 1 < n and src[i + 1] == ">":
                tags.pop()            # self-closing: nothing left open
                modes.pop()
                i += 2
                continue
            if c == ">":
                name = tags[-1][0]
                modes.pop()
                if name in VOID:
                    tags.pop()        # HTML void element, no closer expected
                else:
                    modes.append("TEXT")
                i += 1
                continue
            i += 1
            continue

        # ---------------- TEXT ------------------------------------------------
        if c == "{":
            brackets.append(("{", i, True))
            modes.append("CODE")
            last_sig = "{"
            i += 1
            continue
        if c == "<":
            if i + 1 < n and src[i + 1] == "/":
                name, j = read_name(i + 2)
                while j < n and src[j] != ">":
                    j += 1
                if not tags:
                    errs.append(f"{path}:{line_of(src, i)}: closing </{name}> with nothing open")
                else:
                    o, oi = tags.pop()
                    if o != name:
                        errs.append(f"{path}:{line_of(src, i)}: </{name}> does not match <{o}> opened at line {line_of(src, oi)}")
                modes.pop()           # leave this element's TEXT
                i = j + 1
                continue
            name, j = read_name(i + 1)
            if qualifies(name) and not (name == "" and (j >= n or src[j] != ">")):
                modes.append("TAG")
                tags.append((name, i))
                i = j
                continue
            i += 1
            continue
        i += 1

    for o, oi, _b in brackets:
        errs.append(f"{path}:{line_of(src, oi)}: unclosed '{o}'")
    for o, oi in tags:
        errs.append(f"{path}:{line_of(src, oi)}: unclosed <{o}>")
    return errs


def main(paths):
    bad = 0
    for p in paths:
        errs = scan(open(p, encoding="utf-8").read(), p)
        if errs:
            bad += 1
            print(f"FAIL {p}")
            for e in errs[:12]:
                print("  " + e)
        else:
            print(f"ok   {p}")
    print("\n" + ("ALL_CLEAN" if not bad else f"{bad} FILE(S) WITH ERRORS"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
