"""In-memory stand-in for a tinytuya BulbDevice, used by the UI tests.

It deliberately reproduces the real ceiling light's quirks so the tests guard the
fixes we made:

  * status() never includes the power DP 20 on its own — only after updatedps([20])
    is called does the *next* status() report it. A test that turns the lamp on and
    expects the UI to show "an" therefore only passes while get_dps() keeps doing the
    updatedps round-trip.
  * the light DPs (21-24) stay present even when the lamp is off, so on/off can't be
    inferred from their presence.

Devices live in a registry keyed by device id, so make_device() hands back the same
instance every poll and tests can mutate state directly.
"""

import colorsys

_registry = {}


class FakeBulb:
    def __init__(self, online=True, power=False, dps=None):
        self.online = online
        self._power = power
        self._dps = dps if dps is not None else {"21": "white", "22": 510, "23": 500}
        self._reveal_power = False  # status() exposes DP 20 only right after updatedps()

    # tinytuya socket tuning — no-ops here
    def set_socketTimeout(self, *_):
        pass

    def set_socketRetryLimit(self, *_):
        pass

    def set_socketPersistent(self, *_):
        pass

    def status(self):
        if not self.online:
            return {"Error": "offline"}
        dps = dict(self._dps)
        dps["41"] = True
        if self._reveal_power:           # one-shot, mirroring the device's stale cache
            dps["20"] = self._power
            self._reveal_power = False
        return {"dps": dps}

    def updatedps(self, index=None):
        self._reveal_power = True        # make the *next* status() include DP 20
        return True

    def turn_on(self):
        self._power = True

    def turn_off(self):
        self._power = False

    def set_value(self, dp, val):
        self._dps[str(dp)] = val
        if str(dp) in ("21", "22", "23", "24"):
            self._power = True           # setting a light DP powers the lamp on

    def set_colour(self, r, g, b):
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self._dps["21"] = "colour"
        self._dps["24"] = "%04x%04x%04x" % (int(h * 360), int(s * 1000), int(v * 1000))
        self._power = True


def make_device(cfg):
    """Drop-in for lamp.make_device: return the registry instance for this config."""
    key = cfg["id"]
    if key not in _registry:
        _registry[key] = FakeBulb(online=not cfg.get("_offline", False),
                                  power=cfg.get("_power", False),
                                  dps=dict(cfg["_dps"]) if cfg.get("_dps") else None)
    return _registry[key]


def get(dev_id):
    return _registry.get(dev_id)


def reset():
    _registry.clear()
