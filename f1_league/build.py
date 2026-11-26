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
from f1_league.analysis import analyze_league
from f1_league.scoring import F1_POINTS, build_season, fantasy_champion, mathematical_champion, season_stats

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


TITLE_KINDS = ("fantasy", "f1")   # fantapunti, punti gara


def normalize_titles(raw: Mapping[str, Any] | None) -> dict[str, dict[str, list[int]]]:
    """Titoli da config -> {"fantasy": {nome: [anni]}, "f1": {nome: [anni]}} (nomi in minuscolo).

    Formato nuovo: tabelle [titles.fantasy] e [titles.f1]. Formato vecchio: [titles] con
    "Nome" = [anni], letto come titoli fantapunti.
    """
    out: dict[str, dict[str, list[int]]] = {kind: {} for kind in TITLE_KINDS}
    for key, value in (raw or {}).items():
        if isinstance(value, Mapping):
            kind = str(key).strip().casefold()
            if kind not in out:
                log.warning("titoli: tabella sconosciuta [titles.%s] (usa fantasy o f1)", key)
                continue
            for name, years in value.items():
                out[kind].setdefault(str(name).strip().casefold(), []).extend(int(y) for y in years)
        else:
            out["fantasy"].setdefault(str(key).strip().casefold(), []).extend(int(y) for y in value)
    return out


def build_payload(
    leagues: Sequence[dict],
    season: int,
    race_names: Mapping[int, str],
    table: Sequence[float],
    total_races: int | None = None,
    titles: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    total = total_races or max(race_names, default=0)
    wanted = normalize_titles(titles)
    for league in leagues:
        for race in league["races"]:
            race["name"] = race_names.get(race["id"], f"Gara {race['id']}")
        races = league["races"]
        # senza calendario noto non si puo' dire quanti weekend mancano: nessun campione.
        champions: dict[str, str | None] = {"fantasy": None, "f1": None}
        if total and races:
            remaining = total - len(races)
            champions["f1"] = mathematical_champion(races[-1]["rows"], remaining, table)
            champions["fantasy"] = fantasy_champion(races[-1]["rows"], remaining)
        analyze_league(league)
        league["champion"] = champions["f1"]               # campione matematico dei punti gara (nome in oro)
        league["champion_fantasy"] = champions["fantasy"]  # campione fantapunti, a stagione finita
        # titoli vinti: quelli in config (per nome) + la stagione in corso se il campione e' certo.
        matched: dict[str, set[str]] = {kind: set() for kind in TITLE_KINDS}
        for member in league["members"]:
            name = str(member["name"]).strip().casefold()
            member["titles"] = {}
            for kind in TITLE_KINDS:
                years = set(wanted[kind].get(name, ()))
                if name in wanted[kind]:
                    matched[kind].add(name)
                if champions[kind] == member["key"]:
                    years.add(season)
                member["titles"][kind] = sorted(years)
        for kind in TITLE_KINDS:
            for name in wanted[kind].keys() - matched[kind]:
                log.warning("titoli %s: nessun giocatore chiamato '%s' nella lega '%s'", kind, name, league["name"])
    return {
        "season": season,
        "total_races": total,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "f1_points": list(table),
        "leagues": list(leagues),
    }


def render_html(payload: Mapping[str, Any], archive: Sequence[Mapping[str, Any]] | None = None) -> str:
    """Pagina con la stagione corrente piu' le stagioni archiviate (selezionabili dal menu Anno)."""
    full = {**payload, "archive": list(archive or [])}
    # "</" dentro <script> chiuderebbe il tag: lo si evita nel JSON incorporato.
    data = json.dumps(full, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", data)


def load_archive(out_dir: Path, current_season: int) -> list[dict[str, Any]]:
    """Stagioni salvate in <out>/data/seasons/<anno>.json, escluse quella corrente, dalla piu' recente."""
    found: list[dict[str, Any]] = []
    for file in sorted((out_dir / "data" / "seasons").glob("*.json")):
        try:
            snap = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("archivio illeggibile, ignorato: %s", file)
            continue
        if isinstance(snap, dict) and snap.get("leagues") and int(snap.get("season", 0)) != current_season:
            snap.pop("archive", None)
            found.append(snap)
    return sorted(found, key=lambda x: int(x["season"]), reverse=True)


def write_site(payload: Mapping[str, Any], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(exist_ok=True)
    html_path = out_dir / "index.html"
    json_path = out_dir / "data" / "standings.json"
    paths = [html_path, json_path]
    # Istantanea della stagione: l'anno dopo l'API mostrera' solo la nuova stagione, questa resta.
    if payload.get("leagues"):
        season_path = out_dir / "data" / "seasons" / f"{int(payload['season'])}.json"
        season_path.parent.mkdir(parents=True, exist_ok=True)
        season_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        paths.append(season_path)
    html_path.write_text(render_html(payload, load_archive(out_dir, int(payload["season"]))), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return paths
