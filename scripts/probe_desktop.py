"""Замер десктопной раскладки KanbanWebUI (mobile=False) — числами, не впечатлениями.

shot.py жёстко ставит mobile=True, и на 1440px это отдаёт телефонную раскладку.
Здесь Emulation.setDeviceMetricsOverride(mobile=False), поэтому CSS видит настоящий
десктопный вьюпорт. Кроме скриншота печатает метрики раскладки одним Runtime.evaluate.

    python3 probe_desktop.py URL OUT.png [width] [height]
"""

import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request

CHROME = "/home/hermes/.hermes/tools/chromium-1208/chrome-linux64/chrome"

METRICS = r"""
(() => {
  const q = s => document.querySelector(s);
  const board = q('.board');
  const cols = [...document.querySelectorAll('.board-column')].map(c => ({
    st: c.dataset.status,
    w: Math.round(c.getBoundingClientRect().width),
    empty: c.classList.contains('is-empty'),
    cards: c.querySelectorAll('.task-card').length,
    h: Math.round(c.getBoundingClientRect().height),
  }));
  const cards = [...document.querySelectorAll('.task-card')];
  const vis = cards.filter(x => { const r = x.getBoundingClientRect();
    return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; });
  const nav = q('.tabs-bottom') || q('.topbar') || q('header');
  return {
    vw: innerWidth, vh: innerHeight,
    hOverflow: document.documentElement.scrollWidth - innerWidth,
    docH: document.documentElement.scrollHeight,
    tabsBottom: !!q('.tabs.tabs-bottom'),
    activeTab: q('[role=tab][aria-selected=true]')?.dataset.tab || null,
    railVisible: (() => { const r = q('.board-rail'); if (!r) return null;
      return getComputedStyle(r).display !== 'none' && r.getBoundingClientRect().height > 0; })(),
    headerH: nav ? Math.round(nav.getBoundingClientRect().height) : null,
    mainTop: Math.round((q('main') || document.body).getBoundingClientRect().top),
    boardClient: board ? board.clientWidth : null,
    boardScroll: board ? board.scrollWidth : null,
    boardH: board ? Math.round(board.getBoundingClientRect().height) : null,
    cols, colCount: cols.length, emptyCols: cols.filter(c => c.empty).length,
    colsWidthSum: cols.reduce((a, c) => a + c.w, 0),
    usedPct: board ? Math.round(cols.reduce((a, c) => a + c.w, 0) * 100 / innerWidth) : null,
    cardTotal: cards.length,
    cardsVisible: vis.length,
    cardH: cards.length ? Math.round(cards[0].getBoundingClientRect().height) : 0,
    cardHmin: cards.length ? Math.round(Math.min(...cards.map(c => c.getBoundingClientRect().height))) : 0,
    cardHmax: cards.length ? Math.round(Math.max(...cards.map(c => c.getBoundingClientRect().height))) : 0,
    colH2: cols.filter(c => board && c.h > board.getBoundingClientRect().height * 2).map(c => c.st),
    h2Clipped: [...document.querySelectorAll('.board-column header h2')]
      .filter(h => h.scrollWidth > h.clientWidth + 1).map(h => h.textContent.trim()),
  };
})()
"""


async def capture(url: str, out: str, width: int, height: int) -> None:
    import websockets

    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         "--remote-debugging-port=9334", "--user-data-dir=/tmp/cdp-profile-desktop",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=2))
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

            if out:
                shot = await call("Page.captureScreenshot", format="png", captureBeyondViewport=False)
                with open(out, "wb") as fh:
                    fh.write(base64.b64decode(shot["data"]))

            res = await call("Runtime.evaluate", expression=METRICS, returnByValue=True)
            print(json.dumps(res["result"]["value"], ensure_ascii=False))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    url, out = sys.argv[1], sys.argv[2]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1440
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 900
    asyncio.run(capture(url, out, w, h))