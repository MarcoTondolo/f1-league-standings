"""Calcolo delle due classifiche. Nessun I/O: solo numeri in, numeri out.

Classifica "fantapunti": somma dei punti fantasy di ogni weekend.
Classifica "punti gara": in ogni weekend i primi della classifica fantasy
prendono 25, 18, 15, 12, 10, 8, 6, 4, 2, 1 punti (tabella configurabile) e gli
altri 0; il totale e' la somma di questi punti.

Pareggi
-------
* Weekend: chi ha gli stessi fantapunti condivide la posizione e prende i punti
  di quella posizione (due secondi: entrambi 18, il successivo e' quarto).
* Totale fantapunti: a parita' di somma, stessa posizione.
* Totale punti gara: a parita' si guarda chi ha piu' vittorie, poi piu'
  secondi posti e cosi' via (come in F1); se e' ancora pari, i fantapunti totali;
  se anche quelli sono pari, stessa posizione.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

F1_POINTS: tuple[float, ...] = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)


def competition_ranks(keys: Sequence[tuple]) -> list[int]:
    """Posizioni 1,2,2,4 per una lista gia' ordinata di chiavi di ordinamento."""
    ranks: list[int] = []
    for index, key in enumerate(keys):
        ranks.append(ranks[-1] if index and key == keys[index - 1] else index + 1)
    return ranks


def weekend_ranking(
    points: Mapping[str, float], table: Sequence[float] = F1_POINTS
) -> dict[str, dict]:
    """Classifica di un solo weekend: ``{membro: {pos, fantasy, f1}}``."""
    ordered = sorted(points, key=lambda k: (-points[k], k))
    ranks = competition_ranks([(-points[k],) for k in ordered])
    out: dict[str, dict] = {}
    for key, pos in zip(ordered, ranks):
        f1 = float(table[pos - 1]) if pos <= len(table) else 0.0
        out[key] = {"pos": pos, "fantasy": points[key], "f1": f1}
    return out


@dataclass
class Standing:
    fantasy: float = 0.0
    f1: float = 0.0
    finishes: list[int] = field(default_factory=list)  # quante volte in posizione 1, 2, ...


def _countback(finishes: Sequence[int], depth: int) -> tuple[int, ...]:
    padded = list(finishes) + [0] * (depth - len(finishes))
    return tuple(-n for n in padded[:depth])


def build_season(
    weekend_points: Mapping[int, Mapping[str, float]],
    members: Sequence[str],
    table: Sequence[float] = F1_POINTS,
) -> list[dict]:
    """Classifiche di ogni weekend e totali progressivi.

    ``weekend_points``: id gara -> {membro: fantapunti}. I membri senza dato per
    una gara contano 0. Restituisce una voce per gara, in ordine di id, con le
    righe di tutti i membri (vedi ``README`` per i campi).
    """
    depth = len(table)
    totals = {m: Standing(finishes=[0] * depth) for m in members}
    previous_pos: dict[str, dict[str, int]] = {"fantasy": {}, "f1": {}}
    races: list[dict] = []

    for race_id in sorted(weekend_points):
        raw = {m: float(weekend_points[race_id].get(m, 0.0)) for m in members}
        wk = weekend_ranking(raw, table)
        for m in members:
            t = totals[m]
            t.fantasy += wk[m]["fantasy"]
            t.f1 += wk[m]["f1"]
            if wk[m]["pos"] <= depth:
                t.finishes[wk[m]["pos"] - 1] += 1

        fantasy_order = sorted(members, key=lambda m: (-totals[m].fantasy, m))
        fantasy_ranks = dict(
            zip(fantasy_order, competition_ranks([(-totals[m].fantasy,) for m in fantasy_order]))
        )

        def f1_key(m: str) -> tuple:
            t = totals[m]
            return (-t.f1, *_countback(t.finishes, depth), -t.fantasy)

        f1_order = sorted(members, key=lambda m: (f1_key(m), m))
        f1_ranks = dict(zip(f1_order, competition_ranks([f1_key(m) for m in f1_order])))

        rows = []
        for m in members:
            rows.append(
                {
                    "key": m,
                    "wk_fantasy": wk[m]["fantasy"],
                    "wk_pos": wk[m]["pos"],
                    "wk_f1": wk[m]["f1"],
                    "tot_fantasy": totals[m].fantasy,
                    "tot_fantasy_pos": fantasy_ranks[m],
                    "tot_fantasy_prev": previous_pos["fantasy"].get(m),
                    "tot_f1": totals[m].f1,
                    "tot_f1_pos": f1_ranks[m],
                    "tot_f1_prev": previous_pos["f1"].get(m),
                }
            )
        races.append({"race_id": race_id, "rows": rows})
        previous_pos = {"fantasy": fantasy_ranks, "f1": f1_ranks}

    return races
