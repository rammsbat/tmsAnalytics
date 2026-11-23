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
