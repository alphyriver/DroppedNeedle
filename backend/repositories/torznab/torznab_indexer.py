"""``TorznabIndexer`` - the ``IndexerProtocol`` impl that fans one logical search
out across the N Torznab indexers the user configured.

Mirrors ``NewznabIndexer``: caps-gated query strategy (structured ``t=music`` only
when caps advertises audio-search with artist/album params, else free-text
``t=search``), a per-call timeout, rate-limit backoff, and a short-TTL search
cache so the fan-out and auto-retry re-search don't each re-hit the tracker.
Results are pooled and deduped by the normalised (title, size) identity - the
same key Usenet uses, per ``TorrentRelease``'s contract - with the
higher-priority indexer's copy winning. One indexer erroring never fails the
fan-out. No ``from __future__ import annotations`` (the conformance test compares
real signatures).
"""

import asyncio
import logging
import time

from core.exceptions import NewznabApiError, NewznabAuthError, RateLimitedError
from models.common import ServiceStatus
from models.download_identity import usenet_identity
from repositories.newznab.newznab_models import NewznabCaps
from repositories.protocols.indexer import IndexerResult, TorrentRelease

from .torznab_client import TorznabClient

logger = logging.getLogger(__name__)

_UNKNOWN_FUNCTION = 202  # "No such function" - fall back t=music -> t=search


class TorznabIndexerEntry:
    """One configured indexer paired with its HTTP client. Not serialised - a
    runtime holder the DI provider builds from ``NewznabIndexerSettings`` rows
    whose ``type`` is ``torznab``."""

    def __init__(
        self,
        client: TorznabClient,
        *,
        indexer_id: str,
        name: str,
        categories: list[int],
        enabled: bool = True,
        priority: int = 1,
        limit: int = 100,
    ) -> None:
        self.client = client
        self.id = indexer_id
        self.name = name
        self.categories = categories
        self.enabled = enabled
        self.priority = priority
        self.limit = limit


class TorznabIndexer:
    def __init__(
        self,
        entries: list[TorznabIndexerEntry],
        *,
        search_cache_ttl: float = 300.0,
        caps_cache_ttl: float = 7 * 24 * 3600.0,
        rate_limit_backoff: float = 300.0,
        per_indexer_timeout: float = 30.0,
    ) -> None:
        # Higher priority (lower number) first, so dedup keeps the preferred copy.
        self._entries = sorted(entries, key=lambda e: e.priority)
        self._search_cache_ttl = search_cache_ttl
        self._caps_cache_ttl = caps_cache_ttl
        self._rate_limit_backoff = rate_limit_backoff
        self._timeout = per_indexer_timeout
        self._caps_cache: dict[str, tuple[float, NewznabCaps]] = {}
        self._search_cache: dict[tuple[str, str], tuple[float, list[TorrentRelease]]] = {}
        self._backoff_until: dict[str, float] = {}

    @property
    def indexer_name(self) -> str:
        return "torrent"

    def is_configured(self) -> bool:
        return any(e.enabled for e in self._entries)

    async def health_check(self) -> ServiceStatus:
        enabled = [e for e in self._entries if e.enabled]
        if not enabled:
            return ServiceStatus(status="error", message="No indexers configured")
        reachable = 0
        version: str | None = None
        for entry in enabled:
            try:
                caps = await entry.client.caps(timeout=self._timeout)
            except Exception as exc:  # noqa: BLE001 - health check never raises
                logger.warning(
                    "torznab health: indexer %s unreachable: %s", entry.name, exc
                )
                continue
            reachable += 1
            version = version or caps.server_version
        if reachable:
            return ServiceStatus(
                status="ok",
                version=version,
                message=f"{reachable}/{len(enabled)} indexer(s) reachable",
            )
        return ServiceStatus(status="error", message="No indexer reachable")

    async def search_album(
        self,
        artist_name: str,
        album_title: str,
        year: int | None = None,
        track_count: int | None = None,
        *,
        timeout: float = 30.0,
    ) -> list[IndexerResult]:
        query = f"{artist_name} {album_title}".strip()
        releases = await self._fan_out(
            query, artist=artist_name, album=album_title, year=year, timeout=timeout
        )
        return [IndexerResult(source="torrent", torrent=r) for r in releases]

    async def search_track(
        self,
        artist_name: str,
        track_title: str,
        album_title: str | None = None,
        duration_seconds: int | None = None,
        *,
        timeout: float = 30.0,
    ) -> list[IndexerResult]:
        # Single-track torrents are rare; the orchestrator resolves to the album.
        # Free-text artist+track only, so the structured music path is never taken.
        query = f"{artist_name} {track_title}".strip()
        releases = await self._fan_out(
            query, artist=artist_name, album=None, year=None, timeout=timeout
        )
        return [IndexerResult(source="torrent", torrent=r) for r in releases]

    async def _fan_out(
        self,
        query: str,
        *,
        artist: str,
        album: str | None,
        year: int | None,
        timeout: float,
    ) -> list[TorrentRelease]:
        enabled = [e for e in self._entries if e.enabled]
        if not enabled:
            return []
        per_call = min(timeout, self._timeout)
        results = await asyncio.gather(
            *(
                self._search_one(
                    e, query, artist=artist, album=album, year=year, timeout=per_call
                )
                for e in enabled
            ),
            return_exceptions=True,
        )
        pooled: list[TorrentRelease] = []
        for entry, res in zip(enabled, results):
            if isinstance(res, Exception):
                logger.warning("torznab indexer %s search failed: %s", entry.name, res)
                continue
            pooled.extend(res)
        return self._dedup(pooled)

    async def _search_one(
        self,
        entry: TorznabIndexerEntry,
        query: str,
        *,
        artist: str,
        album: str | None,
        year: int | None,
        timeout: float,
    ) -> list[TorrentRelease]:
        now = time.monotonic()
        if self._backoff_until.get(entry.id, 0.0) > now:
            logger.info("torznab indexer %s in rate-limit backoff; skipping", entry.name)
            return []
        cache_key = (entry.id, query)
        cached = self._search_cache.get(cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]
        if len(self._search_cache) > 256:
            self._search_cache = {
                k: v for k, v in self._search_cache.items() if v[0] > now
            }

        caps = await self._caps(entry, timeout)
        limit = min(entry.limit or caps.limit_max, caps.limit_max)
        audio_params = set(caps.audio_search_params)
        use_music = (
            bool(album)
            and caps.supports_audio_search
            and {"artist", "album"} <= audio_params
        )
        year_param = year if "year" in audio_params else None

        try:
            releases = await self._query(
                entry,
                query,
                artist=artist,
                album=album,
                year=year_param,
                limit=limit,
                use_music=use_music,
                timeout=timeout,
            )
        except RateLimitedError as exc:
            backoff = exc.retry_after_seconds or self._rate_limit_backoff
            self._backoff_until[entry.id] = time.monotonic() + backoff
            logger.warning(
                "torznab indexer %s rate limited; backing off %.0fs", entry.name, backoff
            )
            return []
        except NewznabAuthError:
            logger.error("torznab indexer %s rejected the API key", entry.name)
            return []

        self._search_cache[cache_key] = (
            time.monotonic() + self._search_cache_ttl,
            releases,
        )
        return releases

    async def _query(
        self,
        entry: TorznabIndexerEntry,
        query: str,
        *,
        artist: str,
        album: str | None,
        year: int | None,
        limit: int,
        use_music: bool,
        timeout: float,
    ) -> list[TorrentRelease]:
        if not use_music or album is None:
            return await entry.client.search(
                query, entry.categories, limit=limit, timeout=timeout
            )
        try:
            return await entry.client.music_search(
                artist,
                album,
                entry.categories,
                year=year,
                limit=limit,
                timeout=timeout,
            )
        except NewznabApiError as exc:
            if getattr(exc, "code", None) == _UNKNOWN_FUNCTION:
                logger.info(
                    "torznab indexer %s lacks t=music; falling back to t=search",
                    entry.name,
                )
                return await entry.client.search(
                    query, entry.categories, limit=limit, timeout=timeout
                )
            raise

    async def _caps(self, entry: TorznabIndexerEntry, timeout: float) -> NewznabCaps:
        now = time.monotonic()
        cached = self._caps_cache.get(entry.id)
        if cached is not None and cached[0] > now:
            return cached[1]
        try:
            caps = await entry.client.caps(timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - permissive default
            logger.warning("torznab caps fetch failed for %s: %s", entry.name, exc)
            return NewznabCaps()  # working-indexer defaults: text q, limit 100
        self._caps_cache[entry.id] = (now + self._caps_cache_ttl, caps)
        return caps

    def _dedup(self, releases: list[TorrentRelease]) -> list[TorrentRelease]:
        """Deduped by the cross-indexer (title, size) identity - the key
        ``TorrentRelease`` documents as shared with Usenet. Higher-priority
        indexers come first, so first-seen-wins keeps the preferred copy."""
        seen: set[str] = set()
        out: list[TorrentRelease] = []
        dropped = 0
        for release in releases:
            key = usenet_identity(release.title, release.size_bytes)
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            out.append(release)
        if dropped:
            logger.info("torznab fan-out deduped %d cross-indexer duplicate(s)", dropped)
        return out
