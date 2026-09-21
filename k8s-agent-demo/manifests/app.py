"""
Minimal web-api used for the REAL-cluster demo. It validates LOG_LEVEL at
startup and exits(1) on a bad value -- reproducing the CrashLoopBackOff bug.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

VALID = {"DEBUG", "INFO", "WARN", "ERROR"}
level = os.getenv("LOG_LEVEL", "INFO")
port = int(os.getenv("PORT", "8080"))

print("INFO  starting web-api v1.4.2", flush=True)
if level not in VALID:
    print(f'FATAL invalid LOG_LEVEL "{level}" (allowed: DEBUG, INFO, WARN, ERROR)', flush=True)
    print("FATAL configuration validation failed, exiting (code 1)", flush=True)
    sys.exit(1)

print(f"INFO  config OK (LOG_LEVEL={level}, PORT={port})", flush=True)


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok\n")

    def log_message(self, *a):
        pass


print(f"INFO  listening on :{port}", flush=True)
HTTPServer(("0.0.0.0", port), H).serve_forever()
