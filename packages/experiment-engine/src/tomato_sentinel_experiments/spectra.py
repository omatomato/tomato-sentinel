"""Deterministic, fixture-only signal-channel simulation.

This module models bits and synthetic samples in memory. It has no transport,
audio, radio, GPIO, filesystem or network adapter.
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import gcd
from zlib import crc32

_PREAMBLE = 0xDDAA
_PREAMBLE_BITS = 16
_LENGTH_BITS = 32
_CRC_BITS = 32
_MAX_PAYLOAD_BITS = 65_536
_ENCODINGS = frozenset({"ask", "fsk", "manchester", "pwm"})
_ERROR_CORRECTIONS = frozenset({"none", "hamming84"})
_CHANNELS = frozenset({"acoustic_fixture", "optical_fixture"})
_SYMBOLS: dict[str, dict[int, tuple[int, ...]]] = {
    "ask": {0: (0,), 1: (1,)},
    "manchester": {0: (0, 1), 1: (1, 0)},
    "fsk": {0: (0, 0, 1, 1), 1: (0, 1, 0, 1)},
    "pwm": {0: (1, 0, 0, 0), 1: (1, 1, 1, 0)},
}


@dataclass(frozen=True, slots=True)
class SpectraSimulationResult:
    execution_mode: str
    channel: str
    encoding: str
    error_correction: str
    sample_count: int
    encoded_bit_count: int
    transmitted_sample_count: int
    injected_sample_errors: int
    channel_bit_errors: int
    channel_ber: float
    corrected_errors: int
    uncorrectable_blocks: int
    bit_errors: int
    ber: float
    frame_sync_ok: bool
    checksum_ok: bool

    def as_mapping(self) -> dict[str, object]:
        return asdict(self)


def simulate_spectra_channel(
    *,
    channel: str,
    encoding: str,
    error_correction: str,
    sample_count: int,
    noise_percent: int,
    seed: str,
) -> SpectraSimulationResult:
    """Run one bounded and reproducible synthetic channel experiment."""
    _validate_inputs(
        channel=channel,
        encoding=encoding,
        error_correction=error_correction,
        sample_count=sample_count,
        noise_percent=noise_percent,
        seed=seed,
    )
    payload = _fixture_bits(sample_count, seed)
    checksum = _payload_crc(payload)
    frame = (
        _int_to_bits(_PREAMBLE, _PREAMBLE_BITS)
        + _int_to_bits(sample_count, _LENGTH_BITS)
        + payload
        + _int_to_bits(checksum, _CRC_BITS)
    )
    encoded, padding = _apply_error_correction(frame, error_correction)
    transmitted = _modulate(encoded, encoding)
    received, injected_errors = _inject_noise(
        transmitted,
        noise_percent=noise_percent,
        seed=seed,
        channel=channel,
    )
    demodulated = _demodulate(received, encoding)
    channel_bit_errors = _bit_errors(encoded, demodulated)
    decoded, corrected, uncorrectable = _remove_error_correction(
        demodulated,
        error_correction,
        padding,
    )

    payload_start = _PREAMBLE_BITS + _LENGTH_BITS
    payload_end = payload_start + sample_count
    crc_end = payload_end + _CRC_BITS
    recovered_payload = decoded[payload_start:payload_end]
    recovered_crc = _bits_to_int(decoded[payload_end:crc_end])
    frame_sync_ok = decoded[:_PREAMBLE_BITS] == _int_to_bits(
        _PREAMBLE, _PREAMBLE_BITS
    ) and decoded[_PREAMBLE_BITS:payload_start] == _int_to_bits(
        sample_count, _LENGTH_BITS
    )
    payload_errors = _bit_errors(payload, recovered_payload)
    checksum_ok = (
        frame_sync_ok
        and len(decoded) >= crc_end
        and recovered_crc == _payload_crc(recovered_payload)
    )
    return SpectraSimulationResult(
        execution_mode="simulation",
        channel=channel,
        encoding=encoding,
        error_correction=error_correction,
        sample_count=sample_count,
        encoded_bit_count=len(encoded),
        transmitted_sample_count=len(transmitted),
        injected_sample_errors=injected_errors,
        channel_bit_errors=channel_bit_errors,
        channel_ber=channel_bit_errors / len(encoded),
        corrected_errors=corrected,
        uncorrectable_blocks=uncorrectable,
        bit_errors=payload_errors,
        ber=payload_errors / sample_count,
        frame_sync_ok=frame_sync_ok,
        checksum_ok=checksum_ok,
    )


def _validate_inputs(
    *,
    channel: str,
    encoding: str,
    error_correction: str,
    sample_count: int,
    noise_percent: int,
    seed: str,
) -> None:
    if channel not in _CHANNELS:
        raise ValueError("unsupported synthetic channel")
    if encoding not in _ENCODINGS:
        raise ValueError("unsupported encoding")
    if error_correction not in _ERROR_CORRECTIONS:
        raise ValueError("unsupported error correction")
    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or not 8 <= sample_count <= _MAX_PAYLOAD_BITS
    ):
        raise ValueError("sample_count outside bounds")
    if (
        isinstance(noise_percent, bool)
        or not isinstance(noise_percent, int)
        or not 0 <= noise_percent <= 50
    ):
        raise ValueError("noise_percent outside bounds")
    if not isinstance(seed, str) or not seed or len(seed) > 256:
        raise ValueError("invalid simulation seed")


def _fixture_bits(bit_count: int, seed: str) -> tuple[int, ...]:
    bits: list[int] = []
    counter = 0
    while len(bits) < bit_count:
        digest = sha256(f"{seed}:payload:{counter}".encode()).digest()
        for byte in digest:
            bits.extend((byte >> shift) & 1 for shift in range(7, -1, -1))
        counter += 1
    return tuple(bits[:bit_count])


def _payload_crc(bits: tuple[int, ...]) -> int:
    length = len(bits).to_bytes(4, "big")
    return crc32(length + _pack_bits(bits)) & 0xFFFFFFFF


def _pack_bits(bits: tuple[int, ...]) -> bytes:
    output = bytearray((len(bits) + 7) // 8)
    for index, bit in enumerate(bits):
        output[index // 8] |= bit << (7 - index % 8)
    return bytes(output)


def _int_to_bits(value: int, width: int) -> tuple[int, ...]:
    return tuple((value >> shift) & 1 for shift in range(width - 1, -1, -1))


def _bits_to_int(bits: tuple[int, ...]) -> int:
    value = 0
    for bit in bits:
        value = value << 1 | bit
    return value


def _apply_error_correction(
    bits: tuple[int, ...],
    error_correction: str,
) -> tuple[tuple[int, ...], int]:
    if error_correction == "none":
        return bits, 0
    padding = (-len(bits)) % 4
    padded = bits + (0,) * padding
    encoded: list[int] = []
    for offset in range(0, len(padded), 4):
        d1, d2, d3, d4 = padded[offset : offset + 4]
        p1 = d1 ^ d2 ^ d4
        p2 = d1 ^ d3 ^ d4
        p4 = d2 ^ d3 ^ d4
        first_seven = (p1, p2, d1, p4, d2, d3, d4)
        p8 = 0
        for bit in first_seven:
            p8 ^= bit
        encoded.extend((*first_seven, p8))
    return tuple(encoded), padding


def _remove_error_correction(
    bits: tuple[int, ...],
    error_correction: str,
    padding: int,
) -> tuple[tuple[int, ...], int, int]:
    if error_correction == "none":
        return bits, 0, 0
    if len(bits) % 8:
        raise ValueError("invalid hamming84 block length")
    decoded: list[int] = []
    corrected = 0
    uncorrectable = 0
    for offset in range(0, len(bits), 8):
        block = list(bits[offset : offset + 8])
        syndrome = (
            (block[0] ^ block[2] ^ block[4] ^ block[6])
            | ((block[1] ^ block[2] ^ block[5] ^ block[6]) << 1)
            | ((block[3] ^ block[4] ^ block[5] ^ block[6]) << 2)
        )
        overall_parity = 0
        for bit in block:
            overall_parity ^= bit
        if syndrome and overall_parity:
            block[syndrome - 1] ^= 1
            corrected += 1
        elif not syndrome and overall_parity:
            block[7] ^= 1
            corrected += 1
        elif syndrome and not overall_parity:
            uncorrectable += 1
        decoded.extend((block[2], block[4], block[5], block[6]))
    if padding:
        del decoded[-padding:]
    return tuple(decoded), corrected, uncorrectable


def _modulate(bits: tuple[int, ...], encoding: str) -> tuple[int, ...]:
    symbols = _SYMBOLS[encoding]
    output: list[int] = []
    for bit in bits:
        output.extend(symbols[bit])
    return tuple(output)


def _demodulate(samples: tuple[int, ...], encoding: str) -> tuple[int, ...]:
    zero, one = _SYMBOLS[encoding].values()
    symbol_size = len(zero)
    if len(samples) % symbol_size:
        raise ValueError("invalid modulated sample length")
    output: list[int] = []
    for offset in range(0, len(samples), symbol_size):
        symbol = samples[offset : offset + symbol_size]
        zero_distance = _bit_errors(zero, symbol)
        one_distance = _bit_errors(one, symbol)
        output.append(1 if one_distance < zero_distance else 0)
    return tuple(output)


def _inject_noise(
    samples: tuple[int, ...],
    *,
    noise_percent: int,
    seed: str,
    channel: str,
) -> tuple[tuple[int, ...], int]:
    error_count = len(samples) * noise_percent // 100
    if error_count == 0:
        return samples, 0
    digest = sha256(f"{seed}:{channel}:noise".encode()).digest()
    offset = int.from_bytes(digest[:8], "big") % len(samples)
    step = int.from_bytes(digest[8:16], "big") % len(samples) or 1
    while gcd(step, len(samples)) != 1:
        step += 1
        if step == len(samples):
            step = 1
    if channel == "acoustic_fixture":
        step = _next_coprime(step * 3, len(samples))
    positions = {(offset + index * step) % len(samples) for index in range(error_count)}
    output = list(samples)
    for position in positions:
        output[position] ^= 1
    return tuple(output), len(positions)


def _next_coprime(candidate: int, modulus: int) -> int:
    candidate %= modulus
    candidate = candidate or 1
    while gcd(candidate, modulus) != 1:
        candidate += 1
        if candidate == modulus:
            candidate = 1
    return candidate


def _bit_errors(expected: tuple[int, ...], actual: tuple[int, ...]) -> int:
    shared = sum(left != right for left, right in zip(expected, actual, strict=False))
    return shared + abs(len(expected) - len(actual))
