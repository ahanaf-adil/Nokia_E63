r"""Batch: YouTube search -> phone-sized tagged .m4a for every line of a playlist file.

usage: python songs.py send\playlist.txt OUTDIR
Playlist lines are "Artist - Title" ("#" lines ignored), optionally with "[no lyrics]" (instrumentals)
and "=> Display title" (name/tag shown on the phone, e.g. romanised). For each, "artist title lyrics"
is searched (lyric uploads are the plain studio track, no video intros), falling back to plainer
queries; among results between 90 s and 9 min, one whose title contains the song title wins. It is
downloaded, converted with e63tube's M4A settings and tagged.
Existing outputs are skipped, so a rerun only fetches what's missing. Writes OUTDIR\_matches.txt.
"""
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import e63tube  # puts bin/ on PATH; M4A_OUT

MIN_S, MAX_S = 90, 9 * 60


def safe(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")


def norm(s):
    return re.sub(r"\W+", "", s.lower())


def search(q):
    out = subprocess.run(["yt-dlp", "--encoding", "utf-8", "--flat-playlist", "--print",
                          "%(id)s\t%(duration)s\t%(title)s", f"ytsearch5:{q}"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90).stdout or ""
    hits = []
    for line in out.splitlines():
        vid, dur, yt_title = (line.split("\t", 2) + ["", ""])[:3]
        try:
            if MIN_S <= float(dur) <= MAX_S:
                hits.append((vid, int(float(dur)), yt_title))
        except ValueError:
            continue
    return hits


def find(artist, title, lyrics):
    """Best hit: lyrics search first, then plainer queries; prefer results whose title contains the song title."""
    plain = re.sub(r"\(.*?\)", "", title).strip() or title
    queries = ([f"{artist} {title} lyrics"] if lyrics else []) + [f"{artist} {title}", f"{artist} {plain}", title]
    for q in queries:
        # Only accept a result whose title contains the song title: a blind first hit once gave a cat video.
        named = [h for h in search(q) if norm(plain) and norm(plain) in norm(h[2])]
        if named:
            return named[0]
    return None


def parse(line):
    """'Artist - Title [no lyrics] => Display title' -> artist, search title, display title, use lyrics search."""
    line, _, display = line.partition(" => ")
    lyrics = not re.search(r"\[no lyrics\]|slowed|version|remix", line, re.I)
    line = line.replace("[no lyrics]", "").strip()
    artist, _, title = line.partition(" - ")
    return artist.strip(), title.strip(), (display.strip() or title.strip()), lyrics


def one(line, outdir):
    artist, title, display, lyrics = parse(line)
    dst = os.path.join(outdir, safe(f"{artist} - {display}") + ".m4a")
    if os.path.exists(dst):
        return f"SKIP (exists)\t{line}"
    hit = find(artist, title, lyrics)
    if not hit:
        return f"NOT FOUND\t{line}"
    vid, dur, yt_title = hit
    src = dst + ".src"
    try:
        subprocess.run(["yt-dlp", "-f", "bestaudio/best", "-o", src, "--force-overwrites",
                        f"https://www.youtube.com/watch?v={vid}"], check=True, capture_output=True, timeout=600)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, *e63tube.M4A_OUT,
                        "-metadata", f"title={display}", "-metadata", f"artist={artist}",
                        "-metadata", "album=E63", dst + ".part.m4a"], check=True, capture_output=True, timeout=600)
        os.replace(dst + ".part.m4a", dst)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return f"FAILED\t{line}\t{getattr(e, 'stderr', b'') or ''}"[:300]
    finally:
        for p in (src, dst + ".part.m4a"):
            if os.path.exists(p):
                os.remove(p)
    return f"OK\t{line}\t{dur // 60}:{dur % 60:02d}\t{yt_title}\thttps://youtu.be/{vid}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    playlist, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    lines = [l.strip() for l in open(playlist, encoding="utf-8-sig") if l.strip() and not l.startswith("#")]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda l: one(l, outdir), lines))
    with open(os.path.join(outdir, "_matches.txt"), "a", encoding="utf-8") as f:
        f.write("\n".join(results) + "\n")
    for r in results:
        print(r, flush=True)
    print(f"{sum(r.startswith('OK') for r in results)} downloaded, "
          f"{sum(not r.startswith(('OK', 'SKIP')) for r in results)} problems, of {len(lines)}")


if __name__ == "__main__":
    main()
