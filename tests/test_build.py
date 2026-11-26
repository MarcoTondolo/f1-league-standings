import json

import httpx
import pytest

from f1_league.api import FantasyApi, parse_game_days, parse_league_list
from f1_league.build import build_payload, collect_league, render_html, write_site
from f1_league.client import AuthExpired, FantasyClient
from tests.fakeapi import OWN, handler


def make_api(h=handler):
    return FantasyApi(FantasyClient("tok", OWN, transport=httpx.MockTransport(h), sleep=lambda s: None))


def test_missing_credentials_raise_auth_expired():
    with pytest.raises(AuthExpired):
        FantasyClient("", "")


def test_html_instead_of_json_means_expired_cookie():
    api = make_api(lambda r: httpx.Response(200, text="<!DOCTYPE html><html>login</html>"))
    with pytest.raises(AuthExpired):
        api.private_leagues()


def test_promo_leagues_are_filtered():
    leagues = make_api().private_leagues()
    assert [(l.league_id, l.name) for l in leagues] == [(7, "Amici F1")]


def test_parse_game_days_shapes():
    assert parse_game_days([{"mddetails": {"1": {"pts": "5"}}}]) == {1: 5.0}
    assert parse_game_days({"mddetails": {"2": 7}}) == {2: 7.0}


def test_collect_league_end_to_end():
    data = collect_league(make_api(), 7, spacing=0)
    assert data["name"] == "Amici F1"
    assert len(data["members"]) == 3 and len(data["races"]) == 3
    r1 = {r["key"]: r for r in data["races"][0]["rows"]}
    luca = next(m["key"] for m in data["members"] if m["name"] == "Luca")
    assert r1[luca]["wk_pos"] == 1 and r1[luca]["wk_f1"] == 25
    last = {r["key"]: r for r in data["races"][-1]["rows"]}
    # fantapunti totali: Luca 350, Giulia 320, Marco 310
    assert [last[k]["tot_fantasy_pos"] for k in (luca,)] == [1]
    assert not data["warnings"]


def test_site_embeds_data_safely(tmp_path):
    data = collect_league(make_api(), 7, spacing=0)
    data["name"] = "Lega </script><b>x"
    payload = build_payload([data], 2026, {1: "Australia"}, [25, 18, 15, 12, 10, 8, 6, 4, 2, 1])
    html = render_html(payload)
    assert html.count("</script>") == 1  # solo il tag reale del template
    assert "Australia" in html and "Gara 2" in html
    paths = write_site(payload, tmp_path)
    assert all(p.exists() for p in paths)
    assert json.loads((tmp_path / "data" / "standings.json").read_text())["leagues"][0]["races"][0]["name"] == "Australia"


def test_dotenv_loads_without_overriding(tmp_path, monkeypatch):
    from f1_league.cli import load_dotenv

    env = tmp_path / ".env"
    env.write_text('# commento\nF1_FANTASY_TOKEN="abc=def"\nexport F1_USER_GUID = guid-1\nF1_ALREADY=nuovo\n', encoding="utf-8")
    monkeypatch.delenv("F1_FANTASY_TOKEN", raising=False)
    monkeypatch.delenv("F1_USER_GUID", raising=False)
    monkeypatch.setenv("F1_ALREADY", "vecchio")
    assert load_dotenv(str(env)) is True
    import os
    assert os.environ["F1_FANTASY_TOKEN"] == "abc=def"
    assert os.environ["F1_USER_GUID"] == "guid-1"
    assert os.environ["F1_ALREADY"] == "vecchio"
    assert load_dotenv(str(tmp_path / "manca")) is False


def test_collect_league_includes_stats():
    data = collect_league(make_api(), 7, spacing=0)
    assert set(data["stats"]) == {m["key"] for m in data["members"]}
    assert sum(s["wins"] for s in data["stats"].values()) >= 3


def test_payload_marks_champion_only_when_certain():
    def payload(total):
        data = collect_league(make_api(), 7, spacing=0)
        return build_payload([data], 2026, {}, [25, 18, 15, 12, 10, 8, 6, 4, 2, 1], total)["leagues"][0]

    assert payload(None)["champion"] is None   # calendario sconosciuto
    assert payload(10)["champion"] is None     # 7 weekend ancora da correre
    assert payload(3)["champion"] is not None  # stagione finita: vince il primo


def test_titles_by_kind_from_config_and_current_season(caplog):
    data = collect_league(make_api(), 7, spacing=0)
    luca = next(m["key"] for m in data["members"] if m["name"] == "Luca")
    table = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
    config = {"fantasy": {"luca": [2024]}, "f1": {"Giulia": [2025]}, "Sconosciuto": [2023]}   # ultima voce: formato vecchio
    out = build_payload([data], 2026, {}, table, 3, config)
    members = {m["name"]: m for m in out["leagues"][0]["members"]}
    # stagione finita (3 weekend su 3): Luca e' campione sia nei punti gara sia nei fantapunti
    assert members["Luca"]["titles"] == {"fantasy": [2024, 2026], "f1": [2026]}
    assert members["Giulia"]["titles"] == {"fantasy": [], "f1": [2025]}
    assert any("sconosciuto" in r.message for r in caplog.records)
    assert out["leagues"][0]["champion"] == luca == out["leagues"][0]["champion_fantasy"]


def test_fantasy_title_only_when_season_is_over():
    data = collect_league(make_api(), 7, spacing=0)
    out = build_payload([data], 2026, {}, [25, 18, 15], 10)["leagues"][0]
    assert out["champion_fantasy"] is None
    assert all(m["titles"] == {"fantasy": [], "f1": []} for m in out["members"])


def test_season_snapshot_and_archive(tmp_path):
    from f1_league.build import load_archive

    table = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
    data = collect_league(make_api(), 7, spacing=0)
    write_site(build_payload([data], 2025, {}, table), tmp_path)
    assert (tmp_path / "data" / "seasons" / "2025.json").is_file()
    # l'anno dopo: nuova stagione, quella vecchia resta e finisce nella pagina
    paths = write_site(build_payload([data], 2026, {}, table), tmp_path)
    assert (tmp_path / "data" / "seasons" / "2026.json") in paths
    assert [x["season"] for x in load_archive(tmp_path, 2026)] == [2025]
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '"archive":[{"season":2025' in html
    # stagione senza leghe (inizio anno): nessuna istantanea vuota che sovrascriva
    write_site(build_payload([], 2026, {}, table), tmp_path)
    assert json.loads((tmp_path / "data" / "seasons" / "2026.json").read_text(encoding="utf-8"))["leagues"]


def test_analysis_sentences_are_generated_for_every_member():
    data = collect_league(make_api(), 7, spacing=0)
    out = build_payload([data], 2026, {1: "GP A", 2: "GP B", 3: "GP C"}, [25, 18, 15, 12, 10, 8, 6, 4, 2, 1], 10)
    stats = out["leagues"][0]["stats"]
    assert all(s["analysis"] for s in stats.values())
    leader = next(s for s in stats.values() if s["f1_pos"] == 1)
    assert leader["analysis"][0].startswith("1° in entrambe le classifiche")
    assert any("Miglior weekend: GP" in line for line in leader["analysis"])
    assert all("None" not in line for s in stats.values() for line in s["analysis"])


def test_analysis_prepositions():
    from f1_league.analysis import _prep

    assert [_prep("da", 2), _prep("da", 8), _prep("a", 6), _prep("a", 11)] == ["dal 2°", "dall'8°", "al 6°", "all'11°"]
