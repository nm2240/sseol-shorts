# large-v3로 오독 확인(10-14) — check.py(medium)보다 정확, CPU라 묶음 하나에 수십 초
#   python lv3_check.py epNN               렌더 전: tts 묶음 전부를 받아써 대본과 다른 곳만(숫자 표기 차이는 무시하고 보면 됨)
#   python lv3_check.py epNN --only g_xxxx  다시 합성한 묶음만
#   python lv3_check.py epNN --redo        ⚠ 반복 묶음(타입캐스트가 문장을 두 번 읽음)을 tts/_반복/ 으로 옮김 → tts.py 다시 → 반복 없을 때까지
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
    only = sys.argv[sys.argv.index("--only") + 1:] if "--only" in sys.argv else None   # 다시 합성한 묶음만: --only g_a8571b10 ...
    redo = "--redo" in sys.argv   # 반복 묶음을 tts/_반복/ 으로 옮김 → python tts.py epNN 이 그 묶음만 다시 합성
    reps = []
    for c in p["chunks"]:
        if only and os.path.basename(c["file"]) not in only: continue
        wav = os.path.join(REPO, ep, c["file"] + ".wav")
        dur = sf.info(wav).duration
        txt = " ".join(p["lines"][i].get("say", p["lines"][i]["text"]) for i in c["ids"])
        segs, _ = m.transcribe(wav, language="ko", beam_size=5, condition_on_previous_text=False)
        segs = [s for s in segs if s.start < dur - 0.3]   # 파일 끝 뒤에 같은 문장을 또 적는 착각(ep14) 빼기
        got = " ".join(s.text.strip() for s in segs)
        a, b = norm(txt), norm(got)
        oc = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        ops = [(t, a[i1:i2], b[j1:j2]) for t, i1, i2, j1, j2 in oc if t != "equal"]
        # 반복: 받아쓰기에만 있는 4자 넘는 글 — 타입캐스트가 긴 묶음에서 앞 문장 끝을 한 번 더 읽음
        #   10-15 ep21 네 묶음(「민준이와 둘이 살죠. 남편이 떠난 뒤로」를 두 번 등). check.py는 대본 글자만 세서 못 잡음.
        #   같은 글로 다시 합성하면 대개 고쳐짐(타입캐스트 결과가 매번 다름)
        rep = [b[j1:j2] for t, i1, i2, j1, j2 in oc if t in ("insert", "replace") and (j2 - j1) - (i2 - i1) >= 4]
        if rep:
            reps.append(os.path.basename(c["file"]))
            print("⚠ 반복", c["file"], c["ids"], rep, flush=True)
            for s in segs: print(f"      {s.start:6.2f} {s.text.strip()}", flush=True)
            if redo:
                os.makedirs(os.path.join(REPO, ep, "tts", "_반복"), exist_ok=True)
                os.replace(wav, os.path.join(REPO, ep, "tts", "_반복", f"{os.path.basename(c['file'])}_{len(os.listdir(os.path.join(REPO, ep, 'tts', '_반복')))}.wav"))
        elif ops: print(c["file"], c["ids"], ops, flush=True)
    print("반복 묶음", reps if reps else "없음", "— --redo 로 옮긴 뒤 python tts.py " + ep + " 로 다시 합성" if reps and not redo else "")
    print("끝")
