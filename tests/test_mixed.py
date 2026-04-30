from __future__ import annotations

import struct
import unittest

from busypipe.mixed import MIXED_METADATA_FORMAT, MixedPayloadBuilder, MixedPayloadError


class MixedPayloadBuilderTests(unittest.TestCase):
    def test_build_then_parse(self) -> None:
        builder = MixedPayloadBuilder(min_jitter_bytes=8)
        payload = builder.build(b"secret", 96)

        self.assertEqual(builder.parse(payload), b"secret")
        self.assertEqual(len(payload), 96)

    def test_offsets_jitter_by_at_least_eight_bytes(self) -> None:
        builder = MixedPayloadBuilder(min_jitter_bytes=8)
        offsets: list[int] = []

        for _ in range(20):
            payload = builder.build(b"data", 80)
            offset, _length, _nonce = struct.unpack(MIXED_METADATA_FORMAT, payload[:8])
            offsets.append(offset)

        for previous, current in zip(offsets, offsets[1:]):
            self.assertGreaterEqual(abs(current - previous), 8)

    def test_rejects_invalid_payload_range(self) -> None:
        builder = MixedPayloadBuilder()
        payload = struct.pack(MIXED_METADATA_FORMAT, 40, 10, b"abcd") + b"x"

        with self.assertRaises(MixedPayloadError):
            builder.parse(payload)


if __name__ == "__main__":
    unittest.main()
