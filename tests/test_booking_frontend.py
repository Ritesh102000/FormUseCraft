# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Small contract checks for the public native-booking interface."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORM_JS = (ROOT / "web/static/form.js").read_text()
FORM_TEMPLATE = (ROOT / "web/templates/form.html").read_text()
FORM_CSS = (ROOT / "web/static/css/form.css").read_text()


def test_slot_loading_failure_keeps_an_in_place_retry_control():
    assert 'id="retry-booking-slots"' in FORM_TEMPLATE
    assert "retryBookingSlotsBtn?.addEventListener('click'" in FORM_JS
    assert "loadNativeBookingSlots()" in FORM_JS
    assert "Your form response is saved. Meeting times could not load." in FORM_JS


def test_booking_confirmation_has_all_three_sheet_states():
    assert "no Google Sheet is connected to this form" in FORM_JS
    assert "Google Sheet was updated" in FORM_JS
    assert "Google Sheet update did not finish" in FORM_JS
    assert "Retry Sheet update" in FORM_JS
    assert "will retry automatically" not in FORM_JS


def test_booking_conflict_refreshes_slots_without_falling_through_to_stale_state():
    conflict_start = FORM_JS.index("if (res.status === 409)")
    conflict_end = FORM_JS.index("throw new Error", conflict_start)
    conflict_branch = FORM_JS[conflict_start:conflict_end]

    assert "await loadNativeBookingSlots" in conflict_branch
    assert "return;" in conflict_branch


def test_native_booking_is_date_first_and_only_renders_one_days_times():
    assert "data-booking-calendar-grid" in FORM_JS
    assert "data-booking-time-list" in FORM_JS
    assert "groupBookingSlots" in FORM_JS
    assert "daySlots.forEach((slot)" in FORM_JS
    assert "data.slots.forEach((slot)" not in FORM_JS
    assert "native-booking__picker" in FORM_CSS
    assert "grid-template-columns: repeat(7" in FORM_CSS
    assert "container: native-booking / inline-size" in FORM_CSS
    assert "@container native-booking (max-width: 620px)" in FORM_CSS


def test_native_booking_exposes_selection_and_bounded_loading_states():
    assert 'aria-busy="true"' in FORM_TEMPLATE
    assert 'id="booking-selection"' in FORM_TEMPLATE
    assert "setAttribute('aria-pressed'" in FORM_JS
    assert "BOOKING_LOAD_TIMEOUT_MS" in FORM_JS
    assert "Availability is taking longer than expected" in FORM_JS
    assert 'id="native-booking-slots" aria-live=' not in FORM_TEMPLATE
    assert "bookingScheduleLabel(data.schedule)" in FORM_JS
    assert "Last meeting starts at" in FORM_JS
    assert "selected. Choose a meeting time." in FORM_JS
    assert " (next day)" in FORM_JS
    assert "max-height: 420px" in FORM_CSS
    assert "renderBookingTimes();\n  if (bookingSelectionText)" not in FORM_JS


def test_vercel_config_revalidates_static_assets():
    config = json.loads((ROOT / "vercel.json").read_text())
    static = next(item for item in config["headers"] if item["source"] == "/static/(.*)")
    assert static["headers"] == [
        {"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}
    ]
