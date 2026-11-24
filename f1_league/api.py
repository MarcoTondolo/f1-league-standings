"""Endpoint usati (gli stessi verificati dal progetto f1-fantasy-reporter) e parsing tollerante."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import unquote_plus

from f1_league.client import FantasyClient, FantasyError, NotShared

log = logging.getLogger(__name__)


# -- coercioni tolleranti: l'API manda numeri come stringhe, nomi URL-encoded ------------

def first(payload: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(as_float(value, default))


def decode(value: Any) -> str:
    return "" if value is None else unquote_plus(str(value)).strip()


@dataclass
class League:
    league_id: int
    name: str
    member_count: int = 0


@dataclass
class Member:
    guid: str
    user_name: str
    team_no: int
    team_name: str
    rank: int
    points: float

    @property
    def key(self) -> str:
        return f"{self.guid}:{self.team_no}"


def parse_league_list(payload: Any) -> list[League]:
    rows: list = []
    if isinstance(payload, Mapping):
        for key in ("Details", "leaguesdata", "leagues", "Leagues", "value", "Value"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
    elif isinstance(payload, list):
        rows = payload
    out: list[League] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if "isJoined" in row and not as_int(row.get("isJoined")):
            continue  # leghe promozionali di F1
        league_id = as_int(first(row, "leagueId", "leagueid", "id"))
        if league_id:
            out.append(
                League(
                    league_id,
                    decode(first(row, "leagueName", "leaguename", "name")),
                    as_int(first(row, "memberCount", "memeberCount", "memCount", "membercount")),
                )
            )
    return out


def parse_leaderboard(payload: Any) -> tuple[League, list[Member]]:
    if not isinstance(payload, Mapping):
        payload = payload[0] if isinstance(payload, list) and payload else {}
    info = payload.get("leagueInfo") or {}
    league = League(
        as_int(first(info, "leagueid", "leagueId")),
        decode(first(info, "leagueName", "leaguename")),
        as_int(first(info, "memCount")),
    )
    rows = payload.get("memRank") or payload.get("userRank") or []
    members = [
        Member(
            guid=str(first(r, "guid", default="")).strip(),
            user_name=decode(first(r, "userName", "username")),
            team_no=as_int(first(r, "teamNo", "teamno"), default=1),
            team_name=decode(first(r, "teamName", "teamname")),
            rank=as_int(first(r, "rank")),
            points=as_float(first(r, "ovPoints", "ovpoints")),
        )
        for r in rows
        if isinstance(r, Mapping)
    ]
    members = [m for m in members if m.guid]
    members.sort(key=lambda m: (m.rank or 10**6, -m.points))
    return league, members


def parse_game_days(payload: Any) -> dict[int, float]:
    """Punti per gara (id gara -> fantapunti) da una risposta "gameday".

    Due forme confermate: lista di un elemento (proprio account) oppure dict
    diretto (altri membri). ``mddetails`` copre tutte le gare giocate.
    """
    head: Mapping[str, Any] = {}
    if isinstance(payload, Mapping):
        entries = payload.get("data") or payload.get("Value")
        if isinstance(entries, list) and entries and isinstance(entries[0], Mapping):
            head = entries[0]
        elif isinstance(entries, Mapping):
            head = entries
        elif "data" not in payload and "Value" not in payload:
            head = payload
    elif isinstance(payload, list) and payload and isinstance(payload[0], Mapping):
        head = payload[0]
    details = first(head, "mddetails", "mdDetails") or {}
    points: dict[int, float] = {}
    for race_key, detail in details.items():
        race_id = as_int(race_key)
        if not race_id:
            continue
        value = first(detail, "pts", "points") if isinstance(detail, Mapping) else detail
        if value is not None:
            points[race_id] = as_float(value)
    return points


def is_own_account(member_guid: str, own_guid: str) -> bool:
    """Le righe della classifica usano ``<uuid>-0-<n>``: si confronta per prefisso."""
    return member_guid == own_guid or member_guid.startswith(own_guid)


class FantasyApi:
    def __init__(self, client: FantasyClient) -> None:
        self.client = client

    @property
    def guid(self) -> str:
        return self.client.guid

    def private_leagues(self) -> list[League]:
        return parse_league_list(self.client.get(f"/services/user/league/{self.guid}/1/0/0/privateleague"))

    def leaderboard(self, league_id: int) -> tuple[League, list[Member]]:
        path = f"/services/user/leaderboard/{self.guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/1000/"
        return parse_leaderboard(self.client.get(path))

    def own_game_days(self) -> dict[int, float]:
        return parse_game_days(self.client.get(f"/services/user/gameplay/{self.guid}/getusergamedaysv1/1"))

    def opponent_game_days(self, guid: str, team_no: int) -> dict[int, float]:
        return parse_game_days(
            self.client.get(f"/services/user/opponentteam/opponentgamedayget/1/{guid}/{team_no}")
        )
