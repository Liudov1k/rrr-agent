import subprocess
import threading
import time
from http.server import ThreadingHTTPServer

from rrr_agent.nuotraukos import photos_dir
from rrr_agent.viesos import _open_tunnel, _photo_handler, _stop

name = "a53e20e6709a488eb189b0a1e9990d2d.jpg"
files = {name: photos_dir() / name}
server = ThreadingHTTPServer(("127.0.0.1", 0), _photo_handler(files, []))
port = int(server.server_address[1])
threading.Thread(target=server.serve_forever, daemon=True).start()
proc = None
try:
    for attempt in range(3):
        if proc:
            _stop(proc)
        proc, base = _open_tunnel(port)
        host = base.split("//", 1)[1].strip("/")
        print("BANDYMAS", attempt + 1, base, flush=True)
        try:
            output = subprocess.check_output(["nslookup", host], text=True, timeout=15, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            output = exc.output
        print(output[-400:], flush=True)
        if "Address" in output and "can't find" not in output.lower():
            print("URL", f"{base}/{name}", flush=True)
            time.sleep(45)
            break
finally:
    _stop(proc)
    server.shutdown()
