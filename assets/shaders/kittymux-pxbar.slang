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
static const float R = 10.0;         // logical px, the band's corner radius (kittymux_barpx.ACTIVE_R: hover and active nest)
static const float REACH = 64.0;     // logical px searched up and down the row map (taller than any row)
static const float RAIL_MAX = 130.0; // logical px, kittymux_barpx.RAIL_MAX: narrower is the rail
static const float RUN = 8.0;        // kittymux_barpx.SCALE_RUN: column 0 ends in a run of RUN × scale device px
static const float CARD_M = 6.0;     // logical px: the terminal is a card inset this far from the window's top, right, bottom
static const float CARD_R = 10.0;    // logical px: its corner radius (Rex: the content rests on the sidebar's material)

float3 enc(float3 c) { return pow(max(c, float3(0.0)), float3(1.0 / 2.2)); }
float3 dec(float3 c) { return pow(max(c, float3(0.0)), float3(2.2)); }
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

// the terminal as a rounded card on the sidebar's material: outside the card (a thin margin and the corners) shows the
// sidebar picture's own colour at that height, so the two read as one surface with the content resting on it
float4 card(float4 color, KittyTextures t, KittyCustomShaderData d, float2 span) {
    float2 px = 1.0 / float2(d.viewport_size_pixels);
    float2 p = t.pos / px;
    float4 a = d.central_area;
    float l = a.x / px.x, r = (a.x + a.z) / px.x, b = a.y / px.y, tp = (a.y + a.w) / px.y;
    float edge = min(min(p.x - l, r - p.x), min(p.y - b, tp - p.y));
    if (edge > 40.0) return color;                                  // the card's inside: untouched, and cheap
    float sc = scale_of(t, px, px.x * 0.5);
    float m = CARD_M * sc, rad = CARD_R * sc;
    float2 lo = float2(l, b + m), hi = float2(r - m, tp - m);
    float2 c = clamp(p, lo + rad, hi - rad);
    float dist = length(p - c) - rad;                               // < 0 inside the rounded card
    float out_ = smoothstep(-0.75, 0.75, dist);
    if (out_ <= 0.0) return color;
    float4 matc = t.backbuffer.Sample(float2(span.y - 2.0 * px.x, t.pos.y));     // the sidebar's plain material at this height
    float3 mat = matc.rgb;
    float3 rgb = lerp(color.rgb, mat, out_);
    float rim = (1.0 - smoothstep(0.0, 1.0, abs(dist + 0.5))) * 0.06;          // a hairline where light catches the card's edge
    bool light = dot(mat, float3(0.2126, 0.7152, 0.0722)) > 0.4;
    rgb = lerp(rgb, light ? float3(0.0) : float3(1.0), rim);
    return float4(rgb, lerp(color.a, matc.a, out_));
}

public float4
fragment_main(float4 color, KittyTextures t, KittyCustomShaderData d) {
    float2 span = bar_span(d);
    if (span.x < 0.0) return color;
    if (t.pos.x > span.y) return card(color, t, d, span);
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
    bool rail = span.y / px.x < RAIL_MAX * sc;
    float r0 = (rail ? 9.0 : R) * sc;
    float x0 = INSET * sc, x1 = span.y / px.x - INSET * sc, y0 = bot / px.y, y1 = top / px.y;
    if (rail) {                                                     // the rail's card: kittymux_barpx draws the active one 30 px wide
        float mid = span.y / px.x * 0.5;
        x0 = mid - 15.0 * sc; x1 = mid + 15.0 * sc; y0 += 2.0 * sc; y1 -= 2.0 * sc;
    }
    float2 q = float2(max(max(x0 + r0 - p.x, p.x - (x1 - r0)), 0.0), max(max(y0 + r0 - p.y, p.y - (y1 - r0)), 0.0));
    float inside = 1.0 - smoothstep(r0 - 0.75, r0 + 0.75, length(q));
    bool light = dot(bar, float3(0.2126, 0.7152, 0.0722)) > 0.4;
    float3 veil = light ? float3(0.0) : float3(1.0);
    // in gamma-encoded space, like the picture's own cards (cairo paints the active card's veil 0.085 in sRGB): the hover is
    // about half that step, a press a little more; linear-light lerps looked brighter than the active card on a dark bar
    float lift = (light ? 0.028 : 0.045) * (d.mouse_button_pressed.x > 0.5 ? 1.6 : 1.0);
    float3 e = enc(color.rgb), eb = enc(bar);
    float3 ink = (e - eb) * 0.3 * inside;                           // a settled title lifts toward full strength under the pointer
    float3 hi = dec(clamp(lerp(e, veil, lift * inside) + ink, 0.0, 1.0));
    // the close cross, in the top line of the row (a two-line row keeps its second line); every size in logical px × sc
    if (rail) return float4(hi, color.a);                          // the rail: the tile is the whole row, no cross over it
    float cx = x1 - (PAD - INSET + 6.0) * sc, cy = min(y1 - 15.0 * sc, (y0 + y1) * 0.5);
    float2 r = (p - float2(cx, cy)) / sc;
    if (abs(r.x) < 11.0 && abs(r.y) < 10.0) hi = lerp(color.rgb, dec(lerp(eb, veil, lift)), inside);   // the cover stays inside the band
    float d1 = abs(r.x - r.y) * 0.7071, d2 = abs(r.x + r.y) * 0.7071;
    float on = (max(abs(r.x), abs(r.y)) < 4.5) ? 1.0 - smoothstep(0.6 / sc, 1.4 / sc, min(d1, d2)) : 0.0;
    float3 cross_ink = lerp(bar, veil, 0.62);
    hi = lerp(hi, cross_ink, on);
    return float4(hi, color.a);
}
