# SIMKL Setup — Vidscr Addon

This addon ships with **PIN-based device authentication** for SIMKL, mirroring
the Trakt and Bingebase flows. To use it you need to register a free SIMKL
"app" once and paste the resulting **API Key (client_id)** into the addon
settings. It takes about 30 seconds.

---

## 1. Create a SIMKL account (skip if you have one)

Go to https://simkl.com/ and sign up — free account is fine. Confirm your
email if asked.

## 2. Register a SIMKL "app" to get a client_id

1. Open **https://simkl.com/settings/developer/new/**
2. Fill the form:
   - **Name**: anything, e.g. `Vidscr Kodi`
   - **Description**: e.g. `Personal Kodi addon`
   - **Redirect URI**: `urn:ietf:wg:oauth:2.0:oob`
     *(this is the literal value used by device/PIN flows — copy/paste it as-is)*
   - **Permissions / Scopes**: leave defaults (read + sync)
3. Click **Create**.
4. Copy the **API Key** (this is your `client_id`). Optionally also copy the
   `client_secret` — you only need it if you plan to use the OAuth2 (browser)
   flow instead of PIN, which Vidscr does not require.

## 3. Paste the client_id into Vidscr

In Kodi → **Add-ons → Vidscr → Configure → SIMKL**:

- **Enable SIMKL integration** ✓
- **Custom SIMKL client ID**: paste the API Key from step 2
- **Custom SIMKL client secret**: leave empty (only needed for OAuth2)

## 4. Authenticate

- Click **Authenticate with SIMKL**.
- A dialog will show a short PIN code (e.g. `A1B2C` or similar) and the
  URL **https://simkl.com/pin/**.
- On any browser/phone, open `simkl.com/pin`, log in if needed, and type
  the code.
- The Kodi dialog auto-closes when SIMKL confirms — you'll see a
  "Authentication successful" toast.

## 5. Use it

- **Scrobbling** is automatic during playback. Start / pause / resume / stop
  events are sent to SIMKL alongside Trakt + Bingebase if those are enabled.
  Items watched ≥80% are auto-marked watched on SIMKL (default behaviour).
- **Mark watched context menu** (right-click an item in Vidscr): you'll see
  *"SIMKL: Mark as watched"* in addition to the Trakt/Bingebase entries.
- **Sync watched history now**: pulls your full SIMKL library (movies, TV,
  anime) + paused playbacks into the addon-local store, so watched markers
  and "Continue Watching" rows stay in sync across devices.
- **Sign out of SIMKL**: clears the local token (does not revoke the app on
  SIMKL — you can do that at https://simkl.com/settings/connected-apps/).

---

## Coexisting with Trakt / Bingebase

Each tracker has its own settings category and stores its token in a
separate file in the addon profile:

- `trakt_token.json`
- `bingebase_token.json`
- `simkl_token.json`

Enable any combination — they don't interfere. The player fires scrobble
events to all enabled trackers simultaneously.

## Troubleshooting

- **"SIMKL — client ID required" dialog** — you haven't pasted the
  `client_id` from step 2 into the settings yet.
- **"PIN expired / denied"** — the code only lives ~15 minutes. Try again.
- **Nothing scrobbling** — check `Settings → Debug → View debug log`. Lines
  prefixed with `SIMKL` will tell you what failed (most often a missing
  `client_id` or a 401 if the token was revoked).
- **Free vs commercial** — SIMKL API is free for non-commercial use and
  for apps making <$150/month. Personal Kodi installs are well under
  that threshold.

## Privacy

The token is stored only in your Kodi profile folder
(`userdata/addon_data/plugin.video.vidscr/simkl_token.json`). Nothing is
shared with the addon author. You can revoke access at any time at
https://simkl.com/settings/connected-apps/.
