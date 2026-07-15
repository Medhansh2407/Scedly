import fs from 'fs';
import path from 'path';

export function renderMockPage(filename: string) {
  const html = fs.readFileSync(path.join(process.cwd(), 'public', filename), 'utf-8');
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
  const body = bodyMatch ? bodyMatch[1] : '';
  const fixed = body
    .replace(/href="index\.html"/g, 'href="/"')
    .replace(/href="app\.html"/g, 'href="/app"')
    .replace(/href="login\.html"/g, 'href="/login"')
    .replace(/href="settings\.html"/g, 'href="/settings"')
    .replace(/href="onboarding\.html"/g, 'href="/onboarding"');
  return fixed;
}
