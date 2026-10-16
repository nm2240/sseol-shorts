# 렌더 전 점검: tts.py 다음에 길이 예상과 목소리마다 음높이(나레이터와 반음 차이)
#   10-17 ep31 1,264자가 경숙(느림)으로 약 3분 → 렌더 뒤에야 알면 10분 버림, ep34 오빠(중현 162Hz)·엄마(주하 167Hz)가
#   나레이터(지선 183Hz)와 2반음뿐 → 합성하자마자 이걸로 잡고 대본·목소리를 고친 뒤 렌더(예상은 실제와 ±3초 안)
#   python tts_check.py epNN
import json, os, subprocess, sys
import numpy as np

SR = 16000


def load(path):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32)


def f0_median(x, fmin=70, fmax=450):   # 반전 유머/tools/f0.py 와 같은 방식(자기상관, 유성음 프레임 중간값)
    n, hop = 1024, 256
    lo, hi = SR // fmax, SR // fmin
    out = []
    for i in range(0, len(x) - n, hop):
        fr = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt(np.mean(fr ** 2)) < 0.02:
            continue
        ac = np.correlate(fr, fr, "full")[n - 1:]
        ac /= ac[0] + 1e-9
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.45:
            out.append(SR / k)
    return float(np.median(out)) if out else 0.0


ep = sys.argv[1]
plan = json.load(open(os.path.join(ep, "tts", "plan.json"), encoding="utf-8"))
tot, per = 0.0, {}
for c in plan["chunks"]:
    x = load(os.path.join(ep, c["file"] + ".wav"))
    tot += len(x) / SR
    spk = plan["lines"][c["ids"][0]]["spk"]
    per.setdefault((spk, c["v"]), []).append(x)
n = len(plan["chunks"])
est = tot + 0.45 * n + 3
print(f"{ep} 예상 길이 약 {est:.0f}초({int(est // 60)}:{est % 60:04.1f}) — 음성 {tot:.1f} + 묶음 사이 {0.45 * n:.1f} + 노란 문구 3"
      + ("  ⚠ 2:30~2:55 밖 — 대본 길이를 고칠 것" if not 150 <= est <= 175 else ""))
hz = {k: f0_median(np.concatenate(v)) for k, v in per.items()}
nar = [h for (s, _), h in hz.items() if s == "나레이터"]
ref = nar[0] if nar else 0
for (s, v), h in sorted(hz.items(), key=lambda kv: kv[0][0] != "나레이터"):
    d = 12 * np.log2(h / ref) if ref and h else 0
    warn = "  ⚠ 나레이터와 4반음 안 — 다른 목소리로" if s != "나레이터" and v not in [vv for (ss, vv) in hz if ss == "나레이터"] and abs(d) < 4 else ""
    print(f"  {s:6s} {v:12s} {h:5.0f}Hz  나레이터와 {d:+.1f}반음{warn}")
