import json, os, time, urllib.request, numpy as np, parselmouth, soundfile as sf
KEY = open(os.path.expanduser("~/.volcano/keys/typecast"), encoding="utf-8").read().strip()
M = {v["name"]: v for v in json.load(open(r"C:\Users\Administrator\OneDrive\바탕 화면\volcano-work\타입캐스트_연령별_목소리.json", encoding="utf-8"))["voices"]}
D = os.path.dirname(os.path.abspath(__file__))
S = {"엄마": (["Kyungae", "Juha", "Kyungsook"], "저는 올해 예순여덟입니다. 남편을 먼저 보내고 시골집에서 혼자 삽니다. 이 바보야. 남들 입이 뭐가 중요해."),
     "수진": (["Jiseon", "Soyoung", "Hyewon"], "엄마, 나 오 년 전에 이혼했어. 동네에서 엄마 딸 시집 잘 갔다고 하잖아. 엄마가 걱정할까 봐…"),
     "옆집할머니": (["Jungsoon", "Sooni", "Sookhee"], "수진이 엄마는 좋겠어. 딸이 서울 부잣집으로 시집갔잖아.")}
for who, (vs, text) in S.items():
    for k, n in enumerate(vs, 1):
        p = os.path.join(D, f"{who}_{k}_{M[n]['ko']}_{n}.wav")
        if not os.path.exists(p):
            body = {"voice_id": M[n]["voice_id"], "text": text, "model": "ssfm-v30", "language": "kor",
                    "output": {"audio_format": "wav"}, "prompt": {"emotion_type": "smart"}}
            r = urllib.request.urlopen(urllib.request.Request("https://api.typecast.ai/v1/text-to-speech", data=json.dumps(body).encode(),
                    method="POST", headers={"X-API-KEY": KEY, "Content-Type": "application/json"}), timeout=120).read()
            open(p, "wb").write(r); time.sleep(0.3)
        y, sr = sf.read(p); y = y if y.ndim == 1 else y.mean(1)
        f = parselmouth.Sound(y, sr).to_pitch(pitch_floor=60, pitch_ceiling=450).selected_array["frequency"]; f = f[f > 0]
        e = np.abs(y); idx = np.where(e > 0.02)[0]; dur = (idx[-1] - idx[0]) / sr
        syl = sum(1 for c in text if "가" <= c <= "힣")
        print(f"{who:6s} {k} {M[n]['ko']}({n}) {np.median(f):4.0f}Hz  {syl/dur:4.2f}음절/초  {dur:4.1f}초")
