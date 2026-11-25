"""Приёмка обновления оболочки: баннер «доступно обновление» + reload по кнопке.

Сценарий как на живом телефоне: страница уже открыта на версии N, на сервере
появилась версия N+1. Без баннера человек с открытой вкладкой останется на
старом интерфейсе до полного перезапуска браузера.

Проверяем ровно три вещи:
  1. после появления нового service worker'а виден баннер «доступно обновление»;
  2. по кнопке страница перезагружается и попадает на новый кэш;
  3. баннер после перезагрузки больше не висит.

Версия на диске на время проверки подменяется и всегда возвращается обратно
(try/finally), даже если прогон упал — иначе в репозитории остался бы подменённый
sw.js и разошёлся бы с токеном в index.html.

        python3 probe_sw_update.py URL
"""

import asyncio
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SW_PATH = ROOT / "static" / "sw.js"
CHROME = (os.environ.get("PROBE_CHROME")
          or shutil.which("google-chrome") or shutil.which("chromium")
          or os.path.expanduser("~/.hermes/tools/chromium-1208/chrome-linux64/chrome"))
TEST_SUFFIX = "-updtest"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def run(url: str):
    import websockets

    original = SW_PATH.read_text(encoding="utf-8")
    match = re.search(r"const VERSION = '([^']+)';", original)
    if not match:
        raise SystemExit("в sw.js не найден VERSION")
    version = match.group(1)
    bumped = version + TEST_SUFFIX
    SW_PATH.write_text(original.replace(version, bumped, 1), encoding="utf-8")

    port = free_port()
    profile = os.path.join(tempfile.mkdtemp(prefix="probe-update-"), "profile")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                page = next(t for t in targets if t["type"] == "page")
                ws_url = page["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.3)
        if not ws_url:
            raise SystemExit("CDP не поднялся")

        async with websockets.connect(ws_url, max_size=64 << 20) as ws:
            counter = 0

            async def call(method, **params):
                nonlocal counter
                counter += 1
                await ws.send(json.dumps({"id": counter, "method": method, "params": params}))
                while True:
                    data = json.loads(await ws.recv())
                    if data.get("id") == counter:
                        if "error" in data:
                            raise RuntimeError(f"{method}: {data['error']}")
                        return data.get("result", {})

            async def ev(expression):
                result = await call("Runtime.evaluate", expression=expression,
                                    returnByValue=True, awaitPromise=True, timeout=20000)
                return result.get("result", {}).get("value")

            async def wait_load():
                while True:
                    data = json.loads(await ws.recv())
                    if data.get("method") == "Page.loadEventFired":
                        return

            await call("Page.enable")
            await call("Runtime.enable")
            await call("Page.navigate", url=url)
            await wait_load()
            await asyncio.sleep(6)

            # Возвращаем на диск «старую» версию, чтобы воркер на странице был N,
            # а на сервере уже лежала N+1.
            SW_PATH.write_text(original, encoding="utf-8")

            control_before = await ev(
                "navigator.serviceWorker.ready.then(() => navigator.serviceWorker.controller?.scriptURL || '')"
            )
            await ev("navigator.serviceWorker.getRegistration().then(r => r.update())")
            # Установка новой оболочки: скачивание модулей + precache.
            await asyncio.sleep(12)

            banner = await ev(
                """(() => {
                  const b = document.getElementById('swUpdateBanner');
                  return b ? {hidden: b.hidden, text: b.innerText.replace(/\\s+/g, ' ').trim()} : null;
                })()"""
            )
            waiting = await ev(
                "navigator.serviceWorker.getRegistration().then(r => !!(r && r.waiting))"
            )

            # Кнопка «Обновить»: skipWaiting → controllerchange → reload.
            await ev("document.querySelector('[data-sw-reload]')?.click()")
            await asyncio.sleep(6)
            await wait_load()
            await asyncio.sleep(4)

            after = await ev(
                """(async () => {
                  const b = document.getElementById('swUpdateBanner');
                  return {
                    caches: await caches.keys(),
                    bannerHidden: b ? b.hidden : true,
                    bodyText: document.body.innerText.replace(/\\s+/g, ' ').trim().slice(0, 120),
                  };
                })()"""
            )
            print(json.dumps({
                "disk_version_before": version,
                "bumped_version": bumped,
                "controller": control_before,
                "waiting_worker": waiting,
                "banner": banner,
                "after_reload": after,
            }, ensure_ascii=False, indent=2))
    finally:
        proc.terminate()
        SW_PATH.write_text(original, encoding="utf-8")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    main()
