#!/usr/bin/env python3
"""Local preview server with HTTP Range support (so video seeking works).

Python's built-in `http.server` does NOT honor Range requests, which breaks
dragging the video progress bar. This drop-in replacement adds single-range
support. GitHub Pages already supports Range, so this is only for local preview.

Usage:
    python3 serve.py [port]        # default 8000, binds 0.0.0.0 (LAN-visible)
Then open  http://<this-machine-LAN-IP>:<port>
"""
import os
import sys
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeHandler(SimpleHTTPRequestHandler):
    def handle(self):
        # Browsers abort the in-flight request when you seek; swallow the
        # resulting disconnects instead of dumping a traceback per seek.
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_head(self):
        rng = self.headers.get("Range")
        if rng is None:
            return super().send_head()

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        fs = os.fstat(f.fileno())
        size = fs.st_size
        m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
        if not m:
            f.close()
            self.send_error(400, "Invalid Range")
            return None

        start_s, end_s = m.group(1), m.group(2)
        if start_s == "":
            # suffix range: last N bytes
            length = int(end_s)
            start = max(0, size - length)
            end = size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
        end = min(end, size - 1)

        if start > end or start >= size:
            f.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        f.seek(start)
        self._range = (start, end)
        return f

    def copyfile(self, source, outputfile):
        rng = getattr(self, "_range", None)
        try:
            if rng is None:
                return super().copyfile(source, outputfile)
            start, end = rng
            remaining = end - start + 1
            chunk = 64 * 1024
            while remaining > 0:
                data = source.read(min(chunk, remaining))
                if not data:
                    break
                outputfile.write(data)
                remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client seeked/closed mid-stream — harmless


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = partial(RangeHandler, directory=os.path.dirname(os.path.abspath(__file__)))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"Serving with Range support on http://0.0.0.0:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
