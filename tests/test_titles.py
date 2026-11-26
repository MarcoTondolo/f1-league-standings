import json
import tomllib

from f1_league.titles import add_titles, champions_from_payload, main, record_titles

BASE = """season = 2026

# commento
[titles]
"Marco Tondolo" = [2024]  # nota
Gianfranco = [2025]

[altro]
x = 1
"""


def test_add_new_name_and_new_year_keep_comments():
    text, added = add_titles(BASE, [("Luca Rossi", 2026), ("marco tondolo", 2026)])
    assert added == [("Luca Rossi", 2026), ("marco tondolo", 2026)]
    data = tomllib.loads(text)
    assert data["titles"]["Luca Rossi"] == [2026]
    assert data["titles"]["Marco Tondolo"] == [2024, 2026]
    assert data["altro"] == {"x": 1} and data["season"] == 2026
    assert "# commento" in text and "# nota" in text
    assert text.index("Luca Rossi") < text.index("[altro]")          # resta dentro [titles]


def test_idempotent_and_creates_section():
    text, added = add_titles(BASE, [("Gianfranco", 2025)])
    assert added == [] and text.strip() == BASE.strip()
    text, added = add_titles("season = 2026\n", [('Mario "Max" Verdi', 2026)])
    assert tomllib.loads(text)["titles"] == {'Mario "Max" Verdi': [2026]}


def test_record_titles_writes_file_and_keeps_crlf(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(BASE.replace("\n", "\r\n").encode())
    assert record_titles(path, [("Luca", 2026)]) == [("Luca", 2026)]
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    assert tomllib.loads(path.read_text(encoding="utf-8"))["titles"]["Luca"] == [2026]
    assert record_titles(path, [("Luca", 2026)]) == []


def test_champions_from_payload_and_cli(tmp_path, capsys):
    payload = {"season": 2026, "leagues": [
        {"champion": "k1", "members": [{"key": "k1", "name": "Luca"}, {"key": "k2", "name": "Giulia"}]},
        {"champion": None, "members": [{"key": "k9", "name": "Anna"}]},
    ]}
    assert champions_from_payload(payload) == [("Luca", 2026)]
    data = tmp_path / "s.json"; data.write_text(json.dumps(payload))
    cfg = tmp_path / "c.toml"; cfg.write_text("season = 2026\n")
    assert main(["--data", str(data), "--config", str(cfg)]) == 0
    assert tomllib.loads(cfg.read_text())["titles"] == {"Luca": [2026]}
    assert "Luca" in capsys.readouterr().out
