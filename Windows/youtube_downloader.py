"""Downloads a YouTube video to the Downloads folder with yt-dlp (pytube no longer works
with YouTube). Say "download the YouTube video I copied", or run:
    python youtube_downloader.py <url>
"""
import os
import re
import sys

URL = re.compile(r'https?://(www\.|m\.)?(youtube\.com|youtu\.be)/\S+')


def download(url: str = '', folder: str = '') -> str:
    if not url:
        import pyperclip
        url = (pyperclip.paste() or '').strip()
    if not URL.match(url or ''):
        return 'Copy a YouTube link first, then ask again.'
    import yt_dlp
    folder = folder or os.path.join(os.path.expanduser('~'), 'Downloads')
    # A single file with picture and sound, so no ffmpeg is needed to merge them.
    options = {'format': 'best[ext=mp4]/best', 'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
               'quiet': True, 'noprogress': True, 'noplaylist': True}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
    return f'Downloaded "{info.get("title", "the video")}" to {folder}.'


if __name__ == '__main__':
    print(download(sys.argv[1] if len(sys.argv) > 1 else ''))
