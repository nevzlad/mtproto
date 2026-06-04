import asyncio
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import aiohttp
from telethon import TelegramClient
from telethon.tl.custom import Button


API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL_USERNAME = os.environ['CHANNEL_USERNAME']

FEED_URL = "https://mtproto.cloud/api/feed"


class MTProtoProxyBot:
    def __init__(self):
        self.client = TelegramClient('proxy_bot', API_ID, API_HASH)
        self.proxies = []

    async def start(self):
        await self.client.start(bot_token=BOT_TOKEN)
        print(f"[{datetime.now()}] Bot started as {CHANNEL_USERNAME} target")

    async def parse_mtproto_cloud(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(FEED_URL, timeout=30) as response:
                    response.raise_for_status()
                    data = await response.json(content_type=None)
        except Exception as e:
            print(f"[{datetime.now()}] Fetch error: {e}")
            return

        items = data.get('items', []) if isinstance(data, dict) else []
        seen = set()
        for item in items:
            if item.get('category') != 'proxy' or item.get('kind') != 'mtproto_proxy':
                continue
            if item.get('status') != 'online':
                continue
            proxy = self._build_proxy(item)
            if not proxy:
                continue
            key = (proxy['server'], proxy['port'], proxy['secret'])
            if key in seen:
                continue
            seen.add(key)
            self.proxies.append(proxy)

        print(f"[{datetime.now()}] Proxies found: {len(self.proxies)}")

    @staticmethod
    def _build_proxy(item):
        server = (item.get('server') or '').strip()
        port = item.get('port')
        share_text = item.get('shareText') or item.get('connectUrl') or ''
        if not server or port is None or not share_text:
            return None
        try:
            port = int(port)
        except (TypeError, ValueError):
            return None
        try:
            qs = parse_qs(urlparse(share_text).query)
        except Exception:
            return None
        secret = (qs.get('secret') or [''])[0].strip()
        if not secret:
            return None
        return {'server': server, 'port': port, 'secret': secret}

    async def send_proxy_message(self, proxy):
        try:
            proxy_link = (
                f"tg://proxy?server={proxy['server']}"
                f"&port={proxy['port']}&secret={proxy['secret']}"
            )

            first_text = (
                f"\u26a1\ufe0f <b>\u041f\u0440\u043e\u043a\u0441\u0438 \u0434\u043b\u044f "
                f"\u041e\u0431\u0445\u043e\u0434\u0430 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438 "
                f"Telegram</b>\n\n"
                f"<b>\u0425\u043e\u0441\u0442:</b> <code>{proxy['server']}</code>\n"
                f"<b>\u041f\u043e\u0440\u0442:</b> <code>{proxy['port']}</code>\n"
                f"<b>\u0421\u0435\u043a\u0440\u0435\u0442:</b> <code>{proxy['secret']}</code>\n\n"
                f"\ud83d\udc49 \u041d\u0430\u0436\u043c\u0438\u0442\u0435 <b>\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f</b> \u043d\u0438\u0436\u0435 \u0438 \u043f\u0440\u043e\u043a\u0441\u0438 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u0443\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438."
            )
            await self.client.send_message(
                CHANNEL_USERNAME, first_text,
                parse_mode='html', link_preview=False
            )

            second_text = (
                f"\ud83d\udd10 <b>\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u043a \u043f\u0440\u043e\u043a\u0441\u0438</b>\n\n"
                f"\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443 \u043d\u0438\u0436\u0435, \u0447\u0442\u043e\u0431\u044b "
                f"\u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u0432 "
                f"Telegram \u0432 \u043e\u0434\u0438\u043d \u043a\u043b\u0438\u043a."
            )
            buttons = [
                [Button.url("\ud83d\udd0c \u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f \u043a \u043f\u0440\u043e\u043a\u0441\u0438", proxy_link)],
            ]
            await self.client.send_message(
                CHANNEL_USERNAME, second_text,
                parse_mode='html', buttons=buttons, link_preview=False
            )

            print(f"[{datetime.now()}] Published proxy: {proxy['server']}:{proxy['port']}")
        except Exception as e:
            print(f"[{datetime.now()}] Send error: {e}")

    async def publish_proxies(self):
        for proxy in self.proxies[:10]:
            await self.send_proxy_message(proxy)
            await asyncio.sleep(2)

    async def run(self):
        await self.start()
        await self.parse_mtproto_cloud()
        if self.proxies:
            await self.publish_proxies()
        else:
            print(f"[{datetime.now()}] No proxies found")
        await self.client.disconnect()


async def main():
    bot = MTProtoProxyBot()
    await bot.run()


if __name__ == '__main__':
    asyncio.run(main())
