import * as THREE from "three";

/**
 * Instanced "neon glass" material for the hexagonal towers.
 *
 * Per-instance attributes: aHeat (hotspot 0..1), aCoverage (0..1, or -1 when unknown),
 * aTest (1 for test files), aHue (module hue). Colors above 1.0 are intentional: they are what
 * the bloom pass picks up.
 */
export function createBuildingMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    fog: true,
    uniforms: THREE.UniformsUtils.merge([
      THREE.UniformsLib.fog,
      {
        uTime: { value: 0 },
        uLayer: { value: 1 }, // 0 = structure, 1 = debt
        uSelected: { value: -1 },
        uHovered: { value: -1 },
      },
    ]),
    vertexShader: /* glsl */ `
      attribute float aHeat;
      attribute float aCoverage;
      attribute float aTest;
      attribute float aHue;
      uniform float uSelected;
      uniform float uHovered;
      varying vec2 vUv;
      varying vec3 vNormal;
      varying float vIsCap;
      varying vec3 vViewDir;
      varying float vWorldY;
      varying float vBaseY;
      varying float vTopY;
      varying float vHeat;
      varying float vCoverage;
      varying float vTest;
      varying float vHue;
      varying float vState;
      varying float vSeed;
      #include <fog_pars_vertex>

      void main() {
        vUv = uv;
        mat4 model = modelMatrix * instanceMatrix;
        vec4 worldPosition = model * vec4(position, 1.0);
        // Instances are scaled non-uniformly (tall and thin), so normals need the inverse scale;
        // the plain model matrix would tilt the side normals towards vertical.
        vec3 scale = vec3(length(model[0].xyz), length(model[1].xyz), length(model[2].xyz));
        vNormal = normalize(mat3(model) * (normal / (scale * scale)));
        vIsCap = abs(normal.y) > 0.9 ? 1.0 : 0.0;
        vViewDir = normalize(cameraPosition - worldPosition.xyz);
        vWorldY = worldPosition.y;
        vBaseY = (model * vec4(0.0, 0.0, 0.0, 1.0)).y;
        vTopY = (model * vec4(0.0, 1.0, 0.0, 1.0)).y;
        vHeat = aHeat;
        vCoverage = aCoverage;
        vTest = aTest;
        vHue = aHue;
        float id = float(gl_InstanceID);
        vState = id == uSelected ? 2.0 : (id == uHovered ? 1.0 : 0.0);
        vSeed = fract(sin(id * 12.9898) * 43758.5453);
        vec4 mvPosition = viewMatrix * worldPosition;
        gl_Position = projectionMatrix * mvPosition;
        #include <fog_vertex>
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform float uLayer;
      varying vec2 vUv;
      varying vec3 vNormal;
      varying float vIsCap;
      varying vec3 vViewDir;
      varying float vWorldY;
      varying float vBaseY;
      varying float vTopY;
      varying float vHeat;
      varying float vCoverage;
      varying float vTest;
      varying float vHue;
      varying float vState;
      varying float vSeed;
      #include <fog_pars_fragment>

      const float FLOOR_HEIGHT = 0.9;

      vec3 hsv2rgb(vec3 c) {
        vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
        return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
      }

      vec3 heatColor(float h) {
        vec3 cool = vec3(0.10, 0.85, 1.00);
        vec3 warm = vec3(1.00, 0.55, 0.10);
        vec3 hot = vec3(1.00, 0.10, 0.20);
        vec3 c = mix(cool, warm, smoothstep(0.0, 0.35, h));
        return mix(c, hot, smoothstep(0.35, 0.9, h));
      }

      void main() {
        vec3 n = normalize(vNormal);
        bool isCap = vIsCap > 0.5;

        // Glowing edges: the six vertical edges and the roof rim.
        float edge;
        if (isCap) {
          edge = smoothstep(0.74, 0.84, length(vUv - 0.5) * 2.0);
        } else {
          float u = fract(vUv.x * 6.0);
          float vertical = 1.0 - smoothstep(0.0, 0.03, min(u, 1.0 - u));
          float rim = smoothstep(0.975, 1.0, vUv.y);
          edge = max(vertical, rim);
        }

        // One luminous band per "floor", so height can be read as stacked floors.
        float floorPos = fract((vWorldY - vBaseY) / FLOOR_HEIGHT);
        float bands = isCap ? 0.0 : 1.0 - smoothstep(0.015, 0.05, abs(floorPos - 0.5));

        vec3 accent = uLayer > 0.5
          ? heatColor(vHeat)
          : hsv2rgb(vec3(vHue, 0.75, 1.0));
        float intensity = 1.0;

        if (uLayer > 0.5) {
          // Hotspots pulse, faster and stronger as the score grows.
          intensity *= 1.0 + vHeat * 0.7 * sin(uTime * (1.2 + vHeat * 5.0) + vSeed * 6.28);
          // Poorly covered files lose their edge lights ("switched off").
          if (vCoverage >= 0.0) edge *= mix(0.15, 1.0, smoothstep(0.2, 0.6, vCoverage));
        }
        if (vTest > 0.5) {
          accent = mix(accent, vec3(0.62, 0.50, 1.0), 0.65);
          intensity *= 0.55;
        }

        float fresnel = pow(1.0 - max(dot(n, normalize(vViewDir)), 0.0), 3.0);
        vec3 body = vec3(0.015, 0.03, 0.055) + accent * (0.04 + 0.08 * vHeat * uLayer);
        vec3 color = body + accent * fresnel * 0.45;
        color += accent * (edge * 2.6 + bands * 0.55) * intensity;

        if (vState > 0.5) {
          float boost = vState > 1.5 ? 1.8 : 1.35;
          color *= boost;
          if (vState > 1.5) {
            // Holographic scan climbing the selected tower.
            float scanY = mix(vBaseY, vTopY, fract(uTime * 0.35));
            float scan = 1.0 - smoothstep(0.0, 0.18, abs(vWorldY - scanY));
            color += vec3(0.6, 1.0, 1.0) * scan * 2.5;
          }
        }

        gl_FragColor = vec4(color, 1.0);
        #include <fog_fragment>
      }
    `,
  });
}
