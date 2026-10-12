#!/bin/bash
PY=/c/volcanokit/.venv/Scripts/python.exe
for f in c*_?.txt; do
  b="${f%.txt}"; [ -f "$b.wav" ] && continue
  case "$b" in *_N) v=Achird;; *_L) v=Sadaltager;; esac
  echo "== $b $v"
  PYTHONUTF8=1 $PY /c/volcanokit/agent/vk_tts.py --text-file "$f" --out "$b.wav" --voice $v 2>&1 | tail -2
  [ -f "$b.wav" ] || { echo "FAIL $b"; exit 1; }
done
echo ALLDONE
