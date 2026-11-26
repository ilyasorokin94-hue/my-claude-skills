// Снимок публичной карточки Яндекс Карт и карточек соседей (модуль 01, блок 1).
//
// Как запускать: в Chrome без входа в Яндекс открыть любую страницу
// yandex.ru/maps, затем отдельным шагом выполнить этот скрипт на странице,
// подставив ID из настроек клиники (её audit-nastroyki.md).
// Скрипт только читает. У соседей ничего не нажимаем.
//
// Возвращает JSON одной строкой. Его разбирает scripts/snimok_razbor.py,
// сравнивает с прошлым — scripts/sravnit_snimki.py. Что в снимке и как
// читать разницу: shablony/snimok-kartochki.md.
//
// Поля state-view Яндекс меняет без предупреждения (приёмы Z-05, Z-08).
// Чего не нашлось, попадает в "oshibki" этой карточки: снимок всё равно
// отдаётся, а недостающее добираешь глазами и пишешь в «Как улучшить скилл».

const VERSIYA = '1.0';

const NASTROYKI = {
  orgId: '0000000000',   // ID нашей организации
  sosedi: [              // ID соседей: 3–5 из audit-nastroyki.md, включая выброс
    // '0000000001',
  ],
};

async function snimokKartochki(n) {
  const pad = (x) => String(x).padStart(2, '0');
  const d = new Date();
  const snyato =
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`;

  const stateView = (html) => {
    const m = html.match(/<script[^>]*class="state-view"[^>]*>([\s\S]*?)<\/script>/);
    if (!m) return null;
    try { return JSON.parse(m[1]); } catch (e) { return null; }
  };

  const vzyat = async (put) => {
    const html = await (await fetch(put, { credentials: 'omit' })).text();
    return stateView(html);
  };

  const utmTerm = (url) => {
    const m = String(url ?? '').match(/[?&]utm_term=([^&#]*)/);
    return m ? decodeURIComponent(m[1]) : null;
  };

  const dlina = (s) => (s == null ? null : String(s).length);

  // Каталог берём со вкладки /prices/: там он целиком, вместе с sourceUrl
  // (R-16: часть позиций Яндекс добавляет сам со страниц сайта).
  const katalog = (sv) => {
    const org = sv?.stack?.[0]?.results?.items?.[0] ?? {};
    const gruppy = org.prices?.items ?? org.priceLists ?? [];
    const out = [];
    for (const g of gruppy) {
      for (const p of (g.items ?? g.goods ?? [])) {
        out.push({
          nazvanie: p.title ?? p.name ?? null,
          cena: p.price?.value ?? p.price?.text ?? null,
          foto: !!(p.photo || p.image || p.photos?.length),
          opisanie_znakov: dlina(p.description ?? p.shortDescription),
          razdel: g.title ?? g.name ?? null,
          populyarnoe: !!(p.isPopular ?? p.popular),
          source_url: p.sourceUrl ?? null,
        });
      }
    }
    return out;
  };

  const kartochka = async (id, nasha) => {
    const o = { id: String(id), nasha, oshibki: [] };
    const sv = await vzyat(`/maps/org/${id}/`);
    const it = sv?.stack?.[0]?.results?.items?.[0];
    if (!it) { o.oshibki.push('нет state-view страницы организации'); return o; }

    o.nazvanie = it.title ?? null;
    o.adres = it.address ?? it.fullAddress ?? null;
    o.rubriki = (it.categories ?? []).map((c) => c.name ?? c.title ?? String(c));
    o.rubrika_glavnaya = o.rubriki[0] ?? null;
    o.osobennosti = (it.features ?? []).map((f) => f.name ?? f.title ?? String(f));
    o.chasy = it.workingTime ?? it.hours?.text ?? null;
    o.specrezhim = it.workingStatus ?? null;
    o.telefony = (it.phones ?? []).map((p) => ({
      nomer: p.number ?? p.formatted ?? null, tip: p.type ?? null,
    }));
    o.ssylki = (it.urls ?? it.links ?? []).map((u) => ({
      tip: u.type ?? null, url: u.url ?? String(u), utm_term: utmTerm(u.url ?? u),
    }));
    o.vladelec_podtverzhden = !!(it.businessProperties?.has_verified_owner ??
      it.verified);
    o.horoshee_mesto = it.awards?.goodPlaceYear ?? null;
    o.tarif = it.tariff ?? it.advert?.tariff ?? null;
    if (o.tarif == null) o.oshibki.push('тариф в state-view не найден, смотри кабинет');
    o.knopki = (it.actions ?? it.buttons ?? []).map((b) => ({
      tekst: b.title ?? b.text ?? null, url: b.url ?? null, utm_term: utmTerm(b.url),
    }));

    o.rejting = it.ratingData?.ratingValue ?? null;
    o.ocenok = it.ratingData?.ratingCount ?? null;
    o.otzyvov = it.ratingData?.reviewCount ?? null;
    o.temy = (it.aspects ?? []).map((a) => ({
      tema: a.name ?? a.title ?? null, upominaniy: a.count ?? a.reviewCount ?? null,
    }));

    const promo = it.promo ?? it.promos?.[0] ?? null;
    o.akciya = promo ? {
      zagolovok: promo.title ?? null,
      srok: promo.validUntil ?? promo.date ?? null,
      ssylka: promo.url ?? null,
      utm_term: utmTerm(promo.url),
    } : null;

    o.vrachi = {
      vkladka: !!(it.tabs ?? []).some((t) =>
        /врач/i.test(t.name ?? t.title ?? String(t))),
      chislo: it.doctors?.count ?? (it.doctors?.items ?? []).length || null,
    };

    const foto = it.photos ?? {};
    o.foto = {
      vsego: foto.count ?? null,
      video: it.videos?.count ?? null,
      oblozhka: foto.cover?.urlTemplate ?? foto.cover ?? null,
      pervye: (foto.items ?? []).slice(0, 6).map((p) => p.urlTemplate ?? p.url ?? null),
    };

    // Плитки витрины подписки или объявления: и то и другое лежит в advert.
    const adv = it.advert ?? {};
    o.plitki = (adv.products ?? adv.items ?? []).map((p, i) => ({
      nomer: i + 1,
      nazvanie: p.title ?? p.name ?? null,
      cena: p.price?.value ?? p.price?.text ?? null,
      kartinka: !!(p.photo || p.image),
      ssylka: p.url ?? null,
      utm_term: utmTerm(p.url),
    }));
    o.reklama_vidna = !!adv.advertId || o.plitki.length > 0;

    const svPrices = await vzyat(`/maps/org/${id}/prices/`);
    if (!svPrices) o.oshibki.push('нет state-view вкладки /prices/');
    o.katalog = svPrices ? katalog(svPrices) : [];

    return o;
  };

  const nasha = await kartochka(n.orgId, true);
  const sosedi = [];
  for (const id of (n.sosedi ?? [])) {
    sosedi.push(await kartochka(id, false));
    await new Promise((r) => setTimeout(r, 400 + Math.random() * 400));
  }

  return JSON.stringify({ snyato, versiya_skripta: VERSIYA, nasha, sosedi });
}

snimokKartochki(NASTROYKI);
