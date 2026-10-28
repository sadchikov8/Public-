#!/usr/bin/env python3
"""Генератор сайту emuz.pp.ua.

Джерела:
  data/used.csv, data/new.csv  — опубліковані вкладки таблиці «Сайт» (оновлюються з --fetch)
  data/media.json              — фото/відео по VIN (оновлює scripts/sync_photos.py)
  build/models.json            — характеристики моделей
  build/model_rules.json       — як зв'язати рядок таблиці з моделлю, назви брендів, міст
  build/legacy.json            — старі сторінки → VIN (для переадресації)

Результат: index.html, auto/*.html, sitemap.xml, старі *.html → переадресація.
"""
import csv, html, io, json, os, re, sys, urllib.parse, urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://emuz.pp.ua"
PHONE = "+380938789000"
TG = "https://t.me/+380938789000"
VIBER = "viber://chat?number=%2B380938789000"
# Опубліковані вкладки таблиці «Сайт» (це публічні CSV, не секрет)
CSV_URLS = {"used": "https://docs.google.com/spreadsheets/d/e/2PACX-1vS2x4zNBLq9G3tfawNYTE5Hfvz3ZNCrt5aPtO5tYxCnEsZnJqoCFWXYgFHjYsv7kResza9-zDJzE4pP/pub?single=true&output=csv&gid=1", "new": "https://docs.google.com/spreadsheets/d/e/2PACX-1vS2x4zNBLq9G3tfawNYTE5Hfvz3ZNCrt5aPtO5tYxCnEsZnJqoCFWXYgFHjYsv7kResza9-zDJzE4pP/pub?single=true&output=csv&gid=2"}

def p(*a): return os.path.join(ROOT, *a)
def esc(s): return html.escape(str(s if s is not None else ""), quote=True)
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return default

RULES = load_json(p("build", "model_rules.json"), {})
MODELS = load_json(p("build", "models.json"), {})
LEGACY = load_json(p("build", "legacy.json"), {})
MEDIA = load_json(p("data", "media.json"), {})

COLORS = {"WHITE": "білий", "BLACK": "чорний", "GRAY": "сірий", "GREY": "сірий", "DARK GRAY": "темно-сірий",
          "SMOKY GRAY": "димчасто-сірий", "SILVER": "сріблястий", "BLUE": "синій", "GREEN": "зелений",
          "RED": "червоний", "PURPLE": "фіолетовий", "BEIGE": "бежевий", "BROWN": "коричневий",
          "ORANGE": "помаранчевий", "YELLOW": "жовтий"}

# ---------------------------------------------------------------- data fetch
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "emuz-site-builder"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")

def update_data():
    """Завантажує CSV з опублікованої таблиці. Не перезаписує дані, якщо відповідь підозріла."""
    for name, env, min_rows in (("used", "USED_CSV_URL", 5), ("new", "NEW_CSV_URL", 1)):
        url = os.environ.get(env) or CSV_URLS[name]
        if not url:
            print(f"! {env} не задано — використовую data/{name}.csv як є"); continue
        try:
            text = fetch(url)
        except Exception as e:
            print(f"! не вдалося завантажити {name}: {e} — лишаю попередні дані"); continue
        rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
        bad = any("#REF" in c or "#ERROR" in c or "#N/A" in c for r in rows[:3] for c in r)
        if bad or len(rows) - 1 < min_rows:
            print(f"! {name}: відповідь підозріла ({len(rows)-1} рядків) — лишаю попередні дані"); continue
        with open(p("data", f"{name}.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print(f"✓ {name}: {len(rows)-1} рядків")

def read_csv(name):
    path = p("data", f"{name}.csv")
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]

# ---------------------------------------------------------------- helpers
def num(s):
    s = re.sub(r"[^0-9.]", "", str(s or "").replace(",", "."))
    try: return float(s) if s else None
    except ValueError: return None

def money(v):
    return "$" + f"{int(round(v)):,}".replace(",", " ") if v else "Ціну уточнюйте"

def km(v):
    return f"{int(v):,}".replace(",", " ") + " км" if v else ""

def slugify(*parts):
    s = "-".join(str(x) for x in parts if x)
    s = s.lower().replace("&", "").replace("+", "plus")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")

def brand_name(b):
    return RULES.get("brand_names", {}).get((b or "").strip().upper(), (b or "").strip().title())

def model_name(m):
    m = re.sub(r"^\d{4}\s+", "", (m or "").strip())          # "2025 Tang DM-i" → "Tang DM-i"
    m = re.sub(r"\bOO1\b", "001", m)
    m = re.sub(r"(\d)(DM-?i|DM|EV)\b", r"\1 \2", m, flags=re.I)   # "06DM-i" → "06 DM-i"
    return re.sub(r"\bL (\d)\b", r"L\1", m)                          # "L 7" → "L7"

def city(loc):
    loc = (loc or "").strip()
    return RULES.get("cities", {}).get(loc.upper(), loc.title() if loc.isupper() else loc)

def match_model(text):
    t = text.lower()
    for rx, key in RULES.get("models", []):
        if re.search(rx, t) and key in MODELS: return key
    return None

def fuel_type(text, key):
    if key and MODELS.get(key, {}).get("type"): return MODELS[key]["type"]
    t = text.lower()
    for rx, tp in RULES.get("types", []):
        if re.search(rx, t): return tp
    return "EV"

def clean_notes(info):
    """'USED 10074KM BLACK INTERIOR 20INCH...' → 'Чорний салон · 20INCH ...' (без пробігу)."""
    s = re.sub(r"(?i)used\s*[0-9][0-9 .]*\s*(km|км|miles|m)\b", "", info or "")
    s = re.sub(r"(?i)\b([A-Z&\- ]+?)\s+INTERIOR\b", lambda m: "салон: " + m.group(1).strip().lower(), s)
    parts = [x.strip(" ,;") for x in re.split(r"[\n]+|\s{2,}", s) if x.strip(" ,;")]
    return " · ".join(parts)

def media_for(vins):
    """Повертає (фото[], youtube[]) — перший VIN з групи, у якого є медіа."""
    for v in vins:
        m = MEDIA.get(v)
        if not m: continue
        photos = [("/" + x.lstrip("/")) for x in m.get("photos", [])]
        if not photos:
            photos = [f"https://lh3.googleusercontent.com/d/{i}=w1600" for i in m.get("drive_photos", [])]
        if photos or m.get("youtube"):
            return photos, m.get("youtube", [])
    return [], []

# ---------------------------------------------------------------- model
def build_cars():
    cars = []
    for r in read_csv("used"):
        vin = (r.get("VIN") or "").strip().upper()
        if not vin: continue
        b, m, trim = r.get("Марка", ""), r.get("Модель", ""), (r.get("Комплектація") or "").strip()
        text = f"{b} {m} {trim}"
        key = match_model(text)
        photos, yt = media_for([vin])
        cars.append(dict(
            kind="used", vin=vin, vins=[vin], brand=brand_name(b), model=model_name(m), trim=trim,
            year=(r.get("Рік") or "").strip(), color=COLORS.get((r.get("Колір") or "").strip().upper(), (r.get("Колір") or "").strip().lower()),
            mileage=num(r.get("Пробіг км")), price=num(r.get("Ціна $")), loc=city(r.get("Де")),
            port=(r.get("Порт") or "").strip(), status=(r.get("Статус") or "free").strip(),
            where=(r.get("Наявність") or "stock").strip(), notes=clean_notes(r.get("Опис")),
            qty="", key=key, type=fuel_type(text, key), photos=photos, youtube=yt,
            slug=slugify(brand_name(b), model_name(m), vin[-5:])))
    for r in read_csv("new"):
        b, m, trim = r.get("Марка", ""), r.get("Модель", ""), (r.get("Комплектація") or "").strip()
        if not b.strip(): continue
        vins = [v.strip().upper() for v in (r.get("VINs") or "").split() if len(v.strip()) >= 11]
        text = f"{b} {m} {trim}"
        key = match_model(text)
        photos, yt = media_for(vins)
        qty = (r.get("Кількість") or "").strip()
        where = (r.get("Наявність") or "stock").strip()
        cars.append(dict(
            kind="new", vin="", vins=vins, brand=brand_name(b), model=model_name(m), trim=trim,
            year=(r.get("Рік") or "").strip(), color="", mileage=None, price=num(r.get("Ціна від $")),
            loc="", port="", status="reserved" if qty == "бронь" else "free", where=where, notes="",
            qty=qty, key=key, type=fuel_type(text, key), photos=photos, youtube=yt,
            slug=slugify(brand_name(b), model_name(m), trim, r.get("Рік"), "v-dorozi" if where == "transit" else "")))
    # унікальні slug
    seen = {}
    for c in cars:
        n = seen.get(c["slug"], 0); seen[c["slug"]] = n + 1
        if n: c["slug"] += f"-{n+1}"
    rank = {("free", "stock"): 0, ("free", "transit"): 1, ("reserved", "stock"): 2, ("reserved", "transit"): 3}
    cars.sort(key=lambda c: (c["status"] == "sold", rank.get((c["status"], c["where"]), 4), c["price"] or 1e9))
    return cars

def title(c):
    return " ".join(x for x in (c["brand"], c["model"]) if x)

def status_badge(c):
    if c["status"] == "sold": return '<span class="badge b-sold">Продано</span>'
    if c["status"] == "reserved": return '<span class="badge b-res">Заброньовано</span>'
    if c["where"] == "transit":
        port = f' · порт {esc(c["port"])}' if re.match(r"\d{2}\.\d{2}\.\d{4}$", c["port"] or "") else ""
        return f'<span class="badge b-way">В дорозі{port}</span>'
    loc = f' · {esc(c["loc"])}' if c["loc"] else ""
    return f'<span class="badge b-ok">В наявності{loc}</span>'

def meta_line(c):
    parts = [c["year"] and f'{c["year"]} р.', c["kind"] == "new" and "Новий", km(c["mileage"]), c["trim"]]
    return " · ".join(esc(x) for x in parts if x)

# ---------------------------------------------------------------- templates
LOGO = '<img src="/favicon.svg" alt="EM Electro Motors" width="44" height="44">'

def head(t, desc, url, img, extra=""):
    og = img if img.startswith("http") else SITE + img
    return f"""<!DOCTYPE html>
<html lang="uk"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(t)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="website"><meta property="og:url" content="{esc(url)}">
<meta property="og:title" content="{esc(t)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{esc(og)}"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css?v={VERSION}">{extra}
</head><body>
<header class="top"><a class="brand" href="/">{LOGO}<span>ELECTRO MOTORS</span></a>
<a class="top-call" href="tel:{PHONE}">{esc(PHONE_PRETTY)}</a></header>
"""

FOOT = f"""
<footer class="foot">
  <div>ТОВ «ЕЛЕКТРО-МОТОРС» · оплата на рахунок · кредит та розтермінування від 10%</div>
  <div>Шоуруми: Ужгород · Львів · Київ · Одеса · Вінниця · Кропивницький · Харків · Дніпро</div>
</footer>
<nav class="contact-bar">
  <a href="tel:{PHONE}" class="cb-call"><svg viewBox="0 0 24 24"><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z"/></svg>Подзвонити</a>
  <a href="{VIBER}" class="cb-viber"><svg viewBox="0 0 24 24"><path d="M12 2C6.9 2 3 5.4 3 10.2c0 2.7 1.2 5 3.2 6.5V21l3.2-1.8c.8.2 1.7.3 2.6.3 5.1 0 9-3.4 9-8.2S17.1 2 12 2zm4.6 11.6c-.2.5-1.1 1-1.6 1-.4 0-.9.1-2.8-.6-2.4-.9-3.9-3.3-4-3.5-.1-.2-1-1.3-1-2.4s.6-1.7.8-1.9c.2-.2.5-.3.6-.3h.5c.1 0 .3 0 .5.4l.7 1.7c.1.1.1.3 0 .4l-.3.5-.4.4c-.1.1-.2.3-.1.5.2.3.7 1.1 1.5 1.8 1 .9 1.8 1.1 2.1 1.3.2.1.4.1.5-.1l.7-.8c.2-.2.3-.2.5-.1l1.6.8c.2.1.4.2.4.3.1.1.1.6-.1 1z"/></svg>Viber</a>
  <a href="{TG}" class="cb-tg"><svg viewBox="0 0 24 24"><path d="M21.9 4.3 18.7 19.4c-.2 1-.9 1.3-1.7.8l-4.8-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.9 8.9-8c.4-.3-.1-.5-.6-.2L6.5 13.2 1.8 11.7c-1-.3-1-1 .2-1.5L20.6 3c.9-.3 1.6.2 1.3 1.3z"/></svg>Telegram</a>
</nav>
"""

def card(c):
    href = f"/auto/{c['slug']}.html"
    img = c["photos"][0] if c["photos"] else ""
    photo = (f'<img loading="lazy" src="{esc(img)}" alt="{esc(title(c))}">' if img
             else f'<div class="ph-empty"><span>{esc(c["brand"])}</span>Фото скоро</div>')
    qty = f'<span class="qty">{esc(c["qty"])} авто</span>' if c["qty"] and c["qty"] not in ("1", "бронь") else ""
    price_prefix = "від " if c["kind"] == "new" and c["qty"] not in ("1", "") else ""
    return f"""<a class="card" href="{href}" data-cond="{c['kind']}" data-type="{esc(c['type'])}" data-where="{esc(c['where'])}"
 data-status="{esc(c['status'])}" data-brand="{esc(c['brand'])}" data-price="{int(c['price'] or 0)}" data-km="{int(c['mileage'] or 0)}" data-year="{esc(c['year'])}">
  <div class="card-ph">{photo}<span class="type">{esc(c['type'])}</span>{qty}</div>
  <div class="card-body">
    {status_badge(c)}
    <h3>{esc(title(c))}</h3>
    <div class="meta">{meta_line(c)}</div>
    <div class="price">{price_prefix}{esc(money(c['price']))}</div>
  </div>
</a>"""

def page_index(cars):
    live = [c for c in cars if c["status"] != "sold"]
    sold = [c for c in cars if c["status"] == "sold"]
    brands = sorted({c["brand"] for c in live})
    n_stock = sum(1 for c in live if c["where"] == "stock")
    cover = next((c["photos"][0] for c in live if c["photos"]), "/assets/og.png")
    out = head("EM Electro Motors — електромобілі та гібриди з Китаю",
               f"{len(live)} пропозицій: б/у та нові EV, PHEV, EREV. BYD, ZEEKR, Li Auto, Lynk & Co та ін. Шоуруми у 8 містах України.",
               SITE + "/", cover)
    out += f"""<main>
<section class="hero">
  <h1>Електромобілі та гібриди з Китаю</h1>
  <p>Б/у та нові · {len(live)} пропозицій · {n_stock} вже в Україні</p>
  <ul class="trust"><li>8 шоурумів</li><li>Оплата на рахунок ТОВ</li><li>Кредит від 10%</li></ul>
</section>
<section class="filters" id="filters">
  <div class="seg" data-f="cond"><button class="on" data-v="">Всі</button><button data-v="used">З пробігом</button><button data-v="new">Нові</button></div>
  <div class="seg" data-f="where"><button class="on" data-v="">Будь-де</button><button data-v="stock">В Україні</button><button data-v="transit">В дорозі</button></div>
  <div class="row">
    <select data-f="type"><option value="">Тип: всі</option><option value="EV">EV</option><option value="PHEV">PHEV</option><option value="EREV">EREV</option><option value="HEV">HEV</option></select>
    <select data-f="brand"><option value="">Марка: всі</option>{''.join(f'<option>{esc(b)}</option>' for b in brands)}</select>
    <select data-f="price"><option value="">Ціна: будь-яка</option><option value="0-30000">до $30 000</option><option value="30000-45000">$30–45 тис.</option><option value="45000-999999">від $45 000</option></select>
    <select data-f="sort"><option value="">Спершу в наявності</option><option value="price-asc">Дешевші</option><option value="price-desc">Дорожчі</option><option value="km-asc">Менший пробіг</option></select>
  </div>
  <div class="found" id="found"></div>
</section>
<section class="grid" id="grid">
{''.join(card(c) for c in live)}
</section>
<p class="empty" id="empty">Нічого не знайдено — змініть фільтри або напишіть нам, підберемо під замовлення.</p>
"""
    if sold:
        out += f"""<details class="sold"><summary>Вже продано ({len(sold)})</summary>
<section class="grid">{''.join(card(c) for c in sold)}</section></details>
"""
    out += "</main>" + FOOT + f'<script src="/assets/app.js?v={VERSION}"></script></body></html>'
    return out

def yt_block(ids):
    if not ids: return ""
    frames = "".join(f'<div class="yt"><iframe loading="lazy" src="https://www.youtube-nocookie.com/embed/{esc(i)}" title="Відео" allow="fullscreen" allowfullscreen></iframe></div>' for i in ids)
    return f'<section class="sec"><h2>Відео</h2><div class="yts">{frames}</div></section>'

def page_car(c):
    t = title(c)
    url = f"{SITE}/auto/{c['slug']}.html"
    model = MODELS.get(c["key"] or "", {})
    desc_bits = [c["year"] and f"{c['year']} р.", km(c["mileage"]), c["trim"], money(c["price"])]
    desc = f"{t}: " + ", ".join(x for x in desc_bits if x) + ". EM Electro Motors."
    cover = c["photos"][0] if c["photos"] else "/assets/og.png"
    out = head(f"{t} {c['year']} — {money(c['price'])} | EM Electro Motors", desc, url, cover)
    if c["photos"]:
        slides = "".join(f'<img {LAZY if i else ""}src="{esc(s)}" alt="{esc(t)} — фото {i+1}">' for i, s in enumerate(c["photos"]))
        gallery = f'<div class="gal" id="gal"><div class="gal-track">{slides}</div><span class="gal-n"><b>1</b> / {len(c["photos"])}</span></div>'
    else:
        gallery = f'<div class="gal gal-empty"><span>{esc(c["brand"])}</span>Фото з\'являться найближчим часом</div>'

    facts = []
    if c["year"]: facts.append(("Рік", c["year"]))
    if c["kind"] == "used": facts.append(("Пробіг", km(c["mileage"]) or "—"))
    else: facts.append(("Стан", "Новий"))
    facts.append(("Тип", c["type"]))
    if c["trim"]: facts.append(("Комплектація", c["trim"]))
    if c["color"]: facts.append(("Колір", c["color"]))
    if c["where"] == "stock" and c["loc"]: facts.append(("Де зараз", c["loc"]))
    if c["where"] == "transit":
        facts.append(("Де зараз", c["loc"] or "В дорозі"))
        if c["port"]: facts.append(("Очікується в порту", c["port"]))
    if c["vin"]: facts.append(("VIN", "…" + c["vin"][-6:]))
    if c["kind"] == "new" and c["qty"] and c["qty"] not in ("1", "бронь"): facts.append(("Доступно", c["qty"] + " авто"))
    facts_html = "".join(f"<div><dt>{esc(a)}</dt><dd>{esc(b)}</dd></div>" for a, b in facts)

    specs = model.get("specs") or []
    specs_html = ("<section class=\"sec\"><h2>Характеристики моделі</h2><table class=\"specs\">" +
                  "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in specs) +
                  "</table></section>") if specs else ""
    feats = list(dict.fromkeys(model.get("features") or []))
    feats_html = ("<section class=\"sec\"><h2>Особливості</h2><ul class=\"feats\">" +
                  "".join(f"<li>{esc(f)}</li>" for f in feats) + "</ul></section>") if feats else ""
    notes_html = f'<section class="sec"><h2>Про цей автомобіль</h2><p class="notes">{esc(c["notes"])}</p></section>' if c["notes"] else ""
    price_label = "Ціна від" if c["kind"] == "new" and c["qty"] not in ("1", "") else "Ціна"
    msg = f"Вітаю! Цікавить {t} {c['year']}" + (f" (VIN …{c['vin'][-6:]})" if c["vin"] else f", {c['trim']}") + f" — {url}"
    out += f"""<main class="car">
<a class="back" href="/">← Усі авто</a>
{gallery}
<section class="car-head">
  {status_badge(c)}
  <h1>{esc(t)}</h1>
  <div class="meta">{meta_line(c)}</div>
  <div class="price-box"><span>{price_label}</span><b>{esc(money(c['price']))}</b></div>
  <p class="pay">Оплата на рахунок ТОВ · кредит та розтермінування від 10%</p>
  <div class="cta">
    <a class="btn-main" href="{TG}?text={esc(urllib.parse.quote(msg))}">Запитати про це авто</a>
    <a class="btn-sec" href="tel:{PHONE}">{esc(PHONE_PRETTY)}</a>
  </div>
</section>
<section class="sec"><dl class="facts">{facts_html}</dl></section>
{notes_html}{specs_html}{feats_html}{yt_block(c["youtube"])}
</main>""" + FOOT + f'<script src="/assets/app.js?v={VERSION}"></script></body></html>'
    return out

def page_redirect(target):
    return f"""<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8">
<title>Переадресація…</title><link rel="canonical" href="{SITE}{target}">
<meta http-equiv="refresh" content="0; url={target}"><meta name="robots" content="noindex">
<script>location.replace("{target}")</script></head>
<body><a href="{target}">Перейти</a></body></html>"""

PHONE_PRETTY = "+38 093 878 90 00"
LAZY = 'loading="lazy" '
VERSION = date.today().strftime("%Y%m%d")

# ---------------------------------------------------------------- main
def main():
    if "--fetch" in sys.argv: update_data()
    cars = build_cars()
    if not cars:
        sys.exit("! Немає даних — сайт не перебудовано")
    os.makedirs(p("auto"), exist_ok=True)
    keep = set()
    for c in cars:
        fn = f"{c['slug']}.html"; keep.add(fn)
        with open(p("auto", fn), "w", encoding="utf-8") as f: f.write(page_car(c))
    for fn in os.listdir(p("auto")):            # видалити сторінки авто, яких більше немає
        if fn.endswith(".html") and fn not in keep: os.remove(p("auto", fn))
    with open(p("index.html"), "w", encoding="utf-8") as f: f.write(page_index(cars))
    # старі адреси → нові
    by_vin = {v: c for c in cars for v in c["vins"]}
    by_key = {}
    for c in cars:
        if c["key"] and c["status"] != "sold": by_key.setdefault(c["key"], c)
    for old, info in LEGACY.items():
        c = by_vin.get(info.get("vin") or "") or by_key.get(info.get("model") or "")
        target = f"/auto/{c['slug']}.html" if c else "/"
        with open(p(old), "w", encoding="utf-8") as f: f.write(page_redirect(target))
    today = date.today().isoformat()
    urls = [SITE + "/"] + [f"{SITE}/auto/{c['slug']}.html" for c in cars if c["status"] != "sold"]
    with open(p("sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.writelines(f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
        f.write("</urlset>\n")
    live = sum(1 for c in cars if c["status"] != "sold")
    print(f"✓ {len(cars)} сторінок авто ({live} активних, {len(cars)-live} продано), {len(LEGACY)} старих адрес переадресовано")

if __name__ == "__main__":
    main()
