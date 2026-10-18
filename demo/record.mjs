// Scripted demo walkthrough of the live app, recorded by Playwright.
// Writes raw.webm; each scene shows a coloured corner marker so audio can be synced to the video afterwards.
import { chromium } from "playwright";
import fs from "node:fs";

const URL = "https://insidethegame.delightfulforest-cce043aa.swedencentral.azurecontainerapps.io/";
const segs = JSON.parse(fs.readFileSync("segments.json", "utf8"));
const W = 1920, H = 1080;
const MARKERS = ["#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff", "#00ffff", "#ff8800", "#ffffff"];

const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const context = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: ".", size: { width: W, height: H } } });
const page = await context.newPage();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await page.goto(URL, { waitUntil: "networkidle" });
await page.waitForSelector(".feed", { timeout: 60000 });
await page.addStyleTag({ content: `
  body { zoom: 0.8; }
  #demo-caption { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 9999;
    background: rgba(8,12,20,.92); color: #fff; font: 600 26px system-ui; padding: 12px 26px; border-radius: 10px;
    border-left: 6px solid #b69cff; max-width: 80vw; text-align: center; transition: opacity .3s; }
  #demo-title { position: fixed; inset: 0; z-index: 10000; display: none; align-items: center; justify-content: center;
    flex-direction: column; background: #0a0f17; color: #e6edf6; font-family: system-ui; }
  #demo-title h1 { font-size: 72px; margin: 0 0 18px; }
  #demo-title p { font-size: 30px; color: #8a9ab0; margin: 6px; }
  #demo-marker { position: fixed; left: 0; top: 0; width: 50px; height: 50px; z-index: 10001; background: #000; }
` });
await page.evaluate(() => {
  const c = document.createElement("div"); c.id = "demo-caption"; c.style.opacity = "0"; document.body.appendChild(c);
  const m = document.createElement("div"); m.id = "demo-marker"; document.body.appendChild(m);
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
const clockAtLeast = (mmss, timeout) => page.waitForFunction(
  (target) => {
    const [m, s] = (document.querySelector(".scoreboard .clock")?.textContent ?? "0:00").split(":").map(Number);
    const [tm, ts] = target.split(":").map(Number);
    return m * 60 + s >= tm * 60 + ts;
  }, mmss, { timeout }).catch(() => {});

let i = 0;
async function segment(seg, actions) {
  const start = Date.now();
  await page.evaluate((c) => { document.getElementById("demo-marker").style.background = c; }, MARKERS[i++]);
  await caption(seg.caption);
  await actions();
  const left = seg.dur_s * 1000 - (Date.now() - start);
  if (left > 0) await sleep(left);
}
const S = Object.fromEntries(segs.map((s) => [s.id, s]));

await segment(S.s1, async () => {            // overview
  await click("BOTH");
  await select("16", "4");
  await seek(20);
});
await segment(S.s2, async () => {            // the raw feed, live
  await click("DATA");
  await select("16", "8");
});
await segment(S.s3, async () => {            // forecast + goal at 2:22, real time
  await click("BOTH");
  await seek(134);
  await select("16", "1");
});
await segment(S.s4, async () => {            // agents, analyst mode, into the 3:16 save
  await click("Analyst");
  await select("16", "4");
  await clockAtLeast("3:08", 15000);
  await select("16", "1");
});
await segment(S.s5, async () => {            // ask the AI
  const input = page.locator(".ask-form input");
  await input.click();
  await input.pressSequentially("Who has been the best player so far, and why?", { delay: 35 });
  await input.press("Enter");
  await page.waitForSelector(".ask .answer", { timeout: 15000 }).catch(() => console.log("no answer"));
});
await segment(S.s6, async () => {            // persona: casual, Turkish, follow the home No.10 into the 7:15 equaliser
  await click("Casual fan");
  await select("tr", "tr");
  await select("a10", "h10");
  await click("3D");
  await seek(426);
  await select("16", "1");
});
await segment(S.s7, async () => {            // recap
  await select("tr", "en");
  await click("BOTH");
  await page.getByRole("button", { name: /Pause/ }).click();
  const btn = page.getByRole("button", { name: "Generate" });
  await btn.scrollIntoViewIfNeeded();
  await btn.click();
  await page.waitForSelector("text=Northbridge FC 2-2 Riverside Athletic", { timeout: 40000 }).catch(() => console.log("recap not shown"));
});
await segment(S.s8, async () => {            // title card
  await caption("");
  await page.evaluate(() => { document.getElementById("demo-title").style.display = "flex"; });
});

const video = page.video();
await context.close();
await browser.close();
fs.renameSync(await video.path(), "raw.webm");
console.log("done");
