# MTProto Proxy Bot

Telegram-бот, который каждый час парсит MTProto-прокси с [mtproto.cloud](https://mtproto.cloud/) и публикует их в Telegram-канал. Полностью бесплатный хостинг на GitHub Actions.

## Возможности

- Автопарсинг прокси каждый час
- Публикация в указанный канал от имени бота
- Две кнопки: «Проверить» и «Подключиться» (формат `tg://proxy?...`)
- Полностью serverless — запускается в GitHub Actions

## Настройка

### 1. Telegram API
1. Откройте <https://my.telegram.org>
2. Войдите по номеру телефона
3. **API development tools** → Create new application
4. Скопируйте `api_id` и `api_hash`

### 2. Бот
1. В Telegram напишите [@BotFather](https://t.me/BotFather)
2. Команда `/newbot`, следуйте инструкциям
3. Скопируйте токен

### 3. Канал
1. Создайте канал (например, `@mtprotoactual`)
2. Добавьте бота в канал **администратором** с правом публиковать сообщения

### 4. GitHub-репозиторий и секреты
1. Создайте репозиторий на GitHub
2. Залейте код (см. ниже)
3. **Settings → Secrets and variables → Actions → New repository secret**

Добавьте 4 секрета:

| Имя | Значение |
| --- | --- |
| `API_ID` | ваш `api_id` (только цифры) |
| `API_HASH` | ваш `api_hash` |
| `BOT_TOKEN` | токен бота от BotFather |
| `CHANNEL_USERNAME` | username канала **без @** (например `mtprotoactual`) |

### 5. Активация Actions
1. Вкладка **Actions** → выберите workflow **Hourly MTProto Proxy Publisher**
2. Нажмите **Enable workflow**
3. Для первого теста — **Run workflow**

## Локальный запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # затем заполните .env реальными значениями
python main.py
```

## Расписание

Cron в `.github/workflows/hourly_proxy.yml`:
```yaml
schedule:
  - cron: '0 * * * *'     # каждый час
  # - cron: '0 */2 * * *'  # каждые 2 часа
  # - cron: '0 0 * * *'    # раз в сутки
```

## Безопасность

- Реальные `API_ID` / `API_HASH` / `BOT_TOKEN` хранятся **только** в GitHub Secrets, в коде их нет
- Файл `.env` добавлен в `.gitignore`
- Файл `*.session` (Telethon) тоже игнорируется — коммитить его нельзя

## Лицензия
MIT
