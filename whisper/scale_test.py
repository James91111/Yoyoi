#!/usr/bin/env python3
"""Uji skalabilitas faster-whisper di runner GitHub 4 vCPU (= 2 core fisik).

Mengukur: berapa worker paralel yang benar-benar menambah throughput untuk
model small int8, dan berapa cpu_threads yang optimal per worker.

Jalankan: python3 whisper/scale_test.py
Tidak butuh audio asli — dibuat noise sintetis 20 detik (biaya komputasi
whisper ditentukan panjang audio, bukan isinya).
"""
import os
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from faster_whisper import WhisperModel

SR = 16_000
CLIP_SECONDS = 20
N_CLIPS = 6
OUT = "/tmp/clips"


def make_clips():
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(42)
    paths = []
    for i in range(N_CLIPS):
        p = os.path.join(OUT, f"clip{i:02d}.wav")
        if not os.path.exists(p):
            # noise + nada, cukup untuk memaksa encoder+decoder bekerja
            t = np.arange(SR * CLIP_SECONDS) / SR
            sig = 0.02 * rng.standard_normal(t.size) + 0.1 * np.sin(2 * np.pi * 220 * t)
            pcm = (np.clip(sig, -1, 1) * 32767).astype("<i2")
            with wave.open(p, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(pcm.tobytes())
        paths.append(p)
    return paths


def physical_cores():
    try:
        import subprocess
        out = subprocess.run(["lscpu", "-J"], capture_output=True, text=True).stdout
        import json as _j
        d = _j.loads(out)
        def get(k):
            for f in d["lscpu"]:
                if f["field"].startswith(k):
                    return f["data"]
            return None
        cps = int(get("Core(s) per socket") or 0)
        socks = int(get("Socket(s)") or 1)
        tpc = int(get("Thread(s) per core") or 1)
        return cps * socks, tpc
    except Exception:
        return None, None


def load_wav(path):
    """Baca WAV sendiri -> float32, supaya tidak lewat PyAV (rawan beda versi)."""
    with wave.open(path, "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def run_config(clips, workers, cpu_threads):
    model = WhisperModel("small", device="cpu", compute_type="int8",
                         cpu_threads=cpu_threads)

    audio_arrays = [load_wav(p) for p in clips]

    def one(a):
        segs, _ = model.transcribe(a, language="en", beam_size=1)
        return sum(1 for _ in segs)

    t0 = time.perf_counter()
    if workers == 1:
        for a in audio_arrays:
            one(a)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(one, audio_arrays))
    wall = time.perf_counter() - t0
    audio = CLIP_SECONDS * len(clips)
    return wall, audio / wall  # detik dinding, rasio realtime (x)


def main():
    cores, tpc = physical_cores()
    print(f"runner: cpu_phys={cores} threads_per_core={tpc} "
          f"cpu_count={os.cpu_count()} n_clips={N_CLIPS} clip={CLIP_SECONDS}s")

    clips = make_clips()

    t0 = time.perf_counter()
    _ = WhisperModel("small", device="cpu", compute_type="int8")
    load = time.perf_counter() - t0
    print(f"model_load_small_int8 = {load:.2f} s")

    configs = [
        (1, 1),   # 1 proses, 1 thread  -> baseline per core
        (1, 2),   # 1 proses, 2 thread  -> pakai 1 core fisik + SMT
        (2, 1),   # 2 paralel, 1 thread -> 2 core fisik
        (2, 2),   # 2 paralel x 2 thread
        (4, 1),   # 4 paralel (seperti script aslimu, max_workers=4)
        (4, 2),   # 4 paralel x 2 thread -> oversubscribe berat
    ]

    print("\nworkers,cpu_threads,wall_s,realtime_x")
    results = []
    for w, t in configs:
        wall, rt = run_config(clips, w, t)
        results.append((w, t, wall, rt))
        print(f"{w},{t},{wall:.2f},{rt:.2f}")
        with open("/tmp/whisper_results.csv", "a") as f:
            f.write(f"{w},{t},{wall:.2f},{rt:.2f}\n")

    base = results[0][2]
    print("\n== ringkasan (speedup vs 1 worker x 1 thread) ==")
    for w, t, wall, rt in results:
        print(f"workers={w} threads={t}: wall={wall:6.2f}s realtime={rt:5.2f}x speedup={base/wall:4.2f}x")


if __name__ == "__main__":
    main()
