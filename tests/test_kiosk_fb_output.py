import pathlib
import tempfile
import unittest

from _load import load_kiosk

K = load_kiosk()
from PIL import Image  # noqa: E402


class TestFrameToBytes(unittest.TestCase):
    def test_rgb565_red(self):
        img = Image.new("RGB", (1, 1), (255, 0, 0))
        self.assertEqual(K.frame_to_bytes(img, 16), b"\x00\xf8")

    def test_rgb565_green(self):
        img = Image.new("RGB", (1, 1), (0, 255, 0))
        self.assertEqual(K.frame_to_bytes(img, 16), b"\xe0\x07")

    def test_rgb565_blue(self):
        img = Image.new("RGB", (1, 1), (0, 0, 255))
        self.assertEqual(K.frame_to_bytes(img, 16), b"\x1f\x00")

    def test_rgb565_length(self):
        img = Image.new("RGB", (480, 320), (0, 0, 0))
        self.assertEqual(len(K.frame_to_bytes(img, 16)), 480 * 320 * 2)

    def test_bgrx_red(self):
        img = Image.new("RGB", (1, 1), (255, 0, 0))
        self.assertEqual(K.frame_to_bytes(img, 32), b"\x00\x00\xff\x00")


class TestPadRows(unittest.TestCase):
    def test_no_padding_needed(self):
        data = b"\x01" * 8
        self.assertEqual(K.pad_rows(data, 2, 16, 4), data)

    def test_rows_padded_to_stride(self):
        data = b"\x01\x02\x03\x04" + b"\x05\x06\x07\x08"  # 2 righe da 4 byte
        out = K.pad_rows(data, 2, 16, 6)
        self.assertEqual(out, b"\x01\x02\x03\x04\x00\x00"
                              b"\x05\x06\x07\x08\x00\x00")


class TestFramebufferOutput(unittest.TestCase):
    def test_reads_sysfs_and_writes_frame(self):
        with tempfile.TemporaryDirectory() as td:
            sysfs = pathlib.Path(td) / "graphics" / "fb9"
            sysfs.mkdir(parents=True)
            (sysfs / "virtual_size").write_text("4,2\n")
            (sysfs / "bits_per_pixel").write_text("16\n")
            (sysfs / "stride").write_text("8\n")
            fbdev = pathlib.Path(td) / "fb9"
            fbdev.write_bytes(b"")
            out = K.FramebufferOutput(str(fbdev),
                                      sysfs=str(pathlib.Path(td) / "graphics"))
            self.assertEqual((out.size, out.bpp, out.stride), ((4, 2), 16, 8))
            out.write(Image.new("RGB", (4, 2), (255, 0, 0)))
            self.assertEqual(fbdev.read_bytes(), b"\x00\xf8" * 8)


if __name__ == "__main__":
    unittest.main()
