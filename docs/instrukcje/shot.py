"""Zrzuty ekranu zalogowanej aplikacji ZCO DM (Edge headless + protokół DevTools).

Wstrzykuje token sesji do localStorage (bez logowania hasłem), przechodzi na wskazane
adresy i zapisuje PNG. Obsługuje:
  - `js`   — wyrażenie wykonywane po załadowaniu strony (np. otwarcie okna dialogowego),
  - `clip` — selektor CSS: kadruje zrzut do wskazanego elementu (okna, panelu),
  - `wait` — ile sekund czekać po nawigacji, `wait_js` — po wykonaniu `js`.
"""
import asyncio, base64, json, os, subprocess, sys, time
import urllib.request
import websockets

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9333
ORIGIN = "http://localhost:3003"
SCALE = 2  # gęstość: ostre zrzuty do druku


class Cdp:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method, params=None):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})


async def capture(shots, token, user_json, width, height):
    info = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
    page = next(t for t in info if t["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=60_000_000) as ws:
        c = Cdp(ws)
        await c.call("Page.enable")
        await c.call("Emulation.setDeviceMetricsOverride",
                     {"width": width, "height": height, "deviceScaleFactor": SCALE, "mobile": False})

        await c.call("Page.navigate", {"url": f"{ORIGIN}/login"})
        await asyncio.sleep(2.5)
        await c.call("Runtime.evaluate", {"expression":
            f"localStorage.setItem('auth_token', {json.dumps(token)});"
            f"localStorage.setItem('auth_user', {json.dumps(user_json)}); 'ok'"})

        for s in shots:
            await c.call("Page.navigate", {"url": ORIGIN + s["path"]})
            await asyncio.sleep(s.get("wait", 3))

            if s.get("js"):
                await c.call("Runtime.evaluate", {"expression": s["js"], "awaitPromise": True})
                await asyncio.sleep(s.get("wait_js", 1.2))

            params = {"format": "png", "captureBeyondViewport": False}
            if s.get("clip"):
                r = await c.call("Runtime.evaluate", {"returnByValue": True, "expression": f"""
                    (() => {{ const e=document.querySelector({json.dumps(s['clip'])});
                      if(!e) return null; const b=e.getBoundingClientRect();
                      const p={s.get('pad', 12)};
                      return {{x:Math.max(0,b.left-p), y:Math.max(0,b.top-p),
                               width:b.width+2*p, height:b.height+2*p}}; }})()"""})

                box = r.get("result", {}).get("value")
                if box:
                    params["clip"] = {**box, "scale": SCALE}
                else:
                    print(f"    UWAGA: nie znaleziono {s['clip']} — pełny ekran")

            res = await c.call("Page.captureScreenshot", params)
            with open(s["out"], "wb") as f:
                f.write(base64.b64decode(res["data"]))
            print(f"  {os.path.basename(s['out'])}")


def main():
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                             f"--remote-debugging-port={PORT}",
                             f"--user-data-dir={cfg['profile']}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        asyncio.run(capture(cfg["shots"], cfg["token"], json.dumps(cfg["user"]),
                            cfg.get("width", 1600), cfg.get("height", 1000)))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
