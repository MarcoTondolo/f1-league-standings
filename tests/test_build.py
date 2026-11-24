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
