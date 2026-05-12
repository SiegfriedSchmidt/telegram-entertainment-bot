import hashlib
import json

EMPTY_HASH = "0" * 64


def compute_hash(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def compute_merkle_root(tx_hashes: list[str]) -> str:
    if len(tx_hashes) == 0:
        return EMPTY_HASH

    level = [bytes.fromhex(h) for h in tx_hashes]

    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])

        next_level = []
        for i in range(0, len(level), 2):
            combined = level[i] + level[i + 1]
            hash1 = hashlib.sha256(combined).digest()
            hash2 = hashlib.sha256(hash1).digest()
            next_level.append(hash2)

        level = next_level

    return level[0].hex()


def check_hash_difficulty(block_hash: str, diff: str) -> bool:
    return block_hash.startswith(diff)
