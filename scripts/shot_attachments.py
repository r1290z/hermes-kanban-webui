"""Screenshot the task drawer's attachments block at desktop and mobile sizes.

Opens the WebUI with the access token, clicks a given task card, waits until
the attachments list (and image previews) have rendered, scrolls the block into
view, captures the PNG, and reports horizontal overflow.

    KANBAN_TOKEN=... python3 shot_attachments.py TASK_ID OUT_1440 OUT_390
"""

import asyncio
import base64
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
BASE = os.environ.get("KANBAN_WEBUI_BASE", "http://127.0.0.1:8790")
PORT = 9335

WAIT_CARD = """
(() => new Promise(resolve => {
  const started = Date.now();
  const tick = () => {
    const card = document.querySelector('.task-card');
    if (card || Date.now() - started > 20000) resolve(!!card);
    else setTimeout(tick, 200);
  };
  tick();
}))()
"""

WAIT_ATTACHMENTS = """
(() => new Promise(resolve => {
  const started = Date.now();
  const tick = () => {
    const items = document.querySelectorAll('#attachmentList .attachment-item').length;
    const imgs = [...document.querySelectorAll('#attachmentList img.attachment-thumb')];
    const imgsDone = imgs.every(img => img.complete && img.naturalWidth > 0);
    if ((items > 0 && imgsDone) || Date.now() - started > 20000) resolve(items);
    else setTimeout(tick, 200);
  };
  tick();
}))()
"""

SCROLL_TO_ATTACHMENTS = """
(() => {
  const section = document.getElementById('attachmentsSection');
  if (section) section.scrollIntoView({ block: 'center' });
  const drawer = document.getElementById('drawer');
  if (drawer) drawer.scrollTop = Math.max(0, drawer.scrollTop - drawer.clientHeight / 4);
  return JSON.stringify({
    items: document.querySelectorAll('#attachmentList .attachment-item').length,
    pageOverflow: document.documentElement.scrollWidth - innerWidth,
    drawerOverflow: drawer ? drawer.scrollWidth - drawer.clientWidth : null,
  });
})()
"""


async def run(task_id: str, out_desktop: str, out_mobile: str) -> None:
    import websockets

    token = os.environ["KANBAN_TOKEN"]
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-attachments", "about:blank"],
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
                res = await call("Runtime.evaluate", expression=expr, awaitPromise=await_promise,
                                 returnByValue=True)
                inner = res.get("result", {})
                if inner.get("exceptionDetails"):
                    raise SystemExit(f"evaluate failed: {inner['exceptionDetails']}")
                return inner.get("value")

            await call("Page.enable")
            await call("Page.navigate", url=f"{BASE}/")
            await asyncio.sleep(1.5)
            await evaluate(f"localStorage.setItem('kanbanToken', {json.dumps(token)}); 'ok'", await_promise=False)
            await call("Page.navigate", url=f"{BASE}/")
            await evaluate(WAIT_CARD)
            await evaluate(f"document.querySelector('.task-card[data-task-id={json.dumps(task_id)}]')?.click(); 'ok'", await_promise=False)
            items = await evaluate(WAIT_ATTACHMENTS)
            for out, width, height in ((out_desktop, 1440, 900), (out_mobile, 390, 844)):
                await call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                           deviceScaleFactor=1, mobile=(width < 800))
                await asyncio.sleep(0.6)
                info = await evaluate(SCROLL_TO_ATTACHMENTS)
                await asyncio.sleep(0.4)
                shot = await call("Page.captureScreenshot", format="png")
                with open(out, "wb") as fh:
                    fh.write(base64.b64decode(shot["data"]))
                print(f"{out}: viewport {width}x{height}, {info}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1], sys.argv[2], sys.argv[3]))
