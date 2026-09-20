"""Fetching and caching of the upstream FPL season data.

Source is Vaastav Anand's ``Fantasy-Premier-League`` GitHub repo, which
mirrors the official API into one ``players_raw.csv`` per season. Every
download is cached under ``data/`` so subsequent runs work offline; pass
``refresh=True`` (or ``--refresh`` on the pipeline) to re-pull.

R equivalent: the ``read_csv(".../players_raw.csv")`` block at lines
1004-1024 of ``Price Prediction.Rmd``, plus the ``master_teams`` assembly
at lines 1104-1112.

:func:`load_live_season` bypasses the mirror and reads the official API
directly. The mirror is refreshed on its maintainer's schedule, so for the
*current* season it can lag the real table by weeks; the app's projection
page needs today's numbers.

It also reads ``fixtures``, because "how much of the season has been
played" has no single answer mid-gameweek -- see :class:`SeasonProgress`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
import requests

import config


def _cached_csv(url: str, cache_path, refresh: bool = False) -> pd.DataFrame:
    """Read ``url``, caching the raw bytes at ``cache_path``."""
    if cache_path.exists() and not refresh:
        return pd.read_csv(cache_path, encoding="utf-8")

    df = pd.read_csv(url, encoding="utf-8")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False, encoding="utf-8")
    return df


def load_players_raw(season: int, refresh: bool = False) -> pd.DataFrame:
    """End-of-season (or live, for the current season) player snapshot."""
    folder = config.season_folder(season)
    return _cached_csv(
        f"{config.GITHUB_BASE}{folder}/players_raw.csv",
        config.DATA_DIR / f"players_raw_{folder}.csv",
        refresh,
    )


def load_teams(season: int, refresh: bool = False) -> pd.DataFrame:
    """That season's team id -> name table, normalised to the master schema."""
    folder = config.season_folder(season)
    teams = _cached_csv(
        f"{config.GITHUB_BASE}{folder}/teams.csv",
        config.DATA_DIR / f"teams_{folder}.csv",
        refresh,
    )
    return pd.DataFrame(
        {
            "season": season,
            "team": teams["id"].astype(int),
            "team_name": teams["name"].astype(str),
        }
    )


def load_master_teams(seasons: list[int], refresh: bool = False) -> pd.DataFrame:
    """Season + team id -> team name, covering every requested season.

    ``master_team_list.csv`` upstream only runs to 2023-24, so anything
    newer is appended from that season's own ``teams.csv``. The R did this
    by hand for 2024-25 and pulled 2025-26 off the live API; doing it in a
    loop means no edit is needed next season.
    """
    master = _cached_csv(
        f"{config.GITHUB_BASE}master_team_list.csv",
        config.DATA_DIR / "master_team_list.csv",
        refresh,
    )
    # "2023-24" -> 2023
    master["season"] = master["season"].astype(str).str[:4].astype(int)
    master = master[["season", "team", "team_name"]]
    master["team"] = master["team"].astype(int)
    master["team_name"] = master["team_name"].astype(str)

    covered = set(master["season"].unique())
    missing = [s for s in seasons if s not in covered]
    frames = [master] + [load_teams(s, refresh) for s in missing]

    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(subset=["season", "team"], keep="first")


def load_all_seasons(seasons: list[int], refresh: bool = False) -> dict[int, pd.DataFrame]:
    return {s: load_players_raw(s, refresh) for s in seasons}


# --- live API --------------------------------------------------------------

#: The endpoint ``players_raw.csv`` is itself generated from.
FPL_API = "https://fantasy.premierleague.com/api/bootstrap-static/"

#: Every fixture of the season, with its own played/finished state.
FPL_FIXTURES_API = "https://fantasy.premierleague.com/api/fixtures/"

TOTAL_GAMEWEEKS = 38


def load_live_bootstrap(timeout: int = 20) -> dict:
    """One ``bootstrap-static`` payload: elements, teams and events."""
    response = requests.get(FPL_API, timeout=timeout)
    response.raise_for_status()
    return response.json()


def load_live_fixtures(timeout: int = 20) -> pd.DataFrame:
    """All 380 fixtures, each flagged ``started`` and ``finished``."""
    response = requests.get(FPL_FIXTURES_API, timeout=timeout)
    response.raise_for_status()
    return pd.DataFrame(response.json())


@dataclass
class SeasonProgress:
    """How much of the season each team has actually played.

    There is no single answer to that mid-gameweek, and pretending there
    was is what this class exists to fix. On a Saturday evening in
    gameweek 5, twelve teams have played five matches and eight have
    played four; dividing every player's totals by the same number
    over-projects the first twelve by a quarter and prices them to match.
    So the denominator is per team, not per league.

    Counting finished *events* is wrong twice over. An event only flips
    ``finished`` once its bonus points are confirmed, hours after the last
    whistle and often the next morning, so a Saturday afternoon's matches
    are all still "unfinished" while their points already sit in every
    player's total.

    ``team_games`` therefore counts fixtures that have *started*, each
    worth its own ``minutes / 90``. A match at half time counts as half a
    fixture, which is about how much of its points have been scored.
    """

    #: team id -> fixtures played, fractional while a match is in progress.
    team_games: pd.Series
    #: Events whose bonus has been confirmed. Display only, since it lags.
    gameweeks_finished: int = 0
    #: The gameweek currently open, if any.
    current_event: int | None = None
    #: False when this was inferred offline rather than read from fixtures.
    is_exact: bool = True

    @property
    def league_games(self) -> float:
        """Season elapsed in gameweeks, averaged over the twenty teams.

        The right denominator for anything accruing on the league's
        calendar rather than one team's: transfers in and out tick over
        daily for every player, whether or not their own club has kicked
        off yet.
        """
        return float(self.team_games.mean()) if len(self.team_games) else 0.0

    @property
    def spread(self) -> tuple[float, float]:
        """Fewest and most fixtures played by any one team."""
        if not len(self.team_games):
            return (0.0, 0.0)
        return (float(self.team_games.min()), float(self.team_games.max()))

    @property
    def is_split(self) -> bool:
        """True when teams are mid-gameweek and disagree on games played."""
        low, high = self.spread
        return high - low > 0.01

    def for_players(self, players: pd.DataFrame) -> pd.Series:
        """Games played, one row per player, aligned to ``players``.

        A player's denominator is his club's, not his own: a defender
        benched four games running has still had four gameweeks of
        opportunity, and counting only his own appearances would project
        those zero minutes as if the season had not started.
        """
        games = players["team"].map(self.team_games)
        return games.fillna(self.league_games).astype(float)


def season_progress(fixtures: pd.DataFrame, events: pd.DataFrame) -> SeasonProgress:
    """Per-team fixtures played, read off the fixture list."""
    started = fixtures["started"].fillna(False).astype(bool)
    played = fixtures[started].copy()

    # A finished match is a whole fixture whatever minutes it recorded --
    # an abandoned or shortened game still happened.
    share = (played["minutes"].fillna(0) / 90.0).clip(0.0, 1.0)
    share = share.where(~played["finished"].fillna(False).astype(bool), 1.0)

    both_ends = pd.concat(
        [
            pd.DataFrame({"team": played["team_h"], "share": share}),
            pd.DataFrame({"team": played["team_a"], "share": share}),
        ]
    )
    team_games = both_ends.groupby("team")["share"].sum()

    # Teams yet to kick a ball still need a row, or their players fall
    # through to the league average and look half a season in.
    all_teams = pd.concat([fixtures["team_h"], fixtures["team_a"]]).unique()
    team_games = team_games.reindex(sorted(all_teams), fill_value=0.0).astype(float)

    finished = int(events["finished"].sum()) if "finished" in events else 0

    current = None
    if "is_current" in events:
        open_now = events.loc[events["is_current"].fillna(False).astype(bool), "id"]
        current = int(open_now.iloc[0]) if len(open_now) else None

    return SeasonProgress(
        team_games=team_games,
        gameweeks_finished=finished,
        current_event=current,
    )


def infer_progress(players: pd.DataFrame) -> SeasonProgress:
    """Fall back to reading games played off the players themselves.

    Used only when the fixture list is unreachable. Someone in every squad
    has played every minute, so a team's busiest player's minutes over 90,
    rounded up, is a serviceable guess at its fixture count -- and it is
    still per team, which is the part that matters.
    """
    busiest = players.groupby("team")["minutes"].max().fillna(0).astype(float)
    team_games = (busiest / 90.0).apply(lambda games: float(math.ceil(games)))
    return SeasonProgress(team_games=team_games, is_exact=False)


def load_live_season(
    season: int = config.PREDICT_SEASON, timeout: int = 20
) -> tuple[pd.DataFrame, pd.DataFrame, SeasonProgress]:
    """Today's snapshot of the current season, shaped like a cached CSV.

    Returns ``(players, master_teams, progress)``. The players frame
    carries every column in :data:`clean.RAW_COLS` and the teams frame
    matches the ``(season, team, team_name)`` schema
    :func:`clean.clean_season` merges on, so the pair drops straight into
    the normal cleaning path with no special-casing:

        raw, teams, progress = load_live_season()
        df = clean.clean_season(raw, config.PREDICT_SEASON, teams)

    ``progress`` is the :class:`SeasonProgress` the projection page divides
    by. If the fixture list cannot be fetched, the bootstrap payload alone
    still yields a usable one via :func:`infer_progress`.
    """
    payload = load_live_bootstrap(timeout)

    players = pd.DataFrame(payload["elements"])

    teams = pd.DataFrame(payload["teams"])
    master_teams = pd.DataFrame(
        {
            "season": season,
            "team": teams["id"].astype(int),
            "team_name": teams["name"].astype(str),
        }
    )

    events = pd.DataFrame(payload["events"])

    try:
        progress = season_progress(load_live_fixtures(timeout), events)
    except Exception:  # fixtures down but bootstrap up: degrade, don't fail
        progress = infer_progress(players)
        progress.gameweeks_finished = (
            int(events["finished"].sum()) if "finished" in events else 0
        )

    return players, master_teams, progress
