"""Torznab XML parsing.

Torznab is Newznab's torrent variant, so the transport and caps document are
shared; what is genuinely different is the extended-attribute namespace and the
enclosure type. These tests cover that difference and the shapes real trackers
emit.
"""

from xml.etree import ElementTree as ET

import pytest

from repositories.torznab.torznab_client import _parse_items

_TORZNAB_NS = "http://torznab.com/schemas/2015/feed"


def _feed(items_xml: str) -> ET.Element:
    return ET.fromstring(
        f'<rss xmlns:torznab="{_TORZNAB_NS}"><channel>{items_xml}</channel></rss>'
    )


def _parse(items_xml: str):
    return _parse_items(_feed(items_xml), "idx-1", "Tracker", "https://tracker/api")


def test_parses_torrent_enclosure_with_torznab_attrs():
    releases = _parse(
        """
        <item>
          <title>Some Artist - Some Album [FLAC]</title>
          <guid>abc123</guid>
          <link>https://tracker/dl/abc123.torrent</link>
          <pubDate>Mon, 20 Jul 2026 10:00:00 +0000</pubDate>
          <enclosure url="https://tracker/dl/abc123.torrent"
                     type="application/x-bittorrent" length="12345"/>
          <torznab:attr name="seeders" value="42"/>
          <torznab:attr name="peers" value="50"/>
          <torznab:attr name="infohash" value="DEADBEEF"/>
          <torznab:attr name="size" value="99999"/>
          <torznab:attr name="category" value="3000"/>
          <torznab:attr name="category" value="3010"/>
        </item>
        """
    )

    assert len(releases) == 1
    release = releases[0]
    assert release.title == "Some Artist - Some Album [FLAC]"
    assert release.guid == "abc123"
    assert release.download_url == "https://tracker/dl/abc123.torrent"
    assert release.info_hash == "DEADBEEF"
    assert release.size_bytes == 99999  # attr wins over enclosure length
    assert release.category_ids == [3000, 3010]
    assert release.seeders == 42
    assert release.publish_date is not None


def test_derives_leechers_from_peers_when_not_sent_directly():
    """The Torznab spec defines `peers` as total (seeders + leechers). Trackers
    vary on which they send; a missing leecher count must not read as zero."""
    releases = _parse(
        """
        <item>
          <title>A</title>
          <enclosure url="https://tracker/a.torrent" type="application/x-bittorrent"/>
          <torznab:attr name="seeders" value="10"/>
          <torznab:attr name="peers" value="30"/>
        </item>
        """
    )

    assert releases[0].seeders == 10
    assert releases[0].leechers == 20


def test_explicit_leechers_attr_wins_over_peers_derivation():
    releases = _parse(
        """
        <item>
          <title>A</title>
          <enclosure url="https://tracker/a.torrent" type="application/x-bittorrent"/>
          <torznab:attr name="seeders" value="10"/>
          <torznab:attr name="peers" value="30"/>
          <torznab:attr name="leechers" value="7"/>
        </item>
        """
    )

    assert releases[0].leechers == 7


def test_parses_magnet_only_release():
    releases = _parse(
        """
        <item>
          <title>Magnet Only</title>
          <link>magnet:?xt=urn:btih:CAFE</link>
          <torznab:attr name="seeders" value="3"/>
        </item>
        """
    )

    assert releases[0].magnet_url == "magnet:?xt=urn:btih:CAFE"
    assert releases[0].download_url == ""


def test_magnet_attr_is_used_when_enclosure_is_a_torrent():
    releases = _parse(
        """
        <item>
          <title>Both</title>
          <enclosure url="https://tracker/b.torrent" type="application/x-bittorrent"/>
          <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:BEEF"/>
        </item>
        """
    )

    assert releases[0].download_url == "https://tracker/b.torrent"
    assert releases[0].magnet_url == "magnet:?xt=urn:btih:BEEF"


def test_falls_back_to_namespaceless_attrs():
    """Some trackers emit bare <attr> without declaring the torznab namespace.
    Dropping those would zero every seeder count and make releases look dead."""
    root = ET.fromstring(
        """
        <rss><channel><item>
          <title>Bare Attrs</title>
          <enclosure url="https://tracker/c.torrent" type="application/x-bittorrent"/>
          <attr name="seeders" value="5"/>
        </item></channel></rss>
        """
    )

    releases = _parse_items(root, "idx-1", "Tracker", "https://tracker/api")

    assert releases[0].seeders == 5


def test_skips_items_with_no_torrent_or_magnet_source():
    releases = _parse(
        """
        <item><title>Not a torrent</title><guid>x</guid></item>
        <item>
          <title>Real</title>
          <enclosure url="https://tracker/d.torrent" type="application/x-bittorrent"/>
        </item>
        """
    )

    assert [r.title for r in releases] == ["Real"]


def test_one_unparseable_item_does_not_sink_the_feed():
    releases = _parse(
        """
        <item>
          <title>Good</title>
          <enclosure url="https://tracker/e.torrent" type="application/x-bittorrent"/>
        </item>
        <item><title>Bad</title></item>
        """
    )

    assert [r.title for r in releases] == ["Good"]


def test_relative_download_url_is_resolved_against_the_request_url():
    releases = _parse(
        """
        <item>
          <title>Relative</title>
          <enclosure url="/dl/f.torrent" type="application/x-bittorrent"/>
        </item>
        """
    )

    assert releases[0].download_url == "https://tracker/dl/f.torrent"


def test_shared_newznab_helpers_are_importable():
    """The Torznab client imports XML hardening and error classification from the
    upstream-owned newznab client rather than duplicating them, so there is one
    source of truth for the malformed-feed handling. If upstream renames these,
    this test names the cause instead of surfacing as an ImportError mid-request.
    """
    from repositories.newznab import newznab_client

    for name in (
        "_safe_fromstring",
        "_check_error",
        "_parse_caps",
        "_parse_date",
        "_retry_after",
        "_to_int",
        "_first",
        "_local",
    ):
        assert hasattr(newznab_client, name), (
            f"newznab_client.{name} is gone; repositories/torznab/torznab_client.py "
            "imports it"
        )
