# Kodi GitHub virtual repository

This repository is a fork of a [i96751414's](https://github.com/i96751414) https://github.com/i96751414/repository.github project with minor changes. Many thanks for this project.

This add-on creates a virtual repository for Kodi. This way, one does not need to use a GitHub repository for storing
add-ons zips when all that information is already accessible from each add-on repository.


It works by setting an HTTP server which has the following endpoints:

| Endpoint                                        | Description                                                  |
|-------------------------------------------------|--------------------------------------------------------------|
| http://127.0.0.1:{port}/addons.xml              | Main xml file containing all add-ons information             |
| http://127.0.0.1:{port}/addons.xml.md5          | Checksum of the main xml file                                |
| http://127.0.0.1:{port}/{addon_id}/{asset_path} | Endpoint for serving add-ons assets/zips                     |
| http://127.0.0.1:{port}/update                  | Endpoint for updating repository entries and clearing caches |

## Installation

Get the [latest release](https://github.com/elementumorg/repository.elementumorg/releases/latest) from github.
Then, [install from zip](https://kodi.wiki/view/Add-on_manager#How_to_install_from_a_ZIP_file) within [Kodi](https://kodi.tv/).

## Add-on entries

In order to know which repositories to proxy, the virtual repository needs to be provided with a _list of add-on
entries_.
An example can be found [here](resources/repository.json).
Each entry must follow the following schema (also available as [json schema](resources/repository-schema.json)):

| Property     | Required | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
|--------------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| id           | true     | Add-on id.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| username     | true     | GitHub repository username.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| branch       | false    | The github repository branch. If not defined, it will be either <br>1) the commit of the latest release, <br>2) the respective tag, <br>3) the repository default branch, or <br>4) if all the previous are unable to fetch, "main" branch.                                                                                                                                                                                                                                                                                             |
| assets       | false    | Dictionary containing string/string key-value pairs, where the key corresponds to the relative asset location and the value corresponds to the real asset location. One can also set "zip" asset, which is a special case for the add-on zip. If an asset is not defined, its location will be automatically evaluated.<br><br>Note: assets are treated as "new style" format strings with the following keywords - _id_, _username_, _repository_, _ref_, _system_, _arch_ and _version_ (_version_ is available for zip assets only). |
| asset_prefix | false    | Prefix to use on the real asset location when it is automatically evaluated.                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| repository   | false    | GitHub repository name. If not set, it is assumed to be the same as the add-on id.                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| tag_pattern  | false    | The pattern for matching eligible tags. If not set, all tags are considered.                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| token        | false    | The token to use for accessing the repository. If not provided, the repository must have public access.                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| platforms    | false    | Platforms where the add-on is supported. If not set, it is assumed all platforms are supported.                                                                                                                                                                                                                                                                                                                                                                                                                                         |
