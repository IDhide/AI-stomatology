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
  uniform float uReveal;      // 0..1 intro reveal
  uniform float uBands[8];

  const float TAU = 6.28318530718;

  // =========================================================
  // UTILS
  // =========================================================

  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec3 permute(vec3 x) { return mod289(((x * 34.0) + 1.0) * x); }

  float snoise(vec2 v) {
    const vec4 C = vec4(
      0.211324865405187, 0.366025403784439,
     -0.577350269189626, 0.024390243902439
    );
    vec2 i = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod289(i);
    vec3 p = permute(
      permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0)
    );
    vec3 m = max(
      0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)),
      0.0
    );
    m = m * m; m = m * m;
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
    vec3 g;
    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
  }

  float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    vec2 shift = vec2(100.0);
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
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
    float n = sin(dot(p, vec2(41.0, 289.0)));
    return fract(vec2(262144.0, 32768.0) * n);
  }

  mat2 rotate2D(float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return mat2(c, -s, s, c);
  }

  float easeOut(float x) {
    x = clamp(x, 0.0, 1.0);
    return 1.0 - pow(1.0 - x, 2.6);
  }

  // extra smooth ease-in-out for the reveal (плавность)
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
      float d = abs(bandPosition - idx);
      d = min(d, 8.0 - d);
      float w = max(0.0, 1.0 - d);
      value += uBands[i] * w;
    }
    return clamp(value, 0.0, 1.0);
  }

  // =========================================================
  // FLUID PLASMA (radial FBM + domain warping, no grid)
  // =========================================================

  float plasmaCloud(vec2 uv, vec2 dir, float dist, float seed, float time, float burstLevel) {
    float angle = atan(dir.y, dir.x);

    // Outward radial flow
    float flow = time * 0.8;
    vec2 noiseUV = uv * 6.0 - dir * flow;
    noiseUV += curlNoise2D(uv * 3.5 + time * 0.2) * 0.5; // Swirl distortion

    // Generate fluid shapes
    float cloudNoise = fbm(noiseUV + seed);
    cloudNoise = smoothstep(0.45, 0.85, cloudNoise); // Carve out distinct clumps

    // Asymmetric shape based on angle so it doesn't look like a perfect ring
    float angularEruption = fbm(vec2(angle * 2.0, time * 0.3 + seed));
    float maxDist = 0.02 + angularEruption * 0.18 + burstLevel * 0.3;

    // Fade out based on distance from the sphere edge
    // (max() guards against negative maxDist, which would otherwise flood whole sectors)
    float mask = 1.0 - smoothstep(0.0, max(maxDist, 0.01), dist);

    return cloudNoise * mask;
  }

  vec3 particleColors(float whiteMix, float purpleMix, float magentaMix, float intensity) {
    vec3 deepPurple = vec3(0.48, 0.16, 0.95);
    vec3 violet     = vec3(0.68, 0.42, 1.00);
    vec3 magenta    = vec3(0.92, 0.48, 1.00);
    vec3 softLilac  = vec3(0.82, 0.72, 1.00);
    vec3 whiteGlow  = vec3(0.98, 0.96, 1.00);
    vec3 c = mix(deepPurple, violet, clamp(purpleMix, 0.0, 1.0));
    c = mix(c, magenta, clamp(magentaMix, 0.0, 1.0));
    c = mix(c, softLilac, 0.15);
    c = mix(c, whiteGlow, clamp(whiteMix, 0.0, 1.0));
    return c * intensity;
  }

  vec3 renderPulse(
    vec2 uv, vec2 dir, float sphereDist,
    float phase, float strength, float seed, float audioEnergy
  ) {
    float p = fract(phase);
    float t = easeOut(p);

    // Timing envelope for the burst
    float appear = smoothstep(0.0, 0.08, p);
    float fade = 1.0 - smoothstep(0.2, 1.0, p);
    float envelope = appear * fade * strength;

    if (envelope <= 0.001) return vec3(0.0);

    // Burst intensity expands the cloud
    float burstLevel = t * (0.5 + audioEnergy * 1.5);
    float plasma = plasmaCloud(uv, dir, sphereDist, seed, uTime, burstLevel);

    // Mask out the inner sphere
    float outerMask = smoothstep(-0.005, 0.01, sphereDist);
    float intensity = plasma * envelope * outerMask;

    // Mix violet, magenta and white core
    return particleColors(0.2, 0.7, 0.4, intensity * 2.5);
  }

  // =========================================================
  // INTRO — expanding circular particle ring (появление)
  // =========================================================

  vec3 renderIntroRing(vec2 uv, vec2 dir, vec2 tangent, float radius, float reveal) {
    // ring lives mostly in the first ~85% of the reveal, then fades
    float ringActive = 1.0 - smoothstep(0.68, 1.0, reveal);
    if (ringActive <= 0.001) return vec3(0.0);

    float p = smoothstep(0.02, 0.85, reveal);
    float t = easeOut(p);

    float ringRadius = mix(0.02, 0.98, t);
    float ringWidth  = mix(0.010, 0.070, t);

    float shell = exp(-pow((radius - ringRadius) / ringWidth, 2.0));
    float leading = exp(-pow((radius - ringRadius) / max(ringWidth * 0.5, 0.006), 2.0));

    float appear = smoothstep(0.00, 0.08, reveal);
    float env = shell * appear * ringActive;

    // fluid plasma riding the expanding shell (grid removed)
    vec3 c = vec3(0.0);
    float plasmaRing = plasmaCloud(uv, dir, radius - ringRadius, 5.0, uTime, 0.2);
    c += particleColors(0.5, 0.5, 0.2, plasmaRing * env * 2.0);
    c += vec3(0.55, 0.34, 1.00) * shell * appear * ringActive * 0.22; // soft glow shell
    return c;
  }

  // =========================================================
  // MAIN
  // =========================================================

  void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / min(uRes.x, uRes.y);

    float radius = length(uv);
    vec2 dir = uv / max(radius, 1e-5);
    vec2 tangent = vec2(-dir.y, dir.x);

    float angle = atan(uv.y, uv.x);
    float angle01 = angle / TAU + 0.5;

    float band = sampleAudioBand(angle01);
    float bandSoft = smoothstep(0.0, 1.0, band);

    float audioEnergy = clamp(
      uAmp * 0.72 + bandSoft * 0.42 + uParticlePulse * 0.40 + uBurst * 0.35,
      0.0, 1.0
    );

    // -------- reveal-driven factors (плавное появление) --------
    float reveal      = clamp(uReveal, 0.0, 1.0);
    float sphereGrow  = easeInOut(smoothstep(0.10, 0.92, reveal)); // 0..1 sphere scale
    float sphereAlpha = smoothstep(0.08, 0.55, reveal);            // sphere fade-in
    float partReveal  = smoothstep(0.30, 1.00, reveal);            // ambient dust fade-in
    float globalFade  = smoothstep(0.00, 0.10, reveal);            // fade from black

    // =======================================================
    // SPHERE SIZE (grows in during reveal)
    // =======================================================
    float sphereRadiusFull = 0.180 + uAmp * 0.006 + uActivity * 0.003;
    float sphereRadius = sphereRadiusFull * mix(0.24, 1.0, sphereGrow);

    float sphereDist = radius - sphereRadius;
    float sphereMask = 1.0 - smoothstep(-0.006, 0.006, sphereDist);

    // =======================================================
    // BACKGROUND
    // =======================================================
    vec3 bgCenter = vec3(0.070, 0.022, 0.160);
    vec3 bgMiddle = vec3(0.025, 0.010, 0.072);
    vec3 bgEdge   = vec3(0.003, 0.002, 0.018);

    vec3 background = mix(bgCenter, bgMiddle, smoothstep(0.05, 0.70, radius));
    background = mix(background, bgEdge, smoothstep(0.50, 1.26, radius));

    float bgMist = exp(-radius * radius * 2.35);
    float bgNoise = 0.84 + 0.16 * fbm(uv * 1.08 + vec2(uTime * 0.016, -uTime * 0.013));
    background += vec3(0.095, 0.030, 0.220) * bgMist * bgNoise * 0.85;
    background += vec3(0.040, 0.016, 0.115) * exp(-radius * 1.82) * 0.65;

    vec3 finalColor = background;

    // -------- initial central bloom + ignition flash (first moments) --------
    float ignitionFlash = exp(-radius * radius * 46.0)
      * (1.0 - smoothstep(0.0, 0.24, reveal));
    finalColor += vec3(0.90, 0.76, 1.00) * ignitionFlash * 0.85;

    float earlyBloom = exp(-radius * radius * 9.0)
      * (1.0 - smoothstep(0.10, 0.60, reveal));
    finalColor += vec3(0.42, 0.22, 0.92) * earlyBloom * 0.55;

    // -------- expanding intro ring of particles --------
    finalColor += renderIntroRing(uv, dir, tangent, radius, reveal);

    // =======================================================
    // PARTICLE ORIGIN
    // =======================================================
    float rimShape = fbm(dir * 1.38 + vec2(uTime * 0.030, -uTime * 0.023));
    float rimFine  = snoise(dir * 3.90 + vec2(-uTime * 0.042, uTime * 0.034));
    float audioBulge = bandSoft * (0.0018 + uAmp * 0.0060);

    float particleOrigin =
      sphereRadius + 0.004
      + rimShape * (0.0026 + uParticlePulse * 0.0020)
      + rimFine * 0.0011
      + audioBulge;

    float particleDistance = radius - particleOrigin;

    // =======================================================
    // STEADY DUST AROUND THE SPHERE (fluid plasma)
    // =======================================================
    // Continuous ambient plasma breathing around the sphere
    float steadyPlasma = plasmaCloud(uv, dir, particleDistance, 42.0, uTime * 0.2, uActivity * 0.15);
    float steadyMask = smoothstep(-0.005, 0.01, particleDistance) * (1.0 - smoothstep(0.05, 0.18, particleDistance));
    float steadyEnvelope = steadyMask * partReveal;

    finalColor += particleColors(0.0, 0.6, 0.2, steadyPlasma * steadyEnvelope * (1.0 + uActivity));

    // =======================================================
    // PULSED PARTICLES
    // =======================================================
    float pulseSpeed = 0.155 + uParticlePulse * 0.085 + uBurst * 0.060;

    float phaseA = fract(uParticleTime * pulseSpeed + 0.00);
    float phaseB = fract(uParticleTime * pulseSpeed + 0.32);
    float phaseC = fract(uParticleTime * pulseSpeed + 0.64);

    float strengthA = (0.42 + uParticlePulse * 0.48 + uBurst * 0.38) * partReveal;
    float strengthB = (0.34 + uParticlePulse * 0.34 + uBurst * 0.22) * partReveal;
    float strengthC = (0.28 + uParticlePulse * 0.26 + uBurst * 0.16) * partReveal;

    finalColor += renderPulse(uv, dir, particleDistance, phaseA, strengthA, 11.0, audioEnergy);
    finalColor += renderPulse(uv, dir, particleDistance, phaseB, strengthB, 22.0, audioEnergy);
    finalColor += renderPulse(uv, dir, particleDistance, phaseC, strengthC, 33.0, audioEnergy);

    // =======================================================
    // RIM GLOW FOR PARTICLES
    // =======================================================
    float particleRimGlow = exp(-abs(particleDistance) * 52.0)
      * (1.0 - sphereMask)
      * (0.040 + uParticlePulse * 0.110 + uBurst * 0.060)
      * partReveal;

    finalColor += vec3(0.66, 0.42, 1.00) * particleRimGlow;

    // =======================================================
    // SPHERE
    // =======================================================
    float normalZ = sqrt(
      max(1.0 - (radius * radius) / (sphereRadius * sphereRadius), 0.0)
    );
    vec3 normal = normalize(vec3(uv / sphereRadius, normalZ));
    vec2 sphereUv = uv / sphereRadius;

    // ---- albedo (vertical gradient) ----
    vec3 sphereTopColor    = vec3(0.80, 0.68, 0.99);
    vec3 sphereMidColor    = vec3(0.60, 0.42, 0.95);
    vec3 sphereBottomColor = vec3(0.30, 0.14, 0.72);

    float verticalGradient = smoothstep(-1.0, 1.0, normal.y);
    vec3 albedo = mix(sphereBottomColor, sphereMidColor, verticalGradient);
    albedo = mix(albedo, sphereTopColor, smoothstep(0.20, 1.0, verticalGradient) * 0.70);

    // ---- key light (Blinn-Phong) ----
    vec3 L = normalize(vec3(-0.35, 0.62, 0.70));
    vec3 V = vec3(0.0, 0.0, 1.0);
    vec3 H = normalize(L + V);

    float ndl = dot(normal, L);
    float ndh = clamp(dot(normal, H), 0.0, 1.0);

    float diffuseWrap = clamp((ndl + 0.28) / 1.28, 0.0, 1.0); // soft wrapped diffuse
    float ambient = 0.20;
    float spec = pow(ndh, 42.0) * 0.55;                       // tight highlight

    // ---- fill light from the opposite side, for form ----
    vec3 fillL = normalize(vec3(0.45, -0.25, 0.55));
    float fill = clamp(dot(normal, fillL), 0.0, 1.0) * 0.14;

    vec3 sphereColor = albedo * (ambient + diffuseWrap * 0.98 + fill);
    sphereColor += vec3(0.98, 0.92, 1.00) * spec;

    // ---- fresnel rim: makes the silhouette read as a round volume ----
    float fres = pow(1.0 - normalZ, 3.0);
    sphereColor += vec3(0.62, 0.45, 1.00) * fres * 0.42;

    // ---- subsurface centre glow so it isn't plastic ----
    float sss = exp(-dot(sphereUv, sphereUv) * 1.40);
    sphereColor += vec3(0.72, 0.55, 0.98) * sss * 0.14;

    // ---- darken the lower terminator for depth ----
    float bottomShade = smoothstep(-1.0, -0.05, normal.y);
    sphereColor *= 1.0 - (1.0 - bottomShade) * 0.18;

    sphereColor *= 1.0 + uAmp * 0.030;

    // extra glow while the sphere is still materialising
    sphereColor += vec3(0.55, 0.40, 1.00) * (1.0 - sphereAlpha) * 0.20;

    finalColor = mix(finalColor, sphereColor, sphereMask * sphereAlpha);

    // =======================================================
    // SPHERE GLOW
    // =======================================================
    vec3 sphereGlowColor = vec3(0.46, 0.28, 0.92);
    vec3 sphereEdgeColor = vec3(0.72, 0.60, 0.98);

    float outerSphereGlow = exp(-max(sphereDist, 0.0) * 20.0) * (1.0 - sphereMask);
    finalColor += sphereGlowColor * outerSphereGlow
      * (0.085 + uParticlePulse * 0.040 + uAmp * 0.020) * sphereAlpha;

    float sphereEdgeGlow = exp(-abs(sphereDist) * 42.0) * (1.0 - sphereMask);
    finalColor += sphereEdgeColor * sphereEdgeGlow
      * (0.032 + uParticlePulse * 0.018) * sphereAlpha;

    // =======================================================
    // VIGNETTE + reveal fade from black
    // =======================================================
    finalColor *= 1.0 - 0.26 * smoothstep(0.62, 1.32, radius);
    finalColor *= globalFade;
    finalColor = pow(max(finalColor, 0.0), vec3(0.97));

    gl_FragColor = vec4(finalColor, 1.0);
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

        // intro reveal
        this.introDuration = 1.7;   // seconds
        this.introTime = 0;
        this.reveal = 0;

        this.renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: false,
            powerPreference: "high-performance",
        });
        this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

        this.scene = new THREE.Scene();
        this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

        this.bands = new Float32Array(8);
        this.bandTargets = new Float32Array(8);

        this.uniforms = {
            uRes: { value: new THREE.Vector2(1, 1) },
            uTime: { value: 0 },
            uParticleTime: { value: 0 },
            uAmp: { value: 0 },
            uActivity: { value: 0.15 },
            uParticlePulse: { value: 0 },
            uBurst: { value: 0 },
            uReveal: { value: 0 },
            uBands: { value: this.bands },
        };

        const geometry = new THREE.PlaneGeometry(2, 2);
        const material = new THREE.ShaderMaterial({
            uniforms: this.uniforms,
            vertexShader: VERT,
            fragmentShader: FRAG,
        });

        const quad = new THREE.Mesh(geometry, material);
        this.scene.add(quad);

        this.resize();
        addEventListener("resize", () => this.resize());

        this.clock = new THREE.Clock();
        this._loop();
    }

    resize() {
        const width = innerWidth;
        const height = innerHeight;
        this.renderer.setSize(width, height, false);
        const pixelRatio = this.renderer.getPixelRatio();
        this.uniforms.uRes.value.set(width * pixelRatio, height * pixelRatio);
    }

    // replay the appearance animation whenever you want
    restartIntro() {
        this.introTime = 0;
        this.reveal = 0;
    }

    setAmplitude(amplitude) {
        this.ampTarget = Math.min(1, Math.max(0, amplitude) * 1.30);
    }

    setBands(bands) {
        for (let i = 0; i < 8; i++) {
            this.bandTargets[i] = Math.min(1, Math.max(0, bands[i] ?? 0));
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

        if (state === "speaking" && prevState !== "speaking") {
            this.burst = 1.0;
            this.burstCooldown = 0.45;
        }
    }

    _loop() {
        requestAnimationFrame(() => this._loop());
        const dt = Math.min(this.clock.getDelta(), 0.05);

        // -------- intro reveal progress (smooth) --------
        if (this.introTime < this.introDuration) {
            this.introTime = Math.min(this.introDuration, this.introTime + dt);
        }
        this.reveal = this.introTime / this.introDuration;

        // -------- amplitude smoothing --------
        const ampRate = this.ampTarget > this.amp ? 16.0 : 4.6;
        const ampBlend = 1.0 - Math.exp(-ampRate * dt);
        this.amp += (this.ampTarget - this.amp) * ampBlend;
        this.ampTarget *= Math.exp(-9.6 * dt);

        // -------- bands smoothing --------
        let bandEnergy = 0;
        for (let i = 0; i < 8; i++) {
            const bandRate = this.bandTargets[i] > this.bands[i] ? 16.0 : 4.8;
            const bandBlend = 1.0 - Math.exp(-bandRate * dt);
            this.bands[i] += (this.bandTargets[i] - this.bands[i]) * bandBlend;
            this.bandTargets[i] *= Math.exp(-9.8 * dt);
            bandEnergy += this.bands[i];
        }
        bandEnergy /= 8.0;

        // -------- particle pulse smoothing (a touch softer for плавность) --------
        const particleTarget = Math.min(1, this.amp * 0.98 + bandEnergy * 0.76);
        const pulseRate = particleTarget > this.particlePulse ? 9.0 : 2.4;
        const pulseBlend = 1.0 - Math.exp(-pulseRate * dt);
        this.particlePulse += (particleTarget - this.particlePulse) * pulseBlend;

        // -------- burst trigger on voice onset --------
        const ampRise = Math.max(0, this.amp - this.prevAmp);
        this.burstCooldown = Math.max(0, this.burstCooldown - dt);
        const voiceOnset = ampRise > 0.025 && this.amp > 0.10 && this.burstCooldown <= 0;
        if (voiceOnset) {
            this.burst = 1.0;
            this.burstCooldown = 0.42;
        }
        this.prevAmp = this.amp;
        this.burst *= Math.exp(-2.6 * dt);

        // -------- particle flow time --------
        const particleSpeed =
            0.22
            + this.activity * 0.045
            + this.particlePulse * 0.18
            + bandEnergy * 0.07
            + this.burst * 0.10;
        this.particleTime += dt * particleSpeed;

        // -------- write uniforms --------
        this.uniforms.uTime.value += dt;
        this.uniforms.uParticleTime.value = this.particleTime;
        this.uniforms.uAmp.value = this.amp;
        this.uniforms.uParticlePulse.value = this.particlePulse;
        this.uniforms.uBurst.value = this.burst;
        this.uniforms.uReveal.value = this.reveal;

        const activityBlend = 1.0 - Math.exp(-4.0 * dt);
        this.uniforms.uActivity.value += (this.activity - this.uniforms.uActivity.value) * activityBlend;

        this.renderer.render(this.scene, this.camera);
    }
}