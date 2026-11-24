"""API F1 Fantasy simulata con httpx.MockTransport, per i test."""
import json
from urllib.parse import quote_plus

import httpx

OWN = "11111111-aaaa-bbbb-cccc-000000000001"
OTHERS = {
    "22222222-aaaa-bbbb-cccc-000000000002": ("Luca", "Rosso+Corsa", {1: 120.0, 2: 90.0, 3: 140.0}),
    "33333333-aaaa-bbbb-cccc-000000000003": ("Giulia", "Pit%20Stop", {1: 100.0, 2: 130.0, 3: 90.0}),
}
OWN_POINTS = {1: 110.0, 2: 100.0, 3: 100.0}


def _days(points):
    return {"Data": {"Value": {"mddetails": {str(r): {"pts": str(p)} for r, p in points.items()}}}}


def handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["cookie"].startswith("F1_FANTASY_007=")
    path = request.url.path
    if path.endswith("/privateleague"):
        return httpx.Response(200, json={"Data": {"Value": {"Details": [
            {"leagueId": 7, "leagueName": "Amici+F1", "isJoined": 1, "memberCount": 3},
            {"leagueId": 99, "leagueName": "Promo", "isJoined": 0},
        ]}}})
    if "pvtleagueuserrankget" in path:
        rows = [{"guid": f"{OWN}-0-1", "userName": "Marco", "teamNo": 1, "teamName": "Scuderia+Marco", "rank": 2, "ovPoints": "310"}]
        for i, (guid, (name, team, pts)) in enumerate(OTHERS.items()):
            rows.append({"guid": f"{guid}-0-1", "userName": name, "teamNo": 1, "teamName": team, "rank": 1 + i * 2, "ovPoints": str(sum(pts.values()))})
        return httpx.Response(200, json={"Data": {"Value": {"leagueInfo": {"leagueid": 7, "leagueName": "Amici+F1", "memCount": 3}, "memRank": rows}}})
    if path.endswith("/getusergamedaysv1/1"):
        return httpx.Response(200, json={"Data": {"Value": [{"mddetails": {str(r): {"pts": p} for r, p in OWN_POINTS.items()}}]}})
    if "opponentgamedayget" in path:
        guid = path.rstrip("/").split("/")[-2]
        return httpx.Response(200, json=_days(OTHERS[guid.split("-0-")[0]][2]))
    return httpx.Response(404, text="nope")
