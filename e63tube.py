"""YouTube for the Nokia E63: search + convert to a phone-playable MP4.

Run on the PC (needs yt-dlp and ffmpeg on PATH), then open
http://<pc-ip>:8063/ in the phone's browser.
"""
import html
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8063
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

# E63 RealPlayer: MPEG-4 Visual / H.263 only (no H.264), 320x240 screen.
# Tune bitrates here if playback stutters or quality is too low.
FFMPEG_OUT = ["-vf", "scale=320:-2", "-r", "15", "-c:v", "mpeg4", "-b:v", "300k",
              "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "22050",
              "-movflags", "+faststart"]

converting = set()  # ponytail: in-memory, lost on restart; leftover .part files get redone


def page(body):
    return ("<html><head><meta http-equiv='Content-Type' content='text/html; charset=utf-8'>"
            "<title>E63Tube</title></head><body>"
            "<form action='/search'><input name='q'><input type='submit' value='Search'></form>"
            f"{body}</body></html>").encode()


def search(q):
    out = subprocess.run(["yt-dlp", "--flat-playlist", "--print", "%(id)s\t%(title)s",
                          f"ytsearch15:{q}"], capture_output=True, text=True, timeout=60).stdout
    return [line.split("\t", 1) for line in out.splitlines() if "\t" in line]


def convert(vid):
    src = os.path.join(CACHE, vid + ".src")
    part = os.path.join(CACHE, vid + ".part.mp4")
    try:
        subprocess.run(["yt-dlp", "-f", "best[height<=360]/worst", "-o", src, "--force-overwrites",
                        f"https://www.youtube.com/watch?v={vid}"], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", src, *FFMPEG_OUT, part], check=True, capture_output=True)
        os.replace(part, os.path.join(CACHE, vid + ".mp4"))
    except subprocess.CalledProcessError as e:
        print(f"convert {vid} failed:", e.stderr.decode(errors="replace")[-500:], file=sys.stderr)
    finally:
        if os.path.exists(src):
            os.remove(src)
        converting.discard(vid)


class Handler(BaseHTTPRequestHandler):
    def send(self, body, code=200, ctype="text/html; charset=utf-8", headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        if url.path == "/":
            return self.send(page(""))
        if url.path == "/search":
            q = qs.get("q", [""])[0].strip()
            items = "".join(f"<p><a href='/watch?v={vid}'>{html.escape(title)}</a></p>"
                            for vid, title in search(q)) if q else ""
            return self.send(page(items or "<p>No results.</p>"))
        if url.path == "/watch":
            vid = qs.get("v", [""])[0]
            if not VIDEO_ID.match(vid):
                return self.send(page("<p>Bad video id.</p>"), 400)
            if os.path.exists(os.path.join(CACHE, vid + ".mp4")):
                return self.send(page(f"<p><a href='/video/{vid}.mp4'>Play / download</a></p>"))
            if vid not in converting:
                converting.add(vid)
                threading.Thread(target=convert, args=(vid,), daemon=True).start()
            return self.send(page("<p>Converting... this page refreshes every 10s.</p>"),
                             headers=[("Refresh", f"10; url=/watch?v={vid}")])
        m = re.match(r"^/video/([A-Za-z0-9_-]{11})\.mp4$", url.path)
        if m and os.path.exists(path := os.path.join(CACHE, m[1] + ".mp4")):
            # ponytail: whole file in memory, no Range support; fine for short 300k clips
            with open(path, "rb") as f:
                return self.send(f.read(), ctype="video/mp4")
        self.send(page("<p>Not found.</p>"), 404)


def demo():
    assert VIDEO_ID.match("dQw4w9WgXcQ")
    assert not VIDEO_ID.match("../../etc/pa") and not VIDEO_ID.match("-oevil.mp4x")
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, "selftest.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:duration=2",
                    "-f", "lavfi", "-i", "sine=duration=2", *FFMPEG_OUT, out],
                   check=True, capture_output=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height",
                            "-of", "csv=p=0", out], capture_output=True, text=True).stdout
    assert "mpeg4,320,180" in probe and "aac" in probe, probe
    os.remove(out)
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        demo()
    else:
        os.makedirs(CACHE, exist_ok=True)
        print(f"E63Tube on http://0.0.0.0:{PORT}/  (open http://<this-pc-ip>:{PORT}/ on the phone)")
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
