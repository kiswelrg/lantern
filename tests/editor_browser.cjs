// Optional UI check with an installed Playwright and Chrome. No project dependencies.
// LANTERN_PLAYWRIGHT=/path/to/playwright node tests/editor_browser.cjs
const {chromium} = require(process.env.LANTERN_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {spawn} = require('node:child_process');
const {setTimeout: pause} = require('node:timers/promises');

async function freePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

(async () => {
  const src = path.resolve(__dirname, '..');
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'lantern-editor-browser-'));
  const root = path.join(fixture, 'root');
  fs.mkdirSync(path.join(root, 'sites', 'demo'), {recursive: true});
  fs.mkdirSync(path.join(root, 'apps'), {recursive: true});
  for (const name of ['Caddyfile', '_shared', 'server']) {
    fs.cpSync(path.join(src, name), path.join(root, name), {recursive: true});
  }
  const readme = path.join(root, 'sites/demo/README.md');
  const original = '---\r\ntitle: Browser demo\r\n---\r\n# Browser demo\r\n\r\nOriginal 雪.\r\n\r\n' +
    Array.from({length: 100}, (_, index) => `Line ${index + 1}: A long README should scroll inside a large editor.`).join('\r\n') + '\r\n';
  fs.writeFileSync(readme, original);
  fs.writeFileSync(path.join(root, 'sites/demo/notes.md'), '# Other Markdown\n');
  const port = await freePort();
  const adminPort = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const env = {...process.env, LANTERN_ROOT: root, LANTERN_PORT: String(port), LANTERN_ADMIN_PORT: String(adminPort),
    XDG_CONFIG_HOME: path.join(fixture, 'config'), XDG_DATA_HOME: path.join(fixture, 'data')};
  const children = [];
  function start(command, args, name) {
    const log = fs.openSync(path.join(fixture, name + '.log'), 'w');
    const child = spawn(command, args, {env, stdio: ['ignore', log, log]});
    fs.closeSync(log);
    children.push(child);
    return child;
  }
  let browser;
  try {
    start('caddy', ['run', '--config', path.join(root, 'Caddyfile'), '--adapter', 'caddyfile'], 'caddy');
    start('uv', ['run', '--no-project', 'python', path.join(root, 'server/editor.py')], 'editor');
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        const response = await fetch(base + '/_editor/health');
        ready = response.ok && (await response.json()).ok;
      } catch {}
      if (ready) break;
      if (children.some(child => child.exitCode !== null)) throw new Error('Fixture server exited: ' + fixture);
      await pause(100);
    }
    assert(ready, 'Fixture servers did not start: ' + fixture);
    browser = await chromium.launch({headless: true,
      executablePath: process.env.LANTERN_CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox']});
    const context = await browser.newContext({viewport: {width: 1280, height: 900}});
    const page = await context.newPage();
    const errors = [], mutations = [], historyRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.method() === 'PUT') mutations.push({method: request.method(), url: request.url(), body: request.postDataJSON()});
      if (/\/_editor\/(diff|revision)\?/.test(request.url())) historyRequests.push(request.url());
    });
    await page.goto(base + '/demo/');
    // Headless Chrome has no extensions; check the fallback registry separately.
    const webmcp = await page.evaluate(() => !!globalThis.__PLUNO_WEBMCP_TOOLS__);
    assert.equal(await page.locator('.lantern-bar #readme-edit').count(), 1, 'Keep the actions in the breadcrumb bar');
    await page.screenshot({path: path.join(fixture, 'readme-desktop.png')});
    await page.getByRole('button', {name: 'Edit README', exact: true}).click();
    const source = page.locator('#readme-source'), save = page.locator('#readme-save');
    await source.waitFor({state: 'visible'});
    await page.waitForFunction(() => !document.getElementById('readme-source').disabled);
    assert.equal(await save.isDisabled(), true, 'CRLF source should not start dirty');
    assert.match(await page.locator('#readme-editor-status').innerText(), /Editor 127\.0\.0\.1/);
    async function editorLayout() {
      const layout = await page.evaluate(() => {
        const source = document.getElementById('readme-source');
        const rect = source.getBoundingClientRect();
        const footer = document.querySelector('.readme-editor-footer').getBoundingClientRect();
        const dialog = document.getElementById('readme-editor');
        return {width: rect.width, height: rect.height, viewportWidth: innerWidth, viewportHeight: innerHeight,
          fontSize: parseFloat(getComputedStyle(source).fontSize), footerBottom: footer.bottom,
          dialogScrolls: dialog.scrollHeight > dialog.clientHeight};
      });
      assert(layout.width >= layout.viewportWidth * 0.9, 'Editor should use the window width: ' + JSON.stringify(layout));
      assert(layout.height >= layout.viewportHeight * 0.65, 'Source should fill most of the window height: ' + JSON.stringify(layout));
      assert(layout.fontSize >= 16, 'Use a readable font size');
      assert(layout.footerBottom <= layout.viewportHeight, 'Save and Cancel must stay visible');
      assert.equal(layout.dialogScrolls, false, 'Scroll the source, keeping the footer fixed');
      return layout;
    }
    const desktopLayout = await editorLayout();
    assert.equal(await source.evaluate(el => el.scrollTop), 0, 'Open long READMEs at the beginning');
    assert.equal(await source.evaluate(el => el.scrollHeight > el.clientHeight), true, 'Long source scrolls inside the editor');
    await page.screenshot({path: path.join(fixture, 'editor-desktop.png')});
    await source.fill((await source.inputValue()) + '\nSaved from the UI.\n');
    await Promise.all([page.waitForEvent('load'), save.click()]);
    await page.getByText('Saved from the UI.', {exact: true}).waitFor();
    assert(fs.readFileSync(readme, 'utf8').includes('Saved from the UI.\r\n'), 'Preserve CRLF newlines');
    assert.equal(mutations.length, 1);
    await page.getByRole('button', {name: 'History', exact: true}).click();
    await page.locator('#readme-history-list summary').waitFor();
    assert.match(await page.locator('#readme-history-list').innerText(), /Editor 127\.0\.0\.1/);
    await page.locator('#readme-history-list summary').click();
    await page.locator('.readme-diff').waitFor();
    assert.equal(await page.locator('.readme-diff-delete').count(), 0);
    assert.equal(await page.locator('.readme-diff-add').count(), 2);
    assert((await page.locator('.readme-diff-add .readme-diff-text').allTextContents()).includes('Saved from the UI.'));
    assert(await page.locator('.readme-diff-context').count() <= 3, 'Only nearby unchanged lines should be shown');
    assert(!(await page.locator('.readme-diff').innerText()).includes('Line 1:'), 'Omit unrelated source');
    assert.equal(await page.locator('#readme-history-list pre').count(), 0, 'No full-file source panels');
    await page.screenshot({path: path.join(fixture, 'history-desktop.png')});
    await page.getByRole('button', {name: 'Close', exact: true}).click();

    // Another tab's save must leave this tab's unsaved text visible on a conflict.
    await page.getByRole('button', {name: 'Edit README', exact: true}).click();
    await page.waitForFunction(() => !document.getElementById('readme-source').disabled);
    await source.fill('# My pending edit\n');
    const other = await context.newPage();
    await other.goto(base + '/demo/README.md');
    await other.getByRole('button', {name: 'Edit README', exact: true}).click();
    await other.waitForFunction(() => !document.getElementById('readme-source').disabled);
    await other.locator('#readme-source').fill('# Saved in another tab\n');
    await Promise.all([other.waitForEvent('load'), other.locator('#readme-save').click()]);
    await save.click();
    await page.locator('#readme-editor-status.error').waitFor();
    assert.match(await page.locator('#readme-editor-status').innerText(), /changed since you opened/);
    assert.equal(await source.inputValue(), '# My pending edit\n');
    assert.equal(fs.readFileSync(readme, 'utf8'), '# Saved in another tab\r\n');
    page.once('dialog', dialog => dialog.dismiss());
    await page.getByRole('button', {name: 'Cancel', exact: true}).click();
    assert.equal(await page.locator('#readme-editor').isVisible(), true);
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', {name: 'Cancel', exact: true}).click();
    await page.locator('#readme-editor').waitFor({state: 'hidden'});

    // Both removed and added diff lines must be inert even when they contain HTML.
    const malicious = '<script>window.historyScriptRan = true</script>\n<img src=x onerror="window.historyScriptRan=true">';
    const escapedHistory = async route => route.fulfill({json: {
      additions: 2, deletions: 1, hunks: [{old_start: 1, old_count: 1, new_start: 1, new_count: 2, lines: [
        {kind: 'delete', old_line: 1, new_line: null, text: '<b>Old Markdown</b>'},
        ...malicious.split('\n').map((text, index) => ({kind: 'add', old_line: null, new_line: index + 1, text}))
      ]}]
    }});
    await page.route('**/_editor/diff?*', escapedHistory);
    await page.getByRole('button', {name: 'History', exact: true}).click();
    await page.locator('#readme-history-list summary').first().click();
    await page.locator('.readme-diff').waitFor();
    assert.deepEqual(await page.locator('.readme-diff-add .readme-diff-text').allTextContents(), malicious.split('\n'));
    assert.equal(await page.locator('.readme-diff-delete .readme-diff-text').innerText(), '<b>Old Markdown</b>');
    assert.equal(await page.locator('.readme-diff script, .readme-diff img, .readme-diff b').count(), 0);
    assert.equal(await page.evaluate(() => window.historyScriptRan), undefined);
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.equal(await page.locator('#readme-history-dialog').evaluate(el => el.scrollWidth > el.clientWidth), false);
    await page.screenshot({path: path.join(fixture, 'history-mobile.png')});
    await page.getByRole('button', {name: 'Close', exact: true}).click();
    await page.getByRole('button', {name: 'Edit README', exact: true}).click();
    await page.waitForFunction(() => !document.getElementById('readme-source').disabled);
    assert.equal(await page.locator('#readme-editor').evaluate(el => el.scrollWidth > el.clientWidth), false);
    const mobileLayout = await editorLayout();
    await page.screenshot({path: path.join(fixture, 'editor-mobile.png')});
    await page.getByRole('button', {name: 'Cancel', exact: true}).click();
    await page.screenshot({path: path.join(fixture, 'readme-mobile.png')});
    await page.setViewportSize({width: 1280, height: 900});
    await page.emulateMedia({colorScheme: 'dark'});
    await page.getByRole('button', {name: 'History', exact: true}).click();
    await page.locator('#readme-history-list summary').first().click();
    await page.locator('.readme-diff').waitFor();
    await page.screenshot({path: path.join(fixture, 'history-dark.png')});
    await page.getByRole('button', {name: 'Close', exact: true}).click();
    await page.getByRole('button', {name: 'Edit README', exact: true}).click();
    await page.waitForFunction(() => !document.getElementById('readme-source').disabled);
    await editorLayout();
    await page.screenshot({path: path.join(fixture, 'editor-dark.png')});
    await page.getByRole('button', {name: 'Cancel', exact: true}).click();
    await page.goto(base + '/demo/notes.md');
    assert.equal(await page.locator('#readme-edit').count(), 0);
    assert.deepEqual(errors, []);
    assert(mutations.every(request => request.url.startsWith(base + '/_editor/document?')));
    assert(historyRequests.length > 0 && historyRequests.every(url => url.includes('/_editor/diff?')), 'Fetch compact diffs for history');
    console.log(JSON.stringify({status: 'passed', saveAndReload: true, crlfPreserved: true,
      historyAndIp: true, compactLineDiffs: true, staleSaveRetainsInput: true, cancelPreservesInput: true,
      inertHistoryHtml: true, mobileOverflow: false, desktopLayout, mobileLayout, pageErrors: errors,
      webmcpRegistryAvailable: webmcp, screenshots: fixture}, null, 2));
  } finally {
    if (browser) await browser.close();
    for (const child of children) child.kill('SIGTERM');
    await Promise.all(children.filter(child => child.exitCode === null).map(child =>
      new Promise(resolve => child.once('exit', resolve))));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
