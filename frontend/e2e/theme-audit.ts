import {expect, type Page} from '@playwright/test';

// Check the rendered cascade, not just the token definitions. Inherited legacy
// foregrounds and white backgrounds can pass a token-only theme test.
export async function expectReadableDarkUI(page: Page) {
  const problems = await page.evaluate(() => {
    const rgb = (value: string) => (value.match(/[\d.]+/g) || []).map(Number);
    const luminance = (channels: number[]) => channels.slice(0, 3).map(value => {
      const n = value / 255;
      return n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4;
    }).reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0);
    const background = (el: Element | null): number[] => {
      if (!el) return [24, 28, 27];
      const color = rgb(getComputedStyle(el).backgroundColor);
      const alpha = color[3] ?? 1;
      if (alpha >= 1) return color;
      const behind = background(el.parentElement);
      return color.slice(0, 3).map((value, i) => value * alpha + behind[i] * (1 - alpha));
    };
    const failures: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>('#root *')) {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (!rect.width || !rect.height || rect.bottom < 0 || rect.top > innerHeight || rect.right < 0 || rect.left > innerWidth ||
          style.visibility === 'hidden' || style.display === 'none' || el.closest('[data-design-preview], [disabled], fieldset[disabled]')) continue;
      if (el.closest('details:not([open])') && el.tagName !== 'SUMMARY') continue;
      const ownBackground = rgb(style.backgroundColor);
      const name = `${el.tagName.toLowerCase()}.${el.className}`;
      if ((ownBackground[3] ?? 1) > .9 && luminance(ownBackground) > .8) failures.push(`${name}: light background ${style.backgroundColor}`);
      if (!Array.from(el.childNodes).some(node => node.nodeType === Node.TEXT_NODE && node.textContent?.trim())) continue;
      // Respect clipped content (horizontal tables and hidden rail labels).
      if (el.getClientRects().length === 0) continue;
      const fg = luminance(rgb(style.color)), bg = luminance(background(el));
      const ratio = (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05);
      const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700);
      if (ratio < (large ? 3 : 4.5)) failures.push(`${name}: contrast ${ratio.toFixed(2)} (${el.textContent?.trim().slice(0, 65)})`);
    }
    return [...new Set(failures)];
  });
  expect(problems, 'Rendered UI must not leak light-theme surfaces or low-contrast text').toEqual([]);
}
