"""Master Duel's live overframe gate stores raw little-endian art-id pairs."""

import struct


def decode_full_art_entries(data: bytes) -> list[tuple[int, int]]:
    """Read m_Script directly, without treating its first pair as a header."""
    if len(data) % 4:
        raise ValueError("Overframe data is not a complete list of art-id pairs.")
    return list(struct.iter_unpack("<HH", data))


def set_full_art_entry(data: bytes, art_id: int, entry=None) -> bytes:
    """Remove one trigger, or restore its saved pair, preserving other entries."""
    if not 0 < art_id <= 65535:
        raise ValueError("Card texture name must be a positive 16-bit art ID.")
    entries = decode_full_art_entries(data)
    if entry is not None:
        if entry[0] != art_id:
            raise ValueError("Saved overframe entry belongs to another card.")
        if any(trigger == art_id for trigger, _ in entries):
            return data
        return data + struct.pack("<HH", *entry)
    return b"".join(
        struct.pack("<HH", trigger, base)
        for trigger, base in entries
        if trigger != art_id
    )
