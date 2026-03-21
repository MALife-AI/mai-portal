#!/usr/bin/env node
/**
 * 기능 가이드용 스크린샷 자동 캡처 (Puppeteer)
 *
 * 설치: npm install puppeteer
 * 실행: node docs/capture-screenshots.js
 *
 * 서버가 localhost:5173 (프론트) + localhost:9001 (백엔드)에서 실행 중이어야 합니다.
 */

const puppeteer = require('puppeteer');
const path = require('path');

const BASE = 'http://localhost:5173';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');
const VIEWPORT = { width: 1440, height: 900 };

const PAGES = [
  { name: 'dashboard', path: '/', wait: 2000 },
  { name: 'vault', path: '/vault', wait: 2000 },
  { name: 'agent', path: '/agent', wait: 2000 },
  { name: 'agent-model-selector', path: '/agent', wait: 2000, clip: { x: 0, y: 600, width: 1440, height: 300 } },
  { name: 'ingest', path: '/ingest', wait: 2000 },
  { name: 'search', path: '/search', wait: 2000 },
  { name: 'graph', path: '/graph', wait: 4000 },
  { name: 'skills', path: '/skills', wait: 2000 },
  { name: 'skills-marketplace', path: '/skills', wait: 2000, clickTab: 2 },
  { name: 'admin', path: '/admin', wait: 2000 },
  { name: 'admin-iam', path: '/admin', wait: 2000, clickTab: 1 },
  { name: 'admin-departments', path: '/admin', wait: 2000, clickTab: 2 },
  { name: 'admin-model', path: '/admin', wait: 2000, clickTab: 3 },
  { name: 'admin-metrics', path: '/admin', wait: 2000, clickTab: 4 },
  { name: 'admin-governance', path: '/admin', wait: 2000, clickTab: 5 },
  { name: 'admin-infra', path: '/admin', wait: 2000, clickTab: 6 },
];

(async () => {
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  await page.setViewport(VIEWPORT);

  // Set user to admin01
  await page.goto(BASE);
  await page.evaluate(() => localStorage.setItem('malife_user_id', 'admin01'));

  for (const pg of PAGES) {
    console.log(`Capturing: ${pg.name}...`);
    await page.goto(`${BASE}${pg.path}`, { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, pg.wait));

    // Click tab if specified
    if (pg.clickTab !== undefined) {
      const tabs = await page.$$('button');
      const tabButtons = [];
      for (const btn of tabs) {
        const text = await btn.evaluate(el => el.textContent);
        if (text && btn.isIntersectingViewport()) {
          tabButtons.push(btn);
        }
      }
      if (tabButtons[pg.clickTab]) {
        await tabButtons[pg.clickTab].click();
        await new Promise(r => setTimeout(r, 1500));
      }
    }

    const opts = {
      path: path.join(SCREENSHOT_DIR, `${pg.name}.png`),
      type: 'png',
    };
    if (pg.clip) opts.clip = pg.clip;
    else opts.fullPage = false;

    await page.screenshot(opts);
    console.log(`  -> ${pg.name}.png`);
  }

  // Dark/Light mode screenshots
  console.log('Capturing: dark-mode...');
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle2' });
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('malife_theme', 'dark');
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'dark-mode.png') });

  console.log('Capturing: light-mode...');
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'light');
    localStorage.setItem('malife_theme', 'light');
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'light-mode.png') });

  await browser.close();
  console.log(`\nDone! ${PAGES.length + 2} screenshots saved to docs/screenshots/`);
})();
