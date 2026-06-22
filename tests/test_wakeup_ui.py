"""E2E tests for the Wake-up panel in a real browser, driving the real Flask
routes (/api/wakeup, /api/wakeup/test) end to end against the faked lamp.
"""

from playwright.sync_api import expect

import wakeup


def card(page, name):
    return page.locator(f'[data-name="{name}"]')


def badge(page, name):
    return card(page, name).locator(".badge")


def test_panel_shows_saved_config(page, base_url, fake):
    wakeup.save({"enabled": True, "time": "06:30", "duration_min": 20,
                 "device": "ceiling", "days": [1, 3]})
    page.goto(base_url)
    expect(page.locator("#wu-time")).to_have_value("06:30")
    expect(page.locator("#wu-dur")).to_have_value("20")
    assert page.locator("#wu-enabled").is_checked()


def test_save_button_persists_through_the_api(page, base_url, fake):
    page.on("dialog", lambda d: d.accept())          # saveWakeup() pops an alert
    page.goto(base_url)
    expect(card(page, "ceiling")).to_be_visible()

    page.locator("#wu-enabled").check()
    page.locator("#wu-time").fill("05:45")
    page.get_by_role("button", name="Speichern").click()

    expect(page.locator("#wu-enabled")).to_be_checked()   # let the POST settle
    saved = wakeup.load()
    assert saved["enabled"] is True
    assert saved["time"] == "05:45"


def test_test_button_lights_a_lamp_that_was_off(page, base_url, fake):
    # headline E2E: ceiling is OFF at baseline; "30-Sek-Test" must turn it on,
    # and the change must reach the browser over SSE.
    page.on("dialog", lambda d: d.accept())
    page.goto(base_url)
    expect(badge(page, "ceiling")).to_have_text("aus")

    try:
        page.get_by_role("button", name="30-Sek-Test").click()
        expect(badge(page, "ceiling")).to_have_text("an")
        assert fake.dev("ceiling")._power is True
    finally:
        wakeup.cancel()                              # stop the 30 s ramp thread
