Account Manager
An add-on to make the painful task of authorizing numerous add-ons effortless. Pair multiple service(s) with supported add-ons via a single authorization point and easily manage the data for these service(s).


Instructions for adding this repo in Kodi:
Open the Kodi File Manager
Select "Add source"
The path for the source is https://zaxxon709.github.io/repo/ (Give it the name "709REPO")
How the addon works:
Once authorization is complete a check is done for each supported addon to confirm if the addon is installed and if settings.xml exists for that addon.
If both of these checks are true your Trakt & Debrid data is retrieved from Account Manager and applied to the supported addons.
During the authorization process a one time backup is also performed to save all Trakt & Debrid data to the default backup directory.
Support for Custom API Keys:
Support has been added for your own Custom Trakt API keys. If you have your own keys, please use them. If you do not have keys then head on over to the Trakt website using the link below and create them.
https://trakt.tv/oauth/applications/new

Note for users/builders:
For Account Manager to function correctly you need to ensure the directories containing the settings.xml for each supported addon are present in the addon_data directory.
Some addons do not create the settings.xml after installation. To create it the user first has to open the addon settings menu and then choose 'ok' for the file to be created. If it's not present Account Manager simply does nothing and moves on to the next addon. So, make sure to add these to your build.
You'll find the option to use Custom Trakt API keys in the add-ons settings menu. I would appreciate it if builders would add their own keys to Account Manager prior to uploading their builds.
Backup/Restore Trakt & debrid Data:
The options to backup, restore and clear data can be found in Account Manager's settings menu.
The backup created during authorization only backs up current installed add-ons. If you decide to add additional supported addons you should create another backup to save data for those add-ons.
The default path is not persistent after build updates or fresh starts. For builders i'd recommend your wizard data path for backups. For users i'd recommend whitelisting your backup directory. If the default path is changed make sure to complete another backup.
The default backup path can also be changed by the user at any time via the Account Manager settings menu.
Default Backup Path = special://userdata/addon_data/plugin.program.accountmgr/

Restore all Add-ons to Default:
WARNING! Use only to restore system to default settings.
Open Account Manager and Navigate to the ‘Advanced’ category.
Select 'Restore Default Settings'
This action will delete all your saved data, revoke all add-ons and reset all supported add-ons back to default.

How to Authorize Debrid:
Open Account Manager
Navigate to the 'Accounts' category and choose your debrid service(s)
Select 'Authorize' and proceed to pair your account
Wait for the 'Sync is complete' notification and choose 'OK' to exit
All supported add-ons are now authorized!

How to Authorize Trakt:
Open Account Manager
Navigate to the 'Accounts' category and select ‘Authorize’ to pair your account
Wait for the 'Sync is complete' notification and when prompted choose 'OK' to force close Kodi
All supported add-ons are now authorized!

Authorize Built-in Commands:
Real-Debrid
RunScript(script.module.accountmgr, action=realdebridAuth)

Premiumize
RunScript(script.module.accountmgr, action=premiumizeAuth)

AllDebrid
RunScript(script.module.accountmgr, action=alldebridAuth)

Trakt
RunScript(script.module.accountmgr, action=traktAuth)


Sync Built-in Commands:
Real-Debrid
RunScript(script.module.accountmgr, action=realdebridReSync)

Premiumize
RunScript(script.module.accountmgr, action=premiumizeReSync)

AllDebrid
RunScript(script.module.accountmgr, action=alldebridReSync)

Trakt
RunScript(script.module.accountmgr, action=traktReSync)

Sync Multiple Debrid Accounts
RunScript(script.module.accountmgr, action=ReSyncAll)


View Authorized Add-ons Built-in Commands:
This allows the user to view what addons are currently authorized
Real-Debrid
ActivateWindow(10001,plugin://script.module.acctview/?mode=realdebrid,return)

Premiumize
ActivateWindow(10001,plugin://script.module.acctview/?mode=premiumize,return)

AllDebrid
ActivateWindow(10001,plugin://script.module.acctview/?mode=alldebrid,return)

Trakt
ActivateWindow(10001,plugin://script.module.acctview/?mode=trakt,return)

View Multiple Debrid Accounts
ActivateWindow(10001,plugin://script.module.acctview/?mode=allaccts,return)


Supported Services:
Real-Debrid
Premiumize
All-Debrid
Trakt

Supported Debrid Addons:
Seren
Ezra
Fen
POV
Umbrella
Shadow
Ghost
Unleashed
Chain Reaction
Twisted
Base19
Magic Dragon
Asgard
M.E.T.V
Aliunde
Adina
Artemis
Dynasty
Loonatics Empire
Premiumizer
Realizer
My Accounts
Your Accounts
ResolveURL

Supported Trakt Addons:
Ezra
Fen
POV
Umbrella
Shadow
Ghost
Unleashed
Chain Reaction
Base 19
Magic Dragon
Asgard
Patriot
Homelander
Quicksilver
Chains Genocide
Shazam
The Promise
The Crew
Nightwing
Alvin
Moria
Nine Lives
Scrubs V2
TMDb Helper
Trakt Add-on
My Accounts