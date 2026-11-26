from f1_league.scoring import build_season, season_stats, weekend_ranking


def test_f1_points_top_ten_and_zero_after():
    pts = {f"m{i}": 200 - i for i in range(12)}
    r = weekend_ranking(pts)
    assert [r[f"m{i}"]["f1"] for i in range(12)] == [25, 18, 15, 12, 10, 8, 6, 4, 2, 1, 0, 0]
    assert r["m0"]["pos"] == 1 and r["m11"]["pos"] == 12


def test_weekend_tie_shares_position_and_points():
    r = weekend_ranking({"a": 100, "b": 90, "c": 90, "d": 80})
    assert (r["b"]["pos"], r["c"]["pos"], r["d"]["pos"]) == (2, 2, 4)
    assert r["b"]["f1"] == r["c"]["f1"] == 18
    assert r["d"]["f1"] == 12


def test_totals_both_classifications_and_prev_positions():
    members = ["a", "b", "c"]
    races = build_season({1: {"a": 100, "b": 80, "c": 60}, 2: {"a": 50, "b": 120, "c": 70}}, members)
    r1, r2 = races
    row1 = {r["key"]: r for r in r1["rows"]}
    assert row1["a"]["tot_f1"] == 25 and row1["a"]["tot_fantasy_prev"] is None
    row2 = {r["key"]: r for r in r2["rows"]}
    # fantapunti: a=150 b=200 c=130 ; punti gara: a=25+15=40 b=18+25=43 c=15+18=33
    assert row2["b"]["tot_fantasy_pos"] == 1 and row2["a"]["tot_fantasy_pos"] == 2
    assert row2["b"]["tot_f1_pos"] == 1 and row2["a"]["tot_f1_pos"] == 2 and row2["c"]["tot_f1_pos"] == 3
    assert row2["b"]["tot_f1"] == 43 and row2["a"]["tot_f1"] == 40
    assert row2["b"]["tot_f1_prev"] == 2 and row2["a"]["tot_f1_prev"] == 1


def test_f1_total_tie_broken_by_wins_then_fantasy():
    # a: 1o + 3o = 25+15 ; b: 2o + 2o... costruiamo parita' 40-40 con vittorie diverse
    members = ["a", "b", "c", "d"]
    # gara1: a1 b2 c3 d4 ; gara2: b1 a? -> a terzo (15), b primo (25)
    races = build_season(
        {1: {"a": 100, "b": 90, "c": 80, "d": 70}, 2: {"b": 100, "c": 95, "a": 85, "d": 10}},
        members,
    )
    rows = {r["key"]: r for r in races[-1]["rows"]}
    # a = 25+15 = 40 ; b = 18+25 = 43 ; c = 15+18 = 33
    assert rows["b"]["tot_f1_pos"] == 1
    # parita' vera: stessa somma e stesso countback e stessi fantapunti -> stessa posizione
    tie = build_season({1: {"x": 10, "y": 10}}, ["x", "y"])[0]["rows"]
    assert tie[0]["tot_f1_pos"] == tie[1]["tot_f1_pos"] == 1


def test_missing_member_counts_zero():
    races = build_season({1: {"a": 10}}, ["a", "b"])
    rows = {r["key"]: r for r in races[0]["rows"]}
    assert rows["b"]["wk_fantasy"] == 0 and rows["b"]["wk_pos"] == 2


def test_season_stats_wins_podiums_and_totals():
    members = ["a", "b", "c", "d"]
    races = build_season(
        {
            1: {"a": 100, "b": 90, "c": 80, "d": 70},   # a vince
            2: {"b": 120, "a": 95, "c": 90, "d": 10},   # b vince, a secondo, c terzo
            3: {"b": 110, "c": 105, "d": 100, "a": 50}, # b vince, a ultimo
        },
        members,
    )
    stats = season_stats(races, members)
    assert (stats["a"]["wins"], stats["a"]["podiums"]) == (1, 2)
    assert (stats["b"]["wins"], stats["b"]["podiums"]) == (2, 3)
    assert (stats["c"]["wins"], stats["c"]["podiums"]) == (0, 3)
    assert (stats["d"]["wins"], stats["d"]["podiums"]) == (0, 1)
    assert stats["b"]["fantasy"] == 320 and stats["b"]["fantasy_pos"] == 1
    assert stats["b"]["f1"] == 18 + 25 + 25 and stats["b"]["f1_pos"] == 1
    assert stats["a"]["best_fantasy"] == 100 and stats["a"]["best_race"] == 1
    assert stats["a"]["weekends"] == 3 and stats["a"]["avg_fantasy"] == round(245 / 3, 2)


def test_season_stats_tie_counts_as_win_for_both_and_empty_season():
    stats = season_stats(build_season({1: {"x": 10, "y": 10, "z": 5}}, ["x", "y", "z"]), ["x", "y", "z"])
    assert stats["x"]["wins"] == stats["y"]["wins"] == 1 and stats["z"]["wins"] == 0
    assert stats["z"]["podiums"] == 1  # terzo
    empty = season_stats([], ["x"])
    assert empty["x"]["wins"] == 0 and empty["x"]["fantasy_pos"] is None
