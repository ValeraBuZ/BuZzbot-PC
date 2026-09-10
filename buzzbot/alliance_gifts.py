from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass, field

import cv2
import numpy as np

from buzzbot.matching import imread_unicode


def gift_profile_images():
    """Expose the bundled controls in exported training profiles."""
    import uuid
    from buzzbot.routines import PROFILE_NAMESPACE

    labels = {
        "alliance_title": "Экран альянса",
        "gift_entry": "Открыть подарки альянса",
        "activity_tab": "Награды за активность",
        "purchase_tab": "Награды за покупки",
        "activity_collect_all": "Общий сбор наград за активность",
        "claim": "Получить подарок за покупки",
        "claimed": "Получение подарка подтверждено",
        "reward_title": "Полученные награды",
        "reward_close": "Закрыть полученные награды",
        "empty_notice": "Нет подарков для получения",
    }
    images = []
    for name, label in labels.items():
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"alliance_gifts:{name}"))
        images.append({
            "uid": uid, "path": f"templates/{uid}.png", "asset_name": name,
            "action": "observe", "observer_only": True, "description": label,
            "group": "Подарки альянса", "enabled": True,
            "confidence": 0.88, "grayscale": True, "use_orb": False,
            "use_scaling": False, "delay": 1.0, "cooldown": 0.5,
            "click_offset": [0, 0], "click_sequence": [], "numbers": [], "last_used": 0,
        })
    return images


ASSET_DIR = Path(__file__).parent / "assets" / "alliance_gifts"


@lru_cache(maxsize=24)
def _template(name):
    return imread_unicode(ASSET_DIR / f"{name}.png", cv2.IMREAD_GRAYSCALE)


def _find(frame_bgr, name, bounds, threshold=0.88):
    if frame_bgr is None or getattr(frame_bgr, "ndim", 0) != 3 or not frame_bgr.size:
        return None
    height, width = frame_bgr.shape[:2]
    frame = cv2.resize(frame_bgr, (1280, 720))
    template = _template(name)
    if template is None:
        return None
    left, top, right, bottom = bounds
    search = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        return None
    _, score, _, location = cv2.minMaxLoc(cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED))
    if score < threshold:
        return None
    return (
        round((left + location[0] + template.shape[1] / 2) * width / 1280),
        round((top + location[1] + template.shape[0] / 2) * height / 720),
    )


def detect_alliance_gift_entry(frame_bgr):
    if _find(frame_bgr, "alliance_title", (70, 10, 320, 80)) is None:
        return None
    return _find(frame_bgr, "gift_entry", (1090, 510, 1260, 700))


def alliance_gifts_screen_is_visible(frame_bgr):
    return (
        _find(frame_bgr, "activity_tab", (640, 75, 940, 122)) is not None
        and _find(frame_bgr, "purchase_tab", (970, 75, 1250, 122)) is not None
    )


def detect_alliance_gift_claim(frame_bgr):
    if not alliance_gifts_screen_is_visible(frame_bgr):
        return None
    return _find(frame_bgr, "claim", (1040, 140, 1250, 630), threshold=0.92)


def detect_alliance_activity_collect_all(frame_bgr):
    if selected_gift_tab(frame_bgr) != "activity":
        return None
    return _find(frame_bgr, "activity_collect_all", (1070, 637, 1250, 700), threshold=0.94)


def selected_gift_tab(frame_bgr):
    if not alliance_gifts_screen_is_visible(frame_bgr):
        return None
    gray = cv2.cvtColor(cv2.resize(frame_bgr, (1280, 720)), cv2.COLOR_BGR2GRAY)
    activity = float(np.mean(gray[87:111, 658:925] > 180))
    purchase = float(np.mean(gray[87:111, 982:1230] > 180))
    if max(activity, purchase) < 0.08 or abs(activity - purchase) < 0.05:
        return None
    return "activity" if activity > purchase else "purchase"


def gift_notification_is_visible(frame_bgr, kind):
    frame = cv2.resize(frame_bgr, (1280, 720))
    left, right = (929, 963) if kind == "activity" else (1230, 1270)
    hsv = cv2.cvtColor(frame[73:108, left:right], cv2.COLOR_BGR2HSV)
    red = ((hsv[:, :, 0] < 8) | (hsv[:, :, 0] > 173)) & (hsv[:, :, 1] > 130) & (hsv[:, :, 2] > 120)
    return int(np.count_nonzero(red)) >= 30


def gift_claim_is_confirmed(frame_bgr, target):
    if not alliance_gifts_screen_is_visible(frame_bgr):
        return False
    height, width = frame_bgr.shape[:2]
    x, y = target[0] * 1280 / width, target[1] * 720 / height
    bounds = (max(1040, int(x - 90)), max(125, int(y - 55)), min(1250, int(x + 100)), min(634, int(y + 55)))
    return _find(frame_bgr, "claimed", bounds, threshold=0.85) is not None


def gift_reward_popup_is_visible(frame_bgr):
    return (
        _find(frame_bgr, "reward_title", (220, 105, 1060, 195)) is not None
        and _find(frame_bgr, "reward_close", (350, 555, 930, 625)) is not None
    )


def gift_empty_notice_is_visible(frame_bgr):
    return _find(frame_bgr, "empty_notice", (350, 110, 940, 185)) is not None


def gift_list_view(frame_bgr):
    frame = cv2.resize(frame_bgr, (1280, 720))
    return cv2.resize(cv2.cvtColor(frame[125:634, 645:1248], cv2.COLOR_BGR2GRAY), (160, 130))


def purchase_badge_digits(frame_bgr):
    frame = cv2.resize(frame_bgr, (1280, 720))
    return cv2.cvtColor(frame[76:101, 1230:1260], cv2.COLOR_BGR2GRAY) > 210


def shifted_gift_claim_is_confirmed(frame_bgr, previous_badge):
    # The game recentres lower cards after a tap. Its receipt can consequently
    # move away from the button's former position. Require both a changed
    # notification count and a visible receipt; a disappearing button alone
    # could instead be a navigation or loading transition.
    if previous_badge is None or selected_gift_tab(frame_bgr) != "purchase":
        return False
    changed = np.count_nonzero(previous_badge != purchase_badge_digits(frame_bgr)) >= 8
    return bool(changed and _find(frame_bgr, "claimed", (1130, 125, 1250, 634), threshold=0.85) is not None)


@dataclass(frozen=True)
class GiftAction:
    kind: str
    target: tuple | None = None
    message: str = ""


@dataclass
class AllianceGiftFlow:
    settings: dict
    started_at: float
    done: set = field(default_factory=set)
    purchase_count: int = 0
    activity_result: str = "disabled"
    pending: GiftAction | None = None
    pending_at: float = 0.0
    last_action_at: float = 0.0
    last_scroll: object = None
    stable_scrolls: int = 0
    scrolls: int = 0
    action_number: int = 0
    pending_badge: object = None
    navigation_attempts: dict = field(default_factory=dict)
    scroll_direction: str = "down"

    def navigation_action(self, target, message):
        if target is None or self.navigation_attempts.get(target, 0) >= 3:
            return GiftAction("unavailable", message="переход к подаркам не подтверждён")
        return GiftAction("tap", target, message)

    def record(self, action, frame, now):
        self.action_number += 1
        self.last_action_at = now
        if action.kind in {"claim", "collect_all"}:
            self.pending = action
            self.pending_at = now
            self.pending_badge = purchase_badge_digits(frame) if action.kind == "claim" else None
        elif action.kind == "tap":
            self.navigation_attempts[action.target] = self.navigation_attempts.get(action.target, 0) + 1
        elif action.kind == "dismiss":
            self.pending = None
            self.done.add("activity")
            self.activity_result = "collected_all"
        elif action.kind == "swipe":
            self.last_scroll = gift_list_view(frame)
            self.scrolls += 1

    def next_action(self, frame, now):
        if now - self.started_at > 900:
            return GiftAction("unavailable", message="превышено время сбора подарков")
        if now - self.last_action_at < 1.0:
            return GiftAction("wait")
        selected = selected_gift_tab(frame)
        if self.pending is not None:
            if self.pending.kind == "collect_all":
                if gift_reward_popup_is_visible(frame):
                    height, width = frame.shape[:2]
                    return GiftAction("dismiss", (width // 2, round(height * 645 / 720)), "Подарки: закрываю полученные награды")
                if selected == "activity" and (
                    gift_empty_notice_is_visible(frame)
                    or (not gift_notification_is_visible(frame, "activity") and detect_alliance_gift_claim(frame) is None)
                ):
                    self.done.add("activity")
                    self.activity_result = "empty"
                    self.pending = None
                    return GiftAction("wait")
            elif selected == "purchase" and (
                gift_claim_is_confirmed(frame, self.pending.target)
                or shifted_gift_claim_is_confirmed(frame, self.pending_badge)
            ):
                self.purchase_count += 1
                self.pending = None
                return GiftAction("wait")
            if now - self.pending_at > 6:
                return GiftAction("unavailable", message="получение подарка не подтверждено")
            return GiftAction("wait")

        kinds = [kind for kind in ("activity", "purchase") if self.settings.get(f"collect_{kind}", True)]
        desired = next((kind for kind in kinds if kind not in self.done), None)
        if desired is None:
            return GiftAction("complete")
        entry = detect_alliance_gift_entry(frame)
        if entry is not None:
            return self.navigation_action(entry, "Альянс: открываю подарки")
        if selected is None:
            if now - max(self.started_at, self.last_action_at) > 6:
                return GiftAction("unavailable", message="экран подарков не распознан")
            return GiftAction("wait")
        if selected != desired:
            bounds = (640, 75, 940, 122) if desired == "activity" else (970, 75, 1250, 122)
            target = _find(frame, f"{desired}_tab", bounds)
            label = "активность" if desired == "activity" else "покупки"
            return self.navigation_action(target, f"Подарки: награды за {label}")
        if desired == "activity":
            target = detect_alliance_activity_collect_all(frame)
            if target is None:
                return GiftAction("unavailable", message="кнопка общего сбора активности не распознана")
            return GiftAction("collect_all", target, "Подарки: собираю все награды за активность")

        if self.last_scroll is not None:
            difference = float(np.mean(cv2.absdiff(self.last_scroll, gift_list_view(frame))))
            self.stable_scrolls = self.stable_scrolls + 1 if difference < 2.0 else 0
            self.last_scroll = None
        claim = detect_alliance_gift_claim(frame)
        if claim is not None:
            if self.purchase_count >= 500:
                return GiftAction("unavailable", message="достигнут предел 500 подарков за проход")
            self.stable_scrolls = 0
            return GiftAction("claim", claim, "Подарки: получаю награду за покупки")
        if not gift_notification_is_visible(frame, "purchase"):
            self.done.add("purchase")
            return GiftAction("wait")
        if self.stable_scrolls >= 2 and self.scroll_direction == "down":
            # Claiming a lower card can move the list past gifts above it.
            # Sweep back to the top before deciding that the count is stale.
            self.scroll_direction = "up"
            self.stable_scrolls = 0
            self.scrolls = 0
        elif self.stable_scrolls >= 2 or self.scrolls >= 100:
            return GiftAction("unavailable", message="оставшиеся подарки недоступны для получения")
        height, width = frame.shape[:2]
        y1, y2 = (560, 260) if self.scroll_direction == "down" else (260, 560)
        return GiftAction("swipe", (round(width * 960 / 1280), round(height * y1 / 720), round(width * 960 / 1280), round(height * y2 / 720)), "Подарки: проверяю следующую страницу")
