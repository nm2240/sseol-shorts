"""노란 문구 앞뒤 받아쓰기 확인(10-28 ep121 「혀를 찼죠」의 「죠」가 문구 3초 뒤에 「쪼」로 튐 — SKILL 30번).
완성본에서 노란 문구 앞 5초~뒤 5초를 large-v3로 받아써, 문구가 끝난 뒤 다음 줄이 시작되기 전에 다른 소리(앞 줄 끝 음절)가 끼었는지 본다.
사용: python cta_check.py epNN   (check.py 를 먼저 돌려 check_log.txt 가 있어야 함 — 없으면 check.py 출력에서 문구 시각을 읽음)
"""
import json, os, re, subprocess, sys, tempfile

REPO = os.path.dirname(os.path.abspath(__file__))
ep = sys.argv[1]
d = os.path.join(REPO, ep)
log = os.path.join(d, "check_log.txt")
txt = open(log, encoding="utf8", errors="ignore").read() if os.path.exists(log) else \
    subprocess.run([sys.executable, "-X", "utf8", "check.py", ep], cwd=REPO, capture_output=True, text=True, encoding="utf8").stdout
m = re.search(r"노란 문구 ([\d.]+)~([\d.]+)초", txt)
if not m: sys.exit(f"{ep} 노란 문구 시각을 못 찾음")
x, y = float(m.group(1)), float(m.group(2))
lines = json.load(open(os.path.join(d, "out", "lines_timed.json"), encoding="utf8"))
nxt = min((l["a"] for l in lines if l["a"] >= y - 0.2), default=y + 1)
prv = max((l for l in lines if l["b"] <= x + 0.2), key=lambda l: l["b"])
s0 = max(0.0, x - 5)
wav = os.path.join(tempfile.gettempdir(), f"cta_{ep}.wav")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s0:.2f}", "-t", f"{(nxt + 4) - s0:.2f}", "-i",
                os.path.join(d, "out", f"{ep}_final.mp4"), "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
from faster_whisper import WhisperModel
m = WhisperModel("large-v3", device="cpu", compute_type="int8")
segs, _ = m.transcribe(wav, language="ko", word_timestamps=True)
words = [(s0 + w.start, s0 + w.end, w.word.strip()) for s in segs for w in s.words]
stray = [w for w in words if y - 0.1 < w[0] < nxt - 0.15]
print(f"{ep} 노란 문구 {x:.2f}~{y:.2f}초, 다음 줄 {nxt:.2f}초 / 앞 줄 끝: …{prv['text'][-12:]}")
print("  " + " ".join(f"{a:.2f}:{t}" for a, b, t in words))
print(f"  {'⚠ 문구 뒤 다음 줄 전에 낀 소리: ' + ' '.join(t for a, b, t in stray) if stray else '✓ 문구 뒤 낀 소리 없음'}")
