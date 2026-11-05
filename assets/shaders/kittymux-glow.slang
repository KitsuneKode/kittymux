#language slang 2026
// kittymux glow: on a tab change, the newly active card lights up and settles back (animation_progress 0 → 1).
// Runs only while kitty's tab-change animation plays; it touches only CARD pixels in the tab bar.
import kitty_custom_shader_types;

static const float CARD_W = 0.15;   // the active card = surface_hi = blend(fg, bg, 0.15)
static const float GLOW = 0.07;     // linear light added at the start
static const float EPS = 0.006;

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

public float4
fragment_main(float4 color, KittyTextures t, KittyCustomShaderData d) {
    float4 a = d.central_area;
    if (all(t.pos >= a.xy) && all(t.pos <= a.xy + a.zw)) return color;
    float3 card = theme_blend(d, CARD_W);
    if (distance(color.rgb, card) >= EPS) return color;
    return float4(color.rgb + GLOW * (1.0 - t.animation_progress), color.a);
}
