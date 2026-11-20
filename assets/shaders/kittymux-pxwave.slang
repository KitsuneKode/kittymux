#language slang 2026
// kittymux pxwave: the working loader of the pixel tab bar (python/kittymux_barpx.py), animated. It runs only between the
// events user:kmx-wave-on and user:kmx-wave-off (kittymux_pxbar.publish fires them as rows start and stop working) and at
// 15 fps (kittymux-pxbar.pipeline), so an idle bar costs nothing. The picture draws a still wave; this shader finds the
// working rows through their own family of row-map markers (column 0, kittymux_barpx.marker(working=True)) and redraws
// the three bars rising and falling, each a little behind the one before. A row under the pointer keeps its close cross.
// On the rail the loader is the open ring in the tile's top-right corner (kittymux_barpx._rail_pip): it turns.
import kitty_custom_shader_types;

static const float EPS = 0.008;      // as kittymux-pxbar.slang: colours compared gamma-encoded
static const float PAD = 10.0;       // logical px, kittymux_barpx.PAD
static const float INSET = 5.0;      // logical px, kittymux_barpx.INSET
static const float RUN = 8.0;        // kittymux_barpx.SCALE_RUN
static const float FAMILY = 0.09;    // encoded red-channel distance from the bar: working markers (+30/+36) sit past it, rows (+6/+12) under it
static const float CY = 15.0;        // logical px from a row's top to its first line's centre (a working row always has a second line)
static const float SPEED = 0.85;     // waves per second: calm, never a buzz
static const float RAIL_MAX = 130.0; // kittymux_barpx.RAIL_MAX: a narrower bar is the rail
static const float RAIL_ROW = 36.0;  // kittymux_barpx.RAIL_ROW
static const float RAIL_TILE = 30.0; // kittymux_barpx.RAIL_TILE
static const float RAIL_PIP_IN = 4.5;  // kittymux_barpx.RAIL_PIP_IN: the ring's centre, in from the tile's top and right
static const float RAIL_PIP_R = 3.0;   // kittymux_barpx.RAIL_PIP_R
static const float TURNS = 0.6;      // the rail ring's turns per second

float3 enc(float3 c) { return pow(max(c, float3(0.0)), float3(1.0 / 2.2)); }
float far(float3 a, float3 b) { return distance(enc(a), enc(b)); }

float scale_of(KittyTextures t, float2 px, float mx) {
    float3 bar = t.backbuffer.Sample(float2(mx, 1.0 - 2.0 * px.y)).rgb;
    float3 run = t.backbuffer.Sample(float2(mx, 2.5 * px.y)).rgb;
    if (far(run, bar) < EPS * 0.5) return 0.0;
    float n = 0.0;
    for (int k = 0; k < 48; k++) {
        if (far(t.backbuffer.Sample(float2(mx, (2.5 + float(k)) * px.y)).rgb, run) > EPS) break;
        n += 1.0;
    }
    if (n < 4.0 || n >= 44.0) return 0.0;
    return max(1.0, n / RUN);
}

// the row map's band around device row y (origin bottom-left): (top, bottom), or (-1, -1) when y is not on a working row
float2 working_band(KittyTextures t, float2 px, float y, float sc) {
    float mx = px.x * 0.5;
    float3 bar = t.backbuffer.Sample(float2(mx, 1.0 - 2.0 * px.y)).rgb;
    float3 key = t.backbuffer.Sample(float2(mx, y * px.y)).rgb;
    if (abs(enc(key).r - enc(bar).r) < FAMILY) return float2(-1.0, -1.0);
    float up = 0.0, down = 0.0;
    for (int k = 1; k <= int(64.0 * sc); k++) {
        if (up == 0.0 && far(t.backbuffer.Sample(float2(mx, (y + k) * px.y)).rgb, key) > EPS) up = k;
        if (down == 0.0 && far(t.backbuffer.Sample(float2(mx, (y - k) * px.y)).rgb, key) > EPS) down = k;
        if (up != 0.0 && down != 0.0) break;
    }
    if (up == 0.0 || down == 0.0) return float2(-1.0, -1.0);
    return float2(y + up - 1.0, y - down + 1.0);
}

// the rail: a working row's ring turns, a bright head and a fading tail. The picture's still ring gives the ink (its right
// side) and the tile under it (its hollow centre), so the active tile and the plain rail both stay what they are.
float4 rail_ring(float4 color, KittyTextures t, KittyCustomShaderData d, float2 px, float2 p, float barw, float sc) {
    float cx = barw * 0.5 + (RAIL_TILE * 0.5 - RAIL_PIP_IN) * sc;
    if (abs(p.x - cx) > (RAIL_PIP_R + 1.5) * sc) return color;
    float2 band = working_band(t, px, p.y, sc);
    if (band.x < 0.0) return color;
    float cy = band.x - ((RAIL_ROW - RAIL_TILE) * 0.5 + RAIL_PIP_IN) * sc;   // y grows up: the tile's top is below the row's
    float2 v = p - float2(cx, cy);
    float rr = (RAIL_PIP_R - 0.3) * sc;
    if (length(v) > rr + 1.5 * sc) return color;
    float3 bg = t.backbuffer.Sample(float2(cx, cy) * px).rgb;
    float3 ink = t.backbuffer.Sample(float2(cx + rr, cy) * px).rgb;
    float ring = 1.0 - smoothstep(0.75 * sc - 0.5, 0.75 * sc + 0.5, abs(length(v) - rr));
    float ang = atan2(v.y, v.x) / 6.2832;                           // turns, counter-clockwise from +x
    float head = frac(d.wrapped_time(600) * TURNS);
    float behind = frac(head - ang);                                // 0 at the head, growing along the tail (clockwise turning)
    float on = ring * (behind < 0.75 ? 1.0 - behind * 0.9 : 0.0);
    return float4(lerp(bg, ink, on), color.a);
}

public float4
fragment_main(float4 color, KittyTextures t, KittyCustomShaderData d) {
    float4 a = d.central_area;
    if (a.x < 0.02) return color;                                   // the bar is on the left only
    float2 px = 1.0 / float2(d.viewport_size_pixels);
    float2 p = t.pos / px;
    float barw = a.x / px.x;
    if (p.x > barw || p.x < barw - 90.0) return color;              // only the end slot's strip (up to 3x scale)
    float mx = px.x * 0.5;
    float sc = scale_of(t, px, mx);
    if (sc <= 0.0) return color;
    if (barw < RAIL_MAX * sc) return rail_ring(color, t, d, px, p, barw, sc);
    float right = barw - (PAD + INSET) * sc;
    if (p.x < right - 13.0 * sc || p.x > right) return color;
    float3 bar = t.backbuffer.Sample(float2(mx, 1.0 - 2.0 * px.y)).rgb;
    float3 key = t.backbuffer.Sample(float2(mx, t.pos.y)).rgb;
    if (abs(enc(key).r - enc(bar).r) < FAMILY) return color;        // not a working row
    float up = 0.0, down = 0.0;
    for (int k = 1; k <= int(64.0 * sc); k++) {
        if (up == 0.0 && far(t.backbuffer.Sample(float2(mx, t.pos.y + k * px.y)).rgb, key) > EPS) up = k;
        if (down == 0.0 && far(t.backbuffer.Sample(float2(mx, t.pos.y - k * px.y)).rgb, key) > EPS) down = k;
        if (up != 0.0 && down != 0.0) break;
    }
    if (up == 0.0 || down == 0.0) return color;
    float top = p.y + up - 1.0, bot = p.y - down + 1.0;              // device px, origin bottom-left
    float2 m = d.mouse_pos.xy / px;
    if (d.mouse_pointer_hidden == 0.0 && m.x >= 0.0 && m.x <= barw && m.y <= top + 0.5 && m.y >= bot - 0.5)
        return color;                                               // the pointer's row shows its close cross
    float cy = top - CY * sc;
    if (abs(p.y - cy) > 7.0 * sc) return color;
    float3 bg = t.backbuffer.Sample(float2((right - 16.0 * sc) * px.x, t.pos.y)).rgb;   // the gap before the end slot
    float3 ink = t.backbuffer.Sample(float2((right - 7.0 * sc) * px.x, cy * px.y)).rgb; // the still wave's middle bar
    float time = d.wrapped_time(600);
    float on = 0.0;
    for (int i = 0; i < 3; i++) {
        float w = 2.0 * sc;
        float bx = right - 12.0 * sc + float(i) * 4.0 * sc + w * 0.5;
        float h = (4.0 + 7.0 * (0.5 + 0.5 * sin(time * 6.2832 * SPEED - float(i) * 1.15))) * sc;   // 4..11 logical px
        float2 c = float2(bx, clamp(p.y, cy - h * 0.5 + w * 0.5, cy + h * 0.5 - w * 0.5));
        float dd = length(p - c) - w * 0.5;
        on = max(on, 1.0 - smoothstep(-0.6, 0.6, dd));
    }
    return float4(lerp(bg, ink, on), color.a);
}
