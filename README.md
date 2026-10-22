# E63Tube

YouTube and PC file transfer for the Nokia E63, served from a PC on the same Wi-Fi.

The PC searches and downloads with `yt-dlp`, converts to formats the E63 plays, and serves plain HTTP pages the old browser can open. Search results show thumbnails. Each video can be saved as audio or video, or streamed over RTSP. Files you put in the PC's `send/` folder can be downloaded to the phone a whole folder at a time.

## Setup (on the PC)
1. Install Python 3.8+ and [ffmpeg](https://ffmpeg.org/download.html) (on PATH).
2. Put these in `bin/` next to `e63tube.py` (not in git; the script puts `bin/` first on PATH):
   - `yt-dlp.exe` from [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases)
   - `deno.exe` from [Deno releases](https://github.com/denoland/deno/releases) (yt-dlp needs a JS runtime for YouTube)
   - `mediamtx.exe` from [MediaMTX releases](https://github.com/bluenviron/mediamtx/releases) (RTSP streaming; config in `mediamtx.yml`)
3. `python e63tube.py test` (self-check)
4. `python e63tube.py` (also starts MediaMTX and creates `send/`)
   To start it automatically at boot (no login needed), run `autostart.ps1` once from an elevated PowerShell. Output goes to `cache\server.log`.
5. Allow in the PC firewall: TCP 8063 (pages/downloads), TCP 8554 and UDP 8000-8001 (streaming).

If the PC runs a VPN, YouTube may block downloads ("confirm you're not a bot"): exclude `bin\yt-dlp.exe` with split tunnelling and allow LAN access.

## On the phone: YouTube
Open `http://<pc-ip>:8063/`, search, pick a video, then choose:
- **Audio**: AAC 64 kbps stereo `.m4a`, about 0.5 MB per minute (smallest; the E63 plays AAC/M4A). **MP3, larger** (96 kbps) is the fallback if `.m4a` won't play.
- **Video (MP4)**: MPEG-4 320px for RealPlayer.
- **Stream**: plays in RealPlayer over RTSP without saving (buffers, no seeking).

Audio and Video convert on the PC first; the page refreshes until **Download / play** appears.

## On the phone: PC files
1. On the PC, copy songs (or anything) into `send/`, in folders if you like.
2. On the phone, open **PC files**, go to a folder and pick:
   - **Download all, shrunk for phone (ZIP)**: audio files are re-encoded to the same 64 kbps AAC `.m4a` while packing (a 320 kbps MP3 shrinks to about a fifth); other files are added as they are.
   - **Download all, original files (ZIP)**: everything unchanged.
   Single files can also be downloaded from the list.
3. Open the ZIP with the phone's **Zip manager** and extract it to the memory card. The ZIP is stored, not compressed, so extracting is quick.

ZIPs are built once and cached; adding or changing a file in the folder makes a new one.

## Batch songs from a list (on the PC)
Write a playlist file, one `Artist - Title` per line, then:
`python songs.py send\playlist.txt send\Songs`
Each song is found via a YouTube lyrics-video search (studio audio, no video intros), checked that the result's title contains the song title, converted to the same 64 kbps AAC `.m4a` and tagged. Add `[no lyrics]` for instrumentals and `=> Name` for the name shown on the phone (e.g. romanised Korean, which the E63 can't display). Matches are logged in `_matches.txt`; songs already done are skipped. Copy the results to the card's `Sounds\Digital` folder or download them via **PC files**.

Keep yt-dlp updated (`bin\yt-dlp.exe -U`); YouTube changes break old versions. LAN only: don't port-forward this.
