"""배경 풍경 클립 늘리기(10-28 사용자 「영상 이미지 똑같은 너무 중복해서 쓰지마」).
픽사베이(~/.volcano/keys/pixabay)·Pexels(~/.volcano/keys/pexels) 공식 API로 영상을 검색해 잔잔한 풍경만 골라 bg/pb<번호>.mp4(픽사베이)·p<번호>.mp4(Pexels)로 받고 bg/SOURCES.md 에 출처를 적는다.
사람·차·드론·타임랩스 들어간 제목은 빼고, 받은 뒤 render.py 와 같은 움직임 지수로 2.6 넘거나 5초 안 되는 것은 지운다.
사용: python bg_fetch.py [--max 250]   (이미 받은 번호는 건너뜀, 로그 logs/bg_fetch.txt)
"""
import os, re, sys, json, time, subprocess, urllib.request, urllib.parse
import numpy as np

REPO = os.path.dirname(os.path.abspath(__file__))
BG = os.path.join(REPO, "bg")
SRC = os.path.join(BG, "SOURCES.md")
LOG = os.path.join(REPO, "logs", "bg_fetch.txt")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
MAX = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 250
QUERIES = ["countryside", "village", "rice field", "farm field", "wheat field", "mountain fog", "misty mountain", "sunrise landscape",
           "sunset sky", "clouds sky", "rain window", "rain drops", "old house", "garden flowers", "autumn leaves", "autumn tree",
           "snow landscape", "snowfall", "calm lake", "river stream", "calm sea", "sea waves beach", "forest", "bamboo forest",
           "cherry blossom", "spring flowers", "persimmon tree", "grass wind", "morning dew", "pond", "waterfall", "countryside road",
           "orchard", "vegetable garden", "pine trees", "night sky stars", "moon night", "temple", "candle light", "fireplace",
           "tea cup steam", "window light", "field flowers", "reeds", "lotus", "hills", "valley", "evening light", "sunlight trees"]
BAD = re.compile(r"(^|-)(woman|women|man|men|people|person|girl|boy|child|children|kid|kids|couple|family|baby|hand|hands|face|"
                 r"drone|aerial|car|cars|driving|drive|road-trip|train|traffic|city|street|time-lapse|timelapse|hyperlapse|"
                 r"bird|birds|dog|cat|horse|cow|sheep|person|tourist|hiker|walking|running|dancing)(-|$)")


def log(m):
    open(LOG, "a", encoding="utf8").write(time.strftime("%m-%d %H:%M:%S ") + m + "\n")


def _key(n):
    p = os.path.expanduser(f"~/.volcano/keys/{n}")
    return open(p, encoding="utf8").read().strip() if os.path.exists(p) else ""


KEY, PB_KEY = _key("pexels"), _key("pixabay")   # 10-28 Pexels 는 새 키 발급을 안 해서 픽사베이 키를 씀


def api(q, page):   # Pexels 공식 API(시간당 200번)
    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(q)}&orientation=portrait&size=medium&per_page=80&page={page}"
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": KEY, **UA}), timeout=60))


def pixabay(q):
    """픽사베이 영상 API(1분 100번) → (번호, 태그, 검색어, 받을 주소). 세로가 드물어서 가로는 4K(3840)만 받음 — 가운데를 세로로 잘라도 1080 넘게 남음."""
    url = f"https://pixabay.com/api/videos/?key={PB_KEY}&q={urllib.parse.quote(q)}&per_page=200&safesearch=true"
    out = []
    for h in json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)).get("hits", []):
        tags = h.get("tags", "").replace(", ", "-").replace(" ", "-")
        if BAD.search(tags) or h.get("duration", 0) < 6: continue
        vs = [v for v in h.get("videos", {}).values() if v.get("url") and v.get("width") and v.get("height")]
        port = [v for v in vs if v["height"] > v["width"] and v["width"] >= 1000]
        land = [v for v in vs if v["width"] >= 3840 and v.get("size", 0) < 80e6]
        pick = min(port, key=lambda v: v["width"]) if port else (land[0] if land else None)
        if pick: out.append(("pb" + str(h["id"]), tags, q, pick["url"], h.get("pageURL", "")))
    return out


def motion(path):   # render.py 와 같은 식
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "fps=10,scale=96:170,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 170, 96).astype(float)
    return float(np.abs(np.diff(fr, axis=0)).mean()) if len(fr) > 1 else 99.0


def main():
    if not (KEY or PB_KEY): sys.exit("API 키 없음 — ~/.volcano/keys/pixabay 또는 pexels 에 저장")
    have = {f[1:-4] if not f.startswith("pb") else f[:-4] for f in os.listdir(BG) if f.startswith("p") and f.endswith(".mp4")}
    seen, cands, pages = set(have), [], {}
    for q in QUERIES:
        try:
            if PB_KEY:
                for vid, tags, qq, link, page in pixabay(q):
                    if vid in seen: continue
                    seen.add(vid); cands.append((vid, tags, qq, link)); pages[vid] = page
            if KEY:
                for v in api(q, 1).get("videos", []):
                    vid, slug = str(v["id"]), v.get("url", "").rstrip("/").split("/")[-1]
                    if vid in seen or BAD.search(slug) or v.get("duration", 0) < 6: continue
                    fs = [f for f in v.get("video_files", []) if f.get("width") and f.get("height") and f["height"] > f["width"] and 1000 <= f["width"] <= 1440]
                    if not fs: continue
                    seen.add(vid); cands.append((vid, slug, q, min(fs, key=lambda f: f["width"])["link"])); pages[vid] = f"https://www.pexels.com/video/{vid}/"
        except Exception as e:
            log(f"검색 실패 {q} {e}")
        time.sleep(0.8)
    log(f"후보 {len(cands)}개")
    # 검색어마다 고르게(앞 검색어만 잔뜩 받지 않게)
    by = {}
    for c in cands: by.setdefault(c[2], []).append(c)
    order = [c for i in range(max(map(len, by.values()), default=0)) for q in QUERIES for c in by.get(q, [])[i:i + 1]]
    got = 0
    for vid, slug, q, link in order:
        if got >= MAX: break
        name = vid if vid.startswith("pb") else "p" + vid
        path = os.path.join(BG, name + ".mp4")
        try:
            data = urllib.request.urlopen(urllib.request.Request(link, headers=UA), timeout=300).read()
            if len(data) > 60e6: log(f"건너뜀(큼) {vid}"); continue
            open(path, "wb").write(data)
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                       capture_output=True, text=True).stdout.strip() or 0)
            mo = motion(path)
        except Exception as e:
            log(f"받기 실패 {vid} {e}")
            if os.path.exists(path): os.remove(path)
            continue
        if dur < 5 or mo > 2.6:
            os.remove(path); log(f"지움 {vid} 길이 {dur:.1f} 움직임 {mo:.2f} {slug}"); continue
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", path, "-frames:v", "1", "-vf", "scale=270:-1",
                        os.path.join(BG, name + ".jpg")])
        with open(SRC, "a", encoding="utf8") as f:
            f.write(f"- {name}: {pages.get(vid, '')}  ({q} · {slug[:60]} · {dur:.0f}초 · 움직임 {mo:.2f})\n")
        got += 1; log(f"받음 {got} {name} {dur:.0f}초 움직임 {mo:.2f} {q}")
        time.sleep(0.3)
    log(f"끝 — 새로 {got}개, 지금 bg {len([f for f in os.listdir(BG) if f.endswith('.mp4')])}개")


if __name__ == "__main__":
    main()
