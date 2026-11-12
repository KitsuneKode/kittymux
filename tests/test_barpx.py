import io
import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
try:
    import kittymux_barpx as B  # noqa: E402
    import kittymux_groups as G  # noqa: E402
    import kittymux_theme as th  # noqa: E402
except (ImportError, ValueError) as e:      # cairo / pango / rsvg missing: the renderer is optional
    B = None
    _why = str(e)

PAL = None


def pal():
    global PAL
    if PAL is None:
        c = {"background": 0x1F1F28, "foreground": 0xDCD7BA}
        for i, v in enumerate([0x16161D, 0xC34043, 0x76946A, 0xC0A36E, 0x7E9CD8, 0x957FB8, 0x6A9589, 0xC8C093,
                               0x727169, 0xE82424, 0x98BB6C, 0xE6C384, 0x7FB4CA, 0x938AA9, 0x7AA89F, 0xDCD7BA]):
            c[f"color{i}"] = v
        PAL = th.from_colors(c)
    return PAL


def decode_png(data: bytes):
    """(width, height, rows of (r, g, b, a)) for the 8-bit RGBA PNGs cairo writes; no PIL needed."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h, bpp = 8, b"", 0, 0, 4
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert (depth, ctype) in ((8, 6), (8, 2)), (depth, ctype)
            bpp = 4 if ctype == 6 else 3
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw, rows, prev, stride = zlib.decompress(idat), [], bytearray(w * bpp), w * bpp
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * bpp:x * bpp + bpp]) + ((255,) if bpp == 3 else ()) for x in range(w)])
        prev = line
    return w, h, rows


def session():
    rows = [
        G.Row(1, "Review findings", "rice", branch="feat/x", state="waiting", mark="claude", tint=0xD97757,
              meta="Allow edit to Notifs.qml?", meta_tone="waiting"),
        G.Row(2, "Notch alerts", "rice", branch="feat/x", state="working", mark="claude", tint=0xD97757),
        G.Row(3, "notes.md", "rice", branch="feat/x", mark="neovim"),
        G.Row(4, "Bar redesign", "kittymux", state="working", active=True, mark="claude", tint=0xD97757),
        G.Row(5, "zsh", "home", path="~/Projects"),
    ]
    return G.group(rows)


@unittest.skipIf(B is None, "cairo/pango/rsvg not available")
class BarImageTest(unittest.TestCase):
    def setUp(self):
        self.out = B.render(session(), pal(), width=268, height=400, host="archlinux")
        self.w, self.h, self.px = decode_png(self.out.png)

    def test_the_picture_has_the_size_asked_for(self):
        self.assertEqual((self.w, self.h), (268, 400))

    def test_one_hit_band_per_tab_in_order_without_overlap(self):
        tabs = [hb for hb in self.out.hits if hb.kind == "tab"]
        self.assertEqual([hb.tab_id for hb in tabs], [1, 2, 3, 4, 5])
        for a, b in zip(tabs, tabs[1:]):
            self.assertLessEqual(a.y1, b.y0)
        self.assertTrue(all(hb.y1 > hb.y0 for hb in tabs))

    def test_the_row_map_alternates_per_tab_and_is_the_bar_elsewhere(self):
        bar = self.px[2][self.w // 2][:3]                  # the header's top edge: plain bar
        tabs = [hb for hb in self.out.hits if hb.kind == "tab"]
        marks = [self.px[(hb.y0 + hb.y1) // 2][0][:3] for hb in tabs]
        for a, b in zip(marks, marks[1:]):
            self.assertNotEqual(a, b)
        for m in marks:
            self.assertNotEqual(m, bar)
        self.assertEqual(self.px[2][0][:3], bar)

    def test_the_active_row_is_lighter_than_the_bar(self):
        hb = next(h for h in self.out.hits if h.kind == "tab" and h.tab_id == 4)
        y, x = (hb.y0 + hb.y1) // 2, self.w - 40
        self.assertGreater(sum(self.px[y][x][:3]), sum(self.px[2][self.w // 2][:3]))

    def test_a_needs_you_row_paints_its_chip_in_the_waiting_tone(self):
        hb = next(h for h in self.out.hits if h.kind == "tab" and h.tab_id == 1)
        band = [self.px[y][x] for y in range(hb.y0, hb.y1) for x in range(self.w - 60, self.w - 8)]
        w = pal().waiting
        target = ((w >> 16) & 255, (w >> 8) & 255, w & 255)
        self.assertTrue(any(sum(abs(a - b) for a, b in zip(p[:3], target)) < 60 for p in band))

    def test_scale_two_doubles_the_pixels_and_the_bands(self):
        out2 = B.render(session(), pal(), width=268, height=400, host="archlinux", scale=2)
        self.assertEqual(decode_png(out2.png)[:2], (536, 800))
        t1 = [h for h in self.out.hits if h.kind == "tab"]
        t2 = [h for h in out2.hits if h.kind == "tab"]
        self.assertEqual([h.y0 * 2 for h in t1], [h.y0 for h in t2])

    def test_the_rail_keeps_one_band_per_tab_and_its_row_map(self):
        out = B.render(session(), pal(), width=90, height=400, host="archlinux")
        w, h, px = decode_png(out.png)
        tabs = [hb for hb in out.hits if hb.kind == "tab"]
        self.assertEqual([hb.tab_id for hb in tabs], [1, 2, 3, 4, 5])
        marks = [px[(hb.y0 + hb.y1) // 2][0][:3] for hb in tabs]
        self.assertTrue(all(a != b for a, b in zip(marks, marks[1:])))

    def test_rendering_the_same_model_twice_gives_the_same_bytes(self):
        again = B.render(session(), pal(), width=268, height=400, host="archlinux")
        self.assertEqual(again.png, self.out.png)



@unittest.skipIf(B is None, "cairo/pango/rsvg not installed")
class ViewportTest(unittest.TestCase):
    """More tabs than fit: every drawn tab keeps its band, the rest are counted in a band you can click, and `start` scrolls."""
    @staticmethod
    def many(n=40):
        return G.group([G.Row(tab_id=i, title=f"tab {i}", project="dots") for i in range(1, n + 1)], collapse_after=99)

    def test_tabs_that_do_not_fit_are_counted_below(self):
        out = B.render(self.many(), pal(), width=268, height=400)
        tabs = [h for h in out.hits if h.kind == "tab"]
        self.assertEqual((out.start, out.shown, out.total), (0, len(tabs), 40))
        self.assertLess(out.shown, 40)
        self.assertEqual([h.tab_id for h in tabs], list(range(1, out.shown + 1)))
        self.assertEqual([h.kind for h in out.hits if h.kind in ("up", "down")], ["down"])
        down = next(h for h in out.hits if h.kind == "down")
        self.assertGreaterEqual(down.y0, tabs[-1].y1)

    def test_start_scrolls_the_tabs_and_shows_what_is_above(self):
        out = B.render(self.many(), pal(), width=268, height=400, start=30)
        tabs = [h.tab_id for h in out.hits if h.kind == "tab"]
        self.assertEqual(tabs[0], 31)
        self.assertEqual(out.start, 30)
        self.assertIn("up", [h.kind for h in out.hits])

    def test_everything_that_fits_has_no_more_bands(self):
        out = B.render(self.many(5), pal(), width=268, height=400)
        self.assertEqual((out.shown, out.total), (5, 5))
        self.assertFalse([h for h in out.hits if h.kind in ("up", "down")])

    def test_the_rail_scrolls_too(self):
        out = B.render(self.many(), pal(), width=90, height=400, start=10)
        tabs = [h.tab_id for h in out.hits if h.kind == "tab"]
        self.assertEqual(tabs[0], 11)
        self.assertEqual({h.kind for h in out.hits} & {"up", "down"}, {"up", "down"})

    def test_column_zero_ends_in_a_scale_run_of_eight_device_px_per_unit(self):
        for scale in (1, 2):
            out = B.render(self.many(3), pal(), width=268, height=200, scale=scale)
            w, h, px = decode_png(out.png)
            col = [px[y][0][:3] for y in range(h)]
            run = col[h - 3]
            n = 0
            while col[h - 3 - n] == run:
                n += 1
            self.assertEqual(n, 8 * scale)
            self.assertNotEqual(run, col[h - 1])




@unittest.skipIf(B is None, "cairo/pango/rsvg not installed")
class ControlsTest(unittest.TestCase):
    """The header's collapse and search, the footer's filter (the palette), the rail's mascot: each a control with its own x range."""
    def acts(self, out):
        return {h.project: h for h in out.hits if h.kind == "act"}

    def test_the_wide_bar_has_collapse_search_and_the_palette(self):
        out = B.render(session(), pal(), width=268, height=400, host="archlinux")
        a = self.acts(out)
        self.assertEqual(set(a), {"collapse", "search", "palette", "inbox", "usage", "keys"})
        self.assertLess(a["search"].x1, a["collapse"].x0 + 1)                    # search sits left of collapse
        self.assertGreater(a["palette"].y0, max(h.y1 for h in out.hits if h.kind == "tab") - 1)

    def test_a_control_wins_over_the_band_under_it(self):
        out = B.render(session(), pal(), width=268, height=400, host="archlinux")
        c = self.acts(out)["collapse"]
        self.assertEqual(B.hit_at(out.hits, (c.y0 + c.y1) // 2, (c.x0 + c.x1) // 2).project, "collapse")
        self.assertEqual(B.hit_at(out.hits, (c.y0 + c.y1) // 2, 5).kind, "header")

    def test_the_rail_mascot_expands_the_bar(self):
        out = B.render(session(), pal(), width=90, height=400)
        self.assertEqual(set(self.acts(out)), {"collapse"})

    def test_the_rail_uses_its_width(self):
        # 2026-11-12, the owner: the rail had "too much margin" (20 px tiles in a 9-column bar) and no visible way back open
        self.assertGreaterEqual(B.RAIL_TILE, 26)
        self.assertGreaterEqual(B.RAIL_CARD_W, 40)
        self.assertGreaterEqual(B.RAIL_ROW, B.RAIL_TILE + 10)
        out = B.render(session(), pal(), width=90, height=400)
        tabs = [hb for hb in out.hits if hb.kind == "tab"]
        self.assertTrue(all(hb.y1 - hb.y0 == B.RAIL_ROW for hb in tabs))

    def test_the_rail_card_is_one_card_in_the_picture_and_the_shader(self):
        import os
        src = open(os.path.join(os.path.dirname(__file__), "..", "assets", "shaders", "kittymux-pxbar.slang"), encoding="utf-8").read()
        half = B.RAIL_CARD_W / 2
        self.assertIn(f"x0 = mid - {half:.1f} * sc; x1 = mid + {half:.1f} * sc;", src)
        self.assertIn(f"float r0 = (rail ? {float(B.RAIL_CARD_R):.1f} : R) * sc;", src)

    def test_the_wave_steps_through_its_frames(self):
        row = lambda ph: G.group([G.Row(tab_id=1, title="t", project="p", state="working", phase=ph)])
        frames = {B.render(row(ph), pal(), width=268, height=200).png for ph in (0, 1, 2)}
        self.assertEqual(len(frames), 3)


@unittest.skipIf(B is None, "cairo/pango/rsvg not installed")
class EndMarksTest(unittest.TestCase):
    def png(self, **kw):
        return B.render(G.group([G.Row(tab_id=1, title="t", project="p", **kw)]), pal(), width=268, height=200).png

    def test_waiting_and_done_rows_show_their_age_beside_the_mark(self):
        self.assertNotEqual(self.png(state="waiting", age="10m"), self.png(state="waiting"))
        self.assertNotEqual(self.png(state="done", age="3m"), self.png(state="done"))

    def test_an_unread_row_has_a_mark(self):
        self.assertNotEqual(self.png(state="unread"), self.png(state=""))

    def test_a_muted_waiting_row_does_not_count_or_show_the_chip(self):
        g = G.group([G.Row(tab_id=1, title="t", project="p", state="waiting", muted=True)])
        self.assertEqual(G.needs_you(g), 0)
        self.assertNotEqual(self.png(state="waiting", muted=True), self.png(state="waiting"))


if __name__ == "__main__":
    unittest.main()
