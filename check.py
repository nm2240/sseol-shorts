# 썰풀때는 완성본 점검: 받아쓰기 일치·노란 문구·틱·줄 끝 여운·짧은 자막·영상 규격
import json, os, re, sys, subprocess, difflib, numpy as np, soundfile as sf
EP = sys.argv[1]; OUT = os.path.join(EP, "out")
L = json.load(open(os.path.join(OUT, "lines_timed.json"), encoding="utf-8"))
y, sr = sf.read(os.path.join(OUT, "narr.wav")); y = y if y.ndim == 1 else y.mean(1)
norm = lambda s: re.sub(r"[^가-힣0-9A-Za-z]", "", s)
tot = ok = 0; bad = []
for i, l in enumerate(L):
    a, b = norm(l["text"]), norm("".join(w for _, w in l.get("words", [])))
    m = sum(x.size for x in difflib.SequenceMatcher(None, a, b).get_matching_blocks())
    tot += len(a); ok += m
    if m < len(a): bad.append((i, l["text"], "".join(w + " " for _, w in l.get("words", []))))
print(f"받아쓰기 일치 {ok}/{tot}")
for i, t, w in bad: print(f"  {i:2d} 대본: {t}\n     들림: {w}")
ass = open(os.path.join(OUT, "subs.ass"), encoding="utf-8-sig").read()
ts = lambda s: (lambda h, m, x: int(h) * 3600 + int(m) * 60 + float(x))(*s.split(":"))
cta = re.search(r"Dialogue: 3,([^,]+),([^,]+),Cta", ass); ca, cb = ts(cta.group(1)), ts(cta.group(2))
nxt = min(l.get("seg0", l["a"]) for l in L if l["a"] > ca)
seg = y[int((ca + 0.05) * sr):int((cb - 0.05) * sr)]
print(f"노란 문구 {ca:.2f}~{cb:.2f}초({cb - ca:.2f}초), 다음 말 시작 {nxt:.2f}초(차이 {nxt - cb:+.3f}), 문구 동안 최대 {20 * np.log10(np.abs(seg).max() + 1e-9):.0f}dB")
# 조용한 곳에서 튀는 소리(틱)
d = np.abs(np.diff(y)); fr = int(sr * 0.002); n = len(d) // fr
pk = d[:n * fr].reshape(n, fr).max(1); rms = np.sqrt((y[:n * fr] ** 2).reshape(n, fr).mean(1))
ctx = np.convolve(rms, np.ones(10) / 10, "same")
tick = np.where((pk > 0.03) & (ctx < 0.004))[0]
gp = [L[i + 1].get("seg0", L[i + 1]["a"]) - L[i]["b"] for i in range(len(L) - 1)]
gs = sorted(g for g in gp if g < 2)
print(f"줄 사이 쉼(말소리 끝→다음 말소리) 중간값 {np.median(gs):.2f}초, 최소 {gs[0]:.2f}, 최대 {gs[-1]:.2f}")
print(f"틱 {len(tick)}개", [round(t * 0.002, 2) for t in tick[:10]])
# 줄 끝 여운: 줄 사이 쉼에서 소리가 사라지기 직전 10ms 크기(뚝 끊기면 크고, 잦아들면 작음)
ends = []
for i in range(len(L) - 1):
    g = y[int(L[i]["b"] * sr):int(L[i + 1]["a"] * sr)]
    if len(g) < sr * 0.05: continue
    w = int(sr * 0.01); f = np.sqrt(np.convolve(g ** 2, np.ones(w) / w, "valid"))
    dead = np.where(f < 10 ** (-75 / 20))[0]
    if len(dead) and dead[0] >= w: ends.append((20 * np.log10(f[dead[0] - w] + 1e-9), i))
print(f"줄 끝(소리 사라지기 직전 10ms) 최대 {max(ends)[0]:.0f}dBFS, 줄 {max(ends)[1]}")
ev = re.findall(r"Dialogue: 1,([^,]+),([^,]+),Sub,,0,0,0,,\{[^}]*\}(.*)", ass)
short = [(round(ts(a), 2), round(ts(b) - ts(a), 2), t) for a, b, t in ev if ts(b) - ts(a) < 0.6]
print(f"자막 {len(ev)}조각, 0.6초 미만 {len(short)}개", short)
print(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,pix_fmt,width,height,profile:format=duration",
                      "-of", "compact", os.path.join(OUT, os.path.basename(EP) + "_final.mp4")], capture_output=True, text=True).stdout)
