"""Screenshot a page at a real mobile viewport.

Chrome's `--window-size` does not set the layout viewport in headless=new (a 390x844
request renders at 500x757 and the screenshot is a crop), so the media query never
matches what you asked for. This drives CDP directly: Emulation.setDeviceMetricsOverride
sets the viewport the CSS actually sees.

    python3 shot.py URL OUT.png [width] [height]
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


async def capture(url: str, out: str, width: int, height: int) -> None:
    import websockets

    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         "--remote-debugging-port=9333", "--user-data-dir=/tmp/cdp-profile",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json", timeout=2))
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
                       deviceScaleFactor=2, mobile=True)
            await call("Page.enable")
            await call("Page.navigate", url=url)
            await asyncio.sleep(6)  # let the SPA fetch the board

            shot = await call("Page.captureScreenshot", format="png", captureBeyondViewport=False)
            with open(out, "wb") as fh:
                fh.write(base64.b64decode(shot["data"]))

            size = await call("Runtime.evaluate",
                              expression="innerWidth + 'x' + innerHeight", returnByValue=True)
            overflow = await call("Runtime.evaluate",
                                  expression="document.documentElement.scrollWidth - innerWidth",
                                  returnByValue=True)
            print(f"viewport={size['result']['value']} "
                  f"горизонтальное_переполнение={overflow['result']['value']}px -> {out}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    url, out = sys.argv[1], sys.argv[2]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 390
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 844
    asyncio.run(capture(url, out, w, h))
