'use strict';
const $ = (id) => document.getElementById(id);
let articles = [];
let activeTag = '';

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url : null;
  } catch { return null; }
}

function validate(data) {
  if (!Array.isArray(data)) throw new Error('JSON 最外層必須是文章陣列。');
  return data.map((item, index) => {
    if (!item || typeof item !== 'object' || Array.isArray(item) ||
        typeof item.title !== 'string' || !item.title.trim() ||
        typeof item.url !== 'string' || !safeUrl(item.url) ||
        !Array.isArray(item.tags) || item.tags.some(tag => typeof tag !== 'string' || !tag.trim()) ||
        ![item.author, item.published_at].every(value => value == null || typeof value === 'string')) {
      throw new Error(`第 ${index + 1} 篇文章格式不完整：請檢查網址、標題、作者、日期與標籤。`);
    }
    return { ...item, tags: [...new Set(item.tags)] };
  });
}

function make(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text != null) element.textContent = text;
  return element;
}

function message(text) {
  $('status').textContent = text;
  $('status').hidden = !text;
}

function chooseTag(tag) {
  activeTag = tag;
  renderFilters();
  render();
}

function renderFilters() {
  const tags = [...new Set(articles.flatMap(article => article.tags))];
  const fragment = document.createDocumentFragment();
  for (const tag of ['', ...tags]) {
    const count = tag ? articles.filter(article => article.tags.includes(tag)).length : articles.length;
    const button = make('button', 'filter', `${tag || '全部'} · ${count}`);
    button.type = 'button';
    button.setAttribute('aria-pressed', String(activeTag === tag));
    button.addEventListener('click', () => chooseTag(tag));
    fragment.append(button);
  }
  $('filters').replaceChildren(fragment);
}

function timestamp(value) {
  const time = Date.parse(value || '');
  return Number.isFinite(time) ? time : null;
}

function render() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const list = articles.filter(article => (!activeTag || article.tags.includes(activeTag)) &&
    [article.title, article.author || '', article.url, ...article.tags].join(' ').toLocaleLowerCase().includes(query));
  list.sort((a, b) => {
    if ($('sort').value === 'title') return a.title.localeCompare(b.title, 'zh-Hant');
    const aTime = timestamp(a.published_at), bTime = timestamp(b.published_at);
    if (aTime === null) return bTime === null ? 0 : 1;
    if (bTime === null) return -1;
    return $('sort').value === 'oldest' ? aTime - bTime : bTime - aTime;
  });
  const fragment = document.createDocumentFragment();
  list.forEach((article, index) => {
    const url = safeUrl(article.url);
    const card = make('article', 'card');
    const art = make('div', 'card-art');
    art.setAttribute('aria-hidden', 'true');
    art.append(make('span', 'type', 'READ / LEARN'), make('span', 'article-number', String(index + 1).padStart(2, '0')));
    const body = make('div', 'card-body');
    body.append(make('span', 'domain', url.hostname.replace(/^www\./, '').toUpperCase()));
    const heading = make('h3');
    const title = make('a', 'title-link', article.title);
    title.href = url.href; title.target = '_blank'; title.rel = 'noopener noreferrer';
    heading.append(title); body.append(heading);
    const meta = make('div', 'meta');
    meta.append(make('span', '', article.author || '作者未提供'), make('span', '', '·'), make('span', '', article.published_at || '日期未提供'));
    body.append(meta);
    const tags = make('div', 'tags');
    article.tags.forEach(tag => {
      const button = make('button', 'tag', tag);
      button.type = 'button'; button.setAttribute('aria-label', `篩選標籤：${tag}`);
      button.addEventListener('click', () => chooseTag(tag)); tags.append(button);
    });
    body.append(tags);
    const bottom = make('div', 'card-bottom');
    const link = make('a', 'read', '閱讀原文 ↗');
    link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    bottom.append(make('span', '', `${article.tags.length} 個標籤`), link);
    body.append(bottom); card.append(art, body); fragment.append(card);
  });
  $('cards').replaceChildren(fragment);
  $('total').textContent = articles.length;
  $('result-count').textContent = `顯示 ${list.length} / ${articles.length} 篇文章`;
  $('empty').hidden = list.length !== 0;
}

function accept(data, source) {
  const validated = validate(data);
  articles = validated;
  activeTag = '';
  $('search').value = '';
  $('source').textContent = source;
  message(''); renderFilters(); render();
}

let requestVersion = 0;
async function load() {
  const version = ++requestVersion;
  $('reload').disabled = true;
  message('正在讀取文章…');
  try {
    if (location.protocol === 'file:') throw new Error('file');
    const response = await fetch('articles.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (version !== requestVersion) return;
    accept(data, 'articles.json');
  } catch (error) {
    if (version !== requestVersion) return;
    const hint = location.protocol === 'file:'
      ? '直接開啟網頁時，請按右上方「匯入 JSON」，選取專案中的 articles.json。'
      : `無法讀取 articles.json：${error.message}。請使用右上方「匯入 JSON」選取檔案，或重新讀取。`;
    message(hint);
  } finally { if (version === requestVersion) $('reload').disabled = false; }
}

$('search').addEventListener('input', render);
$('sort').addEventListener('change', render);
$('reload').addEventListener('click', load);
$('reset').addEventListener('click', () => { $('search').value = ''; chooseTag(''); });
$('file').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  const version = ++requestVersion;
  $('reload').disabled = false;
  try {
    const data = JSON.parse(await file.text());
    if (version !== requestVersion) return;
    accept(data, file.name);
  } catch (error) { if (version === requestVersion) message(`匯入失敗：${error.message}。原有文章仍保留。`); }
  finally { event.target.value = ''; }
});
$('year').textContent = new Date().getFullYear();
renderFilters(); render(); load();
