"""Analisi testuale della stagione di ogni giocatore, ricavata solo dai numeri (niente ipotesi sulle cause)."""
from __future__ import annotations

import statistics
from typing import Any

MIN_WEEKENDS = 6      # sotto questa soglia non si parla di andamento
TREND_DELTA = 25      # differenza di media (fantapunti) tra seconda e prima meta' per parlare di crescita/calo


def _n(value: float) -> str:
    value = round(float(value), 1)
    return str(int(value)) if value == int(value) else str(value).replace(".", ",")


def _prep(prefix: str, n: int) -> str:
    """"al 6°", "all'8°"; "dal 6°", "dall'8°" (8, 11 e 18 vogliono l'apostrofo). prefix: "a" o "da"."""
    if n in (8, 11, 18):
        return f"{prefix}ll'{n}°"
    return f"{prefix}l {n}°"


def analyze_league(league: dict[str, Any]) -> None:
    """Aggiunge stats[chiave]["analysis"] = [frasi] a ogni giocatore della lega."""
    races, stats = league.get("races") or [], league.get("stats") or {}
    if not races:
        return
    rows: dict[str, list[dict]] = {key: [] for key in stats}
    for race in races:
        for row in race["rows"]:
            if row["key"] in rows:
                rows[row["key"]].append(row)

    facts: dict[str, dict[str, Any]] = {}
    for key, rs in rows.items():
        if not rs:
            continue
        fantasy = [r["wk_fantasy"] for r in rs]
        half = len(fantasy) // 2
        names = {r["id"]: r["name"] for r in races}
        facts[key] = {
            "fantasy": fantasy,
            "sd": statistics.pstdev(fantasy),
            "trend": statistics.mean(fantasy[half:]) - statistics.mean(fantasy[:half]) if len(fantasy) >= MIN_WEEKENDS else 0.0,
            "worst": min(fantasy),
            "worst_race": names.get(races[fantasy.index(min(fantasy))]["id"]),
            "lead": sum(1 for r in rs if r["tot_f1_pos"] == 1),
            "start": rs[0]["tot_f1_pos"],
            "end": rs[-1]["tot_f1_pos"],
            "weekends": len(rs),
        }
    if not facts:
        return

    most_wins = max(stats[k]["wins"] for k in facts)
    most_podiums = max(stats[k]["podiums"] for k in facts)
    top_best = max(stats[k]["best_fantasy"] for k in facts)
    top_sd, low_sd = max(f["sd"] for f in facts.values()), min(f["sd"] for f in facts.values())
    top_floor = max(f["worst"] for f in facts.values())
    best_trend, worst_trend = max(f["trend"] for f in facts.values()), min(f["trend"] for f in facts.values())
    by_f1 = sorted(facts, key=lambda k: stats[k]["f1"], reverse=True)
    by_fantasy = sorted(facts, key=lambda k: stats[k]["fantasy"], reverse=True)
    names_by_id = {r["id"]: r["name"] for r in races}

    for key, f in facts.items():
        s, text = stats[key], []
        # 1. Posizione nelle due classifiche
        first = f"{s['f1_pos']}° nei punti gara ({_n(s['f1'])}) e {s['fantasy_pos']}° nei fantapunti ({_n(s['fantasy'])})"
        if len(by_f1) > 1 and s["f1_pos"] == 1 and s["fantasy_pos"] == 1:
            second_f1, second_fa = stats[by_f1[1]], stats[by_fantasy[1]]
            first = (f"1° in entrambe le classifiche, con {_n(s['f1'] - second_f1['f1'])} punti gara e "
                     f"{_n(s['fantasy'] - second_fa['fantasy'])} fantapunti di vantaggio sul secondo")
        elif len(by_f1) > 1 and s["f1_pos"] == 1:
            first += f", con {_n(s['f1'] - stats[by_f1[1]]['f1'])} punti gara di vantaggio sul secondo"
        text.append(first + ".")

        # 2. Weekend vinti e podi
        if s["wins"] == 0:
            wins = "Nessun weekend vinto"
        elif s["wins"] == most_wins:
            wins = f"Più weekend vinti della lega ({s['wins']})"
        else:
            wins = f"{s['wins']} weekend {'vinto' if s['wins'] == 1 else 'vinti'}"
        podiums = f"{s['podiums']} {'podio' if s['podiums'] == 1 else 'podi'}"
        if s["podiums"] == most_podiums and s["podiums"] > 0:
            podiums += " (il record della lega)"
        text.append(f"{wins}, {podiums}.")

        # 3. Andamento tra prima e seconda meta' della stagione
        if f["weekends"] >= MIN_WEEKENDS and abs(f["trend"]) >= TREND_DELTA:
            if f["trend"] > 0:
                extra = ", il miglioramento più grande della lega" if f["trend"] == best_trend else ""
                text.append(f"In crescita nella seconda metà della stagione (+{_n(f['trend'])} fantapunti di media a weekend{extra}).")
            else:
                extra = ", il calo più forte della lega" if f["trend"] == worst_trend else ""
                text.append(f"In calo nella seconda metà della stagione ({_n(f['trend'])} fantapunti di media a weekend{extra}).")

        # 4. Regolarita'
        if f["sd"] == low_sd:
            reg = "Il più regolare della lega"
        elif f["sd"] == top_sd:
            reg = "Il più discontinuo della lega"
        else:
            reg = ""
        if f["worst"] == top_floor:
            reg = (reg + ", con " if reg else "Con ") + f"il peggior weekend più alto della lega ({_n(f['worst'])})"
        if reg:
            text.append(reg + ".")

        # 5. Percorso in classifica
        path = []
        if f["start"] - f["end"] >= 3:
            path.append(f"Risalito {_prep('da', f['start'])} posto dopo il primo weekend {_prep('a', f['end'])}")
        elif f["end"] - f["start"] >= 3:
            path.append(f"Sceso {_prep('da', f['start'])} posto dopo il primo weekend {_prep('a', f['end'])}")
        if f["lead"]:
            path.append(f"ha guidato la classifica punti gara per {f['lead']} {'weekend' if f['lead'] == 1 else 'weekend'}")
        if path:
            sentence = ", ".join(path)
            text.append(sentence[0].upper() + sentence[1:] + ".")

        # 6. Weekend migliore e peggiore
        best = f"Miglior weekend: {names_by_id.get(s['best_race'], 'Gara ' + str(s['best_race']))} ({_n(s['best_fantasy'])}"
        best += ", il migliore della lega)" if s["best_fantasy"] == top_best else ")"
        text.append(f"{best}; peggiore: {f['worst_race']} ({_n(f['worst'])}).")

        # 7. Weekend a punti gara
        if s["scoring"] < s["weekends"]:
            text.append(f"Punti gara in {s['scoring']} weekend su {s['weekends']}.")
        else:
            text.append(f"Punti gara in tutti i {s['weekends']} weekend.")
        s["analysis"] = text
