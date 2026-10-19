# 대본 이야기 점검(agy): python story_check.py epNN [epNN …]
#   1) 결말 맞히기 — 제목+인트로(대본 앞 20%, 약 30초)만 agy에게 주고 반전을 맞혀 보게 함(결말은 안 보여 줌)
#      10-18 사용자 「엄마 대신 문자 받은 딸 이 영상처럼 앞 인트로에 결말이 예상되게 하면 안 돼」 — ep38 옛 제목
#      「…보낸 문자, 누가 읽는지 알고 울었습니다」+ 인트로 「장례 날 아내 휴대폰부터 챙긴 건 딸」이면 처음 40초에 결말이 보였음
#   2) 앞뒤 점검 — 전체 대본과 1)의 추측을 주고: 추측이 반전 핵심을 맞혔나, 설정상 말이 안 되는 곳, 서운한 행동 중 이유가 안 풀린 것,
#      반대 뜻으로 읽힐 문장, 설명 없이 나오는 지식
#      10-18 ep35 「과수원 잇겠다는 아들 무슨 내용인지 모르겠어」(내쫓은 이유 없음·수첩 글이 꽃을 얼려 쫓아내려는 계획처럼 읽힘·
#      서리 밤에 불 피우는 이유 설명 없음), ep37 「사돈인데 얼굴을 모른다는 게 말이 안 되잖아」
#   ⚠가 나오면 대본을 고치고 다시 돌림(tts 전에). agy 로그인이 풀리면 멈추고 사용자에게 알림.
import json, os, re, subprocess, sys, time

REPO = os.path.dirname(os.path.abspath(__file__))
AGY = os.path.join(os.environ["LOCALAPPDATA"], "agy", "bin", "agy.exe")


def agy(prompt):
    for _ in range(2):
        p = subprocess.run([AGY, "-p", prompt, "--model", "gemini-3.8-flash-high", "--print-timeout", "300s"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        t = p.stdout
        if "Authentication required" in t + (p.stderr or ""): sys.exit("⚠ agy 로그인이 풀림 — 사용자에게 agy 재로그인 요청")
        try: return json.loads(t[t.index("{"):t.rindex("}") + 1])
        except ValueError: print("agy 응답 해석 실패, 재시도", (p.stderr or t)[-300:]); time.sleep(20)
    return None


def load(ep):
    s = open(os.path.join(REPO, ep, "script.txt"), encoding="utf-8").read()
    title = re.search(r"^제목:\s*(.+)$", s, re.M).group(1).strip()
    L = []
    for l in s.split("\n■ 대본\n")[1].splitlines():
        l = l.strip()
        if not l.startswith(("[", ">>>")): continue
        spk = re.match(r"^(?:>>>\s*)?\[([^·\]]+)", l).group(1)
        txt = re.sub(r"\{([^|}]*)\|[^}]*\}", r"\1", re.sub(r"^(?:>>>\s*)?\[[^\]]+\]\s*", "", l))
        if "화면을 두 번 터치" in txt: continue
        L.append(f"{spk}: {txt}")
    return title, L


P1 = """다음은 유튜브 시니어 가족 사연 쇼츠(약 2분 40초)의 제목과 처음 약 30초 대본이다. 이 이야기는 나레이터가 서운하게 여기던 사람에게 숨은 사정이 있었다는 반전(감동형), 또는 나레이터가 선을 넘은 사람에게 한 방을 먹이는 결말(사이다형)로 끝난다.
도구·명령은 쓰지 말고 글로만 답하라. 결말을 모른다고 생각하고, 이 앞부분만 보고 결말(누가·무엇을·왜)을 가장 그럴듯하게 한두 문장으로 맞혀 보라. 그리고 그 추측에 얼마나 확신하는지 0~100으로 적어라.
JSON 하나만 답하라: {{"guess": "...", "confidence": 0}}

제목: {title}
{intro}"""

P2 = """다음은 유튜브 시니어 가족 사연 쇼츠의 전체 대본(창작 사연)이다. 도구·명령은 쓰지 말고 글로만 답하라. 시청자 입장에서 꼼꼼히 점검하라.
1) 다른 사람이 제목과 처음 30초만 보고 결말을 이렇게 추측했다: 「{guess}」(확신 {conf}). 이 추측이 실제 반전의 핵심(누가·무엇을·왜)을 맞혔는지 판정하라. 대략 맞혔으면 true.
   true는 반전의 구체적인 행동·물건(누가 무엇을 몰래 했는지)까지 맞혔을 때만이다. 「사실은 아꼈다」「병을 숨겼다」처럼 장르의 큰 틀만 맞히고 구체적인 행동이 틀렸으면 false.
   맞혔다면, 제목·인트로의 어떤 말(줄)이 결말을 알려 줬는지 적어라.
2) 이야기 앞뒤가 안 맞거나 시청자가 "무슨 내용인지 모르겠다"고 할 곳을 찾아라:
   - 설정상 말이 안 되는 곳(예: 결혼한 지 일 년인데 사돈이 얼굴을 모름)
   - 제목·앞부분에 나온 서운한 행동 중, 뒤에서 왜 그랬는지 풀리지 않은 것(예: 아들을 서울로 내쫓은 이유가 안 나옴)
   - 반대 뜻으로 읽힐 수 있는 문장(예: 「첫해 꽃이 얼면, 아들은 이 일을 미워하게 된다」가 꽃을 얼려 쫓아내려는 계획처럼 읽힘)
   - 설명 없이 나와서 일반 시청자가 모를 지식·행동(예: 서리 오는 밤에 왜 불을 피우는지)
   - 시간 순서가 꼬인 곳, 인물 관계·호칭이 헷갈리는 곳
   사소한 표현 취향은 빼고, 실제로 이해를 막는 것만 적어라. 없으면 빈 배열.
JSON 하나만 답하라: {{"guessed": true, "spoiler": "결말을 알려 준 줄(없으면 빈 문자열)", "problems": [{{"line": "문제 줄 앞부분", "problem": "무엇이 문제인지", "fix": "고칠 방향"}}]}}

제목: {title}
{body}"""


def check(ep):
    title, L = load(ep)
    tot = sum(len(l) for l in L)
    intro, n = [], 0
    for l in L:
        if n > tot * 0.2: break   # 처음 약 30초(사용자가 말한 「앞 인트로」)
        intro.append(l); n += len(l)
    head = open(os.path.join(REPO, ep, "script.txt"), encoding="utf-8").read().split("■ 목소리")[0]
    cider = ("사이다" in head or "미러링" in head) and "감동·오해형으로" not in head   # 사이다형은 숨은 반전이 아니라 한 방이라 결말 맞히기는 건너뜀(10-20 ep48 머리 「원본은 사위 시점 사이다 → 감동·오해형으로 바꿈」이 사이다로 잡혀 고침)
    r1 = {"guess": "(사이다형 — 결말 맞히기 안 함)", "confidence": "-"} if cider else agy(P1.format(title=title, intro="\n".join(intro))) or {}
    guess, conf = r1.get("guess", ""), r1.get("confidence", "?")
    r2 = agy(P2.format(title=title, body="\n".join(L), guess=guess, conf=conf)) or {}
    if cider: r2["guessed"] = False
    bad = r2.get("guessed") or r2.get("problems")
    print(f"\n== {ep} {'⚠' if bad else '✓'} {title}")
    print(f"  인트로({len(intro)}줄)만 보고 추측(확신 {conf}): {guess}")
    print(f"  결말 맞힘: {r2.get('guessed')}" + (f" — 알려 준 줄: {r2.get('spoiler')}" if r2.get("guessed") else ""))
    for p in r2.get("problems", []):
        print(f"  ⚠ 「{p.get('line', '')}」 {p.get('problem', '')} → {p.get('fix', '')}")
    return r2


if __name__ == "__main__":
    out = {}
    for ep in sys.argv[1:]:
        out[ep] = check(ep)
    json.dump(out, open(os.path.join(REPO, "analysis", "story_check_last.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
