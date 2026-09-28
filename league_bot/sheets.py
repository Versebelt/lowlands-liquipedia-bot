"""Read-only client for the public Lowlands League spreadsheet."""

from __future__ import annotations

import csv
import io
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable

DEFAULT_SPREADSHEET_ID = "15lCX6ljpsGh6bwzHZcctb24DIn-r4wqRGt6gZtLE_k4"


class SheetError(RuntimeError):
    """Raised when public sheet data cannot be loaded or interpreted."""


def normalized(value: object) -> str:
    return str(value or "").strip().casefold()


def number(value: object) -> float:
    raw = str(value or "").strip().replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def display_number(value: object) -> str:
    parsed = number(value)
    return f"{parsed:,.0f}" if parsed.is_integer() else f"{parsed:,.1f}"


def first_value(row: dict[str, str], names: Iterable[str], default: str = "") -> str:
    lookup = {normalized(key): value for key, value in row.items()}
    for name in names:
        if normalized(name) in lookup:
            return str(lookup[normalized(name)] or "").strip()
    return default


@dataclass
class PublicSheet:
    spreadsheet_id: str = DEFAULT_SPREADSHEET_ID
    cache_seconds: int = 120

    def __post_init__(self) -> None:
        self._cache: dict[str, tuple[float, list[dict[str, str]]]] = {}

    def rows(self, tab: str) -> list[dict[str, str]]:
        cached = self._cache.get(tab)
        if cached and time.monotonic() - cached[0] < self.cache_seconds:
            return cached[1]
        query = urllib.parse.urlencode({"tqx": "out:csv", "sheet": tab})
        url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/gviz/tq?{query}"
        request = urllib.request.Request(url, headers={"User-Agent": "Lowlands-League-Bot/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                text = response.read().decode("utf-8-sig")
        except Exception as exc:
            raise SheetError(f"Could not load the {tab} tab: {exc}") from exc
        rows = [dict(row) for row in csv.DictReader(io.StringIO(text))]
        if not rows:
            raise SheetError(f"The {tab} tab returned no rows.")
        self._cache[tab] = (time.monotonic(), rows)
        return rows

    def standings(self) -> list[dict[str, str]]:
        rows = []
        for source in self.rows("Standings"):
            player = first_value(source, ("Player", "Name"))
            rank = first_value(source, ("Rank", "#"))
            if not player or not rank:
                continue
            rows.append({
                "rank": rank,
                "player": player,
                "country": first_value(source, ("Country",)),
                "points": first_value(source, ("League Points", "Points", "Total"), "0"),
                "weeks": first_value(source, ("Weeks Played", "Weeks"), "0"),
                "moving": first_value(source, ("Moving",), "0"),
                "nm": first_value(source, ("NM",), "0"),
                "nmpz": first_value(source, ("NMPZ",), "0"),
                "playoffs": first_value(source, ("Playoffs",)),
            })
        return rows

    def player(self, query: str) -> dict[str, str] | None:
        needle = normalized(query)
        exact = [row for row in self.standings() if normalized(row["player"]) == needle]
        if exact:
            return exact[0]
        partial = [row for row in self.standings() if needle in normalized(row["player"])]
        return partial[0] if len(partial) == 1 else None

    def player_stats(self, query: str) -> dict[str, str] | None:
        rows = []
        for source in self.rows("Player Stats"):
            player = first_value(source, ("Player", "Name"))
            if not player:
                continue
            rows.append({
                "rank": first_value(source, ("Player Stats Rank", "Rank")),
                "player": player,
                "country": first_value(source, ("Country",)),
                "status": first_value(source, ("Status",)),
                "points": first_value(source, ("League Points",)),
                "weeks": first_value(source, ("Weeks",)),
                "average": first_value(source, ("Average / Week",)),
                "last_three": first_value(source, ("Last 3",)),
                "consistency": first_value(source, ("Consistency",)),
                "best_week": first_value(source, ("Best Week",)),
                "worst_week": first_value(source, ("Worst Week",)),
                "best_mode": first_value(source, ("Best Mode",)),
                "cutoff_gap": first_value(source, ("Cutoff Gap",)),
                "streak": first_value(source, ("Top-16 Streak",)),
                "weekly": [first_value(source, (f"Week {week}",)) for week in range(1, 11)],
            })
        needle = normalized(query)
        exact = [row for row in rows if normalized(row["player"]) == needle]
        if exact:
            return exact[0]
        partial = [row for row in rows if needle in normalized(row["player"])]
        return partial[0] if len(partial) == 1 else None

    def mode_leaderboard(self, mode: str) -> list[dict[str, str]]:
        key = normalized(mode)
        if key not in {"moving", "nm", "nmpz"}:
            return []
        return sorted(self.standings(), key=lambda row: number(row[key]), reverse=True)

    def week(self, week: int) -> list[dict[str, str]]:
        result = []
        for source in self.rows("Challenges"):
            if int(number(first_value(source, ("Week",)))) != week:
                continue
            result.append({
                "number": first_value(source, ("Challenge #", "Challenge")),
                "mode": first_value(source, ("Mode",)),
                "map": first_value(source, ("Map",)),
                "deadline": first_value(source, ("Deadline",)),
                "status": first_value(source, ("Status",)),
                "url": first_value(source, ("Challenge URL", "URL", "Link")),
            })
        return result
