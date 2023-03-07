# ============================================================
# KODI Banners - Version 3.0 by D. Lanik (2016)
# ------------------------------------------------------------
# Display banners when playing any video
# ------------------------------------------------------------
# License: GPL (http://www.gnu.org/licenses/gpl-3.0.html)
# ============================================================

import xbmc
import xbmcaddon
import xbmcgui
import os.path
from random import randint
from PIL import Image
from PIL import ImageGrab
from datetime import datetime as date
from threading import Timer
from xml.dom import minidom
from distutils.util import strtobool

# ============================================================
# Define Settings Monitor Class
# ============================================================


class SettingMonitor(xbmc.Monitor):
    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self)

    def onSettingsChanged(self):
        GetSettings()

# ============================================================
# Define Overlay Class
# ============================================================


class OverlayBanner(object):
    def __init__(self, windowid):
        self.showing = False
        self.window = xbmcgui.Window(windowid)
#        viewport_w, viewport_h = self._get_skin_resolution()

        pos = "20,20".split(",")
        pos_x = (viewport_w + int(pos[0]), int(pos[0]))[int(pos[0]) > 0]
        pos_y = (viewport_h + int(pos[1]), int(pos[1]))[int(pos[1]) > 0]
        self.imageTop = xbmcgui.ControlImage(pos_x, pos_y, 1240, 120, os.path.join("media", "banners", "generic_01.jpg"), aspectRatio=0)

        pos = "20,-140".split(",")
        pos_x = (viewport_w + int(pos[0]), int(pos[0]))[int(pos[0]) > 0]
        pos_y = (viewport_h + int(pos[1]), int(pos[1]))[int(pos[1]) > 0]
        self.imageBottom = xbmcgui.ControlImage(pos_x, pos_y, 1240, 120, os.path.join("media", "banners", "generic_01.jpg"), aspectRatio=0)

    def show(self):
        self.showing = True
        self.window.addControl(self.imageBottom)
        self.window.addControl(self.imageTop)

    def hide(self):
        self.showing = False
        self.window.removeControl(self.imageBottom)
        self.window.removeControl(self.imageTop)

    def scaleimage(self, width, height, yoffset):
#        viewport_w, viewport_h = self._get_skin_resolution()

        if width > viewport_w:
            if yoffset > 0:
                width = viewport_w - (yoffset * 2)
                xpos = yoffset
            else:
                width = viewport_w
                xpos = 0
        else:
            xpos = (viewport_w - width) / 2

        ypos = viewport_h - height - yoffset

        xbmc.log("BANNERS >> BANNER POSITION >> " + str(int(xpos)) + "x" + str(int(ypos)))

        self.imageBottom.setHeight(height)
        self.imageBottom.setWidth(width)
        self.imageBottom.setPosition(int(xpos), int(ypos))

        self.imageTop.setHeight(height)
        self.imageTop.setWidth(width)
        self.imageTop.setPosition(int(xpos), int(yoffset))

    def _close(self):
        if self.showing:
            self.hide()
        else:
            pass

        try:
            self.window.clearProperties()
        except Exception:
            pass

# ============================================================
# Get resolution
# ============================================================

    def _get_skin_resolution(self):
        xmlFile = os.path.join(xbmc.translatePath("special://skin/"), "addon.xml")
        xmldoc = minidom.parse(xmlFile)

        res = xmldoc.getElementsByTagName("res")
        xval = int(res[0].attributes["width"].value)
        yval = int(res[0].attributes["height"].value)

        xbmc.log("BANNERS >> RESOLUTION >> " + str(int(xval)) + " x " + str(int(yval)))
        return(xval, yval)

# ============================================================
# Class for timer
# ============================================================


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False

# ============================================================
# Class for KODI player
# ============================================================


class XBMCPlayer(xbmc.Player):
    global rt
    global booDisplayBanner

    def __init__(self, *args):
        pass

    def onPlayBackStarted(self):
        if booDisplayBanner:
            xbmc.log("BANNERS >> PLAYBACK >>PLAYING<<")
            OnPlay()

    def onPlayBackPaused(self):
        if booDisplayBanner:
            xbmc.log("BANNERS >> PLAYBACK >>PAUSED<<")
            OnStop()

    def onPlayBackResumed(self):
        if booDisplayBanner:
            xbmc.log("BANNERS >> PLAYBACK >>RESUMED<<")
            OnPlay()

    def onPlayBackEnded(self):
        if booDisplayBanner:
            xbmc.log("BANNERS >> PLAYBACK >>ENDED<<")
            OnStop()

    def onPlayBackStopped(self):
        if booDisplayBanner:
            xbmc.log("BANNERS >> PLAYBACK >>STOPPED<<")
            OnStop()


# ============================================================
# Player - play
# ============================================================


def OnPlay():
    global __addonwd__
    global rt
    global strBanners
    global intCounterBanner
    global booRandom
    global myWidget
    global booDisplayBanner
    global intYOffset

    condition = xbmc.getCondVisibility('Player.HasMedia')
    is_video = xbmc.getCondVisibility('Player.HasVideo')

    if condition and is_video and booDisplayBanner:
        if booRandom:
            intDisplayBanner = randint(0, intBanners - 1)
        else:
            intDisplayBanner = intCounterBanner

        rt.start()

        try:
            myWidget.show()

            image = Image.open(open(strBanners[intDisplayBanner], 'rb'))
            width, height = image.size
            myWidget.scaleimage(width, height, intYOffset)

            if intBannerpos == 0:
                myWidget.imageBottom.setImage("")
                myWidget.imageTop.setImage(strBanners[intDisplayBanner])
            else:
                myWidget.imageBottom.setImage(strBanners[intDisplayBanner])
                myWidget.imageTop.setImage("")

            xbmc.log("BANNERS >> BANNER RANDOM: [" + str(booRandom) + "] CHANGE TO " + str(intDisplayBanner) + " > " + strBanners[intDisplayBanner])
        except Exception:
            pass

# ============================================================
# Player - stop
# ============================================================


def OnStop():
    global rt
    global myWidget

    rt.stop()

    try:
        myWidget.hide()
    except Exception:
        pass

    xbmc.log("BANNERS >> BANNER OFF")

# ============================================================
# To be repeated every x seconds - shuffle banners
# ============================================================


def hw():
    global __addon__
    global __addonwd__
    global strBanners
    global intBanners
    global intCounterBanner
    global intCyclePause
    global booRandom
    global myWidget
    global intYOffset

    condition = xbmc.getCondVisibility('Player.HasMedia')
    is_video = xbmc.getCondVisibility('Player.HasVideo')
    ActWin = xbmcgui.getCurrentWindowId()

    if condition and is_video and ActWin == 12005:
        intCounterBanner += 1
        if intCounterBanner == intBanners:
            intCounterBanner = 0

        if booRandom:
            intDisplayBanner = randint(0, intBanners - 1)
        else:
            intDisplayBanner = intCounterBanner

        if intCounterBanner == 0 and intCyclePause > 0:     # 1st banner is being displayed - time for pause
            xbmc.log("BANNERS >> BANNER CYCLE PAUSE - WAITING " + str(intCyclePause) + " SECONDS")

            rt.stop()
            myWidget.hide()
            xbmc.sleep(intCyclePause * 1000)
            myWidget.show()
            rt.start()

        xbmc.log("BANNERS >> BANNER RANDOM: [" + str(booRandom) + "] CHANGE TO " + str(intDisplayBanner) + " > " + strBanners[intDisplayBanner])

        image = Image.open(open(strBanners[intDisplayBanner], 'rb'))
        width, height = image.size
        myWidget.scaleimage(width, height, intYOffset)

        if intBannerpos == 0:
            myWidget.imageBottom.setImage("")
            myWidget.imageTop.setImage(os.path.join(__addonwd__, "media", "banners", '%s' % strBanners[intDisplayBanner]))
        else:
            myWidget.imageBottom.setImage(os.path.join(__addonwd__, "media", "banners", '%s' % strBanners[intDisplayBanner]))
            myWidget.imageTop.setImage("")

# ============================================================
# Get extension
# ============================================================


def get_extension(filename):
    ext = os.path.splitext(filename)[1][1:].strip()
    return ext

# ============================================================
# Get settings
# ============================================================


def GetSettings():
    global __addon__
    global __addonwd__
    global __addonname__
    global rt
    global intChange
    global strBanners
    global intBanners
    global intBannerpos
    global myWidget
    global booDisplayBanner
    global intCyclePause
    global intYOffset
    global booRandom
    global intCounterBanner

    try:
        rt.stop()
        rt = None
    except Exception:
        pass

    rt = None
    __addon__ = xbmcaddon.Addon(id='service.banners')

    strBanners = []
    intChange = int(__addon__.getSetting('changetime'))
    intBannerpos = int(__addon__.getSetting('bannerpos'))
    booDisplayBanner = bool(strtobool(str(__addon__.getSetting('on').title())))
    intCyclePause = int(__addon__.getSetting('cyclepause'))
    intYOffset = int(__addon__.getSetting('yoffset'))
    booRandom = bool(strtobool(str(__addon__.getSetting('random').title())))

    path = os.path.join(__addondir__, 'mybanners')      # check if own banners exist
    booOwnBanners = False                               # for the time being, they don't :)

    for root, subdirs, files in os.walk(path):
        for name in files:
            fileExt = get_extension(name)
            if any(fileExt.lower() in i for i in ("jpg", "jpeg", "png", "gif")):
                booOwnBanners = True                    # aha, found own banner
                break                                   # that's enough, break out of loop
        break

    today = date.today().strftime("%A")
    path = os.path.join(__addondir__, 'mybanners', today)      # check if own banners by day exist
    booDayBanners = False                                      # for the time being, they don't :)

    for root, subdirs, files in os.walk(path):
        for name in files:
            fileExt = get_extension(name)
            if any(fileExt.lower() in i for i in ("jpg", "jpeg", "png", "gif")):
                booDayBanners = True                    # aha, found own day banner
                break                                   # that's enough, break out of loop
        break

    if booDayBanners:
        path = os.path.join(__addondir__, 'mybanners', today)
    elif booOwnBanners:
        path = os.path.join(__addondir__, 'mybanners')
    else:
        path = os.path.join(__addonwd__, 'media', 'banners')

    for root, subdirs, files in os.walk(path):
        for name in files:
            fileExt = get_extension(name)
            if any(fileExt.lower() in i for i in ("jpg", "jpeg", "png", "gif")):
                strBanners.append(os.path.join(path, name))
        break

    intBanners = len(strBanners)
    intCounterBanner = 0

    xbmc.log("BANNERS >> SETTINGS >> BANNERS READ >> " + str(intBanners))
    xbmc.log("BANNERS >> SETTINGS >> BANNER POSITION >> " + str(intBannerpos))
    xbmc.log("BANNERS >> SETTINGS >> CHANGE EVERY SECONDS >> " + str(intChange))
    xbmc.log("BANNERS >> SETTINGS >> PAUSE BETWEEN CYCLES >> " + str(intCyclePause))
    xbmc.log("BANNERS >> SETTINGS >> X+Y OFFSET >> " + str(intYOffset))
    xbmc.log("BANNERS >> SETTINGS >> BANNER ON >> " + str(booDisplayBanner))
    xbmc.log("BANNERS >> SETTINGS >> RANDOM >> " + str(booRandom))

    rt = RepeatedTimer(intChange, hw)
    rt.stop()

    try:
        myWidget.imageBottom.setImage("")
        myWidget.imageTop.setImage("")
        myWidget.hide()
    except Exception:
        pass

    OnPlay()

# ============================================================
# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
# ============================================================


__addon__ = xbmcaddon.Addon(id='service.banners')
__addonname__ = __addon__.getAddonInfo('name')
__addonwd__ = xbmc.translatePath(__addon__.getAddonInfo('path'))
__addondir__ = xbmc.translatePath(__addon__.getAddonInfo('profile'))
__version__ = __addon__.getAddonInfo('version')

booOverlayInit = False
intChange = 5
strBanners = []
intBanners = 0
intCounterBanner = 0
intBannerpos = 0
booDisplayBanner = True
intCyclePause = 15
intYOffset = 15
booRandom = False

img = ImageGrab.grab()
xbmc.log("BANNERS >> SCREEN SIZE >> " + str(img.size))
viewport_w = img.size[0]
viewport_h = img.size[1]

rt = None

if __name__ == '__main__':
    xbmc.log("BANNERS >> STARTED VERSION %s" % (__version__))

    folder = os.path.join(__addondir__, 'mybanners')
    if not os.path.exists(folder):
        os.makedirs(folder)

    GetSettings()

    player = XBMCPlayer()
    monitor = xbmc.Monitor()
    monsettings = SettingMonitor()

    while True:
        if monitor.waitForAbort(1):    # Sleep/wait for abort
            rt.stop()
            try:
                myWidget._close()
            except Exception:
                pass

            xbmc.log('BANNERS >> EXIT')
            break                      # Abort was requested while waiting. Exit the while loop.
        elif not booOverlayInit:
            ActWin = xbmcgui.getCurrentWindowId()
            if ActWin == 12005:
                try:
                    x = myWidget
                except NameError:
                    booOverlayInit = True
                    myWidget = OverlayBanner(12005)     # 12005: fullscreenvideo
                    OnPlay()
                    xbmc.log('BANNERS >> INITIALIZING OVERLAY')
                finally:
                    x = None

# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
