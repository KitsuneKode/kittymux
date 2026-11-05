#language slang 2026
// kittymux cards: the vertical tab bar's flat cell cards, finished in pixels.
// Only the tab bar is touched (outside d.central_area). A card is the run of pixels painted in CARD; the bar is BAR
// (both derived here from kitty's own background/foreground exactly as kittymux_theme does, so any theme works).
// For a card pixel near two edges the corner is cut on a circle of RADIUS px (anti-aliased); its top row gets a faint
// sheen; a bar pixel just under (or beside) a card takes a soft shadow. Static: kitty redraws it only when the frame changes.
import kitty_custom_shader_types;

static const float BAR_W = 0.05;    // kittymux_theme: bar = blend(fg, bg, 0.05)
static const float CARD_W = 0.15;   // the active card = surface_hi = blend(fg, bg, 0.15)
static const float RADIUS = 7;      // px
static const float SHADOW = 6;      // px the shadow reaches below a card
static const float SHADOW_ALPHA = 0.30;
static const float SHEEN = 0.035;   // linear light added to a card's top row
static const float EPS = 0.006;     // colour match tolerance (linear)

// kittymux_theme.blend in sRGB with each channel rounded to 1/255, then back to linear: the same colour the bar painted
float3 srgb(float3 c) {
    float3 lo = c * 12.92;
    float3 hi = 1.055 * pow(c, float3(1.0 / 2.4)) - 0.055;
    return lerp(hi, lo, step(c, float3(0.0031308)));
}
float3 lin(float3 c) {                      // the exact sRGB transfer curve (pow 2.2 is off by more than EPS in the darks)
    float3 lo = c / 12.92;
    float3 hi = pow((c + 0.055) / 1.055, float3(2.4));
    return lerp(hi, lo, step(c, float3(0.04045)));
}
float3 theme_blend(KittyCustomShaderData d, float w) {
    float3 m = lerp(srgb(d.background.rgb), srgb(d.foreground.rgb), w);
    return lin(round(m * 255.0) / 255.0);
}

bool near(float3 a, float3 b) { return distance(a, b) < EPS; }

public float4
fragment_main(float4 color, KittyTextures t, KittyCustomShaderData d) {
    float4 a = d.central_area;
    if (all(t.pos >= a.xy) && all(t.pos <= a.xy + a.zw)) return color;      // panes: untouched
    float3 bar = theme_blend(d, BAR_W);
    float3 card = theme_blend(d, CARD_W);
    float2 px = 1.0 / float2(d.viewport_size_pixels);
    int R = int(RADIUS);

    if (near(color.rgb, card)) {
        // distance (px) to the bar on each side, up to RADIUS
        float l = RADIUS + 1, r = RADIUS + 1, u = RADIUS + 1, w = RADIUS + 1;
        for (int k = 1; k <= R; k++) {
            if (l > RADIUS && near(t.backbuffer.Sample(t.pos - float2(k, 0) * px).rgb, bar)) l = k;
            if (r > RADIUS && near(t.backbuffer.Sample(t.pos + float2(k, 0) * px).rgb, bar)) r = k;
            if (u > RADIUS && near(t.backbuffer.Sample(t.pos + float2(0, k) * px).rgb, bar)) u = k;   // origin bottom-left: up is +y
            if (w > RADIUS && near(t.backbuffer.Sample(t.pos - float2(0, k) * px).rgb, bar)) w = k;
        }
        float hx = min(l, r), hy = min(u, w);
        float3 c = color.rgb;
        if (u == 1) c += SHEEN;                                              // the top edge catches the light
        if (hx <= RADIUS && hy <= RADIUS) {
            float dist = length(float2(RADIUS - hx + 0.5, RADIUS - hy + 0.5));
            float cut = smoothstep(RADIUS - 0.75, RADIUS + 0.75, dist);
            c = lerp(c, bar, cut);
        }
        return float4(c, color.a);
    }

    if (near(color.rgb, bar)) {
        // a card above (the shadow falls down) or beside this bar pixel
        float s = 0;
        int S = int(SHADOW);
        for (int k = 1; k <= S; k++) {
            if (near(t.backbuffer.Sample(t.pos + float2(0, k) * px).rgb, card)) {
                float f = 1.0 - float(k) / (SHADOW + 1);
                s = max(s, f * f);
                break;
            }
        }
        for (int k = 1; k <= S / 2; k++) {
            float2 o = float2(k, 0) * px;
            if (near(t.backbuffer.Sample(t.pos + o).rgb, card) || near(t.backbuffer.Sample(t.pos - o).rgb, card)) {
                float f = 1.0 - float(k) / (SHADOW / 2 + 1);
                s = max(s, 0.45 * f * f);
                break;
            }
        }
        return float4(color.rgb * (1.0 - SHADOW_ALPHA * s), color.a);
    }
    return color;
}
