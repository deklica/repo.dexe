# -*- coding: utf-8 -*-

from re import sub as re_sub
import xbmc
import xbmcaddon
try: #Py2
	from HTMLParser import HTMLParser
	unescape = HTMLParser().unescape
	def iteritems(d, **kw):
		return d.iteritems(**kw)
except ImportError: #Py3
	from html import unescape
	def iteritems(d, **kw):
		return iter(d.items(**kw))

def apiLanguage(ret_name=None):
	langDict = {'Bulgarian': 'bg', 'Chinese': 'zh', 'Croatian': 'hr', 'Czech': 'cs', 'Danish': 'da', 'Dutch': 'nl',
						'English': 'en', 'Finnish': 'fi', 'French': 'fr', 'German': 'de', 'Greek': 'el', 'Hebrew': 'he',
						'Hungarian': 'hu', 'Italian': 'it', 'Japanese': 'ja', 'Korean': 'ko', 'Norwegian': 'no', 'Polish': 'pl',
						'Portuguese': 'pt', 'Romanian': 'ro', 'Russian': 'ru', 'Serbian': 'sr', 'Slovak': 'sk',
						'Slovenian': 'sl', 'Spanish': 'es', 'Swedish': 'sv', 'Thai': 'th', 'Turkish': 'tr', 'Ukrainian': 'uk'}
	youtube = ['gv', 'gu', 'gd', 'ga', 'gn', 'gl', 'ty', 'tw', 'tt', 'tr', 'ts', 'tn', 'to', 'tl', 'tk', 'th', 'ti',
						'tg', 'te', 'ta', 'de', 'da', 'dz', 'dv', 'qu', 'zh', 'za', 'zu', 'wa', 'wo', 'jv', 'ja', 'ch', 'co',
						'ca', 'ce', 'cy', 'cs', 'cr', 'cv', 'cu', 'ps', 'pt', 'pa', 'pi', 'pl', 'mg', 'ml', 'mn', 'mi', 'mh',
						'mk', 'mt', 'ms', 'mr', 'my', 've', 'vi', 'is', 'iu', 'it', 'vo', 'ii', 'ik', 'io', 'ia', 'ie', 'id',
						'ig', 'fr', 'fy', 'fa', 'ff', 'fi', 'fj', 'fo', 'ss', 'sr', 'sq', 'sw', 'sv', 'su', 'st', 'sk', 'si',
						'so', 'sn', 'sm', 'sl', 'sc', 'sa', 'sg', 'se', 'sd', 'lg', 'lb', 'la', 'ln', 'lo', 'li', 'lv', 'lt',
						'lu', 'yi', 'yo', 'el', 'eo', 'en', 'ee', 'eu', 'et', 'es', 'ru', 'rw', 'rm', 'rn', 'ro', 'be', 'bg',
						'ba', 'bm', 'bn', 'bo', 'bh', 'bi', 'br', 'bs', 'om', 'oj', 'oc', 'os', 'or', 'xh', 'hz', 'hy', 'hr',
						'ht', 'hu', 'hi', 'ho', 'ha', 'he', 'uz', 'ur', 'uk', 'ug', 'aa', 'ab', 'ae', 'af', 'ak', 'am', 'an',
						'as', 'ar', 'av', 'ay', 'az', 'nl', 'nn', 'no', 'na', 'nb', 'nd', 'ne', 'ng', 'ny', 'nr', 'nv', 'ka',
						'kg', 'kk', 'kj', 'ki', 'ko', 'kn', 'km', 'kl', 'ks', 'kr', 'kw', 'kv', 'ku', 'ky']
	name = None
	name = xbmcaddon.Addon().getSetting('api.language')
	if not name: name = 'AUTO'
	if name[-1].isupper():
		try: name = xbmc.getLanguage(xbmc.ENGLISH_NAME).split(' ')[0]
		except: pass
	try: name = langDict[name]
	except: name = 'en'
	lang = {'youtube': name} if name in youtube else {'youtube': 'en'}
	if ret_name:
		lang['youtube'] = [i[0] for i in iteritems(langDict) if i[1] == lang['youtube']][0]
	return lang

def replaceHTMLCodes(txt):
	# Some HTML entities are encoded twice. Decode double.
	return _replaceHTMLCodes(_replaceHTMLCodes(txt))

def _replaceHTMLCodes(txt):
	if not txt: return ''
	txt = re_sub("(&#[0-9]+)([^;^0-9]+)", "\\1;\\2", txt)
	txt = unescape(txt)
	txt = txt.replace("&quot;", "\"")
	txt = txt.replace("&amp;", "&")
	txt = txt.replace("&lt;", "<")
	txt = txt.replace("&gt;", ">")
	txt = txt.replace("&#38;", "&")
	txt = txt.replace("&nbsp;", "")
	txt = txt.replace('&#8230;', '...')
	txt = txt.replace('&#8217;', '\'')
	txt = txt.replace('&#8211;', '-')
	txt = txt.strip()
	return txt

def getKodiVersion():
	return int(xbmc.getInfoLabel("System.BuildVersion")[:2])

def busy():
	if getKodiVersion() >= 18:
		return xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
	else: return xbmc.executebuiltin('ActivateWindow(busydialog)')

def hide():
	if getKodiVersion() >= 18 and xbmc.getCondVisibility('Window.IsActive(busydialognocancel)'):
		return xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
	else: return xbmc.executebuiltin('Dialog.Close(busydialog)')