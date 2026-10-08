"""Club home shirts, for the site's generated shirt SVGs.

``export_static.py`` ships these in ``model.json``; ``web/js/theme.js``
draws the shirts from them.
"""

from __future__ import annotations

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
