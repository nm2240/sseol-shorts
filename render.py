# 썰쇼츠 공용 렌더러: python render.py epNN
# 타입캐스트 묶음 TTS(tts.py) → 줄 시간 정렬 → 풍경 배경 + 회색 박스 자막(1~3줄) + 다색 제목 + 노란 문구(나레이터가 읽음)
# 편마다 다른 값(제목줄·노란 문구 위치·배경 순서)은 epNN/script.txt 에서 읽는다 — SKILL.md 참고
import json, os, re, subprocess, sys
import numpy as np, soundfile as sf

REPO = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) < 2: sys.exit("사용법: python render.py epNN")
ROOT = os.path.abspath(sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(REPO, sys.argv[1]))
EP = os.path.basename(ROOT)
TTS = os.path.join(ROOT, "tts")
BG = os.path.join(REPO, "bg")   # 잔잔한 풍경 클립(pexels) — bg/SOURCES.md
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)
FONT_DIR = os.path.join(REPO, "fonts")
SCRIPT = [l.rstrip("\n") for l in open(os.path.join(ROOT, "script.txt"), encoding="utf-8-sig")]
FONT = "Do Hyeon"      # 레퍼런스 제목·자막 폰트(배민 도현체 계열, 10-12 비교 확인)
SR = 48000
MAX_LEN = 180.0       # 3분 넘을 때만 속도 조절(최후 수단, 사용자 10-12 "3분 안 넘기면 그냥 쓰자")
MIN_LEN = 150.0       # 2분 30초
SUB_LIMIT = 10        # 한 줄 10자(레퍼런스 크기 125에서 화면 안)
SUB_ROWS = 3          # 이 채널만 자막 한 화면 1~3줄(넷플릭스 한 줄 규칙 예외, 10-13)

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
    out = keep[0]
    xf = int(0.02 * SR)   # 이어 붙이는 곳은 20ms 겹쳐서(틱 소리 방지)
    for k in keep[1:]:
        if len(out) > xf and len(k) > xf:
            r = np.linspace(0, 1, xf, dtype="float32")
            out = np.concatenate([out[:-xf], out[-xf:] * (1 - r) + k[:xf] * r, k[xf:]])
        else:
            out = np.concatenate([out, k])
    return out


def soft_edges(y, a, b, thr_db=-58):
    """말소리(-38dB) 경계 a·b 바깥으로, 끝음절 여운·첫 숨이 -58dB 아래로 잦아드는 곳까지 넓힘."""
    hop = int(SR * 0.01); win = int(SR * 0.02)
    lv = lambda i: 20 * np.log10(np.sqrt(np.mean(y[i:i + win] ** 2)) + 1e-12)
    s = int(a * SR)
    while s - hop > 0 and lv(s - hop) > thr_db and (a * SR - s) < 0.4 * SR: s -= hop
    e = int(b * SR)
    while e + win < len(y) and lv(e) > thr_db and (e - b * SR) < 0.6 * SR: e += hop
    return s / SR, min(len(y) / SR, e / SR + 0.03)


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


_WM_MED = None


_LW_CACHE_P = os.path.join(OUT, "_line_words_cache.json")   # 같은 소리 조각은 다시 받아쓰지 않음(재렌더 7분 → 바뀐 줄만)
_LW_CACHE = json.load(open(_LW_CACHE_P, encoding="utf-8")) if os.path.exists(_LW_CACHE_P) else {}


def line_words(y):
    """줄 조각 하나를 medium 모델로 받아쓰기 → [(조각 안 시각, 낱말)]. 소리가 같으면 저장해 둔 결과를 씀."""
    import hashlib
    key = hashlib.md5(np.ascontiguousarray(y, dtype=np.float32).tobytes()).hexdigest()
    if key in _LW_CACHE: return [tuple(x) for x in _LW_CACHE[key]]
    res = _line_words(y)
    _LW_CACHE[key] = res
    json.dump(_LW_CACHE, open(_LW_CACHE_P, "w", encoding="utf-8"), ensure_ascii=False)
    return res


def _line_words(y):
    global _WM_MED
    if _WM_MED is None:
        from faster_whisper import WhisperModel
        _WM_MED = WhisperModel("medium", device="cpu", compute_type="int8")
    tmp = os.path.join(OUT, "_line.wav"); sf.write(tmp, y, SR)
    segs, _ = _WM_MED.transcribe(tmp, language="ko", word_timestamps=True)
    return [(w.start, w.word) for sg in segs for w in sg.words]


def whisper_anchor(words, next_text, est, start):
    """다음 줄 첫 낱말과 같은 소리로 시작하는 받아쓰기 낱말 중 어림값에 가장 가까운 것의 시작."""
    first = plain(next_text.split()[0])
    for n in (2, 1):
        key = first[:n]
        hits = [t for t, w in words if w.startswith(key) and start + 0.3 < t and abs(t - est) < 3.0]
        if hits: return min(hits, key=lambda t: abs(t - est)) - 0.2
    # 한글 숫자로 시작하는 줄(이십 년·오백만 원)은 받아쓰기가 숫자로 적음(20년) — ep07 「이십 년 동안」을 못 찾아 앞 줄 중간에서 잘림
    if re.match(r"^[일이삼사오육칠팔구]?[십백천만]|^[일이삼사오육칠팔구]+(년|원|시간|시|분|살|개월|달|명|번|평)", first):
        hits = [t for t, w in words if w[:1].isdigit() and start + 0.3 < t and abs(t - est) < 3.0]
        if hits: return min(hits, key=lambda t: abs(t - est)) - 0.2
    return None


def anchor_by_last(words, cur_text, est, start):
    """이 줄 마지막 낱말(있었습니다)을 받아쓰기에서 찾아 그 다음 낱말 시작 — 다음 줄 첫 낱말을 못 알아들었을 때(ep08 「장조림」→「당조림」)."""
    last = plain(cur_text.split()[-1])
    for n in (3, 2):
        key = last[-n:]
        hits = [k for k, (t, w) in enumerate(words[:-1]) if w.endswith(key) and start + 0.3 < t and abs(words[k + 1][0] - est) < 3.0]
        if hits: return words[min(hits, key=lambda k: abs(words[k + 1][0] - est)) + 1][0] - 0.2
    return None


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
            _a = whisper_anchor(words, lines[ids[k + 1]]["text"], est, start)
            if _a is None: _a = anchor_by_last(words, lines[i]["text"], est, start)
            if _a is not None: est = _a
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
LINE_GAP = 0.48       # 화자가 바뀔 때만 쓰는 쉼 — 같은 화자 묶음 안 문장 사이는 타입캐스트가 낸 쉼 그대로(10-13 "문장 끝나고 너무 빠르다", 0.2초 강제 폐기). 0.48 = ep04 타입캐스트 문장 사이 쉼 중간값
MIN_GAP = 0.35        # 묶음 안 문장 사이 쉼 최소(ep04 타입캐스트가 0.18~0.31초로 붙여 읽은 곳 4군데)
# 노란 '두 번 터치' 문구는 script.txt 에서 >>> 줄 바로 앞 대사 뒤에 뜬다
CTA_KEY = None
for _k, _l in enumerate(SCRIPT):
    if _l.startswith(">>>"):
        _prev = [re.match(r"\[[^\]]+\]\s*(.+)", x) for x in SCRIPT[:_k]]
        _prev = [re.sub(r"\{([^{}|]*)\|[^{}]*\}", r"\1", m.group(1)).strip() for m in _prev if m]   # {자막|소리} → 자막
        CTA_KEY = _prev[-1] if _prev else None
CTA_DUR = 3.0         # 문구가 떠 있는 동안 본 나레이션 멈춤 → 문구가 사라지는 순간 다음 줄 시작(10-12)
# 노란 문구를 읽는 목소리(10-13: ep03·ep04는 20대 여성 안내 Daeun, 새 편부터 나레이터가 이어서) — 문구 뜨고 0.15초 뒤 시작, 길면 문구를 그만큼 더 띄움
CTA_VOICE = None
if plan.get("cta"):
    _cv = load(os.path.join(ROOT, plan["cta"]["file"] + ".wav"))
    _on = np.where(np.abs(_cv) > 10 ** (-45 / 20))[0]
    CTA_VOICE = _cv[max(0, _on[0] - int(0.03 * SR)):_on[-1] + int(0.12 * SR)].copy()
    _f = int(0.02 * SR); CTA_VOICE[:_f] *= np.linspace(0, 1, _f); CTA_VOICE[-_f * 3:] *= np.linspace(1, 0, _f * 3)
    CTA_DUR = max(CTA_DUR, 0.15 + len(CTA_VOICE) / SR + 0.35)
# 끝음절 여운(-58dB까지)·첫 숨은 살린 채, 화자 바뀌는 곳 쉼이 짧아지면 그 조용한 부분끼리 겹쳐서(더해서) 붙임
pieces, cta_start, next_speech = [], None, None
for c in chunks:
    y = compress_pauses(load(os.path.join(ROOT, c["file"] + ".wav")))
    spans, head, tail = align_chunk(y, c["ids"])
    base = None   # 이 묶음 0초가 영상에서 몇 초인가 — 묶음 안 줄은 원래 간격 그대로 놓음
    for k, ((a, b), i) in enumerate(zip(spans, c["ids"])):
        if lines[i].get("skip"): continue
        # 끝음절 여운·첫 숨을 자르지 않음(10-12 "뚝뚝·틱틱 끊긴다") — 여러 문장 묶음이면 문장 사이 쉼 가운데까지만
        a0, b0 = soft_edges(y, a, b)
        a0 = max(0.0, min(a0, a - 0.05))
        if k > 0: a0 = max(a0, (spans[k - 1][1] + a) / 2)
        if k + 1 < len(spans): b0 = min(b0, (b + spans[k + 1][0]) / 2)
        seg = y[int(a0 * SR):int(b0 * SR)].copy()
        if cta_start is not None:   # 문구 다음 줄: 첫 숨소리부터 문구가 사라지는 순간에 시작(ep04: 숨이 문구 위로 새던 것 고침)
            t = cta_start; lines[i]["seg0"] = cta_start; cta_start = None
        elif next_speech is None: t = 0.05
        elif base is not None: t = max(base + a0, next_min - (a - a0))   # 같은 묶음: 타입캐스트가 낸 쉼 그대로, 단 0.35초보다 짧으면 늘림
        else: t = max(pieces[-1][0] + 0.3, next_speech - (a - a0))   # 화자 바뀜: 말소리 끝 + 0.48초
        base = t - a0
        fi, fo = int(0.02 * SR), int(0.06 * SR)
        seg[:fi] *= np.sin(np.linspace(0, np.pi / 2, fi)) ** 2; seg[-fo:] *= np.cos(np.linspace(0, np.pi / 2, fo)) ** 2
        lines[i]["a"], lines[i]["b"] = t + (a - a0), t + (b - a0)
        lines[i]["words"] = [(t + ws_, plain(w_)) for ws_, w_ in line_words(seg)]   # 줄 단위 받아쓰기(시각 정확)
        pieces.append((t, seg))
        next_speech = lines[i]["b"] + LINE_GAP
        next_min = lines[i]["b"] + MIN_GAP
        if CTA_KEY and lines[i]["text"].strip() == CTA_KEY:
            cta_start = lines[i]["b"] + 0.1 + CTA_DUR
            if CTA_VOICE is not None: pieces.append((lines[i]["b"] + 0.1 + 0.15, CTA_VOICE))
if CTA_VOICE is not None:   # 안내 목소리 크기를 본 나레이션에 맞춤(ep04: 5dB 작았음) — 봉우리는 나레이션 최대를 넘지 않게
    _act = lambda s: float(np.sqrt((s[np.abs(s) > 0.01] ** 2).mean()))
    _k = next(j for j, (s_, g_) in enumerate(pieces) if g_ is CTA_VOICE)
    _rest = [g_ for j, (s_, g_) in enumerate(pieces) if j != _k]
    _gain = min(np.median([_act(g_) for g_ in _rest]) / _act(CTA_VOICE), max(np.abs(g_).max() for g_ in _rest) / np.abs(CTA_VOICE).max())
    pieces[_k] = (pieces[_k][0], CTA_VOICE * _gain)
    print(f"노란 문구 목소리 {20 * np.log10(_gain):+.1f}dB")
narr = np.zeros(int((max(s + len(g) / SR for s, g in pieces)) * SR) + 1, "float32")
for s, g in pieces:
    narr[int(s * SR):int(s * SR) + len(g)] += g
raw_len = len(narr) / SR
speed = max(1.0, raw_len / (MAX_LEN - 0.6))
if raw_len + 0.6 < MIN_LEN: print(f"경고: {raw_len:.1f}초 — 2분 30초보다 짧음, 대본을 늘릴 것")
print(f"나레이션 {raw_len:.1f}초 → 속도 {speed:.3f}")
sf.write(os.path.join(OUT, "narr_raw.wav"), narr, SR)
af = f"atempo={speed:.4f}," if speed > 1.001 else ""
_m = subprocess.run(["ffmpeg", "-hide_banner", "-i", os.path.join(OUT, "narr_raw.wav"), "-af",
                    f"{af}loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
_m = json.loads(_m[_m.rindex("{"):_m.rindex("}") + 1])
_ln = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={_m['input_i']}:measured_TP={_m['input_tp']}:"
       f"measured_LRA={_m['input_lra']}:measured_thresh={_m['input_thresh']}:offset={_m['target_offset']}:linear=true")
run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(OUT, "narr_raw.wav"),   # 일정한 크기로(실시간 조절은 줄마다 크기가 출렁임)
     "-af", f"{af}{_ln}", "-ar", str(SR), os.path.join(OUT, "narr.wav")])
lines = [l for l in lines if not l.get("skip")]
for l in lines:
    l["a"] /= speed; l["b"] /= speed
    if "seg0" in l: l["seg0"] /= speed
    l["words"] = [(x / speed, w) for x, w in l.get("words", [])]
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


# 자막 나누기(ep03): 실제 글자 폭(도현 125)으로 재고, 문장 끝에서 먼저 나누고,
# 단위·의존명사(원·평·치·줄·때·건…)로 시작하는 줄과 작은따옴표 안에서 끊기는 줄은 피한다
from PIL import ImageFont
_SUBF = ImageFont.truetype(os.path.join(FONT_DIR, "DoHyeon-Regular.ttf"), 125)
SUB_PX = _SUBF.getlength("가" * SUB_LIMIT)
NUM_DET = {"한", "두", "세", "네", "몇", "여러"}   # 뒤에 단위가 오는 수 관형사(한 장·두 개)
SPACE = re.compile(r"^(앞|뒤|옆|위|밑|안|밖)(에|에서|에는|으로|로)?$")   # 「컨테이너 / 앞에」
AUX_HEAD = ("계", "있", "주", "보", "놓", "두", "버리", "드리")   # 「누워 / 계신」 같은 보조용언
DET = {"그", "이", "저", "그런", "이런", "저런", "무슨", "어느", "어떤", "다른"}   # 뒤 말과 붙어 다니는 관형사
DEP = re.compile(r"^(원|평|치|줄|때|건|것|게|수|번|살|개|명|년|적|뿐|듯|만큼|쯤|장|채|포기|마리|분)(을|를|이|가|은|는|에|도|만|로|로만|과|와|의|이라고|이라는|이었습니다|입니다)?$")


VARY, VARY2 = 200, 450   # 앞 화면과 줄 수가 같으면 / 세 화면 연속 같으면 벌점(10-13 "1줄에서 3줄까지 변경하면서")
MID_BRK = 900   # 쉼표·연결어미·조사가 아닌 곳(관형형 「쓸모없다던 / 그 땅」 등)에서 화면을 넘길 때 벌점
MID_SOFT = 350  # 조사 뒤(「딸에게 / 따뜻한」)에서 넘길 때
PARTICLE = re.compile(r"(은|는|이|가|을|를|에|에서|에게|께|도|만|으로|로|와|과|랑|한테)$")
ROW_BIAS = {1: -60, 2: 0, 3: 120}   # 줄 수별 벌점 — 3줄만 많아지지 않게(ep03·04 기준 1·2·3줄 약 2:4:3)
CLAUSE = re.compile(r"(니|고|며|서|데|면|지만|다가|도록|려고|니까|면서|아도|어도|해도|라도|는데|은데|더니|자|요)$")   # 화면을 넘기기 좋은 말끝


def split_line(text, dur=None, wrap=False, hist=(0, 0)):
    """한 줄(같은 화자) → (화면 목록, 마지막 두 화면 줄 수). 화면 하나 = 1~3줄(SUB_ROWS) — 10-13 "글씨가 커서 자막이 빨리 바뀌니까 어지러워"
    + "3줄 하라는 게 아니고 무료하니까 1줄에서 3줄까지 변경하면서" → 앞 화면과 줄 수가 같으면 벌점(hist = 앞 두 화면 줄 수)
    ① 문장을 화면으로 나누고(말끝·쉼표에서, 3줄 안) ② 화면 안을 줄(폭 960px)로 나눈다. 아주 짧은 문장은 다음 문장과 한 화면."""
    rate = len(plain(text)) / dur if dur else None   # 이 줄 말 속도(글자/초) — 너무 빨리 지나가는 화면을 피하려고
    sents = [x for x in re.split(r"(?<=[.?!])\s+", text.replace('"', "").strip()) if x.split()]
    screens = []   # [줄 목록, 문장 하나를 통째로 담았나, 초]
    for si, sent in enumerate(sents):
        last_sent = si == len(sents) - 1
        raw = sent.split()
        if not raw: continue
        words = [sub_clean(w) for w in raw]
        keep = [k for k, w in enumerate(words) if w]
        raw = [raw[k] for k in keep]; words = [words[k] for k in keep]
        n = len(words)
        W = lambda i, j: _SUBF.getlength(("'%s'" if wrap else "%s") % " ".join(words[i:j]))   # 대사는 작은따옴표까지 재기
        quote_open = [" ".join(raw[:k]).count("'") % 2 == 1 for k in range(n + 1)]   # k번째 앞에서 끊으면 따옴표 안인가
        secs = lambda i, j: len(plain(" ".join(words[i:j]))) / rate if rate else 9

        def brk(j):   # j번째 낱말 앞에서 끊을 때 벌점
            if j == n: return 0
            bad = 0 if raw[j - 1].endswith(",") or (re.search(BREAK_OK, words[j - 1]) and len(plain(words[j - 1])) > 1) else 200
            if DEP.match(plain(words[j])): bad += 1500   # 단위·의존명사로 시작 금지
            if plain(words[j - 1]) in NUM_DET: bad += 1500   # 「한 / 장」
            if j < n - 1 and plain(words[j]) in NUM_DET and not raw[j - 1].endswith(","): bad += 300    # 「집 / 한 채」(쉼표 뒤 「한 번도」는 괜찮음)
            if quote_open[j]: bad += 800
            if plain(words[j - 1]) in DET: bad += 1500   # 「그 / 할머니께」
            if SPACE.match(plain(words[j])): bad += 800
            if plain(words[j - 1])[-1:] in "아어워와해여셔져춰" and plain(words[j]).startswith(AUX_HEAD): bad += 600
            if "'" in raw[j] and quote_open[j] and len(plain(words[j])) <= 4: bad += 600   # 닫는 따옴표 말만 다음 줄로
            if plain(words[j]).startswith("싶") or plain(words[j]) == "말고": bad += 600   # 「보고 / 싶은」「들다 / 말고」
            if plain(words[j - 1]).endswith("의") and j - 1 > 0: bad += 300   # 「남의 / 집」 — ~의 뒤 명사와 붙임
            if plain(words[j - 1]).endswith("고") and plain(words[j])[:1] in "가갔간갈오왔와있계싶" and not raw[j - 1].endswith(","): bad += 400   # 「맡기고 / 가신」「하고 / 있었습니다」
            return bad

        _rows = {}

        def rows_of(a, b):   # words[a:b] 를 3줄 안으로 나눔 → {줄 수: (줄 목록, 벌점)} / 3줄에 안 들어가면 {}
            if (a, b) in _rows: return _rows[(a, b)]
            best = {(a, 0): (0.0, None)}   # (끝 낱말, 줄 수) → (벌점, 앞 끝)
            for j in range(a + 1, b + 1):
                for r in range(1, SUB_ROWS + 1):
                    cur = (1e18, None)
                    for i in range(j - 1, a - 1, -1):
                        if (i, r - 1) not in best: continue
                        w = W(i, j)
                        limit = 1000 if " ".join(raw[i:j]).count("'") == 2 else SUB_PX   # 따옴표 말을 통째로 담을 때만 박스가 화면 끝까지
                        if w > 1000 and j - i > 1: break
                        if w > limit and j - i > 1: continue
                        bad = brk(j) if j < b else 0
                        if len(plain(" ".join(words[i:j]))) <= 2 and not (i == a and j == b): bad += 250   # 너무 짧은 줄
                        fill = max(0.0, (SUB_PX - w) / SUB_PX * 10)
                        c = best[(i, r - 1)][0] + 60 + fill ** 2 + bad
                        if c < cur[0]: cur = (c, i)
                    if cur[1] is not None: best[(j, r)] = cur
            opts = {}   # 줄 수 → (줄 목록, 벌점) — 같은 말도 1줄·2줄로 다르게 담을 수 있게(최소 줄 수 +1까지만)
            rmin = min((r for r in range(1, SUB_ROWS + 1) if (b, r) in best), default=None)
            for r0 in range(1, SUB_ROWS + 1):
                if (b, r0) not in best or r0 > rmin + 1: continue
                out, j, r = [], b, r0
                while j > a:
                    i = best[(j, r)][1]; out.append(" ".join(words[i:j])); j = i; r -= 1
                if r0 > rmin and min(len(plain(x)) for x in out) < 4: continue   # 억지로 늘린 줄에 2~3글자만 남으면 안 씀
                opts[r0] = (out[::-1], best[(b, r0)][0])
            _rows[(a, b)] = opts
            return opts

        h0 = (len(screens[-1][0]), len(screens[-2][0]) if len(screens) > 1 else hist[0]) if screens else hist
        best = {(0,) + tuple(h0): (0.0, None)}   # (끝 낱말, 앞 화면 줄 수, 그 앞 화면 줄 수) → (벌점, (앞 상태, 줄 목록))
        for j in range(1, n + 1):
            for i in range(j - 1, -1, -1):
                opts = rows_of(i, j)
                if not opts: break
                base = 100
                if j < n: base += brk(j) * 2 + (0 if raw[j - 1].endswith(",") or CLAUSE.search(words[j - 1]) else MID_SOFT if PARTICLE.search(words[j - 1]) and len(plain(words[j - 1])) > 1 else MID_BRK)   # 화면 사이 어색한 끊김은 줄 사이보다 더 나쁨
                d = secs(i, j)
                if not (i == 0 and j == n) and d < 1.5: base += (1.5 - d) * 400 + (1200 + (1.0 - d) * 1000 if d < 1.0 else 0)   # 문장 조각이 1.5초 안에 바뀜, 1초 안은 거의 금지(ep05 「그런데」 0.4초) — 짧은 문장 통째는 아래에서 합침
                for st, (c0, _) in [(k, v) for k, v in best.items() if k[0] == i]:
                    for r, (rs, rc) in opts.items():
                        c = c0 + base + rc + ROW_BIAS[r] + (VARY if r == st[1] else 0) + (VARY2 if r == st[1] == st[2] else 0)   # 줄 수 바꿔 가며
                        key = (j, r, st[1])
                        if key not in best or c < best[key][0]: best[key] = (c, (st, rs, i == 0 and j == n, d))
        key = min((k for k in best if k[0] == n), key=lambda k: best[k][0])
        part = []
        while key[0] > 0:
            _, (pk, rs, whole, d) = best[key]; part.append([rs, whole, d]); key = pk
        screens += part[::-1]
    # 아주 짧은 문장(1.2초 안)은 다음 화면과 합침(3줄 안일 때)
    k = 0
    while k < len(screens) - 1:
        if screens[k][1] and screens[k][2] < 1.2 and len(screens[k][0]) + len(screens[k + 1][0]) <= SUB_ROWS:
            screens[k] = [screens[k][0] + screens[k + 1][0], False, screens[k][2] + screens[k + 1][2]]
            del screens[k + 1]
        else: k += 1
    out = [s[0] for s in screens]
    return out, (len(out[-1]), len(out[-2]) if len(out) > 1 else hist[0])


def sub_clean(t):
    t = t.replace("…", " ").replace('"', "")
    t = re.sub(r"[.,]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def ass_t(x):
    h, m = divmod(int(x), 3600); m, s = divmod(m, 60)
    return f"{h}:{m:02d}:{s + x % 1:05.2f}"


# 받아쓰기 낱말 시각 — 한 줄 안에서 자막이 바뀌는 순간을 실제 발음에 맞춤
# (ep03) 전체 나레이션을 한 번에 받아쓰면 시각이 0.3~0.5초씩 밀리는 구간이 있어 줄 단위 받아쓰기(lines[i]["words"])를 씀


def piece_times(l, parts):
    """줄 [a,b] 안 받아쓰기 낱말로 조각 경계를 찾음(글자 비율이 가장 가까운 낱말의 시작)."""
    ws = [(x, None, w) for x, w in l["words"] if w]
    tot = sum(len(plain(p)) for p in parts)
    rec_tot = sum(len(w[2]) for w in ws) or 1
    bounds, acc = [], 0
    for pi, p in enumerate(parts[:-1]):
        acc += len(plain(p)); f = acc / tot
        est = l["a"] + (l["b"] - l["a"]) * f
        if len(ws) >= 2:
            cum, best = 0, None
            for k, w in enumerate(ws[:-1]):
                cum += len(w[2]); d = abs(cum / rec_tot - f)
                if best is None or d < best[0]: best = (d, ws[k + 1][0])
            est = best[1]
        # 다음 조각 첫 낱말과 같은 소리로 시작하는 받아쓰기 낱말이 있으면 그 시작에 맞춤
        nxt = plain(parts[pi + 1].split()[0])
        prev_t = bounds[-1] if bounds else l["a"]
        hits = [w[0] for w in ws if w[0] > prev_t + 0.3 and abs(w[0] - est) < 1.2
                and (w[2][:2] == nxt[:2] or (len(nxt) < 2 and w[2][:1] == nxt[:1]))]
        if not hits:   # 받아쓰기는 소리 나는 대로 적음(경숙이→경수기) → 첫 글자만 맞춰 봄
            hits = [w[0] for w in ws if w[0] > prev_t + 0.3 and abs(w[0] - est) < 1.0 and w[2][:1] == nxt[:1]]
        t = (min(hits, key=lambda x: abs(x - est)) if hits else est) - 0.05
        lo = (bounds[-1] if bounds else l["a"]) + 0.4
        bounds.append(min(max(t, lo), l["b"] - 0.4))
    return [l["a"]] + bounds + [l["b"]]


events = []
sub_hist = (0, 0)
for l in lines:
    quote = l["spk"] != "나레이터"
    screens, sub_hist = split_line(l["text"], l["b"] - l["a"], wrap=quote, hist=sub_hist)
    ts = piece_times(l, [" ".join(sc) for sc in screens])
    for k, sc in enumerate(screens):
        p = r"\N".join(sc)
        events.append((ts[k], ts[k + 1], f"'{p}'" if quote else p))
# 문장 사이 쉼 동안은 앞 자막 유지(다음 자막 시작까지)
ev = []
for k, (a, b, s) in enumerate(events):
    if k + 1 < len(events): b = max(b, min(events[k + 1][0], b + 0.8))
    ev.append((a, b, s))

# 제목(썸네일 글씨)은 첫 줄을 읽는 동안만 → 다음 줄부터 자막(레퍼런스와 같음)
TITLE_END = lines[0]["b"] + 0.1
cta_line = next((i for i, l in enumerate(lines) if CTA_KEY and l["text"].strip() == CTA_KEY), None)
if cta_line is not None:
    CTA_A = lines[cta_line]["b"] + 0.1; CTA_B = lines[cta_line + 1].get("seg0", lines[cta_line + 1]["a"])   # 다음 줄 소리가 시작될 때 문구가 사라짐
else:
    CTA_A = CTA_B = 1e9

# 레퍼런스 측정(10-12): 제목 도현 186·외곽선 13·줄 간격 204·가운데 y≈950 / 자막 도현 125·외곽선 5·회색 박스 여백 40·가운데 y≈930
Y, P, W, C, G = "&H0000FFFF&", "&H00FF00FF&", "&H00FFFFFF&", "&H00FFFF00&", "&H0000FF33&"
COLOR = {"노랑": Y, "분홍": P, "흰": W, "하늘": C, "연두": G}
# 제목 글씨 줄: script.txt 의 「제목줄: 추석마다(노랑) / 시댁 일로(분홍) / …」(줄은 /, 한 줄 안 색 바꿈은 「영수증(하늘) 앞에서(흰)」)
# 없으면 첫 문장을 도현 186 폭 1000px 이하로 나눠 노랑·분홍·흰·하늘·흰… 마지막 두 줄 연두
_TF = ImageFont.truetype(os.path.join(FONT_DIR, "DoHyeon-Regular.ttf"), 186)
_tl = next((l.split(":", 1)[1] for l in SCRIPT if l.startswith("제목줄:")), None)
if _tl:
    title_rows = [[(w.strip(), COLOR[c]) for w, c in re.findall(r"([^()/]+?)\((노랑|분홍|흰|하늘|연두)\)", row)]
                  for row in _tl.split("/")]
    title_rows = [r_ for r_ in title_rows if r_]
else:
    rows, cur = [], ""
    for w in sub_clean(lines[0]["text"]).split():
        if cur and _TF.getlength(cur + " " + w) > 1000: rows.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    rows.append(cur)
    cols = [Y, P, W, C] + [W] * len(rows)
    title_rows = [[(r_, G if k >= len(rows) - 2 else cols[k])] for k, r_ in enumerate(rows)]
# 넓은 줄은 낱말 사이에서 자동으로 나눔(10-13 ep06~ep10 제목이 화면 밖으로 나감 — 경고만 하고 넘어갔었음)
TITLE_MAX = 1000   # 외곽선 13 포함 1026px — ep04 970px 줄은 화면 안(사용자 확인)
_fit = []
for r_ in title_rows:
    if _TF.getlength(" ".join(w for w, _ in r_)) > TITLE_MAX: print("제목줄 자동 나눔:", " ".join(w for w, _ in r_))
    cur = []
    for w, col in r_:
        for piece in w.split():
            cand = cur + [(piece, col)]
            if cur and _TF.getlength(" ".join(x for x, _ in cand)) > TITLE_MAX: _fit.append(cur); cur = [(piece, col)]
            else: cur = cand
    if cur: _fit.append(cur)
title_rows = _fit
TITLE_PITCH, TITLE_CY, SUB_Y = 204, 950, 930
TITLE_FS = 186
if len(title_rows) > 8:   # 8줄(높이 1632px)을 넘으면 글씨를 줄여 화면 안에
    TITLE_FS = int(186 * 8 / len(title_rows)); TITLE_PITCH = int(204 * 8 / len(title_rows))
    print(f"제목 {len(title_rows)}줄 → 글씨 {TITLE_FS}")
for r_ in title_rows:
    if _TF.getlength(" ".join(w for w, _ in r_)) * TITLE_FS / 186 > 1000: print("경고: 낱말 하나가 화면보다 넓음", r_)
cta_text = r"화면을 두 번\N터치하면\N이야기가\N이어집니다"

ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Box,{FONT},125,&HFF000000,&HFF000000,&HFF000000,&H6A282828,0,0,0,0,100,100,0,0,4,40,0,5,0,0,0,1
Style: Sub,{FONT},125,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,5,0,5,0,0,0,1
Style: Title,{FONT},186,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,13,0,5,0,0,0,1
Style: Cta,{FONT},150,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,11,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
if cta_line is not None:
    ass += f"Dialogue: 3,{ass_t(CTA_A)},{ass_t(CTA_B)},Cta,,0,0,0,,{{\\pos(540,520)}}{cta_text}\n"
y0 = TITLE_CY - TITLE_PITCH * (len(title_rows) - 1) / 2
for r, row in enumerate(title_rows):
    txt = (r"{\fs%d}" % TITLE_FS if TITLE_FS != 186 else "") + " ".join(r"{\c" + col + "}" + w for w, col in row)
    ass += f"Dialogue: 2,{ass_t(0)},{ass_t(TITLE_END)},Title,,0,0,0,,{{\\pos(540,{y0 + r * TITLE_PITCH:.0f})}}{txt}\n"
for a, b, s in ev:
    if a < TITLE_END - 0.05: continue   # 첫 줄은 제목이 대신함 — 제목 뒤 끝 조각 반짝임 방지(ep04)
    if a < CTA_A: b = min(b, CTA_A)   # 문구가 뜨면 자막은 내림(말도 멈춘 상태)
    ass += f"Dialogue: 0,{ass_t(a)},{ass_t(b)},Box,,0,0,0,,{{\\pos(540,{SUB_Y})}}{s}\n"
    ass += f"Dialogue: 1,{ass_t(a)},{ass_t(b)},Sub,,0,0,0,,{{\\pos(540,{SUB_Y})}}{s}\n"
open(os.path.join(OUT, "subs.ass"), "w", encoding="utf-8-sig").write(ass)

# ---------------------------------------------------------------- 3. 배경 이어 붙이기(1초 교차)
order = ["p28647804", "p18924458", "p33897598", "p8745485", "p39302781", "p34250395", "p12236427",
         "p36236383", "p38283242", "p32701428", "p29181257", "p34727415", "p35591195", "p39410000",
         "p29976399", "p32701429"]   # 기본 순서(ep04 새벽 이야기) — script.txt 「배경: p…, p…」로 편마다 바꿈
_bl = next((l.split(":", 1)[1] for l in SCRIPT if l.startswith("배경:")), None)
if _bl: order = [x.strip() for x in _bl.split(",") if x.strip()]


def motion(path):
    """움직임 지수: 0.1초 간격 프레임 차이 평균(주행 영상 9, 잔잔한 풍경 0.5~2.7)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "fps=10,scale=96:170,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 170, 96).astype(float)
    return float(np.abs(np.diff(fr, axis=0)).mean())


# 빠른 영상(주행·흔들림) 금지 — 움직임 지수 3 넘으면 제외(10-12 사용자 지시)
keep = []
for o in order:
    m = motion(os.path.join(BG, o + ".mp4"))
    if m > 3.0: print(f"배경 제외(빠름): {o} 움직임 {m:.2f}")
    else: keep.append(o)
order = keep
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
final = os.path.join(OUT, f"{EP}_final.mp4")
run(["ffmpeg", "-v", "error", "-y", *inputs, "-i", os.path.join(OUT, "narr.wav"),
     "-filter_complex", ";".join(fl), "-map", "[vout]", "-map", f"{na}:a",
     "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
     "-profile:v", "high", "-c:a", "aac", "-b:a", "192k",
     "-t", f"{DUR:.3f}", "-movflags", "+faststart", final])
run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(OUT, "narr.wav"), "-c:a", "libmp3lame", "-b:a", "192k",
     os.path.join(OUT, f"{EP}_narration.mp3")])
print("완성", final, f"{DUR:.1f}초")

# 완성본을 썰쇼츠\썰쇼츠 최종본 에도 넣음(10-13 사용자) — 파일 이름은 epNN_제목 첫 구절
import shutil
FINAL_DIR = os.path.join(REPO, "썰쇼츠 최종본")
os.makedirs(FINAL_DIR, exist_ok=True)
_t = next((l.split(":", 1)[1] for l in SCRIPT if l.startswith("제목:")), "")
_t = re.sub(r'[\/:*?"<>|.…]', "", _t.split(",")[0]).strip()
_dst = os.path.join(FINAL_DIR, f"{os.path.basename(ROOT)}_{_t}.mp4" if _t else os.path.basename(final))
shutil.copy2(final, _dst)
print("최종본", _dst)
