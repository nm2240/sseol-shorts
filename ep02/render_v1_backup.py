# 썰풀때는 ep02 렌더러: TTS 조각 → 줄 시간 정렬 → 풍경 배경 + 회색 박스 자막 + 다색 제목 + 중간 문구
import json, os, re, subprocess, sys
import numpy as np, soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
TTS = os.path.join(ROOT, "tts")
BG = os.path.join(ROOT, "bg")
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)
FONT_DIR = r"C:\Users\Administrator\Desktop\volcano-work\fonts"
FONT = "Gmarket Sans"
SR = 48000
CHUNK_GAP = 0.75      # 화자 바뀔 때 쉼
MAX_LEN = 180.0       # 3분 넘을 때만 속도 조절(최후 수단, 사용자 10-12 "3분 안 넘기면 그냥 쓰자")
MIN_LEN = 150.0       # 2분 30초
SUB_LIMIT = 12        # 한 줄 12자(84 크기에서 화면 안)

plan = json.load(open(os.path.join(TTS, "plan.json"), encoding="utf-8"))
lines, chunks = plan["lines"], plan["chunks"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print(r.stderr[-3000:]); sys.exit(1)
    return r


def load(path):
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    y = y.mean(1)
    if sr != SR:
        tmp = path + ".48k.wav"
        run(["ffmpeg", "-v", "error", "-y", "-i", path, "-ac", "1", "-ar", str(SR), tmp])
        y, _ = sf.read(tmp, dtype="float32")
    return y


def silences(y, thr_db=-38, min_len=0.12):
    """(시작, 끝) 무음 구간 — 20ms 창 RMS."""
    hop = int(SR * 0.01); win = int(SR * 0.02)
    n = max(1, (len(y) - win) // hop)
    rms = np.array([np.sqrt(np.mean(y[i * hop:i * hop + win] ** 2) + 1e-12) for i in range(n)])
    quiet = 20 * np.log10(rms) < thr_db
    out, s = [], None
    for i, q in enumerate(quiet):
        if q and s is None: s = i
        if not q and s is not None:
            if (i - s) * 0.01 >= min_len: out.append((s * 0.01, i * 0.01))
            s = None
    if s is not None: out.append((s * 0.01, n * 0.01))
    return out


PAUSE_MIN = 0.70      # 문장 사이 쉼 0.7~0.8초(사용자 선택 cmp_plain_pause, 10-12) — 말 속도는 그대로
PAUSE_MAX = 0.80


def compress_pauses(y):
    """0.25초 넘는 쉼을 0.7~0.8초로: 짧으면 가운데에 무음을 넣고, 길면 가운데를 잘라 냄."""
    keep, last = [], 0
    for a, b in silences(y, thr_db=-40, min_len=0.25):
        if a <= 0.05 or b >= len(y) / SR - 0.05: continue
        d = b - a
        if d > PAUSE_MAX:
            keep.append(y[last:int((a + PAUSE_MAX / 2) * SR)]); last = int((b - PAUSE_MAX / 2) * SR)
    keep.append(y[last:])
    return np.concatenate(keep)


def plain(t):
    return re.sub(r"[^가-힣0-9A-Za-z]", "", t)


_WM = None


def whisper_words(y):
    global _WM
    if _WM is None:
        from faster_whisper import WhisperModel
        _WM = WhisperModel("small", device="cpu", compute_type="int8")
    tmp = os.path.join(OUT, "_chunk.wav"); sf.write(tmp, y, SR)
    segs, _ = _WM.transcribe(tmp, language="ko", word_timestamps=True)
    return [(w.start, plain(w.word)) for s in segs for w in s.words if plain(w.word)]


def whisper_anchor(words, next_text, est, start):
    """다음 줄 첫 낱말과 같은 소리로 시작하는 받아쓰기 낱말 중 어림값에 가장 가까운 것의 시작."""
    first = plain(next_text.split()[0])
    for n in (2, 1):
        key = first[:n]
        hits = [t for t, w in words if w.startswith(key) and start + 0.3 < t and abs(t - est) < 3.0]
        if hits: return min(hits, key=lambda t: abs(t - est)) - 0.2
    return est


def align_chunk(y, ids):
    """줄 경계 = 글자 비율 어림 → 받아쓰기로 다음 줄 첫 낱말 위치 → 가장 가까운 무음으로 붙임."""
    sil = silences(y)
    words = whisper_words(y) if len(ids) > 1 else []
    head = sil[0][1] if sil and sil[0][0] == 0 else 0.0
    tail = sil[-1][0] if sil and sil[-1][1] >= len(y) / SR - 0.02 else len(y) / SR
    inner = [(a, b) for a, b in sil if a > head + 0.05 and b < tail - 0.05]
    lens = [len(plain(lines[i]["text"])) for i in ids]
    tot = sum(lens); spans = []; start = head; acc = 0
    used = set()
    for k, i in enumerate(ids):
        acc += lens[k]
        if k == len(ids) - 1:
            end = tail
        else:
            est = head + (tail - head) * acc / tot
            est = whisper_anchor(words, lines[ids[k + 1]]["text"], est, start)
            cands = [(abs((a + b) / 2 - est) - 0.15 * min(b - a, 1.0), j) for j, (a, b) in enumerate(inner)
                     if j not in used and (a + b) / 2 > start + 0.3]
            if cands:
                _, j = min(cands); used.add(j)
                a, b = inner[j]; end = a; nxt = b
            else:
                end = nxt = est
        spans.append((start, end))
        if k < len(ids) - 1: start = nxt
    return spans, head, tail


# ---------------------------------------------------------------- 1. 나레이션 이어 붙이기 + 줄 시간
LINE_GAP = 0.75       # 문장(줄)과 문장 사이 쉼 — 줄 안 쉼표 쉼은 그대로(0.8초 넘으면 줄임)
pieces, t = [], 0.0
for c in chunks:
    y = compress_pauses(load(os.path.join(ROOT, c["file"] + ".wav")))
    spans, head, tail = align_chunk(y, c["ids"])
    for (a, b), i in zip(spans, c["ids"]):
        if lines[i].get("skip"): continue
        seg = y[int(a * SR):int(b * SR)]
        lines[i]["a"], lines[i]["b"] = t, t + len(seg) / SR
        pieces.append(seg); t += len(seg) / SR
        pieces.append(np.zeros(int(LINE_GAP * SR), "float32")); t += LINE_GAP
narr = np.concatenate(pieces[:-1]); raw_len = len(narr) / SR
speed = max(1.0, raw_len / (MAX_LEN - 0.6))
if raw_len + 0.6 < MIN_LEN: print(f"경고: {raw_len:.1f}초 — 2분 30초보다 짧음, 대본을 늘릴 것")
print(f"나레이션 {raw_len:.1f}초 → 속도 {speed:.3f}")
sf.write(os.path.join(OUT, "narr_raw.wav"), narr, SR)
af = f"atempo={speed:.4f}," if speed > 1.001 else ""
run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(OUT, "narr_raw.wav"),
     "-af", f"{af}loudnorm=I=-16:TP=-1.5:LRA=7", "-ar", str(SR), os.path.join(OUT, "narr.wav")])
lines = [l for l in lines if not l.get("skip")]
for l in lines:
    l["a"] /= speed; l["b"] /= speed
DUR = raw_len / speed + 0.6
json.dump(lines, open(os.path.join(OUT, "lines_timed.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 2. 자막(ASS)
def nf_len(s): return sum(1.0 if ord(c) >= 0x2E80 else 0.5 for c in s)
BREAK_OK = r"([은는이가을를에의도만로와과서며고데요죠다까면니게지던한운된는든야랑께]|[?!…'\"])$"


def balanced_split(words, limit):
    n = len(words)
    L = lambda i, j: nf_len(" ".join(words[i:j]))
    best = [(0, 0.0, None)] + [(0, 1e18, None)] * n
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            ln = L(i, j)
            if ln > limit and j - i > 1: break
            cnt, cost, _ = best[i]
            bad = 0 if j == n or (re.search(BREAK_OK, words[j - 1]) and len(plain(words[j - 1])) > 1) else 200
            cand = (cnt + 1, cost + 60 + (limit - min(ln, limit)) ** 2 / 4 + bad, i)
            if cand[1] < best[j][1]: best[j] = cand
    out, j = [], n
    while j > 0:
        i = best[j][2]; out.append(" ".join(words[i:j])); j = i
    return out[::-1]


def sub_clean(t):
    t = t.replace("…", " ").replace('"', "")
    t = re.sub(r"[.,]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def ass_t(x):
    h, m = divmod(int(x), 3600); m, s = divmod(m, 60)
    return f"{h}:{m:02d}:{s + x % 1:05.2f}"


events = []
for l in lines:
    quote = l["spk"] != "나레이터"
    txt = sub_clean(l["text"])
    parts = balanced_split(txt.split(), SUB_LIMIT)
    total = sum(nf_len(p) for p in parts)
    a = l["a"]
    for k, p in enumerate(parts):
        b = l["b"] if k == len(parts) - 1 else a + (l["b"] - l["a"]) * nf_len(p) / total
        shown = f"'{p}'" if quote else p
        events.append((a, b, shown)); a = b
# 자막 사이 빈틈 메우기(다음 자막 시작까지 유지, 최대 0.6초)
ev = []
for k, (a, b, s) in enumerate(events):
    if k + 1 < len(events): b = max(b, min(events[k + 1][0], b + 0.6))
    ev.append((a, b, s))

TITLE_END = lines[1]["b"] + 0.1      # 제목 두 줄 읽는 동안 제목 화면
cta_line = next(i for i, l in enumerate(lines) if "상속 재산이 아닙니다" in l["text"])
CTA_A = lines[cta_line]["b"] + 0.1; CTA_B = CTA_A + 4.0

# 제목: 단어 덩어리마다 색(노랑·분홍·흰·하늘·연두), 검은 외곽선
Y, P, W, C, G = "&H0000FFFF&", "&H00FF33FF&", "&H00FFFFFF&", "&H00FFFF33&", "&H0033FF55&"
title_rows = [[("어머니", Y), ("삼우제 날", Y)], [("새아버지께", P)], [("짐을 싸라고", W)], [("했습니다", W)],
              [("법무사가", C), ("꺼낸", W)], [("등기부에", C)], [("얼굴을", G), ("들 수 없었습니다", G)]]
title_text = r"\N".join(" ".join(r"{\c" + col + "}" + w for w, col in row) for row in title_rows)
cta_text = r"화면을 두 번\N터치하면\N이야기가\N이어집니다"

ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT},84,&H00FFFFFF,&H00FFFFFF,&H70303030,&H70303030,-1,0,0,0,100,100,0,0,3,22,0,5,40,40,0,1
Style: Title,{FONT},118,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,9,0,5,30,30,0,1
Style: Cta,{FONT},104,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,0,5,30,30,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 2,{ass_t(0)},{ass_t(TITLE_END)},Title,,0,0,0,,{{\\pos(540,880)}}{title_text}
Dialogue: 2,{ass_t(CTA_A)},{ass_t(CTA_B)},Cta,,0,0,0,,{{\\pos(540,430)}}{cta_text}
"""
for a, b, s in ev:
    if b <= TITLE_END: continue
    a = max(a, TITLE_END)
    ass += f"Dialogue: 1,{ass_t(a)},{ass_t(b)},Sub,,0,0,0,,{{\\pos(540,860)}}{s}\n"
open(os.path.join(OUT, "subs.ass"), "w", encoding="utf-8-sig").write(ass)

# ---------------------------------------------------------------- 3. 배경 이어 붙이기(1초 교차)
order = ["p36236383", "p12236427", "p32701429", "p32701428", "p8745485", "p34250395",
         "p18924458", "p35591195", "p39410000", "p28647804", "p33897598"]
XF = 1.0
durs = [float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                   os.path.join(BG, o + ".mp4")]).stdout) for o in order]
use, acc = [], 0.0
for o, d in zip(order, durs):
    use.append((o, d)); acc += d - XF
    if acc >= DUR + 1: break
inputs, fl, prev, off = [], [], "v0", 0.0
for k, (o, d) in enumerate(use):
    inputs += ["-i", os.path.join(BG, o + ".mp4")]
    fl.append(f"[{k}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,"
              f"eq=brightness=-0.04:saturation=0.9,format=yuv420p[v{k}]")
for k in range(1, len(use)):
    off += use[k - 1][1] - XF
    fl.append(f"[{prev}][v{k}]xfade=transition=fade:duration={XF}:offset={off:.3f}[x{k}]"); prev = f"x{k}"
ass_path = os.path.join(OUT, "subs.ass").replace("\\", "/").replace(":", "\\:")
fd = FONT_DIR.replace("\\", "/").replace(":", "\\:")
fl.append(f"[{prev}]trim=0:{DUR:.3f},setpts=PTS-STARTPTS,subtitles='{ass_path}':fontsdir='{fd}'[vout]")
na = len(use)
final = os.path.join(OUT, "ep02_final.mp4")
run(["ffmpeg", "-v", "error", "-y", *inputs, "-i", os.path.join(OUT, "narr.wav"),
     "-filter_complex", ";".join(fl), "-map", "[vout]", "-map", f"{na}:a",
     "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
     "-t", f"{DUR:.3f}", "-movflags", "+faststart", final])
print("완성", final, f"{DUR:.1f}초")
