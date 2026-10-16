# 썰풀때는 완성본 점검: 받아쓰기 일치·노란 문구·틱·줄 끝 여운·짧은 자막·영상 규격
import json, os, re, sys, subprocess, difflib, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")   # ⚠ 같은 글자가 cp949 콘솔에서 죽지 않게
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
empty = [i for i, l in enumerate(L) if len(norm("".join(w for _, w in l.get("words", [])))) < max(2, len(norm(l["text"])) // 4)]
if empty: print(f"⚠ 받아쓰기가 거의 빈 줄 {empty} — 타입캐스트가 알아들을 수 없는 소리를 낸 것일 수 있음(ep07 끝맺음 묶음). 원본 tts 묶음을 large-v3로 들어 보고 다시 합성")
for i, t, w in bad: print(f"  {i:2d} 대본: {t}\n     들림: {w}")
# 줄 경계 어긋남: 줄 길이에 비해 말 속도가 튀면 앞뒤 줄로 말이 넘어간 것(10-14 ep12 「남편은 마지막까지,」가 앞 줄 자막에 붙음 → 초당 9.3자)
#   대사(따옴표)는 감정 쉼("너, … 이게")이 있어 빼고 나레이션만, 그냥 빠르게 읽은 줄(1.37배)까지는 정상 — 어긋난 줄은 1.6배
rate = [(len(norm(l["text"])) / max(l["b"] - l["a"], 0.1), i) for i, l in enumerate(L) if len(norm(l["text"])) >= 8 and '"' not in l["text"]]
med = float(np.median([r for r, _ in rate]))
odd = [(i, round(r, 1)) for r, i in rate if r > med * 1.45 or r < med * 0.65]
print(f"줄 말 속도 중간값 초당 {med:.1f}자" + (f", ⚠ 튀는 줄 {odd} — 줄 경계가 어긋났는지 받아쓰기로 확인" if odd else ", 튀는 줄 없음"))
# 줄 끝 잘림: 끝 몇 글자가 다음 줄로 넘어가 끊겨 들림 — 10-16 ep28 「기다려 주지 않|잖아요」(대사라 위 속도 검사에서 빠짐, 사용자 "끊긴 곳이 있어")
#   ① 받아쓰기 끝 낱말이 대본 끝 낱말의 앞부분에서 끝남(않 ← 않잖아요) ② 같은 화자 바로 다음 줄보다 1.45배 넘게 빠른데 끝 낱말이 다름
spd = [len(norm(l["text"])) / max(l["b"] - l["a"], 0.1) for l in L]
cut = []
for i, l in enumerate(L):
    ws = [norm(w) for _, w in l.get("words", []) if norm(w)]
    last = norm(l["text"].split()[-1]) if l["text"].split() else ""
    if not ws or not last: continue
    if len(ws[-1]) <= len(last) - 2 and last.startswith(ws[-1]): cut.append(i)
    elif i + 1 < len(L) and L[i + 1]["spk"] == l["spk"] and L[i + 1]["a"] - l["b"] < 0.6 and spd[i] > spd[i + 1] * 1.45 and ws[-1] != last: cut.append(i)
    # ③ 반대로 다음 줄 첫 낱말이 이 줄 끝에 붙음(ep28 첫 고침에서 「…않잖아요 이번에는」)
    elif i + 1 < len(L) and ws[-1] != last and len(ws[-1]) >= 2 and L[i + 1]["text"].split() and norm(L[i + 1]["text"].split()[0]).startswith(ws[-1]): cut.append(i)
print(f"⚠ 줄 경계가 어긋났을 수 있음 {cut} — 끝 글자가 다음 줄로 넘어갔거나 다음 줄 첫말이 붙었는지 lv3_check.py --lines 로 확인" if cut else "줄 끝 잘림 없음")
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
# 줄 크기: 나레이션 중간값과 2dB 넘게 다르면 ⚠(10-14 사용자 "나래이션에 맞춰서 음량 체크하고 수정해" — 대사 줄이 3~7dB 작았음)
def _lvl(s):
    f = int(sr * 0.02)
    if len(s) < f: return None
    e = np.sqrt((s[:len(s) // f * f].reshape(-1, f) ** 2).mean(1) + 1e-12)
    e = e[(e > e.max() * 0.1) & (e > 10 ** (-50 / 20))]
    return 20 * np.log10(np.sqrt((e ** 2).mean())) if len(e) else None
lv = [(_lvl(y[int(l["a"] * sr):int(l["b"] * sr)]), l.get("spk", ""), i) for i, l in enumerate(L)]
lv = [x for x in lv if x[0] is not None]
ref = float(np.median([d for d, s_, _ in lv if s_ == "나레이터"] or [d for d, _, _ in lv]))
by = {}
for d, s_, _ in lv: by.setdefault(s_, []).append(d - ref)
loud = [(i, s_, round(d - ref, 1)) for d, s_, i in lv if abs(d - ref) > 2.0]
print("줄 크기(나레이션 기준) " + "  ".join(f"{k} {np.median(v):+.1f}dB" for k, v in by.items())
      + (f", ⚠ 2dB 넘게 다른 줄 {loud}" if loud else ", 2dB 넘게 다른 줄 없음"))
ev = re.findall(r"Dialogue: 1,([^,]+),([^,]+),Sub,,0,0,0,,\{[^}]*\}(.*)", ass)
# 자막 한 화면 1~3줄(10-13) — 화면이 1.2초 안에 바뀌면 어지러움
short = [(round(ts(a), 2), round(ts(b) - ts(a), 2), t) for a, b, t in ev if ts(b) - ts(a) < 1.2]
rows = [t.count(r"\N") + 1 for _, _, t in ev]
dur = [ts(b) - ts(a) for a, b, _ in ev]
run = max(len(m.group()) for m in re.finditer(r"1+|2+|3+|[4-9]+", "".join(str(min(r, 9)) for r in rows)))   # 같은 줄 수가 몇 화면 이어지나(10-13 "1줄에서 3줄까지 변경하면서")
print(f"자막 {len(ev)}화면(평균 {np.mean(dur):.1f}초, 1·2·3줄 {rows.count(1)}·{rows.count(2)}·{rows.count(3)}, 같은 줄 수 최장 연속 {run}, 4줄 이상 {sum(r > 3 for r in rows)}), 1.2초 미만 {len(short)}개", short)
print(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,pix_fmt,width,height,profile:format=duration",
                      "-of", "compact", os.path.join(OUT, os.path.basename(EP) + "_final.mp4")], capture_output=True, text=True).stdout)
