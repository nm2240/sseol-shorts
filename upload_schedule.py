# 썰쇼츠 업로드 예약(10-13 사용자 "업로드시간은 5시20분, 이후 3시간 32분 후 한편씩 다음영상 업로드"
#   + "매일 반복해서 해 주고 … 매일 7분씩 시간을 늘려 예약 걸어줘")
#   썰쇼츠 최종본\새영상 의 mp4 가운데 아직 쇼츠업로더 발사대기에 없는 것 → 가장 이른 빈 칸에 예약.
#   칸: 2026-10-14 05:20 기준, 날마다 7분씩 늦춤, 하루 5칸 3시간 32분 간격(05:20·08:52·12:24·15:56·19:28 → 다음 날 05:27…).
#       12일 주기로 다시 05:20부터(10-13 사용자 "10일 주기에 다시 05:20부터 예약" → "12일로 하자") — 12일째 06:37…20:45, 13일째 05:20.
#   같은 이름 .txt(제목·설명·해시태그)가 없는 영상은 걸지 않는다(사용자 확인 뒤 txt와 함께 넣는 규칙).
#   python upload_schedule.py          무엇을 언제 걸지 보기만
#   python upload_schedule.py --go     실제로 예약(쇼츠업로더 run.py --go --pick … --at …)
#   python upload_schedule.py --slots 3   앞으로 3일 칸만 보기
import datetime as dt, json, os, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
NEW = REPO / "썰쇼츠 최종본" / "새영상"
UP = Path(os.environ["USERPROFILE"]) / "Documents" / "쇼츠업로더"
QUEUE = UP / "발사대기.json"
LOG = REPO / "upload_schedule.log"

BASE_DAY = dt.date(2026, 10, 14)
START = 5 * 60 + 20          # 05:20
GAP = 3 * 60 + 32            # 3시간 32분
STEP = 7                     # 날마다 7분씩
PER_DAY = 5
CYCLE = 12                   # 12일마다 다시 05:20부터
LEAD = dt.timedelta(minutes=20)   # 심사확인(10분 주기)이 집어 가도록 최소 20분 앞


def day_slots(day: dt.date) -> list:
    d = (day - BASE_DAY).days % CYCLE
    first = dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=START + STEP * d)
    return [first + dt.timedelta(minutes=GAP * k) for k in range(PER_DAY)]


def future_slots(now: dt.datetime, days: int = 60):
    day = max(now.date(), BASE_DAY)
    for _ in range(days):
        for s in day_slots(day):
            if s >= now + LEAD:
                yield s
        day += dt.timedelta(days=1)


def log(msg: str):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    if "--slots" in sys.argv:
        n = int(sys.argv[sys.argv.index("--slots") + 1])
        day = max(dt.date.today(), BASE_DAY)
        for i in range(n):
            d = day + dt.timedelta(days=i)
            print(d, " ".join(f"{s:%H:%M}" for s in day_slots(d)))
        return
    go = "--go" in sys.argv
    try:
        queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        queue = []
    mine = [q for q in queue if Path(q.get("file", "")).parent == NEW]
    queued = {Path(q["file"]).name for q in mine}
    taken = {q.get("쏠때", "")[:16].replace("T", " ") for q in mine}

    vids = sorted(p for p in NEW.glob("*.mp4") if p.name not in queued)
    no_txt = [p.name for p in vids if not p.with_suffix(".txt").exists()]
    vids = [p for p in vids if p.with_suffix(".txt").exists()]
    for n in no_txt:
        log(f"건너뜀(제목 txt 없음) {n}")
    if not vids:
        if go:
            log(f"새로 걸 영상 없음 (발사대기 {len(mine)}편)")
        else:
            print(f"새로 걸 영상 없음 (발사대기 {len(mine)}편)")
        return

    plan = []
    slots = (s for s in future_slots(dt.datetime.now()) if f"{s:%Y-%m-%d %H:%M}" not in taken)
    for v in vids:
        plan.append((v.name, f"{next(slots):%Y-%m-%d %H:%M}"))
    for name, at in plan:
        print(f"  {at}  {name}")
    if not go:
        print("(보기만 — 실제로 걸려면 --go)")
        return

    py = UP / ".venv" / "Scripts" / "python.exe"
    cmd = [str(py), "run.py", "--go", "--pick", *[n for n, _ in plan],
           "--at", *[f"{n}={a}" for n, a in plan]]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run(cmd, cwd=UP, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    after = json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []
    got = {Path(q["file"]).name: q.get("쏠때", "") for q in after if Path(q.get("file", "")).parent == NEW}
    for name, at in plan:
        if name in got:
            log(f"예약 {got[name][:16]}  {name}")
        else:
            log(f"실패 {name}")
    if any(n not in got for n, _ in plan):
        log("run.py 출력 끝:\n" + "\n".join((r.stdout + r.stderr).strip().splitlines()[-15:]))
        sys.exit(1)


if __name__ == "__main__":
    main()
