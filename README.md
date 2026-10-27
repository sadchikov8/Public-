# emuz.pp.ua — як працює сайт

Сайт збирається автоматично щогодини (GitHub Actions → «Оновлення сайту»).

| Що | Звідки |
|---|---|
| Авто, ціни, статуси, локації | Базова таблиця → файл «Сайт» (вкладки `used`, `new`) |
| Показати / сховати конкретне авто, інша ціна | «Сайт» → вкладка `ручне` |
| Фото | Google Диск, папка по VIN; `00_` — обкладинка, `01_…` — порядок, `x_` — не показувати |
| Характеристики моделі | `build/models.json` |
| Звʼязок «рядок таблиці → модель» | `build/model_rules.json` |

## Налаштування (один раз)
Settings → Secrets and variables → Actions:
- Variables: `USED_CSV_URL`, `NEW_CSV_URL` (опубліковані CSV), `DRIVE_ROOT_ID` = `1D3JgfTkJQTudIJJtm4PT_pB6dgApwbnL`
- Secret: `GDRIVE_SA_JSON` (ключ сервісного акаунта Google з доступом «Читач» до папки Video)

Ручний запуск: Actions → «Оновлення сайту» → Run workflow.
Локально: `python build/build.py` (без мережі, з `data/*.csv`).
