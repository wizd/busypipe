from __future__ import annotations

import asyncio
import unittest

from busypipe.constants import HEADER_LEN, FrameType
from busypipe.frame import FrameCodec, ProtocolError


class FrameCodecTests(unittest.IsolatedAsyncioTestCase):
    async def test_encode_then_decode(self) -> None:
        codec = FrameCodec()
        encoded = codec.encode(FrameType.DATA, b"hello")

        reader = asyncio.StreamReader()
        reader.feed_data(encoded)
        reader.feed_eof()

        frame = await codec.read_frame(reader)
        self.assertEqual(frame.frame_type, FrameType.DATA)
        self.assertEqual(frame.payload, b"hello")
        self.assertEqual(frame.seq, 0)

    async def test_rejects_bad_magic(self) -> None:
        codec = FrameCodec()
        encoded = bytearray(codec.encode(FrameType.PAD, b"abc"))
        encoded[0] = 0x00

        reader = asyncio.StreamReader()
        reader.feed_data(bytes(encoded))
        reader.feed_eof()

        with self.assertRaises(ProtocolError):
            await codec.read_frame(reader)

    async def test_rejects_bad_header_crc(self) -> None:
        codec = FrameCodec()
        encoded = bytearray(codec.encode(FrameType.PAD, b"abc"))
        encoded[HEADER_LEN - 1] ^= 0xFF

        reader = asyncio.StreamReader()
        reader.feed_data(bytes(encoded))
        reader.feed_eof()

        with self.assertRaises(ProtocolError):
            await codec.read_frame(reader)


if __name__ == "__main__":
    unittest.main()
