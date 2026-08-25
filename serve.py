#!/usr/bin/env python3
"""Lokális tesztszerver a docs/ mappához, HTTP Range támogatással.

A Framer CMS-betöltője byte-range kérésekkel olvassa a .framercms fájlokat,
ezért a sima `python3 -m http.server` nem elég (az a teljes fájlt adja vissza,
"Unexpected response length" hibát okozva). A GitHub Pages támogatja a
Range-et, ez a szerver ugyanazt a viselkedést adja lokálban.

Futtatás:  python3 serve.py [port]   (alapértelmezés: 8797)
"""
import os
import re
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path) or "Range" not in self.headers:
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers["Range"].strip())
        if not m or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
        end = min(int(m.group(2)), size - 1) if m.group(1) and m.group(2) else size - 1
        if start >= size:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None
        f = open(path, "rb")
        f.seek(start)
        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        self._range_length = length
        return f

    def copyfile(self, source, outputfile):
        length = getattr(self, "_range_length", None)
        if length is None:
            return super().copyfile(source, outputfile)
        remaining = length
        while remaining > 0:
            chunk = source.read(min(65536, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)
        self._range_length = None


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8797
    docs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    handler = partial(RangeHandler, directory=docs)
    print(f"Szerver: http://localhost:{port}/  (docs: {docs})")
    ThreadingHTTPServer(("", port), handler).serve_forever()
