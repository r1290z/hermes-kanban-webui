"""Поведенческая проба десктопной доски: внутренний скролл колонки, ошибки в консоли,
рисование линий связей и открытие карточки. Печатает JSON с результатом.

    python3 probe_desktop_behavior.py URL [width] [height]
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

CHROME = (os.environ.get("PROBE_CHROME")
          or shutil.which("google-chrome") or shutil.which("chromium")
          or os.path.expanduser("~/.hermes/tools/chromium-1208/chrome-linux64/chrome"))


async def main(url: str, width: int, height: int) -> None:
    import websockets

    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         "--remote-debugging-port=9335", "--user-data-dir=/tmp/cdp-profile-behavior",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    errors = []
    try:
        ws_url = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen("http://127.0.0.1:9335/json", timeout=2))
                page = next(t for t in targets if t["type"] == "page")
                ws_url = page["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.3)
        if not ws_url:
            raise SystemExit("CDP не поднялся")

        async with websockets.connect(ws_url, max_size=64 << 20) as ws:
            seq = 0

            async def call(method: str, **params):
                nonlocal seq
                seq += 1
                await ws.send(json.dumps({"id": seq, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("method") in ("Runtime.exceptionThrown",):
                        errors.append(msg["params"]["exceptionDetails"].get("text", "exception"))
                    if msg.get("method") == "Runtime.consoleAPICalled" and msg["params"]["type"] == "error":
                        errors.append(" ".join(str(a.get("value", a.get("description", "")))
                                               for a in msg["params"]["args"]))
                    if msg.get("id") == seq:
                        if "error" in msg:
                            raise SystemExit(f"{method}: {msg['error']}")
                        return msg.get("result", {})

            async def evaluate(expr: str):
                r = await call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
                return r["result"].get("value")

            await call("Runtime.enable")
            await call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                       deviceScaleFactor=1, mobile=False)
            await call("Page.enable")
            await call("Page.navigate", url=url)
            await asyncio.sleep(6)

            report = {}
            report["board_height"] = await evaluate(
                "document.querySelector('.board').getBoundingClientRect().height")
            report["doc_height"] = await evaluate("document.documentElement.scrollHeight")
            report["col_scrollable"] = await evaluate("""(() => {
              const col = [...document.querySelectorAll('.board-column')]
                .find(c => !c.classList.contains('is-empty'));
              const cards = col.querySelector('.cards');
              return { scrollH: cards.scrollHeight, clientH: cards.clientHeight };
            })()""")
            report["scroll_moves"] = await evaluate("""(async () => {
              const col = [...document.querySelectorAll('.board-column')]
                .find(c => !c.classList.contains('is-empty'));
              const cards = col.querySelector('.cards');
              cards.scrollTop = 400;
              await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
              const after = cards.scrollTop;
              const overlay = document.querySelector('.dependency-overlay');
              const box = overlay ? overlay.getBoundingClientRect() : null;
              return { scrolledTo: after, overlayBox: box && { w: Math.round(box.width), h: Math.round(box.height) } };
            })()""")
            report["card_still_above_fold"] = await evaluate("""(() => {
              const board = document.querySelector('.board').getBoundingClientRect();
              const card = document.querySelector('.board-column .cards .task-card');
              const r = card.getBoundingClientRect();
              return { cardTop: Math.round(r.top), boardTop: Math.round(board.top) };
            })()""")
            report["open_drawer"] = await evaluate("""(async () => {
              document.querySelector('.board-column .cards .task-card').click();
              await new Promise(r => setTimeout(r, 900));
              const d = document.querySelector('.drawer');
              return d ? { open: d.classList.contains('open'), w: Math.round(d.getBoundingClientRect().width),
                            title: (d.querySelector('h2,h3') || {}).textContent?.slice(0, 40) || null } : null;
            })()""")
            report["errors"] = errors
            print(json.dumps(report, ensure_ascii=False))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    url = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 1440
    h = int(sys.argv[3]) if len(sys.argv) > 3 else 900
    asyncio.run(main(url, w, h))