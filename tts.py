# 썰쇼츠 타입캐스트 TTS: python tts.py epNN [--redo-lines 줄번호…] [--full]
# epNN/script.txt 의 [화자·목소리] 줄을 같은 화자끼리 통으로 합성 → epNN/tts/plan.json
# 고친 뒤 다시 돌리면 바뀐 줄만 합성하고 나머지는 받아 둔 소리를 잘라 씀(10-19 비용 아끼기 — 아래 library.json)
# 감정: 나레이션(화자 '나레이터'·노란 문구)은 normal 프리셋으로 잔잔하게, 대사만 smart(앞뒤 묶음 문맥)
#   10-14 사용자 "나레이션은 잔잔해야 하는데 감정이 너무 들어가 있어서 듣기 힘들어. 감정은 대사에만 넣어"
# 키는 ~/.volcano/keys/typecast (저장소에 넣지 않음). 목소리 이름은 voices_by_age.json 의 영문·한글 둘 다 됨
import hashlib, json, os, re, sys, time, urllib.request, urllib.error
REPO = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) < 2: sys.exit("사용법: python tts.py epNN")
ROOT = os.path.abspath(sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(REPO, sys.argv[1]))
TTS = os.path.join(ROOT, "tts")
os.makedirs(TTS, exist_ok=True)
TEMPO = 1.1   # 10-12 사용자 "1.2배 너무 빠르다, 1.1배만" — API audio_tempo로(후처리 atempo 아님)
KEY = open(os.path.expanduser("~/.volcano/keys/typecast"), encoding="utf-8").read().strip()
VOICE_ID = {"Myungjoo": "tc_656059fc4db338e38f77d0bc", "Storyteller Jinsub": "tc_65571d1aa52fc0f2872045fa",
            "Hyejin": "tc_6a21054564d676539427427e", "Sanghyun": "tc_69fc0cff784968297fb45daa"}   # 표 밖 목소리
# 연령별 목소리표(사용자 제공 72명) — 태그에 영문·한글 이름 어느 쪽을 써도 찾게
for v in json.load(open(os.path.join(REPO, "voices_by_age.json"), encoding="utf-8"))["voices"]:
    VOICE_ID.setdefault(v["name"], v["voice_id"]); VOICE_ID.setdefault(v["ko"], v["voice_id"])

BANNED = {"Inhwa", "인화", "Jaesun", "재선", "Ilho", "일호", "Byunghun", "병훈", "Duckchun", "덕춘", "Cheolhoon", "철훈", "Mija", "오미자"}   # 10-12 "인화는 절대 쓰지 마", 10-13 "재선 앞으로 쓰지 마 삭제"·"일호 삭제"·"병훈 삭제", 10-14 "덕춘 삭제. 앞으로 사용금지"·"철훈 삭제 사용 금지"·"오미자 삭제. 금지" — 목소리표(voices_by_age.json "banned")에서도 뺌
# 소리 표기 {자막|소리}: 자막·제목은 앞쪽(정석), 타입캐스트에는 뒤쪽(발음 나는 대로) — 10-13 사용자 "자막은 정석으로 하고 음성을 발음 나는 대로"
PRON = re.compile(r"\{([^{}|]*)\|([^{}]*)\}")
sub_text = lambda t: PRON.sub(r"\1", t)
lines = []
for l in open(os.path.join(ROOT, "script.txt"), encoding="utf-8-sig"):
    m = re.match(r"\[([^·\]]+)·([^\]]+)\]\s*(.+)", l.strip())
    if m: lines.append({"spk": m.group(1), "voice": m.group(2), "raw": m.group(3), "text": sub_text(m.group(3))})
# 노란 문구 읽는 목소리 — 10-13 처음엔 20대 여성 안내(Daeun, ep04·ep03) → 같은 날 "노란 문구는 나레이션하던 인물로 그냥 이어서 해"
# → 새 편은 >>> [나레이터·나레이터 목소리] 로 적고, 앞뒤 줄을 문맥으로 넣어 이어 읽는 말투로 합성
cta, _n = None, 0
for l in open(os.path.join(ROOT, "script.txt"), encoding="utf-8-sig"):
    if re.match(r"\[([^·\]]+)·([^\]]+)\]\s*(.+)", l.strip()): _n += 1
    m = re.match(r">>>\s*\[([^·\]]+)·([^\]]+)\]\s*(.+)", l.strip())
    if m: cta = {"spk": m.group(1), "voice": m.group(2), "raw": m.group(3), "text": sub_text(m.group(3)), "pos": _n}
bad = sorted(({l["voice"] for l in lines} | ({cta["voice"]} if cta else set())) & BANNED)
if bad: sys.exit(f"금지 목소리: {bad} — 다른 목소리로 바꿀 것")


def say(text):   # 따옴표는 소리에 필요 없음, {자막|소리}는 소리 쪽으로
    text = PRON.sub(r"\2", text)
    text = re.sub(r"(^|\s)네가(\s)", r"\1니가\2", text.replace('"', ""))   # '네가'가 '내가'로 들림(ep04) → 소리만 '니가', 자막은 대본대로
    return text.strip()



# 같은 화자가 이어 말하는 줄은 개수 제한 없이 한 번에 합성(10-13 사용자: 문장 끝나고 너무 빠르다 →
# 스마트 이모션으로 문단째 만들고 문장 사이 쉼은 타입캐스트가 낸 그대로 씀. 예전 상한 3문장·130자는 없앰)
groups = []
for i, l in enumerate(lines):
    g = groups[-1] if groups else None
    if g and lines[g[-1]]["voice"] == l["voice"] and lines[g[-1]]["spk"] == l["spk"]:
        g.append(i)
    else:
        groups.append([i])
gtext = [" ".join(say(lines[k]["raw"]) for k in g) for g in groups]


CALM = {"emotion_type": "preset", "emotion_preset": "normal", "emotion_intensity": 1.0}   # 나레이션 — smart는 음높이가 2반음쯤 들뜨고 오르내림이 큼
is_narr = lambda gi: lines[groups[gi][0]]["spk"] == "나레이터"
says = [say(l["raw"]) for l in lines]


def name_of(v, text, calm):   # 파일 이름 = 목소리+글자(+빠르기·잔잔) — 문맥은 안 들어감
    return "g_" + hashlib.md5((v + "|" + text + ("" if TEMPO == 1.0 else f"|t{TEMPO}") + ("|calm" if calm else "")).encode()).hexdigest()[:8]


def tts_call(v, text, calm, prev, nxt):
    body = {"voice_id": VOICE_ID[v], "text": text, "model": "ssfm-v30", "language": "kor",
            "output": {"audio_format": "wav", "audio_tempo": TEMPO},
            "prompt": CALM if calm else {"emotion_type": "smart", "previous_text": prev, "next_text": nxt}}
    req = urllib.request.Request("https://api.typecast.ai/v1/text-to-speech", data=json.dumps(body).encode(),
                                 method="POST", headers={"X-API-KEY": KEY, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=120).read()


# ---- 비용 아끼기(10-19 사용자 "타입캐스트 tts비용이 너무많이 들어가. 수정할때 잘못된 부분만 수정하는쪽으로")
#   예전: 묶음 안 한 줄만 고쳐도 파일 이름(목소리+묶음 전체 글자)이 바뀌어 묶음(많게는 8~9줄)을 통째로 다시 샀음.
#   지금: 묶음 파일이 없으면 줄마다 이미 받은 소리(tts/library.json — 파일별 줄 글자)에서 같은 소리 글자를 찾아 그 구간만 잘라 쓰고
#         (plan.json 조각에 pos·src_texts — render.py가 원래 파일 전체로 줄 경계를 잡은 뒤 그 줄만 씀), 없는 줄만 새로 합성.
#   줄을 빼기만 하면 합성 0, 고친 줄만 합성(대사는 앞뒤 줄을 문맥으로). 다시 쓸 수 있는 글자가 30% 안이면 예전처럼 묶음째.
#   python tts.py epNN --redo-lines 12 13   같은 글자로 그 줄만 다시 받기(끝음절 묻힘·한 줄 반복 등)
#   python tts.py epNN --full              예전처럼 묶음째(줄 사이가 어색할 때)
REDO = {int(x) for x in sys.argv[sys.argv.index("--redo-lines") + 1:] if x.isdigit()} if "--redo-lines" in sys.argv else set()
FULL = "--full" in sys.argv
LIB_P = os.path.join(TTS, "library.json")
LIB = json.load(open(LIB_P, encoding="utf-8")) if os.path.exists(LIB_P) else {"files": {}, "groups": {}}
if not LIB["files"] and os.path.exists(os.path.join(TTS, "plan.json")):   # 예전 plan.json 에서 처음 만듦(그땐 소리 글자를 안 적어서 자막 글자로 어림)
    _op = json.load(open(os.path.join(TTS, "plan.json"), encoding="utf-8"))
    for c in _op["chunks"]:
        if "pos" in c: continue
        _ls = [_op["lines"][i] for i in c["ids"]]
        LIB["files"][os.path.basename(c["file"])] = {"v": c["v"], "spk": _ls[0]["spk"], "calm": _ls[0]["spk"] == "나레이터",
                                                     "says": [l.get("say") or say(l["text"]) for l in _ls], "texts": [l["text"] for l in _ls]}
have = lambda f: os.path.exists(os.path.join(TTS, f + ".wav"))
spent = [0, 0]   # 이번에 합성한 글자 수·호출 수


def synth(v, text, calm, prev, nxt, ids):
    name = name_of(v, text, calm); path = os.path.join(TTS, name + ".wav")
    if have(name) and REDO & set(ids):   # 같은 글자로 다시 받기 — 옛 파일은 _다시 로
        os.makedirs(os.path.join(TTS, "_다시"), exist_ok=True)
        os.replace(path, os.path.join(TTS, "_다시", f"{name}_{len(os.listdir(os.path.join(TTS, '_다시')))}.wav"))
    if not have(name):
        try:
            data = tts_call(v, text, calm, prev, nxt)
        except urllib.error.HTTPError as e:
            if "…" in text:
                text = text.replace("…", ","); data = tts_call(v, text, calm, prev, nxt)
            else:
                print("실패", name, e.code, e.read()[:200]); sys.exit(1)
        open(path, "wb").write(data); spent[0] += len(text); spent[1] += 1
        print(name, v, len(ids), "줄", text[:40]); time.sleep(0.3)
    LIB["files"][name] = {"v": v, "spk": lines[ids[0]]["spk"], "calm": calm,
                          "says": [says[i] for i in ids], "texts": [lines[i]["text"] for i in ids]}
    return name


def piece(v, ids, f, pos):   # 이미 받은 파일 f 의 pos 번째 줄들 — 파일 전체면 예전 형식 그대로
    e = LIB["files"][f]
    if pos == list(range(len(e["says"]))) and e["texts"] == [lines[i]["text"] for i in ids]:
        return {"v": v, "ids": ids, "file": "tts/" + f}
    return {"v": v, "ids": ids, "file": "tts/" + f, "pos": pos, "src_texts": e["texts"], "src_says": e["says"]}


chunks = []
for gi, g in enumerate(groups):
    v, calm = lines[g[0]]["voice"], is_narr(gi)
    name = name_of(v, gtext[gi], calm)
    redo = REDO & set(g)
    comp = LIB["groups"].get(name)   # 이 묶음을 전에 줄 단위로 맞춰 놓았으면 그대로
    if not redo and not FULL and comp and all(have(os.path.basename(c["file"])) for c in comp):
        chunks += comp; continue
    if not redo and have(name):
        LIB["files"].setdefault(name, {"v": v, "spk": lines[g[0]]["spk"], "calm": calm,
                                       "says": [says[i] for i in g], "texts": [lines[i]["text"] for i in g]})
        chunks.append({"v": v, "ids": g, "file": "tts/" + name}); continue
    prev_g = gtext[gi - 1] if gi else ""; next_g = gtext[gi + 1] if gi + 1 < len(groups) else ""
    src = [None] * len(g)   # 줄마다 (파일, 그 파일 몇 번째 줄)
    if not FULL:
        for k, i in enumerate(g):
            if i in REDO: continue
            cands = [(f, p) for f, e in LIB["files"].items() if e["v"] == v and e["spk"] == lines[i]["spk"] and e["calm"] == calm and have(f)
                     for p, s in enumerate(e["says"]) if s == says[i]]
            if not cands: continue
            if k and src[k - 1] and (src[k - 1][0], src[k - 1][1] + 1) in cands:   # 앞 줄과 같은 파일 다음 줄이면 원래 쉼 그대로 이어짐
                src[k] = (src[k - 1][0], src[k - 1][1] + 1); continue
            def run(fp):
                f, p = fp; ss = LIB["files"][f]["says"]; n = 0
                while k + n < len(g) and p + n < len(ss) and ss[p + n] == says[g[k + n]] and g[k + n] not in REDO: n += 1
                return n
            src[k] = max(cands, key=run)
    reuse = sum(len(says[i]) for k, i in enumerate(g) if src[k]); total = sum(len(says[i]) for i in g)
    if FULL or reuse < total * 0.3:
        chunks.append({"v": v, "ids": g, "file": "tts/" + synth(v, gtext[gi], calm, prev_g, next_g, g)})
        LIB["groups"].pop(name, None); continue
    comp, k = [], 0
    while k < len(g):
        ids = [g[k]]
        if src[k]:
            f, p = src[k]; pos = [p]
            while k + 1 < len(g) and src[k + 1] == (f, pos[-1] + 1): k += 1; ids.append(g[k]); pos.append(src[k][1])
            comp.append(piece(v, ids, f, pos))
        else:
            while k + 1 < len(g) and not src[k + 1]: k += 1; ids.append(g[k])
            before = [says[i] for i in g if i < ids[0]]; after = [says[i] for i in g if i > ids[-1]]
            nm = synth(v, " ".join(says[i] for i in ids), calm, " ".join(before) or prev_g, " ".join(after) or next_g, ids)
            comp.append({"v": v, "ids": ids, "file": "tts/" + nm})
        k += 1
    LIB["groups"][name] = comp; chunks += comp
    print("  줄 단위로 맞춤", name, f"{len(g)}줄 중 새로 합성 {sum(1 for s in src if not s)}줄, 나머지는 받아 둔 소리에서")
cta_out = None
if cta:
    name = "cta_" + hashlib.md5((cta["voice"] + "|" + cta["text"] + f"|t{TEMPO}" + ("|ctx" if cta["voice"] != "Daeun" else "") + "|calm").encode()).hexdigest()[:8]
    path = os.path.join(TTS, name + ".wav")
    if not os.path.exists(path):
        body = {"voice_id": VOICE_ID[cta["voice"]], "text": PRON.sub(r"\2", cta["raw"]), "model": "ssfm-v30", "language": "kor",
                "output": {"audio_format": "wav", "audio_tempo": TEMPO},
                "prompt": CALM}   # 노란 문구도 나레이션 — 잔잔하게(10-14)
        req = urllib.request.Request("https://api.typecast.ai/v1/text-to-speech", data=json.dumps(body).encode(),
                                     method="POST", headers={"X-API-KEY": KEY, "Content-Type": "application/json"})
        open(path, "wb").write(urllib.request.urlopen(req, timeout=120).read()); print(name, cta["voice"], "안내")
        spent[0] += len(cta["raw"]); spent[1] += 1
    cta_out = {"voice": cta["voice"], "text": cta["text"], "file": "tts/" + name}
json.dump({"lines": [{"spk": l["spk"], "text": l["text"], "say": s} for l, s in zip(lines, says)], "chunks": chunks, "cta": cta_out},
          open(os.path.join(TTS, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(LIB, open(LIB_P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("완료", len(lines), "줄", f"— 이번에 합성 {spent[0]}자({spent[1]}번)" if spent[1] else "— 새로 합성 없음")
