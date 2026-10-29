"""Screenshot the run-pulse line on a running task card at desktop/mobile sizes.

Opens the WebUI with the access token, waits until the card's pulse line
("[data-pulse-id]") has non-empty text (a live /api/pulse poll result), then
captures board and list views and reports horizontal overflow.

    KANBAN_TOKEN=... python3 shot_pulse.py TASK_ID OUT_PREFIX
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

CHROME = "/home/hermes/.hermes/tools/chromium-1208/chrome-linux64/chrome"
BASE = os.environ.get("KANBAN_WEBUI_BASE", "http://127.0.0.1:8790")
PORT = 9337

WAIT_PULSE = """
(() => new Promise(resolve => {
  const taskId = %s;
  const started = Date.now();
  const tick = () => {
    const el = document.querySelector(`[data-pulse-id="${taskId}"]`);
    if ((el && el.textContent.trim()) || Date.now() - started > 25000) {
      resolve(el ? el.textContent.trim() : null);
    } else setTimeout(tick, 200);
  };
  tick();
}))()
"""

SHOTS = [
    ("board", 1440, 900, False),
    ("board", 390, 844, True),
    ("list", 390, 844, True),
]

GOTO = """
(() => { history.replaceState(null, '', '#view=%VIEW%');
  window.dispatchEvent(new Event('hashchange')); return location.hash; })()
"""

OVERFLOW = """
(() => JSON.stringify({
  pageOverflow: document.documentElement.scrollWidth - innerWidth,
  hash: location.hash,
  listHidden: document.getElementById('viewList')?.hidden,
  pulse: [...document.querySelectorAll('[data-pulse-id]')]
    .map(el => ({ id: el.dataset.pulseId, text: el.textContent.trim() })),
}))()
"""


async def run(task_id: str, out_prefix: str) -> None:
    import websockets

    token = os.environ["KANBAN_TOKEN"]
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-pulse", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2))
                ws_url = next(t for t in targets if t["type"] == "page")["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.3)
        async with websockets.connect(ws_url, max_size=64 << 20) as ws:
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

            async def evaluate(expr, await_promise=True):
                res = await call("Runtime.evaluate", expression=expr,
                                 awaitPromise=await_promise, returnByValue=True)
                inner = res.get("result", {})
                if inner.get("exceptionDetails"):
                    raise SystemExit(f"evaluate failed: {inner['exceptionDetails']}")
                return inner.get("value")

            await call("Page.enable")
            await call("Page.navigate", url=f"{BASE}/")
            await asyncio.sleep(1.5)
            await evaluate(f"localStorage.setItem('kanbanToken', {json.dumps(token)}); 'ok'", await_promise=False)
            await call("Page.navigate", url=f"{BASE}/")
            text = await evaluate(WAIT_PULSE % json.dumps(task_id))
            if not text:
                raise SystemExit(f"pulse line never rendered for {task_id}")
            print(f"pulse line: {text!r}")

            for view, width, height, mobile in SHOTS:
                await call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                           deviceScaleFactor=1, mobile=mobile)
                await evaluate(GOTO.replace("%VIEW%", view))
                await asyncio.sleep(1.2)
                await evaluate(
                    f"(() => {{ const el = document.querySelector('[data-pulse-id={json.dumps(task_id)}]');"
                    " if (el) { el.scrollIntoView({ block: 'center' }); return 'scrolled'; }"
                    " return 'no-element'; })()")
                await asyncio.sleep(0.6)
                info = await evaluate(OVERFLOW)
                vis = await evaluate(
                    f"(() => {{ const els = [...document.querySelectorAll('[data-pulse-id={json.dumps(task_id)}]')];"
                    " return JSON.stringify(els.map(el => { const r = el.getBoundingClientRect();"
                    " const cs = getComputedStyle(el); return { text: el.textContent.trim(),"
                    " x: Math.round(r.x), w: Math.round(r.width), h: Math.round(r.height),"
                    " display: cs.display }; })); })()")
                await asyncio.sleep(0.4)
                shot = await call("Page.captureScreenshot", format="png")
                out = f"{out_prefix}_{view}_{width}.png"
                with open(out, "wb") as fh:
                    fh.write(base64.b64decode(shot["data"]))
                print(f"{out}: viewport {width}x{height}, pulse-vis={vis}, {info}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1], sys.argv[2]))
