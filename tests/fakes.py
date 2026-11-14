"""Local stand-ins for the services the store talks to, so no test ever reaches a real mail server or Meta.

FakeSMTP: a tiny threaded SMTP server (EHLO, MAIL, RCPT, DATA, RSET, NOOP, QUIT; no TLS, no AUTH) that keeps every
message it receives. FakeWhatsApp: an HTTP server that answers the Cloud API's /{phone_id}/messages like Meta does.
"""
import json
import socket
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _SMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        srv = self.server
        self.wfile.write(b"220 fake ESMTP\r\n")
        mail_from, rcpts = None, []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            cmd = line.decode("latin-1").strip()
            up = cmd.upper()
            if up.startswith(("EHLO", "HELO")):
                self.wfile.write(b"250-fake\r\n250 8BITMIME\r\n")
            elif up.startswith("MAIL FROM"):
                mail_from, rcpts = cmd[10:].strip(), []
                self.wfile.write(b"250 OK\r\n")
            elif up.startswith("RCPT TO"):
                if srv.refuse_rcpt:
                    self.wfile.write(b"550 no such user\r\n")
                else:
                    rcpts.append(cmd[8:].strip())
                    self.wfile.write(b"250 OK\r\n")
            elif up == "DATA":
                self.wfile.write(b"354 go ahead\r\n")
                data = []
                while True:
                    l = self.rfile.readline()
                    if l in (b".\r\n", b".\n", b""):
                        break
                    data.append(l)
                srv.messages.append({"from": mail_from, "to": rcpts, "data": b"".join(data).decode("utf-8", "replace")})
                self.wfile.write(b"250 queued\r\n")
            elif up in ("RSET", "NOOP"):
                self.wfile.write(b"250 OK\r\n")
            elif up == "QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"502 not implemented\r\n")


class FakeSMTP(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _SMTPHandler)
        self.messages, self.refuse_rcpt = [], False
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def close(self):
        self.shutdown()
        self.server_close()


class FakeWhatsApp(HTTPServer):
    def __init__(self, status=200):
        self.requests, self.status = [], status

        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                server.requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                        "json": json.loads(body or b"{}")})
                if server.status == 200:
                    payload = {"messages": [{"id": "wamid.FAKE1"}]}
                else:
                    payload = {"error": {"code": 132001, "message": "template does not exist"}}
                out = json.dumps(payload).encode()
                self.send_response(server.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        super().__init__(("127.0.0.1", 0), Handler)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def close(self):
        self.shutdown()
        self.server_close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
