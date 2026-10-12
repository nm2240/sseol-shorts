# 썰쇼츠 타입캐스트 TTS: python tts.py epNN
# epNN/script.txt 의 [화자·목소리] 줄을 같은 화자끼리 통으로 합성(smart 감정, 앞뒤 묶음 문맥) → epNN/tts/plan.json
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

BANNED = {"Inhwa", "인화"}   # 10-12 사용자 "인화는 절대 쓰지 마"
lines = []
for l in open(os.path.join(ROOT, "script.txt"), encoding="utf-8-sig"):
    m = re.match(r"\[([^·\]]+)·([^\]]+)\]\s*(.+)", l.strip())
    if m: lines.append({"spk": m.group(1), "voice": m.group(2), "text": m.group(3)})
# 노란 문구 읽는 목소리 — 10-13 처음엔 20대 여성 안내(Daeun, ep04·ep03) → 같은 날 "노란 문구는 나레이션하던 인물로 그냥 이어서 해"
# → 새 편은 >>> [나레이터·나레이터 목소리] 로 적고, 앞뒤 줄을 문맥으로 넣어 이어 읽는 말투로 합성
cta, _n = None, 0
for l in open(os.path.join(ROOT, "script.txt"), encoding="utf-8-sig"):
    if re.match(r"\[([^·\]]+)·([^\]]+)\]\s*(.+)", l.strip()): _n += 1
    m = re.match(r">>>\s*\[([^·\]]+)·([^\]]+)\]\s*(.+)", l.strip())
    if m: cta = {"spk": m.group(1), "voice": m.group(2), "text": m.group(3), "pos": _n}
bad = sorted(({l["voice"] for l in lines} | ({cta["voice"]} if cta else set())) & BANNED)
if bad: sys.exit(f"금지 목소리: {bad} — 다른 목소리로 바꿀 것")


def say(text):   # 따옴표는 소리에 필요 없음
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
gtext = [" ".join(say(lines[k]["text"]) for k in g) for g in groups]


def tts_group(gi):
    v = lines[groups[gi][0]]["voice"]
    body = {"voice_id": VOICE_ID[v], "text": gtext[gi], "model": "ssfm-v30", "language": "kor",
            "output": {"audio_format": "wav", "audio_tempo": TEMPO},
            "prompt": {"emotion_type": "smart", "previous_text": gtext[gi - 1] if gi else "",
                       "next_text": gtext[gi + 1] if gi + 1 < len(groups) else ""}}
    req = urllib.request.Request("https://api.typecast.ai/v1/text-to-speech", data=json.dumps(body).encode(),
                                 method="POST", headers={"X-API-KEY": KEY, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=120).read()


chunks = []
for gi, g in enumerate(groups):
    v = lines[g[0]]["voice"]
    name = "g_" + hashlib.md5((v + "|" + gtext[gi] + ("" if TEMPO == 1.0 else f"|t{TEMPO}")).encode()).hexdigest()[:8]
    path = os.path.join(TTS, name + ".wav")
    if not os.path.exists(path):
        try:
            data = tts_group(gi)
        except urllib.error.HTTPError as e:
            if "…" in gtext[gi]:
                gtext[gi] = gtext[gi].replace("…", ","); data = tts_group(gi)
            else:
                print("실패", name, e.code, e.read()[:200]); sys.exit(1)
        open(path, "wb").write(data)
        print(name, v, len(g), "줄", gtext[gi][:40]); time.sleep(0.3)
    chunks.append({"v": v, "ids": g, "file": "tts/" + name})
cta_out = None
if cta:
    name = "cta_" + hashlib.md5((cta["voice"] + "|" + cta["text"] + f"|t{TEMPO}" + ("|ctx" if cta["voice"] != "Daeun" else "")).encode()).hexdigest()[:8]
    path = os.path.join(TTS, name + ".wav")
    if not os.path.exists(path):
        body = {"voice_id": VOICE_ID[cta["voice"]], "text": cta["text"], "model": "ssfm-v30", "language": "kor",
                "output": {"audio_format": "wav", "audio_tempo": TEMPO},
                "prompt": {"emotion_type": "smart", "previous_text": say(lines[cta["pos"] - 1]["text"]) if cta["pos"] else "",
                           "next_text": say(lines[cta["pos"]]["text"]) if cta["pos"] < len(lines) else ""}}
        req = urllib.request.Request("https://api.typecast.ai/v1/text-to-speech", data=json.dumps(body).encode(),
                                     method="POST", headers={"X-API-KEY": KEY, "Content-Type": "application/json"})
        open(path, "wb").write(urllib.request.urlopen(req, timeout=120).read()); print(name, cta["voice"], "안내")
    cta_out = {"voice": cta["voice"], "text": cta["text"], "file": "tts/" + name}
json.dump({"lines": [{"spk": l["spk"], "text": l["text"]} for l in lines], "chunks": chunks, "cta": cta_out},
          open(os.path.join(TTS, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("완료", len(lines), "줄")
