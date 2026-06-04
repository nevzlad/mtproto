import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime
from telethon import TelegramClient, errors
from telethon.tl.custom import Button
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate


API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL_USERNAME = os.environ['CHANNEL_USERNAME']

MTPROTO_URL = "https://mtproto.cloud/"
FEED_URL = "https://mtproto.cloud/api/feed"


class MTProtoProxyBot:
    def __init__(self):
        self.client = None
        self.proxies = []
        self.relay_proxies = []

    async def fetch_relay_proxies(self):
        print(f"[{datetime.now()}] Fetching relay proxies from API...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(FEED_URL, timeout=30) as response:
                    data = await response.json(content_type=None)
            items = data.get('items', []) if isinstance(data, dict) else []
            seen = set()
            for item in items:
                if item.get('category') != 'proxy' or item.get('kind') != 'mtproto_proxy':
                    continue
                if item.get('status') != 'online':
                    continue
                server = (item.get('server') or '').strip()
                port = item.get('port')
                share_text = item.get('shareText') or item.get('connectUrl') or ''
                if not server or port is None or not share_text:
                    continue
                from urllib.parse import urlparse, parse_qs
                try:
                    qs = parse_qs(urlparse(share_text).query)
                except Exception:
                    continue
                secret = (qs.get('secret') or [''])[0].strip()
                if not secret:
                    continue
                key = (server, port, secret)
                if key in seen:
                    continue
                seen.add(key)
                self.relay_proxies.append({'server': server, 'port': int(port), 'secret': secret})
            print(f"[{datetime.now()}] Relay proxies found: {len(self.relay_proxies)}")
        except Exception as e:
            print(f"[{datetime.now()}] Relay fetch error: {e}")

    async def try_connect_direct(self):
        self.client = TelegramClient('proxy_bot', API_ID, API_HASH, flood_sleep_threshold=0)
        try:
            await self.client.start(bot_token=BOT_TOKEN)
            print(f"[{datetime.now()}] Connected directly")
            return True
        except errors.FloodWaitError as e:
            print(f"[{datetime.now()}] Direct flood wait: sleeping {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return await self.try_connect_direct()
        except Exception as e:
            print(f"[{datetime.now()}] Direct connection failed: {e}")
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None
            return False

    async def try_connect_via_proxy(self, proxy):
        conn = ConnectionTcpMTProxyRandomizedIntermediate
        proxy_tuple = (proxy['server'], proxy['port'], proxy['secret'])
        self.client = TelegramClient(
            'proxy_bot', API_ID, API_HASH,
            connection=conn, proxy=proxy_tuple,
            flood_sleep_threshold=0
        )
        try:
            await self.client.start(bot_token=BOT_TOKEN)
            print(f"[{datetime.now()}] Connected via proxy {proxy['server']}:{proxy['port']}")
            return True
        except errors.FloodWaitError as e:
            print(f"[{datetime.now()}] Proxy flood wait: sleeping {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return await self.try_connect_via_proxy(proxy)
        except Exception as e:
            print(f"[{datetime.now()}] Proxy {proxy['server']}:{proxy['port']} failed: {e}")
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None
            return False

    async def start(self):
        print(f"[{datetime.now()}] Starting bot, target: {CHANNEL_USERNAME}")

        if await self.try_connect_direct():
            return

        await self.fetch_relay_proxies()
        for proxy in self.relay_proxies:
            if await self.try_connect_via_proxy(proxy):
                return

        raise RuntimeError("Could not connect to Telegram via any method")

    async def parse_mtproto_cloud(self):
        print(f"[{datetime.now()}] PARSER: Starting parsing...")
        seen_set = set()

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(MTPROTO_URL, timeout=30) as response:
                    html = await response.text()
                print(f"[{datetime.now()}] PARSER: HTML page loaded, {len(html)} bytes")

                for m in re.finditer(r'https://mtproto\.cloud/connect\?[^"\'<>]+', html):
                    from urllib.parse import urlparse, parse_qs
                    qs = parse_qs(urlparse(m.group()).query)
                    server = (qs.get('server') or [''])[0].strip().rstrip('.')
                    port_str = (qs.get('port') or [''])[0]
                    secret = (qs.get('secret') or [''])[0].strip()
                    if not server or not port_str or not secret:
                        continue
                    try:
                        port = int(port_str)
                    except (TypeError, ValueError):
                        continue
                    key = (server, port, secret)
                    if key in seen_set:
                        continue
                    seen_set.add(key)
                    proxy = {'server': server, 'port': port, 'secret': secret}
                    self.proxies.append(proxy)
                    print(f"[{datetime.now()}] PARSER: HTML proxy: {server}:{port}")
            except Exception as e:
                print(f"[{datetime.now()}] PARSER: HTML error (fallback to API): {e}")
                try:
                    async with session.get(FEED_URL, timeout=30) as response:
                        data = await response.json(content_type=None)
                    items = data.get('items', []) if isinstance(data, dict) else []
                    print(f"[{datetime.now()}] PARSER: API feed returned {len(items)} items")
                    for item in items:
                        if item.get('category') != 'proxy' or item.get('kind') != 'mtproto_proxy':
                            continue
                        if item.get('status') != 'online':
                            continue
                        server = (item.get('server') or '').strip()
                        port = item.get('port')
                        share_text = item.get('shareText') or item.get('connectUrl') or ''
                        if not server or port is None or not share_text:
                            continue
                        from urllib.parse import urlparse, parse_qs
                        try:
                            qs = parse_qs(urlparse(share_text).query)
                        except Exception:
                            continue
                        secret = (qs.get('secret') or [''])[0].strip()
                        if not secret:
                            continue
                        key = (server, int(port), secret)
                        if key in seen_set:
                            continue
                        seen_set.add(key)
                        proxy = {'server': server, 'port': int(port), 'secret': secret}
                        self.proxies.append(proxy)
                        print(f"[{datetime.now()}] PARSER: API proxy: {server}:{port}")
                except Exception as e2:
                    print(f"[{datetime.now()}] PARSER: API fallback also failed: {e2}")

            print(f"[{datetime.now()}] PARSER: Total proxies found: {len(self.proxies)}")

    async def _call_with_retry(self, fn, *args, max_retries=3, **kwargs):
        for attempt in range(max_retries):
            try:
                return await fn(*args, **kwargs)
            except errors.FloodWaitError as e:
                wait = e.seconds * (1 + attempt)
                print(f"[{datetime.now()}] Flood wait {e.seconds}s, sleeping {wait}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(wait)
        raise RuntimeError(f"Failed after {max_retries} retries")

    async def _send_post_with_button(self, text, button_text, button_url):
        try:
            buttons = [[Button.url(button_text, button_url)]]
            msg = await self._call_with_retry(
                self.client.send_message, CHANNEL_USERNAME, text,
                buttons=buttons, parse_mode='html', link_preview=False
            )
            print(f"[{datetime.now()}] Post sent, msg_id={msg.id if msg else '?'}, btn={button_text}")
            return msg
        except Exception as e:
            print(f"[{datetime.now()}] Send post error: {e}")
            try:
                msg = await self._call_with_retry(
                    self.client.send_message, CHANNEL_USERNAME, text,
                    parse_mode='html', link_preview=False
                )
                print(f"[{datetime.now()}] Fallback text-only post sent, msg_id={msg.id if msg else '?'}")
                return msg
            except Exception as e2:
                print(f"[{datetime.now()}] Fallback also failed: {e2}")
                return None

    async def _check_ping(self, server, port, timeout=5):
        import socket
        import time
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            start = time.time()
            result = sock.connect_ex((server, int(port)))
            ping = round((time.time() - start) * 1000)
            sock.close()
            if result == 0:
                return ping, "\u2705 \u0420\u0430\u0431\u043e\u0447\u0438\u0439"
            return None, "\u274c \u041d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d"
        except (socket.gaierror, socket.timeout, OSError):
            return None, "\u26a0\ufe0f \u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e"

    async def _guess_location(self, server):
        import socket
        try:
            ip = socket.gethostbyname(server)
            parts = ip.split('.')
            if parts[0] in ('149', '151', '158', '185', '188'):
                return "Europe"
            if parts[0] in ('5', '31', '37', '46', '51', '62', '78', '85', '91', '92', '93', '95'):
                return "Europe"
            if parts[0] in ('1', '14', '27', '36', '39', '42', '49', '58', '59', '60', '101', '103', '110', '111', '112', '113', '114', '115', '116', '117', '118', '119', '120', '121', '122', '123', '124', '125', '126', '175', '180', '182', '183', '202', '203', '210', '211', '218', '219', '220', '221', '222', '223'):
                return "Asia"
            if parts[0] in ('13', '23', '24', '32', '35', '40', '44', '45', '47', '50', '52', '54', '63', '64', '65', '66', '67', '68', '69', '70', '71', '72', '73', '74', '75', '76', '96', '97', '98', '99', '100', '104', '107', '108', '162', '165', '166', '167', '168', '170', '174', '184', '198', '199', '204', '205', '206', '207', '208', '209', '216'):
                return "Americas"
            return "Unknown"
        except Exception:
            return "Unknown"

    async def send_proxy_message(self, proxy):
        try:
            from urllib.parse import quote
            server = proxy['server']
            port = proxy['port']
            secret = proxy['secret']
            encoded_secret = quote(secret, safe='')
            web_link = f"https://t.me/proxy?server={server}&port={port}&secret={encoded_secret}"
            copy_link = f"https://t.me/share/url?url={quote(web_link, safe='')}&text={quote(secret, safe='')}"
            check_link = f"https://t.me/share/url?url={quote(web_link, safe='')}&text={quote(f'\u0421\u0442\u0430\u0442\u0443\u0441: \u043f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435: {server}:{port}', safe='')}"

            ping, status = await self._check_ping(server, port)
            location = await self._guess_location(server)

            ping_str = f"{ping} \u043c\u0441" if ping else "N/A"
            info_text = (
                f"\u26a1\ufe0f <b>MTProto \u041f\u0440\u043e\u043a\u0441\u0438 \u2014 \u041e\u0431\u0445\u043e\u0434 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043e\u043a</b>\n\n"
                f"\ud83d\udda5 <b>\u0421\u0435\u0440\u0432\u0435\u0440:</b> <code>{server}</code>\n"
                f"\ud83d\udd0c <b>\u041f\u043e\u0440\u0442:</b> <code>{port}</code>\n"
                f"\ud83d\udd10 <b>\u0421\u0435\u043a\u0440\u0435\u0442:</b> <code>{secret}</code>\n\n"
                f"\ud83d\udcca <b>\u0421\u0442\u0430\u0442\u0443\u0441:</b> {status}\n"
                f"\u26a1 <b>\u041f\u0438\u043d\u0433:</b> {ping_str}\n"
                f"\ud83c\udf0d <b>\u041b\u043e\u043a\u0430\u0446\u0438\u044f:</b> {location}\n\n"
                f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435:"
            )
            await self._send_post_with_button(
                info_text,
                "\ud83d\ude80 \u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
                web_link
            )
            print(f"[{datetime.now()}] Sent INFO+CONNECT post for {server}:{port}")

            copy_text = (
                f"\ud83d\udccb <b>\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0434\u043b\u044f \u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f:</b>\n\n"
                f"<code>server={server}\nport={port}\nsecret={secret}</code>\n\n"
                f"\ud83d\udca1 \u041d\u0430\u0436\u043c\u0438\u0442\u0435 <b>\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c</b> \u2014 \u0434\u0430\u043d\u043d\u044b\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u044f\u0442\u0441\u044f \u0432 \u0431\u0443\u0444\u0435\u0440 \u043e\u0431\u043c\u0435\u043d\u0430."
            )
            await self._send_post_with_button(
                copy_text,
                "\ud83d\udccb \u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
                copy_link
            )
            print(f"[{datetime.now()}] Sent COPY post for {server}:{port}")

            check_text = (
                f"\ud83d\udd0d <b>\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u043f\u0440\u043e\u043a\u0441\u0438:</b>\n\n"
                f"\ud83d\udda5 <b>\u0421\u0435\u0440\u0432\u0435\u0440:</b> <code>{server}</code>\n"
                f"\ud83d\udd0c <b>\u041f\u043e\u0440\u0442:</b> <code>{port}</code>\n"
                f"\ud83d\udcca <b>\u0421\u0442\u0430\u0442\u0443\u0441:</b> {status}\n"
                f"\u26a1 <b>\u041f\u0438\u043d\u0433:</b> {ping_str}\n\n"
                f"\ud83d\udc49 \u041d\u0430\u0436\u043c\u0438\u0442\u0435 <b>\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c</b> \u2014 \u043e\u0442\u043a\u0440\u043e\u0435\u0442\u0441\u044f \u0441\u0441\u044b\u043b\u043a\u0430 \u0434\u043b\u044f \u0442\u0435\u0441\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f."
            )
            await self._send_post_with_button(
                check_text,
                "\ud83d\udd0d \u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c",
                check_link
            )
            print(f"[{datetime.now()}] Published all 3 posts for proxy: {server}:{port}")
        except Exception as e:
            print(f"[{datetime.now()}] Send error: {e}")

    async def publish_proxies(self):
        print(f"[{datetime.now()}] Publishing {len(self.proxies[:10])} proxies...")
        for i, proxy in enumerate(self.proxies[:10], 1):
            print(f"[{datetime.now()}] Publishing proxy {i}/{min(10, len(self.proxies))}: {proxy['server']}:{proxy['port']}")
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
