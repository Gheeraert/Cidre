# local_server.py
from __future__ import annotations

import contextlib
import socket
import threading
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def _find_free_port(host: str = "127.0.0.1") -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


@dataclass
class PreviewServer:
    directory: str
    host: str = "127.0.0.1"
    port: int = 8000

    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None

    def start(self) -> str:
        # si le port demandé est pris, on en choisit un libre
        try_port = int(self.port)
        try:
            handler = partial(SimpleHTTPRequestHandler, directory=self.directory)
            httpd = ThreadingHTTPServer((self.host, try_port), handler)
        except OSError:
            try_port = _find_free_port(self.host)
            handler = partial(SimpleHTTPRequestHandler, directory=self.directory)
            httpd = ThreadingHTTPServer((self.host, try_port), handler)

        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread.start()
        self.port = try_port
        return f"http://{self.host}:{self.port}/"

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._thread = None
