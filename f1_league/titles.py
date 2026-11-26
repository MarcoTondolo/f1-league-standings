"""Registra nel config.toml i campionati vinti.

Quando un campione e' certo il suo nome viene aggiunto, con l'anno della stagione, a config.toml:
tabella ``[titles.f1]`` per i punti gara (campione matematico) e ``[titles.fantasy]`` per i fantapunti
(a stagione finita). Cosi' il titolo resta
anche l'anno dopo, quando la nuova stagione non ha ancora un campione.

Uso da solo:   py -m f1_league.titles                (legge docs/data/standings.json)
Oppure:        py -m f1_league --record-titles       (subito dopo la build)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable, Mapping

_LINE = re.compile(
    r'^(?P<lead>\s*)(?P<key>"(?:[^"\\]|\\.)*"|[A-Za-z0-9_-]+)(?P<eq>\s*=\s*)\[(?P<years>[^\]]*)\](?P<tail>.*)$'
)
_TABLE = re.compile(r"^\s*\[[^\[\]]+\]\s*(#.*)?$")


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unquote(key: str) -> str:
    return json.loads(key) if key.startswith('"') else key


FIELDS = {"f1": "champion", "fantasy": "champion_fantasy"}


def champions_from_payload(payload: Mapping[str, Any]) -> list[tuple[str, int, str]]:
    """(nome, anno, tipo) dei campioni certi presenti nel payload; tipo = "f1" o "fantasy"."""
    season = int(payload["season"])
    found: list[tuple[str, int, str]] = []
    for league in payload.get("leagues", []):
        for kind, field in FIELDS.items():
            key = league.get(field)
            for member in league.get("members", []):
                if key and member.get("key") == key and member.get("name") not in (None, "", "?"):
                    found.append((str(member["name"]), season, kind))
    return found


def add_titles(
    text: str, entries: Iterable[tuple[str, int, str]]
) -> tuple[str, list[tuple[str, int, str]]]:
    """Aggiunge (nome, anno, tipo) alla tabella [titles.<tipo>] del testo TOML, senza toccare il resto.

    Restituisce il nuovo testo e le coppie davvero aggiunte (quelle gia' presenti sono ignorate).
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    added: list[tuple[str, int, str]] = []

    def table_bounds(kind: str) -> tuple[int, int] | None:
        header = re.compile(rf"^\s*\[titles\.{re.escape(kind)}\]\s*(#.*)?$")
        start = next((i for i, l in enumerate(lines) if header.match(l)), None)
        if start is None:
            return None
        end = next((i for i in range(start + 1, len(lines)) if _TABLE.match(lines[i])), len(lines))
        return start, end

    for name, year, kind in entries:
        bounds = table_bounds(kind)
        if bounds is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines += [f"[titles.{kind}]"]
            bounds = table_bounds(kind)
        start, end = bounds  # type: ignore[misc]
        for i in range(start + 1, end):
            m = _LINE.match(lines[i])
            if m and _unquote(m["key"]).strip().casefold() == name.strip().casefold():
                years = {int(y) for y in re.findall(r"\d{4}", m["years"])}
                if year in years:
                    break
                years.add(year)
                lines[i] = f'{m["lead"]}{m["key"]}{m["eq"]}[{", ".join(map(str, sorted(years)))}]{m["tail"]}'
                added.append((name, year, kind))
                break
        else:
            last = end
            while last > start + 1 and not lines[last - 1].strip():
                last -= 1
            lines.insert(last, f"{_quote(name)} = [{year}]")
            added.append((name, year, kind))
    return newline.join(lines) + newline, added


def record_titles(config_path: str | Path, entries: Iterable[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    """Scrive i titoli nel file TOML. Se il risultato non fosse un TOML valido non scrive nulla."""
    path = Path(config_path)
    entries = list(entries)
    if not entries:
        return []
    original = path.read_bytes().decode("utf-8") if path.exists() else ""
    updated, added = add_titles(original, entries)
    if not added:
        return []
    tomllib.loads(updated)  # ValueError se abbiamo rotto il file: meglio non scrivere
    path.write_text(updated, encoding="utf-8", newline="")
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-league-titles", description=__doc__.split("\n")[0])
    parser.add_argument("--data", default="docs/data/standings.json")
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args(argv)
    data = Path(args.data)
    if not data.is_file():
        print(f"{data} non esiste: lancia prima la build.", file=sys.stderr)
        return 1
    payload = json.loads(data.read_text(encoding="utf-8"))
    champions = champions_from_payload(payload)
    if not champions:
        print("Nessun campione matematico per ora.")
        return 0
    added = record_titles(args.config, champions)
    for name, year, kind in added:
        print(f"Titolo {year} ({'fantapunti' if kind == 'fantasy' else 'punti gara'}) registrato per {name}")
    if not added:
        print("Titoli gia' registrati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
