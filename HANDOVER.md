# Handover: Nokia E63 project

Read this first. It summarizes the earlier cloud session.

## Goal
Make an old Nokia E63 useful in 2026: calls, plus internet services relayed through the PC **Edith** (Windows), which does the heavy work and serves simple pages the phone can open.

## Rules from the user
- Work only in `E:\PROJECTS\Nokia_E63`.
- Short, direct answers. Don't guess: verify facts that aren't certain. Ask right away if info is missing.
- Git branch: `claude/youthful-cray-e5dfk5` (remote: `github.com/ahanaf-adil/Nokia_E63`). Don't open PRs unless asked.

## Phone facts that matter
- Symbian OS 9.2 / S60 3.1, ARM11 369 MHz, 320×240 screen, QWERTY keyboard.
- Wi-Fi: 802.11b/g on 2.4 GHz only. Supports WPA2; WPA3-only or 5 GHz networks won't work.
- TLS: the system TLS stack reportedly stops at TLS 1.0, so modern HTTPS sites fail. The PC must fetch HTTPS and serve the phone **plain HTTP**.
- Video (RealPlayer): spec sites list only H.263 and MPEG-4 Visual (VSP) in MP4/3GP. No H.264 confirmed.
- Cellular: 2G/3G only (no 4G/VoLTE). Whether calls work depends on the local carrier. The user's country/carrier isn't known yet.
- Java ME (MIDP 2.0) apps run.

## Decided
- **No custom OS for the phone.** I found no Linux port and almost no hardware docs; a bootloader and drivers would have to be written from scratch.
- **Proxy-style servers on Edith** are the approach, one service at a time.
- Ready-made YouTube options rejected: official app (dead), JTube (reported abandoned/broken, 2025), yt2009 (exists, but Symbian support unconfirmed).
- General web browsing options for later: **WRP** (renders pages as images, github.com/tenox7/wrp) or **WebOne** (HTTPS→HTTP proxy, github.com/atauenis/webone).

## Done: `e63tube.py` (YouTube)
- One file, Python standard library only. Needs `yt-dlp` and `ffmpeg` on PATH.
- Pages: `/` (search box), `/search?q=` (yt-dlp `ytsearch15`), `/watch?v=ID` (converts in a background thread; the page refreshes every 10 s), `/video/ID.mp4`.
- Conversion: yt-dlp `best[height<=360]` → ffmpeg MPEG-4 320px wide, 15 fps, 300k video; AAC 64k mono 22.05 kHz; `+faststart`. Bitrates are in `FFMPEG_OUT`.
- Video IDs are checked with a regex `[A-Za-z0-9_-]{11}`, which blocks path tricks. Cache folder: `cache/` (in .gitignore).
- Known limits (`ponytail:` comments in the code): the converting list is lost on restart; videos are sent as a whole file with no Range/seek support.
- **Tested in the cloud:** `python e63tube.py test` passed (ffmpeg output is mpeg4 320×180 + aac); the server answered `/`, rejected bad IDs with 400 and returned 404 for path traversal.
- **Not tested yet:** real yt-dlp search/download (no YouTube access in the cloud), and playback on the actual phone.

## Next steps on Edith
1. Install anything missing: `winget install Python.Python.3.12 Gyan.FFmpeg yt-dlp.yt-dlp` (yt-dlp and FFmpeg IDs verified; Python ID from memory), then reopen the terminal.
2. `python e63tube.py test`
3. Open the firewall (admin): `netsh advfirewall firewall add rule name="E63Tube" dir=in action=allow protocol=TCP localport=8063`
4. `python e63tube.py`. Find Edith's IPv4 with `ipconfig`; the phone opens `http://<ip>:8063/`.
5. Test on the phone. If it fails, check whether the browser hands `video/mp4` to RealPlayer and whether the codec/bitrate needs changing (H.263 / 3GP is the fallback).
6. Later ideas: news/text browsing (WRP/WebOne), music, messaging bridge. Maps are limited because the phone has no GPS.
