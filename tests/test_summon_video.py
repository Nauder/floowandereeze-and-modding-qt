"""Real MP4 decoding, timing, framing and bounded-input regressions."""

from fractions import Fraction
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import av
from PIL import Image

from unity.summon_frames import (
    FrameOptions,
    ImportMemoryWarning,
    decode_frames,
    sample_frames,
)


class VideoTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "animation.MP4"

    def encode(self, timestamps=(0, 100, 300)):
        with av.open(str(self.path), "w") as container:
            stream = container.add_stream("libx264", rate=10)
            stream.width, stream.height = 32, 16
            stream.pix_fmt = "yuv420p"
            stream.time_base = Fraction(1, 1000)
            stream.codec_context.time_base = Fraction(1, 1000)
            for index, timestamp in enumerate(timestamps):
                with Image.new(
                    "RGB", (32, 16), ("red", "green", "blue")[index % 3]
                ) as image:
                    frame = av.VideoFrame.from_image(image)
                frame.pts, frame.time_base = timestamp, Fraction(1, 1000)
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    def test_real_mp4_variable_timing_fit_crop_and_sampling(self):
        self.encode()
        options = FrameOptions(edge=32, png_fps=1)
        frames, delays = decode_frames(self.path, options, 1)
        self.assertEqual(len(frames), 3)
        self.assertAlmostEqual(delays[0], 0.1)
        self.assertAlmostEqual(delays[1], 0.2)
        self.assertAlmostEqual(delays[2], 0.1)
        self.assertEqual(frames[0].size, (32, 32))
        self.assertEqual(frames[0].getpixel((0, 0))[3], 0)
        self.assertEqual(frames[0].getpixel((16, 16))[3], 255)
        self.assertGreater(frames[0].getpixel((16, 16))[0], 240)
        self.assertGreater(frames[2].getpixel((16, 16))[2], 240)
        cropped, _ = decode_frames(
            self.path, FrameOptions(edge=32, framing="crop"), 1
        )
        self.assertEqual(cropped[0].getpixel((0, 0))[3], 255)
        _, indices, _ = sample_frames(
            frames, delays, 0.6, FrameOptions(fps=10, timing="source")
        )
        self.assertEqual(indices, [0, 1, 1, 2, 2, 2])

    def test_corrupt_mp4_is_actionable(self):
        self.path.write_bytes(b"invalid video")
        with self.assertRaisesRegex(ValueError, "Could not decode MP4"):
            decode_frames(self.path, FrameOptions(), 1)

    def test_real_video_over_old_frame_limit(self):
        self.encode(tuple(range(0, 60100, 100)))
        frames, delays = decode_frames(self.path, FrameOptions(edge=32), 1)
        self.assertEqual(len(frames), 601)
        self.assertEqual(len(delays), 601)

    def test_mp4_service_preview_apply_and_restore(self):
        from test_summon_frames import GraphFixture

        self.encode()
        fixture = GraphFixture(str(self.path.parent / "game"))
        service = fixture.service
        before = {path: path.read_bytes() for path in fixture.originals}
        plan = service.prepare_frame_animation(
            fixture.rows, self.path, FrameOptions(edge=32, fps=10)
        )
        self.assertAlmostEqual(plan["source_duration"], 0.4)
        self.assertTrue(plan["preview"])
        result = service.apply_frame_animation(plan)
        self.assertTrue(result["modified"])
        service.restore_component_set(manifests=result["manifests"])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def fake_container(self, frames):
        self.path.write_bytes(b"placeholder")
        container = Mock()
        container.streams.video = [
            SimpleNamespace(
                average_rate=30,
                frames=100,
                duration=100,
                time_base=Fraction(1, 30),
                codec_context=SimpleNamespace(width=1920, height=1080),
            )
        ]
        container.decode.return_value = iter(frames)
        container.__enter__ = Mock(return_value=container)
        container.__exit__ = Mock(return_value=False)
        return container

    def test_missing_or_empty_video_stream(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                container = self.fake_container([])
                if missing:
                    container.streams.video = []
                with patch("av.open", return_value=container):
                    with self.assertRaisesRegex(ValueError, "no .*video"):
                        decode_frames(self.path, FrameOptions(), 1)

    def video_frame(self, index):
        frame = Mock(width=1920, height=1080)
        frame.time = index / 30
        frame.duration, frame.time_base = 1, Fraction(1, 30)
        frame.to_image.return_value = Image.new("RGB", (1, 1))
        return frame

    def test_cumulative_source_pixels_are_not_a_memory_limit(self):
        container = self.fake_container([self.video_frame(i) for i in range(100)])
        # 100 HD frames exceed the old cumulative 512 MiB allowance.
        with patch("av.open", return_value=container):
            frames, _ = decode_frames(self.path, FrameOptions(edge=32), 1)
        self.assertEqual(len(frames), 100)

    def test_large_import_requires_approval_before_decode(self):
        for unknown in (False, True):
            with self.subTest(unknown=unknown):
                container = self.fake_container([self.video_frame(0)])
                stream = container.streams.video[0]
                if unknown:
                    stream.frames, stream.duration = 0, None
                else:
                    stream.codec_context.width = 8192
                    stream.codec_context.height = 8192
                with patch("av.open", return_value=container):
                    with self.assertRaises(ImportMemoryWarning):
                        decode_frames(self.path, FrameOptions(edge=32), 1)
                    container.decode.assert_not_called()
                    frames, _ = decode_frames(
                        self.path, FrameOptions(edge=32), 1, allow_large_import=True
                    )
                self.assertEqual(len(frames), 1)


if __name__ == "__main__":
    unittest.main()
