"""Report whether cards fit their columns at a given viewport.

A grid item's automatic minimum is min-content, so one long unbreakable token in a
card title (a path like `request_dump_*.json`) can push the card wider than its
column and make it overlap the neighbour. This measures that directly instead of
eyeballing a screenshot.
"""

import asyncio
import json
import subprocess
import sys
import time
import urllib.request

CHROME = "/home/hermes/.hermes/tools/chromium-1208/chrome-linux64/chrome"

PROBE = """
(() => {
  const cols = [...document.querySelectorAll('.board-column')].map(c => {
    const r = c.getBoundingClientRect();
    return { status: c.dataset.status, left: Math.round(r.left), width: Math.round(r.width) };
  });
  const cards = [...document.querySelectorAll('.task-card')].map(c => {
    const r = c.getBoundingClientRect();
    const col = c.closest('.board-column');
    const cr = col.getBoundingClientRect();
    return {
      id: c.dataset.taskId,
      width: Math.round(r.width),
      column: col.dataset.status,
      columnWidth: Math.round(cr.width),
      overflowsBy: Math.round(r.width - cr.width + 24), // 12px padding each side
    };
  });
  const board = document.querySelector('.board');
  return JSON.stringify({
    pageOverflow: document.documentElement.scrollWidth - innerWidth,
    boardOverflow: board ? board.scrollWidth - board.clientWidth : null,
    columns: cols,
    worstCards: cards.sort((a, b) => b.overflowsBy - a.overflowsBy).slice(0, 5),
  });
})()
"""


async def probe(url: str, width: int, height: int) -> None:
    import websockets

    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         "--remote-debugging-port=9334", "--user-data-dir=/tmp/cdp-probe", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=2))
                ws_url = next(t for t in targets if t["type"] == "page")["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.3)
        async with websockets.connect(ws_url, max_size=32 << 20) as ws:
            seq = 0

            async def call(method, **params):
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
            res = await call("Runtime.evaluate", expression=PROBE, returnByValue=True)
            data = json.loads(res["result"]["value"])
            print(f"--- {width}x{height} ---")
            print(f"переполнение страницы: {data['pageOverflow']}px, доски: {data['boardOverflow']}px")
            print("колонки:", [(c["status"], c["width"]) for c in data["columns"]])
            print("худшие карточки:")
            for c in data["worstCards"]:
                print(f"   {c['id']} {c['column']}: карточка {c['width']} при колонке {c['columnWidth']} "
                      f"-> вылезает на {c['overflowsBy']}px")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    url = sys.argv[1]
    for w in (int(a) for a in sys.argv[2:]) if len(sys.argv) > 2 else (1280, 1440, 1600):
        asyncio.run(probe(url, w, 900))
