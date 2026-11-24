// Draws the player's own overlays for scripts/build_playthrough.py, from the built site:
// the title screen, the HUD, every subtitle cue, both decisions frame by frame (countdown, vibe badge,
// then the pick) and the cliffhanger card as it types out. Writes PNGs plus plan.json into <out-dir>.
// Usage: node scripts/playthrough_frames.cjs <base-url> <out-dir> [fps]
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const CW = 1152, CH = 648;          // the player's screen at desktop width, in CSS px (x 5/3 = 1920x1080)
const TITLE_S = 3.5, PRESS_S = 0.6; // title screen, ending with "Play episode" pressed
const ASK_S = 4.2, PICK_S = 0.8;    // the countdown, then the pick
const LEAD_S = 0.4, END_S = 8;      // a beat of black, then the cliffhanger types out (one character per 55 ms, as in the player)
const TYPE_MS = 55;

(async () => {
  const base = process.argv[2], out = process.argv[3], fps = Number(process.argv[4] || 30);
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: CW, height: CH }, deviceScaleFactor: 1920 / CW });
  page.on("pageerror", (e) => console.log("pageerror:", e.message));
  await page.goto(`${base}/index.html`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: `
    #screen { position: fixed !important; left: 0 !important; top: 0 !important; width: ${CW}px !important; height: ${CH}px !important;
              max-width: none !important; margin: 0 !important; border: 0 !important; border-radius: 0 !important;
              box-shadow: none !important; z-index: 2147483647; }
    .rec { animation: none !important; }
    .timer i, .opt, button { transition: none !important; }
    html.clear, html.clear body, html.clear #screen { background: transparent !important; }
    html.clear body * { visibility: hidden !important; }
    html.clear #screen, html.clear #screen *:not(video) { visibility: visible !important; }
    html.clear.nohud #ctl, html.clear.nohud #ctr { visibility: hidden !important; }
  ` });
  const shot = async (file, clear) => {
    await page.evaluate((c) => document.documentElement.classList.toggle("clear", c), clear);
    await page.screenshot({ path: path.join(out, file), clip: { x: 0, y: 0, width: CW, height: CH }, omitBackground: clear });
  };
  const rec = (on) => page.evaluate((on) => { document.querySelector(".rec").style.opacity = on ? "1" : "0"; }, on);
  const blink = (t) => (t % 1.4) < 0.7; // the REC dot: 1.4 s steps(2)

  // the path Sporkwhale's vibe predicts, and the option picked at each decision
  const info = await page.evaluate(() => {
    const route = ["c01", "c02", vibe.trust_pick === "vex" ? "a1" : "b1", "c03", vibe.package_pick === "hand_over" ? "d1" : "d2", "c04"];
    const picks = {};
    route.filter((id) => clips[id].choice.length).forEach((id) => { picks[id] = clips[id].choice.findIndex((o) => route.includes(o.next_clip)); });
    return { route, picks, cues: Object.fromEntries(route.map((id) => [id, clips[id].cues])) };
  });
  const plan = { fps, path: info.route, hud: {}, cues: {}, choices: {} };

  // 1. title screen, then "Play episode" pressed
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await shot("title.png", false);
  await page.evaluate(() => { const b = $("playBtn"); b.style.outline = "2px solid var(--cyan)"; b.style.outlineOffset = "3px"; b.style.filter = "brightness(1.08)"; });
  await shot("title_press.png", false);
  await page.evaluate(() => { $("playBtn").removeAttribute("style"); $("titleCard").hidden = true; });
  plan.title = { frame: "title.png", press: "title_press.png", seconds: TITLE_S, press_seconds: PRESS_S };

  // 2. the HUD for each shot, REC dot on and off
  for (const id of info.route) {
    await page.evaluate((id) => { hud(clips[id]); $("subs").innerHTML = ""; }, id);
    for (const on of [true, false]) {
      await rec(on);
      await shot(`hud_${id}_${on ? "on" : "off"}.png`, true);
    }
    plan.hud[id] = { on: `hud_${id}_on.png`, off: `hud_${id}_off.png` };
  }

  // 3. every subtitle cue, drawn by the player's own subtitle style
  await page.evaluate(() => document.documentElement.classList.add("nohud"));
  for (const id of info.route) {
    plan.cues[id] = [];
    for (const [i, q] of info.cues[id].entries()) {
      await page.evaluate((t) => { $("subs").innerHTML = `<span>${t}</span>`; }, q.t);
      await shot(`sub_${id}_${i}.png`, true);
      plan.cues[id].push({ s: q.s, e: q.e, frame: `sub_${id}_${i}.png` });
    }
  }
  await page.evaluate(() => { $("subs").innerHTML = ""; document.documentElement.classList.remove("nohud"); });

  // 4. each decision: the countdown running, then the pick
  for (const [id, pick] of Object.entries(info.picks)) {
    const dir = `choice_${id}`;
    fs.mkdirSync(path.join(out, dir));
    await page.evaluate((id) => { hud(clips[id]); ask(clips[id]); clearTimeout(timer); }, id);
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(r)))));
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    const askFrames = Math.round(ASK_S * fps), pickFrames = Math.round(PICK_S * fps);
    for (let f = 0; f < askFrames + pickFrames; f++) {
      await page.evaluate(({ t, on, picking, pick }) => {
        $("ctimer").style.transform = `scaleX(${Math.max(0, 1 - t / 12)})`;
        document.querySelector(".rec").style.opacity = on ? "1" : "0";
        if (picking) {
          $("copts").querySelectorAll("button").forEach((b, i) => {
            if (i === pick) { b.style.outline = "2px solid var(--cyan)"; b.style.outlineOffset = "3px"; }
            else b.style.opacity = "0.4";
          });
        }
      }, { t: Math.min(f, askFrames) / fps, on: blink(f / fps), picking: f >= askFrames, pick });
      await shot(`${dir}/f_${String(f).padStart(4, "0")}.png`, true);
    }
    plan.choices[id] = { pattern: `${dir}/f_%04d.png`, frames: askFrames + pickFrames, pick };
  }

  // 5. the cliffhanger card, typing out as in the player
  const text = await page.evaluate((route) => {
    window.typewrite = (el, t) => { el.dataset.full = t; el.textContent = ""; };
    clearTimeout(timer);
    $("choice").hidden = true;
    path = route.slice();
    picks = route.filter((id) => clips[id].choice.length).map((id) => clips[id].choice.find((o) => route.includes(o.next_clip)));
    finish();
    return $("cliff").dataset.full;
  }, info.route);
  fs.mkdirSync(path.join(out, "end"));
  const lead = Math.round(LEAD_S * fps), typing = Math.ceil((text.length * TYPE_MS / 1000) * fps);
  for (let f = 0; f <= lead + typing; f++) {
    const chars = f < lead ? 0 : Math.min(text.length, Math.floor(((f - lead) / fps) * 1000 / TYPE_MS) + 1);
    await page.evaluate((s) => { $("cliff").textContent = s; }, text.slice(0, chars));
    await shot(`end/e_${String(f).padStart(4, "0")}.png`, false);
  }
  plan.end = { pattern: "end/e_%04d.png", seconds: END_S, summary: await page.evaluate(() => $("endSum").textContent) };

  fs.writeFileSync(path.join(out, "plan.json"), JSON.stringify(plan, null, 1));
  console.log(`frames: ${info.route.join(" > ")}; ${plan.end.summary}`);
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
