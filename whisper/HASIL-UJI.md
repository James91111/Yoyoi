# faster-whisper di GitHub Actions — hasil uji nyata

Semua angka di bawah **diukur di runner GitHub milikmu** (`James91111/Yoyoi`, publik, plan Free):
AMD EPYC 7763, 4 vCPU = **2 core fisik + SMT**, 16 GB RAM, `faster-whisper` model `small`, `int8`.

## 1. Jawaban singkat

> "Bisa jalankan di beberapa core/thread?"

Bisa, **tapi menambah worker thread tidak menambah kecepatan.** Yang menambah kecepatan hanya
menambah *thread di dalam model* (`cpu_threads`). Diukur, 6 klip × 20 detik:

| workers | cpu_threads | wall | realtime | speedup |
|---|---|---|---|---|
| 1 | 1 | 23,83 s | 5,04× | 1,00× |
| 1 | **2** | **13,17 s** | **9,11×** | **1,81×** |
| 2 | 1 | 23,70 s | 5,06× | 1,01× |
| 2 | 2 | 12,91 s | **9,30×** | **1,85×** |
| 4 | 1 | 24,21 s | 4,96× | 0,98× ← `max_workers=4` di script aslimu |
| 4 | 2 | 13,60 s | 8,82× | 1,75× |

Bacaan:

- `ThreadPoolExecutor(max_workers=4)` seperti script aslimu = **0,98×**, alias tidak ada gunanya.
- Plafon sebenarnya = **2 core fisik**. Begitu 2 core terpakai, thread tambahan cuma rebutan.
- Konfigurasi terbaik: **CPU_THREADS=2, WORKERS=1** (atau WORKERS=2 kalau ada I/O berat).
- Throughput maksimum ≈ **9,3× realtime** untuk `small` int8 → 1 jam audio ≈ 6,5 menit.

Model load: **1,16 s** dengan cache HuggingFace hangat (5,5 s tanpa cache, plus ~20–30 s unduh pertama).

## 2. Kalau butuh lebih cepat: pecah ke beberapa job (shard), bukan menambah thread

Batas Free = **20 job serentak**, tiap job dapat 4 vCPU sendiri. Jadi:

| Shard (job) | Total vCPU | 1 jam audio selesai dalam |
|---|---|---|
| 1 | 4 | ~6,5 menit |
| 4 | 16 | ~1,7 menit |
| 8 | 32 | ~50 detik |
| 20 | 80 | ~20 detik (plus overhead job) |

Overhead tiap job: ~60–90 detik (checkout, pip install, load model). Jadi untuk pekerjaan kecil,
shard 4 sudah titik manis; 20 shard baru masuk akal untuk audio > 2 jam.

## 3. Kenapa script aslimu tidak bisa langsung dipakai di Actions

| Baris di scriptmu | Masalah di Actions | Perbaikan |
|---|---|---|
| `input("Pilihan [1/2/3]: ")` | tidak ada terminal → `EOFError` | env `LANG_CODE=en/id/auto` |
| `/root/storage/downloads/...` | path itu tidak ada | folder repo `whisper/input`, output `whisper/output` |
| checkpoint `narasi.txt` | runner **dibuang** tiap run, state hilang | tiap shard tulis sendiri, job `merge` gabungkan |
| `ThreadPoolExecutor(max_workers=4)` | 0,98× (lihat tabel) | `WORKERS=1-2`, `cpu_threads=2` |
| `tqdm` | aman (jalan di log) | — |
| `metadata_file` di folder output | perlu ikut di-commit ke repo | sudah didukung (`META_FILE`) |

## 4. Yang sudah aku siapkan & uji di repo ini

- `whisper/transcribe_actions.py` — versi Actions dari scriptmu: tanpa `input()`, path relatif,
  dukung metadata 3 mode + fallback scan, dukung shard, output JSONL.
- `.github/workflows/transcribe.yml` — matrix 4 shard → `upload-artifact` → job `merge` →
  `narasi.txt`. **Sudah dijalankan dan sukses** (4 shard + merge, artefak `narasi-final` terbentuk).
- Ganti jumlah shard lewat tombol **Run workflow** (inputs: `lang`, `shards`, `model`, `cpu_threads`, `workers`).
- Taruh audio di `whisper/input/` lalu push → workflow jalan sendiri.

Catatan teknis: `av` harus dipin `<16`, karena PyAV 16 menghapus argumen `metadata_errors`
yang masih dipakai `faster-whisper` → error `open() got an unexpected keyword argument`.

## 5. Reminder biaya & aturan

- Repo publik = menit Actions **tak terbatas**, tapi batasnya **4 vCPU per job** dan **20 job serentak**.
  Runner lebih besar (8–96 vCPU, GPU) **tidak tersedia** untuk akun personal Free.
- Repo publik berarti **audio + transkrip bisa dilihat siapa pun**. Kalau materinya sensitif, pakai
  repo privat (2 vCPU, 2.000 menit/bulan) atau simpan audio di luar repo dan unduh lewat `curl` saat run.
- GitHub Actions ditujukan untuk CI/CD. Menjadikannya "komputer gratis" untuk beban berat terus-menerus
  melanggar ToS. Transkripsi berkala masih wajar; jangan dipakai untuk mining/render 24 jam.
- Opsional: set secret `HF_TOKEN` supaya unduhan model tidak kena rate-limit anonim.
