"""YouTube for the Nokia E63 (search, save MP3/MP4, or stream over RTSP), plus PC -> phone file transfer.

Run on the PC (needs ffmpeg on PATH; yt-dlp, deno and mediamtx in bin/), then open
http://<pc-ip>:8063/ in the phone's browser. Files put in send/ show up under "PC files",
and each folder can be downloaded as one ZIP for the phone's Zip Manager.
"""
import hashlib
import html
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

PORT = 8063
RTSP_PORT = 8554  # must match rtspAddress in mediamtx.yml
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
SEND = os.path.join(HERE, "send")  # files offered to the phone under "PC files"
# Local tools (yt-dlp.exe, deno.exe, mediamtx.exe) in bin/ win over anything on the system PATH.
os.environ["PATH"] = os.path.join(HERE, "bin") + os.pathsep + os.environ["PATH"]
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YTDLP_GET = ["yt-dlp", "-f", "best[height<=360]/worst"]

# E63 RealPlayer: MPEG-4 Visual / H.263 only (no H.264), 320x240 screen.
# Tune bitrates here if playback stutters or quality is too low.
FFMPEG_OUT = ["-vf", "scale=320:-2", "-r", "15", "-c:v", "mpeg4", "-b:v", "300k",
              "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "22050"]
MP4_FLAGS = ["-movflags", "+faststart"]
# Phone storage is tiny: AAC-LC 64k stereo (.m4a) is ~0.48 MB/min and sounds like ~96k MP3.
# (HE-AAC would be smaller still, but this ffmpeg has no HE-AAC encoder.) MP3 is the fallback.
M4A_OUT = ["-vn", "-c:a", "aac", "-b:a", "64k", "-ar", "44100", "-ac", "2", *MP4_FLAGS]
MP3_OUT = ["-vn", "-c:a", "libmp3lame", "-b:a", "96k", "-ar", "44100"]
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".wma", ".webm")
BESTAUDIO = ["yt-dlp", "-f", "bestaudio/best"]
# format -> (yt-dlp download args, ffmpeg output args, content type)
FORMATS = {"m4a": (BESTAUDIO, M4A_OUT, "audio/mp4"),
           "mp3": (BESTAUDIO, MP3_OUT, "audio/mpeg"),
           "mp4": (YTDLP_GET, FFMPEG_OUT + MP4_FLAGS, "video/mp4")}

converting = set()  # (vid, fmt); ponytail: in-memory, lost on restart; leftover .part files get redone
zipping = set()     # zip paths being built


def page(body):
    return ("<html><head><meta http-equiv='Content-Type' content='text/html; charset=utf-8'>"
            "<title>E63Tube</title></head><body>"
            "<form action='/search'><input name='q'><input type='submit' value='Search'></form>"
            "<p><a href='/files'>PC files</a></p>"
            f"{body}</body></html>").encode()


def in_send(rel):
    """Absolute path for a path relative to send/, or None if it points outside send/."""
    root = os.path.realpath(SEND)
    p = os.path.realpath(os.path.join(root, rel))
    return p if p == root or p.startswith(root + os.sep) else None


def mb(n):
    return f"{n / 1e6:.1f} MB"


def zip_path(folder, shrink):
    """Cache path of the ZIP for folder; the name changes whenever any file in it changes."""
    h = hashlib.sha1(f"{folder}|{shrink}".encode())
    for dp, _, fs in sorted(os.walk(folder)):
        for fn in sorted(fs):
            st = os.stat(os.path.join(dp, fn))
            h.update(f"{dp}|{fn}|{st.st_size}|{st.st_mtime_ns}".encode())
    return os.path.join(CACHE, "zips", h.hexdigest()[:16] + ".zip")


def make_zip(folder, dst, shrink):
    # Stored, not compressed: media doesn't shrink and the phone unpacks stored files fast.
    # shrink: re-encode audio files to the phone's 64k AAC (.m4a) on the way in.
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    part, tmp = dst + ".part", dst + ".tmp.m4a"
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED) as z:
            for dp, _, fs in os.walk(folder):
                for fn in sorted(fs):
                    p = os.path.join(dp, fn)
                    rel = os.path.relpath(p, folder)
                    if shrink and fn.lower().endswith(AUDIO_EXT):
                        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", p, *M4A_OUT, tmp],
                                           capture_output=True)
                        if r.returncode == 0:
                            z.write(tmp, os.path.splitext(rel)[0] + ".m4a")
                            continue
                        print(f"shrink {rel} failed, adding original", file=sys.stderr)
                    z.write(p, rel)
        os.replace(part, dst)
    except OSError as e:
        print(f"zip {folder} failed: {e}", file=sys.stderr)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
        zipping.discard(dst)


def search(q):
    out = subprocess.run(["yt-dlp", "--flat-playlist", "--print", "%(id)s\t%(title)s",
                          f"ytsearch15:{q}"], capture_output=True, text=True, timeout=60).stdout
    return [line.split("\t", 1) for line in out.splitlines() if "\t" in line]


def convert(vid, fmt):
    get, out, _ = FORMATS[fmt]
    src = os.path.join(CACHE, f"{vid}.{fmt}.src")
    part = os.path.join(CACHE, f"{vid}.part.{fmt}")
    try:
        subprocess.run([*get, "-o", src, "--force-overwrites",
                        f"https://www.youtube.com/watch?v={vid}"], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", src, *out, part], check=True, capture_output=True)
        os.replace(part, os.path.join(CACHE, f"{vid}.{fmt}"))
    except subprocess.CalledProcessError as e:
        print(f"convert {vid}.{fmt} failed:", e.stderr.decode(errors="replace")[-500:], file=sys.stderr)
    finally:
        if os.path.exists(src):
            os.remove(src)
        converting.discard((vid, fmt))


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

    def send_file(self, path, ctype=None, name=None):
        """Stream a file from disk (big ZIPs never sit in memory)."""
        ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(os.path.getsize(path)))
        if name:
            ascii_name = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
            self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"')
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile, 256 * 1024)

    def files_page(self, rel):
        folder = in_send(rel)
        if not folder or not os.path.isdir(folder):
            return self.send(page("<p>Folder not found.</p>"), 404)
        names = sorted(os.listdir(folder), key=str.lower)
        dirs = [n for n in names if os.path.isdir(os.path.join(folder, n))]
        files = [n for n in names if os.path.isfile(os.path.join(folder, n))]
        total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(folder) for f in fs)
        count = sum(len(fs) for _, _, fs in os.walk(folder))
        q = quote(rel)
        out = [f"<p><b>{html.escape(rel or 'PC files')}</b> ({count} files, {mb(total)})</p>"]
        if count:
            out.append(f"<p><a href='/zip?d={q}&s=1'>Download all, shrunk for phone (ZIP)</a><br>"
                       f"<small><a href='/zip?d={q}'>Download all, original files (ZIP)</a></small></p>")
        sub = (rel.strip("/") + "/") if rel.strip("/") else ""   # links always use forward slashes
        if rel:
            out.append(f"<p><a href='/files?d={quote(sub.rstrip('/').rpartition('/')[0])}'>[up]</a></p>")
        out += [f"<p><a href='/files?d={quote(sub + d)}'>[{html.escape(d)}]</a></p>" for d in dirs]
        out += [f"<p><a href='/file/{quote(sub + f)}'>{html.escape(f)}</a> "
                f"<small>{mb(os.path.getsize(os.path.join(folder, f)))}</small></p>" for f in files]
        if not names:
            out.append("<p>Empty. Put files in the send folder on the PC.</p>")
        return self.send(page("".join(out)))

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        if url.path == "/":
            return self.send(page(""))
        if url.path == "/files":
            return self.files_page(qs.get("d", [""])[0])
        if url.path in ("/zip", "/zipget"):
            rel, shrink = qs.get("d", [""])[0], qs.get("s", [""])[0] == "1"
            folder = in_send(rel)
            if not folder or not os.path.isdir(folder):
                return self.send(page("<p>Folder not found.</p>"), 404)
            dst = zip_path(folder, shrink)
            name = (os.path.basename(folder) if rel else "PC files") + ".zip"
            if os.path.exists(dst):
                if url.path == "/zipget":
                    return self.send_file(dst, "application/zip", name)
                return self.send(page(f"<p><a href='/zipget?d={quote(rel)}&s={int(shrink)}'>Download {html.escape(name)}"
                                      f"</a> ({mb(os.path.getsize(dst))})</p><p>On the phone: open it with "
                                      f"Zip manager and extract to the memory card.</p>"))
            if dst not in zipping:
                zipping.add(dst)
                threading.Thread(target=make_zip, args=(folder, dst, shrink), daemon=True).start()
            return self.send(page(f"<p>Packing {html.escape(name)}{' and shrinking audio' if shrink else ''}... "
                                  f"this page refreshes every 10s.</p>"),
                             headers=[("Refresh", f"10; url=/zip?d={quote(rel)}&s={int(shrink)}")])
        if url.path.startswith("/file/"):
            path = in_send(unquote(url.path[len("/file/"):]))
            if path and os.path.isfile(path):
                return self.send_file(path, name=os.path.basename(path))
            return self.send(page("<p>Not found.</p>"), 404)
        if url.path == "/search":
            q = qs.get("q", [""])[0].strip()
            items = "".join(f"<p><a href='/watch?v={vid}'><img src='/thumb/{vid}.jpg' width='120' height='90'>"
                            f"<br>{html.escape(title)}</a></p>"
                            for vid, title in search(q)) if q else ""
            return self.send(page(items or "<p>No results.</p>"))
        if url.path in ("/watch", "/get"):
            vid = qs.get("v", [""])[0]
            fmt = qs.get("f", ["mp4"])[0]
            if not VIDEO_ID.match(vid) or fmt not in FORMATS:
                return self.send(page("<p>Bad video id.</p>"), 400)
            if url.path == "/watch":
                # Nothing is converted until a format is picked. Audio first: smallest download.
                host = (self.headers.get("Host") or "").split(":")[0]
                return self.send(page(f"<p><a href='/get?v={vid}&f=m4a'>Audio</a> "
                                      f"<small>(<a href='/get?v={vid}&f=mp3'>MP3, larger</a>)</small></p>"
                                      f"<p><a href='/get?v={vid}&f=mp4'>Video (MP4)</a></p>"
                                      f"<p><a href='rtsp://{host}:{RTSP_PORT}/{vid}'>Stream</a></p>"))
            kind = "video" if fmt == "mp4" else "audio"
            if os.path.exists(os.path.join(CACHE, f"{vid}.{fmt}")):
                return self.send(page(f"<p><a href='/{kind}/{vid}.{fmt}'>Download / play {kind}</a></p>"))
            if (vid, fmt) not in converting:
                converting.add((vid, fmt))
                threading.Thread(target=convert, args=(vid, fmt), daemon=True).start()
            return self.send(page(f"<p>Preparing {kind}... this page refreshes every 10s.</p>"),
                             headers=[("Refresh", f"10; url=/get?v={vid}&f={fmt}")])
        m = re.match(r"^/(video|audio|thumb)/([A-Za-z0-9_-]{11})\.(mp4|m4a|mp3|jpg)$", url.path)
        if m and m[1] == "thumb" and m[3] == "jpg":
            try:
                return self.send(thumb(m[2]), ctype="image/jpeg")
            except OSError:
                return self.send(b"", 404, ctype="image/jpeg")
        if m and (m[1], m[3]) in (("video", "mp4"), ("audio", "m4a"), ("audio", "mp3")) \
                and os.path.exists(path := os.path.join(CACHE, f"{m[2]}.{m[3]}")):
            # ponytail: no Range support, so an interrupted download restarts from zero
            return self.send_file(path, FORMATS[m[3]][2])
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
    for ext, args, codec in (("m4a", M4A_OUT, "aac"), ("mp3", MP3_OUT, "mp3")):
        out = os.path.join(CACHE, "selftest." + ext)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=duration=2", *args, out],
                       check=True, capture_output=True)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name",
                                "-of", "csv=p=0", out], capture_output=True, text=True).stdout
        assert codec in probe, probe
        os.remove(out)
    assert in_send("") and in_send("a/b") and not in_send("..") and not in_send("../cache")
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        demo()
    elif sys.argv[1:] == ["stream"]:
        stream(os.environ["G1"])  # set by MediaMTX from the path regex; already validated there
    else:
        os.makedirs(CACHE, exist_ok=True)
        os.makedirs(SEND, exist_ok=True)
        mtx = subprocess.Popen(["mediamtx", "mediamtx.yml"], cwd=HERE)
        print(f"E63Tube on http://0.0.0.0:{PORT}/  (open http://<this-pc-ip>:{PORT}/ on the phone)")
        try:
            ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
        finally:
            mtx.terminate()
