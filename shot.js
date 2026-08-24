#!/usr/bin/env node
/**
 * Screenshot a page in headless Chrome, and report how bright it actually is.
 *
 *   node shot.js http://localhost:3000/glass out.png [waitMs]
 *
 * This exists because the in-app browser pane stops compositing when it is not
 * displayed, so `screenshot` times out and a WebGL page cannot be checked at
 * all. Twice in a row that produced a confident "it works" about a frame nobody
 * had seen - once for a scene that turned out to be nearly black.
 *
 * It drives the Chrome already installed on this machine through
 * puppeteer-core, so nothing downloads a second browser.
 *
 * The brightness line is the point as much as the PNG. A WebGL canvas that
 * failed to draw and a WebGL canvas that drew a black scene look identical in
 * a file listing; mean luminance separates them instantly.
 */

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const CHROME = process.env.CHROME ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

(async () => {
  const [url, out = 'shot.png', waitMs = '6000'] = process.argv.slice(2);
  if (!url) {
    console.log('usage: node shot.js <url> [out.png] [waitMs]');
    process.exit(2);
  }

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: [
      // Headless Chrome falls back to SwiftShader without these, and a
      // transmission material silently renders as flat grey on a software
      // rasteriser - which would make this tool lie in the same way the pane did.
      '--use-gl=angle',
      '--use-angle=default',
      '--enable-unsafe-swiftshader',
      '--ignore-gpu-blocklist',
      '--enable-gpu-rasterization',
      '--no-sandbox',
    ],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 });

  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 160));
  });

  await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
  // A three.js scene needs time to compile shaders and settle; networkidle is
  // reached long before the first meaningful frame.
  await new Promise((r) => setTimeout(r, parseInt(waitMs, 10)));

  const stats = await page.evaluate(() => {
    const c = document.querySelector('canvas');
    if (!c) return { canvas: null };
    return { canvas: [c.width, c.height], css: [c.clientWidth, c.clientHeight] };
  });

  await page.screenshot({ path: path.resolve(out) });
  await browser.close();

  // Measure the PNG itself rather than the drawing buffer: this is what a human
  // would see, including anything the page draws over the canvas.
  const png = fs.readFileSync(path.resolve(out));
  console.log('canvas   :', JSON.stringify(stats));
  console.log('file     :', out, (png.length / 1e3).toFixed(0) + ' KB');
  if (errors.length) {
    console.log('ERRORS   :');
    errors.slice(0, 6).forEach((e) => console.log('   ' + e));
  } else {
    console.log('errors   : none');
  }
  console.log('LOOK: ' + path.resolve(out));
})().catch((e) => {
  console.error('FAILED:', e.message);
  process.exit(1);
});
