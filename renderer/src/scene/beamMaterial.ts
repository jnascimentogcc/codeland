import * as THREE from "three";

/**
 * Additive light beam through the core of each ring tower. It carries the same accent as the
 * rings (heat or module hue) as energy pulses flowing upwards, faster for hotter files; it is the
 * slot reserved for agent activity in phase 2.
 */
export function createBeamMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uLayer: { value: 1 },
      uSelected: { value: -1 },
      uHovered: { value: -1 },
    },
    vertexShader: /* glsl */ `
      attribute float aHeat;
      attribute float aTest;
      attribute float aHue;
      uniform float uSelected;
      uniform float uHovered;
      varying float vHeight;
      varying float vLocalY;
      varying float vHeat;
      varying float vTest;
      varying float vHue;
      varying float vState;

      void main() {
        vLocalY = position.y;
        vHeight = length(instanceMatrix[1].xyz);
        vHeat = aHeat;
        vTest = aTest;
        vHue = aHue;
        float id = float(gl_InstanceID);
        vState = id == uSelected ? 2.0 : (id == uHovered ? 1.0 : 0.0);
        gl_Position = projectionMatrix * viewMatrix * modelMatrix * instanceMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform float uLayer;
      varying float vHeight;
      varying float vLocalY;
      varying float vHeat;
      varying float vTest;
      varying float vHue;
      varying float vState;

      vec3 hsv2rgb(vec3 c) {
        vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
        return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
      }

      vec3 heatColor(float h) {
        vec3 c = mix(vec3(0.10, 0.85, 1.00), vec3(1.00, 0.55, 0.10), smoothstep(0.0, 0.35, h));
        return mix(c, vec3(1.00, 0.10, 0.20), smoothstep(0.35, 0.9, h));
      }

      void main() {
        vec3 accent = uLayer > 0.5 ? heatColor(vHeat) : hsv2rgb(vec3(vHue, 0.6, 1.0));
        float heat = uLayer > 0.5 ? vHeat : 0.0;
        // Energy pulses travelling up, in world units so all towers share the same rhythm.
        float y = vLocalY * vHeight;
        float pulse = pow(0.5 + 0.5 * sin(y * 2.2 - uTime * (1.5 + heat * 6.0)), 6.0);
        // Fade out at the very bottom and above the roof.
        float fade = smoothstep(0.0, 0.08, vLocalY) * (1.0 - smoothstep(0.92, 1.0, vLocalY));
        float strength = (0.55 + heat * 1.2 + pulse * (0.8 + heat * 1.6)) * fade;
        if (vTest > 0.5) strength *= 0.4;
        if (vState > 0.5) strength *= vState > 1.5 ? 2.2 : 1.5;
        gl_FragColor = vec4(accent * strength, 1.0);
      }
    `,
  });
}
