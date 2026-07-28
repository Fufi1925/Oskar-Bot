# ╔══════════════════════════════════════════════════════════════════╗
# ║   YouTube watching                                               ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Subscribe to a YouTube channel by name and notice two things: a new
upload (including Shorts) and the channel going live.

No API key. Two public endpoints carry all of it:

  * ``/feeds/videos.xml?channel_id=UC...`` -- the RSS feed. Contains the
    15 newest uploads, Shorts among them, with id, title and timestamp.
  * ``/channel/UC.../live`` -- the page YouTube serves for a channel's
    current broadcast. ``"isLive":true`` appears in it only while one is
    actually running.

Both were checked against real channels before this was written: the
feed returned 15 entries for MrBeast, and the live page reported
``live=True`` for a channel that streams around the clock and
``live=False`` for one that does not.

The user types something like ``@MrBeast``, ``MrBeast`` or a full URL.
Only a ``UC...`` id works for the feed, so `resolve` turns whatever was
typed into one -- once, when the subscription is created, rather than on
every poll.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import aiohttp

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
LIVE = "https://www.youtube.com/channel/{cid}/live"

# Without a browser-ish User-Agent YouTube serves a consent interstitial
# that contains none of the markers below.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")
TIMEOUT = aiohttp.ClientTimeout(total=15)


@dataclass
class Video:
    id: str
    title: str
    published: str
    url: str


@dataclass
class Channel:
    id: str
    title: str
    handle: str


class LookupError_(Exception):
    """Raised with a sentence the dashboard can show as-is."""


def _clean(text: str) -> str:
    """Whatever the user typed, reduced to a handle or an id."""
    value = (text or "").strip()
    value = re.sub(r"^https?://", "", value, flags=re.I)
    value = re.sub(r"^(www\.|m\.)?youtube\.com/", "", value, flags=re.I)
    value = value.split("?")[0].split("/")[0] if "/" not in value else value
    return value.strip().lstrip("@").strip()


async def _get(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as response:
            if response.status != 200:
                return None
            return await response.text()
    except Exception:
        return None


async def resolve(session: aiohttp.ClientSession, typed: str) -> Channel:
    """
    Turn what the user typed into a channel id.

    Raises LookupError_ with a German sentence when it cannot, because
    "channel not found" is the one error a server owner will actually
    see and needs to understand.
    """
    raw = (typed or "").strip()
    if not raw:
        raise LookupError_("Bitte einen YouTube-Kanal angeben.")

    # A full channel id needs no lookup at all.
    direct = _clean(raw)
    if CHANNEL_ID.match(direct):
        title = await _title(session, direct)
        if title is None:
            raise LookupError_(f"Zu der ID {direct} gibt es keinen Kanal.")
        return Channel(id=direct, title=title, handle=direct)

    # A /channel/UC... URL carries the id in it.
    embedded = re.search(r"(UC[\w-]{22})", raw)
    if embedded:
        cid = embedded.group(1)
        title = await _title(session, cid)
        if title is None:
            raise LookupError_(f"Zu der ID {cid} gibt es keinen Kanal.")
        return Channel(id=cid, title=title, handle=cid)

    handle = direct
    if not handle:
        raise LookupError_("Bitte einen YouTube-Kanal angeben.")

    # Try the handle page, then the legacy /c/ and /user/ forms.
    for url in (
        f"https://www.youtube.com/@{handle}",
        f"https://www.youtube.com/c/{handle}",
        f"https://www.youtube.com/user/{handle}",
    ):
        html = await _get(session, url)
        if not html:
            continue
        found = re.search(r'"channelId":"(UC[\w-]{22})"', html) or re.search(
            r'channel_id=(UC[\w-]{22})', html
        )
        if not found:
            continue
        cid = found.group(1)
        name = re.search(r'<meta property="og:title" content="([^"]{1,100})"', html)
        return Channel(
            id=cid,
            title=(name.group(1) if name else handle),
            handle=f"@{handle}",
        )

    raise LookupError_(
        f"Den Kanal „{typed}“ gibt es nicht — oder YouTube gibt ihn nicht "
        "heraus. Probier den @Namen genau wie in der URL, oder die "
        "Kanal-ID (beginnt mit UC)."
    )


async def _title(session: aiohttp.ClientSession, channel_id: str) -> str | None:
    """The channel's display name, from its feed."""
    xml = await _get(session, FEED.format(cid=channel_id))
    if not xml:
        return None
    match = re.search(r"<title>(.*?)</title>", xml, re.S)
    return _unescape(match.group(1)) if match else channel_id


def _unescape(text: str) -> str:
    import html as html_module

    return html_module.unescape(text or "").strip()


async def latest_videos(
    session: aiohttp.ClientSession, channel_id: str
) -> list[Video]:
    """
    The newest uploads, newest first.

    Shorts are in here too -- YouTube does not separate them in the
    feed, and the user asked for both.
    """
    xml = await _get(session, FEED.format(cid=channel_id))
    if not xml:
        return []

    videos: list[Video] = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        vid = re.search(r"<yt:videoId>([\w-]+)</yt:videoId>", entry)
        title = re.search(r"<media:title>(.*?)</media:title>", entry, re.S)
        published = re.search(r"<published>(.*?)</published>", entry)
        if not vid:
            continue
        videos.append(Video(
            id=vid.group(1),
            title=_unescape(title.group(1)) if title else "Neues Video",
            published=published.group(1) if published else "",
            url=f"https://www.youtube.com/watch?v={vid.group(1)}",
        ))
    return videos


async def live_now(
    session: aiohttp.ClientSession, channel_id: str
) -> Video | None:
    """
    The broadcast running right now, or None.

    The `/live` page redirects to the stream while one is on and to the
    channel otherwise, so the marker has to be checked rather than the
    status code.
    """
    html = await _get(session, LIVE.format(cid=channel_id))
    if not html:
        return None

    if '"isLive":true' not in html and '"isLiveBroadcast":true' not in html:
        return None

    # An ended stream keeps isLiveBroadcast in its metadata but gains an
    # endDate. Without this check the bot re-announces old streams.
    if '"endDate"' in html and '"isLive":true' not in html:
        return None

    vid = re.search(r'"videoId":"([\w-]{11})"', html)
    if not vid:
        return None

    title = re.search(r'<meta name="title" content="([^"]{1,200})"', html)
    return Video(
        id=vid.group(1),
        title=_unescape(title.group(1)) if title else "Livestream",
        published="",
        url=f"https://www.youtube.com/watch?v={vid.group(1)}",
    )
