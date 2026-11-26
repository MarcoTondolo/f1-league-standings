from __future__ import annotations

import argparse
import logging
import os
import sys
import tomllib
from pathlib import Path

from f1_league.api import FantasyApi
from f1_league.build import build_payload, collect_league, fetch_race_names, write_site
from f1_league.client import AuthExpired, FantasyClient, FantasyError
from f1_league.scoring import F1_POINTS

AUTH_HELP = """\
Cookie di sessione mancante o scaduto. Per aggiornarlo:
  1. Apri https://fantasy.formula1.com e accedi.
  2. F12 -> Application -> Cookies -> https://fantasy.formula1.com
  3. Copia il valore del cookie F1_FANTASY_007 (e' il TOKEN).
  4. F12 -> Network, filtro "privateleague": nell'URL
     /services/user/league/<GUID>/... c'e' il tuo GUID.
  5. Salva i secret F1_FANTASY_TOKEN e F1_USER_GUID (GitHub: Settings ->
     Secrets and variables -> Actions; in locale: variabili d'ambiente).
Il cookie dura circa cinque giorni."""


def load_dotenv(path: str = ".env") -> bool:
    """Carica KEY=VALORE da un file .env. Le variabili gia' impostate hanno la precedenza
    (cosi' i secret di GitHub Actions non vengono mai sovrascritti)."""
    file = Path(path)
    if not file.is_file():
        return False
    for line in file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
    return True


def load_config(path: str) -> dict:
    file = Path(path)
    return tomllib.loads(file.read_text(encoding="utf-8")) if file.exists() else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-league", description=__doc__)
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--out", default="docs", help="cartella del sito (default: docs)")
    parser.add_argument("--env-file", default=".env", help="file con F1_FANTASY_TOKEN e F1_USER_GUID (default: .env)")
    parser.add_argument("--login", action="store_true", help="apre Chrome, tu accedi, e token/GUID vengono salvati in .env")
    parser.add_argument("--record-titles", action=argparse.BooleanOptionalAction, default=True, help="scrive in [titles] di config.toml i campioni certi (default: si'; --no-record-titles per disattivare)")
    parser.add_argument("--league", type=int, action="append", help="id lega (ripetibile)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    if args.login:
        from f1_league.login import LoginError, run_login

        try:
            run_login(args.env_file)
        except LoginError as exc:
            print(f"Login non riuscito: {exc}", file=sys.stderr)
            return 3
    load_dotenv(args.env_file)
    config = load_config(args.config)
    season = int(config.get("season", 2026))
    table = [float(x) for x in config.get("f1_points", F1_POINTS)]
    max_members = int(config.get("max_members", 40))
    wanted = args.league or [int(x) for x in config.get("leagues", [])]
    names = {int(k): str(v) for k, v in (config.get("race_names") or {}).items()}

    try:
        with FantasyClient(os.environ.get("F1_FANTASY_TOKEN", "").strip(), os.environ.get("F1_USER_GUID", "").strip()) as client:
            api = FantasyApi(client)
            if not wanted:
                for league in api.private_leagues():
                    if league.member_count and league.member_count > max_members:
                        logging.warning("salto '%s' (%d iscritti > max_members=%d)", league.name, league.member_count, max_members)
                    else:
                        wanted.append(league.league_id)
            if not wanted:
                print("Nessuna lega da elaborare: indica gli id in config.toml.", file=sys.stderr)
                return 1
            leagues = []
            for league_id in wanted:
                data = collect_league(api, league_id, table=table)
                logging.info("%s: %d membri, %d weekend", data["name"], len(data["members"]), len(data["races"]))
                for warning in data["warnings"]:
                    logging.warning("  ! %s", warning)
                leagues.append(data)
    except AuthExpired as exc:
        print(f"Autenticazione fallita: {exc}\n\n{AUTH_HELP}", file=sys.stderr)
        return 2
    except FantasyError as exc:
        print(f"Errore API: {exc}", file=sys.stderr)
        return 1

    race_names = {**fetch_race_names(season), **names}
    payload = build_payload(leagues, season, race_names, table, int(config.get("total_races", 0)) or None, config.get("titles"))
    for path in write_site(payload, Path(args.out)):
        logging.info("scritto %s", path)
    if args.record_titles:
        from f1_league.titles import champions_from_payload, record_titles

        for name, year, kind in record_titles(args.config, champions_from_payload(payload)):
            logging.info("titolo %d (%s) registrato in %s per %s", year, kind, args.config, name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
