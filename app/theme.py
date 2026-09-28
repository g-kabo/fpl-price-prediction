"""The app's visual vocabulary, for the parts Python has to draw.

``assets/style.css`` owns the page; this module owns what CSS cannot reach:
Plotly figures, and the club shirts, which are generated SVG. The hex values
here mirror the custom properties at the top of the stylesheet -- change one,
change both.

The world is FPL's own transfer market: aubergine chrome, a striped pitch,
shirts in club colours, a price tag under every shirt. Green and pink-red are
reserved for price direction and nothing else, which is why the position
colours below avoid both.
"""

from __future__ import annotations

from base64 import b64encode
from functools import lru_cache

AUBERGINE = "#2b0033"
INK = "#1b0a21"
INK_SOFT = "#5b4a63"
LINE = "#e6e0ea"
PAPER = "#f6f4f8"
SURFACE = "#ffffff"
VOLT = "#00ff85"
#: Chrome accent. Never used for data: green is taken by "rising".
CYAN = "#05e2ff"

#: Direction, and only direction. The text shades clear 4.5:1 on white;
#: the fills carry dark (rise) or white (fall) text on top of them.
RISE = "#007a3f"
FALL = "#d6004f"
HOLD = "#6b5b73"

#: One threshold for "moved", everywhere: FPL prices move in tenths, so a
#: predicted change under £0.1m is a price that holds.
MOVE_THRESHOLD = 0.1

FONT = "Barlow, system-ui, sans-serif"
FONT_FIGURES = "'Barlow Condensed', Barlow, system-ui, sans-serif"

#: Position pills and scatter marks. No green, no red: those mean a price
#: is moving. Each also has a marker shape, so colour is never the only cue.
POSITION_COLOURS = {
    "GK": "#f5b400",
    "DEF": "#00b8d4",
    "MID": "#7c4dff",
    "FWD": "#ff6d00",
}

POSITION_SYMBOLS = {
    "GK": "diamond",
    "DEF": "square",
    "MID": "triangle-up",
    "FWD": "circle",
}

#: Home shirts: ``(body, sleeves, trim, stripe)``. ``stripe`` is ``None``
#: for a plain shirt. Clubs outside this table get a neutral kit rather
#: than a guessed one.
KITS: dict[str, tuple[str, str, str, str | None]] = {
    "Arsenal":        ("#db0007", "#ffffff", "#ffffff", None),
    "Aston Villa":    ("#670e36", "#95bfe5", "#95bfe5", None),
    "Bournemouth":    ("#da291c", "#da291c", "#111111", "#111111"),
    "Brentford":      ("#e30613", "#e30613", "#111111", "#ffffff"),
    "Brighton":       ("#0057b8", "#0057b8", "#ffffff", "#ffffff"),
    "Burnley":        ("#6c1d45", "#99d6ea", "#99d6ea", None),
    "Chelsea":        ("#034694", "#034694", "#ffffff", None),
    "Coventry City":  ("#59cbe8", "#59cbe8", "#ffffff", None),
    "Crystal Palace": ("#1b458f", "#1b458f", "#c4122e", "#c4122e"),
    "Everton":        ("#003399", "#003399", "#ffffff", None),
    "Fulham":         ("#ffffff", "#ffffff", "#111111", None),
    "Hull City":      ("#f5a12d", "#f5a12d", "#111111", "#111111"),
    "Ipswich Town":   ("#0044a9", "#ffffff", "#ffffff", None),
    "Leeds":          ("#ffffff", "#ffffff", "#1d428a", None),
    "Leicester":      ("#003090", "#003090", "#fdbe11", None),
    "Liverpool":      ("#c8102e", "#c8102e", "#f6eb61", None),
    "Luton":          ("#f78f1e", "#f78f1e", "#002d62", None),
    "Man City":       ("#6cabdd", "#6cabdd", "#ffffff", None),
    "Man Utd":        ("#da291c", "#da291c", "#111111", None),
    "Newcastle":      ("#ffffff", "#ffffff", "#111111", "#111111"),
    "Nott'm Forest":  ("#dd0000", "#dd0000", "#ffffff", None),
    "Sheffield Utd":  ("#ee2737", "#ee2737", "#111111", "#ffffff"),
    "Southampton":    ("#d71920", "#d71920", "#111111", "#ffffff"),
    "Spurs":          ("#ffffff", "#ffffff", "#132257", None),
    "Sunderland":     ("#eb172b", "#eb172b", "#111111", "#ffffff"),
    "West Ham":       ("#7a263a", "#1bb1e7", "#1bb1e7", None),
    "Wolves":         ("#fdb913", "#fdb913", "#231f20", None),
}

NEUTRAL_KIT = ("#d9d2de", "#d9d2de", "#5b4a63", None)

_BODY = "M18 22 L18 58 L46 58 L46 22 L46 9 L38 4 Q32 10 26 4 L18 9 Z"
_LEFT_SLEEVE = "M18 9 L5 17 L11 28 L18 23 Z"
_RIGHT_SLEEVE = "M46 9 L59 17 L53 28 L46 23 Z"
_OUTLINE = ("M26 4 Q32 10 38 4 L46 9 L59 17 L53 28 L46 23 L46 58 L18 58 "
            "L18 23 L11 28 L5 17 L18 9 Z")


@lru_cache(maxsize=None)
def shirt_uri(team: str | None) -> str:
    """A club's home shirt as an SVG data URI, for an ``<img>``.

    Drawn rather than sourced: kit colours are facts about a club, where a
    crest or a photographed shirt would be someone's artwork.
    """
    body, sleeves, trim, stripe = KITS.get(team or "", NEUTRAL_KIT)

    stripes = ""
    if stripe:
        bands = "".join(
            f'<rect x="{x}" y="0" width="4" height="64" fill="{stripe}"/>'
            for x in (21, 29, 37)
        )
        stripes = f'<g clip-path="url(#b)">{bands}</g>'

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<defs><clipPath id="b"><path d="{_BODY}"/></clipPath></defs>'
        f'<path d="{_BODY}" fill="{body}"/>'
        f"{stripes}"
        f'<path d="{_LEFT_SLEEVE}" fill="{sleeves}"/>'
        f'<path d="{_RIGHT_SLEEVE}" fill="{sleeves}"/>'
        f'<path d="M26 4 Q32 10 38 4" fill="none" stroke="{trim}" stroke-width="3"/>'
        f'<path d="{_OUTLINE}" fill="none" stroke="rgba(27,10,33,0.35)" '
        'stroke-width="1.2" stroke-linejoin="round"/>'
        "</svg>"
    )
    return "data:image/svg+xml;base64," + b64encode(svg.encode()).decode()


def direction(delta: float) -> str:
    """``"rise"``, ``"fall"`` or ``"hold"``, on the one shared threshold."""
    if delta >= MOVE_THRESHOLD:
        return "rise"
    if delta <= -MOVE_THRESHOLD:
        return "fall"
    return "hold"


def money(value: float, signed: bool = False, places: int = 1) -> str:
    """``£7.5m``, or ``+£0.6m`` / ``−£0.4m`` with a true minus sign."""
    if value is None:
        return "–"
    text = f"£{abs(value):.{places}f}m"
    if not signed:
        return text if value >= 0 else f"−{text}"
    if round(abs(value), places) == 0:
        return f"±{text}"
    return f"+{text}" if value > 0 else f"−{text}"
