"""The role-level search-indexer selectors.

Each acquisition protocol binds to a *role* - "the usenet indexer", "the torrent
indexer" - rather than to a named vendor, so adding or swapping a provider is a
change to one selector instead of every orchestrator construction site.

``get_torrent_search_indexer`` was added to close an asymmetry: usenet already
went through a selector while torrent was bound directly to
``get_prowlarr_indexer``, which made Prowlarr the only torrent source that could
ever exist.
"""

from unittest.mock import patch

from core.dependencies import (
    get_newznab_indexer,
    get_prowlarr_indexer,
    get_torrent_search_indexer,
    get_torznab_indexer,
    get_usenet_search_indexer,
)


def _preferences(*, prowlarr_configured: bool):
    """Patch the preferences service the selectors read.

    ``auto_retry_base_interval_minutes`` must be a real number - the indexer
    builders derive a search-cache TTL from it and a bare MagicMock fails the
    float comparison.
    """
    patcher = patch("core.dependencies.repo_providers.get_preferences_service")
    preferences = patcher.start()
    preferences.return_value.is_prowlarr_configured.return_value = prowlarr_configured
    preferences.return_value.get_download_policy.return_value.auto_retry_base_interval_minutes = 10
    return patcher


def test_torrent_selector_prefers_prowlarr_when_configured():
    """A configured Prowlarr already aggregates the user's trackers, so fanning
    out over separate Torznab rows as well would double-search them."""
    patcher = _preferences(prowlarr_configured=True)
    try:
        assert get_torrent_search_indexer() is get_prowlarr_indexer()
    finally:
        patcher.stop()


def test_torrent_selector_falls_back_to_torznab_fan_out():
    patcher = _preferences(prowlarr_configured=False)
    try:
        assert get_torrent_search_indexer() is get_torznab_indexer()
    finally:
        patcher.stop()


def test_both_protocols_use_the_same_either_or_shape():
    """Usenet and torrent resolve identically: Prowlarr when configured, else the
    per-indexer fan-out. The asymmetry this replaced made Prowlarr the only
    torrent source that could exist."""
    configured = _preferences(prowlarr_configured=True)
    try:
        assert get_usenet_search_indexer() is get_prowlarr_indexer()
        assert get_torrent_search_indexer() is get_prowlarr_indexer()
    finally:
        configured.stop()

    unconfigured = _preferences(prowlarr_configured=False)
    try:
        assert get_usenet_search_indexer() is get_newznab_indexer()
        assert get_torrent_search_indexer() is get_torznab_indexer()
    finally:
        unconfigured.stop()


def test_usenet_selector_prefers_prowlarr_when_configured():
    patcher = _preferences(prowlarr_configured=True)
    try:
        assert get_usenet_search_indexer() is get_prowlarr_indexer()
    finally:
        patcher.stop()


def test_usenet_selector_falls_back_to_newznab_fan_out():
    patcher = _preferences(prowlarr_configured=False)
    try:
        assert get_usenet_search_indexer() is get_newznab_indexer()
    finally:
        patcher.stop()


def test_orchestrator_binds_indexers_through_selectors_only():
    """The regression guard. If a construction site goes back to naming a vendor
    directly, torrent search silently becomes Prowlarr-only again."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "core/dependencies/service_providers.py"
    text = source.read_text()

    assert "torrent_indexer=get_torrent_search_indexer()" in text
    assert "torrent_indexer=get_prowlarr_indexer()" not in text
    assert "usenet_indexer=get_usenet_search_indexer()" in text
