"""Screenshot the live UI through CDP (headless Chrome) at an exact layout viewport.

Same viewport mechanics as probe_ui.py: `--window-size` does not set the layout
viewport in headless=new, so Emulation.setDeviceMetricsOverride does it instead —
what you see in the PNG is what the CSS media queries actually saw.

    python3 scripts/shoot_ui.py URL WIDTH HEIGHT OUT.png [SETTLE_SECONDS]
"""

import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME = (os.environ.get("PROBE_CHROME")
          or shutil.which("google-chrome") or shutil.which("chromium")
          or os.path.expanduser("~/.hermes/tools/chromium-1208/chrome-linux64/chrome"))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def shoot(url: str, width: int, height: int, out: str, settle: float) -> dict:
    import websockets

    port = free_port()
    profile = os.path.join(tempfile.mkdtemp(prefix="shoot-cdp-"), "profile")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                targets = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json", timeout=2))
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
                       deviceScaleFactor=2, mobile=width < 760)
            await call("Page.enable")
            await call("Page.navigate", url=url)
            ready_deadline = time.time() + 20
            while time.time() < ready_deadline:
                state = await call("Runtime.evaluate", expression="document.readyState",
                                   returnByValue=True)
                if state.get("result", {}).get("value") == "complete":
                    break
                await asyncio.sleep(0.25)
            await asyncio.sleep(settle)

            shot = await call("Page.captureScreenshot", format="png", fromSurface=True)
            data = base64.b64decode(shot["data"])
            with open(out, "wb") as handle:
                handle.write(data)
            meta = await call("Runtime.evaluate", returnByValue=True, expression=(
                "JSON.stringify({theme: document.documentElement.dataset.theme,"
                " overflow: document.documentElement.scrollWidth,"
                " height: document.documentElement.scrollHeight})"))
            return {"path": out, "bytes": len(data), "page": json.loads(meta["result"]["value"])}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    if len(sys.argv) < 5:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    url, width, height, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    settle = float(sys.argv[5]) if len(sys.argv) > 5 else float(os.environ.get("PROBE_SETTLE", "6"))
    print(json.dumps(asyncio.run(shoot(url, width, height, out, settle)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())