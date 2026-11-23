"""RNG determinista (D6): todo dato generado sale de aqui, nunca de reloj ni uuid4."""
from __future__ import annotations

import hashlib
import random


def derive_seed(seed: int, stream: str) -> int:
    """Semilla estable e independiente por 'stream' (agregar un generador no altera a los demas)."""
    digest = hashlib.sha256(f"{seed}:{stream}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def make_rng(seed: int, stream: str) -> random.Random:
    return random.Random(derive_seed(seed, stream))


def det_uuid(rng: random.Random) -> str:
    """UUID v4 (36 chars, mayusculas) construido solo con el RNG sembrado (sin `uuid`)."""
    n = rng.getrandbits(128)
    n = (n & ~(0xF << 76)) | (4 << 76)        # version 4
    n = (n & ~(0x3 << 62)) | (0x2 << 62)      # variante RFC 4122
    h = f"{n:032X}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def gauss_int(rng: random.Random, spec: dict) -> int:
    """Entero ~ N(mean, sd) recortado a [min, max] (minutos)."""
    return int(round(min(max(rng.gauss(spec["mean"], spec["sd"]), spec["min"]), spec["max"])))
