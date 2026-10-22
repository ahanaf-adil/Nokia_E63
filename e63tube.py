"""YouTube for the Nokia E63: search, then stream (RTSP) or save a phone-playable MP4.

Run on the PC (needs ffmpeg on PATH; yt-dlp, deno and mediamtx in bin/), then open
http://<pc-ip>:8063/ in the phone's browser.
"""
import html
import os
import re
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8063
RTSP_PORT = 8554  # must match rtspAddress in mediamtx.yml
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
# Local tools (yt-dlp.exe, deno.exe, mediamtx.exe) in bin/ win over anything on the system PATH.
os.environ["PATH"] = os.path.join(HERE, "bin") + os.pathsep + os.environ["PATH"]
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YTDLP_GET = ["yt-dlp", "-f", "best[height<=360]/worst"]

# E63 RealPlayer: MPEG-4 Visual / H.263 only (no H.264), 320x240 screen.
# Tune bitrates here if playback stutters or quality is too low.
FFMPEG_OUT = ["-vf", "scale=320:-2", "-r", "15", "-c:v", "mpeg4", "-b:v", "300k",
              "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "22050"]
MP4_FLAGS = ["-movflags", "+faststart"]

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
        subprocess.run([*YTDLP_GET, "-o", src, "--force-overwrites",
                        f"https://www.youtube.com/watch?v={vid}"], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", src, *FFMPEG_OUT, *MP4_FLAGS, part],
                       check=True, capture_output=True)
        os.replace(part, os.path.join(CACHE, vid + ".mp4"))
    except subprocess.CalledProcessError as e:
        print(f"convert {vid} failed:", e.stderr.decode(errors="replace")[-500:], file=sys.stderr)
    finally:
        if os.path.exists(src):
            os.remove(src)
        converting.discard(vid)


def stream(vid):
    """Publish one video to MediaMTX in real time. Run by MediaMTX (runOnDemand) when the phone connects."""
    out = ["-f", "rtsp", "-rtsp_transport", "tcp", f"rtsp://127.0.0.1:{RTSP_PORT}/{vid}"]
    cached = os.path.join(CACHE, vid + ".mp4")
    if os.path.exists(cached):
        return subprocess.run(["ffmpeg", "-re", "-i", cached, "-c", "copy", *out])
    # yt-dlp must do the download: googlevideo URLs are tied to its (split-tunnelled) IP.
    yt = subprocess.Popen([*YTDLP_GET, "-o", "-", f"https://www.youtube.com/watch?v={vid}"],
                          stdout=subprocess.PIPE)
    try:
        subprocess.run(["ffmpeg", "-re", "-i", "pipe:0", *FFMPEG_OUT, "-flags", "+global_header", *out],
                       stdin=yt.stdout)
    finally:
        yt.kill()


def thumb(vid):
    path = os.path.join(CACHE, vid + ".jpg")
    if not os.path.exists(path):
        with urllib.request.urlopen(f"https://i.ytimg.com/vi/{vid}/default.jpg", timeout=10) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "rb") as f:
        return f.read()


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
            items = "".join(f"<p><a href='/watch?v={vid}'><img src='/thumb/{vid}.jpg' width='120' height='90'>"
                            f"<br>{html.escape(title)}</a></p>"
                            for vid, title in search(q)) if q else ""
            return self.send(page(items or "<p>No results.</p>"))
        if url.path == "/watch":
            # Download first (no buffering); streaming stays available as a fallback link.
            vid = qs.get("v", [""])[0]
            if not VIDEO_ID.match(vid):
                return self.send(page("<p>Bad video id.</p>"), 400)
            host = (self.headers.get("Host") or "").split(":")[0]
            stream = f"<p><small><a href='rtsp://{host}:{RTSP_PORT}/{vid}'>Stream instead</a></small></p>"
            if os.path.exists(os.path.join(CACHE, vid + ".mp4")):
                return self.send(page(f"<p><a href='/video/{vid}.mp4'>Download / play</a></p>{stream}"))
            if vid not in converting:
                converting.add(vid)
                threading.Thread(target=convert, args=(vid,), daemon=True).start()
            return self.send(page(f"<p>Preparing download... this page refreshes every 10s.</p>{stream}"),
                             headers=[("Refresh", f"10; url=/watch?v={vid}")])
        m = re.match(r"^/(video|thumb)/([A-Za-z0-9_-]{11})\.(mp4|jpg)$", url.path)
        if m and m[1] == "thumb" and m[3] == "jpg":
            try:
                return self.send(thumb(m[2]), ctype="image/jpeg")
            except OSError:
                return self.send(b"", 404, ctype="image/jpeg")
        if m and m[1] == "video" and m[3] == "mp4" and os.path.exists(path := os.path.join(CACHE, m[2] + ".mp4")):
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
                    "-f", "lavfi", "-i", "sine=duration=2", *FFMPEG_OUT, *MP4_FLAGS, out],
                   check=True, capture_output=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height",
                            "-of", "csv=p=0", out], capture_output=True, text=True).stdout
    assert "mpeg4,320,180" in probe and "aac" in probe, probe
    os.remove(out)
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        demo()
    elif sys.argv[1:] == ["stream"]:
        stream(os.environ["G1"])  # set by MediaMTX from the path regex; already validated there
    else:
        os.makedirs(CACHE, exist_ok=True)
        mtx = subprocess.Popen(["mediamtx", "mediamtx.yml"], cwd=HERE)
        print(f"E63Tube on http://0.0.0.0:{PORT}/  (open http://<this-pc-ip>:{PORT}/ on the phone)")
        try:
            ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
        finally:
            mtx.terminate()
