# Hasil benchmark CPU — GitHub Actions (Free) vs Mi Pad 6

Diukur nyata di akun `James91111` (plan Free), repo `Yoyoi` (publik), runner `ubuntu-latest`.
Workflow: `.github/workflows/cpu-bench.yml` · Script: `bench/cpu_bench.py` (murni Python, tanpa dependency).

## 1. Batas maksimum CPU

| Jalur | vCPU per job | RAM | Biaya di plan Free |
|---|---|---|---|
| Actions, repo **publik** (kondisimu sekarang) | **4 vCPU** | 16 GB | gratis, menit tak terbatas |
| Actions, repo privat | 2 vCPU | 8 GB | 2.000 menit/bulan, lalu $0,006/mnt |
| Gabungan paralel (20 job serentak) | **80 vCPU** | 320 GB | gratis di repo publik |
| Codespaces | 2 vCPU (4 vCPU = 30 jam) | 8–16 GB | 120 core-hour/bulan |
| Larger runner 8–96 vCPU / GPU | — | — | **tidak tersedia** di plan Free (butuh Team/Enterprise + kartu kredit) |

Jadi angka "maksimal" ada dua: **4 vCPU per job** dan **80 vCPU total** kalau 20 job jalan bersamaan.

## 2. Spesifikasi runner yang benar-benar didapat

```
nproc            = 4
cpu              = AMD EPYC 7763 64-Core Processor
threads_per_core = 2      <-- SMT aktif
cores_per_socket = 2      <-- hanya 2 core fisik!
mem              = 15983 MB
python           = 3.14.4
```

**Temuan penting:** 4 vCPU itu = **2 core fisik × 2 thread (SMT)**, bukan 4 core fisik.
Beban per core saat dipakai 4 proses bahkan turun dari 0,203 s → 0,503 s.

## 3. Angka hasil ukur

Skor = jumlah pekerjaan selesai per detik dinding (makin besar makin cepat).

| Thread | sieve 30 jt (detik/core) | sha256 200k (detik/core) | SKOR_SIEVE | SKOR_SHA |
|---|---|---|---|---|
| 1 | 0,203 | 0,090 | 6,18 | 665 k/s |
| 2 | 0,241 | 0,089 | 10,96 | 1.180 k/s |
| 4 | 0,503 | 0,159 | 10,95 | 1.179 k/s |

**Skalabilitas:** 1→2 thread = **1,77×**, 2→4 thread = **1,00×** (nol tambahan).
Artinya kode yang di-parallel ke 4 proses di runner ini tidak lebih cepat dari 2 proses.

AES-256-GCM (hardware crypto, 16 KB blok): **≈ 3,7 GB/s**.

## 4. Dibanding Mi Pad 6 (4 core)

Mi Pad 6 = Snapdragon 870: 1× Cortex-A77 @3,2 GHz + 3× A77 @2,42 GHz + 4× A55 @1,8 GHz, RAM 6/8 GB.
Kalau kamu batasi ke 4 core performa (prime + 3 gold), itu **4 core fisik sungguhan**.

Referensi Geekbench 6: SD870 single ≈ 1.298, multi 8-core ≈ 3.520 · EPYC 7763 single ≈ 1.289–1.612.

| Skenario | GitHub 4 vCPU vs Mi Pad 6 (4 core) | Estimasi |
|---|---|---|
| Script **1 thread** (paling umum) | runner menang tipis | **1,1–1,4×** lebih cepat |
| Script **4 proses/thread** | runner cuma 2 core + HT, tablet 4 core asli | **≈ sama**, 0,9–1,2× |
| Data besar / RAM > 8 GB | runner 16 GB | menang mutlak (tablet OOM) |
| Jalan > 10 menit nonstop | server tidak throttle | tablet turun ~20–40% karena panas |
| Butuh 20 run serentak | 20 job × 4 vCPU | tablet 1 job |

Kesimpulan praktis: **beda kecepatan "per core" tidak besar (belasan sampai ~40%)**, karena Snapdragon 870
masih kompetitif. Yang benar-benar membedakan adalah **16 GB RAM, tidak ada thermal throttling, dan
paralelisasi 20 job** — bukan kecepatan satu core.

## 5. Ukur sendiri di tablet (biar apple-to-apple)

```bash
pkg install python            # Termux
python cpu_bench.py 1
python cpu_bench.py 2
python cpu_bench.py 4
```

Kirim output `SKOR_SIEVE` ke saya; nisbah dengan angka GitHub di atas langsung ketahuan persis.

## 6. Catatan lain

- Biaya: repo publik = menit tak terbatas, jadi benchmark ini **tidak memotong kuota** apa pun.
- Cold start tiap job: ~20–30 detik (runner baru tiap run, tanpa state).
- Batas 1 job = 6 jam; workflow = 35 hari.
- Commit comments / log mentah tidak bisa aku baca di sesi ini (host unduhan log diblokir), jadi hasil di atas
  diambil dari **annotasi check-run** via `api.github.com`.
