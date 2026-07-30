import * as THREE from "three";

const VERT = /* glsl */ `
  void main() {
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const FRAG = /* glsl */ `
  precision highp float;

  uniform vec2  uRes;
  uniform float uTime;
  uniform float uParticleTime;
  uniform float uAmp;
  uniform float uActivity;
  uniform float uParticlePulse;
  uniform float uBurst;
  uniform float uReveal;
  uniform float uBands[8];

  const float TAU = 6.28318530718;

  // =========================================================
  // UTILS
  // =========================================================

  vec3 mod289(vec3 x) {
    return x - floor(x * (1.0 / 289.0)) * 289.0;
  }

  vec2 mod289(vec2 x) {
    return x - floor(x * (1.0 / 289.0)) * 289.0;
  }

  vec3 permute(vec3 x) {
    return mod289(((x * 34.0) + 1.0) * x);
  }

  float snoise(vec2 v) {
    const vec4 C = vec4(
      0.211324865405187,
      0.366025403784439,
     -0.577350269189626,
      0.024390243902439
    );

    vec2 i = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);

    vec2 i1 = (x0.x > x0.y)
      ? vec2(1.0, 0.0)
      : vec2(0.0, 1.0);

    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;

    i = mod289(i);

    vec3 p = permute(
      permute(
        i.y + vec3(0.0, i1.y, 1.0)
      )
      + i.x
      + vec3(0.0, i1.x, 1.0)
    );

    vec3 m = max(
      0.5 - vec3(
        dot(x0, x0),
        dot(x12.xy, x12.xy),
        dot(x12.zw, x12.zw)
      ),
      0.0
    );

    m = m * m;
    m = m * m;

    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;

    m *= 1.79284291400159
      - 0.85373472095314
      * (a0 * a0 + h * h);

    vec3 g;

    g.x =
      a0.x * x0.x
      + h.x * x0.y;

    g.yz =
      a0.yz * x12.xz
      + h.yz * x12.yw;

    return 130.0 * dot(m, g);
  }

  float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;

    vec2 shift = vec2(100.0);

    mat2 rot = mat2(
      cos(0.5),
      sin(0.5),
      -sin(0.5),
      cos(0.5)
    );

    for (int i = 0; i < 5; i++) {
      value += amplitude * snoise(p);
      p = rot * p * 2.02 + shift;
      amplitude *= 0.48;
    }

    return value;
  }

  float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 34.45);

    return fract(p.x * p.y);
  }

  vec2 hash22(vec2 p) {
    float n = sin(
      dot(
        p,
        vec2(41.0, 289.0)
      )
    );

    return fract(
      vec2(262144.0, 32768.0) * n
    );
  }

  mat2 rotate2D(float angle) {
    float c = cos(angle);
    float s = sin(angle);

    return mat2(
      c,
      -s,
      s,
      c
    );
  }

  float easeOut(float x) {
    x = clamp(x, 0.0, 1.0);

    return 1.0 - pow(1.0 - x, 2.6);
  }

  float easeInOut(float x) {
    x = clamp(x, 0.0, 1.0);

    return x * x * (3.0 - 2.0 * x);
  }

  vec2 curlNoise2D(vec2 p) {
    float e = 0.06;

    float px1 = snoise(p + vec2(e, 0.0));
    float px2 = snoise(p - vec2(e, 0.0));

    float py1 = snoise(p + vec2(0.0, e));
    float py2 = snoise(p - vec2(0.0, e));

    float dx = (px1 - px2) / (2.0 * e);
    float dy = (py1 - py2) / (2.0 * e);

    vec2 curl = vec2(dy, -dx);

    return curl / (1.0 + length(curl));
  }

  float sampleAudioBand(float angle01) {
    float bandPosition = fract(angle01) * 8.0;
    float value = 0.0;

    for (int i = 0; i < 8; i++) {
      float idx = float(i);

      float d = abs(
        bandPosition - idx
      );

      d = min(d, 8.0 - d);

      float w = max(
        0.0,
        1.0 - d
      );

      value += uBands[i] * w;
    }

    return clamp(value, 0.0, 1.0);
  }

  // =========================================================
  // PARTICLE SHAPES
  // =========================================================

  float particleLayer(
    vec2 p,
    float scale,
    float seed,
    float density,
    float size,
    float twinkleSpeed
  ) {
    vec2 grid = p * scale;
    vec2 cell = floor(grid);
    vec2 local = fract(grid) - 0.5;

    vec2 rnd =
      (hash22(cell + seed) - 0.5)
      * 0.82;

    vec2 delta = local - rnd;

    float dist = length(delta);

    float enabled = step(
      1.0 - density,
      hash21(cell + seed * 7.31)
    );

    float core =
      1.0
      - smoothstep(
        size * 0.22,
        size,
        dist
      );

    float halo =
      1.0
      - smoothstep(
        size,
        size * 2.45,
        dist
      );

    float twinklePhase =
      hash21(cell + seed * 3.17)
      * TAU;

    float speedRnd = mix(
      0.65,
      1.35,
      hash21(cell + seed * 9.12)
    );

    float twinkle =
      0.80
      + 0.20
      * sin(
        uTime
        * twinkleSpeed
        * speedRnd
        + twinklePhase
      );

    return enabled
      * (core + halo * 0.10)
      * twinkle;
  }

  vec3 particleColors(
    float whiteMix,
    float purpleMix,
    float magentaMix,
    float intensity
  ) {
    vec3 deepPurple = vec3(
      0.48,
      0.16,
      0.95
    );

    vec3 violet = vec3(
      0.68,
      0.42,
      1.00
    );

    vec3 magenta = vec3(
      0.92,
      0.48,
      1.00
    );

    vec3 softLilac = vec3(
      0.82,
      0.72,
      1.00
    );

    vec3 whiteGlow = vec3(
      0.98,
      0.96,
      1.00
    );

    vec3 c = mix(
      deepPurple,
      violet,
      clamp(purpleMix, 0.0, 1.0)
    );

    c = mix(
      c,
      magenta,
      clamp(magentaMix, 0.0, 1.0)
    );

    c = mix(
      c,
      softLilac,
      0.15
    );

    c = mix(
      c,
      whiteGlow,
      clamp(whiteMix, 0.0, 1.0)
    );

    return c * intensity;
  }

  vec3 renderPulse(
    vec2 uv,
    vec2 dir,
    vec2 tangent,
    float sphereDist,
    float phase,
    float strength,
    float seed,
    float audioEnergy,
    float orbitAngle
  ) {
    float p = fract(phase);
    float t = easeOut(p);

    float appear = smoothstep(
      0.00,
      0.06,
      p
    );

    float fade =
      1.0
      - smoothstep(
        0.60,
        1.00,
        p
      );

    float ignitionWidth = mix(
      0.007,
      0.016,
      smoothstep(
        0.0,
        0.28,
        p
      )
    );

    float ignition = exp(
      -pow(
        (sphereDist - 0.004)
        / ignitionWidth,
        2.0
      )
    );

    ignition *=
      1.0
      - smoothstep(
        0.12,
        0.38,
        p
      );

    float shellCenter = mix(
      0.006,
      0.150,
      t
    );

    float shellWidth = mix(
      0.010,
      0.037,
      t
    );

    float shell = exp(
      -pow(
        (sphereDist - shellCenter)
        / shellWidth,
        2.0
      )
    );

    float sideBias = pow(
      abs(dir.x),
      1.25
    );

    float sideTransition = smoothstep(
      0.18,
      0.72,
      p
    );

    float angularShape = mix(
      1.0,
      0.34 + sideBias * 1.40,
      sideTransition
    );

    float breakup =
      0.55
      + 0.45
      * smoothstep(
        -0.45,
        0.60,
        snoise(
          dir * (2.1 + seed * 0.2)
          + vec2(
            uTime * 0.034,
            seed * 4.7
          )
        )
      );

    float envelope =
      ignition * 0.95
      + shell * angularShape;

    envelope *=
      appear
      * fade
      * strength
      * breakup;

    float innerMask = smoothstep(
      -0.007,
      0.001,
      sphereDist
    );

    float outerMask =
      1.0
      - smoothstep(
        0.165,
        0.230,
        sphereDist
      );

    envelope *=
      innerMask
      * outerMask;

    vec2 curl = curlNoise2D(
      uv * 4.6
      + vec2(
        seed * 7.3,
        uTime * 0.040
      )
    );

    float radialTravel =
      t
      * (
        0.022
        + strength * 0.010
      );

    float baseSwirl =
      sin(
        uTime * 0.34
        + length(uv) * 15.0
        + seed * 2.7
      )
      * (
        0.0012
        + t * 0.0048
      );

    float audioSwirl =
      sin(
        uTime * 1.15
        + seed * 3.1
        + length(uv) * 9.0
      )
      * audioEnergy
      * (
        0.0030
        + t * 0.0070
      );

    float swirl =
      baseSwirl
      + audioSwirl;

    float orbit =
      (
        0.0016
        + audioEnergy * 0.0060
      )
      * t;

    vec2 particleSpace =
      uv
      - dir * radialTravel
      + tangent * (swirl + orbit)
      + curl
      * (
        0.0028
        + t * 0.0058
      );

    particleSpace =
      rotate2D(
        orbitAngle
        * (
          0.6
          + t * 0.6
        )
      )
      * particleSpace;

    vec2 pA = particleSpace;

    vec2 pB =
      rotate2D(
        0.42
        + seed * 0.03
      )
      * (
        particleSpace
        + curl * 0.0017
      );

    vec2 pC =
      rotate2D(
        -0.58
        - seed * 0.02
      )
      * (
        particleSpace
        - curl * 0.0012
      );

    vec2 pD =
      rotate2D(
        0.93
        + seed * 0.01
      )
      * (
        particleSpace
        + tangent * 0.0010
      );

    float layerA = particleLayer(
      pA,
      520.0,
      seed + 1.1,
      0.44,
      0.145,
      0.72
    );

    float layerB = particleLayer(
      pB,
      820.0,
      seed + 7.2,
      0.30,
      0.124,
      0.90
    );

    float layerC = particleLayer(
      pC,
      1180.0,
      seed + 13.7,
      0.20,
      0.108,
      1.06
    );

    float layerD = particleLayer(
      pD,
      860.0,
      seed + 21.4,
      0.060,
      0.114,
      0.66
    );

    float leadingEdge = exp(
      -pow(
        (sphereDist - shellCenter)
        / max(
          shellWidth * 0.55,
          0.006
        ),
        2.0
      )
    );

    float powderA = fbm(
      particleSpace * 34.0
      + vec2(
        uTime * 0.060,
        -uTime * 0.045
      )
    );

    float powderB = snoise(
      particleSpace * 82.0
      + vec2(
        -uTime * 0.085,
        uTime * 0.065
      )
    );

    float powder = smoothstep(
      0.16,
      0.68,
      powderA * 0.76
      + powderB * 0.24
    );

    float purpleIntensity =
      (
        layerA * 0.85
        + layerB * 0.68
        + layerC * 0.46
      )
      * envelope;

    float whiteIntensity =
      layerD
      * envelope
      * (
        0.32
        + leadingEdge * 0.92
      );

    float powderIntensity =
      powder
      * envelope
      * 0.085;

    vec3 color = vec3(0.0);

    color += particleColors(
      0.00,
      0.55,
      0.15,
      purpleIntensity
      * (
        0.88
        + audioEnergy * 0.92
      )
    );

    color += particleColors(
      0.10,
      0.70,
      0.10,
      layerB
      * envelope
      * 0.16
    );

    color += particleColors(
      0.90,
      0.25,
      0.00,
      whiteIntensity
      * (
        0.60
        + audioEnergy * 0.58
      )
    );

    color += particleColors(
      0.10,
      0.45,
      0.05,
      powderIntensity
    );

    return color;
  }

  // =========================================================
  // INTRO RING
  // =========================================================

  vec3 renderIntroRing(
    vec2 uv,
    vec2 dir,
    vec2 tangent,
    float radius,
    float reveal
  ) {
    float ringActive =
      1.0
      - smoothstep(
        0.68,
        1.0,
        reveal
      );

    if (ringActive <= 0.001) {
      return vec3(0.0);
    }

    float p = smoothstep(
      0.02,
      0.85,
      reveal
    );

    float t = easeOut(p);

    float ringRadius = mix(
      0.02,
      0.98,
      t
    );

    float ringWidth = mix(
      0.010,
      0.070,
      t
    );

    float shell = exp(
      -pow(
        (radius - ringRadius)
        / ringWidth,
        2.0
      )
    );

    float leading = exp(
      -pow(
        (radius - ringRadius)
        / max(
          ringWidth * 0.5,
          0.006
        ),
        2.0
      )
    );

    float appear = smoothstep(
      0.00,
      0.08,
      reveal
    );

    float env =
      shell
      * appear
      * ringActive;

    vec2 curl = curlNoise2D(
      uv * 5.0
      + vec2(
        3.1,
        uTime * 0.05
      )
    );

    vec2 pspace =
      uv
      - dir * t * 0.020
      + tangent
      * sin(
        uTime * 0.6
        + radius * 20.0
      )
      * 0.0022
      + curl
      * (
        0.0030
        + t * 0.0040
      );

    float la = particleLayer(
      pspace,
      560.0,
      3.3,
      0.50,
      0.140,
      0.80
    );

    float lb = particleLayer(
      rotate2D(0.5) * pspace,
      900.0,
      9.1,
      0.34,
      0.120,
      1.00
    );

    float lw = particleLayer(
      rotate2D(-0.4) * pspace,
      820.0,
      15.2,
      0.10,
      0.110,
      0.70
    );

    vec3 c = vec3(0.0);

    c += particleColors(
      0.00,
      0.60,
      0.15,
      (
        la * 0.90
        + lb * 0.60
      )
      * env
      * 1.35
    );

    c += particleColors(
      0.92,
      0.20,
      0.00,
      lw
      * env
      * (
        0.5
        + leading * 1.0
      )
      * 1.20
    );

    c += vec3(
      0.55,
      0.34,
      1.00
    )
    * shell
    * appear
    * ringActive
    * 0.22;

    return c;
  }

  // =========================================================
  // MAIN
  // =========================================================

  void main() {
    vec2 uv =
      (
        gl_FragCoord.xy
        - 0.5 * uRes
      )
      / min(uRes.x, uRes.y);

    float radius = length(uv);

    vec2 dir =
      uv
      / max(radius, 1e-5);

    vec2 tangent = vec2(
      -dir.y,
      dir.x
    );

    float angle = atan(
      uv.y,
      uv.x
    );

    float angle01 =
      angle / TAU
      + 0.5;

    float band = sampleAudioBand(
      angle01
    );

    float bandSoft = smoothstep(
      0.0,
      1.0,
      band
    );

    float audioEnergy = clamp(
      uAmp * 0.72
      + bandSoft * 0.42
      + uParticlePulse * 0.40
      + uBurst * 0.35,
      0.0,
      1.0
    );

    float reveal = clamp(
      uReveal,
      0.0,
      1.0
    );

    float sphereGrow = easeInOut(
      smoothstep(
        0.10,
        0.92,
        reveal
      )
    );

    float sphereAlpha = smoothstep(
      0.08,
      0.55,
      reveal
    );

    float partReveal = smoothstep(
      0.30,
      1.00,
      reveal
    );

    float globalFade = smoothstep(
      0.00,
      0.10,
      reveal
    );

    // =======================================================
    // ORIGINAL SPHERE SIZE
    // =======================================================

    float sphereRadiusFull =
      0.180
      + uAmp * 0.006
      + uActivity * 0.003;

    float sphereRadius =
      sphereRadiusFull
      * mix(
        0.24,
        1.0,
        sphereGrow
      );

    float sphereDist =
      radius
      - sphereRadius;

    float sphereMask =
      1.0
      - smoothstep(
        -0.006,
        0.006,
        sphereDist
      );

    // =======================================================
    // ORIGINAL BACKGROUND
    // =======================================================

    vec3 bgCenter = vec3(
      0.070,
      0.022,
      0.160
    );

    vec3 bgMiddle = vec3(
      0.025,
      0.010,
      0.072
    );

    vec3 bgEdge = vec3(
      0.003,
      0.002,
      0.018
    );

    vec3 background = mix(
      bgCenter,
      bgMiddle,
      smoothstep(
        0.05,
        0.70,
        radius
      )
    );

    background = mix(
      background,
      bgEdge,
      smoothstep(
        0.50,
        1.26,
        radius
      )
    );

    float bgMist = exp(
      -radius
      * radius
      * 2.35
    );

    float bgNoise =
      0.84
      + 0.16
      * fbm(
        uv * 1.08
        + vec2(
          uTime * 0.016,
          -uTime * 0.013
        )
      );

    background +=
      vec3(
        0.095,
        0.030,
        0.220
      )
      * bgMist
      * bgNoise
      * 0.85;

    background +=
      vec3(
        0.040,
        0.016,
        0.115
      )
      * exp(-radius * 1.82)
      * 0.65;

    vec3 finalColor = background;

    // =======================================================
    // INTRO FLASH
    // =======================================================

    float ignitionFlash =
      exp(
        -radius
        * radius
        * 46.0
      )
      * (
        1.0
        - smoothstep(
          0.0,
          0.24,
          reveal
        )
      );

    finalColor +=
      vec3(
        0.90,
        0.76,
        1.00
      )
      * ignitionFlash
      * 0.85;

    float earlyBloom =
      exp(
        -radius
        * radius
        * 9.0
      )
      * (
        1.0
        - smoothstep(
          0.10,
          0.60,
          reveal
        )
      );

    finalColor +=
      vec3(
        0.42,
        0.22,
        0.92
      )
      * earlyBloom
      * 0.55;

    finalColor += renderIntroRing(
      uv,
      dir,
      tangent,
      radius,
      reveal
    );

    // =======================================================
    // PARTICLE ORIGIN
    // =======================================================

    float rimShape = fbm(
      dir * 1.38
      + vec2(
        uTime * 0.030,
        -uTime * 0.023
      )
    );

    float rimFine = snoise(
      dir * 3.90
      + vec2(
        -uTime * 0.042,
        uTime * 0.034
      )
    );

    float audioBulge =
      bandSoft
      * (
        0.0018
        + uAmp * 0.0060
      );

    float particleOrigin =
      sphereRadius
      + 0.004
      + rimShape
      * (
        0.0026
        + uParticlePulse * 0.0020
      )
      + rimFine * 0.0011
      + audioBulge;

    float particleDistance =
      radius
      - particleOrigin;

    // =======================================================
    // STEADY DUST
    // =======================================================

    vec2 steadyCurl = curlNoise2D(
      uv * 4.0
      + vec2(
        uTime * 0.028,
        -uTime * 0.023
      )
    );

    float orbitAngle =
      uTime * 0.12
      + uParticleTime * 0.05
      + audioEnergy
      * uTime
      * 0.55;

    float edgeFlow =
      sin(
        uTime * 0.28
        + radius * 14.0
      )
      * (
        0.0026
        + audioEnergy * 0.0050
      )
      + audioEnergy * 0.0034;

    vec2 steadySpace =
      uv
      - dir
      * uParticleTime
      * 0.0012
      + steadyCurl * 0.0034
      + tangent * edgeFlow;

    steadySpace =
      rotate2D(
        orbitAngle * 0.7
      )
      * steadySpace;

    float steadyRim = exp(
      -pow(
        (particleDistance - 0.007)
        / 0.013,
        2.0
      )
    );

    float steadyCloud = exp(
      -pow(
        (particleDistance - 0.024)
        / 0.032,
        2.0
      )
    );

    float steadyMask =
      smoothstep(
        -0.007,
        0.001,
        particleDistance
      )
      * (
        1.0
        - smoothstep(
          0.105,
          0.165,
          particleDistance
        )
      );

    float steadyEnvelope =
      (
        steadyRim * 0.15
        + steadyCloud * 0.040
      )
      * steadyMask
      * (
        0.55
        + uActivity * 0.42
        + uParticlePulse * 0.45
      )
      * partReveal;

    float steadyA = particleLayer(
      steadySpace,
      640.0,
      41.2,
      0.26,
      0.128,
      0.64
    );

    float steadyB = particleLayer(
      rotate2D(-0.48)
      * steadySpace,
      980.0,
      52.6,
      0.17,
      0.110,
      0.82
    );

    float steadyC = particleLayer(
      rotate2D(0.74)
      * steadySpace,
      820.0,
      73.1,
      0.028,
      0.112,
      0.58
    );

    finalColor += particleColors(
      0.00,
      0.55,
      0.05,
      steadyA
      * steadyEnvelope
      * 0.80
    );

    finalColor += particleColors(
      0.10,
      0.70,
      0.00,
      steadyB
      * steadyEnvelope
      * 0.52
    );

    finalColor += particleColors(
      0.88,
      0.15,
      0.00,
      steadyC
      * steadyEnvelope
      * 0.58
    );

    // =======================================================
    // PULSED PARTICLES
    // =======================================================

    float pulseSpeed =
      0.155
      + uParticlePulse * 0.085
      + uBurst * 0.060;

    float phaseA = fract(
      uParticleTime
      * pulseSpeed
      + 0.00
    );

    float phaseB = fract(
      uParticleTime
      * pulseSpeed
      + 0.32
    );

    float phaseC = fract(
      uParticleTime
      * pulseSpeed
      + 0.64
    );

    float strengthA =
      (
        0.42
        + uParticlePulse * 0.48
        + uBurst * 0.38
      )
      * partReveal;

    float strengthB =
      (
        0.34
        + uParticlePulse * 0.34
        + uBurst * 0.22
      )
      * partReveal;

    float strengthC =
      (
        0.28
        + uParticlePulse * 0.26
        + uBurst * 0.16
      )
      * partReveal;

    finalColor += renderPulse(
      uv,
      dir,
      tangent,
      particleDistance,
      phaseA,
      strengthA,
      1.0,
      audioEnergy,
      orbitAngle
    );

    finalColor += renderPulse(
      uv,
      dir,
      tangent,
      particleDistance,
      phaseB,
      strengthB,
      2.0,
      audioEnergy,
      orbitAngle
    );

    finalColor += renderPulse(
      uv,
      dir,
      tangent,
      particleDistance,
      phaseC,
      strengthC,
      3.0,
      audioEnergy,
      orbitAngle
    );

    // =======================================================
    // PARTICLE RIM
    // =======================================================

    float particleRimGlow =
      exp(
        -abs(particleDistance)
        * 52.0
      )
      * (
        1.0
        - sphereMask
      )
      * (
        0.040
        + uParticlePulse * 0.110
        + uBurst * 0.060
      )
      * partReveal;

    finalColor +=
      vec3(
        0.66,
        0.42,
        1.00
      )
      * particleRimGlow;

    // =======================================================
    // UPDATED SPHERE VISUAL
    // =======================================================

    float normalZ = sqrt(
      max(
        1.0
        - (
          radius * radius
        )
        / (
          sphereRadius
          * sphereRadius
        ),
        0.0
      )
    );

    vec2 sphereUv =
      uv
      / sphereRadius;

    float y01 = clamp(
      sphereUv.y * 0.5
      + 0.5,
      0.0,
      1.0
    );

    vec3 sphereBottom = vec3(
      0.310,
      0.075,
      0.635
    );

    vec3 sphereMiddle = vec3(
      0.455,
      0.175,
      0.800
    );

    vec3 sphereTop = vec3(
      0.520,
      0.255,
      0.835
    );

    vec3 sphereColor = mix(
      sphereBottom,
      sphereMiddle,
      smoothstep(
        0.03,
        0.63,
        y01
      )
    );

    sphereColor = mix(
      sphereColor,
      sphereTop,
      smoothstep(
        0.54,
        1.00,
        y01
      )
      * 0.58
    );

    // Большое мягкое пятно выше центра.
    vec2 mainLightUv =
      (
        sphereUv
        - vec2(
          0.055,
          0.405
        )
      )
      * vec2(
        0.82,
        1.02
      );

    float mainLight = exp(
      -dot(
        mainLightUv,
        mainLightUv
      )
      * 1.42
    );

    // Рассеянный свет сверху.
    vec2 capLightUv =
      (
        sphereUv
        - vec2(
          0.025,
          0.720
        )
      )
      * vec2(
        1.03,
        1.72
      );

    float capLight = exp(
      -dot(
        capLightUv,
        capLightUv
      )
      * 1.55
    );

    sphereColor +=
      vec3(
        0.135,
        0.140,
        0.130
      )
      * mainLight
      * 0.78;

    sphereColor +=
      vec3(
        0.100,
        0.100,
        0.110
      )
      * capLight
      * 0.45;

    float lowerShadow =
      1.0
      - smoothstep(
        -0.98,
        0.20,
        sphereUv.y
      );

    float leftShadow =
      1.0
      - smoothstep(
        -1.02,
        0.22,
        sphereUv.x
      );

    sphereColor *=
      1.0
      - lowerShadow * 0.090;

    sphereColor *=
      1.0
      - leftShadow
      * lowerShadow
      * 0.030;

    float edgeDarkening = pow(
      1.0 - normalZ,
      1.28
    );

    sphereColor *=
      1.0
      - edgeDarkening * 0.230;

    float leftSilhouette =
      1.0
      - smoothstep(
        -1.02,
        -0.15,
        sphereUv.x
      );

    sphereColor *=
      1.0
      - leftSilhouette * 0.140;

    sphereColor +=
      vec3(
        0.045,
        0.050,
        0.025
      )
      * pow(
        normalZ,
        0.62
      );

    float bodyVariation = fbm(
      sphereUv * 1.18
      + vec2(
        -0.14,
        0.21
      )
    );

    sphereColor +=
      vec3(
        0.028,
        0.012,
        0.052
      )
      * bodyVariation
      * 0.075;

    sphereColor *=
      1.0
      + uAmp * 0.022;

    sphereColor +=
      vec3(
        0.080,
        0.045,
        0.125
      )
      * (
        1.0
        - sphereAlpha
      )
      * 0.14;

    finalColor = mix(
      finalColor,
      sphereColor,
      sphereMask
      * sphereAlpha
    );

    // =======================================================
    // UPDATED SPHERE GLOW
    // =======================================================

    float outsideDistance = max(
      sphereDist,
      0.0
    );

    float wideGlow =
      exp(
        -outsideDistance
        * 13.5
      )
      * (
        1.0
        - sphereMask
      );

    float nearGlow =
      exp(
        -outsideDistance
        * 39.0
      )
      * (
        1.0
        - sphereMask
      );

    float glowDirection = mix(
      0.72,
      1.16,
      smoothstep(
        -0.65,
        0.82,
        dir.y
      )
    );

    vec3 wideGlowColor = vec3(
      0.245,
      0.095,
      0.465
    );

    vec3 nearGlowColor = vec3(
      0.470,
      0.225,
      0.710
    );

    finalColor +=
      wideGlowColor
      * wideGlow
      * glowDirection
      * (
        0.115
        + uAmp * 0.012
        + uParticlePulse * 0.014
      )
      * sphereAlpha;

    finalColor +=
      nearGlowColor
      * nearGlow
      * glowDirection
      * (
        0.070
        + uAmp * 0.010
        + uParticlePulse * 0.010
      )
      * sphereAlpha;

    // =======================================================
    // FINAL COLOR
    // =======================================================

    finalColor *=
      1.0
      - 0.26
      * smoothstep(
        0.62,
        1.32,
        radius
      );

    finalColor *= globalFade;

    finalColor = pow(
      max(
        finalColor,
        0.0
      ),
      vec3(0.97)
    );

    gl_FragColor = vec4(
      finalColor,
      1.0
    );
  }
`;

export class Visualizer {
    constructor(canvas) {
        this.canvas = canvas;

        this.amp = 0;
        this.ampTarget = 0;
        this.prevAmp = 0;

        this.activity = 0.15;
        this.currentState = "idle";

        this.particleTime = 0;
        this.particlePulse = 0;

        this.burst = 0;
        this.burstCooldown = 0;

        this.introDuration = 1.7;
        this.introTime = 0;
        this.reveal = 0;

        this.renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: false,
            powerPreference: "high-performance",
        });

        this.renderer.setPixelRatio(
            Math.min(
                devicePixelRatio,
                2
            )
        );

        this.scene = new THREE.Scene();

        this.camera = new THREE.OrthographicCamera(
            -1,
            1,
            1,
            -1,
            0,
            1
        );

        this.bands = new Float32Array(8);
        this.bandTargets = new Float32Array(8);

        this.uniforms = {
            uRes: {
                value: new THREE.Vector2(1, 1),
            },

            uTime: {
                value: 0,
            },

            uParticleTime: {
                value: 0,
            },

            uAmp: {
                value: 0,
            },

            uActivity: {
                value: 0.15,
            },

            uParticlePulse: {
                value: 0,
            },

            uBurst: {
                value: 0,
            },

            uReveal: {
                value: 0,
            },

            uBands: {
                value: this.bands,
            },
        };

        const geometry = new THREE.PlaneGeometry(
            2,
            2
        );

        const material = new THREE.ShaderMaterial({
            uniforms: this.uniforms,
            vertexShader: VERT,
            fragmentShader: FRAG,
        });

        const quad = new THREE.Mesh(
            geometry,
            material
        );

        this.scene.add(quad);

        this.resize();

        addEventListener(
            "resize",
            () => this.resize()
        );

        this.clock = new THREE.Clock();

        this._loop();
    }

    resize() {
        const width = innerWidth;
        const height = innerHeight;

        this.renderer.setSize(
            width,
            height,
            false
        );

        const pixelRatio =
            this.renderer.getPixelRatio();

        this.uniforms.uRes.value.set(
            width * pixelRatio,
            height * pixelRatio
        );
    }

    restartIntro() {
        this.introTime = 0;
        this.reveal = 0;
    }

    setAmplitude(amplitude) {
        this.ampTarget = Math.min(
            1,
            Math.max(
                0,
                amplitude
            )
            * 1.30
        );
    }

    setBands(bands) {
        for (let i = 0; i < 8; i++) {
            this.bandTargets[i] = Math.min(
                1,
                Math.max(
                    0,
                    bands[i] ?? 0
                )
            );
        }
    }

    setState(state) {
        const prevState = this.currentState;

        this.currentState = state;

        this.activity = {
            idle: 0.10,
            listening: 0.30,
            thinking: 0.58,
            speaking: 0.50,
        }[state] ?? 0.15;

        if (
            state === "speaking"
            && prevState !== "speaking"
        ) {
            this.burst = 1.0;
            this.burstCooldown = 0.45;
        }
    }

    _loop() {
        requestAnimationFrame(
            () => this._loop()
        );

        const dt = Math.min(
            this.clock.getDelta(),
            0.05
        );

        // =====================================================
        // INTRO
        // =====================================================

        if (
            this.introTime
            < this.introDuration
        ) {
            this.introTime = Math.min(
                this.introDuration,
                this.introTime + dt
            );
        }

        this.reveal =
            this.introTime
            / this.introDuration;

        // =====================================================
        // AMPLITUDE
        // =====================================================

        const ampRate =
            this.ampTarget > this.amp
                ? 16.0
                : 4.6;

        const ampBlend =
            1.0
            - Math.exp(
                -ampRate * dt
            );

        this.amp +=
            (
                this.ampTarget
                - this.amp
            )
            * ampBlend;

        this.ampTarget *= Math.exp(
            -9.6 * dt
        );

        // =====================================================
        // BANDS
        // =====================================================

        let bandEnergy = 0;

        for (let i = 0; i < 8; i++) {
            const bandRate =
                this.bandTargets[i]
                > this.bands[i]
                    ? 16.0
                    : 4.8;

            const bandBlend =
                1.0
                - Math.exp(
                    -bandRate * dt
                );

            this.bands[i] +=
                (
                    this.bandTargets[i]
                    - this.bands[i]
                )
                * bandBlend;

            this.bandTargets[i] *= Math.exp(
                -9.8 * dt
            );

            bandEnergy += this.bands[i];
        }

        bandEnergy /= 8.0;

        // =====================================================
        // PARTICLE PULSE
        // =====================================================

        const particleTarget = Math.min(
            1,
            this.amp * 0.98
            + bandEnergy * 0.76
        );

        const pulseRate =
            particleTarget
            > this.particlePulse
                ? 9.0
                : 2.4;

        const pulseBlend =
            1.0
            - Math.exp(
                -pulseRate * dt
            );

        this.particlePulse +=
            (
                particleTarget
                - this.particlePulse
            )
            * pulseBlend;

        // =====================================================
        // VOICE BURST
        // =====================================================

        const ampRise = Math.max(
            0,
            this.amp - this.prevAmp
        );

        this.burstCooldown = Math.max(
            0,
            this.burstCooldown - dt
        );

        const voiceOnset =
            ampRise > 0.025
            && this.amp > 0.10
            && this.burstCooldown <= 0;

        if (voiceOnset) {
            this.burst = 1.0;
            this.burstCooldown = 0.42;
        }

        this.prevAmp = this.amp;

        this.burst *= Math.exp(
            -2.6 * dt
        );

        // =====================================================
        // PARTICLE TIME
        // =====================================================

        const particleSpeed =
            0.22
            + this.activity * 0.045
            + this.particlePulse * 0.18
            + bandEnergy * 0.07
            + this.burst * 0.10;

        this.particleTime +=
            dt
            * particleSpeed;

        // =====================================================
        // UNIFORMS
        // =====================================================

        this.uniforms.uTime.value += dt;

        this.uniforms.uParticleTime.value =
            this.particleTime;

        this.uniforms.uAmp.value =
            this.amp;

        this.uniforms.uParticlePulse.value =
            this.particlePulse;

        this.uniforms.uBurst.value =
            this.burst;

        this.uniforms.uReveal.value =
            this.reveal;

        const activityBlend =
            1.0
            - Math.exp(
                -4.0 * dt
            );

        this.uniforms.uActivity.value +=
            (
                this.activity
                - this.uniforms.uActivity.value
            )
            * activityBlend;

        this.renderer.render(
            this.scene,
            this.camera
        );
    }
}