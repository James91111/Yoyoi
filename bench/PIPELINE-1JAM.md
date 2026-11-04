# Pipeline 1 jam video: Mi Pad 6 (4 core) vs GitHub Actions (Free)

**Cara baca:** angka GitHub = **hasil ukur** di runner `ubuntu-latest` milik `James91111`
(AMD EPYC 7763, 4 vCPU = 2 core fisik + SMT, 16 GB RAM, disk **88 GB kosong**).
Angka tablet = **estimasi** (belum diukur), diambil dari total 4 jam yang kamu sebut.

## 1. Berapa core yang benar-benar bisa dipakai di GitHub

| | Mi Pad 6 (4 core) | GitHub 1 job |
|---|---|---|
| Core fisik | 4 (1× A77 3,2 + 3× A77 2,42 GHz) | **2** (+SMT = 4 thread) |
| RAM | 6–8 GB | 16 GB |
| Disk | 128/256 GB | 88 GB (ephemeral) |
| Thermal | throttle setelah beberapa menit | tidak throttle |
| Paralel | 1 proses | 20 job sekaligus (80 vCPU total) |

Efisiensi thread yang **terukur** di runner:

- **faster-whisper** (small int8): 1 thread 5,04× realtime → 2 thread **9,11×** (1,81×) → 4 worker **tidak naik**.
- **ffmpeg x264** 1080p30 preset fast: 1 thread 26,3 fps → 2 thread 48,7 fps (1,85×) → 4 thread **59,4 fps (2,26×)**.

Jadi 4 vCPU itu realistis setara **2,3 core** untuk video dan **1,85 core** untuk whisper.
Tablet punyamu secara jumlah core lebih banyak, tapi per core lebih lambat dan kena throttle.

## 2. Angka ukur di runner (1 jam video 1080p30 = 108.000 frame)

| Tahap | Setelan | Throughput | Waktu untuk 1 jam video |
|---|---|---|---|
| Crop 1080×1080 + scale 720×720 | x264 veryfast | 275,5 fps | **6,5 menit** |
| Transkrip | whisper small int8, cpu_threads=2 | 9,3× realtime | **6,5 menit** |
| Render | x264 fast crf23, 4 thread | 59,4 fps | **30 menit** |
| Render | x264 fast crf23, 2 thread | 48,7 fps | 37 menit |

## 3. Perkiraan total (asumsi pembagian 4 jam di tablet)

| Tahap | Tablet 4 core | GitHub 1 job | GitHub 4 shard |
|---|---|---|---|
| Crop | ~30 mnt | 6,5 mnt | ~2 mnt |
| Transkrip | ~15 mnt | 6,5 mnt | ~2 mnt |
| TTS | ~30 mnt | 10–20 mnt | ~5 mnt |
| Render | ~2–2,5 jam | 30 mnt | 30 mnt (render sulit dipecah) |
| Setup (pip, ffmpeg, model) | — | 3–5 mnt | 3–5 mnt |
| Upload + unduh hasil | — | 10–30 mnt (tergantung internetmu) | sama |
| **Total** | **~4 jam** | **~1 jam 15 mnt** | **~55 menit** |

**Hemat: 2,5–3 jam (60–70%)** untuk video 1 jam, dengan catatan asumsi di atas benar.
Kalau videomu 4K, waktu render naik ~3–4× di kedua sisi, tapi selisihnya tetap menguntungkan GitHub.

## 4. Jebakan yang harus kamu tahu dulu

1. **Kuota artifact Free cuma 500 MB.** Video 1 jam 1080p crf23 biasanya 400–900 MB → hampir pasti
   tembus. Solusi: unggah hasil ke **Release asset** (repo publik, gratis) atau pecah per segmen.
2. **Runner dibuang tiap job.** Semua file hilang di akhir → hasil wajib di-upload/commit.
3. **Batas 1 job = 6 jam**, cukup untuk 1 video, tidak untuk batch panjang tanpa shard.
4. **Upload dari rumah sering lebih lambat dari prosesnya.** 1 jam video sumber 2 GB dengan upload
   10 Mbps = ~27 menit; ini tetap masuk hitungan total.
5. **Repo publik = semua file bisa dilihat orang.** Untuk materi sensitif pakai repo privat
   (2 vCPU, 2.000 menit/bulan) atau unduh via URL bertoken saat run.
6. **Actions bukan cloud gratis untuk beban 24 jam** — itu melanggar ToS. Pemakaian wajar (beberapa video/hari) aman.
7. Butuh **ffmpeg** — di runner terbaru tidak preinstall, `sudo apt-get install -y ffmpeg` (~45 detik).

## 5. Rekomendasi setelan

```
renders : ffmpeg -threads 4          (x264 dapat 2,26× dari 1 core)
whisper : CPU_THREADS=2, WORKERS=1   (4 worker = 0,98×, sia-sia)
shard   : 4 job untuk crop + transkrip + TTS; render tetap 1 job
hasil   : simpan ke Release asset, bukan artifact (batas 500 MB)
```
