# Снимок раз в 2 недели и журнал правок (шаблон)

## Снимок

Одна строка на разбор в `snimki.csv` рядом с профилем клиники. Таблица, а не
текст: следующий запуск (и любая модель) должен посчитать динамику по
снимкам, а не вычитывать её из отчётов. Цифры за 2 недели разбора, если не
сказано иначе. Нет данных: пусто, а не ноль.

```csv
data,nedeli,etap,versiya,reklama_shla,byudzhet_menyalsya,karty_pn_bez_rekl_2n,koridor_2n,veb_bez_rekl_2n,karty_rekl_2n,poisk_rekl_2n,zvonok_bez_rekl_2n,marshrut_bez_rekl_2n,zvonki_prinyatye,zvonki_propushchennye,zayavki_karty,zapisi,vizity_kliniki,discovery,dolya,mesto,konkurenty_nedelya,mestnaya_norma,vybros,ocenok,otzyvov_30d,otzyvov_30d_vybros,mest_bespl_iz_7,spros_uslug_vs_proshl,foto,poziciy_kataloga,plitok_s_cenoy,glavnaya_pravka,primechanie,zvonki_podmennyy_2n,zvonki_propushch_dolya,podpiska_aktivna,podpiska_perehody_2n,podpiska_deystviya_2n,podpiska_dney_do_prodleniya,plitok_vsego,plitok_bez_ceny,zayavki_s_plitok_2n,vizity_s_plitok_mes,poziciy_bez_foto,poziciy_bez_ceny,poziciy_publichno_vs_kabinet,foto_novyh_2n,otvety_dolya,otvet_chasov_mediana,pravki_polzovateley_2n,top3_mest_iz_zamera,sovetov_sdelano_iz_proshlyh,tarif_kartochki,obyavleniy_vsego,foto_poslednee_dney
```

| Поле | Откуда |
|---|---|
| `etap`, `versiya` | Записка, строка «Версия» скилла |
| `reklama_shla`, `byudzhet_menyalsya` | Журнал, кабинет |
| `karty_pn_bez_rekl_2n` и коридор | `card_weeks.py`: заработанная часть (приложение + Навигатор без рекламы) и коридор шума из его вывода |
| `veb_bez_rekl_2n`, `karty_rekl_2n`, `poisk_rekl_2n` | `card_weeks.py` |
| `zvonok_bez_rekl_2n`, `marshrut_bez_rekl_2n` | `card_weeks.py` |
| Звонки принятые и пропущенные | Кабинет, «Статистика» |
| Заявки, записи, визиты в клинику из Карт | Таблица, CRM, Метрика сайта (`utm_term`); раз в месяц |
| Discovery, доля, место, какую неделю показывает «Конкуренты» | Кабинет; застыл = так и пиши |
| Местная норма и выброс | «Конкуренты» |
| Оценок, отзывов за 30 дней у нас и у выброса | Публичные карточки |
| Бесплатных мест в топ-5 у двери (`mest_bespl_iz_7`; если запросов больше, в примечании «из N») | Замер позиций, модуль 07 |
| Спрос по 5 услугам против прошлого периода | Вордстат (внешний контур), в процентах |
| Фото, позиций каталога, плиток витрины с ценой | Публичная карточка (`advert.products`) |

## Колонки аудита (с версии 4.0.0)

Добавлены в конец строки, старые колонки не тронуты: в снимках до 4.0.0 они
пустые, и это нормально.

| Поле | Откуда |
|---|---|
| `zvonki_podmennyy_2n`, `zvonki_propushch_dolya` | Кабинет, «Статистика»: звонки подменного номера за 2 недели и доля пропущенных. Норма меньше 5%, флаг больше 10% (N-13) |
| `podpiska_aktivna`, `podpiska_perehody_2n`, `podpiska_deystviya_2n`, `podpiska_dney_do_prodleniya` | Кабинет, «Реклама» и «Статистика». До продления 7 дней и меньше — отдельное сообщение в чат |
| `plitok_vsego`, `plitok_bez_ceny` | Публичная карточка (`advert.products`). «Без цены» — счётчик, а не флаг: правило цены в N-08 |
| `obyavleniy_vsego` | Для карточек, где вместо витрины объявления подписки |
| `zayavki_s_plitok_2n`, `vizity_s_plitok_mes` | Метрика сайта по `utm_term` и выгрузка заявок (`zayavki_svodka.py`). Визиты раз в месяц |
| `poziciy_bez_foto`, `poziciy_bez_ceny`, `poziciy_publichno_vs_kabinet` | Снимок карточки против кабинета (R-16): публично позиций обычно больше |
| `foto_novyh_2n`, `foto_poslednee_dney` | Снимок карточки. Норма 5–10 фото в месяц, старше 60 дней — флаг (N-07) |
| `otvety_dolya`, `otvet_chasov_mediana` | Пакеты обхода отзывов: доля отвеченных и медиана времени ответа |
| `pravki_polzovateley_2n` | Кабинет: правки пользователей за период (публикуются сами через 3 дня) |
| `top3_mest_iz_zamera` | Замер позиций (модуль 07): в скольких парах «точка × запрос» мы в топ-3 |
| `sovetov_sdelano_iz_proshlyh` | «N из M» по советам прошлого аудита |
| `tarif_kartochki` | Снимок карточки: Базовый, Расширенный, Продвинутый. Проверяется первым: на Базовом часть упаковки людям не видна (N-02) |

Если нужной колонки нет, добавь её в конец и предложи в «Как улучшить скилл»:
старые строки останутся пустыми в новой колонке, и это нормально.

## Журнал правок

Одна строка на каждую заметную правку, нашу, клиники или Яндекса. Без журнала
рост не к чему привязать. Колонка «Шаг и цифра» нужна, чтобы видеть, когда
две правки бьют в одну цифру: тогда их эффект не разделить, и в отчёте так и
пишем «не различить».

| Дата | Кто | Что сделали или что случилось | Шаг воронки и цифра | Ждём | Когда проверить | Результат |
|---|---|---|---|---|---|---|
| ДД.ММ | агентство | Цены на 4 плитках витрины | Клик по строке; клики по `utm_term` | +N кликов в неделю | ДД.ММ, через 2–4 недели | |
| ДД.ММ | клиника | Администратор просит отзывы после визита | Отзывы → место; заработанные визиты | 3 отзыва в неделю, визиты через 4–8 недель | ДД.ММ | |
| ДД.ММ | Яндекс | Сбой рекламы | — | — | Исключить недели из сравнения | |

Шаги воронки: спрос, попадание в список, место, клик по строке, действие
(звонок, маршрут, кнопка), заявка, запись, визит в клинику.
