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
#   python upload_schedule.py --ch 달달콩콩 --go --max 5   달달콩콩 채널 칸에 걸기(10-25)
import datetime as dt, json, os, re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
# 10-26 사용자 「이제 g드라이브에 있어」·「업로드한 영상 따로 만들어」·「새영상 파일도 만들어서 분류하고 업로드한 후에는
#   업로드한영상으로 옮기는거 잊지말고」 → 완성본은 G:\내 드라이브\썰쇼츠, 채널마다 <채널>\새영상 · <채널>\업로드 된 영상.
FINALS = Path(r"G:\내 드라이브\썰쇼츠")
UP = Path(os.environ["USERPROFILE"]) / "Documents" / "쇼츠업로더"
QUEUE = UP / "발사대기.json"
LOG = REPO / "upload_schedule.log"

BASE_DAY = dt.date(2026, 10, 15)
# 10-24 사용자 "오늘부터 이채널 6편씩 올려" → 하루 6칸. 원래 세 칸(07:26·10:36·14:52)은 그대로 두고
#   사이와 저녁에 12:44·17:34·20:17을 보탬(12일째 +77분이어도 마지막 칸 21:34 — 업로더 0~7시 금지 밖).
TIMES = [7 * 60 + 26, 10 * 60 + 36, 12 * 60 + 44, 14 * 60 + 52, 17 * 60 + 34, 20 * 60 + 17]
# 10-26 사용자 「8시에서 5시 안에 끝내」·「항상 업로드는 이시간 안에 해야해」·「오후 5시 안에」 → 공개 시각은 늘 08:00~17:00.
#   12일째 +77분이어도 17:00 안이게 08:03~15:38(10-29부터 — 10-26~28은 이미 건 편을 창 안으로 옮겨 6편씩 채움).
TIMES = [8 * 60 + 3, 9 * 60 + 34, 11 * 60 + 5, 12 * 60 + 36, 14 * 60 + 7, 15 * 60 + 38]
# 10-26 사용자 「썰 쇼츠 야담쟁이 이제 하루 3개만 올려」 → 하루 3칸 08:03·10:36·14:52(+77분이어도 16:09).
#   이미 건 편은 하루 3편씩 10-27~11-01로 다시 나눔(10-26은 ep49·50 공개 + ep52 16:09).
TIMES = [8 * 60 + 3, 10 * 60 + 36, 14 * 60 + 52]
WINDOW = (8 * 60, 17 * 60)
STEP = 7                     # 날마다 7분씩
CYCLE = 12                   # 12일마다 다시 07:26부터
LEAD = dt.timedelta(minutes=20)   # 심사확인(10분 주기)이 집어 가도록 최소 20분 앞

# 10-25 사용자 "그럼 오늘부터 달달콩콩에 5편씩 올려" → --ch 달달콩콩: 같은 새영상에서 달달콩콩 채널로 하루 5칸.
#   야담쟁이 칸과 안 겹치게 따로(2026-10-25가 1일째, 날마다 7분씩·12일 주기), 첫날만 오후에 다섯 칸.
#   로그 줄은 「달달콩콩예약」·「달달콩콩 칸 사용」 — 야담쟁이 칸 계산과 섞이지 않게.
CHANNELS = {
    # 10-26 8~17시로: 08:41~15:29(+77분이어도 16:46). 10-26은 사용자가 1편 바로 공개 + 「5시 안에 4개 더」.
    "달달콩콩": {"id": "UC8GeQuJwGEIgGaQVc-wyGhQ", "base": dt.date(2026, 10, 25),
                 # 10-26 사용자 「달달콩콩 예약 걸어. 하루 6개씩 걸어」 → 6칸(+77분이어도 16:57), 10-26은 16:50 한 칸 보탬.
                 "times": [8 * 60 + 41, 10 * 60 + 8, 11 * 60 + 35, 13 * 60 + 2, 14 * 60 + 29, 15 * 60 + 40],
                 "special": {dt.date(2026, 10, 25): [13 * 60 + 41, 15 * 60 + 49, 17 * 60 + 58, 20 * 60 + 6, 22 * 60 + 14],
                             dt.date(2026, 10, 26): [12 * 60 + 31, 13 * 60 + 47, 15 * 60 + 3, 16 * 60 + 19, 16 * 60 + 50]}},
    # 10-26 사용자 「김로또 하루 3개」 → 하루 3칸 08:27·11:19·14:13(+77분이어도 15:30), 2026-10-27이 1일째.
    #   ep%4==3 편이 김로또 새영상으로 감(render.py). 10-26은 ep83 14:00 한 편(사용자 「김로또 채널에 썰쇼츠 한개 올려줘」).
    "김로또": {"id": "UCp0rxIJyyFwxmDXGaAq1wFQ", "base": dt.date(2026, 10, 27),
               "times": [8 * 60 + 27, 11 * 60 + 19, 14 * 60 + 13], "special": {}},
    # 10-28 사용자 「대작에 썰쇼츠 오늘부터 3편 올려줘」 → 하루 3칸 09:12·12:24·15:16(+77분이어도 16:33), 2026-10-28이 1일째.
    #   영상은 G:\내 드라이브\썰쇼츠\대작\새영상(script.txt 「채널: 대작」 또는 손으로 옮긴 편). 10-28은 인증 뒤 오후 세 칸.
    "대작": {"id": "", "base": dt.date(2026, 10, 28),
             "times": [9 * 60 + 12, 12 * 60 + 24, 15 * 60 + 16],
             "special": {dt.date(2026, 10, 28): [13 * 60 + 17, 14 * 60 + 43, 16 * 60 + 11]}},
}
CH = sys.argv[sys.argv.index("--ch") + 1] if "--ch" in sys.argv else None
if CH:
    BASE_DAY, TIMES = CHANNELS[CH]["base"], CHANNELS[CH]["times"]
TAG = f"{CH}예약" if CH else "유튜브예약"
USED = f"{CH} 칸 사용" if CH else "칸 사용"
NEW = FINALS / (CH or "야담쟁이") / "새영상"
# 10-31 사용자 「g드라이브 썰쇼츠 폴더에 넣고 각각의 채널에 업로드한후에는 각각의 폴더로」 → 완성본은 썰쇼츠 바로 아래(render.py).
#   --ch 채널이면 그 폴더에서 이 저장소 편(script.txt 「채널:」이 그 채널이고 파일 이름이 render.py 가 붙인 이름과 같은 것)만 고름 —
#   다른 세션이 같은 폴더에 넣은 같은 번호 편(예: ep152_사위 고깃집…)은 건드리지 않음.
# 10-31 오후 사용자 「이제 채널 구분없이 만들어 놓으면 순차적으로 올릴거고 올리고 난후 각각 채널의 업로드된 파일로」
#   → 「채널:」 줄은 안 봄. 어느 채널이든 번호 앞선 편부터 그 채널 칸에 걸고, 올린 채널의 업로드 된 영상으로 옮김.
ROOT_NEW = FINALS


def _mine(mp4: Path) -> bool:
    ep = mp4.name.split("_")[0]
    sc = REPO / ep / "script.txt"
    if not (CH and sc.exists()): return False
    lines = sc.read_text(encoding="utf-8-sig").splitlines()
    t = next((l.split(":", 1)[1] for l in lines if l.startswith("제목:")), "")
    t = re.sub(r'[\/:*?"<>|.…]', "", t.split(",")[0]).strip()
    return mp4.name == f"{ep}_{t}.mp4"


def _epno(p: Path) -> int:
    m = re.match(r"ep(\d+)_", p.name)
    return int(m.group(1)) if m else 10**6
DONE = FINALS / (CH or "야담쟁이") / "업로드 된 영상"


def day_slots(day: dt.date) -> list:
    if CH and day in CHANNELS[CH]["special"]:
        return [dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=t) for t in CHANNELS[CH]["special"][day]]
    d = (day - BASE_DAY).days % CYCLE
    return [dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=t + STEP * d) for t in TIMES]


def future_slots(now: dt.datetime, days: int = 60):
    day = max(now.date(), BASE_DAY)
    for _ in range(days):
        for s in day_slots(day):
            if not WINDOW[0] <= s.hour * 60 + s.minute <= WINDOW[1]:   # 8~17시 밖 칸은 절대 안 씀
                continue
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
            m = re.search(r"  (\S+예약|.*칸 사용) (\d{4}-\d\d-\d\d \d\d:\d\d)", ln)
            if m and m.group(1) in (TAG, USED): taken.add(m.group(2))
    until = dt.date.fromisoformat(sys.argv[sys.argv.index("--until") + 1]) if "--until" in sys.argv else None

    vids = sorted(p for p in NEW.glob("*.mp4") if p.name not in queued)
    if CH:   # 10-31부터 완성본은 썰쇼츠 바로 아래
        vids += sorted((p for p in ROOT_NEW.glob("ep*.mp4") if p.name not in queued and _mine(p)), key=_epno)
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
    ch = CHANNELS[CH]["id"] if CH else json.loads((NEW / ".채널정보.json").read_text(encoding="utf-8"))["channel_id"]   # 야담쟁이(10-14 다시 연결)
    bad = 0
    for name, at in plan:
        man = UP / "기록" / "_썰쇼츠_예약.json"
        src = next(v for v in vids if v.name == name)
        man.write_text(json.dumps([{"channel": ch, "file": str(src), "title": "", "desc": "", "tags": [],
                                    "publish_at": at, "time_by": "user", "allow_not_short": False}],
                                  ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([str(py), "upload.py", "--manifest", str(man), "--승인"], cwd=UP, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"https://youtu\.be/[\w-]+", r.stdout)
        if m and "성공 1건" in r.stdout:
            log(f"{TAG} {at} {name} {m.group(0)}")
            try:   # 올라간 영상+txt → 그 채널 업로드 된 영상(10-26)
                DONE.mkdir(parents=True, exist_ok=True)
                for f in (src, src.with_suffix(".txt")):
                    if f.exists(): shutil.move(str(f), str(DONE / f.name))
            except OSError as e:
                log(f"  파일 정리 실패(새영상에 남음 — 다시 걸리지 않게 손으로 옮길 것) {e}")
        else:
            bad += 1
            log(f"실패 {name}\n" + "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:]))
            break   # 한도·인증 문제면 뒤 편도 똑같이 실패 — 멈추고 알림
    if bad: sys.exit(1)


if __name__ == "__main__":
    main()
