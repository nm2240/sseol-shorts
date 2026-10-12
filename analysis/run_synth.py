# 유형별 종합 — agy gemini-3.1-pro-high, 유형마다 한 번씩(순서대로)
import json, os, statistics as st, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_agy import run

D = os.path.dirname(os.path.abspath(__file__))
V = json.load(open(os.path.join(D, "per_video.json"), encoding="utf-8"))
cut = lambda s, n: (str(s) if s else "")[:n]

PROMPT = """너는 유튜브 쇼츠 대본 작가 겸 분석가다. 아래는 시니어 가족 사연 쇼츠 채널 「썰풀때는」의 「{typ}」 영상 {n}편을 편별로 요약한 표다(조회수 높은 순, 영상 길이 112~180초, 중간값 164초).
채널 공통 수치: 공백 뺀 말 속도 초당 6.7자, 중간 노란 문구 「화면을 두 번 터치하면 이야기가 이어집니다」는 영상의 52% 지점(중간값 83초), 끝에 '여러분이라면…' 질문 39/81편, 구독 요청 53/81편. 이 유형의 전환 시점 중간값은 영상의 {pc}%.
조회수 높은 편과 낮은 편을 비교해서, 이 채널 대본을 똑같이 재현할 수 있는 「대본 공식」을 한국어 마크다운으로 써라. 반드시 아래 순서와 제목으로:
## 1. 한 줄 정의
## 2. 비트 구성(초·% 단위 표: 구간 / 할 일 / 대표 문장 틀)
## 3. 문장 틀 모음(훅 첫 문장·자기소개·씨앗 장면·전환 직전(노란 문구 앞)·결정타 대사·깨달음·교훈·마지막 문장 — 각각 실제 예 2개와 빈칸 틀)
## 4. 소재 재료 목록(씨앗행동 / 전환계기 / 결말을 자주 나온 순으로, 숫자·금액·기간 쓰는 법)
## 5. 말투 규칙(어미·문장 길이·대사 비율·반복 표현)
## 6. 조회수 상위 vs 하위 차이(구체적으로, 표의 예를 들어)
## 7. 다른 채널 소재를 이 유형 대본으로 바꾸는 절차(단계별 체크리스트)
## 8. 하지 말 것
표에 근거 없는 내용은 쓰지 마라. 군더더기 인사말 없이 바로 시작.

{rows}

[조회수 상위 3편의 구간 구성]
{beats}"""

for typ in ["감동·오해형", "사이다·선긋기형"]:
    out = os.path.join(D, f"synth_{typ[:2]}.md")
    if os.path.exists(out): continue
    vs = sorted([v for v in V if v["유형"] == typ], key=lambda v: -v["views"])
    pc = st.median([v["전환%"] for v in vs if v.get("전환%")])
    rows = "\n".join(
        f"- 조회 {v['views']:,} | {v['dur']}초 | {cut(v['나레이터'], 20)} ↔ {cut(v['상대'], 20)} | 첫: {cut(v['첫두문장'], 70)} | 씨앗: {cut(v['씨앗행동'], 55)}"
        f" | 전환({v.get('전환%')}%): {cut(v['전환계기'], 55)} | 노란앞: {cut(v['노란문구직전'], 40)} | 결정타: {cut(v['결정타대사'], 55)}"
        f" | 결말: {cut(v['결말'], 50)} | 교훈: {cut(v['교훈문장'], 50)} | 끝: {cut(v['마지막문장'], 40)}" for v in vs)
    beats = "\n".join(f"* {cut(v['첫두문장'], 40)}: " + " / ".join(v["구성"]) for v in vs[:3])
    p = PROMPT.format(typ=typ, n=len(vs), pc=pc, rows=rows, beats=beats)
    print(typ, "프롬프트", len(p), "자", flush=True)
    if len(p) > 31000: sys.exit("너무 김")
    print(typ, "완료" if run(p, out, model="gemini-3.1-pro-high") else "실패", flush=True)
