"""썰쇼츠 편 수정용 보관(G:) → 사본 크기 확인 → 로컬 큰 중간 파일 휴지통. 사용: python backup_ep.py ep87 [ep90 ...]"""
import os, re, sys, shutil, subprocess, ctypes
from ctypes import wintypes

REPO = r"C:\Users\Administrator\OneDrive\바탕 화면\volcano-work\썰쇼츠"
G = r"G:\내 드라이브\썰쇼츠"
TOOLS = ["render.py", "tts.py", "check.py", "lv3_check.py", "tts_check.py", "script_stats.py",
         "story_check.py", "tg_preview.py", "cta_check.py", "bg_fetch.py", "upload_schedule.py", "voices_by_age.json", "SKILL.md"]
OUT_KEEP = ["narr.wav", "lines_timed.json", "subs.ass", "_line_words_cache.json"]


def recycle(path):
    # SHFileOperationW FO_DELETE + FOF_ALLOWUNDO → 휴지통
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    op = SHFILEOPSTRUCTW(None, 3, path + "\0\0", None, 0x40 | 0x10 | 0x400 | 0x4, False, None, None)
    r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if r != 0: raise RuntimeError(f"recycle failed {r} {path}")


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    if os.path.getsize(src) != os.path.getsize(dst): raise RuntimeError(f"size mismatch {dst}")


def main(ep):
    d = os.path.join(REPO, ep)
    script = open(os.path.join(d, "script.txt"), encoding="utf8").read()
    m = re.search(r"^채널:\s*(\S+)", script, re.M)
    ch = m.group(1) if m else None
    title = script.splitlines()[0].replace("제목:", "").strip()
    dst = os.path.join(G, ch, "수정용", ep)
    n = 0
    for f in os.listdir(d):
        p = os.path.join(d, f)
        if os.path.isfile(p) and f.endswith(".txt"): copy(p, os.path.join(dst, "작업", f)); n += 1
    for f in os.listdir(os.path.join(d, "tts")):
        p = os.path.join(d, "tts", f)
        if os.path.isfile(p): copy(p, os.path.join(dst, "작업", "tts", f)); n += 1
    for f in os.listdir(os.path.join(d, "out")):
        p = os.path.join(d, "out", f)
        if f in OUT_KEEP or f.endswith("_narration.mp3"): copy(p, os.path.join(dst, "작업", "out", f)); n += 1
    for f in TOOLS:
        p = os.path.join(REPO, f) if f != "SKILL.md" else os.path.join(REPO, "SKILL.md")
        if os.path.exists(p): copy(p, os.path.join(dst, "도구", f)); n += 1
    commit = subprocess.run(["git", "-C", REPO, "log", "-1", "--format=%h %s", "--", ep], capture_output=True, text=True, encoding="utf8").stdout.strip()
    with open(os.path.join(dst, "수정방법.txt"), "w", encoding="utf8") as w:
        w.write(f"""{ep} 수정 방법 (썰쇼츠 · {ch})
- 제목: {title}
- 저장소: GitHub nm2240/sseol-shorts (커밋 {commit}), 로컬 {REPO}
- 되살리기: 이 폴더의 작업\\* 를 저장소 {ep}\\ 로 복사(작업\\out → {ep}\\out). tts\\library.json·plan.json 덕분에 고친 줄만 다시 합성됨.
- 고치기: {ep}\\script.txt 수정 → python tts.py {ep} → python render.py {ep} → python check.py {ep} → python tg_preview.py {ep}
- 원본 소재: script.txt 머리의 유튜브 링크(설정만 빌림, 원본 영상은 쓰지 않음). 배경 풍경은 저장소 bg\\ — 다른 PC는 G:\\내 드라이브\\썰쇼츠\\수정용 공통\\bg 에서 render.py 가 자동으로 받아 옴(준비는 수정용 공통\\다른 PC 준비.txt).
- 완성본: {G}\\{ch}\\새영상(올린 뒤 업로드 된 영상)\\{ep}_*.mp4
""")
    # 로컬 큰 중간 파일만 휴지통(대본·tts·작은 json은 남김 — 고칠 때 바로 씀)
    freed = 0
    cands = [os.path.join(d, f"{ep}_미리보기.mp4")]
    for f in os.listdir(os.path.join(d, "out")):
        if f.endswith(".mp4") or f in ("_chunk.wav", "_line.wav", "_lv3_line.wav", "narr_raw.wav"):
            cands.append(os.path.join(d, "out", f))
    for p in cands:
        if os.path.exists(p):
            freed += os.path.getsize(p); recycle(p)
    print(f"{ep} {ch} 보관 {n}개 → {dst} · 휴지통 {freed/1e6:.0f}MB")
    return freed


if __name__ == "__main__":
    tot = sum(main(e) for e in sys.argv[1:])
    print(f"합계 휴지통 {tot/1e6:.0f}MB")
