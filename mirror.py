#!/usr/bin/env python3
"""novastudio.hu Framer-oldal tükrözése statikus, önhordó másolatba.

Kimenet: docs/ mappa (GitHub Pages-hez), minden asset lokálisan,
minden hivatkozás relatív útvonalra átírva.
"""
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "docs"
SITE = "https://www.novastudio.hu"
ASSET_DOMAINS = (
    "framerusercontent.com",
    "app.framerstatic.com",
    "fonts.gstatic.com",
    "fonts.googleapis.com",
)
TEXT_EXT = {".html", ".css", ".js", ".mjs", ".json", ".svg", ".txt", ".xml"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

URL_RE = re.compile(
    r"https://(?:" + "|".join(re.escape(d) for d in ASSET_DOMAINS) + r")/[^\s\"'<>\\)`{}]+"
)
ESC_URL_RE = re.compile(
    r"https:\\/\\/(?:" + "|".join(re.escape(d) for d in ASSET_DOMAINS) + r")(?:\\/[^\s\"'<>)`{}]*)+"
)


def log(msg):
    print(msg, flush=True)


def fetch(url, binary=True, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data
        except Exception as e:
            if attempt == retries - 1:
                raise
            log(f"  retry {attempt+1} ({e}): {url}")
            time.sleep(2 * (attempt + 1))


def page_local_dir(url):
    """https://www.novastudio.hu/munkaink/foo -> docs/munkaink/foo/"""
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path).strip("/")
    return OUT / path if path else OUT


def asset_local_path(url):
    """CDN-URL -> docs/assets/<domain>/<path>  (query levágva)."""
    p = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(p.path).lstrip("/")
    if not path or path.endswith("/"):
        path += "index"
    return OUT / "assets" / p.netloc / path


def root_url(target_path):
    """Gyökér-abszolút útvonal (/assets/...) a docs/ gyökértől.

    Azért abszolút, mert a JS-modulokba írt relatív útvonalakat a böngésző
    az OLDAL URL-jéhez képest oldja fel, nem a modulfájlhoz képest.
    """
    rel = os.path.relpath(target_path, OUT)
    return "/" + urllib.parse.quote(rel.replace(os.sep, "/"))


def find_asset_urls(text):
    urls = set(URL_RE.findall(text))
    for m in ESC_URL_RE.findall(text):
        urls.add(m.replace("\\/", "/"))
    # zajszűrés: záró írásjelek levágása
    clean = set()
    for u in urls:
        clean.add(u.rstrip(".,;"))
    return clean


def main():
    OUT.mkdir(exist_ok=True)

    # 1) sitemap -> oldalak
    sm = fetch(SITE + "/sitemap.xml").decode("utf-8")
    tree = ET.fromstring(sm)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    page_urls = [loc.text.strip() for loc in tree.findall(".//s:loc", ns)]
    log(f"Sitemap: {len(page_urls)} oldal")

    # 2) oldalak letöltése
    html_files = []
    for url in page_urls:
        d = page_local_dir(url)
        d.mkdir(parents=True, exist_ok=True)
        f = d / "index.html"
        if not f.exists():
            log(f"HTML: {url}")
            f.write_bytes(fetch(url))
        html_files.append(f)

    # 3) assetek letöltése iteratívan (JS/CSS-ből újabb URL-ek jöhetnek)
    url2local = {}   # asset URL (query nélkül) -> lokális Path
    all_urls = {}    # teljes URL (queryvel) -> query nélküli kulcs
    pending_scan = list(html_files) + [
        f for f in OUT.rglob("*")
        if f.is_file() and f.suffix.lower() in TEXT_EXT and f not in html_files
    ]
    scanned = set()
    failed = []

    while pending_scan:
        f = pending_scan.pop()
        if f in scanned:
            continue
        scanned.add(f)
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # CMS-adatchunkok: a Framer runtime a modul-URL-ből építi őket
        # ("/modules/" -> "/cms/" csere), ezért le kell tölteni a cms/ fát is.
        rel_to_modules = None
        try:
            rel_to_modules = f.relative_to(OUT / "assets" / "framerusercontent.com" / "modules")
        except ValueError:
            pass
        if rel_to_modules is not None:
            for name in set(re.findall(r"\./([A-Za-z0-9_.-]+\.framercms)", text)):
                cms_url = ("https://framerusercontent.com/cms/"
                           + str(rel_to_modules.parent).replace(os.sep, "/") + "/" + name)
                base = cms_url
                all_urls[cms_url] = base
                if base not in url2local:
                    local = asset_local_path(base)
                    url2local[base] = local
                    if not local.exists():
                        local.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            log(f"CMS: {base}")
                            local.write_bytes(fetch(base))
                        except Exception as e:
                            log(f"  HIBA: {base} -> {e}")
                            failed.append(base)
                            del url2local[base]

        # Relatív dinamikus importok a sites/ modulokban (pl. import(`./x.mjs`))
        # — ezeket a CDN azonos mappájából kell pótolni.
        rel_to_sites = None
        try:
            rel_to_sites = f.relative_to(OUT / "assets" / "framerusercontent.com" / "sites")
        except ValueError:
            pass
        if rel_to_sites is not None:
            site_dir = str(rel_to_sites.parent).replace(os.sep, "/")
            for name in set(re.findall(r"\./([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.mjs)", text)):
                local = f.parent / name
                if not local.exists():
                    url = f"https://framerusercontent.com/sites/{site_dir}/{name}"
                    try:
                        log(f"CHUNK: {url}")
                        local.write_bytes(fetch(url))
                        pending_scan.append(local)
                    except Exception as e:
                        log(f"  HIBA: {url} -> {e}")
                        failed.append(url)

        for full_url in find_asset_urls(text):
            base = full_url.split("?")[0].split("#")[0]
            if base.endswith("/"):
                # URL-előtag (pl. fontshare/, fonts.gstatic.com/s/) — nem fájl,
                # futásidőben fűzik hozzá a fájlnevet; hagyjuk abszolútnak.
                continue
            all_urls[full_url] = base
            if base in url2local:
                continue
            local = asset_local_path(base)
            url2local[base] = local
            if not local.exists():
                local.parent.mkdir(parents=True, exist_ok=True)
                try:
                    log(f"ASSET: {base}")
                    local.write_bytes(fetch(base))
                except Exception as e:
                    log(f"  HIBA: {base} -> {e}")
                    failed.append(base)
                    del url2local[base]
                    continue
            if local.suffix.lower() in TEXT_EXT:
                pending_scan.append(local)

    # A phosphor ikon-betöltő futásidőben, név szerint tölti az ikonokat
    # (@verzió utótaggal). A teljes névlistát a bundle-ből nyerjük ki, majd
    # minden olyan ikont letöltünk, aminek a neve előfordul az oldal fájljaiban.
    PHOSPHOR_VERSION = "0.0.57"
    all_text = ""
    for f in OUT.rglob("*"):
        if f.is_file() and f.suffix.lower() in TEXT_EXT | {".framercms"}:
            all_text += f.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"`([A-Za-z]+(?:\.[A-Za-z]+){400,})`\.split\(`\.`\)", all_text)
    icon_names = m.group(1).split(".") if m else []
    log(f"Phosphor névlista: {len(icon_names)} ikon")
    kebab = lambda n: re.sub(r"(?<!^)(?=[A-Z])", "-", n).lower()
    used = set()
    for n in icon_names:
        for probe in (f"`{n}`", f'"{n}"', f"`{kebab(n)}`", f'"{kebab(n)}"'):
            if probe in all_text:
                used.add(n)
                break
    log(f"Használt ikonok: {len(used)}")
    picon_dir = OUT / "assets" / "phosphor-icons"
    picon_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(used):
        local = picon_dir / f"{name}.js"
        versioned = picon_dir / f"{name}.js@{PHOSPHOR_VERSION}"
        if not versioned.exists():
            url = f"https://framer.com/m/phosphor-icons/{name}.js@{PHOSPHOR_VERSION}"
            try:
                log(f"ICON: {url}")
                shim = fetch(url).decode("utf-8")
                # a framer.com-os URL csak re-export burok -> a valódi modul kell
                m2 = re.search(r'from\s+"(https://framerusercontent\.com/[^"]+)"', shim)
                data = fetch(m2.group(1)) if m2 else shim.encode("utf-8")
                versioned.write_bytes(data)
                local.write_bytes(data)
            except Exception as e:
                log(f"  HIBA (ikon, nem kritikus): {url} -> {e}")

    log(f"\nAssetek: {len(url2local)} letöltve, {len(failed)} hiba")

    # 4) URL-átírás minden szöveges fájlban
    text_files = [f for f in OUT.rglob("*") if f.is_file() and f.suffix.lower() in TEXT_EXT]
    # hosszabb URL-t előbb cserélünk (query-s változat a query nélküli előtt)
    ordered = sorted(all_urls.keys(), key=len, reverse=True)

    for f in text_files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        orig = text
        for full_url in ordered:
            base = all_urls[full_url]
            if base not in url2local:
                continue
            if full_url not in text and full_url.replace("/", "\\/") not in text:
                continue
            rel = root_url(url2local[base])
            text = text.replace(full_url, rel)
            text = text.replace(full_url.replace("/", "\\/"), rel.replace("/", "\\/"))
        # phosphor ikon-betöltő bázis-URL lokalizálása
        text = text.replace(
            "https://framer.com/m/phosphor-icons/", "/assets/phosphor-icons/"
        )
        # belső oldal-linkek átírása gyökér-abszolútra (csak HTML-ben)
        if f.suffix == ".html":
            def repl_page(m):
                path = urllib.parse.unquote(m.group(1) or "").strip("/")
                return "/" if not path else "/" + urllib.parse.quote(path) + "/"
            text = re.sub(
                r"https://(?:www\.)?novastudio\.hu(/[^\s\"'<>]*)?",
                repl_page,
                text,
            )
            # relatív hrefek ("./x", "../x") abszolútra írása. FONTOS: az
            # eredeti oldalon az útvonalak perjel nélküliek (/munkaink/otp),
            # így a relatív link az OLDAL mappájához képest értendő
            # (aloldalon a "./otp-reklamok#x" saját-oldali horgony!).
            rel_page = f.parent.relative_to(OUT)
            page_path = "/" if str(rel_page) == "." else "/" + str(rel_page).replace(os.sep, "/")
            page_base = "http://x" + page_path.rstrip("/")

            def repl_rel_href(m):
                href = m.group(1)
                u = urllib.parse.urlparse(urllib.parse.urljoin(page_base, href))
                p = u.path or "/"
                if not p.endswith("/") and not re.search(r"\.[a-z0-9]{2,5}$", p, re.I):
                    p += "/"
                hash_ = f"#{u.fragment}" if u.fragment else ""
                return f'href="{p}{hash_}"'
            text = re.sub(r'href="(\.{1,2}/[^"]*)"', repl_rel_href, text)
            # A Framer kliensoldali (SPA) navigációja a tükörben megbízhatatlan
            # (CMS range-lekérések, lefagyás). A router a Navigation API
            # "navigate" eseményével téríti el a linkeket -> a feliratkozást
            # tiltjuk le, így minden belső link teljes oldalbetöltéssel megy.
            # + a hidratálás relatív hrefeket ír vissza (pl. "munkaink/x"), ami a
            # könyvtáras URL-jeink alól rossz helyre oldódna fel -> kattintáskor
            # gyökér-abszolútra normalizálunk (az eredetin minden út gyökérszintű).
            NAV_FIX = (
                '<script data-mirror-nav>(function(){'
                # a kereso-modul new URL()-lel validalja a search-index metat,
                # ezert a gyoker-relativ utvonalat abszolutra irjuk futaskor
                'document.querySelectorAll(\'meta[name^="framer-search-index"]\')'
                '.forEach(function(m){var c=m.getAttribute("content");'
                'if(c&&c.charAt(0)==="/")m.setAttribute("content",location.origin+c);});'
                'if(window.navigation&&window.navigation.addEventListener){'
                'var o=window.navigation.addEventListener.bind(window.navigation);'
                'window.navigation.addEventListener=function(t,f,x){'
                'if(t==="navigate")return;return o(t,f,x);};}'
                'document.addEventListener("click",function(e){'
                'if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||'
                'e.shiftKey||e.altKey)return;'
                'var a=e.target&&e.target.closest?e.target.closest("a[href]"):null;'
                'if(!a)return;var h=a.getAttribute("href")||"";'
                'if(!h||h.charAt(0)==="#"||h.slice(0,2)==="//"||'
                '/^[a-z][a-z0-9+.-]*:/i.test(h))return;'
                'if(a.target&&a.target!=="_self")return;'
                'e.preventDefault();e.stopPropagation();'
                # az eredeti (perjel nelkuli) oldal-utvonalhoz kepest oldjuk fel,
                # igy az aloldali relativ linkek (./x, ../x, x) is jo helyre mennek
                'var u=new URL(h,location.origin+location.pathname.replace(/\\/$/,""));'
                'var p=u.pathname;'
                'if(p.charAt(p.length-1)!=="/"&&!/\\.[a-z0-9]{2,5}$/i.test(p))p+="/";'
                'location.assign(p+u.search+u.hash);},true);'
                '})();</script>'
            )
            text = re.sub(r'<script data-mirror-nav>.*?</script>', "", text)
            text = text.replace("</head>", NAV_FIX + "</head>", 1)
        # new URL(x, "/assets/...") érvénytelen bázissal dobna -> origin elé
        if f.suffix in {".mjs", ".js", ".html"}:
            text = re.sub(
                r"new URL\(([^()]*?),\s*([`\"'])(/assets/[^`\"']*?)\2\)",
                r"new URL(\1,location.origin+\2\3\2)",
                text,
            )
            text = re.sub(
                r"new URL\(\s*([`\"'])(/assets/[^`\"']*?)\1\s*\)",
                r"new URL(location.origin+\1\2\1)",
                text,
            )
        if text != orig:
            f.write_text(text, encoding="utf-8")

    # 5) maradék-ellenőrzés
    leftover = 0
    for f in text_files:
        t = f.read_text(encoding="utf-8", errors="ignore")
        n = len(URL_RE.findall(t)) + len(re.findall(r"https://(?:www\.)?novastudio\.hu/", t))
        if n:
            log(f"MARADÉK ({n}): {f.relative_to(OUT)}")
            leftover += n
    log(f"\nKész. Oldalak: {len(html_files)}, assetek: {len(url2local)}, "
        f"sikertelen: {len(failed)}, maradék külső hivatkozás: {leftover}")
    if failed:
        log("Sikertelen letöltések:")
        for u in failed:
            log(f"  {u}")


if __name__ == "__main__":
    main()
