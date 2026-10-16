# 텔레그램으로 먼저 보낼 미리보기(10-13 사용자 "영상이 만들어지면 항상 나에게 먼저 보내줘")
#   완성본은 80~100MB라 텔레그램 봇 한도(50MB)를 넘는다 → 720x1280·약 40MB로 줄인 사본을 만든다.
#   python tg_preview.py epNN  →  epNN\epNN_미리보기.mp4 (완성본·최종본은 그대로)
import glob, json, os, subprocess, sys

REPO = os.path.dirname(os.path.abspath(__file__))
ep = sys.argv[1]
src = sorted(glob.glob(os.path.join(REPO, "썰쇼츠 최종본", ep + "_*.mp4")))
if not src:   # 10-16 사용자가 "모두 새영상에 넣어" — 이미 새영상으로 옮긴 편을 다시 렌더한 경우
    src = sorted(glob.glob(os.path.join(REPO, "썰쇼츠 최종본", "새영상", ep + "_*.mp4")))
if not src:
    sys.exit(f"{ep} 완성본이 썰쇼츠 최종본에 없습니다")
src = src[-1]
dst = os.path.join(REPO, ep, ep + "_미리보기.mp4")

sec = float(json.loads(subprocess.run(
    ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", src],
    capture_output=True, text=True, encoding="utf-8").stdout)["format"]["duration"])
kbps = int(40 * 8 * 1024 / sec) - 128          # 40MB 안에 들게(오디오 128k 빼고)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", "scale=720:1280",
                "-c:v", "libx264", "-preset", "medium", "-b:v", f"{kbps}k",
                "-maxrate", f"{int(kbps * 1.3)}k", "-bufsize", f"{kbps * 2}k",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", dst], check=True)
mb = os.path.getsize(dst) / 1048576
print(f"미리보기 {dst}  {mb:.1f}MB  ({sec:.0f}초)")
if mb > 49:
    sys.exit("49MB를 넘었습니다 — 텔레그램으로 못 보냅니다")
