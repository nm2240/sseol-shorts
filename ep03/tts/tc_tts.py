# 썰풀때는 타입캐스트 TTS — script.txt 의 [화자·목소리] 줄을 한 줄씩 합성(앞뒤 줄을 문맥으로 smart 감정)
import hashlib, json, os, re, sys, time, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS = os.path.join(ROOT, "tts")
KEY = open(os.path.expanduser("~/.volcano/keys/typecast"), encoding="utf-8").read().strip()
VOICE_ID = {"Jiseon": "tc_6a4f2130d153a5cac8e19996", "Sooni": "tc_60ad0841061ee28740ec2e1c",
            "Myungjoo": "tc_656059fc4db338e38f77d0bc", "Storyteller Jinsub": "tc_65571d1aa52fc0f2872045fa",
            "Hyejin": "tc_6a21054564d676539427427e", "Wonwoo": None, "Duckchun": "tc_5c3c52c95827e00008dd7f34",
            "Cheolhoon": "tc_685cdfad4027aeec7d097a28", "Mija": "tc_6059db64e2d12a32cce1b0c7",
            "Jaesun": "tc_684a7a1446e2a628b5b07230", "Sanghyun": "tc_69fc0cff784968297fb45daa",
            "Inhwa": "tc_6296a815b958a8ed9610b189", "Jungsoon": "tc_5ebea242728f5b00075e6211", "Dupil": "tc_606c6c684085209e5555abb0"}
# 연령별 목소리표(사용자 제공 72명) — 태그에 영문·한글 이름 어느 쪽을 써도 찾게
for v in json.load(open(os.path.join(ROOT, "..", "..", "타입캐스트_연령별_목소리.json"), encoding="utf-8"))["voices"]:
    VOICE_ID.setdefault(v["name"], v["voice_id"]); VOICE_ID.setdefault(v["ko"], v["voice_id"])

lines = []
for l in open(os.path.join(ROOT, "script.txt"), encoding="utf-8-sig"):
    m = re.match(r"\[([^·\]]+)·([^\]]+)\]\s*(.+)", l.strip())
    if m: lines.append({"spk": m.group(1), "voice": m.group(2), "text": m.group(3)})


def say(text):   # 따옴표는 소리에 필요 없음
    return text.replace('"', "").strip()


def tts(i):
    l = lines[i]
    body = {"voice_id": VOICE_ID[l["voice"]], "text": say(l["text"]), "model": "ssfm-v30", "language": "kor",
            "output": {"audio_format": "wav"},
            "prompt": {"emotion_type": "smart", "previous_text": say(lines[i - 1]["text"]) if i else "",
                       "next_text": say(lines[i + 1]["text"]) if i + 1 < len(lines) else ""}}
    req = urllib.request.Request("https://api.typecast.ai/v1/text-to-speech", data=json.dumps(body).encode(),
                                 method="POST", headers={"X-API-KEY": KEY, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=120).read()


# 같은 화자가 이어 말하는 줄은 최대 3문장·130자까지 한 번에 합성(10-12 "대사 끝날 때마다 말이 끊긴다":
# 한 줄씩 만들면 모든 문장을 '마지막 문장'처럼 끝을 삼킴 → 문단으로 읽혀야 끝맺음이 이어짐, ep02 방식)
groups = []
for i, l in enumerate(lines):
    g = groups[-1] if groups else None
    if g and lines[g[-1]]["voice"] == l["voice"] and lines[g[-1]]["spk"] == l["spk"] and len(g) < 3             and sum(len(lines[k]["text"]) for k in g) + len(l["text"]) <= 130:
        g.append(i)
    else:
        groups.append([i])
gtext = [" ".join(say(lines[k]["text"]) for k in g) for g in groups]


def tts_group(gi):
    v = lines[groups[gi][0]]["voice"]
    body = {"voice_id": VOICE_ID[v], "text": gtext[gi], "model": "ssfm-v30", "language": "kor",
            "output": {"audio_format": "wav"},
            "prompt": {"emotion_type": "smart", "previous_text": gtext[gi - 1] if gi else "",
                       "next_text": gtext[gi + 1] if gi + 1 < len(groups) else ""}}
    req = urllib.request.Request("https://api.typecast.ai/v1/text-to-speech", data=json.dumps(body).encode(),
                                 method="POST", headers={"X-API-KEY": KEY, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=120).read()


chunks = []
for gi, g in enumerate(groups):
    v = lines[g[0]]["voice"]
    name = "g_" + hashlib.md5((v + "|" + gtext[gi]).encode()).hexdigest()[:8]
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
json.dump({"lines": [{"spk": l["spk"], "text": l["text"]} for l in lines], "chunks": chunks},
          open(os.path.join(TTS, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("완료", len(lines), "줄")
