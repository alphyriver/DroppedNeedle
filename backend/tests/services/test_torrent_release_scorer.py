"""TorrentReleaseScorer: seeders-as-health (dead torrents dropped outright),
category-primary quality, quarantine-by-identity in the "torrent" namespace."""

from unittest.mock import AsyncMock

import pytest

from api.v1.schemas.settings import DownloadPolicySettings
from models.download import TargetAlbum
from models.download_identity import usenet_identity
from repositories.protocols.indexer import TorrentRelease
from services.native.acquisition.quality import build_snapshot
from services.native.torrent_release_scorer import TorrentReleaseScorer

_TARGET = TargetAlbum(artist_name="Radiohead", album_title="In Rainbows", track_count=10)


def _store(quarantine=None):
    store = AsyncMock()
    store.load_quarantine_set.return_value = set(quarantine or set())
    return store


def _release(
    title, cats, *, size=600_000_000, seeders=50, leechers=3, guid="g", magnet="magnet:?xt=x"
) -> TorrentRelease:
    return TorrentRelease(
        indexer_id="1", indexer_name="RED", guid=guid, title=title,
        magnet_url=magnet, download_url="https://prowlarr/dl", size_bytes=size,
        category_ids=cats, seeders=seeders, leechers=leechers,
    )


def _scorer(quarantine=None):
    return TorrentReleaseScorer(_store(quarantine))


def policy_snapshot(**over):
    """Legacy quality kwargs moved onto the required keyword-only snapshot."""
    base = dict(quality_min="mp3_320", quality_max="lossless")
    base.update(over)
    return build_snapshot(DownloadPolicySettings(**base))


@pytest.mark.asyncio
async def test_clean_lossless_release_reaches_auto():
    rel = _release("Radiohead - In Rainbows (2007) [FLAC]", [3040])
    [cand] = await _scorer().rank(_TARGET, [rel], snapshot=policy_snapshot())
    assert cand.source == "torrent"
    assert cand.torrent_release is rel
    assert cand.tier == "auto"
    assert cand.final_score >= 0.70


@pytest.mark.asyncio
async def test_zero_seeders_is_dropped():
    rel = _release("Radiohead - In Rainbows [FLAC]", [3040], seeders=0)
    assert await _scorer().rank(_TARGET, [rel], snapshot=policy_snapshot()) == []


@pytest.mark.asyncio
async def test_missing_seeders_is_manual_only():
    rel = _release("Radiohead - In Rainbows [FLAC]", [3040], seeders=None)
    ranked = await _scorer().rank(_TARGET, [rel], snapshot=policy_snapshot())
    assert len(ranked) == 1
    assert ranked[0].tier == "manual"


@pytest.mark.asyncio
async def test_low_seeders_lowers_health_but_still_scores():
    healthy = _release("Radiohead - In Rainbows [FLAC]", [3040], seeders=50, guid="a")
    scarce = _release("Radiohead - In Rainbows [FLAC]", [3040], seeders=1, guid="b",
                      size=600_000_001)
    ranked = await _scorer().rank(_TARGET, [healthy, scarce], snapshot=policy_snapshot())
    assert len(ranked) == 2
    assert ranked[0].torrent_release.guid == "a"
    assert ranked[0].final_score > ranked[1].final_score


@pytest.mark.asyncio
async def test_music_video_category_is_dropped():
    rel = _release("Radiohead - In Rainbows [music video]", [3020])
    assert await _scorer().rank(_TARGET, [rel], snapshot=policy_snapshot()) == []


@pytest.mark.asyncio
async def test_quality_min_lossless_drops_mp3_release():
    rel = _release("Radiohead - In Rainbows [MP3-320]", [3010])
    snapshot = policy_snapshot(quality_min="lossless", quality_max="lossless")
    assert await _scorer().rank(_TARGET, [rel], snapshot=snapshot) == []


@pytest.mark.asyncio
async def test_quarantined_identity_is_dropped_in_torrent_namespace():
    rel = _release("Radiohead - In Rainbows [FLAC]", [3040])
    key = ("torrent", usenet_identity(rel.title, rel.size_bytes))
    assert await _scorer(quarantine={key}).rank(_TARGET, [rel], snapshot=policy_snapshot()) == []
    # The same identity quarantined under "usenet" must NOT block the torrent copy.
    other = ("usenet", usenet_identity(rel.title, rel.size_bytes))
    assert len(await _scorer(quarantine={other}).rank(_TARGET, [rel], snapshot=policy_snapshot())) == 1


@pytest.mark.asyncio
async def test_far_too_small_release_is_dropped():
    rel = _release("Radiohead - In Rainbows [FLAC]", [3040], size=5_000_000)
    assert await _scorer().rank(_TARGET, [rel], snapshot=policy_snapshot()) == []
