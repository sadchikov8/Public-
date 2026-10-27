#!/usr/bin/env python3
"""Фото з Google Диска → стиснені WebP у photos/<VIN>/.

Порядок фото в папці VIN:
  00_*.jpg       — обкладинка (перше фото, превʼю в каталозі й месенджерах)
  01_*, 02_* …   — далі в цьому порядку
  x_*            — не показувати
  решта          — за часом зйомки (EXIF), потім за часом зміни файлу

Потрібно: GDRIVE_SA_JSON (ключ сервісного акаунта), DRIVE_ROOT_ID (папка «Video» з папками по VIN).
Сервісному акаунту достатньо доступу «Читач» до кореневої папки.
"""
import csv, io, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def p(*a): return os.path.join(ROOT, *a)

MAX_SIDE = 1600
QUALITY = 78
SOLD_KEEP = 1          # у проданих авто залишаємо лише обкладинку

def vins_needed():
    need, sold = set(), set()
    for name in ("used", "new"):
        path = p("data", f"{name}.csv")
        if not os.path.exists(path): continue
        for r in csv.DictReader(open(path, encoding="utf-8")):
            vs = [r.get("VIN", "")] + (r.get("VINs") or "").split()
            for v in vs:
                v = v.strip().upper()
                if len(v) >= 11:
                    need.add(v)
                    if (r.get("Статус") or "") == "sold": sold.add(v)
    return need, sold

def order_key(f):
    name = f["name"].lower()
    m = re.match(r"^(\d{1,2})_", name)
    if m: return (0, int(m.group(1)), "")
    t = (f.get("imageMediaMetadata") or {}).get("time") or f.get("modifiedTime") or ""
    return (1, 0, t + name)

def main():
    sa = os.environ.get("GDRIVE_SA_JSON")
    root_id = os.environ.get("DRIVE_ROOT_ID")
    if not sa or not root_id:
        print("! GDRIVE_SA_JSON / DRIVE_ROOT_ID не задані — фото не синхронізую"); return
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from PIL import Image, ImageOps

    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    def ls(q, fields):
        out, tok = [], None
        while True:
            r = drive.files().list(q=q, fields=f"nextPageToken, files({fields})", pageSize=1000,
                                   pageToken=tok, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            out += r.get("files", []); tok = r.get("nextPageToken")
            if not tok: return out

    need, sold = vins_needed()
    folders = {}
    for f in ls(f"'{root_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false", "id,name"):
        for v in re.findall(r"[A-HJ-NPR-Z0-9]{17}", f["name"].upper()):   # папка може містити кілька VIN
            folders.setdefault(v, f["id"])

    media = json.load(open(p("data", "media.json"), encoding="utf-8")) if os.path.exists(p("data", "media.json")) else {}
    changed = 0
    for vin in sorted(need):
        fid = folders.get(vin)
        if not fid: continue
        files = ls(f"'{fid}' in parents and mimeType contains 'image/' and trashed=false",
                   "id,name,md5Checksum,modifiedTime,imageMediaMetadata(time)")
        files = [f for f in files if not f["name"].lower().startswith("x_")]
        files.sort(key=order_key)
        if vin in sold: files = files[:SOLD_KEEP]
        entry = media.setdefault(vin, {})
        prev = entry.get("src", [])
        sig = [f["md5Checksum"] for f in files]
        outdir = p("photos", vin)
        if sig == prev and all(os.path.exists(p(x)) for x in entry.get("photos", [])):
            continue
        os.makedirs(outdir, exist_ok=True)
        for old in os.listdir(outdir): os.remove(os.path.join(outdir, old))
        paths = []
        for i, f in enumerate(files):
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=f["id"], supportsAllDrives=True))
            done = False
            while not done: _, done = dl.next_chunk()
            buf.seek(0)
            im = ImageOps.exif_transpose(Image.open(buf)).convert("RGB")
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            rel = f"photos/{vin}/{i:02d}.webp"
            im.save(p(rel), "WEBP", quality=QUALITY, method=6)
            paths.append(rel)
        entry["photos"], entry["src"] = paths, sig
        changed += 1
        print(f"✓ {vin}: {len(paths)} фото")
    # прибрати папки авто, яких більше немає на сайті
    if os.path.isdir(p("photos")):
        for vin in os.listdir(p("photos")):
            if vin not in need:
                for x in os.listdir(p("photos", vin)): os.remove(p("photos", vin, x))
                os.rmdir(p("photos", vin))
                media.get(vin, {}).pop("photos", None); media.get(vin, {}).pop("src", None)
                changed += 1
    json.dump(media, open(p("data", "media.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✓ оновлено {changed} авто")

if __name__ == "__main__":
    main()
