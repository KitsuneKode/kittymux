#language slang 2026
// kittymux cards: the vertical tab bar's flat cell cards, finished in pixels.
// Only the tab bar is touched (outside d.central_area). A card is a run of pixels painted in the active colour,
// or in one of the OSC 9;4 fills the bar paints over a card (waiting tint, progress, error, unknown amount).
// Fills round only at the bar's outer edge, so the end of a partial progress fill stays square.
// A bar row under the pointer (the band the probe stored) gets a softer step of the same mix, with the same
// corner. Glass, when the pipeline asks, lets the bar's own pixels go translucent; text and cards stay opaque.
// Colours are derived here from kitty's background and foreground exactly as kittymux_theme does.
// Static: kitty redraws it when the frame changes, which includes the pointer moving.
import kitty_custom_shader_types;

static const float BAR_W = 0.05;     // kittymux_theme: bar = blend(fg, bg, 0.05)
static const float CARD_W = 0.15;    // the active card = surface_hi = blend(fg, bg, 0.15)
static const float HOVER_W = 0.09;   // a quieter step of the same mix, between the bar and the card
static const float RADIUS = 7;       // px
static const float SHADOW = 6;       // px the shadow reaches below a card
static const float SHADOW_ALPHA = 0.30;
static const float SHEEN = 0.035;    // linear light added to a card's top row
static const float EPS = 0.006;      // colour match tolerance (linear)
static const float GLASS_A = 0.72;   // bar-pixel alpha when glass is on; text and cards stay at 1
static const float CELL_H = 0;       // px; 0 guesses 20. The geninclude sets the live cell height.
static const bool GLASS = false;
static const float3 FILL0 = float3(-1.0, -1.0, -1.0);
static const float3 FILL1 = float3(-1.0, -1.0, -1.0);
static const float3 FILL2 = float3(-1.0, -1.0, -1.0);
static const float3 FILL3 = float3(-1.0, -1.0, -1.0);
static const float3 FILL4 = float3(-1.0, -1.0, -1.0);
static const float3 FILL5 = float3(-1.0, -1.0, -1.0);
static const float3 FILL6 = float3(-1.0, -1.0, -1.0);
static const float3 FILL7 = float3(-1.0, -1.0, -1.0);

float3 srgb(float3 c) {
    float3 lo = c * 12.92;
    float3 hi = 1.055 * pow(c, float3(1.0 / 2.4)) - 0.055;
    return lerp(hi, lo, step(c, float3(0.0031308)));
}
float3 lin(float3 c) {
    float3 lo = c / 12.92;
    float3 hi = pow((c + 0.055) / 1.055, float3(2.4));
    return lerp(hi, lo, step(c, float3(0.04045)));
}
float3 theme_blend(KittyCustomShaderData d, float w) {
    float3 m = lerp(srgb(d.background.rgb), srgb(d.foreground.rgb), w);
    return lin(round(m * 255.0) / 255.0);
}
bool near(float3 a, float3 b) { return distance(a, b) < EPS; }

float2 bar_span(KittyCustomShaderData d) {
    float4 a = d.central_area;
    float left = a.x;
    float right = 1.0 - (a.x + a.z);
    if (left >= 0.02 && left >= right) return float2(0.0, left);
    if (right >= 0.02) return float2(a.x + a.z, 1.0);
    return float2(-1.0, -1.0);
}

public float4
fragment_main(float4 color, KittyTextures t, KittyCustomShaderData d) {
    float4 a = d.central_area;
    if (all(t.pos >= a.xy) && all(t.pos <= a.xy + a.zw)) return color;
    float3 bar = theme_blend(d, BAR_W);
    float3 card = theme_blend(d, CARD_W);
    float3 f0 = lin(FILL0), f1 = lin(FILL1), f2 = lin(FILL2), f3 = lin(FILL3);
    float3 f4 = lin(FILL4), f5 = lin(FILL5), f6 = lin(FILL6), f7 = lin(FILL7);
    bool u0 = FILL0.x >= 0.0, u1 = FILL1.x >= 0.0, u2 = FILL2.x >= 0.0, u3 = FILL3.x >= 0.0;
    bool u4 = FILL4.x >= 0.0, u5 = FILL5.x >= 0.0, u6 = FILL6.x >= 0.0, u7 = FILL7.x >= 0.0;
    bool fill = (u0 && near(color.rgb, f0)) || (u1 && near(color.rgb, f1)) || (u2 && near(color.rgb, f2)) || (u3 && near(color.rgb, f3))
        || (u4 && near(color.rgb, f4)) || (u5 && near(color.rgb, f5)) || (u6 && near(color.rgb, f6)) || (u7 && near(color.rgb, f7));
    bool is_card = near(color.rgb, card);
    float2 px = 1.0 / float2(d.viewport_size_pixels);
    int R = int(RADIUS);
    float glass = 0.0;   // how much of this pixel is really the bar (the corner cut fades a card into it)

    if (is_card || fill) {
        float l = RADIUS + 1, r = RADIUS + 1, u = RADIUS + 1, w = RADIUS + 1;
        for (int k = 1; k <= R; k++) {
            if (l > RADIUS && near(t.backbuffer.Sample(t.pos - float2(k, 0) * px).rgb, bar)) l = k;
            if (r > RADIUS && near(t.backbuffer.Sample(t.pos + float2(k, 0) * px).rgb, bar)) r = k;
            if (u > RADIUS && near(t.backbuffer.Sample(t.pos + float2(0, k) * px).rgb, bar)) u = k;   // origin bottom-left: up is +y
            if (w > RADIUS && near(t.backbuffer.Sample(t.pos - float2(0, k) * px).rgb, bar)) w = k;
        }
        float hx = min(l, r), hy = min(u, w);
        float3 c = color.rgb;
        if (is_card && u == 1) c += SHEEN;
        // a fill's right-hand end sits on the bar too, in the middle of the row: that is the progress, not a corner
        // of the card. Only a fill pixel near the bar's own left or right edge is a card corner.
        float cell_px = CELL_H > 2.0 ? CELL_H : 20.0;
        float2 span = bar_span(d);
        bool outer = span.x >= 0.0 && (t.pos.x < span.x + cell_px * 1.8 * px.x || t.pos.x > span.y - cell_px * 2.6 * px.x);
        if (hx <= RADIUS && hy <= RADIUS && (is_card || outer)) {
            float dist = length(float2(RADIUS - hx + 0.5, RADIUS - hy + 0.5));
            float cut = smoothstep(RADIUS - 0.75, RADIUS + 0.75, dist);
            c = lerp(c, bar, cut);
            glass = cut;
        }
        float alpha = GLASS ? lerp(color.a, GLASS_A, glass) : color.a;
        return float4(c, alpha);
    }

    if (near(color.rgb, bar)) {
        float s = 0;
        int S = int(SHADOW);
        for (int k = 1; k <= S; k++) {
            float3 above = t.backbuffer.Sample(t.pos + float2(0, k) * px).rgb;
            bool above_card = near(above, card)
                || (u0 && near(above, f0)) || (u1 && near(above, f1)) || (u2 && near(above, f2)) || (u3 && near(above, f3))
                || (u4 && near(above, f4)) || (u5 && near(above, f5)) || (u6 && near(above, f6)) || (u7 && near(above, f7));
            if (above_card) {
                float f = 1.0 - float(k) / (SHADOW + 1);
                s = max(s, f * f);
                break;
            }
        }
        for (int k = 1; k <= S / 2; k++) {
            float2 o = float2(k, 0) * px;
            float3 side_r = t.backbuffer.Sample(t.pos + o).rgb;
            float3 side_l = t.backbuffer.Sample(t.pos - o).rgb;
            bool side = near(side_r, card) || near(side_l, card)
                || (u0 && (near(side_r, f0) || near(side_l, f0))) || (u1 && (near(side_r, f1) || near(side_l, f1)))
                || (u2 && (near(side_r, f2) || near(side_l, f2))) || (u3 && (near(side_r, f3) || near(side_l, f3)))
                || (u4 && (near(side_r, f4) || near(side_l, f4))) || (u5 && (near(side_r, f5) || near(side_l, f5)))
                || (u6 && (near(side_r, f6) || near(side_l, f6))) || (u7 && (near(side_r, f7) || near(side_l, f7)));
            if (side) {
                float f = 1.0 - float(k) / (SHADOW / 2 + 1);
                s = max(s, 0.45 * f * f);
                break;
            }
        }
        float3 c = color.rgb * (1.0 - SHADOW_ALPHA * s);
        float4 hv = t.a.Sample(float2(0.0025, 0.005));
        if (hv.b > 0.5 && hv.g > hv.r) {
            float cell_px = CELL_H > 2.0 ? CELL_H : 20.0;
            float2 span = bar_span(d);
            if (span.x >= 0.0) {
                float x0 = span.x + cell_px * 0.55 * px.x;
                float x1 = span.y - cell_px * 2.4 * px.x;
                float2 pix = t.pos * float2(d.viewport_size_pixels);
                float2 rmin = float2(x0, hv.r) * float2(d.viewport_size_pixels);
                float2 rmax = float2(x1, hv.g) * float2(d.viewport_size_pixels);
                float2 edge = min(pix - rmin, rmax - pix);
                if (edge.x > 0.0 && edge.y > 0.0) {
                    float cut = 0.0;
                    if (edge.x < RADIUS && edge.y < RADIUS) {
                        float dist = length(float2(RADIUS - edge.x, RADIUS - edge.y));
                        cut = smoothstep(RADIUS - 0.75, RADIUS + 0.75, dist);
                    }
                    c = lerp(theme_blend(d, HOVER_W), c, cut);
                }
            }
        }
        float alpha = GLASS ? GLASS_A : color.a;
        return float4(c, alpha);
    }
    return color;
}
