"""Raccolta dati di una lega e generazione di ``docs/index.html`` (+ JSON)."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from f1_league.api import FantasyApi, is_own_account
from f1_league.client import AuthExpired, FantasyError, NotShared
from f1_league.scoring import F1_POINTS, build_season, mathematical_champion, season_stats

log = logging.getLogger(__name__)

REQUEST_SPACING_SECONDS = 0.4
CALENDAR_URL = "https://api.jolpi.ca/ergast/f1/{season}.json?limit=100"
TEMPLATE = Path(__file__).with_name("template.html")


def collect_league(
    api: FantasyApi,
    league_id: int,
    *,
    table: Sequence[float] = F1_POINTS,
    spacing: float = REQUEST_SPACING_SECONDS,
    sleep=time.sleep,
) -> dict[str, Any]:
    """Classifiche complete di una lega, dai punti per gara di ogni membro."""
    league, members = api.leaderboard(league_id)
    warnings: list[str] = []
    own_points: dict[int, float] | None = None
    per_member: dict[str, dict[int, float]] = {}
    shown: list = []

    for index, member in enumerate(members):
        if index and spacing:
            sleep(spacing)
        try:
            if is_own_account(member.guid, api.guid):
                if own_points is None:
                    own_points = api.own_game_days()
                if member.team_no == 1:
                    points = own_points
                else:
                    points = api.opponent_game_days(api.guid, member.team_no)
                    if points == own_points:
                        warnings.append(
                            f"{member.user_name} (squadra {member.team_no}): l'API restituisce i punti "
                            "della squadra 1, squadra esclusa."
                        )
                        continue
            else:
                points = api.opponent_game_days(member.guid, member.team_no)
        except NotShared:
            warnings.append(f"{member.user_name}: punti non leggibili, escluso.")
            continue
        except AuthExpired:
            raise
        except FantasyError as exc:
            warnings.append(f"{member.user_name}: errore di lettura ({exc}), escluso.")
            continue
        if not points:
            warnings.append(f"{member.user_name}: nessun punteggio per gara, escluso.")
            continue
        per_member[member.key] = points
        shown.append(member)

    # Solo i weekend gia' punteggiati: se nessuno ha punti la gara non e' ancora disputata.
    race_ids = sorted({r for pts in per_member.values() for r in pts})
    weekend_points = {
        r: {m: pts.get(r, 0.0) for m, pts in per_member.items()} for r in race_ids
    }
    weekend_points = {r: p for r, p in weekend_points.items() if any(v != 0 for v in p.values())}

    keys = [m.key for m in shown]
    races = build_season(weekend_points, keys, table)

    if races:
        last = {row["key"]: row for row in races[-1]["rows"]}
        for m in shown:
            diff = abs(last[m.key]["tot_fantasy"] - m.points)
            if diff > 0.5:
                warnings.append(
                    f"{m.user_name}: la somma dei weekend ({last[m.key]['tot_fantasy']:g}) differisce dal "
                    f"totale ufficiale ({m.points:g}); possibili penalita' o gare non conteggiate."
                )

    return {
        "league_id": league_id,
        "name": league.name or f"Lega {league_id}",
        "members": [
            {"key": m.key, "name": m.user_name or "?", "team": m.team_name, "official": m.points}
            for m in shown
        ],
        "races": [{"id": r["race_id"], "rows": r["rows"]} for r in races],
        "stats": season_stats(races, keys),
        "warnings": warnings,
    }


def fetch_race_names(season: int, *, attempts: int = 3, sleep=time.sleep) -> dict[int, str]:
    """Nomi dei GP dal calendario Jolpica (round = id gara). Non e' mai bloccante."""
    url = CALENDAR_URL.format(season=season)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            races = payload.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            return {int(r["round"]): str(r["raceName"]).replace("Grand Prix", "GP") for r in races}
        except (OSError, ValueError, KeyError) as exc:
            log.warning("calendario non disponibile (%s), tentativo %d/%d", exc, attempt, attempts)
            if attempt < attempts:
                sleep(3 * 2 ** (attempt - 1))
    return {}


def build_payload(
    leagues: Sequence[dict],
    season: int,
    race_names: Mapping[int, str],
    table: Sequence[float],
    total_races: int | None = None,
) -> dict[str, Any]:
    total = total_races or max(race_names, default=0)
    for league in leagues:
        for race in league["races"]:
            race["name"] = race_names.get(race["id"], f"Gara {race['id']}")
        races = league["races"]
        # senza calendario noto non si puo' dire quanti weekend mancano: nessun campione.
        champion = None
        if total and races:
            champion = mathematical_champion(races[-1]["rows"], total - len(races), table)
        league["champion"] = champion
    return {
        "season": season,
        "total_races": total,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "f1_points": list(table),
        "leagues": list(leagues),
    }


def render_html(payload: Mapping[str, Any]) -> str:
    # "</" dentro <script> chiuderebbe il tag: lo si evita nel JSON incorporato.
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", data)


def write_site(payload: Mapping[str, Any], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(exist_ok=True)
    html_path = out_dir / "index.html"
    json_path = out_dir / "data" / "standings.json"
    html_path.write_text(render_html(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return [html_path, json_path]
