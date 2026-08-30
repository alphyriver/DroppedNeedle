"""Pins the /api/v1 surface the production target application must serve.

This started life as a main-vs-target comparison, after the fork's
prowlarr/qbittorrent routers were registered in main.py but not in
target_application.py: the first boot after a library upgrade serves
target_main:app, so those endpoints 404ed until the container was restarted.

Upstream's F-NL-03 clean cutover removed main:app entirely (main.py is now an
unsupported-entrypoint guard), so there is no second app left to diff against -
the target IS the application. The broad comparison and its curated
INTENTIONAL_OMISSIONS allowlist went with it; what remains is the narrow guard
on the regression that motivated the file, which stands on its own.
"""

import re

from fastapi import FastAPI


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


def test_frontend_path_mapping_query_has_no_target_endpoint():
    """Documents a known frontend/backend mismatch rather than asserting a fix.

    LibraryPolicyQueries.svelte.ts reads /settings/library/path-mapping when the
    Library settings page loads, but the target runtime deliberately does not
    serve it. Under the target application that query 404s. This is a frontend
    bug - the query should not run on the target - not a missing route. Pinned here so the mismatch is visible and does not get
    "fixed" by mounting the route, which would break
    tests/routes/test_target_application.py::
      test_target_application_exposes_only_typed_library_root_mutations
    and tests/routes/test_target_library_policy_routes.py::
      test_target_policy_route_inventory_is_complete."""
    from target_application import create_production_target_application

    operations = _v1_operations(create_production_target_application())

    assert ("GET", "/api/v1/settings/library/path-mapping") not in operations


def test_target_app_serves_the_torrent_routes():
    """Narrow guard on the original regression: the torrent routers must be
    registered on the target app, which is what actually boots in production."""
    from target_application import create_production_target_application

    paths = {path for _, path in _v1_operations(create_production_target_application())}

    assert any("prowlarr" in p for p in paths), "prowlarr routes absent from target app"
    assert any("qbittorrent" in p for p in paths), (
        "qbittorrent routes absent from target app"
    )
