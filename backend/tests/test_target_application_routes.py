"""The production target application must expose the same /api/v1 surface as the
normal app, except where it deliberately swaps in a target-specific variant.

This pins the invariant that was violated when the fork's prowlarr/qbittorrent
routers were registered in main.py but not in target_application.py: the first
boot after a library upgrade serves target_main:app, so those endpoints 404ed
until the container was restarted.

Comparison is on (method, parameter-normalised path). Comparing raw paths is
wrong - main declares /library/albums/{mbid}/rescan while the target declares
/library/albums/{album_id}/rescan, which is the *same* URL shape and matches the
same requests. An earlier version of this test compared raw strings and so
reported five phantom gaps while hiding real ones.
"""

import re

from fastapi import FastAPI

# Operations the target application is expected NOT to serve, as
# (method, normalised path). Each entry is an intentional divergence, not an
# oversight - add only with a reason.
#
# The target runtime replaces the mbid-keyed browse surface with
# library_target/library_scan_target equivalents: album collections are keyed by
# {album_id} and scan progress is exposed as /library/scan-runs/* rather than
# /library/scan/*. Those are shape-compatible swaps and do not appear here; only
# endpoints with no target counterpart at all do.
INTENTIONAL_OMISSIONS: frozenset[tuple[str, str]] = frozenset(
    {
        # Legacy aggregate browse endpoints; superseded by /library/albums,
        # /library/artists and /library/recently-added on the target.
        ("GET", "/api/v1/library/"),
        ("GET", "/api/v1/library/grouped"),
        # Legacy scan progress; the target exposes /library/scan-runs/* instead.
        ("GET", "/api/v1/library/scan/stream"),
        ("GET", "/api/v1/library/scan/unmatched"),
        ("POST", "/api/v1/library/scan/unmatched/resolve-batch"),
        ("POST", "/api/v1/library/scan/unmatched/{}/resolve"),
        # Legacy one-shot sync; the target scans via /library/scan-runs.
        ("POST", "/api/v1/library/sync"),
        # Renamed on the target: main serves the library settings document at
        # /settings/library/roots, the target at /settings/library (bare). Same
        # LibrarySettingsResponse, same service call. The frontend's
        # API.library.typedSettings constant still points at /roots but is dead
        # code - nothing calls it.
        ("GET", "/api/v1/settings/library/roots"),
        ("PUT", "/api/v1/settings/library/roots"),
        # Superseded by PUT /settings/library, which writes the whole settings
        # document including roots. API.library.addPath / removePath are dead
        # constants - nothing calls them either.
        ("POST", "/api/v1/settings/library/paths"),
        ("DELETE", "/api/v1/settings/library/paths"),
        # Deliberately absent, and pinned as such by
        # tests/routes/test_target_application.py::
        #   test_target_application_exposes_only_typed_library_root_mutations
        # and tests/routes/test_target_library_policy_routes.py::
        #   test_target_policy_route_inventory_is_complete.
        # Path mapping is a migration-time concern (v1 paths -> v2 roots); once
        # the target runtime is serving, the mapping has already happened. Do not
        # add it here without changing those two tests first - they are the
        # authority on this boundary.
        ("GET", "/api/v1/settings/library/path-mapping"),
    }
)


def _normalise(path: str) -> str:
    """Collapse path parameters so {mbid} and {album_id} compare equal."""
    return re.sub(r"\{[^}]+\}", "{}", path)


def _v1_operations(app: FastAPI) -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1"):
            continue
        for method in getattr(route, "methods", None) or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            operations.add((method, _normalise(path)))
    return operations


def test_target_app_exposes_every_v1_operation_main_does():
    from main import app as main_app
    from target_application import create_production_target_application

    missing = _v1_operations(main_app) - _v1_operations(
        create_production_target_application()
    )
    unexpected = missing - INTENTIONAL_OMISSIONS

    assert not unexpected, (
        "target application is missing v1 operations that main serves: "
        f"{sorted(unexpected)}"
    )


def test_frontend_path_mapping_query_has_no_target_endpoint():
    """Documents a known frontend/backend mismatch rather than asserting a fix.

    LibraryPolicyQueries.svelte.ts reads /settings/library/path-mapping when the
    Library settings page loads, but the target runtime deliberately does not
    serve it (see INTENTIONAL_OMISSIONS). Under the target application that query
    404s. This is a frontend bug - the query should not run on the target - not a
    missing route. Pinned here so the mismatch is visible and does not get
    "fixed" by mounting the route, which would break the two upstream tests
    named in INTENTIONAL_OMISSIONS."""
    from target_application import create_production_target_application

    operations = _v1_operations(create_production_target_application())

    assert ("GET", "/api/v1/settings/library/path-mapping") not in operations


def test_target_app_serves_the_torrent_routes():
    """Narrow guard on the original regression, in case the broad check above
    ever grows an allowlist entry that would hide it."""
    from target_application import create_production_target_application

    paths = {path for _, path in _v1_operations(create_production_target_application())}

    assert any("prowlarr" in p for p in paths), "prowlarr routes absent from target app"
    assert any("qbittorrent" in p for p in paths), (
        "qbittorrent routes absent from target app"
    )
