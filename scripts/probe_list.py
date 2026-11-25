"""Замер таблицы списка на десктопе: высота строки, ширины колонок, обрезка
заголовков, формат даты. Печатает JSON.

    python3 probe_list.py URL [width] [height]
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

METRICS = r"""(() => {
  const rows = [...document.querySelectorAll('#viewList tbody tr')];
  const table = document.querySelector('#viewList table');
  const ths = [...document.querySelectorAll('#viewList thead th')];
  const first = rows[0];
  return {
    rows: rows.length,
    rowH: first ? Math.round(first.getBoundingClientRect().height) : 0,
    rowHmin: rows.length ? Math.round(Math.min(...rows.map(r => r.getBoundingClientRect().height))) : 0,
    rowHmax: rows.length ? Math.round(Math.max(...rows.map(r => r.getBoundingClientRect().height))) : 0,
    tableW: table ? Math.round(table.getBoundingClientRect().width) : 0,
    th: ths.map(x => Math.round(x.getBoundingClientRect().width)),
    thClipped: ths.filter(x => x.scrollWidth > x.clientWidth + 1).map(x => x.textContent.trim()),
    titleW: first ? Math.round(first.children[3].getBoundingClientRect().width) : 0,
    titleClipped: first ? first.children[3].scrollWidth > first.children[3].clientWidth + 1 : null,
    dateCell: first ? first.children[5].textContent.trim() : null,
    docH: document.documentElement.scrollHeight,
    hOverflow: document.documentElement.scrollWidth - innerWidth,
  };
})()"""


async def main(url: str, width: int, height: int) -> None:
    import websockets

    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         "--remote-debugging-port=9337", "--user-data-dir=/tmp/cdp-profile-list",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen("http://127.0.0.1:9337/json", timeout=2))
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
                    if msg.get("id") == seq:
                        if "error" in msg:
                            raise SystemExit(f"{method}: {msg['error']}")
                        return msg.get("result", {})

            await call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                       deviceScaleFactor=1, mobile=False)
            await call("Page.enable")
            await call("Page.navigate", url=url)
            await asyncio.sleep(6)
            res = await call("Runtime.evaluate", expression=METRICS, returnByValue=True)
            print(json.dumps(res["result"]["value"], ensure_ascii=False))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    url = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 1440
    h = int(sys.argv[3]) if len(sys.argv) > 3 else 900
    asyncio.run(main(url, w, h))