# backend/tests/test_dhan_provider_feed.py
import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.market_data.dhan_provider import DhanProvider


def _ltp_packet(security_id: int, ltp: float) -> bytes:
    # 8-byte header (code=2, msg_len, exchange_segment, security_id) + 8-byte LTP payload
    header = struct.pack(">BHBI", 2, 16, 1, security_id)
    payload = struct.pack(">fI", ltp, 0)
    return header + payload


@pytest.mark.asyncio
async def test_ltp_packet_publishes_tick(monkeypatch):
    provider = DhanProvider()
    published = []

    async def fake_publish(channel, payload):
        published.append((channel, payload))

    monkeypatch.setattr("backend.app.market_data.dhan_provider.event_bus.publish", fake_publish)

    tick = provider._parse_packet(_ltp_packet(security_id=13, ltp=25010.5))

    assert tick is not None
    assert tick.instrument == "13"
    assert tick.price == pytest.approx(25010.5)


def test_non_ltp_packet_is_ignored():
    provider = DhanProvider()
    non_ltp = struct.pack(">BHBI", 4, 8, 1, 13)  # feed_response_code=4, not LTP
    assert provider._parse_packet(non_ltp) is None
