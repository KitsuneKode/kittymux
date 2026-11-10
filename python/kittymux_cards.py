# The cards shader's pipeline text. Pure: no kitty imports.
#
# kitty resolves a pipeline's shaders next to the pipeline file, so the geninclude writes a copy into the state
# directory (symlinks to the shipped slang) with this kitty's cell height, the glass flag and the OSC 9;4 fill
# colours baked in as pipeline `var`s. The copy in assets/shaders is the same text with the defaults. The probe
# writes the row under the pointer into texture `a`; the cards shader reads that one texel.

import os

import kittymux_progress
import kittymux_theme

# (state, weight) the bar paints, in the order the shader's FILL0.. slots expect: waiting tint, running progress,
# error fill, unknown amount. Each is emitted twice: over the active card, then over the bar.
FILL_STATES = ("paused", "set", "error", "indeterminate")
FILL_SLOTS = len(FILL_STATES) * 2
# Where the cards shader samples the hover record the probe writes. UV, origin bottom-left.
HOVER_UV = (0.0025, 0.005)
SHADER_NAMES = (
    "kittymux-hover-probe.slang",
    "kittymux-cards.slang",
    "kittymux-glow.slang",
)


def fill_rgbs(pal) -> list[int]:
    """The eight sRGB colours `tab_bar` paints for OSC 9;4, active base then inactive base.

    Waiting is the paused tint, progress is `set`, the error fill is `error`, and the faint full-width tint is
    `indeterminate`. Same weights as `kittymux_progress.TINT`, over `surface_hi` on the active card and over `bar`
    on any other row — the blends in `tab_bar._draw_vertical`."""
    tint = {"paused": pal.waiting, "set": pal.accent, "error": pal.alert, "indeterminate": pal.accent}
    out = []
    for state in FILL_STATES:
        w = kittymux_progress.TINT[state]
        out.append(kittymux_theme.blend(tint[state], pal.surface_hi, w))
        out.append(kittymux_theme.blend(tint[state], pal.bar, w))
    return out


def srgb_float3(rgb: int) -> str:
    """`float3(r, g, b)` in 0..1 sRGB, the bytes the bar painted. The shader converts with its own sRGB curve."""
    chans = [((rgb >> shift) & 255) / 255.0 for shift in (16, 8, 0)]
    return "float3(" + ", ".join(f"{c:.6f}" for c in chans) + ")"


def linear_rgb(rgb: int) -> tuple[float, float, float]:
    """The shader's `lin()` of an sRGB byte colour, so a test can check two fills stay apart in the backbuffer."""
    def chan(s: float) -> float:
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    return tuple(chan(((rgb >> shift) & 255) / 255.0) for shift in (16, 8, 0))


def _fill_vars(fills: list[int] | None) -> list[str]:
    vals = list(fills or [])
    lines = []
    for i in range(FILL_SLOTS):
        if i < len(vals) and isinstance(vals[i], int) and vals[i] >= 0:
            value = srgb_float3(vals[i])
        else:
            value = "float3(-1.0, -1.0, -1.0)"
        lines.append(f"var float3 FILL{i} = {value}")
    return lines


def pipeline_text(glass: bool, cell_h: int, fills: list[int] | None = None) -> str:
    """The pipeline kitty compiles. `cell_h` 0 makes the shader guess a cell; negative fill slots are unused."""
    try:
        h = max(0, int(cell_h))
    except (TypeError, ValueError):
        h = 0
    glass_s = "true" if glass else "false"
    body = "\n".join([
        "# kittymux cards. The geninclude rewrites the var lines for the kitty that is loading this.",
        "textures a",
        f"var float CELL_H = {h}",
        f"var bool GLASS = {glass_s}",
        *_fill_vars(fills),
        "",
        "startgroup",
        "    # static, so kitty redraws it when the pointer moves and not while the pointer is still.",
        "    animation_step 0",
        "    shaders kittymux-hover-probe",
        "    output_texture a",
        "endgroup",
        "",
        "startgroup",
        "    animation_step 0",
        "    shaders kittymux-cards",
        "endgroup",
        "",
        "startgroup",
        "    animation_start tab-change",
        "    animation_stop 420",
        "    animation_curve ease-out",
        "    animation_step 16",
        "    shaders kittymux-glow",
        "endgroup",
        "",
    ])
    return body


def install_pipeline(sdir: str, shader_dir: str, glass: bool, cell_h: int, fills: list[int] | None) -> str:
    """Write the pipeline into `sdir`/shaders and symlink the slang beside it. Returns the pipeline path.

    Rewrites the file only when the text changed, so a reload does not look like a new shader. Raises on I/O
    errors; the geninclude catches that and falls back to the shipped pipeline."""
    dest = os.path.join(sdir, "shaders")
    os.makedirs(dest, mode=0o700, exist_ok=True)
    try:
        os.chmod(dest, 0o700)
    except OSError:
        pass
    for name in SHADER_NAMES:
        src = os.path.join(shader_dir, name)
        link = os.path.join(dest, name)
        if os.path.islink(link) and os.path.realpath(link) == os.path.realpath(src):
            continue
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink(src, link)
    text = pipeline_text(glass, cell_h, fills)
    path = os.path.join(dest, "kittymux-cards.pipeline")
    try:
        old = open(path, encoding="utf-8").read()
    except OSError:
        old = None
    if old != text:
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, text.encode())
        finally:
            os.close(fd)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    return path
