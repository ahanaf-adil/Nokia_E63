# E63Tube

YouTube for the Nokia E63, served from a PC on the same Wi-Fi.

The PC searches and downloads with `yt-dlp`, converts to MPEG-4 320px / AAC (what the E63's RealPlayer plays), and serves plain HTTP pages the old browser can open.

## Setup (on the PC)
1. Install Python 3.8+, [ffmpeg](https://ffmpeg.org/download.html) and [yt-dlp](https://github.com/yt-dlp/yt-dlp) (all on PATH).
2. `python e63tube.py test` (self-check)
3. `python e63tube.py`
4. Allow port 8063 in the PC firewall.

## On the phone
Open `http://<pc-ip>:8063/`, search, pick a video, wait for conversion, tap **Play / download**.

Keep yt-dlp updated (`yt-dlp -U`); YouTube changes break old versions. LAN only: don't port-forward this.
