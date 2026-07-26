import * as THREE from "three";

const VERT = /* glsl */ `
  void main() {
    gl_Position = vec4(position, 1.0);
  }
`;

const FRAG = /* glsl */ `
  precision highp float;

  uniform vec2  uRes;
  uniform float uTime;
  uniform float uWaveTime;
  uniform float uAmp;
  uniform float uActivity;
  uniform float uBands[8];

  const float TAU = 6.28318530718;

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

    vec2 i1 = x0.x > x0.y
      ? vec2(1.0, 0.0)
      : vec2(0.0, 1.0);

    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;

    i = mod289(i);

    vec3 p = permute(
      permute(i.y + vec3(0.0, i1.y, 1.0))
      + i.x + vec3(0.0, i1.x, 1.0)
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
      - 0.85373472095314 * (a0 * a0 + h * h);

    vec3 g;

    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;

    return 130.0 * dot(m, g);
  }

  float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;

    vec2 shift = vec2(100.0);

    mat2 rotation = mat2(
       cos(0.5), sin(0.5),
      -sin(0.5), cos(0.5)
    );

    for (int i = 0; i < 6; i++) {
      value += amplitude * snoise(p);
      p = rotation * p * 2.02 + shift;
      amplitude *= 0.48;
    }

    return value;
  }

  float sampleAudioBand(float angle01) {
    float bandPosition = fract(angle01) * 8.0;
    float value = 0.0;

    for (int i = 0; i < 8; i++) {
      float index = float(i);

      float distanceToBand = abs(
        bandPosition - index
      );

      distanceToBand = min(
        distanceToBand,
        8.0 - distanceToBand
      );

      float weight = max(
        0.0,
        1.0 - distanceToBand
      );

      value += uBands[i] * weight;
    }

    return clamp(value, 0.0, 1.0);
  }

  void main() {
    vec2 uv = (
      gl_FragCoord.xy - 0.5 * uRes
    ) / min(uRes.x, uRes.y);

    float radius = length(uv);

    vec2 direction = uv / max(
      radius,
      1e-5
    );

    float angle = atan(uv.y, uv.x);
    float angle01 = angle / TAU + 0.5;
    float time = uTime;

    float band = sampleAudioBand(angle01);

    float bandSoft = smoothstep(
      0.0,
      1.0,
      band
    );

    float audioEnergy = clamp(
      uAmp * 0.78 + bandSoft * 0.48,
      0.0,
      1.0
    );

    /*
     * Центральная сфера.
     */

    float sphereRadius =
      0.180
      + uAmp * 0.010
      + uActivity * 0.003;

    float sphereDistance =
      radius - sphereRadius;

    float sphereMask = smoothstep(
      0.006,
      -0.006,
      sphereDistance
    );

    /*
     * Органически деформированный контур,
     * от которого начинаются волны.
     */

    float contourNoiseA = fbm(
      direction * 1.55
      + vec2(
        time * 0.045,
        -time * 0.035
      )
    );

    float contourNoiseB = snoise(
      direction * 3.10
      + vec2(
        -time * 0.060,
        time * 0.050
      )
    );

    float contourNoiseC = snoise(
      direction * 5.20
      + vec2(
        time * 0.035,
        11.0
      )
    );

    float breathing = sin(
      time * 0.72
      + contourNoiseA * 1.5
    ) * (
      0.0018
      + uActivity * 0.0016
      + uAmp * 0.0022
    );

    float equalizerBulge = bandSoft * (
      0.007
      + uActivity * 0.004
      + uAmp * 0.022
    );

    float contourAmplitude =
      0.008
      + uActivity * 0.006
      + uAmp * 0.012;

    float contourOffset =
      contourNoiseA * contourAmplitude
      + contourNoiseB * (
        0.004 + uAmp * 0.004
      )
      + contourNoiseC * 0.0025
      + equalizerBulge
      + breathing;

    float waveOrigin =
      sphereRadius
      + 0.004
      + contourOffset;

    float contourDistance =
      radius - waveOrigin;

    /*
     * Жидкое искажение отдельных волн.
     */

    float movingRippleNoise = snoise(
      direction * 3.60
      + vec2(
        time * 0.105,
        -time * 0.085
      )
      + contourDistance
      * vec2(9.0, -6.5)
    );

    float localRippleNoise = snoise(
      uv * 5.00
      + vec2(
        -time * 0.060,
        time * 0.050
      )
    );

    float rippleNoiseAmplitude =
      0.0025
      + uActivity * 0.0018
      + uAmp * 0.0075
      + bandSoft * 0.0050;

    float distortedDistance =
      contourDistance
      + movingRippleNoise
      * rippleNoiseAmplitude
      + localRippleNoise
      * rippleNoiseAmplitude
      * 0.32;

    float outerShapeNoise = fbm(
      direction * 1.25
      + vec2(
        9.0,
        -time * 0.030
      )
    );

    /*
     * Компактная область волн.
     * Они не распространяются по всему экрану.
     */

    float outerExtent = clamp(
      0.128
      + outerShapeNoise * 0.020
      + bandSoft * (
        0.012 + uAmp * 0.014
      )
      + uActivity * 0.006,
      0.100,
      0.175
    );

    float innerGate = smoothstep(
      -0.022,
      -0.002,
      contourDistance
    );

    float outerGate =
      1.0 - smoothstep(
        outerExtent - 0.038,
        outerExtent + 0.004,
        contourDistance
      );

    float waveZone =
      innerGate * outerGate;

    float radialDecay = pow(
      clamp(
        1.0
        - max(contourDistance, 0.0)
        / outerExtent,
        0.0,
        1.0
      ),
      1.08
    );

    /*
     * Широкие и мягкие концентрические волны.
     */

    float ringFrequency = 760.0;

    float ringPhase =
      distortedDistance * ringFrequency
      - uWaveTime;

    float ringCarrier =
      0.5 + 0.5 * cos(ringPhase);

    float sharpRidges = pow(
      ringCarrier,
      6.5
    );

    float softRidges = pow(
      ringCarrier,
      2.2
    );

    float darkGrooves = pow(
      1.0 - ringCarrier,
      3.0
    );

    float slowModulation =
      0.84
      + 0.16 * sin(
        distortedDistance * 62.0
        - uWaveTime * 0.12
        + contourNoiseB * 1.6
      );

    float lineTexture =
      0.88
      + 0.12 * (
        0.5
        + 0.5 * snoise(
          vec2(
            angle01 * 11.0,
            distortedDistance * 34.0
          )
          + vec2(
            time * 0.035,
            -time * 0.025
          )
        )
      );

    float angularPatch =
      0.80
      + 0.20 * smoothstep(
        -0.45,
        0.65,
        snoise(
          direction * 2.10
          + vec2(
            -time * 0.028,
            14.0
          )
        )
      );

    float waveLines = mix(
      softRidges,
      sharpRidges,
      0.55
    );

    waveLines *= slowModulation;
    waveLines *= lineTexture;
    waveLines *= angularPatch;
    waveLines *= waveZone;
    waveLines *= radialDecay;

    float waveShadows =
      darkGrooves
      * waveZone
      * radialDecay;

    float waveSoftGlow =
      softRidges
      * waveZone
      * radialDecay
      * (
        0.38
        + 0.30 * audioEnergy
      );

    /*
     * Цветная плазма между линиями.
     */

    float plasmaField = fbm(
      direction * 2.15
      + vec2(
        time * 0.045,
        5.0
      )
      + contourDistance * 7.0
    );

    float plasmaNoise =
      0.74 + 0.26 * plasmaField;

    float plasmaBody =
      waveZone
      * radialDecay
      * plasmaNoise
      * (
        0.24
        + 0.22 * uActivity
        + 0.22 * audioEnergy
      );

    float edgeGlow =
      exp(
        -abs(contourDistance) * 32.0
      )
      * innerGate
      * (
        0.56
        + 0.42 * audioEnergy
      );

    /*
     * Направленное освещение.
     */

    float lightKey = dot(
      direction,
      normalize(vec2(-0.52, -0.64))
    );

    float lightFill = dot(
      direction,
      normalize(vec2(0.62, 0.20))
    );

    float directionalLight =
      0.58
      + 0.42 * smoothstep(
        -0.35,
        0.92,
        lightKey
      );

    plasmaBody *= directionalLight;

    edgeGlow *=
      0.78
      + 0.22 * directionalLight;

    waveLines *=
      0.82
      + 0.28 * directionalLight;

    waveSoftGlow *=
      0.85
      + 0.22 * directionalLight;

    /*
     * Палитра.
     */

    float hueA = contourNoiseA;
    float hueB = outerShapeNoise;
    float hueC = plasmaField;

    vec3 deepBlue = vec3(
      0.035,
      0.070,
      0.360
    );

    vec3 electricBlue = vec3(
      0.105,
      0.300,
      1.000
    );

    vec3 violet = vec3(
      0.430,
      0.180,
      1.000
    );

    vec3 neonMagenta = vec3(
      0.980,
      0.120,
      0.840
    );

    vec3 neonPink = vec3(
      1.000,
      0.300,
      0.700
    );

    vec3 plasmaColor = mix(
      deepBlue,
      electricBlue,
      smoothstep(
        -0.18,
        0.38,
        hueA
      )
    );

    plasmaColor = mix(
      plasmaColor,
      violet,
      smoothstep(
        0.20,
        0.68,
        hueB
      ) * 0.86
    );

    plasmaColor = mix(
      plasmaColor,
      neonMagenta,
      smoothstep(
        0.48,
        0.86,
        hueC
      ) * 0.78
    );

    plasmaColor = mix(
      plasmaColor,
      neonPink,
      smoothstep(
        0.72,
        0.96,
        hueA
      ) * 0.38
    );

    vec3 lineColor = mix(
      electricBlue,
      neonMagenta,
      smoothstep(
        -0.05,
        0.60,
        hueB
      )
    );

    lineColor = mix(
      lineColor,
      vec3(0.82, 0.72, 1.00),
      0.20 + 0.15 * audioEnergy
    );

    /*
     * Фиолетовый фон всего экрана.
     */

    vec3 backgroundCenter = vec3(
      0.105,
      0.035,
      0.205
    );

    vec3 backgroundMiddle = vec3(
      0.040,
      0.014,
      0.105
    );

    vec3 backgroundEdge = vec3(
      0.007,
      0.003,
      0.025
    );

    vec3 background = mix(
      backgroundCenter,
      backgroundMiddle,
      smoothstep(
        0.05,
        0.68,
        radius
      )
    );

    background = mix(
      background,
      backgroundEdge,
      smoothstep(
        0.52,
        1.28,
        radius
      )
    );

    /*
     * Большое мягкое фиолетовое облако.
     */

    float purpleMist = exp(
      -radius * radius * 2.45
    );

    float backgroundNoise =
      0.82
      + 0.18 * fbm(
        uv * 1.10
        + vec2(
          time * 0.018,
          -time * 0.014
        )
      );

    background += vec3(
      0.115,
      0.035,
      0.255
    ) * purpleMist * backgroundNoise;

    /*
     * Широкое фиолетовое свечение,
     * заметное за пределами шара.
     */

    float widePurpleAura = exp(
      -radius * 1.85
    );

    background += vec3(
      0.052,
      0.018,
      0.135
    ) * widePurpleAura * (
      0.82 + 0.18 * lightFill
    );

    /*
     * Небольшая синяя дымка справа.
     */

    float blueMistDirection = smoothstep(
      -0.70,
      0.85,
      dot(
        direction,
        normalize(vec2(0.70, 0.20))
      )
    );

    background += electricBlue
      * exp(-radius * 3.20)
      * blueMistDirection
      * 0.025;

    /*
     * Итоговая сборка плазмы и волн.
     */

    vec3 finalColor = background;

    finalColor += plasmaColor
      * plasmaBody
      * (
        0.92 + uAmp * 0.46
      );

    finalColor += plasmaColor
      * edgeGlow
      * 0.82;

    finalColor += lineColor
      * waveLines
      * (
        0.95
        + uActivity * 0.24
        + audioEnergy * 0.95
      );

    finalColor += lineColor
      * waveSoftGlow
      * 0.22;

    finalColor -= plasmaColor
      * waveShadows
      * 0.050;

    /*
     * Компактный bloom вокруг волн.
     */

    float bloomGate = innerGate * (
      1.0 - smoothstep(
        outerExtent - 0.015,
        outerExtent + 0.016,
        contourDistance
      )
    );

    float compactBloom =
      exp(
        -max(contourDistance, 0.0)
        * 13.5
      )
      * bloomGate;

    vec3 bloomColor = mix(
      violet,
      neonMagenta,
      0.50
      + 0.20 * sin(time * 0.35)
    );

    finalColor += bloomColor
      * compactBloom
      * (
        0.11
        + 0.10 * uActivity
        + 0.13 * audioEnergy
      );

    /*
     * Мягкая виньетка.
     * Не затемняет фиолетовый фон слишком сильно.
     */

    finalColor *=
      1.0
      - 0.28 * smoothstep(
        0.62,
        1.32,
        radius
      );

    /*
     * Объёмная центральная сфера.
     */

    float normalZ = sqrt(
      max(
        1.0
        - (
          radius * radius
        ) / (
          sphereRadius * sphereRadius
        ),
        0.0
      )
    );

    vec3 normal = vec3(
      uv / sphereRadius,
      normalZ
    );

    float sphereBump = snoise(
      uv * 8.0
      + vec2(
        time * 0.30,
        -time * 0.20
      )
    ) * (
      0.10
      + uAmp * 0.32
    );

    normal = normalize(
      normal
      + vec3(sphereBump * 0.18)
    );

    vec3 lightDirection = normalize(
      vec3(-0.35, 0.65, 0.60)
    );

    float diffuse = clamp(
      dot(normal, lightDirection),
      0.0,
      1.0
    );

    vec3 sphereBase = vec3(
      0.030,
      0.014,
      0.075
    );

    vec3 sphereMid = vec3(
      0.180,
      0.085,
      0.440
    );

    vec3 sphereHighlight = vec3(
      0.620,
      0.480,
      1.000
    );

    vec3 sphereColor = mix(
      sphereBase,
      sphereMid,
      smoothstep(
        0.0,
        0.82,
        diffuse
      )
    );

    sphereColor = mix(
      sphereColor,
      sphereHighlight,
      pow(diffuse, 5.0) * 0.72
    );

    /*
     * Магентовый блик на сфере.
     */

    vec3 specularLight = normalize(
      vec3(-0.55, -0.70, 0.75)
    );

    vec3 viewDirection = vec3(
      0.0,
      0.0,
      1.0
    );

    vec3 halfVector = normalize(
      specularLight + viewDirection
    );

    float specular = pow(
      max(
        0.0,
        dot(normal, halfVector)
      ),
      24.0
    );

    sphereColor += neonMagenta
      * specular
      * 0.82;

    /*
     * Синее ambient-освещение справа.
     */

    float ambient = max(
      0.0,
      dot(
        normal,
        normalize(
          vec3(0.70, 0.15, 0.50)
        )
      )
    );

    sphereColor += electricBlue
      * ambient
      * 0.16;

    /*
     * Светящаяся кромка сферы.
     */

    float rim = pow(
      1.0 - normalZ,
      3.0
    );

    sphereColor += mix(
      neonMagenta,
      violet,
      0.5
    ) * rim * 0.48;

    sphereColor *=
      1.0 + uAmp * 0.30;

    sphereColor *=
      0.97
      + 0.05 * snoise(
        uv * 6.0
        + time * 0.12
      );

    finalColor = mix(
      finalColor,
      sphereColor,
      sphereMask
    );

    /*
     * Яркая тонкая кромка шарика.
     */

    float sphereRim =
      exp(
        -abs(sphereDistance) * 60.0
      )
      * (1.0 - sphereMask);

    finalColor += mix(
      violet,
      neonMagenta,
      0.58
    ) * sphereRim * (
      0.32
      + uAmp * 0.34
      + bandSoft * 0.14
    );

    /*
     * Более широкое свечение вокруг шарика.
     */

    float sphereGlow = exp(
      -max(sphereDistance, 0.0)
      * 22.0
    );

    finalColor += mix(
      electricBlue,
      violet,
      0.55
    ) * sphereGlow * (
      0.09
      + 0.12 * uAmp
      + 0.06 * bandSoft
    ) * (
      1.0 - sphereMask
    );

    /*
     * Дополнительное фиолетово-розовое
     * свечение вокруг самого ядра.
     */

    float sphereOuterGlow = exp(
      -max(sphereDistance, 0.0)
      * 10.5
    );

    sphereOuterGlow *=
      1.0 - smoothstep(
        sphereRadius + 0.02,
        sphereRadius + 0.19,
        radius
      );

    finalColor += mix(
      violet,
      neonMagenta,
      0.38
    ) * sphereOuterGlow * (
      0.030
      + uAmp * 0.065
      + uActivity * 0.018
    ) * (
      1.0 - sphereMask
    );

    gl_FragColor = vec4(
      max(finalColor, 0.0),
      1.0
    );
  }
`;

export class Visualizer {
    constructor(canvas) {
        this.canvas = canvas;

        this.amp = 0;
        this.ampTarget = 0;
        this.activity = 0.15;
        this.waveTime = 0;

        this.renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: false,
            powerPreference: "high-performance",
        });

        this.renderer.setPixelRatio(
            Math.min(devicePixelRatio, 2)
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

            uWaveTime: {
                value: 0,
            },

            uAmp: {
                value: 0,
            },

            uActivity: {
                value: 0.15,
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

    setAmplitude(amplitude) {
        this.ampTarget = Math.min(
            1,
            Math.max(0, amplitude) * 1.35
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
        this.activity = {
            idle: 0.10,
            listening: 0.32,
            thinking: 0.62,
            speaking: 0.52,
        }[state] ?? 0.15;
    }

    _loop() {
        requestAnimationFrame(
            () => this._loop()
        );

        const dt = Math.min(
            this.clock.getDelta(),
            0.05
        );

        /*
         * Быстрая атака аудио,
         * более мягкое затухание.
         */

        const ampRate =
            this.ampTarget > this.amp
                ? 20.0
                : 5.5;

        const ampBlend =
            1.0 - Math.exp(-ampRate * dt);

        this.amp += (
            this.ampTarget - this.amp
        ) * ampBlend;

        this.ampTarget *= Math.exp(
            -10.5 * dt
        );

        let bandEnergy = 0;

        for (let i = 0; i < 8; i++) {
            const bandRate =
                this.bandTargets[i] > this.bands[i]
                    ? 23.0
                    : 6.5;

            const bandBlend =
                1.0 - Math.exp(-bandRate * dt);

            this.bands[i] += (
                this.bandTargets[i]
                - this.bands[i]
            ) * bandBlend;

            this.bandTargets[i] *= Math.exp(
                -11.0 * dt
            );

            bandEnergy += this.bands[i];
        }

        bandEnergy /= 8.0;

        /*
         * Чем громче речь, тем быстрее
         * волны расходятся наружу.
         */

        const waveSpeed =
            3.2
            + this.activity * 1.2
            + this.amp * 10.5
            + bandEnergy * 3.5;

        this.waveTime += dt * waveSpeed;

        this.uniforms.uTime.value += dt;
        this.uniforms.uWaveTime.value = this.waveTime;
        this.uniforms.uAmp.value = this.amp;

        const activityBlend =
            1.0 - Math.exp(-4.0 * dt);

        this.uniforms.uActivity.value += (
            this.activity
            - this.uniforms.uActivity.value
        ) * activityBlend;

        this.renderer.render(
            this.scene,
            this.camera
        );
    }
}