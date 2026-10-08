"""Check docs/future-ideas.md for the mistakes that creep in when editing it.

    python .claude/skills/future-ideas/scripts/check_ideas.py [path]

Prints one line per problem and exits 1 if there are any, 0 if the doc is
clean. Run it after docs/link_ideas.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[4] / "docs" / "future-ideas.md"

LEVELS = ("Low–Med", "Med–High", "Low", "Medium", "High")
#: A level, optionally followed by a qualifier: "Low for visitors".
SCORE = re.compile(r"^(?:Low–Med|Med–High|Low|Medium|High)(?:\s|$)")
STATUSES = ("idea", "planned", "in progress", "done", "dropped")
IDEA_CELL = re.compile(r'^\s*(?:<a name="idea-(\d+)"></a>)?(\d+)\s*$')
LINK = re.compile(r"\]\(#idea-(\d+)\)")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def numbers(cell: str) -> list[int]:
    """Idea numbers in a list cell such as ``[38](#idea-38), 31``."""
    return [int(n) for n in re.findall(r"(?<![\w-])(\d+)(?![\w-])", re.sub(r"\(#idea-\d+\)", "", cell))]


def check(text: str) -> list[str]:
    problems: list[str] = []
    lines = text.split("\n")

    # Tables: a row after a blank line with no header row above it has been
    # split off its table and renders as plain text.
    for n, line in enumerate(lines[1:-1], start=1):
        if line.startswith("|") and lines[n - 1].strip() == "" and not lines[n + 1].startswith("|---"):
            problems.append(f"line {n + 1}: table row split from its table by a blank line")

    # Idea rows, read through their table's header.
    ideas: dict[int, int] = {}
    open_ideas: list[int] = []
    section, header = "", None
    for n, line in enumerate(lines, start=1):
        if line.startswith("## "):
            section, header = line[3:], None
            continue
        if not line.startswith("|"):
            # A blank line that splits a table (reported above) shouldn't
            # also lose the header for every row after it.
            following = lines[n:n + 2]
            split = (line.strip() == "" and len(following) == 2 and following[0].startswith("|")
                     and not following[1].startswith("|---"))
            if not split:
                header = None
            continue
        row = cells(line)
        if header is None:
            header = row
            continue
        if line.startswith("|---"):
            continue
        match = IDEA_CELL.match(row[0]) if row else None
        if not match or header[0] != "#":
            continue
        number = int(match.group(2))
        if match.group(1) and int(match.group(1)) != number:
            problems.append(f"line {n}: anchor idea-{match.group(1)} on idea {number}")
        if number in ideas:
            problems.append(f"line {n}: idea {number} also at line {ideas[number]}")
        ideas[number] = n
        if len(row) != len(header):
            problems.append(f"line {n}: idea {number} has {len(row)} cells, its table has {len(header)}"
                            " (a stray | in the text?)")
            continue
        named = dict(zip(header, row))
        for column in ("Effort", "Usefulness", "Impact"):
            value = named.get(column, "")
            if not SCORE.match(value):
                problems.append(f"line {n}: idea {number} {column} {value!r} is not a score")
        status = named.get("Status", "")
        if status.startswith(("idea", "planned", "in progress")):
            open_ideas.append(number)
        if not status.startswith(STATUSES):
            problems.append(f"line {n}: idea {number} status {status!r} is not one of {STATUSES}")

    if not ideas:
        return problems + ["no idea rows found"]

    # Every number named in a guide, combination or verdict must be an idea;
    # the branch guide must place every idea exactly once.
    placed: dict[int, int] = {}
    on_pages: set[int] = set()
    off_site: set[int] = set()  # verdict Report or Tooling: never on a page
    section = ""
    for n, line in enumerate(lines, start=1):
        if line.startswith("## "):
            section = line[3:]
            continue
        if not line.startswith("|") or line.startswith("|---"):
            continue
        row = cells(line)
        if section.startswith("Report or app") and row[0] in ("**Report**", "**Tooling**"):
            off_site.update(numbers(row[1]))
        if section.startswith("Ideas by existing page") and len(row) > 1:
            on_pages.update(numbers(row[1]))
        if section.startswith(("Branch or straight", "Report or app", "Combinations",
                               "Ideas by existing page")) and len(row) > 1:
            if row[1] in ("Ideas",) or "everything else" in row[1]:
                continue
            bare = re.findall(r"(?<![\[\-\d])\b\d+\b(?![\]\d])", row[1])
            if bare:
                problems.append(f"line {n}: unlinked idea numbers {', '.join(bare)}: run docs/link_ideas.py")
            for number in numbers(row[1]):
                if number not in ideas:
                    problems.append(f"line {n}: {section!r} names idea {number}, which doesn't exist")
                elif section.startswith("Branch or straight"):
                    if number in placed:
                        problems.append(f"line {n}: idea {number} also placed at line {placed[number]}"
                                        " in the branch guide")
                    placed[number] = n
    # Finished and dropped ideas may leave the guide; open ones may not.
    for number in sorted(set(open_ideas) - set(placed)):
        problems.append(f"idea {number} is open but missing from the branch guide")
    # Every open idea that lands on the site needs a row in "Ideas by existing
    # page"; reports and tooling never do, and finished ideas leave it.
    if any(l.startswith("## Ideas by existing page") for l in lines):
        for number in sorted(set(open_ideas) - off_site - on_pages):
            problems.append(f"idea {number} is open and on the site but missing from 'Ideas by existing page'")
        for number in sorted(on_pages & (set(ideas) - set(open_ideas))):
            problems.append(f"idea {number} is done or dropped but still in 'Ideas by existing page'")

    for target in sorted({int(t) for t in LINK.findall(text)} - set(ideas)):
        problems.append(f"a link points at idea {target}, which doesn't exist")
    unlinked = [m for m in re.findall(r"(?<![\[\w#/&])#(\d{1,3})\b",
                                      "\n".join(l for l in lines if not l.startswith("#")))]
    if unlinked:
        problems.append(f"{len(unlinked)} unlinked #N references: run docs/link_ideas.py")
    return problems


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT
    problems = check(path.read_text(encoding="utf-8"))
    for problem in problems:
        print(problem)
    ideas = len(re.findall(r'^\| (?:<a name="idea-\d+"></a>)?\d+ \|', path.read_text(encoding="utf-8"), re.M))
    print(f"{path.name}: {ideas} ideas, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
