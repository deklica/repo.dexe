OpenSubtitles.org by OpenSubtitles with dual subs KODI add-on
=============================================================

The possibility to use two subtitles at the same time was build in by moham96.
See https://github.com/moham96/service.subtitles.opensubtitles_by_opensubtitles

Changelog

5.5.2 (2023-12-02)
- Some default settings were not applied if not changed first

5.5.1
- Try to allight subtitles better in case of bottom/bottom
- Allow negative vertical margin
- Make Auto Charset the default (again)

5.5.0
- Allows to show the subtitles on top/bottom, bottom/left - right, bottom/bottom

5.4.0
- Allows to extend the time the subtitle(s) are shown on screen for slow readers.

5.3.0
- Possibility to choose two subtitles. One will be shown at the bottom, the other on top
- Works both with Python 2 (kodi 17, 18) and Python 3 (kodi 19)

5.2.14
- New feature: Users are able to check for subtitles when Kodi is not playing, by using the manual search or by standing on an item and opening the subtitles search dialog (By key or by an external addon) | @burekas
- The external addon for the contextmenu can be downloaded from here: https://github.com/burekas7/context.subtitlesdialog.contextmenu

5.1.14
- Users are able to download subtitles as anonymous without authentication. Added localized descriptions, media files

5.0.14
- Fix for Portuguese (Brazil) broken by 42f6ec9, thx host505

5.0.13
- Fix for Greek subtitles, thx host505

5.0.12
- compare season and episode and display only matching results

5.0.11
- fix: search issues
- cosmetics
- add slash or backslash at the end of path (fix xbmcvfs.exists in Helix), thx Ondrej Bima

5.0.10
- fix: Don't unquote(urldecode) file_original_path as it breaks http file hashing, thx arnova

5.0.9
- fix hash large rars, Beam
- Support for preferred language sorting and fetch using IMDBID, Glenn Jennehed
- fix: hack to work around issue where Brazilian is not found as language in XBMC

5.0.8
- fix: extension is needed for downloaded files

5.0.7
- fix: Do not use unsafe file names, thx Cesar Canassa

5.0.6
- clean temp folder
- add login details to addon settings

5.0.5
- [fix] ascii UNICODE.decode
- [fix] manual search string unquoted
- cosmetics and code simplification

5.0.4
- manual search button support

5.0.3
- fix Portuguese (Brazil) and Greek

5.0.2
- icon.png and added logo.png for skin to use in window

5.0.1
- let skin control flag filetype

5.0.0
- move the service out of XBMC Subtitles


# Installation in kodi:
Via repository https://peno64.github.io/repository.peno64/
