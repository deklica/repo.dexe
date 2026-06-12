# Vidscr — Kodi Addon

A clean, simple Movies & TV Shows addon for Kodi 19+ (tested on Omega 21).

## Features

### Movies
- New Releases (Now Playing)
- Popular / Top Rated / Upcoming
- Oscar Nominated
- Genres (Action, Drama, Sci-Fi, ...)
- Actors (browse popular + search)
- Networks / Studios (Disney, Warner Bros, A24, ...)

### TV Shows
- **New Episodes** — 7-day (configurable) upcoming episode calendar using TVmaze (US + UK by default)
- **TVmaze Premiering Shows** — new series premiering soon
- On The Air / Popular / Top Rated
- Genres
- Actors
- Networks (Netflix, HBO, Prime Video, BBC, ITV, ...)

### Search
- Movies, TV Shows, People, and Multi-search

## Metadata
Posters and metadata come from **TMDB** (v3). A default API key is bundled; you can swap it in *Settings*.

## Playback
Streams are resolved from **vidsrcme.ru**:

1. The embed page is fetched and the Cloudnestra iframe hashes extracted.
2. Each server's `/rcp/{hash}` → `/prorcp/{hash2}` flow is walked server-side to pull the `.m3u8` URL.
3. HLS streams play via **InputStream Adaptive** with Referer/Origin headers.
4. If the built-in resolver can't handle an unusual host, the addon falls back to **ResolveURL** (optional dependency).

## Installation

1. Download `plugin.video.vidscr-1.0.0.zip`.
2. In Kodi: *Add-ons* → *Install from zip file* → select the zip.
3. (Optional) Install `script.module.resolveurl` for extra host coverage.
4. Open *Vidscr* from Video add-ons.

## Settings

| Setting | Description |
|---|---|
| TMDB API Key | v3 key (default key pre-filled) |
| TMDB Language | UI language for metadata |
| Region | Affects "New Releases" and certification |
| Calendar Countries | Up to two countries for the TV calendar (US + GB default) |
| Calendar Days | 1–14 days of upcoming episodes |
| Vidsrc Host | `vidsrcme.ru` by default; swap if a mirror is needed |
| Prefer ResolveURL | Try ResolveURL first instead of the built-in resolver |
| InputStream Adaptive | Use ISA for HLS (recommended) |

## License
GPL-3.0-or-later
