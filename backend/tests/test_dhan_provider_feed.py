# backend/tests/test_dhan_provider_feed.py
import struct

import pytest

from backend.app.market_data import dhan_provider as dp_module
from backend.app.market_data.dhan_provider import DhanProvider


def _ltp_packet(security_id: int, ltp: float) -> bytes:
    # 8-byte header (code=2, msg_len, exchange_segment, security_id) + 8-byte LTP payload.
    # Dhan's binary feed is little-endian (per DhanHQ v2 docs), so this must
    # match _parse_packet's "<BHBI"/"<fI" unpack format, not big-endian.
    header = struct.pack("<BHBI", 2, 16, 1, security_id)
    payload = struct.pack("<fI", ltp, 0)
    return header + payload


def _non_ltp_packet(code: int, security_id: int) -> bytes:
    # A full 16-byte packet (not just the 8-byte header) so a test using this
    # actually exercises the feed_response_code check in _parse_packet rather
    # than short-circuiting on the earlier length guard.
    header = struct.pack("<BHBI", code, 16, 1, security_id)
    payload = struct.pack("<fI", 0.0, 0)
    return header + payload


@pytest.mark.asyncio
async def test_ltp_packet_publishes_tick(monkeypatch):
    provider = DhanProvider()
    published = []

    async def fake_publish(channel, payload):
        published.append((channel, payload))

    # Patch the attribute on the already-imported module object directly
    # (matching tests/test_active_broker.py's pattern) rather than via a
    # dotted monkeypatch.setattr string. This repo is importable via two
    # module-path roots ("app.*" and "backend.app.*" depending on which test
    # module ran first), and monkeypatch's dotted-string resolver can land on
    # the bare "app.market_data" namespace package — which has no
    # "dhan_provider" attribute — causing a spurious AttributeError that has
    # nothing to do with this test's own logic.
    monkeypatch.setattr(dp_module.event_bus, "publish", fake_publish)

    tick = provider._parse_packet(_ltp_packet(security_id=13, ltp=25010.5))

    assert tick is not None
    assert tick.instrument == "13"
    assert tick.price == pytest.approx(25010.5)

    # _parse_packet itself never touches event_bus (only _read_loop does), so
    # this pins that expectation explicitly rather than leaving fake_publish
    # wired up with nothing asserted about it.
    assert published == []


def test_ltp_packet_wire_format_is_little_endian():
    # Pin the wire format against a literal little-endian byte sequence,
    # independent of _ltp_packet/_parse_packet agreeing with each other by
    # construction — this is what would have caught the endianness bug.
    # code=2, message_length=16, exchange_segment=1, security_id=13 (LE uint32),
    # then last_traded_price=25010.5 (LE float32), last_trade_time=0 (LE uint32).
    raw = (
        b"\x02"          # feed_response_code = 2 (uint8)
        b"\x10\x00"      # message_length = 16 (uint16 LE)
        b"\x01"          # exchange_segment = 1 (uint8)
        b"\x0d\x00\x00\x00"  # security_id = 13 (uint32 LE)
        + struct.pack("<f", 25010.5)  # last_traded_price (float32 LE)
        + b"\x00\x00\x00\x00"  # last_trade_time = 0 (uint32 LE)
    )

    provider = DhanProvider()
    tick = provider._parse_packet(raw)

    assert tick is not None
    assert tick.instrument == "13"
    assert tick.price == pytest.approx(25010.5)


def test_non_ltp_packet_is_ignored():
    provider = DhanProvider()
    # Full 16-byte packet with a non-LTP feed_response_code (4), so this
    # genuinely exercises the `code != LTP_FEED_RESPONSE_CODE` branch instead
    # of returning None via the earlier `len(raw) < 16` length guard.
    non_ltp = _non_ltp_packet(code=4, security_id=13)
    assert len(non_ltp) == 16
    assert provider._parse_packet(non_ltp) is None


def test_short_packet_is_ignored():
    provider = DhanProvider()
    header_only = struct.pack("<BHBI", 4, 8, 1, 13)  # only 8 bytes, below the 16-byte minimum
    assert provider._parse_packet(header_only) is None


def test_parse_frame_splits_multiplexed_packets():
    # Dhan can multiplex multiple packets into one WebSocket binary frame;
    # message_length in each header tells you where the next one starts.
    # This confirms _parse_frame walks past the first packet instead of only
    # ever looking at the first 16 bytes of the frame.
    frame = _ltp_packet(security_id=13, ltp=25010.5) + _ltp_packet(security_id=99, ltp=48000.25)

    provider = DhanProvider()
    ticks = provider._parse_frame(frame)

    assert len(ticks) == 2
    assert ticks[0].instrument == "13"
    assert ticks[0].price == pytest.approx(25010.5)
    assert ticks[1].instrument == "99"
    assert ticks[1].price == pytest.approx(48000.25)
