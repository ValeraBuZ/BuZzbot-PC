"""One leader creates a rally, one verified account joins, then return home."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import logging
import threading
import time

import cv2
import numpy as np

from buzzbot.matching import _reference_frame
from buzzbot.ldplayer import index_from_serial
from buzzbot.state import BotState

logger = logging.getLogger("BuZzbot")
ASSETS = Path(__file__).parent / "assets/own_rally"


def locate_asset(frame, name, region=None, confidence=0.84):
    reference, sx, sy = _reference_frame(frame)
    marker = cv2.imread(str(ASSETS / f"{name}.png"), cv2.IMREAD_GRAYSCALE)
    if reference is None or marker is None:
        return None
    x, y, w, h = region or (0, 0, 1280, 720)
    gray = cv2.cvtColor(reference[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
    if gray.shape[0] < marker.shape[0] or gray.shape[1] < marker.shape[1]:
        return None
    _, score, _, at = cv2.minMaxLoc(cv2.matchTemplate(gray, marker, cv2.TM_CCOEFF_NORMED))
    if score < confidence:
        return None
    return ((x+at[0]+marker.shape[1]/2)*sx, (y+at[1]+marker.shape[0]/2)*sy)


def same_text(first, second):
    if first.shape != second.shape or not first.size:
        return False
    a = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)
    # Compare foreground text; the alliance card background is animated.
    a = (a >= 195).astype(np.uint8) * 255
    b = (b >= 195).astype(np.uint8) * 255
    if np.std(a) < 8 or np.std(b) < 8:
        return False
    a = cv2.GaussianBlur(a, (3, 3), .7)
    b = cv2.GaussianBlur(b, (3, 3), .7)
    return float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)[0, 0]) >= 0.88


def same_coordinates(first, second):
    """Compare each printed coordinate character, not an average over the line."""
    def characters(crop):
        mask = (cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) >= 195).astype(np.uint8)*255
        mask[np.count_nonzero(mask, axis=1) > mask.shape[1]*.7] = 0  # Link underline.
        occupied = np.any(mask, axis=0)
        boundaries = np.diff(np.r_[False, occupied, False].astype(np.int8))
        parts = []
        for left, right in zip(np.where(boundaries == 1)[0], np.where(boundaries == -1)[0]):
            glyph = mask[:, left:right]
            rows = np.where(np.any(glyph, axis=1))[0]
            if len(rows) and np.count_nonzero(glyph) >= 3:
                parts.append(cv2.resize(glyph[rows[0]:rows[-1]+1], (20, 28)))
        return parts
    if first.shape != second.shape or not first.size:
        return False
    a, b = characters(first), characters(second)
    if len(a) < 6 or len(a) != len(b):
        return False
    return all(float(cv2.matchTemplate(cv2.GaussianBlur(x,(3,3),.7),
                                      cv2.GaussianBlur(y,(3,3),.7),
                                      cv2.TM_CCOEFF_NORMED)[0,0]) >= .85 for x,y in zip(a,b))


@dataclass
class RallyRow:
    name: np.ndarray
    target: np.ndarray
    top: int
    owned: bool
    preparing: bool

    def matches(self, other):
        return same_text(self.name, other.name) and same_coordinates(self.target, other.target)


def rally_rows(frame):
    reference, _sx, _sy = _reference_frame(frame)
    if reference is None or locate_asset(reference, "war_title", (430, 20, 410, 65)) is None:
        return []
    marker = cv2.imread(str(ASSETS / "collective_title.png"), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return []
    gray = cv2.cvtColor(reference[105:610, 660:1110], cv2.COLOR_BGR2GRAY)
    scores = cv2.matchTemplate(gray, marker, cv2.TM_CCOEFF_NORMED)
    rows = []
    for _ in range(4):
        _, score, _, at = cv2.minMaxLoc(scores)
        if score < 0.82:
            break
        top = at[1] + 105
        scores[max(0, at[1]-55):at[1]+55, :] = -1
        if top+148 > 625:
            continue
        rows.append(RallyRow(
            reference[top:top+31, 271:540].copy(),
            reference[top+94:top+122, 1018:1147].copy(), top,
            locate_asset(reference, "cancel_own", (350, top+70, 75, 65)) is not None,
            locate_asset(reference, "preparing", (340, top+112, 640, 45), confidence=0.80) is not None,
        ))
    return sorted(rows, key=lambda row: row.top)


def select_new_rally(before, after):
    fresh = [row for row in after if row.owned and row.preparing
             and not any(row.matches(old) for old in before)]
    return fresh[0] if len(fresh) == 1 else None


def participant_candidates(profiles, leader_id, participant_id="any"):
    leader = next((p for p in profiles if p["id"] == leader_id), None)
    if leader is None:
        return []
    leader_serial = leader.get("adb_serial")
    leader_serial_index = index_from_serial(leader_serial)
    def same_connection(profile):
        if profile.get("adb_serial") == leader_serial:
            return True
        # ADB recovery may adopt the TCP alias for just the active profile.
        # Both canonical aliases still identify the same LDPlayer instance.
        return (leader_serial_index is not None
                and leader_serial_index == leader.get("ldplayer_index")
                and index_from_serial(profile.get("adb_serial")) == leader_serial_index)
    return [p for p in profiles if p.get("enabled", True) and p["id"] != leader_id
            and (participant_id == "any" or p["id"] == participant_id)
            and p.get("ldplayer_index") == leader.get("ldplayer_index")
            and same_connection(p)]


def joining_squad_target(frame):
    """Recognise the one-button deployment prompt opened by joining a rally."""
    if locate_asset(frame, "deployment_title", (1125, 0, 155, 65)) is None:
        return None
    return locate_asset(frame, "create_squad", (850, 200, 240, 90))


def first_saved_squad_target(frame):
    if locate_asset(frame, "squad_title", (760, 15, 135, 50)) is None:
        return None
    return locate_asset(frame, "preset_one", (1060, 210, 70, 75))


def saved_squad_loaded(frame):
    return (first_saved_squad_target(frame) is not None
            and locate_asset(frame, "preset_loaded", (430, 90, 420, 100)) is not None)


class OwnRallyController:
    def __init__(self, settings):
        self.settings = dict(settings)
        self.cancel = threading.Event()
        self.rounds = 0
        self.participant_cursor = 0

    def check(self, bot):
        if self.cancel.is_set() or bot.stop_hotkey_pressed:
            raise InterruptedError("Режим своих сборов остановлен")

    def resume_worker(self, bot):
        self.check(bot)
        bot.stop_event.clear()
        bot._set_state(BotState.RUNNING)
        bot.account_switch_stop_message = ""

    def wait(self, bot, seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.check(bot)
            if self.cancel.wait(min(.3, max(0, until-time.monotonic()))):
                self.check(bot)
            while bot.is_paused:
                self.check(bot)
                self.cancel.wait(.2)

    def frame(self, bot):
        self.check(bot)
        while bot.is_paused:
            self.wait(bot, .2)
        bot._invalidate_capture()
        return bot._capture_screen_bgr(force=True)[0]

    def tap(self, bot, point):
        self.check(bot)
        while bot.is_paused:
            self.wait(bot, .2)
        if point is None:
            return False
        bot.adb_client.tap(round(point[0]), round(point[1]))
        self.wait(bot, .8)
        return True

    def wait_asset(self, bot, name, seconds=5, region=None):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            point = locate_asset(self.frame(bot), name, region)
            if point:
                return point
            self.wait(bot, .4)
        return None

    def select_first_saved_squad(self, bot, march):
        """Load preset 1 for either rally role and require the game's receipt."""
        frame = self.frame(bot)
        # A receipt left by an earlier manual selection cannot prove this tap.
        for _ in range(10):
            if not saved_squad_loaded(frame):
                break
            self.wait(bot, .3)
            frame = self.frame(bot)
        if saved_squad_loaded(frame):
            return None
        loaded = False
        for attempt in range(3):
            # Re-detect the button on the latest frame; never reuse coordinates
            # after a popup or a transition away from the squad panel.
            target = first_saved_squad_target(frame)
            if target is None:
                break
            bot.set_status_message(
                f"Свои сборы: загружаю сохранённый отряд №1 ({attempt+1}/3)", force=True)
            if not self.tap(bot, target):
                return None
            for _ in range(10):
                frame = self.frame(bot)
                if first_saved_squad_target(frame) is None:
                    break
                loaded = loaded or saved_squad_loaded(frame)
                if loaded:
                    location, bbox, _score = bot._locate_image(march)
                    if (location is not None and bbox is not None
                            and bot._validate_detected_match(march, bbox)[0]):
                        logger.info("Own rally saved squad 1 loaded and ready on account %s", bot.current_account_id)
                        return location
                self.wait(bot, .3)
            if loaded:
                break  # Receipt confirmed; a missing march button needs recovery.
            # Include a fresh frame after the final wait, so a late receipt is
            # not mistaken for a missed tap and clicked over by the retry.
            frame = self.frame(bot)
            if saved_squad_loaded(frame):
                location, bbox, _score = bot._locate_image(march)
                if (location is not None and bbox is not None
                        and bot._validate_detected_match(march, bbox)[0]):
                    logger.info("Own rally saved squad 1 loaded and ready on account %s", bot.current_account_id)
                    return location
                break
        bot._save_routine_calibration_frame('own_rally', 'preset_unavailable', frame)
        return None

    def open_war(self, bot):
        self.check(bot)
        if not bot._return_to_main_screen(max_back_steps=7):
            return False
        def tap_icon(name, region, offset):
            point = self.wait_asset(bot, name, region=region)
            if point is None:
                return False
            scale = self.frame(bot).shape[0]/720
            return self.tap(bot, (point[0], point[1]-offset*scale))
        if not tap_icon("alliance_button", (880, 590, 190, 125), 40):
            return False
        if not self.wait_asset(bot, "alliance_title", region=(80, 10, 230, 80)):
            return False
        if not tap_icon("military_button", (570, 330, 190, 205), 48):
            return False
        return self.wait_asset(bot, "war_title", region=(430, 20, 410, 65)) is not None

    def switch(self, bot, profile):
        self.resume_worker(bot)
        bot._own_rally_task = None
        bot.routine_last_outcome = {}
        verify_only = bool(bot.current_account_id == profile['id'] and profile.get('verified_igg_id')
                           and bot._return_to_main_screen(max_back_steps=7))
        if not bot._prepare_account_switch(profile, verify_only=verify_only):
            raise RuntimeError(bot.status_message)
        bot.account_switch_task["settings"]["_stop_after_verification"] = True
        if verify_only:
            bot.account_switch_task['settings']['_verify_only'] = True
            bot.account_switch_selected_at = time.time()
        bot.account_switch_failure_count = 1
        bot.save_config()
        bot.routine_mode = True
        bot.routine_next_run["__account_switch__"] = 0
        bot._run_clicker_loop()
        self.check(bot)
        if bot.current_account_id != profile["id"] or not bot.account_switch_confirmed or bot.account_switch_error:
            raise RuntimeError(bot.account_switch_error or "IGG участника не подтверждён")
        self.resume_worker(bot)

    def create(self, bot):
        self.resume_worker(bot)
        if not self.open_war(bot):
            return None, 0
        before = rally_rows(self.frame(bot))
        if not bot._return_to_main_screen(max_back_steps=7):
            return None, 0
        source = next(t for t in bot.routine_tasks if t["id"] == "collective_mind")
        bot._own_rally_task = deepcopy(source)
        bot._own_rally_task["enabled"] = True
        bot.routine_only_task_id = "collective_mind"
        bot.routine_mode = True
        bot.current_routine_task_id = None
        bot.current_routine_index = 0
        bot.routine_pass_completed = False
        bot.routine_next_run["collective_mind"] = 0
        bot.routine_last_outcome = {}
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot._run_clicker_loop()
        self.check(bot)
        result = bot.routine_last_outcome
        bot._own_rally_task = None
        self.resume_worker(bot)
        if result.get("outcome") != "completed" or "march" not in result.get("completed_steps", []):
            return None, 0
        created_at = time.time()
        if not self.open_war(bot):
            return None, created_at
        frame = self.frame(bot)
        bot._save_routine_calibration_frame('own_rally', 'created', frame)
        return select_new_rally(before, rally_rows(frame)), created_at

    def join(self, bot, identity, created_at):
        # Allow time for the squad selection and network confirmation.
        if time.time() >= created_at + 270 or not self.open_war(bot):
            return False
        for _page in range(5):
            if time.time() >= created_at + 270:
                return False
            frame = self.frame(bot)
            if _page == 0:
                bot._save_routine_calibration_frame('own_rally', 'participant', frame)
            rows = rally_rows(frame)
            logger.info('Own rally candidates page=%s identities=%s', _page,
                        [(r.top, same_text(r.name, identity.name), same_coordinates(r.target, identity.target), r.preparing) for r in rows])
            matches = [r for r in rows if r.matches(identity) and r.preparing]
            if len(matches) == 1:
                row = matches[0]
                _ref, sx, sy = _reference_frame(frame)
                if not self.tap(bot, (640*sx, (row.top+65)*sy)):
                    return False
                return self.send_joining_squad(bot, created_at)
            if len(matches) > 1:
                return False
            if locate_asset(frame, "war_title") is None:
                return False
            height, width = frame.shape[:2]
            bot.adb_client.swipe(round(width*.55), round(height*.78), round(width*.55), round(height*.38), 350)
            self.wait(bot, .6)
        return False

    def send_joining_squad(self, bot, created_at):
        join_point = self.wait_asset(bot, "join_button", seconds=5)
        if time.time() >= created_at+280 or not self.tap(bot, join_point):
            return False
        march = next((i for i in bot.search_images if i.get("runtime_step") == "march"
                      and i.get("group") == "Коллективный разум"), None)
        if march is None:
            return False
        bot._own_rally_task = deepcopy(next(t for t in bot.routine_tasks if t["id"] == "collective_mind"))
        bot._own_rally_task["enabled"] = True
        bot.current_routine_task_id = "collective_mind"
        try:
            create_attempts = 0
            for _ in range(20):
                self.check(bot)
                frame = self.frame(bot)
                create_point = joining_squad_target(frame)
                if create_point is not None:
                    if create_attempts >= 2 or time.time() >= created_at+280:
                        return False
                    bot.set_status_message("Свои сборы: создаю отряд для вступления", force=True)
                    if not self.tap(bot, create_point):
                        return False
                    create_attempts += 1
                    self.wait(bot, 1)
                    continue
                location, bbox, _score = bot._locate_image(march)
                if location is not None and bbox is not None:
                    if time.time() >= created_at+285:
                        return False
                    sent = bot._execute_action(march, location)
                    if sent:
                        bot._register_routine_march(bot._own_rally_task, time.time())
                    return bool(sent)
                self.wait(bot, .5)
            bot._save_routine_calibration_frame('own_rally', 'join_unavailable', self.frame(bot))
            logger.warning("Own rally joining squad was not ready for dispatch")
            return False
        finally:
            bot._own_rally_task = None
            bot.current_routine_task_id = None

    def run(self, bot):
        leader_id = self.settings["leader_id"]
        try:
            leader = next(p for p in bot.account_profiles if p["id"] == leader_id)
            # Explicit mode switches always verify the account, even when
            # ordinary automatic rotation is disabled.
            self.switch(bot, leader)
            failures = 0
            while True:
                self.check(bot)
                choices = [p for p in participant_candidates(bot.account_profiles, leader_id,
                           self.settings.get("participant_id", "any"))
                           if p.get("auto_login") and bot.account_has_saved_login(p["id"])
                           and bot.account_has_saved_password(p["id"])]
                if not choices:
                    raise RuntimeError("Нет доступного аккаунта для вступления")
                participant = choices[self.participant_cursor % len(choices)]
                self.participant_cursor += 1
                bot.set_status_message("Свои сборы: создаю сбор на основном аккаунте", force=True)
                identity, created_at = self.create(bot)
                if identity is None:
                    outcome = getattr(bot, 'routine_last_outcome', {})
                    if str(outcome.get('reason', '')).startswith('цель уже занята'):
                        bot.set_status_message("Свои сборы: цель занята, ищу на уровень ниже", force=True)
                        self.wait(bot, max(5, bot.routine_next_run.get('collective_mind', 0)-time.time()))
                        continue
                    reason = str(outcome.get('reason', ''))
                    if reason.startswith('сохранённый отряд №1 не загружен'):
                        # The saved heroes/troops may still be on a march. A
                        # unavailable preset is not evidence of a broken rally.
                        failures = 0
                        delay = max(30, bot.routine_next_run.get('collective_mind', 0)-time.time())
                        bot.set_status_message(
                            f"Свои сборы: отряд №1 пока не загружен; повтор через {int(delay)} сек",
                            force=True)
                        self.wait(bot, delay)
                        continue
                    if reason.startswith(('коллективный разум доступных уровней не найден',
                                          'коллективный разум: повторное открытие поиска')):
                        bot.set_status_message(f"Свои сборы: {reason}; ожидаю повторного поиска", force=True)
                        self.wait(bot, max(10, bot.routine_next_run.get('collective_mind', 0)-time.time()))
                        continue
                    failures += 1
                    if failures >= 3:
                        raise RuntimeError("Не удалось подтвердить свой сбор за 3 попытки; проверьте игру и альянс")
                    delay = max(30, created_at+305-time.time()) if created_at else 30
                    detail = "сбор не найден в альянсе" if created_at else (reason or "сбор не создан")
                    bot.set_status_message(f"Свои сборы: {detail}, повтор через {int(delay)} сек", force=True)
                    self.wait(bot, delay)
                    continue
                failures = 0
                self.switch(bot, participant)
                bot.set_status_message(f"Свои сборы: вступает {participant['name']}", force=True)
                joined = self.join(bot, identity, created_at)
                logger.info("Own rally participant %s joined=%s", participant["id"], joined)
                self.switch(bot, leader)
                self.rounds += 1
                bot.set_status_message(
                    f"Свои сборы: круг {self.rounds}, " + ("участник отправлен" if joined else "вступление недоступно"),
                    force=True,
                )
                if not self.settings.get("repeat", True):
                    return
                self.wait(bot, max(5, created_at+305-time.time()))
        except InterruptedError:
            bot.account_switch_stop_message = "Режим своих сборов остановлен"
        except Exception as exc:
            logger.exception("Own rally mode stopped")
            bot.account_switch_stop_message = f"Свои сборы: {exc}"
        finally:
            bot._own_rally_task = None
            bot.own_rally_controller = None
            bot.routine_only_task_id = None
            bot.current_routine_task_id = None
