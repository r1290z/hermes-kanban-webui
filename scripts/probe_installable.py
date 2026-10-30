"""Проверка установимости PWA глазами браузера: манифест + критерии installability.

Ручная установка на Android проверяется руками, но все причины отказа Chrome
умеет называть сам: `Page.getInstallabilityErrors` перечисляет их списком
(нет иконки 192/512, нет service worker'а с fetch, манифест не JSON и т.п.).
Пустой список — установка доступна.

        python3 probe_installable.py URL
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME = os.environ.get(
    "PROBE_CHROME", "/home/hermes/.hermes/tools/chromium-1208/chrome-linux64/chrome"
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def run(url: str):
    import websockets

    port = free_port()
    profile = os.path.join(tempfile.mkdtemp(prefix="probe-install-"), "profile")
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

            await call("Page.enable")
            await call("Page.navigate", url=url)
            while True:
                data = json.loads(await ws.recv())
                if data.get("method") == "Page.loadEventFired":
                    break
            # Манифест подтягивается после load; воркер должен успеть встать.
            await asyncio.sleep(7)

            manifest = await call("Page.getAppManifest")
            errors = await call("Page.getInstallabilityErrors")
            print(json.dumps({
                "manifest_url": manifest.get("url"),
                "manifest_errors": manifest.get("errors", []),
                "parsed": bool(manifest.get("parsed")),
                "installability_errors": errors.get("installabilityErrors", []),
            }, ensure_ascii=False, indent=2))
    finally:
        proc.terminate()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    main()
