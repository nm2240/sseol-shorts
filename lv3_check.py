# large-v3로 오독 확인(10-14) — check.py(medium)보다 정확, CPU라 묶음 하나에 수십 초
#   python lv3_check.py epNN               렌더 전: tts 묶음 전부를 받아써 대본과 다른 곳만(숫자 표기 차이는 무시하고 보면 됨)
#   python lv3_check.py epNN --lines 0 21  렌더 뒤: 완성 나레이션(out/narr.wav)에서 그 줄만 다시 받아쓰기
import difflib, json, os, re, sys
import soundfile as sf
from faster_whisper import WhisperModel

REPO = os.path.dirname(os.path.abspath(__file__))
ep = sys.argv[1]
norm = lambda s: re.sub(r"[^가-힣]", "", s)
m = WhisperModel("large-v3", device="cpu", compute_type="int8")

if "--lines" in sys.argv:
    ids = [int(x) for x in sys.argv[sys.argv.index("--lines") + 1:]]
    L = json.load(open(os.path.join(REPO, ep, "out", "lines_timed.json"), encoding="utf-8"))
    y, sr = sf.read(os.path.join(REPO, ep, "out", "narr.wav"))
    tmp = os.path.join(REPO, ep, "out", "_lv3_line.wav")
    for i in ids:
        l = L[i]
        a = max(0, l.get("seg0", l["a"]) - 0.15); b = l["b"] + 0.25
        sf.write(tmp, y[int(a * sr):int(b * sr)], sr)
        segs, _ = m.transcribe(tmp, language="ko", beam_size=5)
        print(i, "대본:", l["text"]); print("   large-v3:", " ".join(s.text.strip() for s in segs), flush=True)
else:
    p = json.load(open(os.path.join(REPO, ep, "tts", "plan.json"), encoding="utf-8"))
    for c in p["chunks"]:
        txt = " ".join(p["lines"][i].get("say", p["lines"][i]["text"]) for i in c["ids"])
        segs, _ = m.transcribe(os.path.join(REPO, ep, c["file"] + ".wav"), language="ko", beam_size=5)
        got = " ".join(s.text.strip() for s in segs)
        a, b = norm(txt), norm(got)
        ops = [(t, a[i1:i2], b[j1:j2]) for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes() if t != "equal"]
        if ops: print(c["file"], c["ids"], ops, flush=True)
    print("끝")
