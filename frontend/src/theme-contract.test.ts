// @vitest-environment node
/// <reference types="node" />
import {readFileSync, readdirSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {expect, it} from 'vitest';

const source = resolve('src');
const read = (name: string) => readFileSync(join(source, name), 'utf8');

it('keeps CSS in one explicit cascade instead of unlayered component imports', () => {
  const entry = read('app.css');
  expect(entry).toContain('@layer legacy, theme;');
  for (const name of readdirSync(source).filter(name => name.endsWith('.css') && !['app.css', 'ITGTheme.css'].includes(name))) {
    expect(entry, `${name} must stay in the legacy layer`).toContain(`@import './${name}' layer(legacy);`);
  }
  expect(entry).toContain("@import './ITGTheme.css' layer(theme);");
  for (const name of readdirSync(source).filter(name => name.endsWith('.tsx') && name !== 'main.tsx')) {
    expect(read(name), `${name} must not bypass cascade layers`).not.toMatch(/import\s+['"][^'"]+\.css['"]/);
  }
});

it('keeps theme precedence independent of root IDs, classless buttons and important flags', () => {
  const theme = read('ITGTheme.css');
  expect(theme).not.toContain('#root');
  expect(theme).not.toContain('!important');
  expect(theme).not.toMatch(/:not\(\[class\]\)\s*\{/);
});
