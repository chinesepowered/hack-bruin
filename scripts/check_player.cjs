// Plays the episode in a real browser and checks that every path reaches the cliffhanger card.
// Each shot is skipped to its last moments, so all four paths take about a minute.
// Usage: node scripts/check_player.cjs [url] [--slow] [--paths=1]   (locally: python3 scripts/serve_site.py first)
//   --slow  delays every video request by 400 ms, like a real network (start-up races show up locally)
const { chromium } = require("playwright");

(async () => {
  const args = process.argv.slice(2);
  const url = args.find((a) => !a.startsWith("--")) || "http://127.0.0.1:8765/";
  const slow = args.includes("--slow");
  const nPaths = Number((args.find((a) => a.startsWith("--paths=")) || "--paths=4").split("=")[1]);
  const browser = await chromium.launch();
  let ok = 0;
  for (const picks of [[0, 0], [0, 1], [1, 0], [1, 1]].slice(0, nPaths)) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    if (slow) await page.route(/\.mp4(\?|$)/, async (route) => { await new Promise((r) => setTimeout(r, 400)); await route.continue(); });
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.click("#playBtn");
    const played = [];
    let decision = 0, outcome = "stuck";
    for (let step = 0; step < 16; step++) {
      // wait for the next thing to happen: a new shot playing, a decision, or the cliffhanger card
      const last = played[played.length - 1] || null;
      const state = await page.waitForFunction((last) => {
        if (!$("endCard").hidden) return { kind: "end" };
        if (!$("choice").hidden) return { kind: "choice" };
        const file = current && current.video.split("/").pop();
        if (current && current.clip_id !== last && !active.paused && active.currentTime > 0.1 && active.src.endsWith(file))
          return { kind: "shot", id: current.clip_id };
        return null;
      }, last, { timeout: 25000, polling: 100 }).then((h) => h.jsonValue()).catch(() => ({ kind: "stuck" }));
      if (state.kind === "shot") {
        played.push(state.id);
        await page.evaluate(() => { active.currentTime = Math.max(0, active.duration - 0.4); });
      } else if (state.kind === "choice") {
        await page.locator("#copts button").nth(picks[decision++]).click();
        await page.waitForFunction(() => $("choice").hidden, null, { timeout: 5000 }).catch(() => {});
      } else {
        outcome = state.kind;
        break;
      }
    }
    const info = await page.evaluate(() => ({ current: current && current.clip_id, endSum: $("endSum").textContent }));
    const good = outcome === "end" && played.length === 6 && !errors.length;
    ok += good ? 1 : 0;
    console.log(`${good ? "PASS" : "FAIL"} picks ${picks.join("/")}: ${played.join(" > ")}` +
      (outcome === "end" ? `  |  ${info.endSum}` : `  |  ${outcome} after ${info.current}`) + (errors.length ? `  |  errors: ${errors.join("; ")}` : ""));
    await page.close();
  }
  await browser.close();
  console.log(`${ok}/${nPaths} paths reached the cliffhanger`);
  process.exit(ok === nPaths ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
