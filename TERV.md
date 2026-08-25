# Nova Studio weboldal — Framer kiváltása ingyenes hostinggal

**Cél:** a www.novastudio.hu (Framer, ~60 000 Ft/év) egy-az-egyben lemásolása statikus oldalként, ingyenes hostingra (GitHub Pages), a saját domain megtartásával. A Framer-előfizetés ezután lemondható.

**Státusz (2026-08-25):** Tükrözés + lokális ellenőrzés KÉSZ. Következik: user végigkattint lokálisan (http://localhost:8797/), utána GitHub Pages + DNS.

**Technikai megjegyzések a tükörhöz (jövőbeli session-öknek):**
- `mirror.py` végzi a teljes tükrözést a `docs/` mappába; újrafuttatható, a meglévő fájlokat átugorja.
- Minden URL gyökér-abszolút (`/assets/...`) — a JS-be írt relatív útvonalakat a böngésző az oldalhoz képest oldaná fel, ezért kellett. Emiatt a hosting csak domain-gyökérből működik (custom domain vagy user-site, NEM github.io/repo alútvonal).
- `new URL(x, "/assets/...")` hívásokba `location.origin` van befűzve (különben Invalid base URL hibával elhal a render).
- Framer CMS-adatchunkok (`.framercms`) a `/modules/`→`/cms/` úton; lazy-load `./*.mjs` chunkok és a phosphor ikonkészlet (1030 db, verziózott fájlnévvel is: `Name.js@0.0.57`) mind lokalizálva.
- Szándékosan külső maradt 2 URL-előtag a runtime-ban (fonts.gstatic.com/s/, framerusercontent.com/third-party-assets/fontshare/) — dinamikus font-fallbackhez; minden ténylegesen használt fontfájl lokális.
- Teljes 29 oldalas böngészős bejárás: 0 konzolhiba, 0 külső kérés, 0 szerveroldali 404.
- **Kliensoldali (SPA) navigáció KIKAPCSOLVA** (2026-08-25, „munkáink nem megy" hibajavítás): a Framer routere a Navigation API `navigate` eseményével téríti el a linkeket, és a tükörben lefagyott/elakadt (CMS range-lekérések). A minden HTML-be beszúrt `data-mirror-nav` szkript (1) letiltja a `navigate`-feliratkozást, (2) kattintáskor a hidratálás által visszaírt relatív linkeket (`munkaink/x`) gyökér-abszolútra normalizálja — az eredeti oldalon minden útvonal gyökérszintű volt, nálunk könyvtáras (`/munkaink/`), ezért duplázódna. Minden belső link teljes oldalbetöltés (minden oldal SSR HTML-ként létezik, így ez megbízható).
- **Kereső javítva:** a search-modul `new URL()`-lel validálja a `framer-search-index` meta tartalmát — relatív útvonalra elhasal („Site is being indexed"). A beszúrt szkript induláskor abszolútra írja a meta-tageket. A searchIndex JSON-ok lokálban.
- **Lokális teszt: `python3 serve.py`** (port 8797) — HTTP Range-támogatással szolgálja ki a docs/-t (a sima http.server nem tud Range-et, amitől a Framer CMS-betöltő „Unexpected response length" hibát dobna).
- Böngésző-cache csapda: a lokális szerver nem küld Cache-Control-t, módosítás után Cmd+Shift+R kell a teszthez.

## Felmérés eredménye (2026-08-25)

- **29 oldal** összesen: főoldal + cégünk, brandup, karrier, kepzesek, munkaink, kontakt + 22 munkáink-aloldal (sitemap.xml-ből).
- **Nincs űrlap** sehol — a kontakt oldalon csak `mailto:info@novastudio.hu` és `tel:` linkek. Nem kell szerveroldali funkció → tisztán statikus másolat működik.
- **Minden asset a framerusercontent.com CDN-ről jön** (csak a főoldalon 219 hivatkozás): képek, mp4 videók, fontok, és a Framer runtime JS (animációk). Ezeket **le kell tölteni lokálba**, mert az előfizetés lemondása után a CDN-tartalom törlődhet.
- YouTube-beágyazások vannak — azok változatlanul működnek majd.

## Lépések

1. **Tükrözés (Python szkript, `mirror.py`):**
   - Sitemap alapján mind a 29 oldal HTML-jének letöltése.
   - Minden hivatkozott asset (kép, videó, font, JS, CSS — framerusercontent.com és társai) letöltése az `assets/` mappába, beleértve a `srcset` variánsokat és a CSS-ekben/JS-ben hivatkozott URL-eket is.
   - HTML-ekben az URL-ek átírása lokális relatív útvonalakra; ékezetes URL-ek (pl. `/cégünk`) mappanévvé alakítása `index.html`-lel, hogy a linkek változatlanul működjenek.
2. **Ellenőrzés lokálisan:** `python3 -m http.server`-rel felszolgálva minden oldal végigkattintása — layout, animációk, videók, menü, aloldal-linkek. Automatikus check: nem maradt-e a HTML-ekben framerusercontent/framer.com hivatkozás.
3. **GitHub Pages élesítés:**
   - Repo: `gyovaiadam97/novastudio-web` (public — a Pages ingyenes szintjéhez az kell; egy publikus weboldalnál ez nem gond).
   - Méret-ellenőrzés: GitHub-limit 100 MB/fájl, ~1 GB/repo. Ha egy mp4 túl nagy → tömörítés (ffmpeg) vagy YouTube/külső hosting.
   - Custom domain: `CNAME` fájl + DNS-átállítás a domainszolgáltatónál (www → CNAME `gyovaiadam97.github.io`, apex → GitHub A-rekordok). HTTPS-t a GitHub adja ingyen.
4. **Átállás biztonságosan:** előbb a GitHub Pages-verzió ellenőrzése ideiglenes címen, csak utána DNS-átállítás. A Framer-előfizetést **csak azután** mondjuk le, hogy az új oldal a saját domainen hibátlanul fut (a DNS-átállás után is érdemes 1-2 hetet várni a lemondással).

## Amit tudni kell (trade-offok)

- Az eredmény **befagyasztott másolat**: nincs többé Framer-szerkesztő. Módosítás ezután a HTML szerkesztésével történik (Claude-dal ez gyorsan megy, de nem drag-and-drop).
- A domain (novastudio.hu) éves díja marad — az a Framer-díjtól független.
- A Framer-animációk a letöltött runtime JS-sel jó eséllyel működni fognak, de ezt a lokális teszt dönti el; ami nem működik, azt egyszerűbb CSS-animációra cseréljük.

## Nyitott kérdések

- Ki kezeli a novastudio.hu DNS-ét (melyik szolgáltató)? Az átállításhoz oda belépés kell.
- Van-e olyan oldal/tartalom, ami NEM kell az új verzióba?
