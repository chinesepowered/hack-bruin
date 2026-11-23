// Screenshots of the player's states and the Bruin lineage docs, for the README and the demo video.
// Usage: node scripts/screenshots.cjs <base-url> <out-dir>
const { chromium } = require("playwright");
const fs = require("node:fs");

(async () => {

const base = process.argv[2] || "http://127.0.0.1:8765";
const out = process.argv[3] || "demo/build/shots";
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 });
page.on("pageerror", (e) => console.log("pageerror:", e.message));
await page.goto(`${base}/index.html`, { waitUntil: "networkidle" });
await page.waitForTimeout(800);

const shot = async (name, selector) => {
  const el = selector ? page.locator(selector) : page;
  await el.screenshot({ path: `${out}/${name}.png` });
  console.log("shot", name);
};

// 1. title screen
await shot("title", "#screen");

// 2. first decision, with the vibe badge, over the decision frame
await page.evaluate(() => {
  $("titleCard").hidden = true;
  active.poster = "media/s03.jpg"; active.classList.remove("off");
  ask(clips.c02);
});
await page.waitForTimeout(600);
await shot("choice1", "#screen");

// 3. second decision
await page.evaluate(() => { clearTimeout(timer); active.poster = "media/s06.jpg"; ask(clips.c03); });
await page.waitForTimeout(600);
await shot("choice2", "#screen");

// 4. the cliffhanger card after a full path
await page.evaluate(() => {
  clearTimeout(timer);
  $("choice").hidden = true;
  path = ["c01", "c02", "b1", "c03", "d2", "c04"];
  ["c01", "c02", "b1", "c03", "d2", "c04"].forEach((c) => seen.add(c));
  picks = [clips.c02.choice[1], clips.c03.choice[1]];
  finish();
});
await page.waitForTimeout(3500);
await shot("end", "#screen");

// 5. panels
await shot("map", "#mapPanel");
await shot("crew", "#crewPanel");
await shot("making", "#making");
await page.setViewportSize({ width: 1440, height: 900 });
await page.screenshot({ path: `${out}/full.png`, fullPage: true });
console.log("shot full");

// 6. Bruin lineage docs
const docs = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 });
await docs.goto(`${base}/pipeline.html`, { waitUntil: "networkidle" });
await docs.waitForTimeout(1500);
await docs.screenshot({ path: `${out}/docs_home.png` });
console.log("shot docs_home");
await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
