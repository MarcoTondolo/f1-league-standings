import json
import tomllib

from f1_league.titles import add_titles, champions_from_payload, main, record_titles

BASE = """season = 2026

# commento
[titles.fantasy]
"Marco Tondolo" = [2024]  # nota
Gianfranco = [2025]

[altro]
x = 1
"""


def test_add_new_name_and_new_year_keep_comments():
    text, added = add_titles(BASE, [("Luca Rossi", 2026, "fantasy"), ("marco tondolo", 2026, "fantasy")])
    assert len(added) == 2
    data = tomllib.loads(text)
    assert data["titles"]["fantasy"]["Luca Rossi"] == [2026]
    assert data["titles"]["fantasy"]["Marco Tondolo"] == [2024, 2026]
    assert data["altro"] == {"x": 1} and data["season"] == 2026
    assert "# commento" in text and "# nota" in text
    assert text.index("Luca Rossi") < text.index("[altro]")          # resta dentro la sua tabella


def test_kinds_are_kept_apart_and_sections_created():
    text, added = add_titles(BASE, [("Marco Tondolo", 2026, "f1")])
    data = tomllib.loads(text)
    assert data["titles"]["f1"] == {"Marco Tondolo": [2026]}
    assert data["titles"]["fantasy"]["Marco Tondolo"] == [2024]       # il fantasy non e' toccato
    text, added = add_titles("season = 2026\n", [('Mario "Max" Verdi', 2026, "f1")])
    assert tomllib.loads(text)["titles"]["f1"] == {'Mario "Max" Verdi': [2026]}


def test_idempotent():
    text, added = add_titles(BASE, [("Gianfranco", 2025, "fantasy")])
    assert added == [] and text.strip() == BASE.strip()


def test_record_titles_writes_file_and_keeps_crlf(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(BASE.replace("\n", "\r\n").encode())
    assert record_titles(path, [("Luca", 2026, "f1")]) == [("Luca", 2026, "f1")]
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    assert tomllib.loads(path.read_text(encoding="utf-8"))["titles"]["f1"]["Luca"] == [2026]
    assert record_titles(path, [("Luca", 2026, "f1")]) == []


def test_champions_from_payload_and_cli(tmp_path, capsys):
    payload = {"season": 2026, "leagues": [
        {"champion": "k1", "champion_fantasy": "k2",
         "members": [{"key": "k1", "name": "Luca"}, {"key": "k2", "name": "Giulia"}]},
        {"champion": None, "members": [{"key": "k9", "name": "Anna"}]},
    ]}
    assert sorted(champions_from_payload(payload)) == [("Giulia", 2026, "fantasy"), ("Luca", 2026, "f1")]
    data = tmp_path / "s.json"; data.write_text(json.dumps(payload))
    cfg = tmp_path / "c.toml"; cfg.write_text("season = 2026\n")
    assert main(["--data", str(data), "--config", str(cfg)]) == 0
    titles = tomllib.loads(cfg.read_text())["titles"]
    assert titles == {"f1": {"Luca": [2026]}, "fantasy": {"Giulia": [2026]}}
    assert "Luca" in capsys.readouterr().out
