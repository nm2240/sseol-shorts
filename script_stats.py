# 대본 수치 점검: python script_stats.py ep07 ep08 …  — 글자 수(1,200~1,380)·대사 비율(약 25%)·나레이션 말끝(~습니다 60·~어요 25·~죠 15%, 같은 말끝 3번까지)·노란 문구 위치(약 52%)·최장 문장(60자 이하)
import re, collections, sys
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
