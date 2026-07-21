"""Raw httpx + XML wrapper around one Torznab indexer. No fan-out logic (that's
``TorznabIndexer``); this is the per-indexer HTTP + parse layer.

Torznab is Newznab's torrent variant: identical transport (``t=caps``/``t=search``,
``&apikey=`` query param, XML-only, ``<error>`` on HTTP 200), identical caps
document. It differs in exactly two places:

1. Extended attributes live under the **torznab** namespace
   (``http://torznab.com/schemas/2015/feed``) rather than the newznab one, and
   carry ``seeders``/``peers``/``magneturl``/``infohash``.
2. Items carry a torrent or magnet enclosure instead of an NZB, so they parse to
   ``TorrentRelease`` rather than ``UsenetRelease``.

Everything else - XML hardening, error classification, rate-limit handling, date
and int coercion - is imported from ``newznab_client`` rather than duplicated.
That module is upstream-owned and actively edited; importing keeps one source of
truth for the hardening rules (which exist because real indexers emit malformed
XML) and keeps this fork from editing an upstream file it would then have to
merge on every sync. The imports are module-private by name; if upstream renames
them this fails loudly at import time, and
``tests/repositories/test_torznab_client.py`` pins them so the failure names the
cause.
"""

import logging
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx

from core.exceptions import NewznabApiError, RateLimitedError
from repositories.newznab.newznab_client import (
    _check_error,
    _first,
    _local,
    _parse_caps,
    _parse_date,
    _retry_after,
    _safe_fromstring,
    _to_int,
)
from repositories.newznab.newznab_models import NewznabCaps
from repositories.protocols.indexer import TorrentRelease

logger = logging.getLogger(__name__)

# The torznab extended-attribute namespace; attrs are <torznab:attr name= value=>.
_NS = "http://torznab.com/schemas/2015/feed"
_ATTR = f"{{{_NS}}}attr"


class TorznabClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        indexer_id: str = "",
        indexer_name: str = "",
    ) -> None:
        self._http = http
        # The user pastes the full API path (e.g. https://idx/api); keep it verbatim.
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._indexer_id = indexer_id
        self._indexer_name = indexer_name or base_url

    async def caps(self, *, timeout: float = 30.0) -> NewznabCaps:
        """Torznab serves the same caps document as Newznab."""
        root = await self._get({"t": "caps"}, timeout=timeout)
        _check_error(root)
        return _parse_caps(root)

    async def search(
        self,
        query: str,
        categories: list[int],
        *,
        offset: int = 0,
        limit: int = 100,
        timeout: float = 30.0,
    ) -> list[TorrentRelease]:
        """Free-text ``t=search`` - the always-available path."""
        params = {
            "t": "search",
            "q": query,
            "extended": "1",
            "offset": str(offset),
            "limit": str(limit),
        }
        if categories:
            params["cat"] = ",".join(str(c) for c in categories)
        return await self._search_request(params, timeout=timeout)

    async def music_search(
        self,
        artist: str,
        album: str,
        categories: list[int],
        *,
        year: int | None = None,
        offset: int = 0,
        limit: int = 100,
        timeout: float = 30.0,
    ) -> list[TorrentRelease]:
        """Structured ``t=music`` - used ONLY when caps advertises audio-search with
        artist/album params. The caller falls back to ``search`` on a 202."""
        params = {
            "t": "music",
            "artist": artist,
            "album": album,
            "extended": "1",
            "offset": str(offset),
            "limit": str(limit),
        }
        if year:
            params["year"] = str(year)
        if categories:
            params["cat"] = ",".join(str(c) for c in categories)
        return await self._search_request(params, timeout=timeout)

    async def _search_request(
        self, params: dict[str, str], *, timeout: float
    ) -> list[TorrentRelease]:
        root = await self._get(params, timeout=timeout)
        _check_error(root)
        request_url = f"{self._base_url}?{params.get('t', '')}"
        return _parse_items(root, self._indexer_id, self._indexer_name, request_url)

    async def _get(self, params: dict[str, str], *, timeout: float) -> ET.Element:
        merged = {**params, "apikey": self._api_key}
        try:
            response = await self._http.get(
                self._base_url, params=merged, timeout=timeout
            )
        except httpx.HTTPError as exc:
            raise NewznabApiError(f"torznab request failed: {exc}") from exc
        if response.status_code == 429:
            raise RateLimitedError(
                "torznab: rate limited", retry_after_seconds=_retry_after(response)
            )
        if response.status_code >= 400:
            raise NewznabApiError(
                f"torznab returned HTTP {response.status_code}",
                details=response.text[:200],
                code=response.status_code,
            )
        return _safe_fromstring(response.content)


class _NotATorrent(Exception):
    """Internal signal: an item carried no torrent or magnet source."""


def _parse_items(
    root: ET.Element, indexer_id: str, indexer_name: str, request_url: str
) -> list[TorrentRelease]:
    releases: list[TorrentRelease] = []
    for item in root.iter("item"):
        try:
            release = _parse_item(item, indexer_id, indexer_name, request_url)
        except _NotATorrent:
            # A mixed feed (some indexers serve both) must not discard valid siblings.
            logger.warning("torznab: skipping non-torrent item from %s", indexer_name)
            continue
        except Exception as exc:  # noqa: BLE001 - one bad item must not sink the feed
            logger.warning(
                "torznab: skipping unparseable item from %s: %s", indexer_name, exc
            )
            continue
        if release is not None:
            releases.append(release)
    return releases


def _parse_item(
    item: ET.Element, indexer_id: str, indexer_name: str, request_url: str
) -> TorrentRelease | None:
    attrs = _attr_map(item)

    magnet_url = (_first(attrs.get("magneturl")) or "").strip()
    download_url = ""
    enclosure_size = 0
    for enc in item.findall("enclosure"):
        etype = (enc.get("type") or "").lower()
        url = (enc.get("url") or "").strip()
        if not url:
            continue
        if url.startswith("magnet:"):
            magnet_url = magnet_url or url
            continue
        # Torznab enclosures are application/x-bittorrent; a no-type enclosure is
        # accepted, matching the Newznab client's permissive read.
        if "torrent" in etype or etype == "":
            download_url = url
            enclosure_size = _to_int(enc.get("length")) or 0
            if "torrent" in etype:
                break

    if not download_url and not magnet_url:
        link = (item.findtext("link") or "").strip()
        if link.startswith("magnet:"):
            magnet_url = link
        elif link:
            # Trackers commonly return a proxied .torrent fetch as <link>.
            download_url = link

    if not download_url and not magnet_url:
        raise _NotATorrent()

    size = _to_int(_first(attrs.get("size"))) or enclosure_size
    category_ids = [
        c for v in attrs.get("category", []) if (c := _to_int(v)) is not None
    ]
    # `peers` is total (seeders + leechers) in the Torznab spec; derive leechers
    # from it when the indexer does not send `leechers` directly.
    seeders = _to_int(_first(attrs.get("seeders")))
    leechers = _to_int(_first(attrs.get("leechers")))
    if leechers is None:
        peers = _to_int(_first(attrs.get("peers")))
        if peers is not None and seeders is not None:
            leechers = max(0, peers - seeders)

    return TorrentRelease(
        indexer_id=indexer_id,
        indexer_name=indexer_name,
        guid=item.findtext("guid") or "",
        title=(item.findtext("title") or "Unknown").strip(),
        download_url=urljoin(request_url, download_url) if download_url else "",
        magnet_url=magnet_url,
        info_hash=(_first(attrs.get("infohash")) or "").strip(),
        size_bytes=size,
        category_ids=category_ids,
        seeders=seeders,
        leechers=leechers,
        grabs=_to_int(_first(attrs.get("grabs"))),
        publish_date=_parse_date(item.findtext("pubDate")),
    )


def _attr_map(item: ET.Element) -> dict[str, list[str]]:
    """``{name.lower(): [values]}`` from the item's ``<torznab:attr>`` elements
    (``category`` repeats). Attr-name match is case-insensitive.

    Falls back to a namespace-agnostic scan when the feed declares no torznab
    namespace - some trackers emit bare ``<attr>`` elements, and dropping their
    seeders would make every release look dead at scoring.
    """
    out: dict[str, list[str]] = {}
    elements = item.findall(_ATTR)
    if not elements:
        elements = [el for el in item if _local(el.tag) == "attr"]
    for attr in elements:
        name = (attr.get("name") or "").lower()
        value = attr.get("value")
        if name and value is not None:
            out.setdefault(name, []).append(value)
    return out
