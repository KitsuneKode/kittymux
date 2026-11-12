#language slang 2026
// kittymux pxbar: hover for the pixel tab bar (python/kittymux_barpx.py), which kitty shows as the OS window's background
// image through blank tab-bar cells. Column 0 of the picture is a row map: every tab row's pixels there share one marker
// colour (alternating per row), the bar's own colour everywhere else. This shader paints column 0 back to its neighbour,
// and gives the row under the pointer a rounded highlight with a close cross at its end (over a cover that hides the age).
// A press darkens the band a little. Static: kitty redraws it when the pointer moves, not while it is still.
import kitty_custom_shader_types;

static const float EPS = 0.008;      // distance between gamma-encoded colours: markers 6 levels apart stay ~0.02 apart
                                     // even on a black bar (in linear RGB they were 0.002 apart there and merged)
static const float INSET = 5.0;      // logical px, matches kittymux_barpx.INSET
static const float PAD = 10.0;       // logical px, matches kittymux_barpx.PAD
static const float R = 8.0;          // logical px, the band's corner radius
static const float REACH = 64.0;     // logical px searched up and down the row map (taller than any row)
static const float RUN = 8.0;        // kittymux_barpx.SCALE_RUN: column 0 ends in a run of RUN × scale device px

float3 enc(float3 c) { return pow(max(c, float3(0.0)), float3(1.0 / 2.2)); }
float far(float3 a, float3 b) { return distance(enc(a), enc(b)); }

float2 bar_span(KittyCustomShaderData d) {
    float4 a = d.central_area;
    if (a.x >= 0.02) return float2(0.0, a.x);       // left edge only: the picture is anchored top-left
    return float2(-1.0, -1.0);
}

// the device-pixel scale the picture was drawn at: the length of the run at the bottom of column 0, over RUN
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
    float2 span = bar_span(d);
    if (span.x < 0.0 || t.pos.x > span.y) return color;
    float2 px = 1.0 / float2(d.viewport_size_pixels);
    if (t.pos.x < px.x) color = t.backbuffer.Sample(t.pos + float2(px.x, 0.0));     // hide the row map
    float2 m = d.mouse_pos.xy;
    if (d.mouse_pointer_hidden != 0.0 || m.x < 0.0 || m.x > span.y || m.y < 0.0 || m.y > 1.0) return color;
    float mx = px.x * 0.5;
    float sc = scale_of(t, px, mx);
    float reach = REACH * sc;
    if (m.y < (4.0 + RUN * sc) * px.y) return color;                               // the scale run, not a row
    if (abs(t.pos.y - m.y) / px.y > reach) return color;
    float3 key = t.backbuffer.Sample(float2(mx, m.y)).rgb;
    float3 bar = t.backbuffer.Sample(float2(mx, 1.0 - 2.0 * px.y)).rgb;             // the header's top edge: plain bar
    if (far(key, bar) < EPS * 0.5) return color;                                    // a header, a label or a gap
    float up = 0.0, down = 0.0;
    for (int k = 1; k <= int(reach); k++) {
        if (up == 0.0 && far(t.backbuffer.Sample(float2(mx, m.y + k * px.y)).rgb, key) > EPS) up = k;
        if (down == 0.0 && far(t.backbuffer.Sample(float2(mx, m.y - k * px.y)).rgb, key) > EPS) down = k;
        if (up != 0.0 && down != 0.0) break;
    }
    if (up == 0.0 || down == 0.0) return color;
    float top = m.y + (up - 1.0) * px.y, bot = m.y - (down - 1.0) * px.y;
    if (t.pos.y > top + px.y * 0.5 || t.pos.y < bot - px.y * 0.5) return color;
    float2 p = t.pos / px;
    float r0 = R * sc;
    float x0 = INSET * sc, x1 = span.y / px.x - INSET * sc, y0 = bot / px.y, y1 = top / px.y;
    float2 q = float2(max(max(x0 + r0 - p.x, p.x - (x1 - r0)), 0.0), max(max(y0 + r0 - p.y, p.y - (y1 - r0)), 0.0));
    float inside = 1.0 - smoothstep(r0 - 0.75, r0 + 0.75, length(q));
    bool light = dot(bar, float3(0.2126, 0.7152, 0.0722)) > 0.4;
    float3 veil = light ? float3(0.0) : float3(1.0);
    float lift = (light ? 0.05 : 0.055) * (d.mouse_button_pressed.x > 0.5 ? 1.6 : 1.0);
    float3 hi = lerp(color.rgb, veil, lift * inside);
    // the close cross, in the top line of the row (a two-line row keeps its second line); every size in logical px × sc
    float cx = x1 - (PAD - INSET + 6.0) * sc, cy = min(y1 - 15.0 * sc, (y0 + y1) * 0.5);
    float2 r = (p - float2(cx, cy)) / sc;
    if (abs(r.x) < 11.0 && abs(r.y) < 10.0) hi = lerp(color.rgb, lerp(bar, veil, lift), inside);   // the cover stays inside the band
    float d1 = abs(r.x - r.y) * 0.7071, d2 = abs(r.x + r.y) * 0.7071;
    float on = (max(abs(r.x), abs(r.y)) < 4.5) ? 1.0 - smoothstep(0.6 / sc, 1.4 / sc, min(d1, d2)) : 0.0;
    float3 ink = lerp(bar, veil, 0.62);
    hi = lerp(hi, ink, on);
    return float4(hi, color.a);
}
