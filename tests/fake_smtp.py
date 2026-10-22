"""A minimal in-process SMTP server for tests: accepts mail and keeps it."""
import socketserver
import threading
from email import message_from_bytes, policy


class _Handler(socketserver.StreamRequestHandler):
    def reply(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")
        self.wfile.flush()

    def handle(self) -> None:
        self.reply("220 fake-smtp ready")
        sender, recipients = None, []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            command = line.decode(errors="replace").strip()
            verb = command.split(" ", 1)[0].upper()

            if verb in ("EHLO", "HELO"):
                self.reply("250 fake-smtp")
            elif verb == "MAIL":
                sender, recipients = command.split(":", 1)[1].strip(), []
                self.reply("250 ok")
            elif verb == "RCPT":
                recipients.append(command.split(":", 1)[1].strip())
                self.reply("250 ok")
            elif verb == "DATA":
                self.reply("354 end with <CRLF>.<CRLF>")
                chunks = []
                while True:
                    data_line = self.rfile.readline()
                    if data_line in (b".\r\n", b""):
                        break
                    chunks.append(data_line)
                raw = b"".join(chunks)
                self.server.inbox.append({
                    "envelope_from": sender,
                    "envelope_to": recipients,
                    "message": message_from_bytes(raw, policy=policy.default),
                    "raw": raw,
                })
                self.reply("250 queued")
            elif verb == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("250 ok")


class FakeSMTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.inbox: list[dict] = []
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self.server_address[1]

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.shutdown()
        self.server_close()
