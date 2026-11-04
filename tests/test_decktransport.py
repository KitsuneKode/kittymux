"""Protocol contracts: placements persist, fragments survive, uploads stay bounded."""
import base64
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_decktransport as dt


class ProtocolTests(unittest.TestCase):
    def test_update_preserves_placement_and_does_not_delete_visible_image(self):
        out = io.StringIO()
        show = dt.Graphics(out, transport="direct")
        show.show(bytes(16), 2, 2)
        first = out.getvalue()
        out.seek(0)
        out.truncate()
        show.show(bytes(16), 2, 2)
        self.assertIn("a=T", first)
        self.assertIn("z=-2", first)
        self.assertIn("a=f", out.getvalue())
        self.assertIn("r=1", out.getvalue())
        self.assertNotIn("a=d", out.getvalue())

    def test_resize_recreates_image_with_new_dimensions(self):
        out = io.StringIO()
        show = dt.Graphics(out, transport="direct")
        show.show(bytes(16), 2, 2)
        show.show(bytes(24), 3, 2)
        self.assertEqual(out.getvalue().count("a=T"), 2)
        self.assertIn("s=3,v=2", out.getvalue())

    def test_direct_chunks_reassemble_rgba(self):
        out = io.StringIO()
        show = dt.Graphics(out, transport="direct")
        data = bytes(range(256)) * 64
        show.show(data, 64, 64)
        chunks = out.getvalue().split("\x1b_G")[1:]
        payloads = [c.split(";", 1)[1].split("\x1b\\")[0] for c in chunks]
        self.assertTrue(all(len(p) <= 4096 for p in payloads))
        self.assertEqual(base64.b64decode("".join(payloads)), data)
        self.assertIn("m=0", chunks[-1])

    def test_invalid_dimensions_never_upload(self):
        for w, h, n in ((0, 1, 0), (10001, 1, 40004), (2, 2, 3)):
            out = io.StringIO()
            with self.assertRaises(ValueError):
                dt.Graphics(out, transport="direct").show(bytes(n), w, h)
            self.assertEqual(out.getvalue(), "")

    def test_animation_is_small_and_terminal_driven(self):
        out = io.StringIO()
        show = dt.Graphics(out, transport="direct")
        show.spinner([bytes(16), bytes(16)], 2, [(20, 32)], (10, 16), 50)
        data = out.getvalue()
        self.assertIn("a=f", data)
        self.assertIn("a=a", data)
        self.assertIn("s=3,v=1", data)
        self.assertIn("a=p", data)
        self.assertIn("z=-1", data)

    def test_a_placed_frame_names_its_cell_and_its_z(self):
        out = io.StringIO()
        dt.Graphics(out, transport="direct").show(bytes(16), 2, 2, col=1, row=2, z=1)
        text = out.getvalue()
        self.assertIn("\x1b[2;1H", text)
        self.assertIn("z=1", text)
        self.assertIn("a=T", text)


class InputTests(unittest.TestCase):
    def test_every_mouse_split_and_coalesced_key(self):
        report = b"\x1b[<0;72;442M"
        for split in range(1, len(report)):
            parser = dt.Input()
            self.assertEqual(parser.feed(report[:split]), [])
            self.assertEqual(parser.feed(report[split:] + b"q"),
                             [("mouse", 0, 72, 442, b"M"), ("key", b"q")])

    def test_graphics_response_is_not_an_escape_key(self):
        parser = dt.Input()
        self.assertEqual(parser.feed(b"\x1b_Gi=1;OK\x1b\\"), [("graphics", b"i=1;OK")])

    def test_unterminated_input_is_bounded(self):
        parser = dt.Input()
        parser.feed(b"\x1b_G" + b"x" * 10000)
        self.assertLessEqual(len(parser.pending), 4096)


if __name__ == "__main__":
    unittest.main()
