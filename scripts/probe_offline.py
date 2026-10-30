"""Приёмка офлайн-оболочки: загрузка → сеть выключена → перезагрузка.

Живьём проверяет то, ради чего писался service worker:

* после обрыва сети перезагрузка всё равно рисует оболочку (её отдаёт кэш);
* фоновые запросы к /api получают 503 {"offline": true};
* блоки данных показывают «нет сети · Повторить», а не пустоту и не
  «не удалось загрузить».

Важная деталь: `Network.emulateNetworkConditions` действует на тот target, на
котором включён. Запросы страницы идут через service worker — это отдельный
target, и если не выключить сеть и там, воркер спокойно сходит на сервер, а
проверка покажет живой ответ вместо офлайна. Поэтому цепляемся к service worker
через Target.setAutoAttach(flatten) и глушим сеть в обеих сессиях.

        python3 probe_offline.py URL [WIDTH HEIGHT]

Токен доступа берётся из KANBAN_TOKEN (или из /home/hermes/.hermes/kanban-webui.env),
без него доска показывает форму входа вместо данных.
"""

import asyncio
import base64
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME = os.environ.get(
    "PROBE_CHROME", "/home/hermes/.hermes/tools/chromium-1208/chrome-linux64/chrome"
)
SETTLE_SECONDS = float(os.environ.get("PROBE_SETTLE", "6"))
ENV_FILE = "/home/hermes/.hermes/kanban-webui.env"


def token_from_env() -> str:
    """Токен берём из окружения или из env-файла сервиса — не хардкодим."""
    token = os.environ.get("KANBAN_TOKEN")
    if token:
        return token.strip()
    try:
        with open(ENV_FILE, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("HERMES_KANBAN_WEBUI_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Session:
    def __init__(self, ws):
        self.ws = ws
        self.next_id = 0
        self.attached: list[dict] = []

    async def _read(self) -> dict:
        data = json.loads(await self.ws.recv())
        method = data.get("method")
        if method == "Target.attachedToTarget":
            self.attached.append(data["params"])
        return data

    async def call(self, method: str, session_id: str | None = None, **params):
        self.next_id += 1
        message_id = self.next_id
        payload = {"id": message_id, "method": method, "params": params}
        if session_id:
            payload["sessionId"] = session_id
        await self.ws.send(json.dumps(payload))
        while True:
            data = await self._read()
            if data.get("id") == message_id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})

    async def wait_event(self, name: str, timeout: float = 60.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.2, deadline - time.time())
            try:
                data = await asyncio.wait_for(self._read(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if data.get("method") == name:
                return data
        raise SystemExit(f"не дождались события {name}")

    async def ev(self, expression: str):
        result = await self.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
            timeout=20000,
        )
        if result.get("exceptionDetails"):
            return {"error": result["exceptionDetails"].get("text", "exception")}
        return result.get("result", {}).get("value")

    def sw_sessions(self) -> list[str]:
        return [
            item["sessionId"]
            for item in self.attached
            if item["targetInfo"]["type"] == "service_worker"
        ]


async def set_offline(s: Session, offline: bool, with_sw: bool = True) -> list[str]:
    """Глушим (или возвращаем) сеть на странице и на всех service worker'ах."""
    await s.call(
        "Network.emulateNetworkConditions",
        offline=offline, latency=0, downloadThroughput=0 if offline else -1,
        uploadThroughput=0 if offline else -1,
    )
    touched = []
    if not with_sw:
        return touched
    for session_id in s.sw_sessions():
        try:
            await s.call("Network.enable", session_id=session_id)
            await s.call(
                "Network.emulateNetworkConditions", session_id=session_id,
                offline=offline, latency=0,
                downloadThroughput=0 if offline else -1,
                uploadThroughput=0 if offline else -1,
            )
            touched.append(session_id)
        except RuntimeError as err:  # воркер мог умереть между вызовами
            print(f"[probe] service worker {session_id}: {err}", file=sys.stderr)
    return touched


async def probe(url: str, width: int, height: int, token: str):
    import websockets

    port = free_port()
    profile = os.path.join(tempfile.mkdtemp(prefix="probe-offline-"), "profile")
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
            s = Session(ws)
            for domain in ("Page", "Runtime", "Network"):
                await s.call(f"{domain}.enable")
            # Без flatten к service worker'у не подключиться из сессии страницы.
            await s.call("Target.setAutoAttach", autoAttach=True,
                         waitForDebuggerOnStart=False, flatten=True)
            await s.call(
                "Emulation.setDeviceMetricsOverride",
                width=width, height=height, deviceScaleFactor=2, mobile=True,
            )

            await s.call("Page.navigate", url=url)
            await s.wait_event("Page.loadEventFired")
            await asyncio.sleep(2)

            # Токен кладём в localStorage и перезагружаемся: api.js читает его оттуда.
            if token:
                await s.ev(
                    "localStorage.setItem('kanbanToken', %s)" % json.dumps(token)
                )
                await s.call("Page.reload", ignoreCache=False)
                await s.wait_event("Page.loadEventFired")

            # Первая (сетевая) загрузка: воркер встаёт и кэширует оболочку.
            ready = await s.ev(
                "navigator.serviceWorker.ready.then(() => "
                "(async () => ({controller: !!navigator.serviceWorker.controller,"
                " caches: await caches.keys()}))())"
            )
            await asyncio.sleep(SETTLE_SECONDS)
            warm = await s.ev(
                """({cards: document.querySelectorAll('.card, .task-card').length,
                     tokens: document.body.innerText.length,
                     overflow: document.documentElement.scrollWidth - window.innerWidth,
                     hasNetError: /нет сети|no network/.test(document.body.innerText)})"""
            )

            # Обрыв: сеть глушится и у страницы, и у service worker'а.
            sw_off = await set_offline(s, True)
            await s.call("Page.reload", ignoreCache=False)
            await s.wait_event("Page.loadEventFired")
            await asyncio.sleep(SETTLE_SECONDS)

            state = await s.ev(
                """(async () => {
                  const shell = !!document.querySelector('.tabs, #board, .view');
                  const api = await fetch('/api/board', {headers: {'accept': 'application/json'}})
                    .then(async r => ({status: r.status, body: (await r.text()).slice(0, 120)}))
                    .catch(e => ({status: 'fetch-failed', body: String(e)}));
                  const errors = [...document.querySelectorAll('[role="alert"]')]
                    .map(n => n.innerText.replace(/\\s+/g, ' ').trim()).slice(0, 6);
                  return {
                    title: document.title,
                    shell,
                    tabs: document.querySelectorAll('.tabs').length,
                    errors,
                    bodyText: document.body.innerText.replace(/\\s+/g, ' ').trim().slice(0, 400),
                    api,
                    overflow: document.documentElement.scrollWidth - window.innerWidth,
                    hasNoNetwork: /нет сети|no network|네트워크 없음/.test(document.body.innerText),
                    hasRetry: /Повторить|Retry|다시 시도/.test(document.body.innerText),
                  };
                })()"""
            )
            # Второй путь офлайна: блок, чьих данных в кэше нет (у «Ленты» другой
            # URL с курсором), должен показать «нет сети · Повторить», а не
            # пустой список.
            await s.ev("document.querySelector('[data-tab=\"feed\"]')?.click()")
            await asyncio.sleep(SETTLE_SECONDS)
            feed = await s.ev(
                """({errors: [...document.querySelectorAll('[role="alert"]')]
                      .map(n => n.innerText.replace(/\\s+/g, ' ').trim()).slice(0, 4),
                    text: document.body.innerText.replace(/\\s+/g, ' ').trim().slice(0, 200)})"""
            )
            shot = os.environ.get("PROBE_SHOT")
            if shot:
                # Скриншот офлайна: оболочка + полоса «нет сети» — доказательство
                # для человека, что экран не пустой и не врёт про данные.
                await s.ev("document.querySelector('[data-tab=\"now\"]')?.click()")
                await asyncio.sleep(2)
                image = await s.call("Page.captureScreenshot", format="png")
                pathlib.Path(shot).write_bytes(base64.b64decode(image["data"]))
                print(f"[probe] скриншот: {shot}", file=sys.stderr)

            # Третий путь: холодный старт без кэша ответов. Вычищаем /api/* из
            # кэша и перезагружаемся — доска обязана показать «нет сети ·
            # Повторить» на месте колонок, а не пустоту («задач нет» — ложь).
            purged = await s.ev(
                """(async () => {
                  let removed = 0;
                  for (const name of await caches.keys()) {
                    const cache = await caches.open(name);
                    for (const req of await cache.keys()) {
                      if (new URL(req.url).pathname.startsWith('/api/')) {
                        await cache.delete(req);
                        removed += 1;
                      }
                    }
                  }
                  return removed;
                })()"""
            )
            await s.call("Page.reload", ignoreCache=False)
            await s.wait_event("Page.loadEventFired")
            await asyncio.sleep(SETTLE_SECONDS)
            cold = await s.ev(
                """(async () => {
                  document.querySelector('[data-tab="board"]')?.click();
                  await new Promise(r => setTimeout(r, 1500));
                  const block = document.querySelector('#board .board-error');
                  return {
                    purged: %d,
                    hasBlock: !!block,
                    blockText: block ? block.innerText.replace(/\\s+/g, ' ').trim() : '',
                    cards: document.querySelectorAll('#board .card, #board .task-card').length,
                    overflow: document.documentElement.scrollWidth - window.innerWidth,
                  };
                })()""" % purged
            )
            if shot:
                board_shot = str(pathlib.Path(shot).with_name("pwa_offline_board_390.png"))
                image = await s.call("Page.captureScreenshot", format="png")
                pathlib.Path(board_shot).write_bytes(base64.b64decode(image["data"]))
                print(f"[probe] скриншот: {board_shot}", file=sys.stderr)
            print(json.dumps(
                {"sw": ready, "network_load": warm, "sw_offline_sessions": sw_off,
                 "offline": state, "offline_feed": feed, "offline_cold_board": cold},
                ensure_ascii=False, indent=2,
            ))
    finally:
        proc.terminate()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    url = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 390
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 844
    asyncio.run(probe(url, width, height, token_from_env()))


if __name__ == "__main__":
    main()
