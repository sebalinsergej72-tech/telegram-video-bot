# Telegram Video Download Bot

Бот для скачивания видео из YouTube и Instagram.

## Установка

1. Получи токен бота у [@BotFather](https://t.me/BotFather) в Telegram:
   - Отправь `/newbot`
   - Введи имя и username бота
   - Скопируй токен

2. Установи зависимости:
   ```bash
   cd telegram-video-bot
   pip install -r requirements.txt
   ```

3. Создай файл `.env` и добавь токен:
   ```bash
   cp .env.example .env
   # Открой .env и вставь свой токен
   ```

4. Запусти бота:
   ```bash
   python bot.py
   ```

## Использование

Отправь боту ссылку на видео из YouTube или Instagram — он скачает и отправит видео в чат.

Поддерживаемые ссылки:
- `https://www.youtube.com/watch?v=...`
- `https://youtu.be/...`
- `https://www.youtube.com/shorts/...`
- `https://www.instagram.com/reel/...`
- `https://www.instagram.com/p/...`

Ограничение: максимальный размер видео — 50 МБ (лимит Telegram).
