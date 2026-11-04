#!/usr/bin/env python3
"""Benchmark CPU portabel — jalan di Termux/Pydroid (tablet) maupun di GitHub Actions.

Pakai:
    python3 bench/cpu_bench.py            # 1 core
    python3 bench/cpu_bench.py 4          # 4 core paralel

Tanpa dependency eksternal, supaya hasilnya apple-to-apple antara Mi Pad 6
dan runner GitHub.
"""
import os
import sys
import time
from multiprocessing import Process, Queue

SIEVE_LIMIT = 30_000_000
SHA_ROUNDS = 200_000


def sieve(limit):
    """Sieve of Eratosthenes — kerja integer murni, bergantung ke clock/IPC."""
    flags = bytearray([1]) * (limit + 1)
    flags[0] = flags[1] = 0
    i = 2
    while i * i <= limit:
        if flags[i]:
            flags[i * i::i] = bytearray(len(range(i * i, limit + 1, i)))
        i += 1
    return sum(flags)


def sha_loop(rounds=SHA_ROUNDS):
    """Rantai SHA-256 — kerja dependen serial, murni latensi clock."""
    import hashlib
    h = b"yoyoi"
    for _ in range(rounds):
        h = hashlib.sha256(h).digest()
    return h[0]


def worker(q, core_id):
    t0 = time.perf_counter()
    primes = sieve(SIEVE_LIMIT)
    t_sieve = time.perf_counter() - t0

    t0 = time.perf_counter()
    sha_loop()
    t_sha = time.perf_counter() - t0

    q.put((core_id, t_sieve, t_sha, primes))


def run(workers):
    q = Queue()
    t0 = time.perf_counter()
    procs = [Process(target=worker, args=(q, i)) for i in range(workers)]
    for p in procs:
        p.start()
    res = [q.get() for _ in procs]
    for p in procs:
        p.join()
    wall = time.perf_counter() - t0

    primes = res[0][3] * workers          # tiap worker menyelesaikan sieve penuh
    hashes = SHA_ROUNDS * workers
    return {
        "workers": workers,
        "wall": wall,
        "sieve_per_core": sum(r[1] for r in res) / workers,
        "sha_per_core": sum(r[2] for r in res) / workers,
        "prime_throughput": primes / wall,   # bilangan prima / detik dinding
        "hash_throughput": hashes / wall,    # hash / detik dinding
    }


def main():
    try:
        workers = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    except ValueError:
        workers = 1

    print(f"cores_dipakai={workers}  cpu_count_terdeteksi={os.cpu_count()}")

    best = None
    for _ in range(2):                       # best-of-2 supaya noise turun
        r = run(workers)
        if best is None or r["wall"] < best["wall"]:
            best = r

    print(f"  sieve {SIEVE_LIMIT/1e6:.0f}jt per core = {best['sieve_per_core']:.3f} s")
    print(f"  sha256 {SHA_ROUNDS//1000}k per core   = {best['sha_per_core']:.3f} s")
    print(f"  wall clock total          = {best['wall']:.3f} s")
    print(f"  SKOR_SIEVE = {best['prime_throughput']/1e6:.2f} juta-prima/detik-wall")
    print(f"  SKOR_SHA   = {best['hash_throughput']/1e3:.1f} ribu-hash/detik-wall")


if __name__ == "__main__":
    main()
