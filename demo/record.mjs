// Scripted demo walkthrough of the live app, recorded by Playwright.
// Writes raw.webm + offsets.json (segment start times in ms from recording start).
import { chromium } from "playwright";
import fs from "node:fs";

const URL = "https://insidethegame.delightfulforest-cce043aa.swedencentral.azurecontainerapps.io/";
const segs = JSON.parse(fs.readFileSync("segments.json", "utf8"));
const W = 1920, H = 1080;

const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const context = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: ".", size: { width: W, height: H } } });
const t0 = Date.now();
const page = await context.newPage();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await page.goto(URL, { waitUntil: "networkidle" });
await page.waitForSelector("text=Live narrative", { timeout: 60000 });
await page.addStyleTag({ content: `
  body { zoom: 0.8; }
  #demo-caption { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 9999;
    background: rgba(8,12,20,.92); color: #fff; font: 600 26px system-ui; padding: 12px 26px; border-radius: 10px;
    border-left: 6px solid #ffe65a; max-width: 80vw; text-align: center; transition: opacity .3s; }
  #demo-title { position: fixed; inset: 0; z-index: 10000; display: none; align-items: center; justify-content: center;
    flex-direction: column; background: #0a0f17; color: #e6edf6; font-family: system-ui; }
  #demo-title h1 { font-size: 72px; margin: 0 0 18px; }
  #demo-title p { font-size: 30px; color: #8a9ab0; margin: 6px; }
` });
await page.evaluate(() => {
  const c = document.createElement("div"); c.id = "demo-caption"; c.style.opacity = "0"; document.body.appendChild(c);
  const t = document.createElement("div"); t.id = "demo-title";
  t.innerHTML = "<h1>Inside the Game</h1><p>Explainable match intelligence for every fan</p>" +
    "<p>Microsoft Agent Framework · Azure OpenAI · Azure Container Apps</p>" +
    "<p style='margin-top:28px;font-size:22px'>github.com/Mertan2/insidethegame-match-intelligence</p>";
  document.body.appendChild(t);
});

const caption = (text) => page.evaluate((text) => {
  const c = document.getElementById("demo-caption"); c.textContent = text; c.style.opacity = text ? "1" : "0";
}, text);
const select = (optionValue, value) => page.locator(`select:has(option[value="${optionValue}"])`).first().selectOption(value);
const seek = (t) => page.evaluate((t) => {
  const el = document.querySelector("input.seek");
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, String(t));
  el.dispatchEvent(new Event("input", { bubbles: true }));
}, t);
const click = (text) => page.getByRole("button", { name: text, exact: true }).click();

// Sync marker: a solid colour square in the corner, one colour per scene, found later in the video
// (the recorder's clock drifts from wall time, so wall-clock offsets alone can't place the audio).
const MARKERS = ["#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff", "#00ffff", "#ffffff"];
await page.evaluate(() => {
  const m = document.createElement("div"); m.id = "demo-marker";
  m.style.cssText = "position:fixed;left:0;top:0;width:50px;height:50px;z-index:10001;background:#000";
  document.body.appendChild(m);
});
const offsets = {};
let segIndex = 0;
async function segment(seg, actions) {
  const start = Date.now();
  offsets[seg.id] = start - t0;
  await page.evaluate((c) => { document.getElementById("demo-marker").style.background = c; }, MARKERS[segIndex++]);
  await caption(seg.caption);
  await actions();
  const left = seg.dur_s * 1000 - (Date.now() - start);
  if (left > 0) await sleep(left);
}
const S = Object.fromEntries(segs.map((s) => [s.id, s]));

// s1: overview, both views, match running.
await segment(S.s1, async () => {
  await click("BOTH");
  await select("16", "4");
  await seek(30);
});

// s2: 3D close-up following a striker (legs visible), toggle a plugin off and on.
await segment(S.s2, async () => {
  await seek(60);
  await click("3D");
  await select("a10", "a10");
  await sleep(6000);
  const cb = page.locator("label", { hasText: "momentum" }).locator("input");
  // Controlled by the server's ack, so click rather than check()/uncheck() (which assert instantly).
  await cb.click(); await sleep(2500); await cb.click();
});

// s3: the forecast moment, slowed down: Kai Whitlock's shot at 2:22 is called on target, then the goal.
await segment(S.s3, async () => {
  await select("a10", "");
  await click("BOTH");
  await seek(134);
  await select("16", "1");
});

// s4: analyst mode, play on (no seek, so no server rebuild) into the 3:16 save: why-bullets and agent trace.
await segment(S.s4, async () => {
  await click("Analyst");
  await select("16", "4");
  await page.waitForFunction(() => (document.querySelector(".scoreboard .clock")?.textContent ?? "") >= "3:08", null, { timeout: 20000 }).catch(() => {});
  await select("16", "1");
});

// s5: casual fan, Turkish, following the home No.10 into the 7:15 equaliser.
await segment(S.s5, async () => {
  await click("Casual fan");
  await select("tr", "tr");
  await select("a10", "h10");
  await click("3D");
  await seek(426);
  await select("16", "1");
});

// s6: automated recap (English, follows the same player).
await segment(S.s6, async () => {
  await select("tr", "en");
  await click("BOTH");
  await page.getByRole("button", { name: /Pause/ }).click();
  const btn = page.getByRole("button", { name: "Generate" });
  await btn.scrollIntoViewIfNeeded();
  const clicked = Date.now();
  page.on("request", (r) => r.url().includes("/recap") && console.log("recap request", r.url().split("?")[1], Date.now() - clicked, "ms"));
  page.on("response", (r) => r.url().includes("/recap") && console.log("recap response", r.status(), Date.now() - clicked, "ms"));
  await btn.click();
  await page.waitForSelector("text=Northbridge FC 2-2 Riverside Athletic", { timeout: 40000 }).catch(() => console.log("recap not shown"));
  console.log("recap visible after", Date.now() - clicked, "ms");
  await sleep(4000); // let it sit on screen
  await page.locator(".panel h4").first().scrollIntoViewIfNeeded().catch(() => {});
});

// s7: title card.
await segment(S.s7, async () => {
  await caption("");
  await page.evaluate(() => { document.getElementById("demo-title").style.display = "flex"; });
});

const video = page.video();
await context.close();
await browser.close();
fs.renameSync(await video.path(), "raw.webm");
fs.writeFileSync("offsets.json", JSON.stringify(offsets, null, 2));
console.log("done", offsets);
