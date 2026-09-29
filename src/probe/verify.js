// ShotSense Data Probe — headless verification harness (retro / accordion build)
// 用法： NODE_PATH=/Users/js/.workbuddy-ai/binaries/node/workspace/node_modules \
//        /Users/js/.workbuddy-ai/binaries/node/versions/22.22.2-3/bin/node src/probe/verify.js
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const URL = 'file://' + path.resolve(__dirname, '../../index.html');
const OUT = '/tmp/probe-shots';
fs.mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log((ok ? '  PASS  ' : '  FAIL  ') + name + (detail ? '  — ' + detail : ''));
}

/* the page is a long accordion stack, so always bring the chart on screen
   before converting data coordinates into viewport pixels */
async function pointIn(page, chartId, seriesIdx, dataIdx) {
  await page.evaluate(id => document.getElementById(id).scrollIntoView({ block: 'center', behavior: 'instant' }), chartId);
  await sleep(700);
  return page.evaluate((id, si, di) => {
    const el = document.getElementById(id);
    const c = echarts.getInstanceByDom(el);
    const d = c.getOption().series[si].data[di];
    const v = (d && d.value !== undefined) ? d.value : d;
    const px = c.convertToPixel({ seriesIndex: si }, v);
    const r = el.getBoundingClientRect();
    return { x: r.left + px[0], y: r.top + px[1], w: r.width, h: r.height, v: v };
  }, chartId, seriesIdx, dataIdx);
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1'],
    defaultViewport: { width: 1720, height: 1180 }
  });
  const page = await browser.newPage();
  const errors = [], warns = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => {
    const t = m.type(), x = m.text();
    if (t === 'error') errors.push('CONSOLE: ' + x);
    else if (t === 'warning') warns.push(x);
  });

  const t0 = Date.now();
  await page.goto(URL, { waitUntil: 'load', timeout: 240000 });
  await page.waitForFunction('window.PROBE_READY === true', { timeout: 240000, polling: 400 });
  console.log('READY in ' + ((Date.now() - t0) / 1000).toFixed(2) + ' s');
  await page.waitForFunction(
    () => { const b = document.getElementById('boot'); return b && b.style.display === 'none'; },
    { timeout: 20000 });
  /* the page uses smooth scrolling; the harness needs instant jumps so that
     coordinates taken from getBoundingClientRect stay valid */
  await page.addStyleTag({ content: 'html{scroll-behavior:auto !important}' });
  await sleep(500);

  /* ---------- 1. statistics cross-validation vs pandas ---------- */
  const stats = await page.evaluate(() => {
    const out = {};
    ['shot_dist_calc', 'touch_time', 'close_def_dist', 'score_margin_at_shot',
     'team_rolling_fg_last_10', 'age_at_season', 'shot_clock', 'height_in',
     'player_rolling_fg_last_5', 'rest_days'].forEach(n => { out[n] = window.PROBE_STATS(n); });
    const cols = window.PROBE_COLS();
    out.__cat = cols.filter(s => s.endsWith(':cat')).length;
    out.__num = cols.filter(s => s.endsWith(':num')).length;
    return out;
  });
  console.log('\n--- STATS ---');
  Object.keys(stats).forEach(k => {
    const s = stats[k];
    if (typeof s === 'number') { console.log('  ' + k + ' = ' + s); return; }
    console.log('  ' + k.padEnd(26) + ' n=' + s.n + ' mean=' + s.mean.toPrecision(8) +
      ' std=' + s.std.toPrecision(6) + ' skew=' + s.skew.toPrecision(6) +
      ' kurt=' + s.kurt.toPrecision(6) + ' med=' + (s.median === undefined ? '-' : s.median.toPrecision(8)));
  });

  /* ---------- 2. boot / structural sanity ---------- */
  const struct = await page.evaluate(() => {
    const cards = Array.prototype.map.call(document.querySelectorAll('.card'), c => ({
      id: c.id, open: c.classList.contains('open'),
      title: c.querySelector('.card-title').textContent,
      digest: c.querySelector('.card-digest').textContent.trim().slice(0, 60)
    }));
    return {
      cards,
      lang: window.PROBE_LANG,
      open: window.PROBE_OPEN,
      fontsLoaded: document.fonts ? document.fonts.size : -1,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      header: document.getElementById('mShots').textContent + ' / ' +
              document.getElementById('mPlayers').textContent + ' / ' +
              document.getElementById('mParams').textContent + ' / ' +
              document.getElementById('mFg').textContent,
      langbar: !!document.querySelector('.langbar .langbtn'),
      noNeon: getComputedStyle(document.body).backgroundImage.indexOf('gradient') < 0,
      i18nEmpty: Array.prototype.filter.call(document.querySelectorAll('[data-i18n]'),
        n => !n.textContent.trim() && !n.querySelector('*')).map(n => n.dataset.i18n),
      stampWidths: Array.prototype.map.call(document.querySelectorAll('.stamprow .stamp'),
        s => Math.round(s.getBoundingClientRect().width)),
      btnWidths: Array.prototype.map.call(document.querySelectorAll('.toolbar .btn'),
        b => b.textContent.trim() + '=' + Math.round(b.getBoundingClientRect().width)),
      cardTitles: Array.prototype.map.call(document.querySelectorAll('.card-title'), c => c.textContent),
      mcellLabels: Array.prototype.map.call(document.querySelectorAll('.mcell .k'), c => c.textContent),
      stampText: Array.prototype.map.call(document.querySelectorAll('.stamprow .stamp'), s => s.textContent)
    };
  });
  console.log('\n--- STRUCTURE ---');
  struct.cards.forEach(c => console.log('  [' + (c.open ? 'X' : ' ') + '] ' + c.id.padEnd(12) + c.title + '   |  ' + c.digest));
  console.log('  header  : ' + struct.header);
  console.log('  langbar : ' + struct.langbar + '   lang=' + struct.lang);
  console.log('  bodyBg  : ' + struct.bodyBg + '   noGradient=' + struct.noNeon);
  check('10 accordion cards present', struct.cards.length === 10, struct.cards.length + ' cards');
  check('default: only 00+01 open', struct.open.length === 2 && struct.open.includes('s-select') && struct.open.includes('s-profile'),
    JSON.stringify(struct.open));
  check('language bar exists', struct.langbar === true);
  check('canvas background is #F4F1DE', struct.bodyBg === 'rgb(244, 241, 222)', struct.bodyBg);
  check('no CSS gradients on body', struct.noNeon === true);
  console.log('  stamps  : ' + JSON.stringify(struct.stampText));
  console.log('  buttons : ' + struct.btnWidths.join('  '));
  console.log('  titles  : ' + struct.cardTitles.join(' / '));
  console.log('  mcell   : ' + struct.mcellLabels.join(' / '));
  check('every data-i18n node has boot-time text', struct.i18nEmpty.length === 0,
    struct.i18nEmpty.length ? 'empty: ' + struct.i18nEmpty.join(',') : 'all filled');
  check('rubber stamps are not collapsed', struct.stampWidths.every(w => w > 60), JSON.stringify(struct.stampWidths));
  check('toolbar buttons are not collapsed', struct.btnWidths.every(b => Number(b.split('=')[1]) > 45),
    struct.btnWidths.join(' '));
  check('all 10 card titles have text', struct.cardTitles.every(x => x.trim().length > 0),
    struct.cardTitles.filter(x => !x.trim()).length + ' empty');

  /* ---------- 3. fonts actually applied ---------- */
  await page.evaluate(() => document.fonts.ready);
  const fontInfo = await page.evaluate(() => {
    const faces = Array.from(document.fonts).map(f => f.family + '/' + f.weight + '/' + f.status);
    return {
      heading: getComputedStyle(document.querySelector('.masthead h1')).fontFamily,
      value: getComputedStyle(document.querySelector('#mShots')).fontFamily,
      stat: getComputedStyle(document.querySelector('#statCards .stat .v')).fontFamily,
      label: getComputedStyle(document.querySelector('.masthead .dek')).fontFamily,
      faces: faces.filter((x, i, a) => a.indexOf(x) === i),
      checkSerif: document.fonts.check('900 40px "Playfair Display"'),
      checkMono: document.fonts.check('400 14px "JetBrains Mono"'),
      checkSans: document.fonts.check('400 14px "Inter"'),
      distinct: faces.length
    };
  });
  console.log('\n--- FONTS ---');
  console.log('  heading : ' + fontInfo.heading);
  console.log('  metric  : ' + fontInfo.value);
  console.log('  statcard: ' + fontInfo.stat);
  console.log('  label   : ' + fontInfo.label);
  console.log('  faces   : ' + fontInfo.distinct);
  fontInfo.faces.forEach(f => console.log('   - ' + f));
  check('Playfair Display on headings', /Playfair/.test(fontInfo.heading), fontInfo.heading);
  check('JetBrains Mono on metric values', /JetBrains/.test(fontInfo.value), fontInfo.value);
  check('JetBrains Mono on stat cards', /JetBrains/.test(fontInfo.stat), fontInfo.stat);
  check('Inter on body labels', /Inter/.test(fontInfo.label), fontInfo.label);
  check('8 embedded @font-face faces registered', fontInfo.distinct === 8, fontInfo.distinct + ' faces');
  check('all three families resolve in the font cache',
    fontInfo.checkSerif && fontInfo.checkMono && fontInfo.checkSans,
    'serif=' + fontInfo.checkSerif + ' mono=' + fontInfo.checkMono + ' sans=' + fontInfo.checkSans);

  await page.screenshot({ path: OUT + '/01-default.png' });

  /* ---------- 3b. switch to a numeric α for the shape cards ---------- */
  await page.evaluate(() => {
    const s = document.getElementById('selA');
    s.value = 'shot_dist_calc'; s.dispatchEvent(new Event('change', { bubbles: true }));
    const b = document.getElementById('selB');
    b.value = 'touch_time'; b.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await sleep(1200);

  /* ---------- 4. open the distribution card ---------- */
  await page.evaluate(() => document.querySelector('.card-head[data-toggle="s-dist"]').click());
  await sleep(1600);
  const dist = await page.evaluate(() => {
    const c = echarts.getInstanceByDom(document.getElementById('cDist'));
    const o = c.getOption();
    return {
      title: document.getElementById('distTitle').textContent,
      sub: document.getElementById('distSub').textContent,
      types: o.series.map(s => s.type),
      counts: o.series.map(s => (s.data ? s.data.length : 0)),
      axisColor: o.xAxis[0].axisLine.lineStyle.color,
      splitColor: o.xAxis[0].splitLine.lineStyle.color,
      note: document.getElementById('distNote').innerText.replace(/\n+/g, ' ').slice(0, 170)
    };
  });
  console.log('\n--- DISTRIBUTION ---');
  console.log(JSON.stringify(dist, null, 1));
  check('histogram custom series drawn', dist.types[0] === 'custom' && dist.counts[0] > 5, JSON.stringify(dist.types));
  check('KDE line overlaid', dist.types[1] === 'line', JSON.stringify(dist.types));
  check('axis line is ink navy', dist.axisColor === '#1D3557', dist.axisColor);
  check('grid line is vintage paper', dist.splitColor === '#E5E0D8', dist.splitColor);
  await page.screenshot({ path: OUT + '/02-dist.png' });

  /* ---------- 5. Q-Q + box ---------- */
  await page.evaluate(() => {
    document.querySelector('.card-head[data-toggle="s-qq"]').click();
    document.querySelector('.card-head[data-toggle="s-outlier"]').click();
  });
  await sleep(1600);
  const qqbox = await page.evaluate(() => {
    const q = echarts.getInstanceByDom(document.getElementById('cQq'));
    const b = echarts.getInstanceByDom(document.getElementById('cBox'));
    return {
      qqSeries: q ? q.getOption().series.map(s => s.name + '(' + (s.data ? s.data.length : 0) + ')') : null,
      qqCards: Array.prototype.map.call(document.querySelectorAll('#qqCards .stat'),
        d => d.querySelector('.k').textContent + '=' + d.querySelector('.v').textContent),
      boxSeries: b ? b.getOption().series.map(s => s.name + '(' + (s.data ? s.data.length : 0) + ')') : null,
      boxCards: Array.prototype.map.call(document.querySelectorAll('#boxCards .stat'),
        d => d.querySelector('.k').textContent + '=' + d.querySelector('.v').textContent),
      boxSub: document.getElementById('boxSub').textContent
    };
  });
  console.log('\n--- QQ / BOX ---');
  console.log(JSON.stringify(qqbox, null, 1));
  check('Q-Q has reference line + sample', qqbox.qqSeries && qqbox.qqSeries.length === 2, JSON.stringify(qqbox.qqSeries));
  check('box has custom box + fliers', qqbox.boxSeries && qqbox.boxSeries.length === 2, JSON.stringify(qqbox.boxSeries));
  await page.screenshot({ path: OUT + '/03-qq-box.png' });

  /* ---------- 6. bivariate + real hover/click ---------- */
  await page.evaluate(() => document.querySelector('.card-head[data-toggle="s-pair"]').click());
  await sleep(1800);
  const pair = await page.evaluate(() => {
    const c = echarts.getInstanceByDom(document.getElementById('cPair'));
    return {
      title: document.getElementById('pairTitle').textContent,
      sub: document.getElementById('pairSub').textContent,
      series: c ? c.getOption().series.map(s => s.name + '(' + (s.data ? s.data.length : 0) + ')') : null
    };
  });
  console.log('\n--- PAIR ---');
  console.log(JSON.stringify(pair, null, 1));
  await page.screenshot({ path: OUT + '/04-pair.png' });

  const pt = await pointIn(page, 'cPair', 0, 1200);
  await page.mouse.move(pt.x, pt.y);
  await sleep(900);
  await page.screenshot({ path: OUT + '/05-hover.png' });
  const tipText = await page.evaluate(() => {
    const cands = Array.prototype.filter.call(document.querySelectorAll('div'), d => {
      const cs = getComputedStyle(d);
      return cs.position === 'absolute' && d.innerText && d.innerText.trim().length > 4 &&
             d.getBoundingClientRect().width > 20;
    });
    return cands.length ? cands[cands.length - 1].innerText.replace(/\n+/g, ' | ') : '(no tooltip)';
  });
  console.log('  hover tooltip: ' + tipText.slice(0, 200));
  check('hover tooltip shows a record', /day|MADE|MISS|shot_dist|touch_time/i.test(tipText), tipText.slice(0, 90));

  await page.mouse.click(pt.x, pt.y);
  await sleep(900);
  const detail = await page.evaluate(() => {
    const d = document.getElementById('probeDetail');
    return { cls: d.className, lines: d.innerText.split('\n').length,
             head: d.innerText.split('\n').slice(0, 5).join(' | ') };
  });
  console.log('  inspector: ' + JSON.stringify(detail));
  check('click populates the point inspector', detail.lines > 50 && /SHOT RECORD/.test(detail.head), detail.head);
  await page.screenshot({ path: OUT + '/06-inspector.png' });

  /* ---------- 7. association card ---------- */
  await page.evaluate(() => document.querySelector('.card-head[data-toggle="s-rel"]').click());
  await sleep(900);
  const rel = await page.evaluate(() => ({
    name: document.getElementById('relName').textContent,
    val: document.getElementById('relVal').textContent,
    label: document.getElementById('relLabel').textContent,
    dir: document.getElementById('relDir').textContent,
    meter: document.getElementById('relMeter').innerHTML
  }));
  console.log('\n--- ASSOCIATION ---');
  console.log(JSON.stringify(rel, null, 1));
  check('association readout populated', rel.val !== '—' && rel.meter.length > 0, rel.name + ' = ' + rel.val);
  await page.screenshot({ path: OUT + '/07-rel.png' });

  /* ---------- 8. matrix ---------- */
  await page.evaluate(() => document.querySelector('.card-head[data-toggle="s-matrix"]').click());
  await sleep(7000);
  const mx = await page.evaluate(() => {
    const c = echarts.getInstanceByDom(document.getElementById('cHeat'));
    const o = c.getOption();
    return {
      cells: o.series[0].data.length,
      labels: o.xAxis[0].data.length,
      sub: document.getElementById('mxSub').textContent,
      visualMap: o.visualMap[0].type,
      topRows: document.querySelectorAll('#topPairs tbody tr').length,
      first: (document.querySelector('#topPairs tbody tr') || {}).innerText
    };
  });
  console.log('\n--- MATRIX ---');
  console.log(JSON.stringify(mx, null, 1));
  check('58x58 = 3364 heatmap cells', mx.cells === 3364, mx.cells + ' cells');
  check('top pairs table filled', mx.topRows === 20, mx.topRows + ' rows');
  await page.screenshot({ path: OUT + '/08-matrix.png' });

  const hp = await pointIn(page, 'cHeat', 0, 0);
  const hpCell = await page.evaluate(() => {
    const c = echarts.getInstanceByDom(document.getElementById('cHeat'));
    const px = c.convertToPixel({ seriesIndex: 0 }, [12, 30]);
    const r = document.getElementById('cHeat').getBoundingClientRect();
    return { x: r.left + px[0], y: r.top + px[1] };
  });
  await page.mouse.click(hpCell.x, hpCell.y);
  await sleep(1600);
  const afterHeat = await page.evaluate(() => ({
    a: document.getElementById('selA').value,
    b: document.getElementById('selB').value,
    relOpen: document.getElementById('s-rel').classList.contains('open')
  }));
  console.log('  heatmap click -> ' + JSON.stringify(afterHeat));
  check('heatmap click sets α and β', afterHeat.a && afterHeat.b && afterHeat.a !== afterHeat.b,
    afterHeat.a + ' / ' + afterHeat.b);

  /* ---------- 9. missingness ---------- */
  await page.evaluate(() => document.querySelector('.card-head[data-toggle="s-quality"]').click());
  await sleep(1500);
  const miss = await page.evaluate(() => {
    const c = echarts.getInstanceByDom(document.getElementById('cMiss'));
    const o = c.getOption();
    return {
      bars: o.series[0].data.length,
      labels: o.yAxis[0].data.length,
      sub: document.getElementById('missSub').textContent,
      cards: Array.prototype.map.call(document.querySelectorAll('#qCards .stat'),
        d => d.querySelector('.k').textContent + '=' + d.querySelector('.v').textContent),
      firstLabel: o.yAxis[0].data[0],
      firstTick: o.yAxis[0].axisLabel !== undefined
    };
  });
  console.log('\n--- MISSINGNESS ---');
  console.log(JSON.stringify(miss, null, 1));
  check('missing map has 20 bars', miss.bars === 20, miss.bars + ' bars');
  check('missing labels are readable names', /[a-z_]{6,}/.test(String(miss.firstLabel)), String(miss.firstLabel));
  await page.screenshot({ path: OUT + '/09-missing.png' });

  /* ---------- 10. ledger ---------- */
  await page.evaluate(() => document.querySelector('.card-head[data-toggle="s-ledger"]').click());
  await sleep(900);
  const led = await page.evaluate(() => ({
    rows: document.querySelectorAll('#ledgerTbl tbody tr').length,
    headers: document.querySelectorAll('#ledgerTbl thead th').length,
    sub: document.getElementById('ledgerSub').textContent,
    selA: document.querySelectorAll('#ledgerTbl tr.selA').length,
    selB: document.querySelectorAll('#ledgerTbl tr.selB').length,
    first: (document.querySelector('#ledgerTbl tbody tr') || {}).innerText.replace(/\t/g, ' | ')
  }));
  console.log('\n--- LEDGER ---');
  console.log(JSON.stringify(led, null, 1));
  check('ledger shows 58 rows / 9 columns', led.rows === 58 && led.headers === 9, led.rows + ' x ' + led.headers);
  check('ledger marks current α and β', led.selA === 1 && led.selB === 1, 'selA=' + led.selA + ' selB=' + led.selB);
  await page.screenshot({ path: OUT + '/10-ledger.png' });

  /* ledger group filter + search */
  await page.evaluate(() => {
    const chips = document.querySelectorAll('#groupChips .chip');
    chips[1].click();
  });
  await sleep(500);
  const filtered = await page.evaluate(() => ({
    rows: document.querySelectorAll('#ledgerTbl tbody tr').length,
    sub: document.getElementById('ledgerSub').textContent,
    chip: document.querySelector('#groupChips .chip.on').textContent
  }));
  console.log('  group filter -> ' + JSON.stringify(filtered));
  check('group filter reduces ledger rows', filtered.rows > 0 && filtered.rows < 58, JSON.stringify(filtered));
  await page.evaluate(() => document.querySelector('#groupChips .chip').click());
  await sleep(400);

  await page.evaluate(() => {
    const s = document.getElementById('ledSearch');
    s.value = 'rolling'; s.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await sleep(500);
  const searched = await page.evaluate(() => document.querySelectorAll('#ledgerTbl tbody tr').length);
  console.log('  search "rolling" -> ' + searched + ' rows');
  check('search filters ledger', searched > 0 && searched < 58, searched + ' rows');
  await page.evaluate(() => {
    const s = document.getElementById('ledSearch');
    s.value = ''; s.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await sleep(400);

  /* ---------- 11. categorical parameter path ---------- */
  await page.evaluate(() => {
    const s = document.getElementById('selA');
    s.value = 'action_type'; s.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await sleep(1800);
  const cat = await page.evaluate(() => {
    const c = echarts.getInstanceByDom(document.getElementById('cDist'));
    return {
      cards: Array.prototype.map.call(document.querySelectorAll('#statCards .stat'),
        d => d.querySelector('.k').textContent + '=' + d.querySelector('.v').textContent),
      types: c ? c.getOption().series.map(s => s.type + '(' + s.data.length + ')') : null,
      note: document.getElementById('statNote').innerText.slice(0, 140),
      distNote: document.getElementById('distNote').innerText.slice(0, 140),
      qqTitle: document.getElementById('qqTitle').textContent
    };
  });
  console.log('\n--- CATEGORICAL α ---');
  console.log(JSON.stringify(cat, null, 1));
  check('categorical α renders a bar chart', cat.types && cat.types[0] === 'bar(49)', JSON.stringify(cat.types));
  check('categorical profile cards populated', cat.cards.length === 7, cat.cards.length + ' cards');
  check('categorical note reads correctly', /Jump Shot/.test(cat.note) && /不平衡比/.test(cat.note), cat.note.slice(0, 70));
  await page.screenshot({ path: OUT + '/11-cat.png' });

  /* cat × num pair + inspector on a categorical pair */
  await page.evaluate(() => {
    const s = document.getElementById('selB');
    s.value = 'touch_time'; s.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await sleep(2000);
  const catnum = await page.evaluate(() => {
    const c = echarts.getInstanceByDom(document.getElementById('cPair'));
    return {
      sub: document.getElementById('pairSub').textContent,
      series: c ? c.getOption().series.map(s => s.name + '(' + s.data.length + ')') : null,
      note: document.getElementById('pairNote').innerText.slice(0, 110)
    };
  });
  console.log('\n--- CAT × NUM ---');
  console.log(JSON.stringify(catnum, null, 1));
  check('cat × num renders jitter + class medians', catnum.series && catnum.series.length === 2, JSON.stringify(catnum.series));
  await page.screenshot({ path: OUT + '/12-catnum.png' });

  const cnp = await pointIn(page, 'cPair', 0, 300);
  await page.mouse.click(cnp.x, cnp.y);
  await sleep(900);
  const catInsp = await page.evaluate(() => {
    const d = document.getElementById('probeDetail');
    return { lines: d.innerText.split('\n').length, head: d.innerText.split('\n').slice(0, 3).join(' | ') };
  });
  console.log('  cat×num inspector: ' + JSON.stringify(catInsp));
  check('inspector works for categorical pairs too', catInsp.lines > 50, catInsp.head);
  await page.screenshot({ path: OUT + '/12b-catnum-inspector.png' });

  /* ---------- 12. heavy-tailed parameter: kurtosis + box outliers ---------- */
  await page.evaluate(() => {
    const s = document.getElementById('selA');
    s.value = 'touch_time'; s.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await sleep(1600);
  const heavy = await page.evaluate(() => {
    const b = echarts.getInstanceByDom(document.getElementById('cBox'));
    return {
      stats: window.PROBE_STATS('touch_time'),
      boxSub: document.getElementById('boxSub').textContent,
      fliers: b.getOption().series[1].data.length,
      skewCard: Array.prototype.map.call(document.querySelectorAll('#statCards .stat'),
        d => d.querySelector('.k').textContent + '=' + d.querySelector('.v').textContent).slice(3, 6)
    };
  });
  console.log('\n--- HEAVY TAIL ---');
  console.log(JSON.stringify(heavy, null, 1));
  check('touch_time kurtosis matches pandas (~21.87)', Math.abs(heavy.stats.kurt - 21.872) < 0.02, heavy.stats.kurt);
  check('box plot draws capped fliers', heavy.fliers > 0 && heavy.fliers <= 4200, heavy.fliers + ' fliers');
  await page.screenshot({ path: OUT + '/13-heavy.png' });

  /* ---------- 13. language switch ---------- */
  await page.evaluate(() => document.querySelector('.langbtn[data-lang="en"]').click());
  await sleep(2200);
  const en = await page.evaluate(() => ({
    lang: window.PROBE_LANG,
    htmlLang: document.documentElement.lang,
    title: document.title,
    h1: document.querySelector('.masthead h1').innerText,
    cards: Array.prototype.map.call(document.querySelectorAll('.card-title'), c => c.textContent),
    profileCard: (document.querySelector('#statCards .stat .k') || {}).textContent,
    distTitle: document.getElementById('distTitle').textContent,
    foot: document.getElementById('footLeft').textContent,
    stored: localStorage.getItem('probe-lang'),
    groupChips: Array.prototype.map.call(document.querySelectorAll('#groupChips .chip'), c => c.textContent),
    groupCells: Array.prototype.map.call(document.querySelectorAll('#ledgerTbl tbody tr td:nth-child(3)'), c => c.textContent).slice(0, 4),
    tagKind: document.querySelector('#ledgerTbl tbody tr .tag').textContent
  }));
  console.log('\n--- ENGLISH ---');
  console.log(JSON.stringify(en, null, 1));
  check('language switched to English', en.lang === 'en' && en.htmlLang === 'en', en.htmlLang);
  check('card titles translated', /Statistical Profile/.test(en.cards[1]), en.cards.slice(0, 3).join(' / '));
  check('stat card labels translated', /MEAN|MEDIAN/.test(en.profileCard || ''), en.profileCard);
  check('preference persisted', en.stored === 'en', String(en.stored));
  console.log('  groups  : ' + en.groupChips.join(' | '));
  check('group filter chips translated', /Shot Type/.test(en.groupChips.join(' ')) &&
    !/出手型態/.test(en.groupChips.join(' ')), en.groupChips.slice(0, 3).join(' / '));
  check('ledger group column translated', !/出手型態|賽況/.test(en.groupCells.join(' ')),
    en.groupCells.join(' / '));
  await page.screenshot({ path: OUT + '/14-english.png' });

  /* english charts still fine */
  const enChart = await page.evaluate(() => {
    const c = echarts.getInstanceByDom(document.getElementById('cDist'));
    const d = echarts.getInstanceByDom(document.getElementById('cBox'));
    return {
      distTitle: c.getOption().title[0].text,
      distSub: c.getOption().title[0].subtext,
      boxSub: d.getOption().title[0].subtext,
      panelH3: document.getElementById('distTitle').textContent,
      distNote: document.getElementById('distNote').innerText.slice(0, 80)
    };
  });
  console.log('  EN chart: ' + JSON.stringify(enChart));
  check('charts re-rendered in English', /bins/.test(enChart.distSub) && /fence/.test(enChart.boxSub),
    enChart.distSub + ' | ' + enChart.boxSub);
  check('panel header translated', /Distribution/.test(enChart.panelH3), enChart.panelH3);

  /* ---------- 14. expand / collapse all ---------- */
  await page.evaluate(() => document.getElementById('btnExpand').click());
  await sleep(4500);
  const allOpen = await page.evaluate(() => document.querySelectorAll('.card.open').length);
  console.log('\n  expand-all -> ' + allOpen + ' cards open');
  check('expand-all opens every card', allOpen === 10, allOpen + '/10');
  await page.screenshot({ path: OUT + '/15-expanded-top.png' });
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.42));
  await sleep(900);
  await page.screenshot({ path: OUT + '/16-expanded-mid.png' });
  await page.evaluate(() => document.getElementById('btnCollapse').click());
  await sleep(700);
  const collapsed = await page.evaluate(() => Array.prototype.map.call(document.querySelectorAll('.card.open'), c => c.id));
  console.log('  collapse-all -> open: ' + JSON.stringify(collapsed));
  check('collapse-all leaves only 00 open', collapsed.length === 1 && collapsed[0] === 's-select', JSON.stringify(collapsed));
  await page.screenshot({ path: OUT + '/17-collapsed.png' });

  /* ---------- 15. back to Chinese, responsive ---------- */
  await page.evaluate(() => {
    document.querySelector('.langbtn[data-lang="zh"]').click();
    document.querySelector('.card-head[data-toggle="s-profile"]').click();
    document.querySelector('.card-head[data-toggle="s-dist"]').click();
  });
  await sleep(1800);
  await page.evaluate(() => window.scrollTo(0, 0));
  await sleep(400);
  await page.screenshot({ path: OUT + '/18-zh-top.png' });

  await page.setViewport({ width: 900, height: 1300 });
  await sleep(1300);
  await page.screenshot({ path: OUT + '/19-narrow-900.png' });
  await page.setViewport({ width: 430, height: 1100 });
  await sleep(1300);
  await page.screenshot({ path: OUT + '/20-mobile-430.png' });
  const mob = await page.evaluate(() => ({
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
    sw: document.documentElement.scrollWidth, iw: window.innerWidth,
    langbarVisible: document.querySelector('.langbar .langcard').getBoundingClientRect().bottom <= window.innerHeight + 1
  }));
  console.log('\n  mobile: ' + JSON.stringify(mob));
  check('no horizontal overflow at 430px', mob.overflowX === false, mob.sw + ' vs ' + mob.iw);
  check('language bar visible on mobile', mob.langbarVisible === true);

  /* ---------- report ---------- */
  const failed = results.filter(r => !r.ok);
  console.log('\n================ VERIFICATION ================');
  console.log('  checks : ' + results.length + '   passed: ' + (results.length - failed.length) + '   failed: ' + failed.length);
  failed.forEach(f => console.log('   x ' + f.name + ' — ' + f.detail));
  console.log('=== ERRORS (' + errors.length + ') ===');
  errors.slice(0, 25).forEach(e => console.log('  ' + e));
  console.log('=== WARNINGS (' + warns.length + ') ===');
  warns.slice(0, 8).forEach(e => console.log('  ' + e));
  await browser.close();
  console.log('\nshots -> ' + OUT);
  process.exit(failed.length || errors.length ? 1 : 0);
})().catch(e => { console.error('HARNESS FAIL', e); process.exit(2); });
