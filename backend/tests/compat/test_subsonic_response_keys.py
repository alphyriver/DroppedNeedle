"""Pins the endpoint -> response-element contract for the Subsonic shim.

Subsonic names the wrapper element after the endpoint ("getAlbumList2" ->
"albumList2") everywhere except getAlbumInfo2, which wraps its payload in
"albumInfo". Clients index that key directly -- Music Assistant does
response["subsonic-response"]["albumInfo"] and raises KeyError on a mismatch --
so a wrong wrapper breaks real clients while the status code still reads "ok"
and nothing in our own test suite notices.

These cases pin the convention *and* its one exception so a future endpoint
can't quietly regress either.
"""

import json

import pytest

from api.compat.subsonic.ids import encode
from tests.compat.conftest import subsonic_query


def _body(response):
    return json.loads(response.content)["subsonic-response"]


# (endpoint, extra params, expected wrapper element)
# "album_id"/"artist_id" are placeholders resolved against the seeded library.
_CASES = [
    ("getAlbumInfo", {"id": "album_id"}, "albumInfo"),
    # The exception: NOT "albumInfo2".
    ("getAlbumInfo2", {"id": "album_id"}, "albumInfo"),
    ("getArtistInfo", {"id": "artist_id"}, "artistInfo"),
    ("getArtistInfo2", {"id": "artist_id"}, "artistInfo2"),
    ("getAlbumList", {"type": "alphabeticalByName"}, "albumList"),
    ("getAlbumList2", {"type": "alphabeticalByName"}, "albumList2"),
    ("getStarred", {}, "starred"),
    ("getStarred2", {}, "starred2"),
    ("search2", {"query": "a"}, "searchResult2"),
    ("search3", {"query": "a"}, "searchResult3"),
]


@pytest.mark.asyncio
async def test_response_wrapper_element_matches_subsonic_contract(compat_env):
    query = subsonic_query(compat_env.secret, "alice")
    artists, _ = await compat_env.view.get_artists()
    placeholders = {
        "album_id": encode("album", compat_env.ids["rg"]),
        "artist_id": encode("artist", artists[0].artist_mbid),
    }

    mismatches = []
    for endpoint, extra, expected_key in _CASES:
        params = {
            key: placeholders.get(value, value) for key, value in extra.items()
        }
        body = _body(
            compat_env.client.get(
                f"/subsonic/rest/{endpoint}", params={**query, **params}
            )
        )
        if body.get("status") != "ok":
            mismatches.append(f"{endpoint}: status={body.get('status')} {body!r}")
        elif expected_key not in body:
            present = sorted(k for k in body if k not in {
                "status", "version", "type", "serverVersion", "openSubsonic",
            })
            mismatches.append(
                f"{endpoint}: expected wrapper {expected_key!r}, got {present}"
            )

    assert not mismatches, "Subsonic wrapper element mismatches:\n" + "\n".join(
        mismatches
    )
