"""Bounded, transport-neutral framing for public local pairing messages."""

import struct
import zlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Never

LOCAL_PAIRING_FRAME_VERSION = 1
MAXIMUM_LOCAL_PAIRING_PAYLOAD_BYTES = 1024
LOCAL_PAIRING_FRAME_HEADER_BYTES = 20
MAXIMUM_LOCAL_PAIRING_FRAME_BYTES = (
    LOCAL_PAIRING_FRAME_HEADER_BYTES + MAXIMUM_LOCAL_PAIRING_PAYLOAD_BYTES
)

_MAGIC = b"TSLP"
_HEADER_WITHOUT_CRC = struct.Struct(">4sBBHIHH")
_HEADER = struct.Struct(">4sBBHIHHI")


class LocalPairingFrameRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class LocalPairingFrameType(IntEnum):
    HELLO = 1
    CANCEL = 2


@dataclass(frozen=True, slots=True)
class LocalPairingFrame:
    frame_type: LocalPairingFrameType
    sequence: int
    payload: bytes = field(repr=False)


def encode_local_pairing_frame(frame: LocalPairingFrame) -> bytes:
    _validate_frame(frame)
    header_without_crc = _HEADER_WITHOUT_CRC.pack(
        _MAGIC,
        LOCAL_PAIRING_FRAME_VERSION,
        frame.frame_type.value,
        0,
        frame.sequence,
        len(frame.payload),
        0,
    )
    checksum = zlib.crc32(frame.payload, zlib.crc32(header_without_crc))
    return header_without_crc + struct.pack(">I", checksum & 0xFFFFFFFF) + frame.payload


def decode_local_pairing_frame(encoded: bytes) -> LocalPairingFrame:
    if not isinstance(encoded, bytes):
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_BYTES_REQUIRED")
    header = _decode_header(encoded)
    expected_length = LOCAL_PAIRING_FRAME_HEADER_BYTES + header.payload_length
    if len(encoded) != expected_length:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_LENGTH_MISMATCH")

    payload = encoded[LOCAL_PAIRING_FRAME_HEADER_BYTES:]
    frame = LocalPairingFrame(
        frame_type=header.frame_type,
        sequence=header.sequence,
        payload=payload,
    )
    _validate_frame(frame)

    expected_checksum = zlib.crc32(
        payload,
        zlib.crc32(encoded[: LOCAL_PAIRING_FRAME_HEADER_BYTES - 4]),
    )
    if header.checksum != expected_checksum & 0xFFFFFFFF:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_CHECKSUM_INVALID")
    return frame


@dataclass(frozen=True, slots=True)
class _DecodedHeader:
    frame_type: LocalPairingFrameType
    sequence: int
    payload_length: int
    checksum: int


def _decode_header(encoded: bytes | bytearray) -> _DecodedHeader:
    if len(encoded) < LOCAL_PAIRING_FRAME_HEADER_BYTES:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_HEADER_INCOMPLETE")
    (
        magic,
        version,
        frame_type_value,
        flags,
        sequence,
        payload_length,
        reserved,
        checksum,
    ) = _HEADER.unpack_from(encoded)
    if magic != _MAGIC:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_MAGIC_INVALID")
    if version != LOCAL_PAIRING_FRAME_VERSION:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_VERSION_UNSUPPORTED")
    try:
        frame_type = LocalPairingFrameType(frame_type_value)
    except ValueError as error:
        raise LocalPairingFrameRejectedError(
            "PAIRING_FRAME_TYPE_UNSUPPORTED"
        ) from error
    if flags != 0:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_FLAGS_INVALID")
    if sequence == 0:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_SEQUENCE_INVALID")
    if reserved != 0:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_RESERVED_INVALID")
    if payload_length > MAXIMUM_LOCAL_PAIRING_PAYLOAD_BYTES:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_PAYLOAD_TOO_LARGE")
    return _DecodedHeader(
        frame_type=frame_type,
        sequence=sequence,
        payload_length=payload_length,
        checksum=checksum,
    )


def _validate_frame(frame: LocalPairingFrame) -> None:
    if not isinstance(frame, LocalPairingFrame):
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_REQUIRED")
    if not isinstance(frame.frame_type, LocalPairingFrameType):
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_TYPE_UNSUPPORTED")
    if (
        isinstance(frame.sequence, bool)
        or not isinstance(frame.sequence, int)
        or not 1 <= frame.sequence <= 0xFFFFFFFF
    ):
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_SEQUENCE_INVALID")
    if not isinstance(frame.payload, bytes):
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_PAYLOAD_BYTES_REQUIRED")
    if len(frame.payload) > MAXIMUM_LOCAL_PAIRING_PAYLOAD_BYTES:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_PAYLOAD_TOO_LARGE")
    if frame.frame_type is LocalPairingFrameType.HELLO and not frame.payload:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_HELLO_EMPTY")
    if frame.frame_type is LocalPairingFrameType.CANCEL and frame.payload:
        raise LocalPairingFrameRejectedError("PAIRING_FRAME_CANCEL_PAYLOAD_INVALID")


class LocalPairingFrameDecoder:
    """Single-frame incremental decoder with a fixed maximum buffer."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._complete = False
        self._terminal_reason: str | None = None

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: object) -> LocalPairingFrame | None:
        if self._terminal_reason is not None:
            raise LocalPairingFrameRejectedError(self._terminal_reason)
        if self._complete:
            raise LocalPairingFrameRejectedError("PAIRING_FRAME_ALREADY_COMPLETE")
        if not isinstance(chunk, bytes):
            return self._reject("PAIRING_FRAME_BYTES_REQUIRED")
        if len(self._buffer) + len(chunk) > MAXIMUM_LOCAL_PAIRING_FRAME_BYTES:
            return self._reject("PAIRING_FRAME_BUFFER_OVERFLOW")

        self._buffer.extend(chunk)
        if len(self._buffer) < LOCAL_PAIRING_FRAME_HEADER_BYTES:
            return None

        try:
            header = _decode_header(self._buffer)
        except LocalPairingFrameRejectedError as error:
            return self._reject(error.reason_code)
        expected_length = LOCAL_PAIRING_FRAME_HEADER_BYTES + header.payload_length
        if len(self._buffer) < expected_length:
            return None
        if len(self._buffer) > expected_length:
            return self._reject("PAIRING_FRAME_LENGTH_MISMATCH")

        try:
            frame = decode_local_pairing_frame(bytes(self._buffer))
        except LocalPairingFrameRejectedError as error:
            return self._reject(error.reason_code)
        self._clear_buffer()
        self._complete = True
        return frame

    def cancel(self) -> None:
        if self._terminal_reason is None and not self._complete:
            self._terminal_reason = "PAIRING_FRAME_CANCELLED"
        self._clear_buffer()

    def _reject(self, reason_code: str) -> Never:
        self._terminal_reason = reason_code
        self._clear_buffer()
        raise LocalPairingFrameRejectedError(reason_code)

    def _clear_buffer(self) -> None:
        self._buffer[:] = b"\x00" * len(self._buffer)
        self._buffer.clear()
