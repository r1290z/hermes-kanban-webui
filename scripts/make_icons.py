"""Рисует знак «H» и снимает PNG через headless Chrome.

Иконки PWA собираются из одного источника: белая литера «H» на фоне #0b0c0e.
Литера рисуется прямоугольниками внутри SVG, поэтому результат не зависит от
того, какие шрифты стоят в системе, и внешние файлы не нужны.

    ./.venv/bin/python scripts/make_icons.py [--out static/icons] [--chrome PATH]

Скриншот снимает сам Chrome через CDP (Page.captureScreenshot с clip), а не
`chrome --screenshot --window-size`: в headless=new последний отдаёт не тот
размер. Проверено вручную — при `--window-size=192,192` файл получается
192x192, но контент занимает только 105 строк из 192, остальное прозрачная
пустота. Через CDP с Emulation.setDeviceMetricsOverride размер точный.

Маскабельный вариант — фон во весь квадрат, литера с отступом 20% (безопасная
зона маски Android), обычные иконки — отступ 16%.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHROME = os.environ.get(
    "PROBE_CHROME", "/home/hermes/.hermes/tools/chromium-1208/chrome-linux64/chrome"
)
BACKGROUND = "#0b0c0e"
INK = "#ffffff"

# (файл, сторона в px, отступ литеры в долях стороны)
ICONS = (
    ("icon-192.png", 192, 0.16),
    ("icon-512.png", 512, 0.16),
    ("icon-maskable-512.png", 512, 0.20),
    ("apple-touch-icon-180.png", 180, 0.16),
)


def letter_rects(size: int, pad_fraction: float) -> list[tuple[float, float, float, float]]:
    """Три прямоугольника литеры «H»: левая стойка, правая стойка, перекладина."""
    pad = size * pad_fraction
    box = size - 2 * pad
    stem = box * 0.19
    # Перекладина заходит на пол-стойки внутрь каждой стойки: иначе на стыке
    # из-за субпиксельного сглаживания остаётся шов в 1px.
    return [
        (pad, pad, stem, box),
        (pad + box - stem, pad, stem, box),
        (pad + stem / 2, pad + (box - stem) / 2, box - stem, stem),
    ]


def icon_html(size: int, pad_fraction: float) -> str:
    rects = "\n    ".join(
        f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="{INK}"/>'
        for x, y, w, h in letter_rects(size, pad_fraction)
    )
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Hermes Kanban</title>
<style>html,body{{margin:0;padding:0;width:{size}px;height:{size}px;background:transparent}}
svg{{display:block}}</style></head>
<body>
  <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"
       viewBox="0 0 {size} {size}">
    <rect x="0" y="0" width="{size}" height="{size}" fill="{BACKGROUND}"/>
    {rects}
  </svg>
</body></html>
"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Chrome:
    """Минимальный CDP-клиент: один таб, навигация, скриншот с точным clip."""

    def __init__(self, chrome: str, workdir: Path):
        self.chrome = chrome
        self.workdir = workdir
        self.proc: subprocess.Popen | None = None
        self.ws = None
        self.seq = 0

    async def __aenter__(self) -> "Chrome":
        import websockets

        if not Path(self.chrome).exists():
            raise SystemExit(f"Chrome не найден: {self.chrome} (--chrome / PROBE_CHROME)")
        port = free_port()
        profile = self.workdir / "chrome-profile"
        self.proc = subprocess.Popen(
            [self.chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
             "--hide-scrollbars", "--force-device-scale-factor=1",
             f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 30
        ws_url = None
        while time.time() < deadline:
            try:
                targets = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json", timeout=2))
                page = next(t for t in targets if t["type"] == "page")
                ws_url = page["webSocketDebuggerUrl"]
                break
            except Exception:
                await asyncio.sleep(0.3)
        if not ws_url:
            raise SystemExit("CDP не поднялся")
        self._websockets = websockets
        self.ws = await websockets.connect(ws_url, max_size=64 << 20)
        return self

    async def __aexit__(self, *exc) -> None:
        if self.ws is not None:
            await self.ws.close()
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    async def call(self, method: str, **params):
        ws = self.ws
        if ws is None:
            raise SystemExit("CDP-соединение не открыто")
        self.seq += 1
        await ws.send(json.dumps({"id": self.seq, "method": method, "params": params}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == self.seq:
                if "error" in msg:
                    raise SystemExit(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def render(self, html: str, size: int) -> bytes:
        page_file = self.workdir / f"icon-{size}.html"
        page_file.write_text(html, encoding="utf-8")
        await self.call("Emulation.setDeviceMetricsOverride", width=size, height=size,
                        deviceScaleFactor=1, mobile=False)
        # Фон страницы прозрачный: знак лежит на своей подложке, альфа остаётся
        # только на сглаженных краях (спека §10).
        await self.call("Emulation.setDefaultBackgroundColorOverride",
                        color={"r": 0, "g": 0, "b": 0, "a": 0})
        await self.call("Page.enable")
        await self.call("Page.navigate", url=page_file.as_uri())
        deadline = time.time() + 20
        while time.time() < deadline:
            state = await self.call("Runtime.evaluate", expression="document.readyState",
                                   returnByValue=True)
            if state.get("result", {}).get("value") == "complete":
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.2)
        result = await self.call("Page.captureScreenshot", format="png", fromSurface=True,
                                 captureBeyondViewport=False,
                                 clip={"x": 0, "y": 0, "width": size, "height": size, "scale": 1})
        return base64.b64decode(result["data"])


async def render_all(chrome_bin: str, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="kanban-icons-", dir=os.environ.get("TMPDIR") or None) as tmp:
        async with Chrome(chrome_bin, Path(tmp)) as chrome:
            for name, size, pad in ICONS:
                data = await chrome.render(icon_html(size, pad), size)
                target = out_dir / name
                target.write_bytes(data)
                written.append(target)
                print(f"{target} — {len(data)} байт, {size}x{size}")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Сгенерировать иконки PWA")
    parser.add_argument("--out", default=str(ROOT / "static" / "icons"))
    parser.add_argument("--chrome", default=DEFAULT_CHROME)
    args = parser.parse_args()
    asyncio.run(render_all(args.chrome, Path(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
