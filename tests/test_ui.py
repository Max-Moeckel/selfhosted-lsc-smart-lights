"""Playwright UI regression tests, run against the real app with a faked lamp.

Each test guards a bug we actually hit:
  * power state shows correctly (the DP-20 / updatedps fix)
  * status is pushed over SSE without polling
  * profile buttons apply and stay highlighted
  * a focused button's own click updates its card (focus-guard regression)
  * a card isn't rebuilt when only another card changes (per-card diff)
"""

import re

from playwright.sync_api import expect


def card(page, name):
    return page.locator(f'[data-name="{name}"]')


def badge(page, name):
    return card(page, name).locator(".badge")


def profile_btn(page, name, label):
    return card(page, name).get_by_role("button", name=label, exact=True)


def open_ui(page, base_url):
    page.goto(base_url)
    expect(card(page, "ceiling")).to_be_visible()
    return page


def test_devices_render(page, base_url, fake):
    open_ui(page, base_url)
    # ceiling online and off at baseline; bulb offline
    expect(badge(page, "ceiling")).to_have_text("aus")
    expect(badge(page, "bulb")).to_have_text("offline")


def test_power_toggle_updates_badge_and_device(page, base_url, fake):
    open_ui(page, base_url)
    # the badge itself is the power toggle
    expect(badge(page, "ceiling")).to_have_text("aus")

    badge(page, "ceiling").click()
    expect(badge(page, "ceiling")).to_have_text("an")
    assert fake.dev("ceiling")._power is True

    badge(page, "ceiling").click()
    expect(badge(page, "ceiling")).to_have_text("aus")
    assert fake.dev("ceiling")._power is False


def test_external_change_is_pushed_over_sse(page, base_url, fake):
    # Guards the DP-20/updatedps fix AND the SSE push: turning the lamp on out-of-band
    # (no UI interaction) must reach the browser, and only does if get_dps() reveals
    # the hidden power DP and the server streams the change.
    open_ui(page, base_url)
    expect(badge(page, "ceiling")).to_have_text("aus")

    fake.dev("ceiling").turn_on()                   # external change, no click

    expect(badge(page, "ceiling")).to_have_text("an")


def test_profile_applies_and_stays_highlighted(page, base_url, fake):
    open_ui(page, base_url)

    profile_btn(page, "ceiling", "Arbeiten").click()
    expect(profile_btn(page, "ceiling", "Arbeiten")).to_have_class(re.compile(r"btn-primary"))

    # the command actually drove the lamp (working = bright 100 / temp 100)
    dps = fake.dev("ceiling")._dps
    assert dps["22"] == 1000 and dps["23"] == 1000

    # highlight survives the server reconcile push (match_profile re-confirms it)
    page.wait_for_timeout(800)
    expect(profile_btn(page, "ceiling", "Arbeiten")).to_have_class(re.compile(r"btn-primary"))


def test_focused_button_click_updates_its_card(page, base_url, fake):
    # Regression: clicking a button focuses it; the re-render guard must not suppress
    # the optimistic highlight on the very card the click lives in.
    open_ui(page, base_url)

    profile_btn(page, "ceiling", "Lesen").click()
    expect(profile_btn(page, "ceiling", "Lesen")).to_have_class(re.compile(r"btn-primary"))
    expect(badge(page, "ceiling")).to_have_text("an")


def test_ceiling_card_not_rebuilt_when_only_bulb_changes(page, base_url, fake):
    # Per-card diff: a status push that only changes the bulb must not rebuild (and
    # so detach the buttons of) the unchanged ceiling card.
    open_ui(page, base_url)
    expect(badge(page, "ceiling")).to_have_text("aus")

    mark = """() => {
      const c = document.querySelector('[data-name="ceiling"]');
      const b = [...c.querySelectorAll('button')].find(x => x.textContent.trim() === 'Arbeiten');
      b.dataset.marker = 'keep';
    }"""
    page.evaluate(mark)

    # bring the bulb online out-of-band → a push that changes only the bulb card
    fake.dev("bulb").online = True
    fake.dev("bulb").turn_on()
    expect(badge(page, "bulb")).to_have_text("an")

    read = """() => {
      const c = document.querySelector('[data-name="ceiling"]');
      const b = [...c.querySelectorAll('button')].find(x => x.textContent.trim() === 'Arbeiten');
      return b ? b.dataset.marker : null;
    }"""
    assert page.evaluate(read) == "keep"            # ceiling DOM survived → not rebuilt
