# TuneIn Radio for Kodi

[![CodeQL](https://github.com/joaconigro/plugin.audio.tuneinradio/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/joaconigro/plugin.audio.tuneinradio/actions/workflows/codeql-analysis.yml)

A plugin that allows you to access thousands of radio stations at TuneIn from within Kodi.

## Features

- Display TuneIn favourites.
- Display recently played stations/shows.
- Download shows and podcasts.
- Browse thousands of radio station streams.
- Search for a specific radio station.
- Ability to add/remove stations to/from TuneIn favourites.
- Manually enter a stream to play.
- Add stations to Kodi favourites.

## Installation

Download the corresponding zip file [from here][1] according to your Kodi version and install the addon.
Versions 4.x or higher are for Matrix (>= 19).
Versions 3.x are for Leia and older (< 19).
See [How to install an Add-on from zip file][2] for more details on installing addons from zip file.

## Usage

The TuneIn Radio add-on can be accessed from the Music Addons menu.

## Settings

The following settings are available.

### **TuneIn**

*Username*: TuneIn account username.

*Password*: TuneIn account password.

*Display TuneIn Featured Station*: If set to true display TuneIn featured stations. Default: true

*Display TuneIn Local Station(s)*: If set to true display TuneIn local stations. Default: true

*Language*: Language used by TuneIn. Allowed values: ar-SA|cs-CZ|da-DK|nl-NL|fi-FI|fr-FR|de-DE|el-GR|hi-IN|hu-HU|it-IT|ja-JP|ko-KR|pl-PL|pt-PT|ru-RU|zh-CN|es-ES|sv-SV|zh-TW|tr-TR|en-GB|en-US. Default: en-GB. **Note**: This isn't the add-on interface language. Add-on language will be setted automatically with Kodi interface language, and the only translations available, for now, are English and Spanish.

*Latitude/Longitude*: A specific latitude/longitude pair, comma separated, used to target local radio.

### **Appearance**

*Icon Colour*: Set the colour of the icons used in add-on. Allowed values: White|Black|Red. Default: White

*Number Of Recents*: Number of recent stations/shows to store. Default: 5

*Prompt When Changing Station*: Display a Yes/No dialog when changing stations. Default: true

*Display Fanart*: Display the TuneIn Radio background. Default: true

*Only show TuneIn favourites*: Display only the TuneIn users favourites. The main menu (favourites, recent, browse, search and custom url) will not be displayed. Default: false

### **Downloads**

*Enable Downloads*: Default: true

*Download Path*: Path to download files to.

*Download In Background*: Whether the downloads should occur in background. Default: false

### **Formats**

*AAC/AAC+*: Default: false

*AM (Broadcast)*: Default: false

*DAB (Broadcast)*: Default: false

*FM (Broadcast)*: Default: false

*HD (Broadcast)*: Default: false

*HTML Web Page*: Default: false

*MP3*: Default: true

*OGG*: Default: false

*QuickTime*: Default: false

*RealMedia*: Default: false

*RTMP Flash*: Default: false

*Satellite (Broadcast)*: Default: false

*Windows Media*: Default: true

*Windows Media Professional*: Default: true

*Windows Media Video*: Default: true

*Windows Media Voice*: Default: true

### **Advanced**

*HTTPS**: Use to set protocol (http or https). Default: true

*Use UTF-8 encoding* Use to read list. Default: false. **You must set to true on Android devices**.

*Update Cache (hrs)*: How often to contact TuneIn to update format and genres cache. Default: 24

## FAQ

**Is this plugin available in a Kodi addons repository?** No

**Why doesn't "Such and Such" station play?** There are usual three reason why a station isn't playing:

1. The TuneIn is providing a link to an external website, rather than an audio stream.</li>
2. The TuneIn is providing an audio stream that Kodi can not play.</li>
3. There's a bug in my plugin.

[1]: https://github.com/joaconigro/plugin.audio.tuneinradio/releases
[2]: https://kodi.wiki/view/Add-on_manager#How_to_install_from_a_ZIP_file
