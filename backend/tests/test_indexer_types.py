"""The indexer ``type`` discriminator.

``type`` is the wire format, and it determines which protocol arm the indexer's
releases land in: newznab -> usenet, torznab -> torrent. Both live in the same
configured list, so the providers must split on it - an unfiltered list would
point NZB parsing at a tracker.
"""

from unittest.mock import patch

import pytest

from api.v1.schemas.settings import INDEXER_TYPES, NewznabIndexerSettings


def test_defaults_to_newznab_for_rows_saved_before_the_type_existed():
    assert NewznabIndexerSettings(id="a").type == "newznab"


@pytest.mark.parametrize("indexer_type", sorted(INDEXER_TYPES))
def test_accepts_every_supported_type(indexer_type):
    assert NewznabIndexerSettings(id="a", type=indexer_type).type == indexer_type


def test_type_is_normalised_before_validation():
    assert NewznabIndexerSettings(id="a", type="  TORZNAB ").type == "torznab"


def test_rejects_an_unknown_type():
    with pytest.raises(ValueError, match="Unknown indexer type"):
        NewznabIndexerSettings(id="a", type="jackett")


def test_prowlarr_is_not_a_valid_indexer_type():
    """Prowlarr returns BOTH usenet and torrent arms, so it has no single
    protocol and cannot be a typed list entry. It keeps its own singleton
    ProwlarrConnectionSettings."""
    assert "prowlarr" not in INDEXER_TYPES
    with pytest.raises(ValueError):
        NewznabIndexerSettings(id="a", type="prowlarr")


@pytest.mark.parametrize(
    ("indexer_type", "expected"),
    [("newznab", "usenet"), ("torznab", "torrent")],
)
def test_protocol_is_derived_from_type(indexer_type, expected):
    assert NewznabIndexerSettings(id="a", type=indexer_type).protocol == expected


def test_url_scheme_is_defaulted_for_both_types():
    for indexer_type in sorted(INDEXER_TYPES):
        settings = NewznabIndexerSettings(id="a", type=indexer_type, url="idx.test/api")
        assert settings.url == "https://idx.test/api"


def _rows():
    return [
        NewznabIndexerSettings(id="n1", type="newznab", url="https://nzb.test", name="N"),
        NewznabIndexerSettings(id="t1", type="torznab", url="https://trk.test", name="T"),
    ]


def test_newznab_provider_ignores_torznab_rows():
    from core.dependencies.repo_providers import get_newznab_indexer

    get_newznab_indexer.cache_clear()
    with patch(
        "core.dependencies.repo_providers.get_preferences_service"
    ) as preferences:
        preferences.return_value.get_indexers_raw.return_value = _rows()
        preferences.return_value.get_download_policy.return_value.auto_retry_base_interval_minutes = 10
        indexer = get_newznab_indexer()
    get_newznab_indexer.cache_clear()

    assert [e.id for e in indexer._entries] == ["n1"]


def test_torznab_provider_ignores_newznab_rows():
    from core.dependencies.repo_providers import get_torznab_indexer

    get_torznab_indexer.cache_clear()
    with patch(
        "core.dependencies.repo_providers.get_preferences_service"
    ) as preferences:
        preferences.return_value.get_indexers_raw.return_value = _rows()
        preferences.return_value.get_download_policy.return_value.auto_retry_base_interval_minutes = 10
        indexer = get_torznab_indexer()
    get_torznab_indexer.cache_clear()

    assert [e.id for e in indexer._entries] == ["t1"]


def test_the_two_fan_outs_report_their_protocol_as_indexer_name():
    from repositories.newznab.newznab_indexer import NewznabIndexer
    from repositories.torznab.torznab_indexer import TorznabIndexer

    assert NewznabIndexer([]).indexer_name == "usenet"
    assert TorznabIndexer([]).indexer_name == "torrent"
