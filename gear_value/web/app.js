'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const gold = value => Number(value).toLocaleString('ru-RU');
let state, evidence = '', excludedId = null, editingId = '', result = null, toastTimer, recognizing = false;
function toast(message, error = false) { $('toast').textContent = message; $('toast').className = error ? 'error' : ''; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, error ? 10000 : 5000); }
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-App-Token':state.token}, body:JSON.stringify(data)});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Не удалось выполнить действие.');
  return body;
}
async function perform(button, action) { button.disabled = true; try { await action(); } catch(error) { toast(error.message, true); } finally { button.disabled = false; } }
function options(map, selected = '') { return Object.entries(map).map(([key,label]) => `<option value="${esc(key)}" ${key === selected ? 'selected' : ''}>${esc(label)}</option>`).join(''); }
function page(name) { document.querySelectorAll('.page').forEach(el => el.hidden = el.id !== `page-${name}`); document.querySelectorAll('.nav').forEach(el => el.classList.toggle('active', el.dataset.page === name)); $('breadcrumb').textContent = {estimate:'Рабочее место / Оценка',market:'Рабочее место / База аукциона',research:'Рабочее место / Исследование'}[name]; }
function addStat(container, stat = {}) {
  if ($(container).children.length >= 8) { toast('Максимум 8 характеристик.'); return; }
  const row = document.createElement('div'); row.className = 'stat-row';
  row.innerHTML = `<div class="stat-row-top"><select class="stat-key" aria-label="Характеристика">${options(state.catalog.STAT_LABELS, stat.key || 'ranged.reduction')}</select><button type="button" class="icon-button remove-stat" aria-label="Удалить характеристику">×</button></div><input class="custom-stat" maxlength="160" placeholder="Точное название характеристики" value="${esc(stat.custom || '')}" ${stat.key !== 'custom' ? 'hidden' : ''}><div class="stat-row-values"><input class="stat-value" type="number" min="0" max="1000" step="0.01" value="${esc(stat.value ?? '')}" required placeholder="Значение, %" aria-label="Значение в процентах"><select class="stat-color" aria-label="Цвет характеристики">${options(state.catalog.STAT_COLORS, stat.color || 'unknown')}</select></div>`;
  row.querySelector('.remove-stat').onclick = () => row.remove();
  row.querySelector('.stat-key').onchange = event => { const custom = row.querySelector('.custom-stat'); custom.hidden = event.target.value !== 'custom'; custom.required = !custom.hidden; };
  $(container).append(row);
}
function getStats(container) { return [...$(container).children].map(row => ({key:row.querySelector('.stat-key').value, value:row.querySelector('.stat-value').value, color:row.querySelector('.stat-color').value, custom:row.querySelector('.custom-stat').value})); }
function getItem() { return {name:$('name').value,slot:$('slot').value,rarity:$('rarity').value,level:$('level').value,market:$('market').value,attempts:$('attempts').value,trait:$('trait').value,stats:getStats('stats'),base_stats:getStats('base-stats')}; }
function statText(stat) { return `${stat.key === 'custom' ? stat.custom : state.catalog.STAT_LABELS[stat.key]}: ${String(stat.value).replace('.', ',')}%`; }
function statsHTML(stats) { return stats.map(s => `<div class="stat-line ${esc(s.color)}">${esc(statText(s))}</div>`).join(''); }
function showEvidence() { $('evidence-preview').innerHTML = evidence ? `<img class="screenshot-thumb" src="/images/${encodeURIComponent(evidence)}" data-image="${esc(evidence)}" alt="Снимок текущего предмета"><p class="hint">Снимок прикрепится к сохраняемому наблюдению.</p>` : ''; }
function fillItem(record) {
  for (const name of ['name','slot','rarity','level','market','attempts','trait']) $(name).value = record[name] ?? '';
  $('stats').replaceChildren(); $('base-stats').replaceChildren();
  record.stats.forEach(s => addStat('stats', s)); (record.base_stats || []).forEach(s => addStat('base-stats', s));
  $('base-details').open = true; evidence = record.evidence || ''; excludedId = record.id; editingId = ''; showEvidence();
  $('sample').value = record.id;
}
function newItem() {
  $('item-form').reset(); $('sample').value = ''; $('stats').replaceChildren(); $('base-stats').replaceChildren();
  addStat('stats'); evidence = ''; excludedId = null; editingId = ''; result = null; showEvidence();
  $('estimate-result').innerHTML = '<div class="empty-mark">◈</div><h2>Новый предмет</h2><p>Заполните его параметры и нажмите «Рассчитать стоимость».</p>';
  page('estimate'); $('name').focus();
}
async function recognizeScreenshot(file) {
  if (recognizing) { toast('Предыдущий снимок ещё распознаётся.'); return; }
  if (!file || !['image/png','image/jpeg','image/webp'].includes(file.type)) { toast('Выберите PNG, JPG или WebP.',true); return; }
  if (file.size > 15000000) { toast('Снимок больше 15 МБ.',true); return; }
  page('estimate'); recognizing = true; document.body.classList.add('recognizing');
  $('choose-screenshot').disabled = true;
  const status = $('recognition-status'); status.hidden = false; status.textContent = 'Читаю карточку и характеристики…';
  try {
    const response = await fetch('/api/recognize',{method:'POST',headers:{'Content-Type':file.type,'X-App-Token':state.token},body:file});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Не удалось прочитать снимок.');
    const market = $('market').value || 'Текущий аукцион';
    fillItem({...data.item,id:'',market,evidence:data.evidence});
    excludedId = null; editingId = ''; result = null;
    $('open-save').textContent = 'Добавить наблюдение цены';
    $('estimate-result').innerHTML = '<div class="empty-mark">◈</div><h2>Карточка прочитана</h2><p>Сверьте поля со снимком и нажмите «Рассчитать стоимость».</p>';
    document.querySelectorAll('.needs-review').forEach(el=>el.classList.remove('needs-review'));
    for (const id of ['name','slot','rarity','level','attempts']) if ($(id).value === '') $(id).classList.add('needs-review');
    document.querySelectorAll('.stat-value').forEach(el=>{if(el.value==='')el.classList.add('needs-review');});
    status.innerHTML = `<strong>${esc(data.message)}</strong>${data.warnings.length ? `<ul>${data.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul>` : ''}<div class="hint">Если вещь без усиления, укажите 0. Снимок прикреплён; запись в базу цен появится только после сохранения наблюдения.</div>`;
  } catch(error) {
    status.textContent = error.message; toast(error.message,true);
  } finally {
    recognizing = false; document.body.classList.remove('recognizing'); $('choose-screenshot').disabled = false;
  }
}
function bindScreenshotInput() {
  $('choose-screenshot').onclick = ()=>$('screenshot-file').click();
  $('screenshot-file').onchange = async()=>{const file=$('screenshot-file').files[0];if(file)await recognizeScreenshot(file);$('screenshot-file').value='';};
  document.addEventListener('paste',event=>{
    if (!state || document.querySelector('dialog[open]')) return;
    const image = [...(event.clipboardData?.items || [])].find(item=>item.kind==='file' && item.type.startsWith('image/'));
    if(image){event.preventDefault();recognizeScreenshot(image.getAsFile());}
  });
  const drop = $('screenshot-drop');
  drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('dragover');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));
  drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('dragover');const file=event.dataTransfer.files[0];if(file)recognizeScreenshot(file);});
}
function compHTML(record, related = false) {
  return `<div class="comp"><div><div class="comp-name">${esc(record.name)} ${record.level ? `+${record.level}` : ''}</div><div class="comp-meta"><span class="tag ${esc(record.status)}">${esc(state.catalog.STATUSES[record.status])}</span> · ${esc(record.observed)} · попыток: ${record.attempts ?? '?'}</div><div class="comp-stats">${statsHTML(record.stats)}</div>${related ? `<p class="hint">Совпадает: ${esc(record.common.join('; '))}. Остальные параметры отличаются.</p>` : ''}<div class="comp-meta">${esc(record.source)}</div>${record.evidence ? `<button class="evidence-link" data-image="${esc(record.evidence)}">Посмотреть снимок ↗</button>` : ''}</div><div><div class="comp-price">${gold(record.price)} <small>G</small></div>${related ? '' : `<div class="comp-meta">Близость параметров: ${record.similarity}%</div>`}</div></div>`;
}
function renderResult(data) {
  result = data;
  const demand = data.demand_context;
  const demandHTML = demand ? `<div class="note"><strong>Сверка со спросом</strong><p>${esc(demand.summary)}</p><a href="${esc(demand.url)}" target="_blank" rel="noopener noreferrer">${esc(demand.source)} ↗</a><p class="hint">${esc(demand.limitation)}</p></div>` : '';
  const title = {sold:'Ориентир по завершённым сделкам',ask:'Запрашивают продавцы · продажа не подтверждена',insufficient:'Недостаточно близких аналогов'}[data.basis];
  let priceHTML = `<div class="price">— <span>золота</span></div><div class="price-subtitle">Цена предмета пока не определена</div>`;
  if(data.headline) {
    priceHTML = `<div class="price">${gold(data.headline.median)} <span>золота</span></div><div class="price-subtitle">${data.headline.count === 1 ? 'Одно наблюдение' : `Разброс: ${gold(data.headline.low)}–${gold(data.headline.high)} G · ${data.headline.count} наблюдений`}</div>`;
    const feeText = $('fee').value;
    if (feeText !== '') { const fee = Number(feeText); if (!Number.isFinite(fee) || fee < 0 || fee > 100) throw new Error('Комиссия должна быть от 0 до 100%.'); priceHTML += `<p class="hint">При продаже за эту сумму после указанной комиссии ${fee}%: ${gold(Math.floor(data.headline.median*(1-fee/100)))} G. Фиксированные сборы не учтены.</p>`; }
  }
  $('estimate-result').innerHTML = `<div class="result-kicker">${title}</div>${priceHTML}<span class="tag ${data.basis === 'ask' ? 'ask' : ''}">${esc(data.confidence)}</span><div class="mini-metrics"><div><strong>${data.sold?.count || 0}</strong><span>Завершённые продажи</span></div><div><strong>${data.asks?.count || 0}</strong><span>Предложения</span></div><div><strong>${data.bids?.count || 0}</strong><span>Текущие ставки</span></div></div>${demandHTML}${data.warnings.map(s => `<div class="note">${esc(s)}</div>`).join('')}${data.sold && data.basis !== 'sold' ? `<p class="hint">Отдельные продажи: ${gold(data.sold.low)}–${gold(data.sold.high)} G (${data.sold.count}). Их пока мало для оценки.</p>` : ''}${data.bids ? `<p class="hint">Текущие ставки: ${gold(data.bids.low)}–${gold(data.bids.high)} G. Торги ещё не закончены.</p>` : ''}${data.unsold_count ? `<p class="hint">Не продалось близких лотов: ${data.unsold_count}. Их цены исключены из ориентира.</p>` : ''}<div class="section-line"><h3>Сопоставимые лоты</h3><span class="muted">${data.matches.length}</span></div>${data.matches.length ? data.matches.map(r=>compHTML(r)).join('') : '<p class="hint">Полных аналогов нет. Другой набор характеристик не подменяет цену вашей вещи.</p>'}${data.related.length ? `<details><summary>Похожие по отдельным характеристикам · ${data.related.length}</summary><p class="hint">Справочная подборка для проверки рынка. В расчёт выше не входит.</p>${data.related.map(r=>compHTML(r,true)).join('')}</details>` : ''}<p class="hint">Период: ${data.max_age} дней. Исключено устаревших: ${data.excluded.stale}, из других рынков: ${data.excluded.market}, повторов: ${data.excluded.duplicate}.${excludedId ? ' Выбранный лот не используется для оценки самого себя.' : ''}</p>`;
}
async function calculate() { if (!$('item-form').reportValidity()) return; const data = await api('/api/estimate', {item:getItem(),max_age:$('max-age').value,exclude_id:excludedId}); renderResult(data); }
function renderMarket() {
  const counts = {sold:0,ask:0,bid:0}; state.records.forEach(r=>{if(r.status in counts) counts[r.status]++;});
  $('nav-count').textContent = state.records.length;
  $('market-metrics').innerHTML = [[state.records.length,'Всего наблюдений'],[counts.ask,'Цены продавцов'],[counts.sold,'Подтверждённые продажи'],[counts.bid,'Текущие ставки']].map(([n,t])=>`<div class="metric"><strong>${n}</strong><span>${t}</span></div>`).join('');
  const term = $('search').value.toLocaleLowerCase('ru-RU'); const status = $('status-filter').value;
  const rows = state.records.filter(r => (!status || r.status === status) && [r.name,r.source,r.market,...r.stats.map(statText)].join(' ').toLocaleLowerCase('ru-RU').includes(term)).sort((a,b)=>b.observed.localeCompare(a.observed)||a.price-b.price);
  $('market-table').innerHTML = rows.length ? `<table><thead><tr><th>Предмет и характеристики</th><th>Цена</th><th>Наблюдение</th><th>Действия</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.name)} ${r.level ? `+${r.level}` : ''}</strong><div class="muted">${esc(state.catalog.SLOTS[r.slot])} · ${esc(state.catalog.RARITIES[r.rarity])}</div>${statsHTML(r.stats)}<div class="muted">Попыток: ${r.attempts ?? '?'}${r.trait ? ` · ${esc(r.trait)}` : ''}</div></td><td class="money">${gold(r.price)} G</td><td><span class="tag ${esc(r.status)}">${esc(state.catalog.STATUSES[r.status])}</span><p class="muted">${esc(r.observed)}<br>${esc(r.market)}<br>${esc(r.source)}</p>${r.evidence ? `<button class="text-button" data-image="${esc(r.evidence)}">Снимок ↗</button>` : ''}</td><td><div class="row-actions"><button class="text-button" data-evaluate="${esc(r.id)}">Сравнить</button><button class="text-button" data-edit="${esc(r.id)}">Изменить</button><button class="text-button" data-delete="${esc(r.id)}">Удалить</button></div></td></tr>`).join('')}</tbody></table>` : '<div class="no-results">Наблюдений не найдено.</div>';
  const selected = $('sample').value; $('sample').innerHTML = '<option value="">Выберите сохранённый лот…</option>'+state.records.map(r=>`<option value="${esc(r.id)}">${esc(r.name)} · ${gold(r.price)} G · ${esc(state.catalog.STATUSES[r.status])}</option>`).join(''); $('sample').value = selected;
  $('item-names').innerHTML = [...new Set(state.records.map(r=>r.name))].map(n=>`<option value="${esc(n)}"></option>`).join('');
  $('data-location').textContent = `База и резервная копия: ${state.data_dir}. Экспорт содержит записи; снимки остаются в папке screenshots и в комплекте приложения.`;
}
async function refresh() { state = await api('/api/state'); renderMarket(); }
function renderResearch() {
  const sample = state.research.sample;
  const sampleHTML = sample ? `<section class="panel"><h2>Что видно на ваших снимках</h2><p>${esc(sample.summary)}</p><div class="research-grid">${sample.examples.map(e=>`<article><h3>${esc(e.name)} · ${gold(e.price)} G</h3><p>${esc(e.note)}</p><button class="text-button" data-image="${esc(e.evidence)}">Проверить карточку ↗</button></article>`).join('')}</div></section>` : '';
  $('research-content').innerHTML = `<div class="note">Проверено ${esc(state.research.checked)}. ${esc(state.research.coverage)}</div>${sampleHTML}<div class="research-grid">${state.research.findings.map(f=>`<article class="panel"><span class="tag">${esc(f.region)} · ${esc(f.kind)}</span><h2>${esc(f.title)}</h2><p>${esc(f.summary)}</p><p class="hint">${esc(f.limitation)}</p><a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">${esc(f.source)} ↗</a></article>`).join('')}</div>`;
}
function openSave(record = null) {
  if (!$('item-form').reportValidity()) return;
  if (!getStats('stats').length) { toast('Добавьте особые характеристики.',true); return; }
  editingId = record?.id || '';
  $('save-title').textContent = record ? 'Изменить наблюдение' : 'Наблюдение цены';
  $('record-price').value = record?.price || ''; $('record-status').value = record?.status || 'ask'; $('record-date').value = record?.observed || state.today;
  $('record-source').value = record?.source || 'Карточка лота в игре'; $('record-notes').value = record?.notes || ''; $('sale-check').checked = record?.sale_confirmed || false;
  $('record-evidence').textContent = evidence ? `Прикреплён снимок: ${evidence}` : 'Снимок не прикреплён.'; saleCheck(); $('save-dialog').showModal();
}
function saleCheck(){const sold=$('record-status').value==='sold';$('sale-check-label').hidden=!sold;$('sale-check').required=sold;}
document.addEventListener('click', async event => {
  const image = event.target.closest('[data-image]');
  if(image) { $('large-image').src = '/images/'+encodeURIComponent(image.dataset.image); $('image-dialog').showModal(); return; }
  const evaluate = event.target.closest('[data-evaluate]');
  if(evaluate) { fillItem(state.records.find(r=>r.id===evaluate.dataset.evaluate));page('estimate');await perform(evaluate,calculate);return; }
  const edit = event.target.closest('[data-edit]');
  if(edit) { const r=state.records.find(r=>r.id===edit.dataset.edit); fillItem(r);page('estimate');toast('Параметры перенесены в форму. Исправьте их и нажмите «Добавить наблюдение цены».');editingId=r.id;$('open-save').textContent='Сохранить изменения лота'; return; }
  const remove = event.target.closest('[data-delete]');
  if(remove && confirm('Удалить это наблюдение из локальной базы? Предыдущая версия сохранится в резервной копии.')) await perform(remove,async()=>{await api('/api/delete',{id:remove.dataset.delete});await refresh();toast('Наблюдение удалено.');});
});
async function init() {
  state = await api('/api/state');
  $('slot').innerHTML=options(state.catalog.SLOTS);$('rarity').innerHTML=options(state.catalog.RARITIES);
  $('record-status').innerHTML=options(state.catalog.STATUSES);$('status-filter').innerHTML += options(state.catalog.STATUSES);
  $('record-date').max=state.today;
  document.querySelectorAll('.nav').forEach(el=>el.onclick=()=>page(el.dataset.page));
  $('add-stat').onclick=()=>addStat('stats');$('add-base').onclick=()=>addStat('base-stats',{key:'squad.attack'});
  $('new-item').onclick=$('add-record').onclick=()=>{newItem();$('open-save').textContent='Добавить наблюдение цены';};
  $('sample').onchange=()=>{const r=state.records.find(r=>r.id===$('sample').value);if(r){fillItem(r);$('open-save').textContent='Добавить наблюдение цены';perform($('sample'),calculate);}};
  $('item-form').onsubmit=event=>{event.preventDefault();perform(event.submitter,calculate);};
  $('open-save').onclick=()=>openSave(editingId ? state.records.find(r=>r.id===editingId) : null);
  $('close-save').onclick=()=>$('save-dialog').close();$('close-image').onclick=()=>$('image-dialog').close();
  $('record-status').onchange=saleCheck;
  $('save-form').onsubmit=event=>{event.preventDefault();perform(event.submitter,async()=>{const raw={...getItem(),id:editingId,price:$('record-price').value,status:$('record-status').value,observed:$('record-date').value,source:$('record-source').value,notes:$('record-notes').value,sale_confirmed:$('sale-check').checked,evidence};const saved=await api('/api/save',raw);$('save-dialog').close();editingId='';excludedId=saved.id;$('open-save').textContent='Добавить наблюдение цены';await refresh();toast('Наблюдение сохранено.');await calculate();});};
  $('search').oninput=renderMarket;$('status-filter').onchange=renderMarket;
  $('export').onclick=()=>perform($('export'),async()=>{const data=await api('/api/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`DoomsdayGearValue-${state.today}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  $('import').onclick=()=>$('import-file').click();$('import-file').onchange=async()=>{const file=$('import-file').files[0];if(!file)return;await perform($('import'),async()=>{if(file.size>8000000)throw new Error('Файл больше 8 МБ.');const data=JSON.parse(await file.text());const r=await api('/api/import',data);await refresh();toast(`Добавлено: ${r.added}. Уже были в базе: ${r.skipped}.`);});$('import-file').value='';};
  $('devices').onclick=()=>perform($('devices'),async()=>{const d=await api('/api/devices');$('device').innerHTML=d.devices.map(s=>`<option>${esc(s)}</option>`).join('');if(!d.devices.length)toast('Подключённые эмуляторы не найдены.');});
  $('capture').onclick=()=>perform($('capture'),async()=>{if(!$('device').value)throw new Error('Сначала нажмите «Найти» и выберите эмулятор.');const d=await api('/api/capture',{serial:$('device').value});const response=await fetch('/images/'+encodeURIComponent(d.evidence));const blob=await response.blob();await recognizeScreenshot(new File([blob],'capture.png',{type:'image/png'}));});
  $('shutdown').onclick=()=>perform($('shutdown'),async()=>{await api('/api/shutdown',{});document.body.innerHTML='<main style="margin:40px"><h1>Приложение остановлено</h1><p>Можно закрыть вкладку. Наблюдения сохранены.</p></main>';});
  $('fee').oninput=()=>{if(result){try{renderResult(result);}catch(e){toast(e.message,true);}}};
  renderMarket();renderResearch();addStat('stats');bindScreenshotInput();
}
init().catch(error=>{ $('estimate-result').textContent='Не удалось открыть базу: '+error.message; toast(error.message,true); });
