# 대본 수치 점검: python script_stats.py ep07 ep08 …  — 글자 수(1,200~1,380)·대사 비율(약 25%)·나레이션 말끝(~습니다 60·~어요 25·~죠 15%, 같은 말끝 3번까지)·노란 문구 위치(약 52%)·최장 문장(60자 이하)·반전 물건 겹침(10-18)
import re, collections, sys, json
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")   # ⚠ 를 cp949 콘솔에서 찍다 죽지 않게
for ep in sys.argv[1:]:
    S = open(f"{ep}/script.txt", encoding="utf-8").read().split("\n■ 대본\n")[1].splitlines()
    L = [l for l in S if l.startswith("[")]
    txt = lambda l: re.sub(r"^\[[^\]]+\]\s*", "", l)
    tot = sum(len(txt(l)) for l in L); dlg = sum(len(txt(l)) for l in L if not l.startswith("[나레이터"))
    ends = []
    for l in L:
        if not l.startswith("[나레이터"): continue
        for s in re.split(r"(?<=[.?!])\s+", txt(l)):
            s = s.strip().rstrip(".?!'\"")
            if s: ends.append("다" if re.search(r"(니다|니까)$", s) else "죠" if s.endswith("죠") else "요" if s.endswith("요") else "-")
    c = collections.Counter(ends); n = len(ends)
    run = max(len(m.group()) for m in re.finditer(r"다+|요+|죠+", "".join(ends)))
    k = [i for i, l in enumerate(S) if l.startswith(">>>")][0]
    pos = sum(len(txt(l)) for l in S[:k] if l.startswith("[")) / tot
    print(f"{ep} 글자 {tot} 대사 {round(dlg/tot*100)}%({sum(1 for l in L if not l.startswith('[나레이터'))}번) 말끝 다{round(c['다']/n*100)} 요{round(c['요']/n*100)} 죠{round(c['죠']/n*100)} 연속최대 {run} 노란문구 {round(pos*100)}% 최장문장 {max(len(s) for l in L for s in re.split(r'(?<=[.?!])\s+', txt(l)))}")
    print("   ", "".join(ends))
    # 제목줄 한 줄 폭(도현 186, render.py TITLE_MAX 1000px) — 넘으면 render가 아무 데서나 나눔(10-15 ep25 「한 번도 안 / 오던」)
    tl = [x for x in open(f"{ep}/script.txt", encoding="utf-8").read().splitlines() if x.startswith("제목줄:")]
    if tl:
        from PIL import ImageFont
        F = ImageFont.truetype("fonts/DoHyeon-Regular.ttf", 186)
        wide = [(w, int(F.getlength(w))) for w in (re.sub(r"\([^)]*\)", "", r).strip() for r in tl[0][4:].split("/")) if F.getlength(w) > 1000]
        print("    제목줄", f"⚠ 1000px 넘는 줄 {wide} — 나눠 적을 것" if wide else "폭 괜찮음")
    # 반전 물건 겹침(10-18 사용자 「수첩을 너무 많이 써먹어. 좀 줄여」 — ep12·25·35·38이 수첩, ep05·23 공책, ep11 장부)
    #   손으로 쓴 기록장(수첩·공책·장부·일기장·가계부)은 앞 10편에 한 번이라도 있으면 ⚠, 다른 물건은 앞 3편과 같으면 ⚠
    FAM = {"기록장(수첩·공책·장부)": ("수첩", "공책", "장부", "일기장", "가계부"), "봉투": ("봉투",), "통장": ("통장",),
           "영수증": ("영수증",), "편지·쪽지": ("편지", "쪽지", "메모")}
    def used(e):
        try: B = open(f"{e}/script.txt", encoding="utf-8").read().split("\n■ 대본\n")[1]
        except (FileNotFoundError, IndexError): return set()
        return {k for k, ws in FAM.items() if sum(B.count(w) for w in ws) >= 2}
    num = int(re.sub(r"\D", "", ep))
    msg = []
    for k in sorted(used(ep)):
        back = 10 if k.startswith("기록장") else 3
        dup = [f"ep{i:02d}" for i in range(num - back, num) if k in used(f"ep{i:02d}")]
        msg.append(f"{k} ⚠ 앞 {back}편 {'·'.join(dup)}에도 씀 — 다른 물건으로" if dup else f"{k} 괜찮음")
    print("    반전 물건", " / ".join(msg) if msg else "기록장·봉투·통장·영수증·편지 안 씀")
    # 합성 전에 길이·음높이 미리 보기(10-19 사용자 "타입캐스트 tts비용이 너무많이 들어가") — analysis/voice_stats.json(python voice_stats.py)
    #   지난 편 소리로 잰 목소리별 빠르기(글자/초, 묶음 파일 앞뒤 쉼 포함)·음높이. 나레이션=normal, 대사=스마트 이모션(문맥 따라 출렁 → 범위)
    try:
        VS = json.load(open("analysis/voice_stats.json", encoding="utf-8"))
        VT = json.load(open("voices_by_age.json", encoding="utf-8"))["voices"]
        EN = {v["ko"]: v["name"] for v in VT} | {v["name"]: v["name"] for v in VT}
        han = lambda t: len(re.sub(r"[^가-힣0-9]", "", re.sub(r"\{([^{}|]*)\|([^{}]*)\}", r"\2", t)))
        tags = [re.match(r"^\[([^·\]]+)·([^\]]+)\]", l).groups() for l in L]
        groups = []
        for (sp, v), l in zip(tags, L):
            if groups and groups[-1][0] == (sp, v): groups[-1][1] += han(txt(l))
            else: groups.append([(sp, v), han(txt(l))])
        est, miss = 3 + 0.45 * len(groups), set()
        for (sp, v), n in groups:
            d = VS.get(EN.get(v, v), {}).get("narr" if sp == "나레이터" else "dlg") or VS.get(EN.get(v, v), {}).get("narr" if sp != "나레이터" else "dlg")
            if d: est += n / d["rate"]
            else: miss.add(v); est += n / 5.6
        print(f"    예상 길이(합성 전, 지난 편 빠르기) 약 {int(est // 60)}:{est % 60:04.1f}" + ("  ⚠ 2:30~2:55 밖 — 합성 전에 대본부터" if not 150 <= est <= 175 else "")
              + (f"  (표에 없는 목소리 {sorted(miss)} 는 5.6자/초로 어림)" if miss else ""))
        nv = next(EN.get(v, v) for (sp, v) in tags if sp == "나레이터")
        ref = (VS.get(nv, {}).get("narr") or {}).get("hz")
        seen, sup = set(), []
        for sp, v in tags:
            if sp == "나레이터" or (sp, v) in seen: continue
            seen.add((sp, v)); d = VS.get(EN.get(v, v), {}).get("dlg")
            if EN.get(v, v) == nv: continue   # 나레이터 본인 대사
            if not (d and d["hz"] and ref):
                print(f"    음높이 {sp}·{v}: 표에 없음 — 합성 뒤 tts_check"); continue
            st = lambda h: 12 * np.log2(h / ref)
            lo, hi = st(d["hz_min"]), st(d["hz_max"])
            w = "" if min(abs(st(d["hz"])), 99) >= 4 and (lo >= 4 or hi <= -4 or d["files"] < 2) else ("  ⚠ 4반음 안 — 다른 목소리로" if abs(st(d["hz"])) < 4 else "  △ 문맥 따라 4반음 안으로 들어올 수 있음")
            print(f"    음높이 {sp}·{v}: 대사 {d['hz']}Hz({d['hz_min']}~{d['hz_max']}) 나레이터 {nv} {ref}Hz와 {st(d['hz']):+.1f}반음({lo:+.1f}~{hi:+.1f}){w}")
            sup.append((sp, v, d["hz"]))
        for x in range(len(sup)):   # 조연끼리도 4반음(SKILL 목소리) — 서로 이어 말하는 사이면 더 중요
            for y in range(x + 1, len(sup)):
                dd = 12 * np.log2(sup[y][2] / sup[x][2])
                if abs(dd) < 4: print(f"    △ 조연끼리 {sup[x][0]}·{sup[x][1]} / {sup[y][0]}·{sup[y][1]} {dd:+.1f}반음 — 둘이 이어 말하면 바꿀 것")
    except FileNotFoundError:
        print("    (analysis/voice_stats.json 없음 — python voice_stats.py)")

