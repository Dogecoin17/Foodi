import pytest

from app import protocol as P


def test_dispense_roundtrip():
    m = P.decode(P.encode_dispense(7, 123456, 40))
    assert m.type == P.MsgType.CMD_DISPENSE and m.seq == 7
    assert m.payload == {"cmd_id": 123456, "grams": 40}


def test_schedule_roundtrip():
    entries = [(480, 40, 127), (1080, 35, 31)]
    m = P.decode(P.encode_set_schedule(1, entries))
    assert m.payload["entries"] == entries


def test_telemetry_roundtrip():
    m = P.decode(P.encode_telemetry(3, -12, 80, P.FeederState.IDLE))
    assert m.payload == {"weight_g": -12, "food_level_pct": 80, "state": P.FeederState.IDLE}


def test_nack_and_dispensed():
    assert P.decode(P.encode_nack(1, 9, P.ErrorCode.JAM)).payload["error"] == P.ErrorCode.JAM
    assert P.decode(P.encode_dispensed(1, 9, 40, 38)).payload["actual_g"] == 38


def test_sync_time_negative_tz():
    assert P.decode(P.encode_sync_time(1, 1_700_000_000, -300)).payload["tz_offset_min"] == -300


def test_rejects_bad_version_and_short_packets():
    with pytest.raises(ValueError):
        P.decode(b"\x09\x01\x00\x00")
    with pytest.raises(ValueError):
        P.decode(b"\x01")
    with pytest.raises(ValueError):
        P.decode(b"\x01\x01\x00\x00\x01")  # truncated dispense payload


def test_seq_wraps_to_u16():
    assert P.decode(P.encode_tare(0x10001)).seq == 1
