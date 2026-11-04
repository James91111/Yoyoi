#!/usr/bin/env bash
# Uji media pipeline di runner GitHub: encode x264, crop+scale, dan ruang disk.
set -uo pipefail

echo "== CPU =="
nproc
lscpu | grep -Ei 'model name|^cpu\(s\)|thread|core\(s\)'

echo "== Disk =="
df -h / /tmp 2>/dev/null | sed 's/  */ /g'

echo "== Memori =="
free -m | head -2

echo "== ffmpeg =="
ffmpeg -hide_banner -version | head -1

# 60 detik 1080p30 = 1800 frame, sebagai bahan uji
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=1920x1080:rate=30 \
  -t 60 -c:v libx264 -preset ultrafast -crf 18 /tmp/src.mp4
ls -lh /tmp/src.mp4 | awk '{print "src_size="$5}'

echo "== encode 1080p30 preset fast, skalabilitas thread =="
for t in 1 2 4; do
  start=$(date +%s.%N)
  ffmpeg -hide_banner -loglevel error -y -i /tmp/src.mp4 -c:v libx264 \
    -preset fast -crf 23 -threads "$t" /tmp/out_$t.mp4
  end=$(date +%s.%N)
  awk -v s="$start" -v e="$end" -v t="$t" \
    'BEGIN{ d=e-s; printf "threads=%s wall=%.2fs fps=%.1f\n", t, d, 1800/d }'
done

echo "== crop 1080x1080 + scale 720x720 preset veryfast (mirip tahap crop) =="
start=$(date +%s.%N)
ffmpeg -hide_banner -loglevel error -y -i /tmp/src.mp4 \
  -vf "crop=1080:1080:420:0,scale=720:720" -c:v libx264 -preset veryfast -crf 23 /tmp/crop.mp4
end=$(date +%s.%N)
awk -v s="$start" -v e="$end" 'BEGIN{ d=e-s; printf "crop+scale wall=%.2fs fps=%.1f\n", d, 1800/d }'

echo "== sisa disk setelah uji =="
df -h / | sed 's/  */ /g' | tail -1
