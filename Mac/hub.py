"""The JARVIS hub: a window for JARVIS's status and settings (ui/hub.html, run by hub_api.py).

Open it from the tray menu (Open hub), with "Open JARVIS Hub.bat", or:  python hub.py
It is a separate program, so it works whether or not JARVIS is running.
"""
import os

from hub_api import HubApi

UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui', 'hub.html')


def main():
    import webview
    api = HubApi()
    width, height = 1180, 760
    screen = webview.screens[0]  # the main screen; pywebview would otherwise open it top-left
    api._window = webview.create_window('JARVIS hub', url=UI_FILE, js_api=api, width=width, height=height,
                                        x=screen.x + max((screen.width - width) // 2, 0),
                                        y=screen.y + max((screen.height - height) // 2, 0),
                                        min_size=(980, 640), background_color='#0B0D0F')
    webview.start()


if __name__ == '__main__':
    main()
