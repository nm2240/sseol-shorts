# 썰쇼츠 (sseol-shorts)

「썰풀때는」 형식의 시니어 가족 감동 사연 쇼츠 프리셋. 규칙·순서는 **SKILL.md**.

```
python tts.py ep04      # 타입캐스트 TTS (키: ~/.volcano/keys/typecast)
python render.py ep04   # → ep04/out/ep04_final.mp4, 썰쇼츠 최종본/
python check.py ep04    # 점검
```
필요: Python 3.12, ffmpeg, numpy, soundfile, Pillow, faster-whisper, parselmouth(음높이 측정). 배경 mp4는 bg/SOURCES.md.
