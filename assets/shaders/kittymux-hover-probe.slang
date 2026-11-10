#language slang 2026
// Finds the tab row under the pointer and writes it into one texel the cards shader samples,
// (0.0025, 0.005): (y0, y1, valid, 1) in UV, origin at the bottom-left.
// Every other pixel returns immediately. A row is the run between bar-coloured gaps (the blank line
// kittymux leaves between tabs). Static: kitty redraws it when the pointer moves, and not while it is still.
import kitty_custom_shader_types;

static const float BAR_W = 0.05;
static const float CARD_W = 0.15;
static const float EPS = 0.006;
static const float CELL_H = 0;          // px; 0 guesses 20. The geninclude sets the live cell height.
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

bool is_fill(float3 c, float3 f0, float3 f1, float3 f2, float3 f3, float3 f4, float3 f5, float3 f6, float3 f7,
             bool u0, bool u1, bool u2, bool u3, bool u4, bool u5, bool u6, bool u7) {
    return (u0 && near(c, f0)) || (u1 && near(c, f1)) || (u2 && near(c, f2)) || (u3 && near(c, f3))
        || (u4 && near(c, f4)) || (u5 && near(c, f5)) || (u6 && near(c, f6)) || (u7 && near(c, f7));
}

// The vertical bar, in UV. (-1, -1) when the bar is horizontal or hidden: hover is a vertical-bar effect.
float2 bar_span(KittyCustomShaderData d) {
    float4 a = d.central_area;
    float left = a.x;
    float right = 1.0 - (a.x + a.z);
    if (left >= 0.02 && left >= right) return float2(0.0, left);
    if (right >= 0.02) return float2(a.x + a.z, 1.0);
    return float2(-1.0, -1.0);
}

// 0 = a blank gap row (entirely the bar colour, ignoring the divider), 1 = the active card or a progress
// fill, 2 = some other row. One glyph is enough to keep a line from being a gap.
int row_kind(float y, float x0, float x1, float3 bar, float3 card, KittyTextures t,
             float3 f0, float3 f1, float3 f2, float3 f3, float3 f4, float3 f5, float3 f6, float3 f7,
             bool u0, bool u1, bool u2, bool u3, bool u4, bool u5, bool u6, bool u7) {
    int nbar = 0;
    int ncard = 0;
    float xR = x0 + (x1 - x0) * 0.82;
    for (int i = 0; i < 16; i++) {
        float x = lerp(x0, xR, (float(i) + 0.5) / 16.0);
        float3 c = t.backbuffer.Sample(float2(x, y)).rgb;
        if (near(c, bar)) nbar++;
        else if (near(c, card) || is_fill(c, f0, f1, f2, f3, f4, f5, f6, f7, u0, u1, u2, u3, u4, u5, u6, u7)) ncard++;
    }
    if (nbar == 16) return 0;
    if (ncard >= 3) return 1;
    return 2;
}

public float4
fragment_main(float4 color, KittyTextures t, KittyCustomShaderData d) {
    // Only the texel the cards shader samples does the scan.
    float2 texel = 1.0 / float2(d.viewport_size_pixels);
    if (abs(t.pos.x - 0.0025) >= texel.x * 1.25 || abs(t.pos.y - 0.005) >= texel.y * 1.25)
        return float4(0.0, 0.0, 0.0, 1.0);

    float3 bar = theme_blend(d, BAR_W);
    float3 card = theme_blend(d, CARD_W);
    float3 f0 = lin(FILL0), f1 = lin(FILL1), f2 = lin(FILL2), f3 = lin(FILL3);
    float3 f4 = lin(FILL4), f5 = lin(FILL5), f6 = lin(FILL6), f7 = lin(FILL7);
    bool u0 = FILL0.x >= 0.0, u1 = FILL1.x >= 0.0, u2 = FILL2.x >= 0.0, u3 = FILL3.x >= 0.0;
    bool u4 = FILL4.x >= 0.0, u5 = FILL5.x >= 0.0, u6 = FILL6.x >= 0.0, u7 = FILL7.x >= 0.0;
    float cell_px = CELL_H > 2.0 ? CELL_H : 20.0;
    float cell = cell_px / float(d.viewport_size_pixels.y);
    float2 span = bar_span(d);
    float2 m = d.mouse_pos.xy;
    bool mouse = d.mouse_pointer_hidden == 0.0 && all(m >= float2(0.0)) && all(m <= float2(1.0))
        && span.x >= 0.0 && m.x >= span.x && m.x <= span.y;
    float y0 = 0.0, y1 = 0.0;
    float valid = 0.0;
    if (mouse) {
        int here = row_kind(m.y, span.x, span.y, bar, card, t, f0, f1, f2, f3, f4, f5, f6, f7, u0, u1, u2, u3, u4, u5, u6, u7);
        // a gap is not a row, and the active card already reads as the selection
        if (here == 2) {
            // a real gap is a blank cell. The padding between a title and its subtitle is shorter, so it stays
            // inside the row. Stop only after three quarters of a cell of bar, then step back over that run.
            float fine = cell * 0.2;
            y0 = m.y;
            y1 = m.y;
            int up = 0;
            int down = 0;
            for (int i = 1; i <= 24; i++) {
                float y = m.y + float(i) * fine;
                if (y > 0.995) { y1 = 0.995; break; }
                int k = row_kind(y, span.x, span.y, bar, card, t, f0, f1, f2, f3, f4, f5, f6, f7, u0, u1, u2, u3, u4, u5, u6, u7);
                if (k == 0) up++; else up = 0;
                y1 = y;
                if (float(up) * fine >= cell * 0.75) { y1 = y - fine * float(up); break; }
                if (float(i) * fine > cell * 4.0) break;
            }
            for (int i = 1; i <= 24; i++) {
                float y = m.y - float(i) * fine;
                if (y < 0.005) { y0 = 0.005; break; }
                int k = row_kind(y, span.x, span.y, bar, card, t, f0, f1, f2, f3, f4, f5, f6, f7, u0, u1, u2, u3, u4, u5, u6, u7);
                if (k == 0) down++; else down = 0;
                y0 = y;
                if (float(down) * fine >= cell * 0.75) { y0 = y + fine * float(down); break; }
                if (float(i) * fine > cell * 4.0) break;
            }
            y1 = min(y1 + cell * 0.15, 0.995);
            y0 = max(y0 - cell * 0.15, 0.005);
            if (y1 > y0 + cell * 0.45) valid = 1.0;
        }
    }
    return float4(y0, y1, valid, 1.0);
}
