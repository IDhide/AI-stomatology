// Скриншоты веб-киоска Smile.AI в разных режимах.
// Использование: node scripts/screenshot_ui.js
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({
    executablePath:
      process.env.PW_CHROME ||
      "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    args: ["--no-sandbox", "--use-gl=swiftshader"],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto("http://127.0.0.1:8080/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500); // фон/частицы прогрелись

  // 1) IDLE — медузы/космос
  await page.evaluate(() => window.SmileUI.setMode("idle"));
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "docs/ui_idle.png" });

  // 2) SPEAKING — фиолетовый круг + аудио-волна + субтитр (как на референсе)
  await page.evaluate(() => {
    window.SmileUI.setMode("speaking");
    window.SmileUI.setSubtitle(
      "Здравствуйте! Я Лена, виртуальный администратор клиники Smile. Чем могу помочь?",
      "bot"
    );
  });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "docs/ui_speaking.png" });

  // 3) LISTENING — зелёный акцент
  await page.evaluate(() => {
    window.SmileUI.setMode("listening");
    window.SmileUI.setSubtitle("вы: у меня кариес, хочу записаться", "user");
  });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "docs/ui_listening.png" });

  // 4) THINKING — янтарный
  await page.evaluate(() => {
    window.SmileUI.setMode("thinking");
    window.SmileUI.setSubtitle("", "bot");
  });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "docs/ui_thinking.png" });

  await browser.close();
  console.log("OK: docs/ui_idle.png, ui_speaking.png, ui_listening.png, ui_thinking.png");
})();
