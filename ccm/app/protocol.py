"""Foodi BLE wire protocol v1 (see docs/ble-protocol.md). Pure functions, no I/O."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum

VERSION = 1
HEADER = struct.Struct("<BBH")  # version, msg_type, seq
SCHEDULE_ENTRY = struct.Struct("<HHB")  # minute_of_day, grams, days_mask


class MsgType(IntEnum):
    CMD_DISPENSE = 0x01
    CMD_CANCEL = 0x02
    CMD_TARE = 0x03
    CMD_SET_SCHEDULE = 0x04
    CMD_SYNC_TIME = 0x05
    EVT_ACK = 0x81
    EVT_NACK = 0x82
    EVT_DISPENSED = 0x83
    EVT_TELEMETRY = 0x84


class ErrorCode(IntEnum):
    BAD_VERSION = 1
    BAD_PAYLOAD = 2
    BUSY = 3
    EMPTY_HOPPER = 4
    OVER_LIMIT = 5
    JAM = 6


class FeederState(IntEnum):
    IDLE = 0
    DISPENSING = 1
    ERROR = 2
    LOW_FOOD = 3


@dataclass
class Message:
    type: MsgType
    seq: int
    payload: dict = field(default_factory=dict)


def _pack(msg_type: MsgType, seq: int, body: bytes = b"") -> bytes:
    return HEADER.pack(VERSION, int(msg_type), seq & 0xFFFF) + body


# ---- encoders: CCM -> feeder ------------------------------------------------
def encode_dispense(seq: int, cmd_id: int, grams: int) -> bytes:
    return _pack(MsgType.CMD_DISPENSE, seq, struct.pack("<IH", cmd_id, grams))


def encode_cancel(seq: int, cmd_id: int) -> bytes:
    return _pack(MsgType.CMD_CANCEL, seq, struct.pack("<I", cmd_id))


def encode_tare(seq: int) -> bytes:
    return _pack(MsgType.CMD_TARE, seq)


def encode_sync_time(seq: int, unix_ts: int, tz_offset_min: int) -> bytes:
    return _pack(MsgType.CMD_SYNC_TIME, seq, struct.pack("<Ih", unix_ts, tz_offset_min))


def encode_set_schedule(seq: int, entries: list[tuple[int, int, int]]) -> bytes:
    body = struct.pack("<B", len(entries)) + b"".join(SCHEDULE_ENTRY.pack(*e) for e in entries)
    return _pack(MsgType.CMD_SET_SCHEDULE, seq, body)


# ---- encoders: feeder -> CCM (used by the simulator and tests) ---------------
def encode_ack(seq: int, cmd_id: int = 0) -> bytes:
    return _pack(MsgType.EVT_ACK, seq, struct.pack("<I", cmd_id))


def encode_nack(seq: int, cmd_id: int, error: ErrorCode) -> bytes:
    return _pack(MsgType.EVT_NACK, seq, struct.pack("<IB", cmd_id, int(error)))


def encode_dispensed(seq: int, cmd_id: int, target_g: int, actual_g: int) -> bytes:
    return _pack(MsgType.EVT_DISPENSED, seq, struct.pack("<IHH", cmd_id, target_g, actual_g))


def encode_telemetry(seq: int, weight_g: int, food_level_pct: int, state: FeederState) -> bytes:
    return _pack(MsgType.EVT_TELEMETRY, seq, struct.pack("<iBB", weight_g, food_level_pct, int(state)))


# ---- decoder ----------------------------------------------------------------
def decode(data: bytes) -> Message:
    if len(data) < HEADER.size:
        raise ValueError("packet too short")
    version, raw_type, seq = HEADER.unpack_from(data)
    if version != VERSION:
        raise ValueError(f"unsupported protocol version {version}")
    body = data[HEADER.size:]
    t = MsgType(raw_type)
    try:
        if t == MsgType.CMD_DISPENSE:
            cmd_id, grams = struct.unpack("<IH", body)
            p = {"cmd_id": cmd_id, "grams": grams}
        elif t == MsgType.CMD_CANCEL:
            (cmd_id,) = struct.unpack("<I", body)
            p = {"cmd_id": cmd_id}
        elif t == MsgType.CMD_TARE:
            p = {}
        elif t == MsgType.CMD_SYNC_TIME:
            ts, tz = struct.unpack("<Ih", body)
            p = {"unix_ts": ts, "tz_offset_min": tz}
        elif t == MsgType.CMD_SET_SCHEDULE:
            (count,) = struct.unpack_from("<B", body)
            entries = [SCHEDULE_ENTRY.unpack_from(body, 1 + i * SCHEDULE_ENTRY.size) for i in range(count)]
            p = {"entries": entries}
        elif t == MsgType.EVT_ACK:
            (cmd_id,) = struct.unpack("<I", body)
            p = {"cmd_id": cmd_id}
        elif t == MsgType.EVT_NACK:
            cmd_id, code = struct.unpack("<IB", body)
            p = {"cmd_id": cmd_id, "error": ErrorCode(code)}
        elif t == MsgType.EVT_DISPENSED:
            cmd_id, target, actual = struct.unpack("<IHH", body)
            p = {"cmd_id": cmd_id, "target_g": target, "actual_g": actual}
        elif t == MsgType.EVT_TELEMETRY:
            weight, level, state = struct.unpack("<iBB", body)
            p = {"weight_g": weight, "food_level_pct": level, "state": FeederState(state)}
        else:  # pragma: no cover
            raise ValueError("unknown type")
    except struct.error as exc:
        raise ValueError(f"bad payload for {t.name}") from exc
    return Message(t, seq, p)
