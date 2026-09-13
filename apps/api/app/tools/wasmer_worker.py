"""Fixed programs run inside Wasmer. No host filesystem mounts or guest network."""

import asyncio
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

from wasmer_sdk import Wasmer

SUMMARY = """import csv, io, json
from decimal import Decimal
rows = list(csv.DictReader(open('/workspace/data.csv')))
if not rows or len(rows) > 1000:
    raise ValueError('Expected 1 to 1000 rows')
values = [Decimal(row['amount']) for row in rows]
if not all(value.is_finite() for value in values):
    raise ValueError('Amounts must be finite')
print(json.dumps({'rows': len(rows), 'total': str(sum(values)), 'currency': 'fixture units'}))
"""

PROBE = """import json, socket
p = json.load(open('/workspace/probe.json'))
results = {}
try:
    open(p['host_path']).read()
    results['host_file_blocked'] = False
except OSError:
    results['host_file_blocked'] = True
try:
    s = socket.socket()
    s.settimeout(2)
    s.connect(('127.0.0.1', p['port']))
    s.close()
    results['network_blocked'] = False
except OSError:
    results['network_blocked'] = True
print(json.dumps(results))
"""


async def run(payload):
    if payload.get("kind") not in ("summary", "containment_probe"):
        raise ValueError("Unsupported program")
    with tempfile.TemporaryDirectory(prefix="safeops-canary-") as temp:
        canary = Path(temp) / "synthetic-secret.txt"
        canary.write_text("SYNTHETIC_SAFEOPS_CANARY_NOT_A_REAL_SECRET")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(2)
            port = listener.getsockname()[1]
            # Positive controls: the host really can read this file and reach this port.
            host_file_readable = canary.read_text().startswith("SYNTHETIC_")
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                accepted, _ = listener.accept()
                accepted.close()
            files = {"main.py": SUMMARY, "data.csv": payload.get("csv_data", "")}
            if payload["kind"] == "containment_probe":
                files = {
                    "main.py": PROBE,
                    "probe.json": json.dumps({"host_path": str(canary), "port": port}),
                }
            async with Wasmer(cache_root=os.environ.get("SAFEOPS_WASMER_CACHE", ".wasmer")) as w:
                # network omitted = disabled. Only these in-memory files enter /workspace.
                async with await w.sandboxes.create(
                    packages=["python/python@=3.13.18"],
                    files=files,
                ) as sandbox:
                    output = await sandbox.command("python", ["/workspace/main.py"]).run()
                    result = json.loads(output.text())
            if payload["kind"] == "containment_probe":
                listener.setblocking(False)
                try:
                    accepted, _ = listener.accept()
                    accepted.close()
                    result["host_received_guest_connection"] = True
                except BlockingIOError:
                    result["host_received_guest_connection"] = False
                result["positive_controls"] = {
                    "host_can_read_canary": host_file_readable,
                    "host_can_connect_listener": True,
                }
            return result


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read(20000))
        print(json.dumps(asyncio.run(run(payload))))
    except Exception as exc:
        # No secrets or native diagnostic details in the tool protocol.
        print(type(exc).__name__, file=sys.stderr)
        sys.exit(1)
