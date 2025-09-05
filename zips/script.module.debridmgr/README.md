# Debrid Manager

A slimmed down version of Account Manager. Supports debrid accounts only.<br><br>

### 709 Repository
[![Download Repo](https://img.shields.io/badge/Download-Repo-blue.svg?style=for-the-badge)](https://raw.githubusercontent.com/Zaxxon709/nexus/main/repository.709-1.0.zip)<br>

### Instructions for adding this repo in Kodi:

<ul>
    <li>Open the Kodi File Manager</li>
    <li>Select "Add source"</li>
    <li>The path for the source is <code>https://zaxxon709.github.io/repo/</code> (Give it the name "709REPO")</li><br>
</ul>  


### Supported Services:


1.  Real-Debrid<br>
2.  Premiumize<br>
3.  All-Debrid<br>
4.  TorBox<br>
5.  Easy Debrid<br>
6.  OffCloud<br><br>


### Open Debrid Manager:

<p>RunAddon(script.module.debridmgr)</p><br>


### Authorize:<br>

<p>Real-Debrid<br>
RunScript(script.module.debridmgr, action=realdebridAuth)</p>

<p>Premiumize<br>
RunScript(script.module.debridmgr, action=premiumizeAuth)</p>

<p>AllDebrid<br>
RunScript(script.module.debridmgr, action=alldebridAuth)</p>

<p>TorBox<br>
RunScript(script.module.debridmgr, action=torboxAuth)</p>

<p>Easy Debrid<br>
RunScript(script.module.debridmgr, action=easydebridAuth)</p>

<p>OffCloud<br>
RunScript(script.module.debridmgr, action=offcloudAuth)</p><br>


### Sync:<br>

<p>Real-Debrid<br>
RunScript(script.module.debridmgr, action=realdebridReSync)</p>

<p>Premiumize<br>
RunScript(script.module.debridmgr, action=premiumizeReSync)</p>

<p>AllDebrid<br>
RunScript(script.module.debridmgr, action=alldebridReSync)</p>

<p>Sync Multiple Debrid Accounts<br>
RunScript(script.module.debridmgr, action=ReSyncAll)</p>

<p>TorBox<br>
RunScript(script.module.debridmgr, action=torboxReSync)</p>

<p>Easy Debrid<br>
RunScript(script.module.debridmgr, action=easydebridReSync)</p>

<p>OffCloud<br>
RunScript(script.module.debridmgr, action=offcloudReSync)</p><br>


### View Authorized Addons:<br>

<p>Real-Debrid<br>
ActivateWindow(10001,plugin://script.module.dbview/?mode=realdebrid,return)</p>

<p>Premiumize<br>
ActivateWindow(10001,plugin://script.module.dbview/?mode=premiumize,return)</p>

<p>AllDebrid<br>
ActivateWindow(10001,plugin://script.module.dbview/?mode=alldebrid,return)</p>

<p>View Multiple Debrid Accounts<br>
ActivateWindow(10001,plugin://script.module.dbview/?mode=allaccts,return)</p>

<p>TorBox<br>
ActivateWindow(10001,plugin://script.module.dbview/?mode=torbox,return)</p>

<p>Easy Debrid<br>
ActivateWindow(10001,plugin://script.module.dbview/?mode=easydebrid,return)</p>

<p>OffCloud<br>
ActivateWindow(10001,plugin://script.module.dbview/?mode=offcloud,return)</p>