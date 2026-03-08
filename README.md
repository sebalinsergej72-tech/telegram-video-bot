# Telegram Video Download Bot

Бот для скачивания видео из YouTube и Instagram. Репозиторий подготовлен для запуска в Railway без зависимости от локального компьютера.

## Как работает в облаке

- Telegram-бот обрабатывает сообщения через polling.
- На Railway дополнительно поднимается HTTP healthcheck-сервер на `PORT`, чтобы сервис считался живым и не зависел от локального запуска.
- `railway.json`, `Procfile` и `nixpacks.toml` уже готовы для деплоя.

## Переменные окружения

- `BOT_TOKEN` — обязателен, токен бота от [@BotFather](https://t.me/BotFather)
- `INSTAGRAM_SESSION_ID` — опционален, нужен для скачивания некоторых закрытых или ограниченных Instagram-ссылок
- `PUBLIC_BASE_URL` — обязателен для облачного режима webhook, например `https://worker-production-d0fe.up.railway.app`
- `ALLOW_POLLING` — опционален только для явной локальной разработки; без него локальный запуск запрещен

## Локальный запуск

1. Установи зависимости:
   ```bash
   pip install -r requirements.txt
   ```

2. Создай `.env`:
   ```bash
   cp .env.example .env
   ```

3. Заполни переменные:
   ```env
   BOT_TOKEN=...
   INSTAGRAM_SESSION_ID=
   ALLOW_POLLING=true
   ```

4. Запусти бота:
   ```bash
   python bot.py
   ```

## Деплой в Railway

1. Создай отдельный сервис из этого репозитория.
2. Убедись, что Railway использует корень репозитория как `Root Directory`.
3. Добавь переменную `BOT_TOKEN`.
4. Добавь переменную `PUBLIC_BASE_URL` со своим Railway-доменом.
5. Если нужен Instagram, добавь `INSTAGRAM_SESSION_ID`.
6. После деплоя проверь, что `/health` отвечает `200 OK`.

В облаке бот работает через webhook. Локальный polling по умолчанию отключен, поэтому случайный `python bot.py` больше не должен перехватывать updates.

## Использование

Отправь боту ссылку на видео из YouTube или Instagram, и он покажет кнопки:
- `Видео`
- `Аудио`

Команды тоже остаются:
- `/audio https://...`
- `/video https://...`

Поддерживаемые ссылки:
- `https://www.youtube.com/watch?v=...`
- `https://youtu.be/...`
- `https://www.youtube.com/shorts/...`
- `https://www.instagram.com/reel/...`
- `https://www.instagram.com/p/...`

Ограничение: максимальный размер отправляемого файла — 50 МБ.
