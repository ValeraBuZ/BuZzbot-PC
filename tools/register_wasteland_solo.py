from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import sys
import time

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault(
    "BUZZBOT_RUNTIME_DIR",
    str((PROJECT_ROOT / "dist" / "BuZzbotPortable").resolve()),
)

from buzzbot.adb import AdbClient
from buzzbot_app import AutoClicker, logger


GAME_PACKAGE = "com.igg.android.doomsdaylastsurvivors"
DEFAULT_ACCOUNT_IDS = ("zzub1", "igg_3", "igg_4", "igg_5", "igg_6", "igg_7")
PROTECTED_ACCOUNT_IDS = {"buzz"}
EVENT_TEMPLATE = PROJECT_ROOT / "tools" / "assets" / "wasteland_event_entry.png"
REGISTERED_TEMPLATE = PROJECT_ROOT / "tools" / "assets" / "wasteland_registered_status.png"
TEAM_NAME_DIALOG_TEMPLATE = PROJECT_ROOT / "tools" / "assets" / "wasteland_team_name_dialog.png"
TEAM_CREATED_TEMPLATE = PROJECT_ROOT / "tools" / "assets" / "wasteland_team_created.png"


def _safe_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", str(value or ""))
    return cleaned[:14] or "Account"


def _capture(client, path):
    frame = client.screenshot_bgr()
    if not cv2.imwrite(str(path), frame):
        raise OSError(f"Could not save screenshot: {path}")
    return frame


def _scaled_point(frame, x, y):
    height, width = frame.shape[:2]
    return int(round(x * width / 1280.0)), int(round(y * height / 720.0))


def _tap(client, frame, x, y):
    client.tap(*_scaled_point(frame, x, y))


def _team_button_visible(frame):
    height, width = frame.shape[:2]
    x1, y1 = _scaled_point(frame, 450, 570)
    x2, y2 = _scaled_point(frame, 830, 670)
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array((5, 100, 130)), np.array((40, 255, 255)))
    return int(cv2.countNonZero(mask)) >= max(250, int(roi.shape[0] * roi.shape[1] * 0.12))


def _template_visible(frame, template_path, threshold):
    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None or frame is None:
        return False
    if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
        return False
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(result)[1]) >= float(threshold)


def _team_name_dialog_visible(frame):
    return _template_visible(frame, TEAM_NAME_DIALOG_TEMPLATE, 0.72)


def _team_created_visible(frame):
    return _template_visible(frame, TEAM_CREATED_TEMPLATE, 0.72)


def _registration_phase_selected(frame):
    """Return whether the event is currently on its registration phase."""
    if frame is None:
        return False
    reference = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(reference, cv2.COLOR_BGR2HSV)

    def orange_fraction(y1, y2):
        roi = hsv[y1:y2, 35:300]
        orange = (
            (roi[:, :, 0] >= 5)
            & (roi[:, :, 0] <= 35)
            & (roi[:, :, 1] >= 90)
            & (roi[:, :, 2] >= 110)
        )
        return float(np.mean(orange))

    registration = orange_fraction(130, 230)
    active_event = orange_fraction(230, 330)
    return registration >= 0.08 and registration > active_event * 2.0


def _event_target(frame):
    template = cv2.imread(str(EVENT_TEMPLATE), cv2.IMREAD_COLOR)
    if template is None or frame is None:
        return None
    if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
        return None
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    _minimum, score, _minimum_location, location = cv2.minMaxLoc(result)
    if float(score) < 0.78:
        return None
    return (
        location[0] + template.shape[1] // 2,
        location[1] + template.shape[0] // 2,
    )


def _registered_status_visible(frame):
    template = cv2.imread(str(REGISTERED_TEMPLATE), cv2.IMREAD_COLOR)
    if template is None or frame is None:
        return False
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(result)[1]) >= 0.72


def _pin_serial(bot, serial):
    if bot.adb_serial == serial and bot.adb_client and bot.adb_client.serial == serial:
        return
    bot.adb_serial = serial
    bot._refresh_adb_client()


def _wait_for_main_screen(bot, serial, timeout_seconds=360.0):
    _pin_serial(bot, serial)
    deadline = time.time() + float(timeout_seconds)
    while time.time() < deadline:
        if bot._is_main_screen_visible():
            return True
        time.sleep(1.0)
    return False


def _switch_account(bot, account_id, timeout_seconds=300.0):
    if not bot.start_account_switch(account_id):
        return False, bot.status_message
    deadline = time.time() + float(timeout_seconds)
    while time.time() < deadline and bot.is_running:
        time.sleep(0.5)
    if bot.is_running:
        bot.stop()
    if bot._thread:
        bot._thread.join(timeout=5.0)
    success = bool(bot.account_switch_confirmed and not bot.account_switch_error)
    return success, bot.account_switch_error or bot.account_switch_last_result or bot.status_message


def _open_wasteland_registration(client, output_dir, label):
    frame = client.screenshot_bgr()
    # Event order differs by account, so locate its visual card instead of using
    # a fixed position. Toggle the event drawer once when the card is hidden.
    for attempt in range(3):
        target = _event_target(frame)
        if target is None:
            if attempt >= 1:
                break
            _tap(client, frame, 463, 78)
            time.sleep(1.5)
            frame = client.screenshot_bgr()
            continue
        client.tap(*target)
        time.sleep(3.0)
        frame = _capture(client, output_dir / f"{label}_event_{attempt + 1}.png")
        if not _registration_phase_selected(frame):
            return frame, "registration_closed"
        if _team_button_visible(frame):
            return frame, "create"
        client.keyevent(4)
        time.sleep(1.0)
        frame = client.screenshot_bgr()
    return None, "missing"


def _create_solo_team(client, output_dir, account_name):
    label = _safe_name(account_name)
    frame, state = _open_wasteland_registration(client, output_dir, label)
    if state == "registration_closed":
        client.keyevent(4)
        time.sleep(1.0)
        return False, "registration phase is closed"
    if frame is None:
        return False, "registration prompt was not detected"

    # The registered commander row is alliance-wide. Only the large Team
    # button opens the current account's create/join flow.
    _tap(client, frame, 640, 617)
    time.sleep(2.0)
    frame = _capture(client, output_dir / f"{label}_name_dialog.png")
    if not _team_name_dialog_visible(frame):
        client.keyevent(4)
        time.sleep(1.0)
        return False, "team name dialog was not confirmed"
    _tap(client, frame, 680, 313)
    time.sleep(0.7)
    team_name = f"Solo{label}"[:20]
    client.clear_focused_text(32)
    client.input_text(team_name)
    time.sleep(0.7)
    focused = client.focused_edit_text_value()
    if focused is not None and focused != team_name:
        client.clear_focused_text(32)
        client.input_text(team_name)
        time.sleep(0.7)
        focused = client.focused_edit_text_value()
    if focused is not None and focused != team_name:
        return False, "team name input was not confirmed"

    frame = client.screenshot_bgr()
    _tap(client, frame, 1198, 670)
    time.sleep(0.7)
    frame = client.screenshot_bgr()
    _tap(client, frame, 785, 480)
    time.sleep(5.0)
    success_frame = _capture(client, output_dir / f"{label}_registered.png")
    if not _team_created_visible(success_frame):
        return False, "solo team creation was not confirmed"
    # Keep the proof screenshot, then close the confirmation before switching.
    _tap(client, success_frame, 640, 464)
    time.sleep(1.5)
    client.keyevent(4)
    time.sleep(1.5)
    return True, "solo team created"


def main():
    parser = argparse.ArgumentParser(description="Register local IGG profiles for Wasteland Exploration")
    parser.add_argument("--serial", default="127.0.0.1:5565")
    parser.add_argument("--accounts", default=",".join(DEFAULT_ACCOUNT_IDS))
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--wait-until-open",
        action="store_true",
        help="Keep retrying unfinished accounts until the next registration phase opens",
    )
    parser.add_argument("--poll-seconds", type=float, default=3600.0)
    parser.add_argument("--max-wait-hours", type=float, default=168.0)
    args = parser.parse_args()

    account_ids = [item.strip() for item in args.accounts.split(",") if item.strip()]
    if any(account_id.casefold() in PROTECTED_ACCOUNT_IDS for account_id in account_ids):
        parser.error("The protected BuZz profile cannot be registered by this tool")
    if args.poll_seconds < 60.0:
        parser.error("--poll-seconds must be at least 60")
    if args.max_wait_hours <= 0:
        parser.error("--max-wait-hours must be positive")

    output_dir = args.output or PROJECT_ROOT / "test_runs" / f"wasteland_registration_{datetime.now():%Y%m%d_%H%M%S}"
    output_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(output_dir / "registration.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    results_by_account = {}
    pending = list(account_ids)
    wait_deadline = time.time() + args.max_wait_hours * 3600.0
    bot = AutoClicker(root=None)
    bot.stop_schedule_thread()
    bot.save_config = lambda: None
    bot.minimize_on_start = False
    bot.input_backend = "adb"
    bot.adb_serial = args.serial
    bot.account_rotation_enabled = False
    bot._refresh_adb_client()
    client = AdbClient(bot.adb_path or None, args.serial)
    # Account profiles describe where they are normally used. This maintenance
    # pass intentionally switches every profile inside one known emulator.
    for profile in bot.account_profiles:
        profile["adb_serial"] = args.serial
        profile["ldplayer_index"] = 5

    try:
        while pending:
            registration_closed = False
            for account_id in list(pending):
                profile = next(
                    (item for item in bot.account_profiles if item.get("id") == account_id),
                    None,
                )
                result = {
                    "account_id": account_id,
                    "name": profile.get("name") if profile else account_id,
                    "attempted_at": datetime.now().astimezone().isoformat(),
                }
                results_by_account[account_id] = result
                if profile is None or profile.get("login_method") != "igg":
                    result.update(ok=False, detail="profile is missing or is not IGG")
                else:
                    switched, detail = _switch_account(bot, account_id)
                    _pin_serial(bot, args.serial)
                    result["switch"] = detail
                    if not switched or not _wait_for_main_screen(bot, args.serial, 90.0):
                        result.update(
                            ok=False,
                            detail="account switch did not reach the main screen",
                        )
                    else:
                        ok, detail = _create_solo_team(
                            client,
                            output_dir,
                            profile.get("name") or account_id,
                        )
                        result.update(ok=ok, detail=detail)
                        if ok:
                            pending.remove(account_id)
                        elif detail == "registration phase is closed":
                            registration_closed = True

                ordered_results = [
                    results_by_account[item]
                    for item in account_ids
                    if item in results_by_account
                ]
                (output_dir / "summary.json").write_text(
                    json.dumps(ordered_results, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if registration_closed:
                    break

            if not pending or not args.wait_until_open:
                break
            if time.time() >= wait_deadline:
                logger.warning(
                    "Wasteland registration wait expired with pending accounts: %s",
                    ", ".join(pending),
                )
                break
            wait_seconds = min(float(args.poll_seconds), max(0.0, wait_deadline - time.time()))
            logger.info(
                "Wasteland registration is not open; retrying %s in %.0f seconds",
                ", ".join(pending),
                wait_seconds,
            )
            time.sleep(wait_seconds)
    finally:
        bot.stop()
        if bot._thread:
            bot._thread.join(timeout=5.0)
        bot.stop_schedule_thread()
        logger.removeHandler(handler)
        handler.close()
        results = [
            results_by_account[item]
            for item in account_ids
            if item in results_by_account
        ]
        (output_dir / "summary.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    results = [
        results_by_account[item]
        for item in account_ids
        if item in results_by_account
    ]
    print(output_dir)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results and all(item.get("ok") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
