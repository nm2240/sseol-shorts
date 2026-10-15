# 썰쇼츠 업로드 예약(10-13 사용자 "업로드시간은 5시20분, 이후 3시간 32분 후 한편씩 다음영상 업로드"
#   + "매일 반복해서 해 주고 … 매일 7분씩 시간을 늘려 예약 걸어줘")
#   썰쇼츠 최종본\새영상 의 mp4 가운데 아직 쇼츠업로더 발사대기에 없는 것 → 가장 이른 빈 칸에 예약.
#   칸: 10-15 사용자 "오전 7시 26분 첫 시작에 10시 36분, 2시 52분 이렇게 올려" + "이 세 시각 + 날마다 7분씩"
#       → 2026-10-15 하루 3칸 07:26·10:36·14:52 기준, 날마다 7분씩 늦춤(10-16 07:33·10:43·14:59 …).
#       12일 주기로 다시 07:26부터(10-13 "12일로 하자") — 12일째 08:43·11:53·16:09, 13일째 07:26.
#       (10-13~14는 05:20부터 3시간 32분 간격 하루 5칸이었음 — 05:20은 업로더 심야 금지에 걸려 늦게 나갔음)
#   같은 이름 .txt(제목·설명·해시태그)가 없는 영상은 걸지 않는다(사용자 확인 뒤 txt와 함께 넣는 규칙).
#   python upload_schedule.py          무엇을 언제 걸지 보기만
#   python upload_schedule.py --go     실제로 예약 — 10-15부터 발사대기 없이 **지금 유튜브에 올리고 공개 시각 예약**
#       (사용자 "이제 내가 예약 걸으라고 하면 발사대기 하지말고 유튜브에 예약 걸면돼"): 쇼츠업로더 upload.py --manifest(publish_at=칸, time_by=user) --승인
#       → 비공개 업로드 → 검토(약 30분) 뒤 review.py가 비공개+publishAt → 그 시각에 공개. 성공하면 업로더 folders.mark_done 으로 업로드 된 영상에.
#       쓴 칸은 upload_schedule.log 「유튜브예약」·「칸 사용」 줄로 기억.
#   python upload_schedule.py --go --until 2026-10-16   그날 칸까지만 걸기
#   python upload_schedule.py --slots 3   앞으로 3일 칸만 보기
#   python upload_schedule.py --go --max 4   앞에서 4편만 걸기
import datetime as dt, json, os, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
NEW = REPO / "썰쇼츠 최종본" / "새영상"
UP = Path(os.environ["USERPROFILE"]) / "Documents" / "쇼츠업로더"
QUEUE = UP / "발사대기.json"
LOG = REPO / "upload_schedule.log"

BASE_DAY = dt.date(2026, 10, 15)
TIMES = [7 * 60 + 26, 10 * 60 + 36, 14 * 60 + 52]   # 07:26·10:36·14:52 (첫날 기준)
STEP = 7                     # 날마다 7분씩
CYCLE = 12                   # 12일마다 다시 07:26부터
LEAD = dt.timedelta(minutes=20)   # 심사확인(10분 주기)이 집어 가도록 최소 20분 앞


def day_slots(day: dt.date) -> list:
    d = (day - BASE_DAY).days % CYCLE
    return [dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=t + STEP * d) for t in TIMES]


def future_slots(now: dt.datetime, days: int = 60):
    day = max(now.date(), BASE_DAY)
    for _ in range(days):
        for s in day_slots(day):
            if s >= now + LEAD:
                yield s
        day += dt.timedelta(days=1)


def make_txt(mp4: Path) -> bool:
    """사용자가 영상만 새영상에 넣었을 때(10-13 "내가 검수하고 새영상으로 넣어 놓을께") —
    epNN/description.txt(제목: …/설명:/…/#해시태그)를 업로더 형식 [제목]/[설명]/[해시태그] 로 옆에 만든다."""
    src = REPO / mp4.name.split("_")[0] / "description.txt"
    if not src.exists():
        return False
    title, desc, tags, cur = "", [], [], None
    for line in src.read_text(encoding="utf-8-sig").splitlines():
        t = line.strip()
        if t.startswith("제목:"):
            title, cur = t[3:].strip(), None
        elif t.startswith("설명:"):
            cur = desc
            if t[3:].strip():
                desc.append(t[3:].strip())
        elif t and all(w.startswith("#") for w in t.split()):
            tags += t.split()
        elif cur is not None:
            cur.append(line.rstrip())
    if not title:
        return False
    body = "\n".join(desc).strip()
    mp4.with_suffix(".txt").write_text(f"[제목]\n{title}\n\n[설명]\n{body}\n\n[해시태그]\n{' '.join(tags)}\n",
                                       encoding="utf-8")
    return True


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
    if LOG.exists():   # 유튜브에 바로 예약한 칸·다른 식으로 쓴 칸(「칸 사용」)
        for ln in LOG.read_text(encoding="utf-8").splitlines():
            m = re.search(r"(유튜브예약|칸 사용) (\d{4}-\d\d-\d\d \d\d:\d\d)", ln)
            if m: taken.add(m.group(2))
    until = dt.date.fromisoformat(sys.argv[sys.argv.index("--until") + 1]) if "--until" in sys.argv else None

    vids = sorted(p for p in NEW.glob("*.mp4") if p.name not in queued)
    for v in vids:
        if not v.with_suffix(".txt").exists() and go and make_txt(v):
            log(f"제목 txt 만듦(epNN/description.txt) {v.with_suffix('.txt').name}")
    no_txt = [p.name for p in vids if not p.with_suffix(".txt").exists()]
    vids = [p for p in vids if p.with_suffix(".txt").exists()]
    if "--max" in sys.argv:   # 10-15 사용자 "오늘 몫 4편만" — 앞에서 N편만 걸고 나머지는 새영상에 둠
        vids = vids[:int(sys.argv[sys.argv.index("--max") + 1])]
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
        at = next(slots)
        if until and at.date() > until: break
        plan.append((v.name, f"{at:%Y-%m-%d %H:%M}"))
    if not plan:
        print("걸 칸 없음"); return
    for name, at in plan:
        print(f"  {at}  {name}")
    if not go:
        print("(보기만 — 실제로 걸려면 --go)")
        return

    py = UP / ".venv" / "Scripts" / "python.exe"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    ch = json.loads((NEW / ".채널정보.json").read_text(encoding="utf-8"))["channel_id"]   # 야담쟁이(10-14 다시 연결)
    bad = 0
    for name, at in plan:
        man = UP / "기록" / "_썰쇼츠_예약.json"
        man.write_text(json.dumps([{"channel": ch, "file": str(NEW / name), "title": "", "desc": "", "tags": [],
                                    "publish_at": at, "time_by": "user", "allow_not_short": False}],
                                  ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([str(py), "upload.py", "--manifest", str(man), "--승인"], cwd=UP, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"https://youtu\.be/[\w-]+", r.stdout)
        if m and "성공 1건" in r.stdout:
            log(f"유튜브예약 {at} {name} {m.group(0)}")
            d = subprocess.run([str(py), "-c", "import folders, sys; folders.mark_done(sys.argv[1])", str(NEW / name)],
                               cwd=UP, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if d.returncode: log(f"  파일 정리 실패(새영상에 남음 — 다시 걸리지 않게 손으로 옮길 것) {d.stderr.strip()[-120:]}")
        else:
            bad += 1
            log(f"실패 {name}\n" + "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:]))
            break   # 한도·인증 문제면 뒤 편도 똑같이 실패 — 멈추고 알림
    if bad: sys.exit(1)


if __name__ == "__main__":
    main()
