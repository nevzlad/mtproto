import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import os
import socket
import sqlite3
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, quote
from telethon import TelegramClient, errors
from telethon.tl.custom import Button
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL_USERNAME = os.environ['CHANNEL_USERNAME']

# Источники парсинга
MTPROTO_URL = "https://mtproto.cloud/"
FEED_URL = "https://mtproto.cloud/api/feed"
MTPRO_XYZ_URL = "https://mtpro.xyz/"
MTPRO_XYZ_API = "https://mtpro.xyz/api/proxies"

# Telegram-каналы для парсинга
TELEGRAM_CHANNELS = [
    "ProxyFree_Ru"
]

DB_FILE = "published_proxies.db"


class MTProtoProxyBot:
    def __init__(self):
        self.client = None
        self.proxies = []
        self.relay_proxies = []
        self.db = self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_FILE)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS published_proxies (
                server TEXT,
                port INTEGER,
                secret TEXT,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (server, port, secret)
            )
        ''')
        conn.commit()
        return conn

    def _is_already_published(self, server, port, secret):
        cursor = self.db.execute(
            'SELECT 1 FROM published_proxies WHERE server=? AND port=? AND secret=?',
            (server, port, secret)
        )
        return cursor.fetchone() is not None

    def _mark_as_published(self, server, port, secret):
        try:
            self.db.execute(
                'INSERT OR REPLACE INTO published_proxies (server, port, secret, published_at) VALUES (?, ?, ?, ?)',
                (server, port, secret, datetime.now())
            )
            self.db.commit()
        except Exception as e:
            print(f"[{datetime.now()}] DB error: {e}")

    def _cleanup_old_records(self, days=7):
        try:
            cutoff = datetime.now() - timedelta(days=days)
            self.db.execute(
                'DELETE FROM published_proxies WHERE published_at < ?',
                (cutoff,)
            )
            self.db.commit()
        except Exception as e:
            print(f"[{datetime.now()}] Cleanup error: {e}")

    async def _is_proxy_working(self, server, port, timeout=5):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((server, int(port)))
            sock.close()
            return result == 0
        except (socket.gaierror, socket.timeout, OSError):
            return False

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
        print(f"[{datetime.now()}] PARSER: Starting mtproto.cloud parsing...")
        seen_set = set()
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(MTPROTO_URL, timeout=30) as response:
                    html = await response.text()
                print(f"[{datetime.now()}] PARSER: HTML loaded, {len(html)} bytes")
                for m in re.finditer(r'https://mtproto\.cloud/connect\?[^"\'<>]+', html):
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
                    self.proxies.append({'server': server, 'port': port, 'secret': secret})
                    print(f"[{datetime.now()}] PARSER: HTML proxy: {server}:{port}")
            except Exception as e:
                print(f"[{datetime.now()}] PARSER: HTML error (fallback to API): {e}")
                try:
                    async with session.get(FEED_URL, timeout=30) as response:
                        data = await response.json(content_type=None)
                    items = data.get('items', []) if isinstance(data, dict) else []
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
                        self.proxies.append({'server': server, 'port': int(port), 'secret': secret})
                except Exception as e2:
                    print(f"[{datetime.now()}] PARSER: API fallback failed: {e2}")
        print(f"[{datetime.now()}] PARSER: mtproto.cloud - Total: {len(self.proxies)}")

    async def parse_mtpro_xyz(self):
        print(f"[{datetime.now()}] PARSER: Starting mtpro.xyz parsing...")
        initial_count = len(self.proxies)
        seen_set = set()
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(MTPRO_XYZ_API, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        items = data if isinstance(data, list) else data.get('proxies', data.get('items', []))
                        for item in items:
                            server = (item.get('server') or item.get('host') or '').strip()
                            port = item.get('port')
                            secret = (item.get('secret') or item.get('password') or '').strip()
                            if not server or port is None or not secret:
                                continue
                            try:
                                port = int(port)
                            except (TypeError, ValueError):
                                continue
                            key = (server, port, secret)
                            if key in seen_set:
                                continue
                            seen_set.add(key)
                            self.proxies.append({'server': server, 'port': port, 'secret': secret})
                            print(f"[{datetime.now()}] PARSER: mtpro.xyz API proxy: {server}:{port}")
            except Exception as e:
                print(f"[{datetime.now()}] PARSER: mtpro.xyz API error: {e}")
            try:
                async with session.get(MTPRO_XYZ_URL, timeout=30) as response:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    for link in soup.find_all('a', href=re.compile(r'tg://proxy')):
                        href = link['href']
                        qs = parse_qs(urlparse(href).query)
                        server = (qs.get('server') or [''])[0].strip()
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
                        self.proxies.append({'server': server, 'port': port, 'secret': secret})
            except Exception as e:
                print(f"[{datetime.now()}] PARSER: mtpro.xyz HTML error: {e}")
        print(f"[{datetime.now()}] PARSER: mtpro.xyz - New: {len(self.proxies) - initial_count}")

    async def parse_telegram_channels(self):
        """Парсинг Telegram-каналов через публичные веб-превью"""
        print(f"[{datetime.now()}] PARSER: Starting Telegram channels parsing...")
        initial_count = len(self.proxies)
        seen_set = set()
        
        async with aiohttp.ClientSession() as session:
            for channel in TELEGRAM_CHANNELS:
                try:
                    url = f"https://t.me/s/{channel}"
                    print(f"[{datetime.now()}] PARSER: Fetching @{channel}...")
                    
                    async with session.get(url, timeout=30) as response:
                        if response.status != 200:
                            print(f"[{datetime.now()}] PARSER: @{channel} returned {response.status}")
                            continue
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        messages = soup.find_all('div', class_='tgme_widget_message_text')
                        print(f"[{datetime.now()}] PARSER: @{channel} - Found {len(messages)} messages")
                        
                        for msg in messages:
                            text = msg.get_text()
                            
                            # Паттерн 1: tg://proxy?server=...&port=...&secret=...
                            for match in re.finditer(r'tg://proxy\?server=([^&]+)&port=(\d+)&secret=([^&\s]+)', text):
                                server = match.group(1).strip()
                                port_str = match.group(2)
                                secret = match.group(3).strip()
                                try:
                                    port = int(port_str)
                                except ValueError:
                                    continue
                                key = (server, port, secret)
                                if key in seen_set:
                                    continue
                                seen_set.add(key)
                                self.proxies.append({'server': server, 'port': port, 'secret': secret})
                                print(f"[{datetime.now()}] PARSER: @{channel} tg:// proxy: {server}:{port}")
                            
                            # Паттерн 2: https://t.me/proxy?server=...&port=...&secret=...
                            for match in re.finditer(r'https://t\.me/proxy\?server=([^&]+)&port=(\d+)&secret=([^&\s]+)', text):
                                server = match.group(1).strip()
                                port_str = match.group(2)
                                secret = match.group(3).strip()
                                try:
                                    port = int(port_str)
                                except ValueError:
                                    continue
                                key = (server, port, secret)
                                if key in seen_set:
                                    continue
                                seen_set.add(key)
                                self.proxies.append({'server': server, 'port': port, 'secret': secret})
                                print(f"[{datetime.now()}] PARSER: @{channel} https:// proxy: {server}:{port}")
                            
                            # Паттерн 3: IP:Port:Secret
                            for match in re.finditer(r'(\d+\.\d+\.\d+\.\d+):(\d+):([a-fA-F0-9]{32,})', text):
                                server = match.group(1)
                                port_str = match.group(2)
                                secret = match.group(3)
                                try:
                                    port = int(port_str)
                                except ValueError:
                                    continue
                                key = (server, port, secret)
                                if key in seen_set:
                                    continue
                                seen_set.add(key)
                                self.proxies.append({'server': server, 'port': port, 'secret': secret})
                                print(f"[{datetime.now()}] PARSER: @{channel} IP:Port:Secret proxy: {server}:{port}")
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    print(f"[{datetime.now()}] PARSER: @{channel} error: {e}")
        
        new_count = len(self.proxies) - initial_count
        print(f"[{datetime.now()}] PARSER: Telegram channels - New: {new_count}")

    async def validate_proxies(self):
        print(f"[{datetime.now()}] VALIDATOR: Starting validation...")
        working = []
        for proxy in self.proxies:
            server, port, secret = proxy['server'], proxy['port'], proxy['secret']
            if self._is_already_published(server, port, secret):
                print(f"[{datetime.now()}] VALIDATOR: Skip duplicate {server}:{port}")
                continue
            is_working = await self._is_proxy_working(server, port, timeout=5)
            if is_working:
                working.append(proxy)
                print(f"[{datetime.now()}] VALIDATOR: ✅ {server}:{port}")
            else:
                print(f"[{datetime.now()}] VALIDATOR: ❌ {server}:{port}")
            await asyncio.sleep(0.3)
        self.proxies = working
        print(f"[{datetime.now()}] VALIDATOR: Working: {len(working)}")

    async def _call_with_retry(self, fn, *args, max_retries=3, **kwargs):
        for attempt in range(max_retries):
            try:
                return await fn(*args, **kwargs)
            except errors.FloodWaitError as e:
                wait = e.seconds * (1 + attempt)
                print(f"[{datetime.now()}] Flood wait {e.seconds}s, sleeping {wait}s")
                await asyncio.sleep(wait)
        raise RuntimeError(f"Failed after {max_retries} retries")

    async def _check_ping(self, server, port, timeout=5):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            start = time.time()
            result = sock.connect_ex((server, int(port)))
            ping = round((time.time() - start) * 1000)
            sock.close()
            if result == 0:
                return ping, "✅ Рабочий"
            return None, "❌ Недоступен"
        except (socket.gaierror, socket.timeout, OSError):
            return None, "⚠️ Неизвестно"

    async def _guess_location(self, server):
        try:
            ip = socket.gethostbyname(server)
            parts = ip.split('.')
            if parts[0] in ('149', '151', '158', '185', '188', '5', '31', '37', '46', '51', '62', '78', '85', '91', '92', '93', '95'):
                return "Europe"
            if parts[0] in ('13', '23', '24', '32', '35', '40', '44', '45', '47', '50', '52', '54', '63', '64', '65', '66', '67', '68', '69', '70', '71', '72', '73', '74', '75', '76', '96', '97', '98', '99', '100', '104', '107', '108', '162', '165', '166', '167', '168', '170', '174', '184', '198', '199', '204', '205', '206', '207', '208', '209', '216'):
                return "Americas"
            return "Asia"
        except Exception:
            return "Unknown"

    async def send_proxy_message(self, proxy):
        try:
            server = proxy['server']
            port = proxy['port']
            secret = proxy['secret']
            encoded_secret = quote(secret, safe='')
            web_link = f"https://t.me/proxy?server={server}&port={port}&secret={encoded_secret}"
            copy_link = f"https://t.me/share/url?url={quote(web_link, safe='')}&text={quote(secret, safe='')}"
            check_msg = f"Статус: проверьте подключение: {server}:{port}"
            check_link = f"https://t.me/share/url?url={quote(web_link, safe='')}&text={quote(check_msg, safe='')}"

            ping, status = await self._check_ping(server, port)
            location = await self._guess_location(server)
            ping_str = f"{ping} мс" if ping else "N/A"

            info_text = (
                f"⚡️ <b>MTProto Прокси — Обход блокировок</b>\n\n"
                f"🖥 <b>Сервер:</b> <code>{server}</code>\n"
                f"🔌 <b>Порт:</b> <code>{port}</code>\n"
                f"🔐 <b>Секрет:</b> <code>{secret}</code>\n\n"
                f"📊 <b>Статус:</b> {status}\n"
                f"⚡ <b>Пинг:</b> {ping_str}\n"
                f"🌍 <b>Локация:</b> {location}\n\n"
                f"<b>Выберите действие:</b>"
            )

            buttons = [
                [Button.url("🚀 Подключить", web_link)],
                [Button.url("📋 Копировать", copy_link)],
                [Button.url("🔍 Проверить", check_link)]
            ]

            msg = await self._call_with_retry(
                self.client.send_message, CHANNEL_USERNAME, info_text,
                buttons=buttons, parse_mode='html', link_preview=False
            )
            self._mark_as_published(server, port, secret)
            print(f"[{datetime.now()}] Sent post for {server}:{port}, msg_id={msg.id if msg else '?'}")
        except Exception as e:
            print(f"[{datetime.now()}] Send error: {e}")

    async def publish_proxies(self):
        print(f"[{datetime.now()}] Publishing {len(self.proxies[:10])} proxies...")
        for i, proxy in enumerate(self.proxies[:10], 1):
            print(f"[{datetime.now()}] Publishing {i}/{min(10, len(self.proxies))}: {proxy['server']}:{proxy['port']}")
            await self.send_proxy_message(proxy)
            await asyncio.sleep(2)

    async def run(self):
        await self.start()
        
        # Парсинг со всех источников
        await self.parse_mtproto_cloud()
        await self.parse_mtpro_xyz()
        await self.parse_telegram_channels()
        
        print(f"[{datetime.now()}] Total before validation: {len(self.proxies)}")
        await self.validate_proxies()
        print(f"[{datetime.now()}] Working proxies: {len(self.proxies)}")
        
        if self.proxies:
            await self.publish_proxies()
        else:
            print(f"[{datetime.now()}] No working proxies found")
        
        self._cleanup_old_records(days=7)
        await self.client.disconnect()


async def main():
    bot = MTProtoProxyBot()
    await bot.run()


if __name__ == '__main__':
    asyncio.run(main())