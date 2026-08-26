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


async def capture(shots, token, user_json, width, height, origin, jezyk):
    info = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
    page = next(t for t in info if t["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=60_000_000) as ws:
        c = Cdp(ws)
        await c.call("Page.enable")
        await c.call("Emulation.setDeviceMetricsOverride",
                     {"width": width, "height": height, "deviceScaleFactor": SCALE, "mobile": False})

        await c.call("Page.navigate", {"url": f"{origin}/login"})
        await asyncio.sleep(2.5)
        # Język interfejsu siedzi w ciasteczku `locale` i jest czytany PO STRONIE
        # SERWERA przy każdym żądaniu. Ustawiamy je razem z sesją, więc nie ruszamy
        # ustawień konta na produkcji — zrzuty w obcym języku nie zostawiają śladu.
        # `localStorage.clear()` (zrzut ekranu logowania) ciasteczka nie kasuje,
        # więc ekran logowania też wychodzi w wybranym języku.
        ustaw = (f"document.cookie = 'locale={jezyk}; path=/; max-age=86400';"
                 f"localStorage.setItem('auth_token', {json.dumps(token)});"
                 f"localStorage.setItem('auth_user', {json.dumps(user_json)}); 'ok'")
        await c.call("Runtime.evaluate", {"expression": ustaw})

        for s in shots:
            # `wyloguj` — zrzut ekranu logowania. Sesję trzeba zdjąć przed nawigacją,
            # bo zalogowana aplikacja przekierowuje z /login na Dashboard.
            if s.get("wyloguj"):
                await c.call("Runtime.evaluate", {"expression": "localStorage.clear(); 'ok'"})
            await c.call("Page.navigate", {"url": origin + s["path"]})
            await asyncio.sleep(s.get("wait", 3))

            # Kilka kroków po kolei: wejście do folderu, zaznaczenie, otwarcie okna.
            # Każdy dostaje własną pauzę, bo React przerysowuje ekran między nimi.
            for klucz in ("js", "js2", "js3"):
                if not s.get(klucz):
                    continue
                await c.call("Runtime.evaluate", {"expression": s[klucz], "awaitPromise": True})
                await asyncio.sleep(s.get("wait_" + klucz, 1.2))

            params = {"format": "png", "captureBeyondViewport": False}
            if s.get("clip") or s.get("clip_js"):
                # `clip_js` — wyrażenie zwracające element. Potrzebne tam, gdzie
                # kadrowany fragment nie ma stabilnego selektora CSS (np. rząd paneli
                # rozpoznawany po nagłówku, który w nim leży).
                znajdz = s["clip_js"] if s.get("clip_js") else f"document.querySelector({json.dumps(s['clip'])})"
                r = await c.call("Runtime.evaluate", {"returnByValue": True, "expression": f"""
                    (() => {{ const e={znajdz};
                      if(!e) return null; const b=e.getBoundingClientRect();
                      const p={s.get('pad', 12)};
                      return {{x:Math.max(0,b.left-p), y:Math.max(0,b.top-p),
                               width:b.width+2*p, height:b.height+2*p}}; }})()"""})

                box = r.get("result", {}).get("value")
                if box:
                    params["clip"] = {**box, "scale": SCALE}
                else:
                    print(f"    UWAGA: nie znaleziono kadru dla {os.path.basename(s['out'])} — pełny ekran")

            res = await c.call("Page.captureScreenshot", params)
            os.makedirs(os.path.dirname(s["out"]), exist_ok=True)
            with open(s["out"], "wb") as f:
                f.write(base64.b64decode(res["data"]))
            print(f"  {os.path.basename(s['out'])}")
            if s.get("wyloguj"):
                await c.call("Runtime.evaluate", {"expression": zaloguj})


def main():
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    # `--lang` ustawia język SAMEJ PRZEGLĄDARKI, nie aplikacji. Widać go na
    # elementach, których nie rysujemy my: przycisk pola wyboru pliku („Wybierz
    # pliki / Nie wybrano pliku") jest napisem Edge'a i na zrzucie z niemieckiego
    # interfejsu sterczał po polsku, bo taki jest język systemu.
    jezyk = cfg.get("jezyk", "pl")
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                             f"--lang={jezyk}", f"--accept-lang={jezyk}",
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
                            cfg.get("width", 1600), cfg.get("height", 1000),
                            cfg.get("origin", "http://localhost:3010"),
                            cfg.get("jezyk", "pl")))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
