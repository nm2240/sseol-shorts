# 썰풀때는 81편 분석 자료(2026-10-13)

- `per_video.json`: 편별 구조(agy gemini-3.8-flash-high, 8편씩) + 조회수·길이·날짜·전환%
- `agy_종합_*.md`: 유형별 종합(agy gemini-3.1-pro-high) — 원본 그대로. 자동자막 오류("1은 한 살" = 일흔한 살)를 숫자 표기 훅으로 오해한 부분, 오열·과장 권고는 SCRIPT_FORMULA.md에서 바로잡음
- `run_agy.py`·`run_synth.py`: 분석 스크립트(자막은 yt-dlp ko 자동자막 json3 → corpus.json, 저장소엔 안 넣음)
- 정리본: ../SCRIPT_FORMULA.md
