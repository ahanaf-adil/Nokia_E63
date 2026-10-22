# E63Tube

YouTube for the Nokia E63, served from a PC on the same Wi-Fi.

The PC searches and downloads with `yt-dlp`, converts to MPEG-4 320px / AAC (what the E63's RealPlayer plays), and serves plain HTTP pages the old browser can open. Search results show thumbnails. Each video can be saved as audio (MP3) or video (MP4), or streamed over RTSP.

## Setup (on the PC)
1. Install Python 3.8+ and [ffmpeg](https://ffmpeg.org/download.html) (on PATH).
2. Put these in `bin/` next to `e63tube.py` (not in git; the script puts `bin/` first on PATH):
   - `yt-dlp.exe` from [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases)
   - `deno.exe` from [Deno releases](https://github.com/denoland/deno/releases) (yt-dlp needs a JS runtime for YouTube)
   - `mediamtx.exe` from [MediaMTX releases](https://github.com/bluenviron/mediamtx/releases) (RTSP streaming; config in `mediamtx.yml`)
3. `python e63tube.py test` (self-check)
4. `python e63tube.py` (also starts MediaMTX)
5. Allow in the PC firewall: TCP 8063 (pages/downloads), TCP 8554 and UDP 8000-8001 (streaming).

If the PC runs a VPN, YouTube may block downloads ("confirm you're not a bot"): exclude `bin\yt-dlp.exe` with split tunnelling and allow LAN access.

## On the phone
Open `http://<pc-ip>:8063/`, search, pick a video, then choose:
- **Audio (MP3)**: 96 kbps MP3 for the music player, the smallest download.
- **Video (MP4)**: MPEG-4 320px for RealPlayer.
- **Stream**: plays in RealPlayer over RTSP without saving (buffers, no seeking).

Audio and Video convert on the PC first; the page refreshes until **Download / play** appears.

Keep yt-dlp updated (`bin\yt-dlp.exe -U`); YouTube changes break old versions. LAN only: don't port-forward this.
