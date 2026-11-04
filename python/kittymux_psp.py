"""Program Status Protocol (OSC 7501) — what an agent says it is doing, read on its way to the terminal.

kitty 0.49 drops OSC 7501, so `bin/mux-pty` sits between kitty and an agent kittymux started: it passes every byte
through, answers the protocol's probe, keeps the records here, and hands the summary to kitty as a user variable
(`kittymux_psp`, via OSC 1337 SetUserVar) that the scanner reads. Pure: no kitty imports, no I/O.

Spec (draft 0.4): ESC ] 7501 ; key=value[:key=value…] ST, ST = ESC \\ or BEL; probe ESC ] 7501 ; ? ST.
"""
from __future__ import annotations

import base64
import binascii
import json
import re

STATES = ("idle", "working", "done", "blocked", "error", "clear")
KINDS = ("permission", "question", "auth")
REPLY = b"\x1b]7501;?:states=idle,working,done,blocked,error:kinds=permission,question,auth\x1b\\"
MAX_SEQ = 4096
MAX_RECORDS = 256
VAR = "kittymux_psp"

_KEY = re.compile(r"[a-z]+")
_VALUE = re.compile(r"[A-Za-z0-9_.,+/=-]*")
_APP = re.compile(r"[A-Za-z0-9_.+-]{1,32}")
_SEG = re.compile(r"[A-Za-z0-9_.+-]{1,32}")
_PREFIX = b"\x1b]7501;"


def _b64(value: str, enc_max: int, dec_max: int) -> str | None:
    if len(value) > enc_max:
        return None
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), validate=True)
        text = raw.decode("utf-8")
    except (binascii.Error, ValueError):
        return None
    if len(raw) > dec_max or any(ord(c) < 32 or ord(c) == 127 for c in text):
        return None
    return text


def parse(payload: str) -> dict | None:
    """One report's payload (after `7501;`) as a record, or None if the spec says to ignore it."""
    pairs: dict[str, str] = {}
    for part in payload.split(":"):
        key, eq, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if not eq or not _KEY.fullmatch(key) or len(key) > 16 or not _VALUE.fullmatch(value):
            continue                                    # a malformed pair is skipped, the rest still counts
        pairs[key] = value                              # repeated keys: the last wins
    state = pairs.get("state")
    if state not in STATES:
        return None
    rec: dict = {"state": state}
    if "id" in pairs:
        segs = pairs["id"].split("/")
        if len(pairs["id"]) > 128 or len(segs) > 8 or not all(_SEG.fullmatch(s) for s in segs):
            return None                                 # an invalid id ignores the report (no fallback to the root)
        rec["id"] = pairs["id"]
    if pairs.get("kind") in KINDS and state == "blocked":
        rec["kind"] = pairs["kind"]
    if "progress" in pairs and state in ("working", "blocked") and pairs["progress"].isdigit() and int(pairs["progress"]) <= 100:
        rec["progress"] = int(pairs["progress"])
    if "app" in pairs:
        if not _APP.fullmatch(pairs["app"]):
            return None
        rec["app"] = pairs["app"]
    for key, enc_max, dec_max in (("title", 256, 192), ("msg", 2732, 2048)):
        if key in pairs:
            text = _b64(pairs[key], enc_max, dec_max)
            if text is None:
                return None                             # bad base64 or a control character: discard the whole report
            rec[key] = text
    return rec


class Scanner:
    """Finds OSC 7501 sequences in a byte stream that arrives in arbitrary chunks. `feed` returns events:
    ("query",) for a probe, ("report", record) for a valid report. Nothing is removed from the stream."""

    def __init__(self) -> None:
        self._buf = b""            # bytes of a sequence that may still be ours (starts with ESC)

    def feed(self, data: bytes) -> list:
        events: list = []
        data = self._buf + data
        self._buf = b""
        i = 0
        while True:
            j = data.find(b"\x1b]", i)
            if j < 0:
                if data.endswith(b"\x1b"):
                    self._buf = b"\x1b"
                break
            head = data[j:j + len(_PREFIX)]
            if not _PREFIX.startswith(head):            # another OSC: not ours
                i = j + 2
                continue
            if len(head) < len(_PREFIX):                # "ESC ] 75" at the end of a chunk: wait for more
                self._buf = data[j:]
                break
            body_start = j + len(_PREFIX)
            end, st_len = -1, 0
            for k in range(body_start, min(len(data), j + MAX_SEQ)):
                c = data[k]
                if c == 0x07:
                    end, st_len = k, 1
                    break
                if c == 0x1b:
                    if k + 1 < len(data) and data[k + 1] == 0x5c:
                        end, st_len = k, 2
                        break
                    if k + 1 >= len(data):
                        break                           # ESC as the last byte: maybe the start of ST
                    end = -2                            # ESC + something else: the sequence was cut off
                    break
            if end == -2:
                i = body_start
                continue
            if end < 0:
                if len(data) - j >= MAX_SEQ:            # too long: give up on it
                    i = body_start
                    continue
                self._buf = data[j:]
                break
            payload = data[body_start:end].decode("ascii", "replace")
            if payload.strip() == "?":
                events.append(("query",))
            else:
                rec = parse(payload)
                if rec is not None:
                    events.append(("report", rec))
            i = end + st_len
        return events


class Records:
    """The records one program reported, by id ("" is the root). Each report replaces its record whole."""

    def __init__(self) -> None:
        self.by_id: dict[str, dict] = {}

    def apply(self, rec: dict, now: float) -> None:
        rid = rec.get("id", "")
        if rec["state"] == "clear":
            if not rid:
                self.by_id.clear()
            else:
                for k in [k for k in self.by_id if k == rid or k.startswith(rid + "/")]:
                    del self.by_id[k]
            return
        self.by_id.pop(rid, None)
        self.by_id[rid] = {**rec, "t": now}
        while len(self.by_id) > MAX_RECORDS:            # the least recently updated goes
            del self.by_id[min(self.by_id, key=lambda k: self.by_id[k]["t"])]

    def drop_live(self) -> None:
        """A new prompt began or the program exited: working and blocked (and idle) records go, done and error stay."""
        for k in [k for k, r in self.by_id.items() if r["state"] in ("working", "blocked", "idle")]:
            del self.by_id[k]

    def summary(self) -> dict | None:
        """The one record that speaks for the program: the most urgent, then the newest."""
        if not self.by_id:
            return None
        rank = {"blocked": 5, "error": 4, "working": 3, "done": 2, "idle": 1}
        return max(self.by_id.values(), key=lambda r: (rank.get(r["state"], 0), r["t"]))


def user_var(summary: dict | None) -> bytes:
    """OSC 1337 SetUserVar carrying the summary as JSON (empty clears it). kitty stores it on the window."""
    value = "" if summary is None else json.dumps(summary, separators=(",", ":"), ensure_ascii=False)
    enc = base64.b64encode(value.encode()).decode()
    return f"\x1b]1337;SetUserVar={VAR}={enc}\x07".encode()


def read_var(user_vars: dict) -> dict | None:
    """The summary back from a window's user variables (kitty decodes the base64), or None."""
    raw = (user_vars or {}).get(VAR) or ""
    try:
        rec = json.loads(raw)
    except ValueError:
        return None
    return rec if isinstance(rec, dict) and rec.get("state") in STATES else None


def apply_to_view(rec: dict | None, view: dict, marker: str, line: str) -> tuple[str, str]:
    """Fold a reported status into the scanner's inputs, as the strongest evidence there is: `view` is the scanner's
    bookkeeping (as hooks fill it), `marker`/`line` what the screen showed. Returns the (marker, line) to resolve with."""
    if not rec:
        return marker, line
    state, t = rec["state"], float(rec.get("t") or 0)
    text = rec.get("msg") or rec.get("title") or ""
    if state == "blocked":
        view["why"] = "it reports it is blocked (OSC 7501)"
        return "waiting", text or line or ({"auth": "Needs a login", "question": "Has a question"}.get(rec.get("kind", ""), "Needs your permission"))
    if state == "working":
        view["status"], view["ts_status"] = "working", t
        return ("" if marker == "waiting" else marker), line
    if state == "done":
        if t > float(view.get("agent_done_ts") or 0):
            view["agent_done_ts"] = t
        view["done_source"] = "agent"
        return ("" if marker == "waiting" else marker), line
    if state == "error":
        # Not a completion: a quiet screen must not grow a checkmark, and a busy one must not hide the failure.
        view.pop("agent_done_ts", None)
        view.pop("done_source", None)
        view["status"], view["ts_status"] = "error", t
        if text:
            view["msg"] = text
        if marker in ("limited", "waiting"):          # a prompt or a limit still outranks a reported failure
            return marker, line
        return "error", text
    if state == "idle":
        view["status"], view["ts_status"] = "idle", t
    return marker, line


class Boundary:
    """Whether the output so far ends at a clean point: outside every escape sequence (CSI, OSC/DCS/APC strings such as
    kitty's image chunks, which span many reads) and not inside a UTF-8 character. The relay only slips its own
    sequence into the stream there. Scans with bytes.find, so a busy stream costs little."""

    GROUND, ESC, CSI, STR, STR_ESC, ONE = range(6)

    def __init__(self) -> None:
        self.state = self.GROUND

    def feed(self, data: bytes) -> bool:
        i, n = 0, len(data)
        while i < n:
            s = self.state
            if s == self.GROUND:
                e = data.find(b"\x1b", i)
                if e < 0:
                    return _utf8_complete(data[max(i, n - 4):])
                self.state, i = self.ESC, e + 1
            elif s == self.ESC:
                c = data[i]
                i += 1
                if c == 0x5B:
                    self.state = self.CSI
                elif c in (0x5D, 0x50, 0x5F, 0x5E, 0x58):           # ] P _ ^ X: strings ended by BEL or ST
                    self.state = self.STR
                elif c in b"()*+-./#%":
                    self.state = self.ONE
                else:
                    self.state = self.GROUND
            elif s == self.ONE:
                i += 1
                self.state = self.GROUND
            elif s == self.CSI:
                while i < n and not (0x40 <= data[i] <= 0x7E):
                    i += 1
                if i < n:
                    i += 1
                    self.state = self.GROUND
            elif s == self.STR:
                bel, esc = data.find(b"\x07", i), data.find(b"\x1b", i)
                hits = [x for x in (bel, esc) if x >= 0]
                if not hits:
                    return False
                k = min(hits)
                self.state, i = (self.GROUND if k == bel else self.STR_ESC), k + 1
            else:                                                     # STR_ESC
                if data[i] == 0x5C:
                    self.state, i = self.GROUND, i + 1
                else:
                    self.state = self.ESC                             # ESC + other: a new sequence begins
        return self.state == self.GROUND and (n == 0 or _utf8_complete(data[-4:]))


def _utf8_complete(tail: bytes) -> bool:
    """True unless `tail` ends partway through a UTF-8 character."""
    for back in range(1, min(4, len(tail)) + 1):
        b = tail[-back]
        if b < 0x80:
            return True
        if b >= 0xC0:                                                 # a lead byte: how long should it be?
            need = 2 if b < 0xE0 else 3 if b < 0xF0 else 4
            return back >= need
    return True
