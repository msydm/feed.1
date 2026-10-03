#!/usr/bin/env python3
"""
Generates an RSS feed of upcoming Metal Sydney Metal gigs from the
public Google Calendar ICS feed — sorted soonest-first, with past
events dropped automatically. Writes the result to docs/feed.xml,
which GitHub Pages serves as a plain static file (no redirects,
unlike Google Apps Script web apps — this is why we moved here).
"""

import datetime
import os
import urllib.request
import xml.sax.saxutils as saxutils

import recurring_ical_events
from icalendar import Calendar

# Public iCal address for the "Metal Sydney Metal Gig Guide" calendar.
# Find/confirm this under Google Calendar settings for that calendar ->
# "Integrate calendar" -> "Public address in iCal format".
ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "3bo1375knjblilkb1okh5tom758qr0ke%40import.calendar.google.com/"
    "public/basic.ics"
)

MAX_EVENTS = 50
LOOKAHEAD_DAYS = 730  # ~2 years ahead
FEED_TITLE = "Metal Sydney Metal — Upcoming Gigs"
FEED_LINK = "https://metalsydneymetal.com"
FEED_DESCRIPTION = "Upcoming gigs from the Metal Sydney Metal gig guide."
OUTPUT_PATH = "docs/feed.xml"


def fetch_ics(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _as_aware_datetime(dt):
    """Normalize a date or datetime value to a timezone-aware UTC datetime."""
    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        return datetime.datetime.combine(
            dt, datetime.time.min, tzinfo=datetime.timezone.utc
        )
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def get_events():
    ics_bytes = fetch_ics(ICS_URL)
    cal = Calendar.from_ical(ics_bytes)

    now = datetime.datetime.now(datetime.timezone.utc)
    end = now + datetime.timedelta(days=LOOKAHEAD_DAYS)

    # Expands recurring events (RRULE) into individual instances within
    # range, and returns only events overlapping [now, end] — i.e.
    # events already in progress are kept, events that have fully
    # ended are dropped. Mirrors CalendarApp.getEvents(now, future)
    # from the original Apps Script version.
    events = recurring_ical_events.of(cal).between(now, end)
    events = sorted(events, key=lambda ev: _as_aware_datetime(ev["DTSTART"].dt))
    return events[:MAX_EVENTS], now


def escape(text):
    return saxutils.escape(str(text or ""))


def format_when(ev):
    dt = ev["DTSTART"].dt
    is_all_day = isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime)
    if is_all_day:
        return dt.strftime("%a %-d %b %Y")

    start_str = dt.strftime("%a %-d %b %Y, %-I:%M %p")
    dtend = ev.get("DTEND")
    if dtend:
        end_str = dtend.dt.strftime("%-I:%M %p")
        return f"{start_str} \u2013 {end_str}"
    return start_str


def build_item(ev, now):
    title = escape(ev.get("SUMMARY"))
    location = str(ev.get("LOCATION") or "")
    description = str(ev.get("DESCRIPTION") or "")
    uid = str(ev.get("UID") or "")

    start = _as_aware_datetime(ev["DTSTART"].dt)

    parts = [format_when(ev)]
    if location:
        parts.append(f"Location: {location}")
    if description:
        parts.append(description)
    desc_text = escape(" | ".join(parts))

    # Mirror the start date into the past around "now" so RSS readers
    # that resort by pubDate (newest first) still show soonest-first:
    # an event 3 days out gets a pubDate 3 days ago, one 60 days out
    # gets a pubDate 60 days ago.
    offset = start - now
    mirrored_pub = now - offset
    pub_date = mirrored_pub.strftime("%a, %d %b %Y %H:%M:%S GMT")

    return (
        "<item>\n"
        f"<title>{title}</title>\n"
        f"<link>{escape(FEED_LINK)}</link>\n"
        f'<guid isPermaLink="false">{escape(uid)}</guid>\n'
        f"<pubDate>{pub_date}</pubDate>\n"
        f"<description>{desc_text}</description>\n"
        "</item>"
    )


def build_rss():
    events, now = get_events()
    items = "\n".join(build_item(ev, now) for ev in events)
    now_str = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        f"<title>{escape(FEED_TITLE)}</title>\n"
        f"<link>{escape(FEED_LINK)}</link>\n"
        f"<description>{escape(FEED_DESCRIPTION)}</description>\n"
        f"<lastBuildDate>{now_str}</lastBuildDate>\n"
        f"{items}\n"
        "</channel></rss>"
    )


def main():
    rss = build_rss()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
