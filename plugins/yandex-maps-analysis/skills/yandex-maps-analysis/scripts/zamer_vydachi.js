// Заготовка замера выдачи Яндекс Карт (модуль 07, приём Z-08).
//
// Как запускать: в Chrome без входа в Яндекс открыть любую страницу
// yandex.ru/maps, затем отдельным шагом выполнить этот скрипт на странице,
// подставив настройки клиники в NASTROYKI (из её zamer-nastroyki.md).
// Скрипт возвращает строки CSV в формате модуля 07 без шапки.
//
// Поля state-view Яндекс меняет. На первом запуске у новой клиники сверь
// 2–3 пары глазами с живой выдачей; если поле переехало, поправь функции
// ниже и предложи правку в «Как улучшить скилл».

const NASTROYKI = {
  orgId: '0000000000',            // ID организации нашей карточки
  imya: 'Название в выдаче',      // запасной способ узнать карточку
  z: 14,
  tochki: [
    // { imya: 'У двери клиники', lat: 55.0, lon: 37.0 },
  ],
  zaprosy: [
    // 'стоматология', 'стоматология рядом', ...
  ],
};

async function zamerVydachi(n) {
  const pad = (x) => String(x).padStart(2, '0');
  const d = new Date();
  const data = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
  const vremya = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const kav = (s) => '"' + String(s ?? '').replace(/"/g, '""') + '"';

  const nasha = (it) =>
    String(it.id ?? '') === n.orgId ||
    String(it.uri ?? '').includes(n.orgId) ||
    (!!n.imya && String(it.title ?? '').toLowerCase() === n.imya.toLowerCase());

  const podstavleno = (it) => {
    const cats = it?.matchedObjects?.categories ?? [];
    const items = cats.flatMap((c) => c.categoryItems ?? []);
    if (!items.length) return '';
    const p = items[0];
    const cena = p.price?.text ?? p.price?.value ?? '';
    return [p.name ?? p.title ?? '', cena].filter(Boolean).join(' ');
  };

  const stroki = [];
  for (const t of n.tochki) {
    for (const q of n.zaprosy) {
      const url = `/maps/?ll=${t.lon},${t.lat}&z=${n.z}&text=${encodeURIComponent(q)}`;
      let items = [];
      let prim = '';
      try {
        const html = await (await fetch(url, { credentials: 'omit' })).text();
        const m = html.match(/<script[^>]*class="state-view"[^>]*>([\s\S]*?)<\/script>/);
        if (!m) prim = 'нет state-view (капча или другая разметка)';
        else items = JSON.parse(m[1])?.stack?.[0]?.results?.items ?? [];
      } catch (e) {
        prim = 'ошибка: ' + e.message;
      }
      let platnoe = '', besplatnoe = '', svobodnyh = 0, nashIt = null;
      items.forEach((it, i) => {
        const reklama = !!it.advert;
        if (!reklama) svobodnyh += 1;
        if (nasha(it) && !nashIt) {
          nashIt = it;
          if (reklama) platnoe = i + 1; else besplatnoe = svobodnyh;
        }
      });
      const pervyy = items[0] ?? {};
      stroki.push([
        data, vremya, kav(t.imya), t.lat, t.lon, kav(q),
        nashIt ? 'да' : (items.length ? 'нет' : ''),
        platnoe, besplatnoe,
        kav(pervyy.title ?? ''), pervyy.advert ? 'да' : '',
        items.length || '', kav(nashIt ? podstavleno(nashIt) : ''), kav(prim),
      ].join(','));
      await new Promise((r) => setTimeout(r, 400 + Math.random() * 400));
    }
  }
  return stroki.join('\n');
}

zamerVydachi(NASTROYKI);
