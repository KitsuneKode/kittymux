#language slang 2026
// kittymux pxwave: the working loader of the pixel tab bar (python/kittymux_barpx.py), animated. It runs only between the
// events user:kmx-wave-on and user:kmx-wave-off (kittymux_pxbar.publish fires them as rows start and stop working) and at
// 15 fps (kittymux-pxbar.pipeline), so an idle bar costs nothing. The picture draws a still wave; this shader finds the
// working rows through their own family of row-map markers (column 0, kittymux_barpx.marker(working=True)) and redraws
// the three bars rising and falling, each a little behind the one before. A row under the pointer keeps its close cross.
import kitty_custom_shader_types;

static const float EPS = 0.008;      // as kittymux-pxbar.slang: colours compared gamma-encoded
static const float PAD = 10.0;       // logical px, kittymux_barpx.PAD
static const float INSET = 5.0;      // logical px, kittymux_barpx.INSET
static const float RUN = 8.0;        // kittymux_barpx.SCALE_RUN
static const float FAMILY = 0.09;    // encoded red-channel distance from the bar: working markers (+30/+36) sit past it, rows (+6/+12) under it
static const float CY = 15.0;        // logical px from a row's top to its first line's centre (a working row always has a second line)
static const float SPEED = 0.85;     // waves per second: calm, never a buzz

float3 enc(float3 c) { return pow(max(c, float3(0.0)), float3(1.0 / 2.2)); }
float far(float3 a, float3 b) { return distance(enc(a), enc(b)); }

float scale_of(KittyTextures t, float2 px, float mx) {
    float3 run = t.backbuffer.Sample(float2(mx, 2.5 * px.y)).rgb;
    float n = 0.0;
    for (int k = 0; k < 48; k++) {
        if (far(t.backbuffer.Sample(float2(mx, (2.5 + float(k)) * px.y)).rgb, run) > EPS) break;
        n += 1.0;
    }
    return max(1.0, n / RUN);
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
