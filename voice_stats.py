# 지난 편 소리로 목소리마다 빠르기·음높이 표: python voice_stats.py → analysis/voice_stats.json
#   10-19 사용자 "타입캐스트 tts비용이 너무많이 들어가" — ep45에서 큰아들·막내 목소리를 고르느라 시험 합성을 여러 번 했음
#   (필재는 예전 기록 101Hz였는데 실제 124Hz). 합성 전에 script_stats.py 가 이 표로 길이·반음 차이를 미리 봄 → 고를 때 돈 안 씀.
#   나레이션(잔잔한 normal)과 대사(스마트 이모션)는 음높이가 달라서 따로 잼. 대사는 문맥 따라 출렁여서 범위(최저~최고)도 적음.
import glob, json, os, re, sys
import numpy as np
from tts_check import load, f0_median, SR

REPO = os.path.dirname(os.path.abspath(__file__))
PER = 8   # 목소리·말투마다 음높이는 파일 8개까지만 잼(오래 걸려서)
han = lambda t: len(re.sub(r"[^가-힣0-9]", "", t))
_VT = json.load(open(os.path.join(REPO, "voices_by_age.json"), encoding="utf-8"))["voices"]
EN = {v["ko"]: v["name"] for v in _VT} | {v["name"]: v["name"] for v in _VT}   # 태그에 한글로 쓴 것(김건)도 영문으로 합침
acc = {}
for pp in sorted(glob.glob(os.path.join(REPO, "ep*", "tts", "plan.json"))):
    ep = os.path.basename(os.path.dirname(os.path.dirname(pp)))
    p = json.load(open(pp, encoding="utf-8"))
    for c in p["chunks"]:
        if "pos" in c: continue
        wav = os.path.join(REPO, ep, c["file"] + ".wav")
        if not os.path.exists(wav): continue
        ls = [p["lines"][i] for i in c["ids"]]
        mode = "narr" if ls[0]["spk"] == "나레이터" else "dlg"
        if c["v"] not in EN: continue   # 표 밖(ep01·02 옛 이름)
        a = acc.setdefault((EN[c["v"]], mode), {"chars": 0, "dur": 0.0, "hz": [], "eps": set()})
        x = load(wav)
        a["chars"] += sum(han(l.get("say") or l["text"]) for l in ls); a["dur"] += len(x) / SR; a["eps"].add(ep)
        if len(a["hz"]) < PER and len(x) > SR:
            h = f0_median(x)
            if h: a["hz"].append(round(h))
out = {}
for (v, mode), a in sorted(acc.items()):
    if not a["dur"]: continue
    out.setdefault(v, {})[mode] = {"rate": round(a["chars"] / a["dur"], 2), "hz": int(np.median(a["hz"])) if a["hz"] else None,
                                   "hz_min": min(a["hz"]) if a["hz"] else None, "hz_max": max(a["hz"]) if a["hz"] else None,
                                   "files": len(a["hz"]), "eps": sorted(a["eps"])[-5:]}
json.dump(out, open(os.path.join(REPO, "analysis", "voice_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for v, m in out.items():
    print(v, "  ".join(f"{k} {d['rate']}자/초 {d['hz']}Hz({d['hz_min']}~{d['hz_max']})" for k, d in m.items()))
