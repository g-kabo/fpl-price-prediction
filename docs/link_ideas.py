"""Make every idea number in ``future-ideas.md`` a link to that idea.

    python docs/link_ideas.py

Gives each idea's row an anchor (``#idea-<n>``), turns references to an
idea into links to it (``#8`` in prose, and the bare number lists in the
combination, branch and report tables), and refreshes the "Jump to" line
of section links under the title. Safe to re-run after adding ideas: links
already made are left alone.
"""

from __future__ import annotations

import re
from pathlib import Path

PATH = Path(__file__).with_name("future-ideas.md")

#: An idea's row, with or without the anchor an earlier run added.
ROW = re.compile(r'^\| (?:<a name="idea-\d+"></a>)?(\d+) \|')
#: ``#8`` not already inside a link (``[#8]``) and not part of a longer word.
REFERENCE = re.compile(r"(?<![\[\w#/&])#(\d{1,3})\b")
#: A cell that is only a list of ideas, each a bare number or an existing link.
_ITEM = r"(?:\d+|\[\d+\]\(#idea-\d+\))"
NUMBER_LIST = re.compile(rf"^\s*{_ITEM}(\s*,\s*{_ITEM})*\s*$")
#: A bare number in such a list, not the inside of a link.
BARE_NUMBER = re.compile(r"(?<![\[\-\d])\b(\d+)\b(?![\]\d])")
JUMP_PREFIX = "**Jump to:**"


def _slug(heading: str) -> str:
    """The anchor GitHub and VS Code give a heading."""
    text = re.sub(r"[^\w\- ]", "", heading.lower())
    return text.strip().replace(" ", "-")


def link(text: str) -> str:
    lines = text.split("\n")
    ideas = {int(m.group(1)) for line in lines if (m := ROW.match(line))}

    def ref(match: re.Match) -> str:
        n = int(match.group(1))
        return f"[#{n}](#idea-{n})" if n in ideas else match.group(0)

    out = []
    for line in lines:
        if line.startswith(JUMP_PREFIX) or line.startswith("#"):
            # Headings keep their text, so their own anchors stay stable.
            out.append(line)
            continue
        row = ROW.match(line)
        if row:
            n = row.group(1)
            line = f'| <a name="idea-{n}"></a>{n} |' + line[row.end():]
        if line.startswith("|"):
            cells = line.split("|")
            for i, cell in enumerate(cells):
                if "idea-" in cell and "<a name" in cell:
                    continue
                if NUMBER_LIST.match(cell):
                    cells[i] = BARE_NUMBER.sub(lambda m: f"[{m.group(1)}](#idea-{m.group(1)})"
                                               if int(m.group(1)) in ideas else m.group(0), cell)
                else:
                    cells[i] = REFERENCE.sub(ref, cell)
            line = "|".join(cells)
        else:
            line = REFERENCE.sub(ref, line)
        out.append(line)

    # The "Jump to" line, rebuilt each run from the current sections.
    out = [line for line in out if not line.startswith(JUMP_PREFIX)]
    sections = [line[3:] for line in out if line.startswith("## ")]
    jump = JUMP_PREFIX + " " + " · ".join(f"[{s}](#{_slug(s)})" for s in sections)
    title = next(i for i, line in enumerate(out) if line.startswith("# "))
    out[title + 1:title + 1] = ["", jump]
    # Collapse the blank lines the insert may have doubled.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


if __name__ == "__main__":
    PATH.write_text(link(PATH.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Linked {PATH.name}")
