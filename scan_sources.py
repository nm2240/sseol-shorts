# 썰쇼츠 소재 찾기(10-13 "소재 찾아서 매일 오전 4시에 4개씩 만들어")
#   python scan_sources.py            채널 5개 최신 쇼츠 목록 갱신 → 아직 분석 안 한 인기 편(채널 중간값 대비 배수 순) 자막 → agy 분석 → 소재후보.md 표에 추가
#   python scan_sources.py --list     안 쓴 후보를 점수순으로(점수 = 배수(log10)×2 + 감동형 각색×1.2 + 현실성×0.8, 상2·중1·하0)
#   옵션: --top 8(새로 분석할 편 수) --recent 40(채널마다 최신 몇 편까지 목록을 다시 받나) --no-agy
import json, math, os, re, statistics, subprocess, sys, tempfile, time

sys.stdout.reconfigure(encoding="utf-8")
D = os.path.dirname(os.path.abspath(__file__))
CH = os.path.join(D, "analysis", "sources_channels.json")
PV = os.path.join(D, "analysis", "sources_per_video.json")
MD = os.path.join(D, "소재후보.md")
AGY = os.path.join(os.environ["LOCALAPPDATA"], "agy", "bin", "agy.exe")
G = {"상": 2, "중": 1, "하": 0}
arg = lambda k, d: int(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
man = lambda v: f"{v / 10000:.0f}만" if v >= 10000 else f"{v / 10000:.1f}만"


def rows():
    """소재후보.md 표 줄: (번호, 제목, id, 채널, 조회수, 배수, 유형, 감동, 현실, 사용)"""
    out = []
    for ln in open(MD, encoding="utf-8").read().splitlines():
        c = [x.strip() for x in ln.split("|")]
        if len(c) == 11 and c[1].isdigit():
            m = re.search(r"\[(.*)\]\(https://www\.youtube\.com/shorts/([\w-]{11})\)", c[2])
            if m: out.append((int(c[1]), m.group(1), m.group(2), c[3], c[4], float(re.sub(r"[^0-9.]", "", c[5]) or 0), c[6], c[7], c[8], c[9]))
    return out


def score(r):
    return 2 * math.log10(max(r[5], 0.5)) + 1.2 * G.get(r[7], 0) + 0.8 * G.get(r[8], 0)


def list_unused():
    pv = {x["id"]: x for x in json.load(open(PV, encoding="utf-8"))}
    un = sorted((r for r in rows() if not r[9]), key=lambda r: -score(r))
    print(f"안 쓴 후보 {len(un)}개(감동형 각색 상 {sum(r[7] == '상' for r in un)}개)")
    for r in un:
        p = pv.get(r[2], {})
        print(f"#{r[0]} 점수 {score(r):.2f} | {r[1]} | {r[3]} {r[4]} {r[5]:.0f}배 | {r[6]} 감동{r[7]} 현실{r[8]} | https://www.youtube.com/shorts/{r[2]}")
        if p: print(f"    관계: {p.get('나레이터', '')} / {p.get('상대', '')}\n    각색: {p.get('각색_아이디어', '')}")


def ytdlp_list(url, n):
    """조회수는 기본 호출, 제목은 lang=ko 호출에서(기본 호출 제목은 영어 번역으로 올 때가 있고, lang=ko 는 조회수가 빔)"""
    if not re.search(r"/(shorts|videos)/?$", url): url = url.rstrip("/") + "/shorts"
    got = []
    for ex in ([], ["--extractor-args", "youtube:lang=ko"]):
        p = subprocess.run(["yt-dlp", "--flat-playlist", "--playlist-end", str(n), "-J", *ex, url],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if p.returncode: print("목록 실패", url, p.stderr[-300:]); return []
        got.append({e["id"]: e for e in json.loads(p.stdout).get("entries", []) if e.get("id")})
    return [{"id": k, "title": (got[1].get(k) or e).get("title") or e.get("title") or "", "views": e.get("view_count")} for k, e in got[0].items()]


HAN = re.compile(r"[가-힣]")


def subs(vid, tmp):
    subprocess.run(["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "ko", "--sub-format", "json3",
                    "-o", os.path.join(tmp, "%(id)s.%(ext)s"), f"https://www.youtube.com/shorts/{vid}"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    f = os.path.join(tmp, f"{vid}.ko.json3")
    if not os.path.exists(f): return ""
    ev = json.load(open(f, encoding="utf-8")).get("events", [])
    return " ".join("".join(s.get("utf8", "") for s in e.get("segs", [])).strip() for e in ev if e.get("segs")).replace("\n", " ")


PROMPT = """너는 유튜브 쇼츠 각색 소재 분석가다. 아래는 시니어 가족·시골 사연 쇼츠 {n}편의 자동자막(구두점 없음)이다. 우리 채널은 설정만 빌려 「가족 사이 오해 → 알고 보니 숨은 희생」 감동형으로 관계·물건·반전·대사를 새로 쓴다.
편마다 아래 항목을 뽑아 JSON 배열 하나로만 답하라(설명 문장 금지, 코드블록 금지). 자막에 없는 내용은 지어내지 말고 "없음".
{{"id": 영상id, "유형": "감동·오해형" | "사이다·선긋기형" | "미스터리·사건형" | "기타",
 "나레이터": "나이·성별·누구", "상대": "갈등·오해 상대와 관계", "줄거리": "세 문장 안",
 "오해_또는_갈등": "핵심 장면 한 줄", "반전_장치": "진실이 드러나는 물건·서류·사람", "결말": "마지막 행동·관계 변화",
 "숫자": "금액·기간·나이", "현실성": "상|중|하(이유 한 줄)",
 "감동형_각색_가능": "상|중|하 — 가족 사이 오해→숨은 희생으로 바꾸기 쉬운 정도와 이유",
 "각색_아이디어": "가족판 감동형으로 바꾼 줄거리 한두 문장(관계·물건·반전은 원본과 다르게)"}}

{body}"""


def agy(prompt):
    for _ in range(2):
        p = subprocess.run([AGY, "-p", prompt, "--model", "gemini-3.8-flash-high", "--print-timeout", "600s"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        t = p.stdout
        if "Authentication required" in t + (p.stderr or ""): print("⚠ agy 로그인이 풀림 — 사용자에게 agy 재로그인 요청"); return None
        try: return json.loads(t[t.index("["):t.rindex("]") + 1])
        except ValueError: print("agy 응답 해석 실패, 재시도", (p.stderr or t)[-300:]); time.sleep(20)
    return None


def scan():
    chs = json.load(open(CH, encoding="utf-8"))
    today = time.strftime("%Y-%m-%d")
    new = 0
    for name, ch in chs.items():
        got = ytdlp_list(ch["url"], arg("--recent", 40))
        old = {v["id"]: v for v in ch["videos"]}
        for v in got:
            if v["id"] in old:
                if v["views"]: old[v["id"]]["views"] = v["views"]
                if HAN.search(v["title"]): old[v["id"]]["title"] = v["title"]
            else:
                v["dur"] = None; v["seen"] = today; ch["videos"].insert(0, v); new += 1
        print(f"{name}: 최신 {len(got)}편 확인, 새 영상 {sum(v.get('seen') == today for v in ch['videos'])}편")
    json.dump(chs, open(CH, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    # 표 제목이 영어로 들어간 줄은 한국어 제목으로
    ko = {v["id"]: v["title"] for ch in chs.values() for v in ch["videos"] if HAN.search(v.get("title") or "")}
    md = open(MD, encoding="utf-8").read()
    for r in rows():
        if not HAN.search(r[1]) and r[2] in ko:
            md = md.replace(f"[{r[1]}](https://www.youtube.com/shorts/{r[2]})", f"[{ko[r[2]].replace('|', '/').replace('[', '(').replace(']', ')')}](https://www.youtube.com/shorts/{r[2]})")
    open(MD, "w", encoding="utf-8").write(md)
    known = {r[2] for r in rows()} | {x["id"] for x in json.load(open(PV, encoding="utf-8"))}
    cand = []
    for name, ch in chs.items():
        vs = [v["views"] for v in ch["videos"] if v.get("views")]
        med = statistics.median(vs) if vs else 1
        for v in ch["videos"]:
            if v["id"] not in known and v.get("views") and v["views"] / med >= 2:
                cand.append((v["views"] / med, name, v))
    cand.sort(key=lambda x: -x[0])
    print(f"분석 안 한 인기 편(배수 2 이상) {len(cand)}개")
    if "--no-agy" in sys.argv or not cand: return
    pick, body = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for mult, name, v in cand:
            if len(pick) >= arg("--top", 8): break
            t = subs(v["id"], tmp)
            if len(t) < 80: print("자막 없음, 건너뜀", v["id"], v["title"]); continue
            pick.append((mult, name, v)); body.append(f"### id={v['id']} | 채널 {name} | 조회수 {v['views']} | 제목: {v['title']}\n{t[:4000]}")
    if not pick: return
    res = agy(PROMPT.format(n=len(pick), body="\n\n".join(body)))
    if not res: print("⚠ agy 분석 실패 — 기존 후보로 진행"); return
    by = {x.get("id"): x for x in res if isinstance(x, dict)}
    pv = json.load(open(PV, encoding="utf-8"))
    md = open(MD, encoding="utf-8").read().rstrip("\n")
    n = max(r[0] for r in rows())
    for mult, name, v in pick:
        x = by.get(v["id"])
        if not x: continue
        x["id"] = v["id"]; pv.append(x); n += 1
        g = lambda k: (str(x.get(k, "")).strip() or "하")[0]
        title = v["title"].replace("|", "/").replace("[", "(").replace("]", ")")
        md += f"\n| {n} | [{title}](https://www.youtube.com/shorts/{v['id']}) | {name} | {man(v['views'])} | {mult:.0f}배 | {x.get('유형', '기타')} | {g('감동형_각색_가능')} | {g('현실성')} |  |"
        print(f"추가 #{n} {title} ({name} {man(v['views'])}, {mult:.0f}배) 감동{g('감동형_각색_가능')}")
    json.dump(pv, open(PV, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(MD, "w", encoding="utf-8").write(md + "\n")


if __name__ == "__main__":
    list_unused() if "--list" in sys.argv else scan()
