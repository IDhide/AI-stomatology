// Конфигурация сцены «Океан Оливии».
// Все ключевые параметры вынесены сюда (ТЗ §22). Профиль качества (§21)
// масштабирует нагрузку. Значения можно переопределить файлом kiosk/config.json
// (fetch при старте) — см. loadConfig().

export const PALETTE = {
  // фоновая палитра (ТЗ §6.1)
  bg: ["#03040B", "#07091A", "#0B1028", "#1A0D32", "#241044", "#4B1A74", "#52C7D9"],
  // допустимые оттенки медуз (ТЗ §7.3)
  jelly: ["#6ec3ff", "#8a7bff", "#3fe0e0", "#ff9ad6", "#bfe0ff", "#a08cff"],
  core: "#7b3ff2",
  coreGlow: "#a06bff",
};

// Базовый конфиг (профиль High). Профили Low/Medium прореживают нагрузку.
const BASE = {
  quality: "high",
  jellyfish: {
    minCount: 5,
    maxCount: 9,
    minSpeed: 0.02,
    maxSpeed: 0.08,
    glowIntensity: 0.7,
    tentacleSegments: 24,
  },
  particles: {
    count: 2500,       // фоновые
    planktonCount: 260, // биолюминесцентный планктон
    brightness: 0.4,
  },
  core: {
    idleIntensity: 0.15,
    activeIntensity: 1.0,
    pulseIntervalMin: 8,
    pulseIntervalMax: 18,
  },
  camera: {
    driftIntensity: 0.12,
    zoomIntensity: 0.04,
  },
  transitions: {
    awakeningDuration: 1.2,
    returnDuration: 2.2,
  },
  events: {
    intervalMin: 20,
    intervalMax: 120,
  },
  render: {
    pixelRatio: 1.0,
    bloom: true,
    bloomStrength: 0.65,
    bloomRadius: 0.75,
    bloomThreshold: 0.72,
    fog: true,
    depthEffects: true,
  },
};

// Отличия профилей качества от базового (ТЗ §21).
const PROFILES = {
  low: {
    jellyfish: { minCount: 3, maxCount: 4, tentacleSegments: 12 },
    particles: { count: 700, planktonCount: 90 },
    render: {
      pixelRatio: 0.75,
      bloom: true,
      bloomStrength: 0.55,
      fog: false,
      depthEffects: false,
    },
  },
  medium: {
    jellyfish: { minCount: 5, maxCount: 7, tentacleSegments: 18 },
    particles: { count: 1500, planktonCount: 160 },
    render: {
      pixelRatio: 1.0,
      bloom: true,
      bloomStrength: 0.75,
      fog: true,
      depthEffects: false,
    },
  },
  high: {}, // = BASE
};

function deepMerge(target, patch) {
  const out = Array.isArray(target) ? target.slice() : { ...target };
  for (const k of Object.keys(patch || {})) {
    const v = patch[k];
    if (v && typeof v === "object" && !Array.isArray(v)) {
      out[k] = deepMerge(target[k] || {}, v);
    } else {
      out[k] = v;
    }
  }
  return out;
}

export function buildConfig(overrides = {}) {
  const quality = (overrides.quality || BASE.quality || "high").toLowerCase();
  let cfg = deepMerge(BASE, PROFILES[quality] || {});
  cfg = deepMerge(cfg, overrides);
  cfg.quality = quality;
  return cfg;
}

// Пытаемся подтянуть kiosk/config.json (необязательно). При ошибке — дефолт.
export async function loadConfig() {
  try {
    const res = await fetch("/config.json", { cache: "no-store" });
    if (res.ok) return buildConfig(await res.json());
  } catch (_) {
    /* нет файла — работаем на дефолтах */
  }
  return buildConfig();
}

// Авто-подбор профиля по «слабости» устройства (грубая эвристика).
export function autoQuality() {
  const mem = navigator.deviceMemory || 8;
  const cores = navigator.hardwareConcurrency || 4;
  if (mem <= 4 || cores <= 2) return "low";
  if (mem <= 8 || cores <= 4) return "medium";
  return "high";
}
