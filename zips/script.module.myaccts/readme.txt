Debrid Manager
Pair multiple Debrid service(s) with supported add-ons via a single authorization point and easily manage the data for these service(s).


Instructions for adding this repo in Kodi:
Open the Kodi File Manager
Select "Add source"
The path for the source is https://zaxxon709.github.io/repo/ (Give it the name "709REPO")
How the addon works:
Once authorization is complete a check is done for each supported addon to confirm if the addon is installed and if settings.xml exists for that addon.
If both of these checks are true your debrid data is retrieved from Debrid Manager and applied to the supported addons.
During the authorization process a one time backup is also performed to save all Trakt & Debrid data to the default backup directory.

Note for users/builders:
For Debrid Manager to function correctly you need to ensure the directories containing the settings.xml for each supported addon are present in the addon_data directory.
Some addons do not create the settings.xml after installation. To create it the user first has to open the addon settings menu and then choose 'ok' for the file to be created. If it's not present Debrid Manager simply does nothing and moves on to the next addon. So make sure to add these to your build.

Backup/Restore Trakt & debrid Data:
The options to backup, restore and clear data can be found in Debrid Manager's settings menu.
The backup created during authorization only backs up current installed add-ons. If you decide to add additional supported addons you should create another backup to save data for those add-ons.
The default path is not perssitent after build updates or fresh starts. For builders i'd recommend your wizard data path for backups. For users i'd recommend whitelisting your backup directory. If the default path is changed make sure to complete another backup.
The default backup path can also be changed by the user at any time via the Debrid Manager settings menu.
Default Backup Path = special://userdata/addon_data/script.module.myaccts/


How to Authorize:
Open Debrid Manager and navigate to the debrid service of your choice
Select 'Authorize' and proceed to pair your account
Wait for the 'Sync is complete' notification and choose 'OK' to exit
All supported add-ons are now authorized

Authorize Built-in Commands:
Real-Debrid
RunScript(script.module.myaccts, action=realdebridAuth)

Premiumize
RunScript(script.module.myaccts, action=premiumizeAuth)

AllDebrid
RunScript(script.module.myaccts, action=alldebridAuth)


Sync Additional Addons:
If you decide to install additional supported add-ons you can sync them to your debrid account with 1-click!
Real-Debrid
RunScript(script.module.myaccts, action=realdebridReSync)

Premiumize
RunScript(script.module.myaccts, action=premiumizeReSync)

AllDebrid
RunScript(script.module.myaccts, action=alldebridReSync)


View/Manage Debrid Data:
This allows the user to see what addons are currently authorized and provides a 1-click option to revoke all authorizations.
Real-Debrid
ActivateWindow(10001,plugin://script.module.myauth/?mode=realdebrid,return)

Premiumize
ActivateWindow(10001,plugin://script.module.myauth/?mode=premiumize,return)

AllDebrid
ActivateWindow(10001,plugin://script.module.myauth/?mode=alldebrid,return)


Supported Services:
Real-Debrid
Premiumize
All-Debrid

Supported Addons:
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
Premiumizer
Realizer
My Accounts
ResolveURL
