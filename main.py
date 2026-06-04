import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.custom import Button


API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL_USERNAME = os.environ['CHANNEL_USERNAME']

MTPROTO_URL = "https://mtproto.cloud/"


class MTProtoProxyBot:
    def __init__(self):
        self.client = TelegramClient('proxy_bot', API_ID, API_HASH)
        self.proxies = []

    async def start(self):
        await self.client.start(bot_token=BOT_TOKEN)
        print(f"[{datetime.now()}] Bot started as {CHANNEL_USERNAME} target")

    async def parse_mtproto_cloud(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(MTPROTO_URL, timeout=30) as response:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    proxy_cards = soup.find_all(
                        'div', class_=re.compile(r'proxy|card|server', re.I)
                    )
                    for card in proxy_cards:
                        proxy_data = self.extract_proxy_from_card(card)
                        if proxy_data:
                            self.proxies.append(proxy_data)

                    text = soup.get_text()
                    self.extract_proxies_from_text(text)

                print(f"[{datetime.now()}] Proxies found: {len(self.proxies)}")
            except Exception as e:
                print(f"[{datetime.now()}] Parse error: {e}")

    def extract_proxy_from_card(self, card):
        try:
            server = port = secret = None

            server_tag = card.find(text=re.compile(r'server|сервер', re.I))
            if server_tag:
                parent = server_tag.find_parent()
                if parent:
                    server_text = parent.get_text(strip=True)
                    server_match = re.search(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', server_text)
                    if server_match:
                        server = server_match.group(1)

            port_tag = card.find(text=re.compile(r'port|порт', re.I))
            if port_tag:
                parent = port_tag.find_parent()
                if parent:
                    port_text = parent.get_text(strip=True)
                    port_match = re.search(r'(\d{2,5})', port_text)
                    if port_match:
                        port = int(port_match.group(1))

            secret_tag = card.find(text=re.compile(r'secret|ключ', re.I))
            if secret_tag:
                parent = secret_tag.find_parent()
                if parent:
                    secret_text = parent.get_text(strip=True)
                    secret_match = re.search(r'([a-fA-F0-9]{32,})', secret_text)
                    if secret_match:
                        secret = secret_match.group(1)

            if server and port and secret:
                return {'server': server, 'port': port, 'secret': secret}
        except Exception as e:
            print(f"Extract error: {e}")
        return None

    def extract_proxies_from_text(self, text):
        patterns = [
            r'server[:\s]+([a-zA-Z0-9.-]+)[\s,\n]+port[:\s]+(\d+)[\s,\n]+secret[:\s]+([a-fA-F0-9]+)',
            r'tg://proxy\?server=([^&]+)&port=(\d+)&secret=([^&\s]+)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 3:
                    proxy = {
                        'server': match[0].strip(),
                        'port': int(match[1]),
                        'secret': match[2].strip(),
                    }
                    if not any(
                        p['server'] == proxy['server'] and p['port'] == proxy['port']
                        for p in self.proxies
                    ):
                        self.proxies.append(proxy)

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
