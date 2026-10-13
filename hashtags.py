# 벤치마크 채널 해시태그 모으기(10-13 사용자 "다른 채널에 있는 헤시테그 가져 올 수 있어?")
#   analysis/sources_channels.json(scan_sources.py가 갱신)의 채널마다 조회수 상위 N편 → yt-dlp로 설명·태그를 받아
#   설명 속 #해시태그와 태그 칸을 모아 많이 쓴 순으로 → analysis/hashtags.json
#   python hashtags.py [--top 10]
import collections, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(REPO, "analysis", "sources_channels.json")
OUT = os.path.join(REPO, "analysis", "hashtags.json")
TOP = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 10
HASH = re.compile(r"#[^\s#.,!?()\[\]<>\"']+")


def meta(vid):
    p = subprocess.run(["yt-dlp", "--skip-download", "-j", f"https://www.youtube.com/shorts/{vid}"],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        return None
    j = json.loads(p.stdout)
    return {"hashtags": HASH.findall(j.get("description") or "") + HASH.findall(j.get("title") or ""),
            "tags": j.get("tags") or [], "desc": (j.get("description") or "")[:300]}


chans = json.load(open(SRC, encoding="utf-8"))
jobs = []
for name, c in chans.items():
    for v in sorted(c["videos"], key=lambda v: -(v.get("views") or 0))[:TOP]:
        jobs.append((name, v))
with ThreadPoolExecutor(4) as ex:
    metas = list(ex.map(lambda nv: meta(nv[1]["id"]), jobs))

result = {"top": TOP, "channels": {}, "hashtag_count": {}, "tag_count": {}}
hc, tc = collections.Counter(), collections.Counter()
for (name, v), m in zip(jobs, metas):
    if not m:
        continue
    result["channels"].setdefault(name, []).append({"id": v["id"], "title": v["title"], "views": v.get("views"), **m})
    hc.update(set(h.lower() for h in m["hashtags"]))      # 한 영상에서 같은 태그는 한 번만
    tc.update(set(t.lower() for t in m["tags"]))
result["hashtag_count"] = dict(hc.most_common())
result["tag_count"] = dict(tc.most_common())
json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

got = sum(len(v) for v in result["channels"].values())
print(f"{got}/{len(jobs)}편 받음 → {OUT}")
for name, vs in result["channels"].items():
    c = collections.Counter(h for v in vs for h in set(x.lower() for x in v["hashtags"]))
    print(f"\n[{name}] {len(vs)}편  " + " ".join(f"{h}({n})" for h, n in c.most_common(12)))
print("\n[전체 해시태그] " + " ".join(f"{h}({n})" for h, n in hc.most_common(30)))
print("[전체 태그 칸] " + " ".join(f"{t}({n})" for t, n in tc.most_common(20)))
