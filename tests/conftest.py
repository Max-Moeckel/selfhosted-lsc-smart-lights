"""Test harness: run the real Flask app + SSE poller against a faked lamp.

Everything the UI depends on runs for real — the Flask routes, the central status
poller, the SSE stream, the templates and the actual app.js in a real browser. Only
the LAN device is swapped for an in-memory fake, so the tests are deterministic and
need no hardware.
"""

import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

# Make the app package importable (repo root) and the fake (this dir).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_lamp  # noqa: E402

# ceiling: online, colour-capable. bulb: offline (as in reality).
TEST_CONFIG = {
    "ceiling": {"id": "ceiling-id", "ip": "0.0.0.0", "key": "k", "version": "3.3"},
    "bulb": {"id": "bulb-id", "ip": "0.0.0.0", "key": "k", "version": "3.3", "_offline": True},
}


def _device_id(name):
    return TEST_CONFIG[name]["id"]


@pytest.fixture(scope="session")
def base_url():
    import lamp
    lamp.load_config = lambda: TEST_CONFIG          # serve the test devices
    lamp.make_device = fake_lamp.make_device        # ...backed by the fake

    import status
    status.POLL_INTERVAL = 0.2                       # fast pushes for snappy tests

    import wakeup
    wakeup.start = lambda: None                      # no wake-up scheduler under test

    from werkzeug.serving import make_server

    import app as app_module  # importing starts the SSE poller
    server = make_server("127.0.0.1", 0, app_module.app, threaded=True)
    port = server.socket.getsockname()[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{port}"
    for _ in range(50):                              # wait until it answers
        try:
            urllib.request.urlopen(url + "/", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield url
    server.shutdown()


class FakeAccess:
    """Lets a test read/mutate the faked devices by friendly name."""

    def dev(self, name):
        return fake_lamp.get(_device_id(name))


@pytest.fixture(autouse=True)
def fake(base_url):
    """Reset every device to a known baseline before each test."""
    fake_lamp.reset()
    fake_lamp.make_device(TEST_CONFIG["ceiling"])   # online, off, white
    fake_lamp.make_device(TEST_CONFIG["bulb"])      # offline
    import status
    status.poke()                                    # publish the baseline promptly
    return FakeAccess()
