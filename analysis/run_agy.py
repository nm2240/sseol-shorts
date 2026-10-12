# 썰풀때는 81편 편별 구조 분석 — agy(gemini-3.8-flash-high)로 8편씩 순서대로(병렬 없음)
import json, os, subprocess, sys, time

D = os.path.dirname(os.path.abspath(__file__))
AGY = os.path.join(os.environ["LOCALAPPDATA"], "agy", "bin", "agy.exe")
R = json.load(open(os.path.join(D, "corpus.json"), encoding="utf-8"))
R.sort(key=lambda r: -r["views"])
OUTD = os.path.join(D, "agy_out"); os.makedirs(OUTD, exist_ok=True)


def timed(r):
    out, nxt = [], 0
    for t, x in r["segs"]:
        if t >= nxt: out.append(f"[{int(t)}초]"); nxt = t + 10
        out.append(x)
    return " ".join(out)


PROMPT = """너는 유튜브 쇼츠 대본 분석가다. 아래는 시니어 가족 사연 쇼츠 채널 「썰풀때는」의 영상 {n}편 자동자막(구두점 없음, [N초]는 시각)이다.
편마다 아래 항목을 뽑아 JSON 배열 하나로만 답하라(설명 문장 금지, 코드블록 금지). 자막에 없는 내용은 지어내지 말고 "없음".
{{"id": 영상id, "유형": "감동·오해형" | "사이다·선긋기형" | "기타",
 "나레이터": "나이·성별·누구(예: 68세 어머니)", "상대": "갈등·오해 상대와 관계",
 "첫두문장": "영상 첫 두 문장 그대로", "훅방식": "첫 10초가 시청자를 붙잡는 방법 한 줄",
 "씨앗행동": "오해나 갈등을 만든 상대의 겉행동", "숫자": "대본에 나온 금액·기간·나이 숫자들",
 "전환계기": "진실이 드러나거나 판이 뒤집히는 계기(물건·서류·사람·한마디)", "전환시각초": 숫자,
 "노란문구직전": "'화면을 두 번 터치하면' 문구 바로 앞 문장(없으면 없음)",
 "결정타대사": "클라이맥스 대사 그대로", "결말": "마지막 행동·관계 변화",
 "교훈문장": "끝부분 교훈·깨달음 문장 그대로", "마지막문장": "마지막 문장 그대로",
 "말투": "어미·문장 길이·반복 표현 특징 한 줄",
 "구성": ["0~10초: …", "10~30초: …", "… 구간마다 한 줄씩(초 단위)"]}}

{body}"""


def run(prompt, out_path, model="gemini-3.8-flash-high"):
    for attempt in range(2):
        p = subprocess.run([AGY, "-p", prompt, "--model", model, "--print-timeout", "600s"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        txt = p.stdout.strip()
        if txt and len(txt) > 300:
            open(out_path, "w", encoding="utf-8").write(txt); return True
        print("재시도", out_path, p.returncode, (p.stderr or "")[-300:]); time.sleep(20)
    return False


if __name__ == "__main__":
    B = 8
    for bi in range(0, len(R), B):
        out = os.path.join(OUTD, f"b{bi // B:02d}.json")
        if os.path.exists(out): continue
        part = R[bi:bi + B]
        body = "\n\n".join(f"### id={r['id']} | 조회수 {r['views']} | {r['dur']}초 | 제목: {r['title']}\n{timed(r)}" for r in part)
        ok = run(PROMPT.format(n=len(part), body=body), out)
        print(time.strftime("%H:%M:%S"), "묶음", bi // B, "완료" if ok else "실패", flush=True)
    print("편별 분석 끝")
