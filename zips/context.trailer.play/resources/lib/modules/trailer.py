# -*- coding: utf-8 -*-

import random
import requests
import xbmc
import xbmcaddon
import xbmcgui
try: #Py2
	from urllib import quote_plus
except ImportError: #Py3
	from urllib.parse import quote_plus
from resources.lib.modules import tools


class Trailer:
	def __init__(self):
		self.key = xbmcaddon.Addon('plugin.video.youtube').getSetting('youtube.api.key')
		if self.key == '': self.key = random.choice([
			'AIzaSyBW-Z3TneLX-aG9TC5G061BTc9bBgftmPA'
			'AIzaSyA0LiS7G-KlrlfmREcCAXjyGqa_h_zfrSE',
			'AIzaSyDgcri5Aipa9EBeE48IJAYyd71aiPOpwWw',
			'AIzaSyBOXZVC-xzrdXSAmau5UM3rG7rc8eFIuFw'])
		self.key_link = '&key=%s' % self.key
		self.search_link = 'https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&maxResults=15&q=%s' + self.key_link


	def play(self, type, name, year, windowedtrailer=0):
		tools.busy()
		try:
			url = self.worker(type, name, year)
			if not url: return
			xbmc.executebuiltin("PlayMedia(%s)" % (url))
			if windowedtrailer == 1:
				xbmc.sleep(100)
				while xbmc.Player().isPlayingVideo():
					xbmc.sleep(100)
				xbmc.executebuiltin("Dialog.Close(%s, true)" % xbmcgui.getCurrentWindowDialogId())
		except:
			import traceback
			traceback.print_exc()


	def worker(self, type, name, year):
		query = name + ' ' + str(year) + ' trailer'
		# query = name + ' ' + str(year) + ' review' # may incorporate later but not at cost of 2 requests
		query = self.search_link % quote_plus(query)
		return self.search(query)


	def search(self, url):
		try:
			apiLang = tools.apiLanguage().get('youtube', 'en')
			if apiLang != 'en': url += "&relevanceLanguage=%s" % apiLang
			response = requests.get(url).json()
			error =  response.get('error', [])
			if error:
				tools.hide()
				message = error.get('message', [])
				icon = xbmcaddon.Addon('plugin.video.youtube').getAddonInfo('icon')
				xbmcgui.Dialog().notification('YOUTUBE', message, icon=icon)
				return None

			json_items = response.get('items', [])
			items = [i.get('id', {}).get('videoId') for i in json_items]

			labels = [i.get('snippet', {}).get('title') for i in json_items]
			labels = [tools.replaceHTMLCodes(i) for i in labels]
			tools.hide()
			select = xbmcgui.Dialog().select('YOUTUBE TRAILERS:', labels)
			if select == -1: return None
			item = [items[select]]

			for vid_id in item:
				url = 'plugin://plugin.video.youtube/play/?video_id=%s' % vid_id
				return url
		except:
			import traceback
			traceback.print_exc()
			tools.hide()