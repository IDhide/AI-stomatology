// Точка входа визуала. Раньше здесь жил простой реактивный шар; теперь это
// полноценная сцена «Океан Оливии» (см. scene/OceanScene.js). Имя Visualizer
// сохранено для обратной совместимости.
export { OceanScene, OceanScene as Visualizer } from "./scene/OceanScene.js";
export { loadConfig, buildConfig, autoQuality } from "./scene/config.js";
