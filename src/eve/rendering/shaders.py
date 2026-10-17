"""GLSL 1.20 shaders (runs on macOS legacy GL 2.1 contexts, Windows and Linux alike).

Soft studio lighting in view space: key light upper-left, cool fill from the right, a
back light for separation, hemisphere ambient, wrapped diffuse, Blinn-Phong highlights and
a fresnel rim. Lighting is computed in linear space and gamma-encoded at the end.
Output is premultiplied alpha so the transparent desktop window composites correctly.
"""

VERTEX = """
#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat3 p3d_NormalMatrix;
attribute vec4 p3d_Vertex;
attribute vec3 p3d_Normal;
attribute vec4 p3d_Color;
varying vec3 v_normal;
varying vec3 v_pos;
varying vec4 v_color;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_pos = (p3d_ModelViewMatrix * p3d_Vertex).xyz;
    v_normal = normalize(p3d_NormalMatrix * p3d_Normal);
    v_color = p3d_Color;
}
"""

FRAGMENT = """
#version 120
uniform vec3 u_base;      // linear albedo
uniform vec4 u_params;    // x specular, y shininess, z rim, w diffuse wrap
uniform vec3 u_emission;  // linear emission
uniform float u_unlit;    // 1 = emissive only
uniform float u_alpha;    // overall opacity (unlit translucent parts)
varying vec3 v_normal;
varying vec3 v_pos;
varying vec4 v_color;

vec3 encode(vec3 c) {
    c = c / (1.0 + 0.12 * c);               // gentle highlight roll-off
    return pow(clamp(c, 0.0, 1.0), vec3(1.0 / 2.2));
}

float wrapped(vec3 n, vec3 l, float w) {
    return max((dot(n, l) + w) / (1.0 + w), 0.0);
}

void main() {
    if (u_unlit > 0.5) {
        float a = clamp(v_color.a * u_alpha, 0.0, 1.0);
        gl_FragColor = vec4(encode(u_emission) * a, a);
        return;
    }
    vec3 n = normalize(v_normal);
    vec3 v = normalize(-v_pos);
    if (dot(n, v) < -0.2) n = -n;

    vec3 key_dir = normalize(vec3(-0.55, 0.65, 0.55));
    vec3 fill_dir = normalize(vec3(0.85, 0.05, 0.45));
    vec3 back_dir = normalize(vec3(0.25, 0.55, -0.8));
    vec3 key_col = vec3(1.0, 0.97, 0.93) * 1.05;
    vec3 fill_col = vec3(0.55, 0.63, 0.80) * 0.42;
    vec3 back_col = vec3(0.70, 0.80, 1.00) * 0.55;

    float hemi = n.y * 0.5 + 0.5;
    vec3 ambient = mix(vec3(0.16, 0.15, 0.15), vec3(0.36, 0.39, 0.46), hemi);

    float w = u_params.w;
    vec3 diffuse = ambient
        + key_col * wrapped(n, key_dir, w)
        + fill_col * wrapped(n, fill_dir, w)
        + back_col * wrapped(n, back_dir, 0.0) * 0.4;

    float shin = u_params.y;
    vec3 spec = key_col * pow(max(dot(n, normalize(key_dir + v)), 0.0), shin)
              + fill_col * 0.6 * pow(max(dot(n, normalize(fill_dir + v)), 0.0), shin * 0.5);
    float fres = pow(1.0 - max(dot(n, v), 0.0), 3.0);
    vec3 rim = vec3(0.70, 0.82, 1.0) * fres * u_params.z;

    vec3 color = u_base * diffuse + spec * u_params.x + rim + u_emission;
    gl_FragColor = vec4(encode(color), 1.0);
}
"""
