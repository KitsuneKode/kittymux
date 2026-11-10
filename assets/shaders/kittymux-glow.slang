#language slang 2026
// kittymux glow: on a tab change, the newly active card lights up and settles. Runs only while kitty's
// tab-change animation plays. A fill pixel (progress, waiting, error) lights the same way, so a card that is
// all fill still glows.
import kitty_custom_shader_types;

static const float CARD_W = 0.15;
static const float GLOW = 0.07;
static const float EPS = 0.006;
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

public float4
fragment_main(float4 color, KittyTextures t, KittyCustomShaderData d) {
    float4 area = d.central_area;
    if (all(t.pos >= area.xy) && all(t.pos <= area.xy + area.zw)) return color;
    float3 card = theme_blend(d, CARD_W);
    float3 f0 = lin(FILL0), f1 = lin(FILL1), f2 = lin(FILL2), f3 = lin(FILL3);
    float3 f4 = lin(FILL4), f5 = lin(FILL5), f6 = lin(FILL6), f7 = lin(FILL7);
    bool on_card = near(color.rgb, card)
        || (FILL0.x >= 0.0 && near(color.rgb, f0)) || (FILL1.x >= 0.0 && near(color.rgb, f1))
        || (FILL2.x >= 0.0 && near(color.rgb, f2)) || (FILL3.x >= 0.0 && near(color.rgb, f3))
        || (FILL4.x >= 0.0 && near(color.rgb, f4)) || (FILL5.x >= 0.0 && near(color.rgb, f5))
        || (FILL6.x >= 0.0 && near(color.rgb, f6)) || (FILL7.x >= 0.0 && near(color.rgb, f7));
    float3 c = color.rgb;
    if (on_card) c += GLOW * (1.0 - t.animation_progress);
    return float4(c, color.a);
}
