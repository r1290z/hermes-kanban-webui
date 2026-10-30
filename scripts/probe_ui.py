"""Evaluate a JS expression in a real (headless) browser and print its JSON result.

`--window-size` does not set the layout viewport in headless=new, so the media query
would not match what you asked for. This drives CDP directly:
Emulation.setDeviceMetricsOverride sets the viewport the CSS actually sees, then
Runtime.evaluate returns the value of the expression.

    python3 probe_ui.py URL WIDTH HEIGHT "JS_EXPRESSION"

Prints one line: the JSON value of the expression (or {"error": "..."} on failure).
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

CHROME = os.environ.get("PROBE_CHROME",
                        "/home/hermes/.hermes/tools/chromium-1208/chrome-linux64/chrome")
SETTLE_SECONDS = float(os.environ.get("PROBE_SETTLE", "5"))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def probe(url: str, width: int, height: int, expression: str):
    import websockets

    port = free_port()
    profile = os.path.join(tempfile.mkdtemp(prefix="probe-cdp-"), "profile")
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
            await asyncio.sleep(SETTLE_SECONDS)  # let the SPA fetch the board

            result = await call("Runtime.evaluate", expression=expression,
                                returnByValue=True, awaitPromise=True)
            if "exceptionDetails" in result:
                details = result["exceptionDetails"]
                text = details.get("exception", {}).get("description") or details.get("text")
                return {"error": text}
            return result.get("result", {}).get("value")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    if len(sys.argv) < 4:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    url = sys.argv[1]
    width = int(sys.argv[2])
    height = int(sys.argv[3])
    expression = sys.argv[4] if len(sys.argv) > 4 else "document.title"
    value = asyncio.run(probe(url, width, height, expression))
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())