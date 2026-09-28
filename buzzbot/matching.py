from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import cv2
import numpy as np


REFERENCE_WIDTH = 1280
REFERENCE_HEIGHT = 720


def _reference_frame(frame_bgr):
    if frame_bgr is None or not isinstance(frame_bgr, np.ndarray) or frame_bgr.ndim != 3:
        return None, 1.0, 1.0
    height, width = frame_bgr.shape[:2]
    if width <= 0 or height <= 0:
        return None, 1.0, 1.0
    if (width, height) == (REFERENCE_WIDTH, REFERENCE_HEIGHT):
        return frame_bgr, 1.0, 1.0
    resized = cv2.resize(frame_bgr, (REFERENCE_WIDTH, REFERENCE_HEIGHT))
    return resized, width / REFERENCE_WIDTH, height / REFERENCE_HEIGHT


def settlement_region_button_is_visible(frame_bgr):
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None:
        return False
    marker = cv2.imread(str(Path(__file__).parent / "assets/navigation/region_label.png"), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return False
    region = cv2.cvtColor(frame[685:720, 10:125], cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(region, marker, cv2.TM_CCOEFF_NORMED).max()) >= 0.88


def detect_offline_resources_confirm_target(frame_bgr):
    """Recognise the resource report shown after login, including its button."""
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    directory = Path(__file__).parent / "assets/accounts"
    for filename, region in (
        ("offline_resources_label.png", gray[148:193, 510:920]),
        ("offline_resources_confirm.png", gray[616:674, 670:980]),
    ):
        marker = cv2.imread(str(directory / filename), cv2.IMREAD_GRAYSCALE)
        if marker is None or float(cv2.matchTemplate(region, marker, cv2.TM_CCOEFF_NORMED).max()) < 0.88:
            return None
    return round(824 * sx), round(644 * sy)


def detect_vehicle_barracks_target(frame_bgr):
    """Find the garage facade; its title and training form still need checking."""
    directory = Path(__file__).parent / "assets/training"
    for path in sorted(directory.glob("vehicle_barracks_*.png")):
        marker = cv2.imread(str(path))
        target, _inliers = detect_merchant_shop_feature_target(
            frame_bgr, marker, min_inliers=12, search_bounds=(95, 130, 1160, 585),
        )
        if target is not None:
            return target
    return None


def detect_fence_survivor_target(frame_bgr):
    """Find the green question marker despite camera zoom and moving scenery."""
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None:
        return None
    marker = cv2.imread(str(Path(__file__).parent / "assets/survivors/question.png"), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return None
    region = frame[150:610, 95:1245]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    best = (0.80, None)
    for scale in (0.65, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4):
        template = cv2.resize(marker, None, fx=scale, fy=scale)
        _low, score, _low_at, location = cv2.minMaxLoc(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED))
        if score <= best[0]:
            continue
        x, y = location
        h, w = template.shape
        hsv = cv2.cvtColor(region[y:y+h, x:x+w], cv2.COLOR_BGR2HSV)
        green = (hsv[:, :, 0] >= 28) & (hsv[:, :, 0] <= 90) & (hsv[:, :, 1] >= 60) & (hsv[:, :, 2] >= 65)
        if float(np.mean(green)) >= 0.10:
            best = score, (round((95+x+w/2)*sx), round((150+y+h/2)*sy))
    return best[1]


def detect_radar_complete_all_target(frame_bgr):
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None or not radar_overview_is_visible(frame):
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    directory = Path(__file__).parent / "assets/radar"
    label = cv2.imread(str(directory / "complete_all_label.png"), 0)
    lock = cv2.imread(str(directory / "complete_all_lock.png"), 0)
    if label is None or lock is None:
        return None
    if cv2.matchTemplate(gray[645:710, 5:220], label, cv2.TM_CCOEFF_NORMED).max() < 0.86:
        return None
    if cv2.matchTemplate(gray[520:600, 105:185], lock, cv2.TM_CCOEFF_NORMED).max() >= 0.80:
        return None
    return round(100 * sx), round(600 * sy)


def detect_radar_task_pin_targets(frame_bgr):
    """Existing missions can remain actionable after their red dots disappear."""
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None or not radar_overview_is_visible(frame):
        return []
    gray = cv2.cvtColor(frame[130:590, 250:1080], cv2.COLOR_BGR2GRAY)
    candidates = []
    for path in (Path(__file__).parent / "assets/radar/pins").glob("*.png"):
        template = cv2.imread(str(path), 0)
        if template is None:
            continue
        for scale in (0.9, 1.0, 1.1):
            marker = cv2.resize(template, None, fx=scale, fy=scale)
            result = cv2.matchTemplate(gray, marker, cv2.TM_CCOEFF_NORMED)
            for y, x in zip(*np.where(result >= 0.86)):
                candidates.append((float(result[y, x]), x + marker.shape[1] / 2 + 250,
                                   y + marker.shape[0] / 2 + 130))
    targets = []
    for _score, x, y in sorted(candidates, reverse=True):
        if all((x - px) ** 2 + (y - py) ** 2 > 32 ** 2 for px, py in targets):
            targets.append((x, y))
    return [(round(x * sx), round(y * sy)) for x, y in sorted(targets, key=lambda p: (p[1], p[0]))]


def stamina_dialog_is_visible(frame_bgr):
    """Return whether the insufficient-stamina item dialog is visible."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    # Map decorations and event banners share the old color pattern. Require
    # the actual dialog title before any stamina-item or close-button tap.
    marker = cv2.imread(str(Path(__file__).parent / "assets/stamina/dialog_title.png"), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return False
    heading = cv2.cvtColor(frame[73:122, 485:790], cv2.COLOR_BGR2GRAY)
    if float(cv2.matchTemplate(heading, marker, cv2.TM_CCOEFF_NORMED).max()) < 0.88:
        return False

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    def color_ratio(box, lower, upper):
        x1, y1, x2, y2 = box
        roi = hsv[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.0
        mask = cv2.inRange(
            roi,
            np.array(lower, dtype=np.uint8),
            np.array(upper, dtype=np.uint8),
        )
        return float(np.mean(mask > 0))

    if color_ratio((1030, 74, 1085, 120), (8, 70, 90), (40, 255, 255)) < 0.15:
        return False
    if color_ratio((210, 160, 305, 245), (35, 80, 60), (95, 255, 255)) < 0.10:
        return False
    if color_ratio((840, 290, 1090, 610), (10, 100, 120), (35, 255, 255)) < 0.10:
        return False
    return True


def detect_stamina_refill_target(frame_bgr, amount=50):
    """Return the visible stamina item button for +50, +100, or +500."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or not stamina_dialog_is_visible(frame_bgr):
        return None

    centers = {50: 348, 100: 454, 500: 559}
    try:
        center_y = centers[int(amount)]
    except (KeyError, TypeError, ValueError):
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    button_roi = hsv[center_y - 24:center_y + 24, 850:1090]
    enabled_mask = cv2.inRange(
        button_roi,
        np.array([10, 100, 120], dtype=np.uint8),
        np.array([35, 255, 255], dtype=np.uint8),
    )
    if button_roi.size == 0 or float(np.mean(enabled_mask > 0)) < 0.15:
        return None
    return int(round(968 * scale_x)), int(round(center_y * scale_y))


def detect_lowest_stamina_refill_target(frame_bgr):
    """Find the lowest visible gold item button after scrolling to +1000."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or not stamina_dialog_is_visible(frame_bgr):
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array([10, 100, 120], dtype=np.uint8),
        np.array([35, 255, 255], dtype=np.uint8),
    )
    mask[:280, :] = 0
    mask[640:, :] = 0
    mask[:, :830] = 0
    mask[:, 1100:] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 9), dtype=np.uint8))

    candidates = []
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if 150 <= width <= 240 and 28 <= height <= 60:
            candidates.append((y + height / 2.0, x + width / 2.0))
    if not candidates:
        return None
    center_y, center_x = max(candidates)
    return int(round(center_x * scale_x)), int(round(center_y * scale_y))


def detect_blank_webview_close_target(frame_bgr):
    """Find the close button on the blank Google/IGG login webview."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if float(np.mean(gray >= 220)) < 0.97:
        return None

    close_region = gray[8:62, 1208:1274]
    dark_ratio = float(np.mean(close_region < 190))
    if not 0.02 <= dark_ratio <= 0.25:
        return None

    return int(round(1246 * scale_x)), int(round(34 * scale_y))


def detect_settlement_event_panel_collapse_target(frame_bgr):
    """Find the right-pointing toggle of the expanded settlement event panel.

    The expanded event ribbon covers the upper third of the settlement and can
    hide hospital completion markers while the camera is being searched. The
    toggle is a stable pale ``>`` on a narrow dark tab. A collapsed ribbon
    shows the opposite chevron, so comparing the middle and edge centroids
    prevents this detector from reopening it.
    """
    return _detect_settlement_event_panel_toggle(frame_bgr, expand=False)


def detect_settlement_event_panel_expand_target(frame_bgr):
    """Find the left-pointing toggle of a collapsed settlement event panel."""
    return _detect_settlement_event_panel_toggle(frame_bgr, expand=True)


def _detect_settlement_event_panel_toggle(frame_bgr, *, expand):
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    tab = gray[58:108, 451:475]
    arrow = gray[70:95, 455:472]
    if tab.size == 0 or arrow.size == 0:
        return None
    if float(np.mean(tab <= 75)) < 0.45:
        return None

    bright = arrow >= 145
    bright_count = int(np.count_nonzero(bright))
    if not 45 <= bright_count <= 180:
        return None

    def centroid_x(row_start, row_end):
        _rows, columns = np.where(bright[row_start:row_end])
        if columns.size < 5:
            return None
        return float(np.mean(columns))

    top_x = centroid_x(3, 9)
    middle_x = centroid_x(10, 16)
    bottom_x = centroid_x(17, 23)
    if top_x is None or middle_x is None or bottom_x is None:
        return None
    if expand and middle_x > min(top_x, bottom_x) - 2.5:
        return None
    if not expand and middle_x < max(top_x, bottom_x) + 2.5:
        return None

    return int(round(463 * scale_x)), int(round(83 * scale_y))


def _bright_cross_ratio(frame, center, half_width=50, half_height=42):
    """Measure the pale cross used by empty truck slots."""
    center_x, center_y = center
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    x1 = max(0, center_x - half_width)
    x2 = min(frame.shape[1], center_x + half_width)
    y1 = max(0, center_y - half_height)
    y2 = min(frame.shape[0], center_y + half_height)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    bright = (gray[y1:y2, x1:x2] >= 160) & (hsv[y1:y2, x1:x2, 1] <= 90)
    local_x = center_x - x1
    local_y = center_y - y1
    vertical = bright[:, max(0, local_x - 10):local_x + 11]
    horizontal = bright[max(0, local_y - 10):local_y + 11, :]
    if vertical.size == 0 or horizontal.size == 0:
        return 0.0
    return min(float(np.mean(vertical)), float(np.mean(horizontal)))


def detect_truck_personal_slot_target(frame_bgr):
    """Return an unlocked personal-shipment ``+`` slot.

    The large upper plus belongs to Alliance Escort and must never be used for
    personal truck dispatch.  Personal slots are the two lower unlocked cards.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    # Personal slots may include the third/fourth lower card on upgraded accounts.
    candidates = ((207, 410), (768, 410), (497, 551), (1060, 551))
    # A prepared-but-not-started truck is resumed before opening another slot.
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    for center_x, center_y in candidates:
        # Keep the label search inside this card. The orange body of the
        # lower truck overlaps the old wide region beside an upper timer.
        unsent = hsv[center_y + 20:center_y + 62, center_x - 100:center_x + 101]
        red = (
            ((unsent[:, :, 0] < 12) | (unsent[:, :, 0] > 170))
            & (unsent[:, :, 1] > 90)
            & (unsent[:, :, 2] > 85)
        )
        if float(np.mean(red)) >= 0.008:
            return int(round(center_x * scale_x)), int(round(center_y * scale_y))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    pale = (gray >= 160) & (hsv[:, :, 1] <= 90)
    for center in candidates:
        x, y = center
        # Require all four arms. A lock and its explanatory text can satisfy
        # the old average-brightness test without containing a plus.
        plus_visible = min(float(pale[y+dy-6:y+dy+7, x+dx-7:x+dx+8].mean())
                           for dx, dy in ((-22, 0), (22, 0), (0, -17), (0, 17))) >= 0.42
        if _bright_cross_ratio(frame, center) >= 0.10 and plus_visible:
            return (
                int(round(center[0] * scale_x)),
                int(round(center[1] * scale_y)),
            )
    return None


def detect_truck_occupied_slot_targets(frame_bgr):
    """Return occupied personal truck cards for collection/status checks."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return []
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    targets = []
    for center_x, center_y in ((207, 410), (768, 410), (497, 551), (1060, 551)):
        region = hsv[center_y - 100:center_y + 75, center_x - 145:center_x + 145]
        unsent_region = hsv[center_y + 20:center_y + 62, center_x - 100:center_x + 101]
        unsent_red = (
            ((unsent_region[:, :, 0] < 12) | (unsent_region[:, :, 0] > 170))
            & (unsent_region[:, :, 1] > 90)
            & (unsent_region[:, :, 2] > 85)
        )
        if float(np.mean(unsent_red)) >= 0.008:
            # Prepared "Not sent" cards belong to the dispatch path, where
            # escort selection is mandatory before the gold start button.
            continue
        # Occupied cards contain the saturated blue truck body. Empty plus
        # cards and locked cards do not.
        blue = (
            (region[:, :, 0] >= 80)
            & (region[:, :, 0] <= 135)
            & (region[:, :, 1] >= 65)
            & (region[:, :, 2] >= 60)
        )
        if float(np.mean(blue)) >= 0.010:
            targets.append(
                (int(round(center_x * scale_x)), int(round(center_y * scale_y)))
            )
    return targets


def truck_alliance_escort_is_visible(frame_bgr):
    """Recognise Alliance Escort so it cannot be mistaken for a personal truck."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    if _truck_text_matches(frame, "alliance_title.png", (80, 10, 570, 75)):
        return True
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Alliance Escort has a persistent red 0/1 or 1/1 ticket counter here and
    # no personal-shipment tab bar in the upper-right corner.
    ticket = hsv[145:205, 370:450]
    red = (
        ((ticket[:, :, 0] < 12) | (ticket[:, :, 0] > 170))
        & (ticket[:, :, 1] > 105)
        & (ticket[:, :, 2] > 85)
    )
    tabs = hsv[14:66, 850:1268]
    orange_tabs = (
        (tabs[:, :, 0] >= 5)
        & (tabs[:, :, 0] <= 35)
        & (tabs[:, :, 1] >= 55)
        & (tabs[:, :, 2] >= 95)
    )
    return bool(float(np.mean(red)) >= 0.008 and float(np.mean(orange_tabs)) < 0.40)


def truck_express_overview_is_visible(frame_bgr):
    """Recognise the personal/other shipment overview."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None or detect_truck_transporting_close_target(frame) is not None:
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    tabs = hsv[14:66, 850:1268]
    orange_tabs = (
        (tabs[:, :, 0] >= 5)
        & (tabs[:, :, 0] <= 35)
        & (tabs[:, :, 1] >= 55)
        & (tabs[:, :, 2] >= 95)
    )
    return bool(
        float(np.mean(orange_tabs)) >= 0.20
        and (
            _bright_cross_ratio(frame, (640, 190)) >= 0.18
            or _truck_overview_title_visible(frame)
        )
    )


def _truck_overview_title_visible(frame):
    marker = cv2.imread(str(Path(__file__).parent / "assets/trucks/overview_title.png"), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return False
    region = cv2.cvtColor(frame[5:70, 70:520], cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(region, marker, cv2.TM_CCOEFF_NORMED).max()) >= 0.82


def truck_arrival_reward_is_visible(frame_bgr):
    """Recognise the full-screen reward shown after an arrived personal truck.

    This screen is neither the shipment overview nor the world-map detail
    panel.  Treating it as an unconfirmed detail used to leave the rewards
    uncollected and defer the whole truck task.
    """
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None or truck_express_overview_is_visible(frame):
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    divider = hsv[205:235, 90:1190]
    orange = (
        (divider[:, :, 0] >= 4)
        & (divider[:, :, 0] <= 35)
        & (divider[:, :, 1] >= 70)
        & (divider[:, :, 2] >= 85)
    )
    title = hsv[235:305, 485:795]
    bright_text = (title[:, :, 1] <= 75) & (title[:, :, 2] >= 180)
    lower = hsv[450:690, 80:1200]
    dark_lower = lower[:, :, 2] <= 95
    return bool(
        float(np.mean(orange)) >= 0.025
        and float(np.mean(bright_text)) >= 0.012
        and float(np.mean(dark_lower)) >= 0.45
    )


def truck_daily_dispatch_limit_is_visible(frame_bgr):
    """An empty physical slot remains clickable after daily dispatches reach 0."""
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None or not truck_express_overview_is_visible(frame):
        return False
    if _truck_text_matches(frame, "daily_limit_message.png", (300, 115, 980, 163)):
        return True
    # This is a remaining-dispatch counter: 4/4 is available, 0/4 exhausted.
    # Keep the zero search before the slash; a zero elsewhere cannot block it.
    return (
        _truck_text_matches(frame, "daily_dispatches_label.png", (5, 661, 271, 704))
        and _truck_text_matches(frame, "zero_remaining.png", (268, 665, 289, 700))
    )


def truck_personal_dispatch_card_is_visible(frame_bgr):
    frame, _sx, _sy = _reference_frame(frame_bgr)
    return bool(frame is not None
                and _truck_text_matches(frame, "personal_card_title.png", (510, 55, 770, 105))
                and detect_truck_start_dispatch_target(frame) is not None)


def detect_truck_transporting_close_target(frame_bgr):
    """Recognise the personal in-transit modal by its title and status text."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None
    if (_truck_text_matches(frame, "personal_card_title.png", (510, 55, 770, 105))
            and _truck_text_matches(frame, "transporting_label.png", (495, 510, 785, 553))):
        return round(1057 * scale_x), round(80 * scale_y)
    return None


def detect_truck_start_dispatch_target(frame_bgr):
    """Return the enabled gold Start Escort button on a personal shipment."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or detect_truck_transporting_close_target(frame) is not None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    region = hsv[552:618, 420:855]
    gold = (
        (region[:, :, 0] >= 8)
        & (region[:, :, 0] <= 38)
        & (region[:, :, 1] >= 70)
        & (region[:, :, 2] >= 130)
    )
    if float(np.mean(gold)) < 0.30:
        return None
    return int(round(640 * scale_x)), int(round(585 * scale_y))


def detect_truck_escort_confirmation_target(frame_bgr):
    """Return the gold Done button on the personal escort formation screen."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    region = hsv[580:650, 805:1195]
    orange = (
        (region[:, :, 0] >= 4)
        & (region[:, :, 0] <= 35)
        & (region[:, :, 1] >= 60)
        & (region[:, :, 2] >= 80)
    )
    if float(np.mean(orange)) < 0.55:
        return None
    return int(round(1000 * scale_x)), int(round(616 * scale_y))


def detect_truck_active_detail_back_target(frame_bgr):
    """Return the back arrow for an in-progress truck's world-map panel."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if (frame is None or truck_express_overview_is_visible(frame)
            or truck_alliance_escort_is_visible(frame)):
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    region = hsv[150:220, 1100:1190]
    orange = (
        (region[:, :, 0] >= 5)
        & (region[:, :, 0] <= 35)
        & (region[:, :, 1] >= 60)
        & (region[:, :, 2] >= 110)
    )
    if float(np.mean(orange)) < 0.045:
        return None
    return int(round(1143 * scale_x)), int(round(181 * scale_y))


def detect_truck_ready_collection_target(frame_bgr):
    """Return a real gold Collect button inside a truck's world-map panel."""
    if detect_truck_active_detail_back_target(frame_bgr) is None:
        return None
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    region = hsv[540:625, 755:1175]
    gold = (
        (region[:, :, 0] >= 8)
        & (region[:, :, 0] <= 38)
        & (region[:, :, 1] >= 75)
        & (region[:, :, 2] >= 145)
    )
    if float(np.mean(gold)) < 0.30:
        return None
    return int(round(965 * scale_x)), int(round(582 * scale_y))


def truck_auto_dispatch_is_enabled(frame_bgr):
    """Return whether the personal truck auto-dispatch toggle is on."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    left = hsv[345:384, 955:995]
    right = hsv[345:384, 995:1038]
    left_handle = (left[:, :, 1] <= 105) & (left[:, :, 2] >= 135)
    right_handle = (right[:, :, 1] <= 105) & (right[:, :, 2] >= 135)
    return bool(float(np.mean(right_handle)) > float(np.mean(left_handle)) + 0.08)


def _truck_text_matches(frame, name, region):
    marker = cv2.imread(str(Path(__file__).parent / "assets/trucks" / name), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return False
    left, top, right, bottom = region
    gray = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(gray, marker, cv2.TM_CCOEFF_NORMED).max()) >= 0.84


def truck_formation_is_visible(frame_bgr):
    frame, _sx, _sy = _reference_frame(frame_bgr)
    return frame is not None and _truck_text_matches(
        frame, "formation_title.png", (810, 580, 1195, 650)
    )


def detect_truck_formation_add_target(frame_bgr):
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None or not truck_formation_is_visible(frame):
        return None
    for y in (140, 230, 320):
        if _truck_text_matches(frame, "slot_plus.png", (33, y - 25, 81, y + 25)):
            return round(57 * sx), round(y * sy)
    return None


def detect_truck_squad_done_target(frame_bgr):
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None or not _truck_text_matches(frame, "squad_done.png", (860, 616, 1065, 670)):
        return None
    # An enabled Done button alone also appears with zero troops. Require an
    # actual selected troop bar before accepting the game's proposed squad.
    hsv = cv2.cvtColor(frame[120:525, 748:1040], cv2.COLOR_BGR2HSV)
    green = (hsv[:, :, 0] >= 35) & (hsv[:, :, 0] <= 90) & (hsv[:, :, 1] >= 90) & (hsv[:, :, 2] >= 90)
    if float(np.mean(green)) < 0.001:
        return None
    return round(963 * sx), round(643 * sy)


def detect_shop_selection_marker_target(
    frame_bgr,
    building_target,
    action_template_bgr=None,
):
    """Find the gold Shop marker directly above a facade candidate.

    The previous broad contour search extended into the bottom navigation and
    could return the Alliance button as the right-most "radial" action.  Shop
    exposes a distinctive gold diamond above its roof, so local template
    matching is both safer and more stable.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or not building_target:
        return None
    building_x = float(building_target[0]) / max(scale_x, 1e-6)
    building_y = float(building_target[1]) / max(scale_y, 1e-6)
    template = np.asarray(action_template_bgr) if action_template_bgr is not None else None
    if template is None or template.size == 0 or template.ndim not in (2, 3):
        return None
    template_gray = (
        cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        if template.ndim == 3
        else template
    )
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    left = int(max(0, building_x - 190))
    right = int(min(1280, building_x + 190))
    top = int(max(0, building_y - 245))
    bottom = int(min(600, building_y + 15))
    search = frame_gray[top:bottom, left:right]
    if search.size == 0:
        return None

    best_score = -1.0
    best_target = None
    for scale in np.linspace(0.55, 1.70, 24):
        resized = cv2.resize(
            template_gray,
            None,
            fx=float(scale),
            fy=float(scale),
            interpolation=cv2.INTER_CUBIC,
        )
        if resized.shape[0] >= search.shape[0] or resized.shape[1] >= search.shape[1]:
            continue
        result = cv2.matchTemplate(search, resized, cv2.TM_CCOEFF_NORMED)
        _minimum, score, _min_location, location = cv2.minMaxLoc(result)
        if float(score) > best_score:
            best_score = float(score)
            best_target = (
                left + location[0] + resized.shape[1] / 2.0,
                top + location[1] + resized.shape[0] / 2.0,
            )
    if best_target is None or best_score < 0.58:
        return None
    return (
        int(round(best_target[0] * scale_x)),
        int(round(best_target[1] * scale_y)),
    )


def detect_training_radial_action_target(frame_bgr, barracks_title_target):
    """Find the labelled Train action near an independently verified barracks.

    Max-level barracks omit Upgrade, moving Train left. Its label remains
    below the circular action, so a fixed offset from the title is unsafe.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or barracks_title_target is None:
        return None
    title_x = float(barracks_title_target[0]) / max(scale_x, 1e-6)
    title_y = float(barracks_title_target[1]) / max(scale_y, 1e-6)
    left = max(0, int(title_x - 300))
    right = min(1280, int(title_x + 300))
    top = max(0, int(title_y + 100))
    bottom = min(650, int(title_y + 410))
    if right <= left or bottom <= top:
        return None
    gray = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
    for filename in ("training_action_label.png", "training_action_label_bright.png"):
        template = imread_unicode(Path(__file__).parent / "assets/training" / filename, cv2.IMREAD_GRAYSCALE)
        if template is None or gray.shape[0] < template.shape[0] or gray.shape[1] < template.shape[1]:
            continue
        _, score, _, location = cv2.minMaxLoc(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED))
        if score >= 0.82:
            label_x = left + location[0] + template.shape[1] / 2
            label_y = top + location[1] + template.shape[0] / 2
            return round(label_x * scale_x), round((label_y - 44) * scale_y)
    return None


def detect_shop_radial_action_target(frame_bgr, building_target=None):
    """Return the ordinary Shop action after the building is selected.

    Prefer the labelled action on upgraded buildings with an Armory button.
    Low-level Shop has three actions and four green selection arrows, allowing
    its ordinary Shop action to be located at the centre of that radial menu.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None
    if building_target:
        building_x = int(round(float(building_target[0]) / max(scale_x, 1e-6)))
        building_y = int(round(float(building_target[1]) / max(scale_y, 1e-6)))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        asset_dir = Path(__file__).parent / "assets/merchant"
        title = cv2.imread(str(asset_dir / "merchant_building_title.png"), cv2.IMREAD_GRAYSCALE)
        label = cv2.imread(str(asset_dir / "merchant_shop_action_label.png"), cv2.IMREAD_GRAYSCALE)
        def label_location(template, bounds, threshold):
            if template is None:
                return None
            left, top, right, bottom = bounds
            search = gray[top:bottom, left:right]
            if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
                return None
            _, score, _, location = cv2.minMaxLoc(cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED))
            return (left + location[0] + template.shape[1] / 2, top + location[1] + template.shape[0] / 2, float(score)) if score >= threshold else None
        title_seen = False
        best_action = None
        best_score = -1.0
        if title is not None and label is not None:
            # The live IGG 5 menu renders both labels 30% larger than these
            # reference crops, even though the frame remains 1280x720. Match
            # both at one coherent UI scale; do not relax either threshold.
            for ui_scale in np.linspace(0.85, 1.40, 23):
                scaled_title = cv2.resize(title, None, fx=float(ui_scale), fy=float(ui_scale))
                scaled_label = cv2.resize(label, None, fx=float(ui_scale), fy=float(ui_scale))
                title_location = label_location(scaled_title, (max(0, building_x - 220), max(0, building_y - 170), min(1280, building_x + 220), max(1, building_y - 45)), 0.82)
                if title_location is None:
                    continue
                title_seen = True
                # Ordinary Shop is at/below-left of its title. Armory and
                # Beast Shop are separate controls to the right; their labels
                # must not substitute for the ordinary one when it is hidden.
                half_label = scaled_label.shape[1] / 2
                action_bounds = (
                    max(0, building_x - 250, int(title_location[0] - 170 * ui_scale - half_label)),
                    min(719, building_y + 40),
                    min(1280, building_x + 250, int(title_location[0] + 20 * ui_scale + half_label)),
                    min(650, building_y + 240),
                )
                action_location = label_location(scaled_label, action_bounds, 0.74)
                if action_location is None:
                    continue
                score = title_location[2] + action_location[2]
                if score > best_score:
                    best_score = score
                    best_action = (action_location[0], action_location[1] - 40 * ui_scale)
        if best_action is not None:
            return round(best_action[0] * scale_x), round(best_action[1] * scale_y)
        if title_seen:
            # A selected Shop with an unverified ordinary action is not the
            # unlabeled low-level layout handled by the geometric fallback.
            return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # The arrows are a narrow yellow-green.  A broader green range also picks
    # up vegetation and illuminated facade details, joining an arrow to the
    # building and making its contour unusable.
    green = cv2.inRange(
        hsv,
        np.array([34, 130, 150], dtype=np.uint8),
        np.array([55, 255, 255], dtype=np.uint8),
    )
    if building_target:
        building_x = int(round(float(building_target[0]) / max(scale_x, 1e-6)))
        building_y = int(round(float(building_target[1]) / max(scale_y, 1e-6)))
        # The catalogue may centre Shop much higher than the ordinary camera
        # route.  The old fixed 280..510 band consequently erased every real
        # selection arrow (the live IGG 4 arrows were at y=138..240).  Anchor
        # the mask to the just-tapped building instead of assuming one camera
        # height.
        green[:max(0, building_y - 100), :] = 0
        green[min(720, building_y + 115):, :] = 0
        green[:, :max(0, building_x - 240)] = 0
        green[:, min(1280, building_x + 240):] = 0
    else:
        green[:280, :] = 0
        green[510:, :] = 0
        green[:, :560] = 0
        green[:, 1020:] = 0
    contours, _hierarchy = cv2.findContours(
        green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    arrows = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = float(cv2.contourArea(contour))
        # Horizontal arrows are roughly 25x19, while the left/right arrow can
        # be only 14x25 after isometric scaling.  Accept either orientation;
        # the four-marker span check below remains the false-positive guard.
        if 12 <= width <= 55 and 18 <= height <= 42 and area >= 150.0:
            arrows.append((x + width / 2.0, y + height / 2.0))
    if len(arrows) < 4:
        return None
    x_values = [point[0] for point in arrows]
    y_values = [point[1] for point in arrows]
    horizontal_span = max(x_values) - min(x_values)
    vertical_span = max(y_values) - min(y_values)
    if not 90 <= horizontal_span <= 230 or not 65 <= vertical_span <= 155:
        return None
    building_center_x = (min(x_values) + max(x_values)) / 2.0
    bottom_arrow_y = max(y_values)
    action_x = int(round(building_center_x))
    action_y = int(round(bottom_arrow_y + 45.0))

    # Several settlement buildings use the same four green selection arrows.
    # Equipment Repair is the important live false positive: it exposes only
    # two actions, leaving bare ground at the centre where Shop's middle action
    # must be.  Verify that a real high-contrast circular control occupies that
    # position before returning a tap.  This prevents a no-op centre tap from
    # being interpreted as "merchant unavailable".
    radius = 28
    left = max(0, action_x - radius)
    right = min(1280, action_x + radius + 1)
    top = max(0, action_y - radius)
    bottom = min(720, action_y + radius + 1)
    action_roi = frame[top:bottom, left:right]
    if action_roi.size == 0:
        return None
    action_gray = cv2.cvtColor(action_roi, cv2.COLOR_BGR2GRAY)
    action_edges = cv2.Canny(action_gray, 60, 140)
    if (
        float(np.std(action_gray)) < 38.0
        or float(np.mean(action_edges > 0)) < 0.07
    ):
        return None
    return (
        int(round(action_x * scale_x)),
        int(round(action_y * scale_y)),
    )


def detect_merchant_shop_building_target(
    frame_bgr,
    sign_template_bgr,
    min_score=0.44,
    search_bounds=None,
):
    """Locate the real Shop sign and return a tap below it.

    The settlement contains several shield and notice-board emblems that look
    vaguely like the four-stroke Shop sign.  The older 0.18 threshold accepted
    those objects and then treated an unrelated radial action as the merchant.
    Match only the dedicated sign crop at a materially stronger score.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or sign_template_bgr is None:
        return None, -1.0
    template = np.asarray(sign_template_bgr)
    if template.size == 0:
        return None, -1.0
    if template.ndim == 3:
        template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    elif template.ndim != 2:
        return None, -1.0

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if search_bounds is None:
        left, top, right, bottom = 300, 150, 1000, 545
    else:
        left, top, right, bottom = map(int, search_bounds)
        left = max(0, min(1279, left))
        top = max(0, min(719, top))
        right = max(left + 1, min(1280, right))
        bottom = max(top + 1, min(720, bottom))
    search_edges = cv2.Canny(gray[top:bottom, left:right], 40, 120)
    best_score = -1.0
    best_target = None
    for scale in np.linspace(0.55, 1.55, 21):
        resized = cv2.resize(
            template,
            None,
            fx=float(scale),
            fy=float(scale),
            interpolation=cv2.INTER_CUBIC,
        )
        if (
            resized.shape[0] >= search_edges.shape[0]
            or resized.shape[1] >= search_edges.shape[1]
        ):
            continue
        edges = cv2.Canny(resized, 40, 120)
        if int(np.count_nonzero(edges)) < 12:
            continue
        result = cv2.matchTemplate(search_edges, edges, cv2.TM_CCOEFF_NORMED)
        _minimum, score, _min_location, location = cv2.minMaxLoc(result)
        if float(score) > best_score:
            best_score = float(score)
            best_target = (
                int(round((left + location[0] + resized.shape[1] / 2) * scale_x)),
                int(round((top + location[1] + resized.shape[0] / 2 + 35) * scale_y)),
            )
    if best_target is None or best_score < float(min_score):
        return None, best_score
    return best_target, best_score


def detect_merchant_shop_feature_target(
    frame_bgr,
    building_template_bgr,
    min_inliers=10,
    search_bounds=(80, 75, 1210, 620),
):
    """Locate Shop by stable facade details despite small camera distortions.

    Edge-template matching is intentionally retained as a cheap fallback, but
    it is too brittle for the isometric settlement camera: a tiny pan changes
    the facade perspective enough to turn an exact Shop crop into a score near
    zero.  SIFT correspondences plus a RANSAC homography tolerate that change
    while the inlier and projected-box checks reject unrelated buildings.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or building_template_bgr is None:
        return None, 0
    template = np.asarray(building_template_bgr)
    if template.size == 0 or template.ndim not in (2, 3):
        return None, 0

    left, top, right, bottom = map(int, search_bounds)
    left = max(0, min(1279, left))
    top = max(0, min(719, top))
    right = max(left + 1, min(1280, right))
    bottom = max(top + 1, min(720, bottom))
    search = frame[top:bottom, left:right]
    if search.size == 0:
        return None, 0

    template_gray = (
        cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        if template.ndim == 3
        else template
    )
    search_gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    try:
        sift = cv2.SIFT_create(nfeatures=2500, contrastThreshold=0.015)
    except (AttributeError, cv2.error):
        return None, 0
    template_keypoints, template_descriptors = sift.detectAndCompute(
        template_gray, None
    )
    search_keypoints, search_descriptors = sift.detectAndCompute(search_gray, None)
    if (
        template_descriptors is None
        or search_descriptors is None
        or len(template_keypoints) < 4
        or len(search_keypoints) < 4
    ):
        return None, 0

    matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(
        template_descriptors, search_descriptors, k=2
    )
    good = [
        first
        for pair in matches
        if len(pair) == 2
        for first, second in [pair]
        if first.distance < 0.76 * second.distance
    ]
    if len(good) < max(4, int(min_inliers)):
        return None, 0

    source_points = np.float32(
        [template_keypoints[match.queryIdx].pt for match in good]
    ).reshape(-1, 1, 2)
    target_points = np.float32(
        [search_keypoints[match.trainIdx].pt for match in good]
    ).reshape(-1, 1, 2)
    homography, inlier_mask = cv2.findHomography(
        source_points, target_points, cv2.RANSAC, 5.0
    )
    if homography is None or inlier_mask is None:
        return None, 0
    inliers = int(np.count_nonzero(inlier_mask))
    if inliers < int(min_inliers):
        return None, inliers

    template_height, template_width = template_gray.shape[:2]
    corners = np.float32(
        [[[0, 0], [template_width, 0], [template_width, template_height], [0, template_height]]]
    )
    projected = cv2.perspectiveTransform(corners, homography)[0]
    projected_width = float(
        (np.linalg.norm(projected[1] - projected[0]) + np.linalg.norm(projected[2] - projected[3]))
        / 2.0
    )
    projected_height = float(
        (np.linalg.norm(projected[3] - projected[0]) + np.linalg.norm(projected[2] - projected[1]))
        / 2.0
    )
    polygon_area = abs(float(cv2.contourArea(projected.reshape(-1, 1, 2))))
    if (
        not np.isfinite(projected).all()
        or not 95.0 <= projected_width <= 280.0
        or not 65.0 <= projected_height <= 210.0
        or polygon_area < 6500.0
    ):
        return None, inliers

    center = np.mean(projected, axis=0)
    center_x = left + float(center[0])
    center_y = top + float(center[1])
    if not (left <= center_x <= right and top <= center_y <= bottom):
        return None, inliers
    return (
        int(round(center_x * scale_x)),
        int(round(center_y * scale_y)),
    ), inliers


def mysterious_merchant_screen_is_visible(frame_bgr):
    """Require the merchant grid, its title and its selected left-hand tab."""
    if not _shop_offer_grid_is_visible(frame_bgr):
        return False
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    directory = Path(__file__).parent / "assets/merchant"
    marker = imread_unicode(directory / "merchant_title.png", cv2.IMREAD_GRAYSCALE)
    tab_marker = imread_unicode(directory / "merchant_tab.png", cv2.IMREAD_GRAYSCALE)
    if marker is None or tab_marker is None:
        return False
    header = cv2.cvtColor(frame[55:98, 140:480], cv2.COLOR_BGR2GRAY)
    if float(np.max(cv2.matchTemplate(header, marker, cv2.TM_CCOEFF_NORMED))) < 0.82:
        return False
    tab = frame[365:478, 15:125]
    tab_gray = cv2.cvtColor(tab, cv2.COLOR_BGR2GRAY)
    if float(cv2.matchTemplate(tab_gray, tab_marker, cv2.TM_CCOEFF_NORMED).max()) < 0.82:
        return False
    tab_hsv = cv2.cvtColor(tab, cv2.COLOR_BGR2HSV)
    selected_red = (
        ((tab_hsv[:, :, 0] <= 12) | (tab_hsv[:, :, 0] >= 170))
        & (tab_hsv[:, :, 1] >= 55) & (tab_hsv[:, :, 2] >= 100)
    )
    # Inactive tabs retain the same lettering but are darkened. A matching
    # title during the shop transition cannot make an inactive tab current.
    return float(np.mean(selected_red)) >= 0.30


def detect_shop_merchant_tab_target(frame_bgr):
    """Locate the merchant tab when Shop remembered another subsection."""
    if not _shop_offer_grid_is_visible(frame_bgr):
        return None
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    marker = cv2.imread(str(Path(__file__).parent / "assets/merchant/merchant_tab.png"), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return None
    tabs = cv2.cvtColor(frame[350:490, :135], cv2.COLOR_BGR2GRAY)
    if float(np.max(cv2.matchTemplate(tabs, marker, cv2.TM_CCOEFF_NORMED))) < 0.75:
        return None
    return int(round(68 * scale_x)), int(round(424 * scale_y))


def _shop_offer_grid_is_visible(frame_bgr):
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # The settlement building catalogue is also brown/red and used to pass
    # the broad merchant signature.  Its lower half is dominated by large,
    # low-saturation parchment construction cards; merchant offers are not.
    # Reject this screen before sampling any apparent resource price strips.
    catalogue_cards = hsv[330:700, :]
    catalogue_pale = (
        (catalogue_cards[:, :, 1] <= 75)
        & (catalogue_cards[:, :, 2] >= 75)
    )
    if float(np.mean(catalogue_pale)) >= 0.50:
        return False
    panel = hsv[65:650, 95:1035]
    dark_brown = (
        (panel[:, :, 0] <= 35)
        & (panel[:, :, 1] >= 35)
        & (panel[:, :, 2] <= 145)
    )
    left_tabs = hsv[90:590, 0:155]
    muted_red = (
        ((left_tabs[:, :, 0] <= 12) | (left_tabs[:, :, 0] >= 170))
        & (left_tabs[:, :, 1] >= 35)
        & (left_tabs[:, :, 2] >= 65)
    )
    return bool(float(np.mean(dark_brown)) >= 0.20 and float(np.mean(muted_red)) >= 0.025)


def settlement_building_catalogue_is_visible(frame_bgr):
    """Recognise the settlement building catalogue, regardless of its tab.

    The catalogue can reopen on the last-used tab (including Decorations).
    Merchant navigation must therefore prove that the large construction-card
    panel is actually open before it swipes or selects the Economy tab.
    """
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cards = hsv[330:700, :]
    tabs = hsv[185:325, :]
    pale_cards = (
        (cards[:, :, 1] <= 75)
        & (cards[:, :, 2] >= 75)
    )
    dark_tab_bar = tabs[:, :, 2] <= 75
    return bool(
        float(np.mean(pale_cards)) >= 0.62
        and float(np.mean(dark_tab_bar)) >= 0.58
    )


def detect_mysterious_merchant_absent_ok_target(frame_bgr):
    """Return OK on the notice shown while the merchant is away."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    parchment = hsv[215:465, 345:935]
    button = hsv[484:534, 507:773]
    if parchment.size == 0 or button.size == 0:
        return None
    pale = (
        (parchment[:, :, 1] <= 70)
        & (parchment[:, :, 2] >= 110)
    )
    gold = (
        (button[:, :, 0] >= 8)
        & (button[:, :, 0] <= 38)
        & (button[:, :, 1] >= 70)
        & (button[:, :, 2] >= 130)
    )
    if float(np.mean(pale)) < 0.72 or float(np.mean(gold)) < 0.68:
        return None
    return int(round(640 * scale_x)), int(round(509 * scale_y))


def detect_merchant_free_refresh_target(frame_bgr):
    """Require the explicit Free Refresh label on the verified merchant page."""
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None or not mysterious_merchant_screen_is_visible(frame):
        return None
    marker = cv2.imread(str(Path(__file__).parent / "assets/merchant/free_refresh.png"), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return None
    region = frame[605:678, 855:1040]
    score = float(cv2.matchTemplate(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY), marker, cv2.TM_CCOEFF_NORMED).max())
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    gold = (hsv[:, :, 0] >= 8) & (hsv[:, :, 0] <= 42) & (hsv[:, :, 1] >= 70) & (hsv[:, :, 2] >= 130)
    if score < 0.86 or float(np.mean(gold)) < 0.30:
        return None
    return round(948 * sx), round(638 * sy)


def detect_mysterious_merchant_non_gem_offer_targets(frame_bgr):
    """Return offers with a positively identified resource icon and amount."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or not mysterious_merchant_screen_is_visible(frame):
        return []
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # These are crops of real price-bar icons, not the larger item artwork or
    # HUD counters. Unknown currencies remain unclickable until supported by
    # an observed price icon; a gold fill alone says nothing about the cost.
    directory = Path(__file__).parent / "assets/merchant"
    resource_icons = [
        icon for name in ("currency_food.png", "currency_wood.png")
        if (icon := imread_unicode(directory / name)) is not None
    ]
    if not resource_icons:
        return []
    candidates = []
    # Price bars move vertically when the offer list scrolls. Locate their
    # gold background inside the three price columns, excluding item artwork
    # and the fixed gem-funded refresh control below the scroll viewport.
    for x1, x2 in ((293, 448), (601, 756), (909, 1064)):
        stripe = hsv[155:585, x1:x2]
        gold = (
            (stripe[:, :, 0] >= 10) & (stripe[:, :, 0] <= 40)
            & (stripe[:, :, 1] >= 70) & (stripe[:, :, 2] >= 110)
        )
        rows = np.mean(gold, axis=1) >= 0.35
        edges = np.diff(np.r_[False, rows, False].astype(np.int8))
        for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            if not 20 <= end - start <= 55:
                continue
            y1, y2 = int(start) + 155, int(end) + 155
            region = hsv[y1:y2, x1:x2]
            purple = (
                (region[:, :, 0] >= 115)
                & (region[:, :, 0] <= 170)
                & (region[:, :, 1] >= 35)
                & (region[:, :, 2] >= 65)
            )
            if float(np.mean(purple)) > 0.05:
                continue
            icon_region = frame[y1:y2, x1 + 3:x1 + 60]
            icon_seen = False
            for icon in resource_icons:
                for icon_scale in (0.85, 0.9, 1.0, 1.1, 1.2):
                    template = cv2.resize(icon, None, fx=icon_scale, fy=icon_scale)
                    if (
                        template.shape[0] > icon_region.shape[0]
                        or template.shape[1] > icon_region.shape[1]
                    ):
                        continue
                    if float(cv2.matchTemplate(
                        icon_region, template, cv2.TM_CCOEFF_NORMED,
                    ).max()) >= 0.86:
                        icon_seen = True
                        break
                if icon_seen:
                    break
            if not icon_seen:
                continue
            # A transition can expose the currency before the button's cost.
            # Require visible amount glyphs to its right as well; the caller
            # separately confirms this same offer in a fresh stable frame.
            amount = region[:, 52:-5]
            amount_mask = (
                (amount[:, :, 1] < 70) & (amount[:, :, 2] >= 190)
            ).astype(np.uint8) * 255
            _count, _labels, stats, _centers = cv2.connectedComponentsWithStats(amount_mask)
            if not any(
                3 <= width <= 20 and 10 <= height <= 28 and area >= 25
                for _x, _y, width, height, area in stats[1:]
            ):
                continue
            candidates.append(
                (int(round((x1 + x2) / 2 * scale_x)),
                 int(round((y1 + y2) / 2 * scale_y)))
                )
    return sorted(candidates, key=lambda point: (point[1], point[0]))


def _game_server_error_text_mask(frame, *, dark=False):
    """Keep lettering, rather than the title artwork or gold button fill."""
    if dark:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        return np.clip((110 - gray) * 4, 0, 255).astype(np.uint8)
    low = np.min(frame, axis=2).astype(np.float32)
    high = np.max(frame, axis=2).astype(np.float32)
    mask = np.clip((low - (high - low) * .5 - 80) * 3, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(mask, (3, 3), .8)


def detect_game_server_connection_error(frame_bgr) -> bool:
    """Recognize the Russian title-screen connection error and its EXIT label.

    Both cropped text anchors must match their own narrow 1280x720 regions.
    A generic gold button, an SDK login error, or ordinary loading is not proof
    of this screen and must not trigger game-restart recovery.
    """
    if (not isinstance(frame_bgr, np.ndarray) or frame_bgr.ndim != 3
            or frame_bgr.shape[2] != 3 or frame_bgr.dtype != np.uint8):
        return False
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    assets = Path(__file__).parent / "assets" / "accounts"
    anchors = (
        ("server_connection_error_text.png", (425, 515, 825, 571), False),
        ("server_connection_exit_text.png", (515, 596, 750, 657), True),
    )
    for filename, (x1, y1, x2, y2), dark in anchors:
        template = imread_unicode(assets / filename)
        if template is None:
            return False
        template_mask = _game_server_error_text_mask(template, dark=dark)
        region_mask = _game_server_error_text_mask(frame[y1:y2, x1:x2], dark=dark)
        if (template_mask.shape[0] > region_mask.shape[0]
                or template_mask.shape[1] > region_mask.shape[1]
                or float(np.std(template_mask)) < 1):
            return False
        score = cv2.minMaxLoc(cv2.matchTemplate(
            region_mask, template_mask, cv2.TM_CCOEFF_NORMED,
        ))[1]
        if not np.isfinite(score) or score < .90:
            return False
    return True


def detect_login_session_expired_ok_target(frame_bgr):
    """Find the wide yellow OK button in the expired-login dialog."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array([15, 60, 120], dtype=np.uint8),
        np.array([40, 255, 255], dtype=np.uint8),
    )
    mask[:400, :] = 0
    mask[600:, :] = 0
    mask[:, :300] = 0
    mask[:, 980:] = 0

    candidates = []
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        aspect = width / float(height) if height else 0.0
        center_x = x + width / 2.0
        center_y = y + height / 2.0
        if (
            180 <= width <= 380
            and 30 <= height <= 80
            and 3.5 <= aspect <= 9.0
            and 500 <= center_x <= 780
            # The title screen's yellow UPDATE button is centred around y=466
            # and otherwise has almost the same colour and proportions as the
            # confirmation button.  The interrupted-session dialog always
            # places its action row lower in the modal.
            and 485 <= center_y <= 560
        ):
            candidates.append((width * height, center_x, center_y))
    if not candidates:
        return None

    _area, center_x, center_y = max(candidates)
    return int(round(center_x * scale_x)), int(round(center_y * scale_y))


def detect_gem_confirmation_cancel_target(frame_bgr):
    """Recognize the gem-spending warning and return only its No button.

    Require the warning title, currency icon, explicit cancellation label and
    purple paid button together. A generic login OK dialog is not this modal.
    The variable price is deliberately excluded from the templates.
    """
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    directory = Path(__file__).parent / "assets/research"
    for name, bounds in (
        ("gem_warning_title", (555, 170, 720, 220)),
        ("gem_warning_cancel", (450, 480, 540, 537)),
        ("gem_warning_currency", (730, 440, 790, 488)),
    ):
        template = cv2.imread(str(directory / (name + ".png")), 0)
        if template is None:
            return None
        x1, y1, x2, y2 = bounds
        score = float(cv2.matchTemplate(
            gray[y1:y2, x1:x2], template, cv2.TM_CCOEFF_NORMED,
        ).max())
        if not np.isfinite(score) or score < 0.88:
            return None
    hsv = cv2.cvtColor(frame[488:529, 655:908], cv2.COLOR_BGR2HSV)
    if np.mean((hsv[:, :, 0] >= 115) & (hsv[:, :, 0] <= 160)
               & (hsv[:, :, 1] >= 60)) < 0.45:
        return None
    return round(495 * sx), round(509 * sy)


def detect_research_action_target(frame_bgr):
    """Return the enabled gold Collect/Confirm button on a research screen.

    Research completion and research start use the same lower-right action
    slot, but the button text changes between accounts and game languages.
    The caller only uses this detector while the research routine is already
    inside a selected laboratory, which keeps this colour fallback scoped to
    the safe research flow.
    """
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return None
    height, width = frame_bgr.shape[:2]
    if width < 640 or height < 360:
        return None
    scale_x = width / 1280.0
    scale_y = height / 720.0
    frame = cv2.resize(frame_bgr, (1280, 720), interpolation=cv2.INTER_LINEAR)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    left, top, right, bottom = 800, 515, 1165, 650
    region = hsv[top:bottom, left:right]
    gold = (
        (region[:, :, 0] >= 8)
        & (region[:, :, 0] <= 42)
        & (region[:, :, 1] >= 65)
        & (region[:, :, 2] >= 125)
    ).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 5))
    gold = cv2.morphologyEx(gold, cv2.MORPH_CLOSE, kernel)
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(gold, 8)
    candidates = []
    for index in range(1, count):
        component_left = int(stats[index, cv2.CC_STAT_LEFT])
        component_top = int(stats[index, cv2.CC_STAT_TOP])
        component_width = int(stats[index, cv2.CC_STAT_WIDTH])
        component_height = int(stats[index, cv2.CC_STAT_HEIGHT])
        component_area = int(stats[index, cv2.CC_STAT_AREA])
        touches_search_edge = (
            component_top <= 3
            or component_left + component_width >= region.shape[1] - 3
        )
        if not (
            150 <= component_width <= 340
            and 28 <= component_height <= 90
            and component_area >= 3500
            and component_width / max(1.0, float(component_height)) >= 2.5
            and not touches_search_edge
        ):
            continue
        center_x, center_y = centroids[index]
        candidates.append(
            (
                component_area,
                left + float(center_x),
                top + float(center_y),
                component_left,
                component_top,
            )
        )
    if not candidates:
        return None
    _area, center_x, center_y, _component_left, _component_top = max(
        candidates,
        key=lambda item: item[0],
    )
    return int(round(center_x * scale_x)), int(round(center_y * scale_y))


def research_progress_bar_is_active(frame_bgr):
    """Return whether the centred laboratory shows an active research timer.

    Selecting the left research queue centres the laboratory.  While a project
    is running, its stable green horizontal progress bar appears immediately
    below the countdown.  This is stronger evidence than the animated ``1/1``
    HUD counter and lets a resumed daily pass accept research that is already
    in progress without repeatedly tapping the settlement.
    """
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    left, top, right, bottom = 540, 390, 750, 425
    region = hsv[top:bottom, left:right]
    green = cv2.inRange(
        region,
        np.array([35, 80, 70], dtype=np.uint8),
        np.array([95, 255, 255], dtype=np.uint8),
    )
    matching_rows = 0
    for row_index in range(10, min(29, green.shape[0])):
        row = green[row_index] > 0
        boundaries = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        starts = np.where(boundaries == 1)[0]
        ends = np.where(boundaries == -1)[0]
        row_matches = any(
            25 <= int(start) <= 75 and 25 <= int(end - start) <= 175
            for start, end in zip(starts, ends)
        )
        matching_rows = matching_rows + 1 if row_matches else 0
        if matching_rows >= 4:
            return True
    return False


def research_radial_menu_is_visible(before_bgr, after_bgr):
    """Confirm that the centred laboratory exposed its research radial action.

    Settlement timers, units and event art animate continuously, so a global
    frame difference is not evidence that the radial menu opened.  The actual
    research control occupies a stable lower-right sector beside the centred
    laboratory and changes that sector substantially.
    """
    before, _scale_x, _scale_y = _reference_frame(before_bgr)
    after, _after_scale_x, _after_scale_y = _reference_frame(after_bgr)
    if before is None or after is None:
        return False
    left, top, right, bottom = 720, 345, 855, 470
    change = float(
        cv2.absdiff(
            before[top:bottom, left:right],
            after[top:bottom, left:right],
        ).mean()
    )
    return change >= 10.0


def research_tree_is_visible(frame_bgr):
    """Return whether a full personal-research tree/detail panel is open."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Both economy and war research use the same large dark panel.  This guard
    # deliberately does not depend on language, branch title or project text.
    panel = gray[90:650, 120:1160]
    side_tabs = gray[100:610, 35:110]
    return (
        float(np.mean(panel < 80)) >= 0.72
        and float(np.mean(side_tabs < 95)) >= 0.72
    )


def research_branch_is_selected(frame_bgr, branch):
    """Confirm the selected research branch from its highlighted side tab."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None or branch not in {"economy", "war"}:
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    regions = {
        "economy": hsv[115:225, 35:110],
        "war": hsv[245:355, 35:110],
    }

    def highlight_ratio(region):
        return float(
            np.mean(
                (region[:, :, 0] >= 8)
                & (region[:, :, 0] <= 42)
                & (region[:, :, 1] >= 55)
                & (region[:, :, 2] >= 95)
            )
        )

    selected = highlight_ratio(regions[branch])
    other = highlight_ratio(regions["war" if branch == "economy" else "economy"])
    return selected >= 0.035 and selected >= other + 0.02


def research_tree_progress_is_active(frame_bgr):
    """Detect an already-running project in the open research tree.

    The settlement progress bar is sometimes hidden even though opening the
    laboratory shows a countdown, a long progress track and the large gold
    Speed-up button at the top of either research branch.  Detecting this
    stable control pair prevents an active project from being mistaken for an
    idle laboratory and repeatedly scanning completed nodes.
    """
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None or not research_tree_is_visible(frame):
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    button = hsv[55:125, 780:970]
    button_gold = (
        (button[:, :, 0] >= 8)
        & (button[:, :, 0] <= 42)
        & (button[:, :, 1] >= 65)
        & (button[:, :, 2] >= 115)
    ).astype(np.uint8)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        button_gold,
        8,
    )
    has_speed_button = any(
        115 <= int(stats[index, cv2.CC_STAT_WIDTH]) <= 185
        and 28 <= int(stats[index, cv2.CC_STAT_HEIGHT]) <= 62
        and int(stats[index, cv2.CC_STAT_AREA]) >= 2200
        for index in range(1, count)
    )

    track = hsv[80:108, 420:800]
    dark_track_ratio = float(np.mean(track[:, :, 2] <= 70))
    gold_track_ratio = float(
        np.mean(
            (track[:, :, 0] >= 8)
            & (track[:, :, 0] <= 42)
            & (track[:, :, 1] >= 55)
            & (track[:, :, 2] >= 105)
        )
    )
    return (
        has_speed_button
        and dark_track_ratio >= 0.35
        and gold_track_ratio >= 0.005
    )


def detect_login_saved_account_continue_target(frame_bgr):
    """Detect the Continue button on the saved IGG account confirmation page."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    account_card = gray[90:274, 238:1043]
    continue_button = hsv[294:360, 238:1043]
    other_account_button = hsv[379:445, 238:1043]

    dark_card = account_card < 125
    yellow_button = (
        (continue_button[:, :, 0] >= 15)
        & (continue_button[:, :, 0] <= 40)
        & (continue_button[:, :, 1] >= 80)
        & (continue_button[:, :, 2] >= 160)
    )
    neutral_button = (
        (other_account_button[:, :, 1] <= 45)
        & (other_account_button[:, :, 2] >= 150)
        & (other_account_button[:, :, 2] <= 245)
    )
    if (
        float(np.mean(dark_card)) < 0.65
        or float(np.mean(yellow_button)) < 0.70
        or float(np.mean(neutral_button)) < 0.70
    ):
        return None

    return int(round(640 * scale_x)), int(round(326 * scale_y))


def world_map_hud_is_visible(frame_bgr):
    """Recognize both world-map controls independently of the terrain color."""
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None:
        return False
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for name, (x,y,w,h) in (
        ('world_search_icon', (0,390,130,130)),
        ('world_shelter_label', (0,681,160,39)),
    ):
        marker = cv2.imread(str(Path(__file__).parent/'assets/navigation'/f'{name}.png'), 0)
        if marker is None:
            return False
        roi=gray[y:y+h,x:x+w]
        if roi.shape[0]<marker.shape[0] or roi.shape[1]<marker.shape[1]:
            return False
        _,score,_,at=cv2.minMaxLoc(cv2.matchTemplate(roi,marker,cv2.TM_CCOEFF_NORMED))
        if score<.85:
            return False
        crop=roi[at[1]:at[1]+marker.shape[0],at[0]:at[0]+marker.shape[1]]
        bright=marker>=200
        if not np.any(bright) or np.mean(crop[bright]>=150)<.8:
            return False
    return True


def detect_igg_id_selection_target(frame_bgr):
    """Detect the first saved-ID row in IGG's non-accessible WebView."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    body = gray[70:680, 0:1280]
    back_icon = gray[8:60, 8:62]
    close_icon = gray[8:60, 1210:1272]
    title = gray[10:58, 500:780]
    account_row = gray[128:196, 225:1055]
    link = hsv[198:260, 760:1080]

    blue_link = (
        (link[:, :, 0] >= 90)
        & (link[:, :, 0] <= 125)
        & (link[:, :, 1] >= 110)
        & (link[:, :, 2] >= 150)
    )
    if (
        float(np.mean(body >= 230)) < 0.94
        or not 0.01 <= float(np.mean(back_icon < 120)) <= 0.20
        or not 0.01 <= float(np.mean(close_icon < 160)) <= 0.20
        or float(np.mean(title < 120)) < 0.015
        or float(np.mean(account_row < 130)) < 0.006
        or float(np.mean(blue_link)) < 0.008
    ):
        return None

    return int(round(640 * scale_x)), int(round(162 * scale_y))


def equipment_report_screen_is_visible(frame_bgr):
    """Return whether Doomsday's full-screen equipment-report offer is open.

    The upper row contains free score-milestone rewards while the large lower
    banner is a paid offer. Keep this detector deliberately specific so the
    reward handler can never confuse another shop screen with this overlay.
    """
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    header = hsv[35:305, 160:1120]
    paid_panel = hsv[305:700, 155:1125]
    close_region = hsv[40:110, 1060:1140]

    pale_header = (header[:, :, 1] < 90) & (header[:, :, 2] > 105)
    red_panel = (
        ((paid_panel[:, :, 0] <= 15) | (paid_panel[:, :, 0] >= 170))
        & (paid_panel[:, :, 1] > 55)
        & (paid_panel[:, :, 2] > 65)
    )
    gold_close = (
        (close_region[:, :, 0] >= 5)
        & (close_region[:, :, 0] <= 40)
        & (close_region[:, :, 1] >= 45)
        & (close_region[:, :, 2] >= 105)
    )
    return (
        float(np.mean(pale_header)) >= 0.62
        and float(np.mean(red_panel)) >= 0.45
        and float(np.mean(gold_close)) >= 0.12
    )


def detect_equipment_report_free_reward_target(frame_bgr):
    """Find the next illuminated free reward in the equipment-report row.

    Only the five fixed upper milestone cards are inspected. In particular,
    this function cannot return a point inside the paid lower banner.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or not equipment_report_screen_is_visible(frame):
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    for center_x in (460, 590, 723, 854, 985):
        card = hsv[198:294, center_x - 50:center_x + 50]
        gold = (
            (card[:, :, 0] >= 8)
            & (card[:, :, 0] <= 40)
            & (card[:, :, 1] >= 55)
            & (card[:, :, 2] >= 125)
        )
        border = np.zeros(gold.shape, dtype=bool)
        border[:8, :] = True
        border[-8:, :] = True
        border[:, :8] = True
        border[:, -8:] = True
        if float(np.mean(gold[border])) >= 0.52:
            return (
                int(round(center_x * scale_x)),
                int(round(245 * scale_y)),
            )
    return None


def detect_equipment_report_close_target(frame_bgr):
    """Return the overlay close button only after no free reward remains."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or not equipment_report_screen_is_visible(frame):
        return None
    if detect_equipment_report_free_reward_target(frame) is not None:
        return None
    return int(round(1099 * scale_x)), int(round(72 * scale_y))


def detect_game_event_overlay_close_target(frame_bgr):
    """Detect a full-screen promotional overlay blocking account navigation."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    close_region = hsv[74:152, 1110:1195]
    alternate_close_region = hsv[70:220, 1020:1225]
    content = hsv[70:570, 150:1130]
    action_button = hsv[565:650, 440:840]
    gold_close = (
        (close_region[:, :, 0] >= 5)
        & (close_region[:, :, 0] <= 40)
        & (close_region[:, :, 1] >= 45)
        & (close_region[:, :, 2] >= 105)
    )
    alternate_gold_close = (
        (alternate_close_region[:, :, 0] >= 5)
        & (alternate_close_region[:, :, 0] <= 40)
        & (alternate_close_region[:, :, 1] >= 45)
        & (alternate_close_region[:, :, 2] >= 105)
    )
    rich_content = (content[:, :, 1] >= 55) & (content[:, :, 2] >= 75)
    gold_button = (
        (action_button[:, :, 0] >= 8)
        & (action_button[:, :, 0] <= 40)
        & (action_button[:, :, 1] >= 70)
        & (action_button[:, :, 2] >= 135)
    )
    rich_ratio = float(np.mean(rich_content))
    button_ratio = float(np.mean(gold_button))
    close_ratio = float(np.mean(gold_close))
    alternate_close_ratio = float(np.mean(alternate_gold_close))
    legacy_count, _legacy_labels, legacy_stats, legacy_centroids = (
        cv2.connectedComponentsWithStats(gold_close.astype(np.uint8), 8)
    )
    legacy_candidates = [
        (legacy_stats[index, cv2.CC_STAT_AREA], legacy_centroids[index])
        for index in range(1, legacy_count)
        if 350 <= legacy_stats[index, cv2.CC_STAT_AREA] <= 2000
        and 25 <= legacy_stats[index, cv2.CC_STAT_WIDTH] <= 70
        and 25 <= legacy_stats[index, cv2.CC_STAT_HEIGHT] <= 70
    ]
    if (
        0.035 <= close_ratio <= 0.25
        and rich_ratio >= 0.30
        and button_ratio >= 0.20
        and legacy_candidates
    ):
        _area, center = max(legacy_candidates, key=lambda item: item[0])
        return (
            int(round((1110 + float(center[0])) * scale_x)),
            int(round((74 + float(center[1])) * scale_y)),
        )
    if (
        not 0.015 <= alternate_close_ratio <= 0.16
        or rich_ratio < 0.24
        or button_ratio < 0.20
    ):
        return None
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        alternate_gold_close.astype(np.uint8),
        8,
    )
    candidates = [
        (stats[index, cv2.CC_STAT_AREA], centroids[index])
        for index in range(1, count)
        if 350 <= stats[index, cv2.CC_STAT_AREA] <= 3000
        and 25 <= stats[index, cv2.CC_STAT_WIDTH] <= 100
        and 25 <= stats[index, cv2.CC_STAT_HEIGHT] <= 70
    ]
    if not candidates:
        return None
    _area, center = max(candidates, key=lambda item: item[0])
    return (
        int(round((1020 + float(center[0])) * scale_x)),
        int(round((70 + float(center[1])) * scale_y)),
    )


def detect_igg_game_login_ok_target(frame_bgr):
    """Detect the final in-game confirmation shown after choosing an IGG ID."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dialog = gray[160:575, 315:965]
    cancel_button = hsv[478:540, 355:635]
    ok_button = hsv[478:540, 645:925]
    neutral_cancel = (
        (cancel_button[:, :, 0] <= 30)
        & (cancel_button[:, :, 1] <= 150)
        & (cancel_button[:, :, 2] >= 55)
        & (cancel_button[:, :, 2] <= 190)
    )
    gold_ok = (
        (ok_button[:, :, 0] >= 8)
        & (ok_button[:, :, 0] <= 40)
        & (ok_button[:, :, 1] >= 70)
        & (ok_button[:, :, 2] >= 145)
    )
    if (
        float(np.mean(dialog >= 145)) < 0.55
        or float(np.mean(neutral_cancel)) < 0.45
        or float(np.mean(gold_ok)) < 0.55
    ):
        return None
    # The map behind this modal may be bright (for example, desert terrain).
    # Check the panel itself, its two buttons and the IGG wording instead of
    # requiring a dark background. Purchase confirmations share this layout;
    # geometry alone must never authorize login.
    marker = cv2.imread(
        str(Path(__file__).parent / "assets/accounts/igg_id_confirmation_marker.png"),
        cv2.IMREAD_GRAYSCALE,
    )
    if marker is None:
        return None
    # Unity scales the modal briefly while the SDK closes. Its dark
    # background is valid; recognize the actual IGG wording at that scale.
    score = max(float(cv2.matchTemplate(
        gray[260:430, 370:930], cv2.resize(marker, None, fx=scale, fy=scale),
        cv2.TM_CCOEFF_NORMED,
    ).max()) for scale in (0.94, 0.96, 0.98, 1.0))
    if score < 0.82:
        return None
    return int(round(784 * scale_x)), int(round(508 * scale_y))


def detect_account_settings_back_target(frame_bgr):
    """Detect the in-game Account page shown after an IGG ID is selected."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    panel = gray[86:668, 133:1147]
    back_button = hsv[594:643, 507:773]
    dark_panel = panel < 105
    gold_button = (
        (back_button[:, :, 0] >= 10)
        & (back_button[:, :, 0] <= 40)
        & (back_button[:, :, 1] >= 55)
        & (back_button[:, :, 2] >= 135)
    )
    if float(np.mean(dark_panel)) < 0.72 or float(np.mean(gold_button)) < 0.55:
        return None
    return int(round(640 * scale_x)), int(round(618 * scale_y))


def detect_account_details_close_target(frame_bgr):
    """Detect the outer Account details page reached after the login-method page."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    join_rows = (
        hsv[158:191, 950:1130],
        hsv[229:263, 950:1130],
        hsv[371:406, 950:1130],
    )
    gold_fractions = []
    for row in join_rows:
        gold = (
            (row[:, :, 0] >= 8)
            & (row[:, :, 0] <= 40)
            & (row[:, :, 1] >= 35)
            & (row[:, :, 2] >= 120)
        )
        gold_fractions.append(float(np.mean(gold)))
    if min(gold_fractions) < 0.55:
        return None
    return int(round(1133 * scale_x)), int(round(43 * scale_y))


def detect_settings_close_target(frame_bgr):
    """Detect the root in-game Settings grid after account dialogs are closed."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    tile_regions = (
        hsv[118:263, 188:387],
        hsv[118:263, 430:629],
        hsv[118:263, 670:869],
        hsv[118:263, 910:1110],
    )
    tile_fractions = []
    for tile in tile_regions:
        muted_brown = (
            (tile[:, :, 0] >= 5)
            & (tile[:, :, 0] <= 35)
            & (tile[:, :, 1] >= 15)
            & (tile[:, :, 1] <= 180)
            & (tile[:, :, 2] >= 40)
            & (tile[:, :, 2] <= 180)
        )
        tile_fractions.append(float(np.mean(muted_brown)))
    if min(tile_fractions) < 0.35:
        return None
    return int(round(1133 * scale_x)), int(round(43 * scale_y))


def detect_commander_settings_target(frame_bgr):
    frame, sx, sy = _reference_frame(frame_bgr)
    if frame is None:
        return None
    directory = Path(__file__).parent / "assets/accounts"
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for name, region in (("commander_title.png", gray[15:90, 80:540]),
                         ("commander_settings.png", gray[645:710, 100:260])):
        marker = cv2.imread(str(directory / name), cv2.IMREAD_GRAYSCALE)
        if marker is None or cv2.matchTemplate(region, marker, cv2.TM_CCOEFF_NORMED).max() < 0.85:
            return None
    return round(180 * sx), round(637 * sy)


def detect_commander_profile_back_target(frame_bgr):
    """Detect the commander profile screen that remains under Settings."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    if detect_commander_settings_target(frame) is not None:
        return int(round(47 * scale_x)), int(round(45 * scale_y))

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    back = hsv[12:82, 12:90]
    right_panel = gray[26:286, 808:1274]
    gold_back = (
        (back[:, :, 0] >= 8)
        & (back[:, :, 0] <= 40)
        & (back[:, :, 1] >= 70)
        & (back[:, :, 2] >= 110)
    )
    if float(np.mean(gold_back)) < 0.06 or float(np.mean(right_panel < 95)) < 0.75:
        return None
    return int(round(47 * scale_x)), int(round(45 * scale_y))


def collective_search_not_found_is_visible(frame_bgr):
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None:
        return False
    marker = cv2.imread(str(Path(__file__).parent / "assets/collective/not_found.png"), 0)
    if marker is None:
        return False
    gray = cv2.cvtColor(frame[80:200, 100:1180], cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(gray, marker, cv2.TM_CCOEFF_NORMED).max()) >= .82


def zombie_search_not_found_is_visible(frame_bgr):
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None:
        return False
    gray = cv2.cvtColor(frame[80:200, 100:1180], cv2.COLOR_BGR2GRAY)
    for name in ('not_found_zombie', 'not_found_message'):
        marker = cv2.imread(str(Path(__file__).parent / f'assets/zombie/{name}.png'), 0)
        if marker is None or float(cv2.matchTemplate(gray, marker, cv2.TM_CCOEFF_NORMED).max()) < .82:
            return False
    return True


def zombie_target_card_is_visible(frame_bgr):
    """Require the zombie heading and Attack action on the same target card."""
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None:
        return False
    directory = Path(__file__).parent / 'assets/zombie'
    title = cv2.imread(str(directory / 'card_title.png'), 0)
    attack = cv2.imread(str(directory / 'card_attack.png'), 0)
    if title is None or attack is None:
        return False
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _low, score, _at, (x,y) = cv2.minMaxLoc(cv2.matchTemplate(gray[120:280], title, cv2.TM_CCOEFF_NORMED))
    if score < .84:
        return False
    y += 120
    region = gray[y+320:min(650,y+410), max(0,x-55):min(1280,x+245)]
    return (region.shape[0] >= attack.shape[0] and region.shape[1] >= attack.shape[1]
            and float(cv2.matchTemplate(region, attack, cv2.TM_CCOEFF_NORMED).max()) >= .84)


def collective_target_card_is_visible(frame_bgr):
    """Require the collective-mind name and its own Rally action on one card."""
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None:
        return False
    directory = Path(__file__).parent / "assets/collective"
    title = cv2.imread(str(directory / "card_title.png"), 0)
    rally = cv2.imread(str(directory / "card_rally.png"), 0)
    if title is None or rally is None:
        return False
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _low, score, _at, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(gray[120:280], title, cv2.TM_CCOEFF_NORMED))
    if score < .84:
        return False
    y += 120
    region = gray[y+280:min(650, y+410), x+150:min(1280, x+350)]
    return (region.shape[0] >= rally.shape[0] and region.shape[1] >= rally.shape[1]
            and float(cv2.matchTemplate(region, rally, cv2.TM_CCOEFF_NORMED).max()) >= .84)


def collective_target_busy_is_visible(frame_bgr):
    """The game permits only one alliance rally against a particular target."""
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None:
        return False
    marker = cv2.imread(str(Path(__file__).parent / "assets/collective/target_busy.png"), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return False
    region = cv2.cvtColor(frame[70:220, 150:1130], cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(region, marker, cv2.TM_CCOEFF_NORMED).max()) >= 0.85


def detect_collective_tutorial_continue_target(frame_bgr):
    """Detect the guided collective-mind overlay that blocks the map."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    bottom_gray = cv2.cvtColor(frame[560:720], cv2.COLOR_BGR2GRAY)
    dark_ratio = float(np.count_nonzero(bottom_gray < 85)) / float(bottom_gray.size)
    # Each page replaces the guide character, but the dialogue itself stays
    # strongly dimmed and is distinct from the ordinary map HUD.
    if dark_ratio < 0.82:
        return None

    return int(round(640 * scale_x)), int(round(650 * scale_y))


def detect_prize_hunt_squad_confirmation_target(frame_bgr):
    """Detect the squad/preset mismatch confirmation shown inside prize hunt."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    title = hsv[160:215, 315:965]
    panel = hsv[215:475, 350:930]
    confirm = hsv[480:535, 640:930]

    brown_title = (
        (title[:, :, 0] <= 30)
        & (title[:, :, 1] >= 30)
        & (title[:, :, 2] >= 40)
        & (title[:, :, 2] <= 150)
    )
    light_panel = (panel[:, :, 1] < 100) & (panel[:, :, 2] >= 110)
    yellow_confirm = (
        (confirm[:, :, 0] >= 8)
        & (confirm[:, :, 0] <= 42)
        & (confirm[:, :, 1] >= 80)
        & (confirm[:, :, 2] >= 130)
    )
    if (
        float(np.mean(brown_title)) < 0.55
        or float(np.mean(light_panel)) < 0.65
        or float(np.mean(yellow_confirm)) < 0.45
    ):
        return None

    return int(round(784 * scale_x)), int(round(508 * scale_y))


def detect_alliance_donation_entry_target(frame_bgr, entry_template, confidence=0.88):
    """Match the stable top of the alliance icon despite its warning badge.

    The canonical entry image includes a dynamic red warning at its lower
    right. Keep its original threshold and target centre, but search only its
    unchanged upper pixels in the bottom HUD. The caller must confirm home.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or not isinstance(entry_template, np.ndarray):
        return None
    if entry_template.shape != (54, 57, 3):
        return None
    try:
        threshold = float(confidence)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(threshold) or threshold > 1.0:
        return None
    threshold = max(0.88, threshold)
    needle = entry_template[:23, :]
    # Do not let a changed/custom constant image match every HUD pixel.
    if float(np.std(needle)) < 1.0:
        return None
    left, top, right, bottom = 915, 595, 1020, 705
    result = cv2.matchTemplate(frame[top:bottom, left:right], needle, cv2.TM_CCOEFF_NORMED)
    _minimum, score, _minimum_location, location = cv2.minMaxLoc(result)
    if score < threshold:
        return None
    return (
        int(round((left + location[0] + entry_template.shape[1] // 2) * scale_x)),
        int(round((top + location[1] + entry_template.shape[0] // 2) * scale_y)),
    )


def alliance_donation_attempts_exhausted(frame_bgr):
    """Confirm the displayed donation counter is exactly ``: 0/30``.

    This is positive counter recognition, not the absence of an active
    donation button. The colon is part of the glyph mask so 10/30 and 20/30
    cannot be mistaken for zero. Unknown layouts remain unconfirmed.
    """
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None or frame.shape[2] != 3:
        return False
    # Orange glyphs captured from the game's counter at 1280 x 720.
    glyph_rows = (
        "..........#####.......###..#####.....#####..",
        ".........#######......###.#######...#######.",
        "........###...###....###.###...###.###...###",
        ".##.....###...###....###.##....###.###...###",
        "###.....###...###....##........###.###...###",
        "........###...###...###......####..###...###",
        "........###...###...###....#####...###...###",
        "........###...###...##.......####..###...###",
        "........###...###..###.........###.###...###",
        "........###...###..##....##....###.###...###",
        "........###...###.###....###...###.###...###",
        "###......#######..###....########...#######.",
        "###.......######..##......######.....######.",
        ".................###........................",
    )
    glyphs = np.array(
        [[255 if pixel == "#" else 0 for pixel in row] for row in glyph_rows],
        dtype=np.uint8,
    )
    counter = cv2.cvtColor(frame[490:525, 1040:1140], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(counter, np.array((10, 100, 110)), np.array((40, 255, 255)))
    score = cv2.minMaxLoc(cv2.matchTemplate(mask, glyphs, cv2.TM_CCOEFF_NORMED))[1]
    return bool(score >= 0.94)


def _alliance_marked_label_location(frame, region):
    """Recognize the actual Marked label even while its red ribbon pulses."""
    marker = imread_unicode(
        Path(__file__).parent / "assets/alliance_donations/marked_label.png",
        cv2.IMREAD_GRAYSCALE,
    )
    if marker is None:
        return None
    left, top, right, bottom = region
    gray = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
    best = (0.82, None)
    for scale in (0.9, 1.0, 1.1):
        template = cv2.resize(marker, None, fx=scale, fy=scale)
        _low, score, _low_at, location = cv2.minMaxLoc(
            cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        )
        if score > best[0]:
            x, y = location
            best = score, (left + x + template.shape[1] / 2,
                           top + y + template.shape[0] / 2)
    return best[1]


def alliance_marked_project_is_visible(frame_bgr):
    """Confirm the marked project panel, not just a red tree notification."""
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None or _alliance_marked_label_location(frame, (390, 100, 565, 155)) is None:
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Both resource and premium buttons belong to the donation panel. The
    # premium button is only a visual guard; it is never clicked.
    ordinary = hsv[562:602, 865:1115]
    premium = hsv[562:602, 570:820]
    return bool(
        (np.mean((ordinary[:, :, 0] >= 8) & (ordinary[:, :, 0] <= 42)
                 & (ordinary[:, :, 1] >= 70) & (ordinary[:, :, 2] >= 100)) >= 0.35
         or alliance_donation_attempts_exhausted(frame))
        and np.mean((premium[:, :, 0] >= 115) & (premium[:, :, 0] <= 160)
                    & (premium[:, :, 1] >= 40)) >= 0.35
    )


def detect_alliance_marked_project_target(frame_bgr):
    """Find the alliance technology card carrying the compact red marker."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    label = _alliance_marked_label_location(frame, (170, 155, 1100, 660))
    if label is not None:
        label_x, label_y = label
        return round((label_x - 110) * scale_x), round((label_y + 16) * scale_y)

    return None


def detect_radar_notification_targets(frame_bgr):
    """Find actionable radar markers by their compact red notification dot."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return []

    blue, green, red = cv2.split(frame)
    blue = blue.astype(np.float32)
    green = green.astype(np.float32)
    red = red.astype(np.float32)
    mask = (
        (red > 120)
        & (red > 2.2 * (green + 1.0))
        & (red > 2.2 * (blue + 1.0))
    ).astype(np.uint8) * 255

    # Exclude the HUD and the right-side squad list. Only map markers live here.
    mask[:130, :] = 0
    mask[590:, :] = 0
    mask[:, :250] = 0
    mask[:, 1080:] = 0
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
    )

    targets = []
    contours, _hierarchy = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = float(cv2.contourArea(contour))
        perimeter = float(cv2.arcLength(contour, True))
        circularity = 4.0 * math.pi * area / (perimeter * perimeter) if perimeter else 0.0
        extent = area / float(width * height) if width and height else 0.0
        if not (
            100.0 <= area <= 320.0
            and 12 <= width <= 23
            and 12 <= height <= 23
            and 0.7 <= width / float(height) <= 1.4
            and circularity >= 0.55
            and extent >= 0.5
        ):
            continue

        # The notification dot is attached to the marker's upper-right edge.
        target_x = (x + width / 2.0 - 24.0) * scale_x
        target_y = (y + height / 2.0 + 30.0) * scale_y
        targets.append((int(round(target_x)), int(round(target_y))))

    return sorted(set(targets), key=lambda point: (point[1], point[0]))


def radar_task_card_is_visible(frame_bgr):
    """Recognize the clipboard itself, including cards with disabled actions."""
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None:
        return False
    clip = imread_unicode(Path(__file__).parent / "assets/radar/card_clip.png", cv2.IMREAD_GRAYSCALE)
    if clip is None:
        return False
    gray = cv2.cvtColor(frame[70:190, 70:435], cv2.COLOR_BGR2GRAY)
    return bool(cv2.matchTemplate(gray, clip, cv2.TM_CCOEFF_NORMED).max() >= 0.82)


def radar_overview_is_visible(frame_bgr):
    """Recognize the radar map without relying on one animated template."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    def color_ratio(region, low, high):
        if region.size == 0:
            return 0.0
        mask = cv2.inRange(
            region,
            np.array(low, dtype=np.uint8),
            np.array(high, dtype=np.uint8),
        )
        return float(np.count_nonzero(mask)) / float(mask.size)

    back_button = hsv[0:90, 0:90]
    energy_bar = hsv[15:65, 960:1245]
    execute_all = hsv[510:710, 15:190]
    gold_low = (8, 70, 80)
    gold_high = (42, 255, 255)
    return bool(
        color_ratio(back_button, gold_low, gold_high) >= 0.06
        and color_ratio(energy_bar, (35, 75, 70), (95, 255, 255)) >= 0.08
        and color_ratio(execute_all, gold_low, gold_high) >= 0.05
    )


def radar_marker_has_notification(frame_bgr, bbox, padding=24):
    """Return whether a radar marker match contains a nearby red notification dot."""
    if not bbox or len(bbox) != 4:
        return False
    left, top, width, height = map(int, bbox)
    margin = max(0, int(padding))
    right = left + width
    bottom = top + height
    return any(
        left - margin <= target_x <= right + margin
        and top - margin <= target_y <= bottom + margin
        for target_x, target_y in detect_radar_notification_targets(frame_bgr)
    )


def radar_category_has_notification(frame_bgr, task_id):
    """Detect the red badge on the quick or march radar category button."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    task_regions = {
        "radar_quick": (1180, 100, 1280, 205),
        "radar_marches": (1180, 205, 1280, 315),
    }
    region = task_regions.get(str(task_id or ""))
    if region is None:
        return False

    left, top, right, bottom = region
    blue, green, red = cv2.split(frame[top:bottom, left:right])
    blue = blue.astype(np.float32)
    green = green.astype(np.float32)
    red = red.astype(np.float32)
    mask = (
        (red > 120)
        & (red > 2.0 * (green + 1.0))
        & (red > 2.0 * (blue + 1.0))
    ).astype(np.uint8) * 255

    component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask)
    for index in range(1, component_count):
        _x, _y, width, height, area = map(int, stats[index])
        if (
            80 <= area <= 360
            and 10 <= width <= 24
            and 10 <= height <= 24
            and 0.65 <= width / float(height) <= 1.5
        ):
            return True
    return False


def detect_radar_card_action_target(frame_bgr):
    """Return the center of an enabled yellow action button on a radar card."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    button = hsv[592:649, 108:380]
    enabled_mask = cv2.inRange(
        button,
        np.array([12, 120, 160], dtype=np.uint8),
        np.array([42, 255, 255], dtype=np.uint8),
    )
    if float(np.count_nonzero(enabled_mask)) / float(enabled_mask.size) < 0.20:
        return None
    return int(round(244 * scale_x)), int(round(621 * scale_y))


def radar_card_has_active_countdown(frame_bgr):
    """Recognize a timer only on a radar card explicitly marked in progress.

    Available cards also show six digits in this strip: their event expiry
    ("Завершится через") is not evidence of a dispatched squad. Require the
    game's "В процессе" status inside the card before inspecting its timer.
    """
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    in_progress_label = imread_unicode(
        Path(__file__).parent / "assets/radar/in_progress_label.png",
        cv2.IMREAD_GRAYSCALE,
    )
    if in_progress_label is None:
        return False
    card_status = gray[300:650, 65:430]
    status_visible = False
    for scale in (0.9, 1.0, 1.1):
        label = cv2.resize(in_progress_label, None, fx=scale, fy=scale)
        if float(
            cv2.matchTemplate(card_status, label, cv2.TM_CCOEFF_NORMED).max()
        ) >= 0.82:
            status_visible = True
            break
    if not status_visible:
        return False

    timer_strip = gray[338:378, 292:430]
    if timer_strip.size == 0:
        return False
    dark = (timer_strip < 105).astype(np.uint8) * 255
    component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        dark
    )
    glyphs = []
    for index in range(1, component_count):
        x, y, width, height, area = map(int, stats[index])
        if 5 <= width <= 14 and 11 <= height <= 22 and area >= 24:
            glyphs.append((x, y, width, height))

    # The six digits share a baseline. Colons are intentionally ignored
    # because their two tiny dots are affected most by capture scaling.
    for anchor in glyphs:
        aligned = sorted(
            (
                glyph
                for glyph in glyphs
                if abs(glyph[1] - anchor[1]) <= 3
                and abs(glyph[3] - anchor[3]) <= 4
            ),
            key=lambda glyph: glyph[0],
        )
        if len(aligned) < 6:
            continue
        for start in range(len(aligned) - 5):
            run = aligned[start : start + 6]
            centers = [x + width / 2.0 for x, _y, width, _height in run]
            span = centers[-1] - centers[0]
            gaps = [right - left for left, right in zip(centers, centers[1:])]
            if 65.0 <= span <= 105.0 and all(7.0 <= gap <= 25.0 for gap in gaps):
                return True
    return False


def detect_radar_pass_purchase_cancel_target(frame_bgr):
    """Return only the Cancel button from the radar-pass purchase dialog."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    dialog_body = hsv[210:470, 335:945]
    cancel_button = hsv[480:535, 360:630]
    ok_button = hsv[480:535, 650:920]

    neutral_body = (
        (dialog_body[:, :, 1] <= 65)
        & (dialog_body[:, :, 2] >= 130)
    )
    yellow_lower = np.array([10, 80, 120], dtype=np.uint8)
    yellow_upper = np.array([42, 255, 255], dtype=np.uint8)
    cancel_yellow = cv2.inRange(cancel_button, yellow_lower, yellow_upper)
    ok_yellow = cv2.inRange(ok_button, yellow_lower, yellow_upper)

    body_fraction = float(np.count_nonzero(neutral_body)) / float(neutral_body.size)
    cancel_yellow_fraction = float(np.count_nonzero(cancel_yellow)) / float(cancel_yellow.size)
    ok_yellow_fraction = float(np.count_nonzero(ok_yellow)) / float(ok_yellow.size)
    if body_fraction < 0.70 or ok_yellow_fraction < 0.45 or cancel_yellow_fraction > 0.08:
        return None
    return int(round(496 * scale_x)), int(round(508 * scale_y))


def detect_radar_world_action_target(frame_bgr):
    """Find a yellow action button shown after a radar card sends us to the map."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    roi = hsv[440:620, 800:1160]
    mask = cv2.inRange(
        roi,
        np.array([8, 100, 130], dtype=np.uint8),
        np.array([45, 255, 255], dtype=np.uint8),
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        np.ones((5, 5), dtype=np.uint8),
    )

    candidates = []
    contours, _hierarchy = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = float(cv2.contourArea(contour))
        if 150 <= width <= 290 and 30 <= height <= 70 and area >= 3500.0:
            candidates.append((area, x + width / 2.0 + 800, y + height / 2.0 + 440))
    if not candidates:
        return None
    _area, target_x, target_y = max(candidates)
    return int(round(target_x * scale_x)), int(round(target_y * scale_y))


def detect_radar_deployment_prompt_target(frame_bgr):
    """Return the safe Create squad button from the radar deployment prompt."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    panel = hsv[40:310, 835:1105]
    neutral_panel = (
        (panel[:, :, 1] <= 120)
        & (panel[:, :, 2] >= 110)
    )
    if float(np.count_nonzero(neutral_panel)) / float(neutral_panel.size) < 0.45:
        return None

    def enabled_button_fraction(top, bottom):
        button = hsv[top:bottom, 860:1085]
        mask = cv2.inRange(
            button,
            np.array([8, 80, 140], dtype=np.uint8),
            np.array([45, 255, 255], dtype=np.uint8),
        )
        return float(np.count_nonzero(mask)) / float(mask.size)

    # Requiring both stacked buttons prevents a generic world-map action from
    # being mistaken for the deployment prompt.
    if enabled_button_fraction(180, 235) < 0.20:
        return None
    if enabled_button_fraction(240, 295) < 0.20:
        return None
    return int(round(970 * scale_x)), int(round(210 * scale_y))


def detect_radar_squad_march_target(frame_bgr):
    """Return the enabled March button from the world-map squad panel.

    The live 4/4 deployment layout renders this button narrower than the
    exported template.  Requiring the pale squad-size panel and the dark hero
    roster keeps this fallback specific to the deployment screen instead of a
    generic yellow world-map action.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    panel = hsv[40:310, 835:1105]
    button = hsv[218:263, 875:1065]
    roster = hsv[65:550, 1135:1278]
    if not panel.size or not button.size or not roster.size:
        return None

    pale_panel = (panel[:, :, 1] <= 120) & (panel[:, :, 2] >= 110)
    gold_button = (
        (button[:, :, 0] >= 8)
        & (button[:, :, 0] <= 45)
        & (button[:, :, 1] >= 70)
        & (button[:, :, 2] >= 120)
    )
    dark_roster = roster[:, :, 2] <= 90
    if (
        float(np.mean(pale_panel)) < 0.55
        or float(np.mean(gold_button)) < 0.45
        or float(np.mean(dark_roster)) < 0.45
    ):
        return None
    return int(round(970 * scale_x)), int(round(240 * scale_y))


def zombie_camp_checkbox_is_checked(frame_bgr, attack_target=None):
    """Detect the optional 'set up camp after attack' checkmark."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    attack_x, attack_y = (966, 561) if attack_target is None else (
        attack_target[0] / scale_x, attack_target[1] / scale_y,
    )
    center_x, center_y = round(attack_x - 146), round(attack_y - 43)
    if not (11 <= center_x < frame.shape[1] - 11 and 12 <= center_y < frame.shape[0] - 12):
        return False
    checkbox_inner = frame[center_y - 12:center_y + 12, center_x - 11:center_x + 11]
    hsv = cv2.cvtColor(checkbox_inner, cv2.COLOR_BGR2HSV)
    colored_bright = (
        (hsv[:, :, 1] >= 80)
        & (hsv[:, :, 2] >= 135)
    )
    return float(np.count_nonzero(colored_bright)) / float(colored_bright.size) >= 0.08


def detect_camped_march_card_targets(frame_bgr):
    """Return visible march cards whose status icon is the cyan camp tent."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return []

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    targets = []
    for top in (190, 260, 330, 400):
        # Cyan player names and world objects can pass the color test at the
        # same screen position when the march panel is collapsed. Require the
        # portrait card frame before interpreting cyan pixels as a camp icon.
        card_roi_top = max(0, top - 15)
        card_roi_bottom = min(frame.shape[0], top + 80)
        card_roi_left, card_roi_right = 1155, 1275
        card_roi = frame[
            card_roi_top:card_roi_bottom,
            card_roi_left:card_roi_right,
        ]
        if card_roi.size == 0:
            continue
        card_gray = cv2.cvtColor(card_roi, cv2.COLOR_BGR2GRAY)
        card_edges = cv2.Canny(card_gray, 60, 140)
        contours, _hierarchy = cv2.findContours(
            card_edges,
            cv2.RETR_LIST,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        card_frame_present = False
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            absolute_x = card_roi_left + x
            absolute_y = card_roi_top + y
            if (
                75 <= width <= 110
                and 50 <= height <= 80
                and absolute_x <= 1180
                and absolute_x + width >= 1250
                and top - 15 <= absolute_y <= top + 12
            ):
                card_frame_present = True
                break
        if not card_frame_present:
            # An unselected portrait can have an open/low-contrast border,
            # so Canny does not always yield one rectangular contour. In
            # that case require the actual tent icon, not just cyan pixels.
            tent = imread_unicode(
                Path(__file__).parent / "assets/marches/camp_status.png",
                cv2.IMREAD_GRAYSCALE,
            )
            status_gray = cv2.cvtColor(frame[top+38:top+66, 1237:1263], cv2.COLOR_BGR2GRAY)
            if tent is None or float(cv2.matchTemplate(status_gray, tent, cv2.TM_CCOEFF_NORMED).max()) < 0.88:
                continue

        status_roi = hsv[top + 38:top + 66, 1237:1263]
        if status_roi.size == 0:
            continue
        cyan = cv2.inRange(
            status_roi,
            np.array([75, 90, 90], dtype=np.uint8),
            np.array([105, 255, 255], dtype=np.uint8),
        )
        if int(np.count_nonzero(cyan)) < 80:
            continue
        targets.append(
            (
                int(round(1218 * scale_x)),
                int(round((top + 32) * scale_y)),
            )
        )
    return targets


def detect_march_retreat_target(frame_bgr):
    """Recognise retreat and its neighbouring emoji action on a selected squad."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    # Circle fitting drifts on the moving map background and sometimes puts
    # the two button centres at different heights. Match their actual icons;
    # require both actions in the same layout to reject unrelated gold UI.
    directory = Path(__file__).parent / "assets/marches"
    retreat = imread_unicode(directory / "retreat_icon.png", cv2.IMREAD_GRAYSCALE)
    emoji = imread_unicode(directory / "emoji_icon.png", cv2.IMREAD_GRAYSCALE)
    if retreat is None or emoji is None:
        return None
    roi_left, roi_top = 280, 360
    gray = cv2.cvtColor(frame[roi_top:590, roi_left:920], cv2.COLOR_BGR2GRAY)
    best_score, best_target = 0.0, None
    # World-map zoom also scales these two actions, independently of the
    # emulator resolution. At minimum zoom they are about 62.5% of normal.
    for scale in (0.50, 0.55, 0.60, 0.625, 0.65, 0.675, 0.70, 0.75, 0.80,
                  0.85, 0.90, 0.95, 1.0, 1.05, 1.10, 1.15, 1.20):
        arrow = cv2.resize(retreat, None, fx=scale, fy=scale)
        face = cv2.resize(emoji, None, fx=scale, fy=scale)
        ah, aw = arrow.shape
        fh, fw = face.shape
        scores = cv2.matchTemplate(gray, arrow, cv2.TM_CCOEFF_NORMED)
        for _candidate in range(3):
            _low, arrow_score, _low_at, (x, y) = cv2.minMaxLoc(scores)
            if arrow_score < 0.84:
                break
            # Suppress this peak before considering another matching arrow.
            scores[max(0, y-ah//2):y+ah//2+1, max(0, x-aw//2):x+aw//2+1] = -1
            cx, cy = x + aw / 2, y + ah / 2
            face_x, face_y = round(cx - 113 * scale - fw / 2), round(cy - fh / 2)
            left, top = max(0, face_x - 6), max(0, face_y - 6)
            region = gray[top:face_y+fh+7, left:face_x+fw+7]
            if region.shape[0] < fh or region.shape[1] < fw:
                continue
            face_score = float(cv2.matchTemplate(region, face, cv2.TM_CCOEFF_NORMED).max())
            score = min(arrow_score, face_score)
            if face_score >= 0.84 and score > best_score:
                best_score = score
                best_target = (
                    round((roi_left + cx) * scale_x),
                    round((roi_top + cy) * scale_y),
                )
    return best_target


def detect_back_confirmation_cancel_target(frame_bgr):
    """Return Cancel for the confirmation dialog opened by Android Back."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    modal_body = frame[210:470, 330:950]
    left_button = frame[482:535, 360:632]
    right_button = frame[482:535, 650:920]
    if not modal_body.size or not left_button.size or not right_button.size:
        return None

    body_hsv = cv2.cvtColor(modal_body, cv2.COLOR_BGR2HSV)
    left_hsv = cv2.cvtColor(left_button, cv2.COLOR_BGR2HSV)
    right_hsv = cv2.cvtColor(right_button, cv2.COLOR_BGR2HSV)
    pale_body = (body_hsv[:, :, 1] <= 55) & (body_hsv[:, :, 2] >= 135)
    gold_button = (
        (right_hsv[:, :, 0] >= 8)
        & (right_hsv[:, :, 0] <= 40)
        & (right_hsv[:, :, 1] >= 70)
        & (right_hsv[:, :, 2] >= 120)
    )
    left_gold = (
        (left_hsv[:, :, 0] >= 8)
        & (left_hsv[:, :, 0] <= 40)
        & (left_hsv[:, :, 1] >= 70)
        & (left_hsv[:, :, 2] >= 120)
    )
    # A connection-error modal has one centred gold OK button spanning both
    # halves.  Android Back confirmation has a dark/grey Cancel on the left and
    # a separate gold action on the right.  Without this guard the generic
    # recovery tapped OK forever and mislabeled it as cancelling game exit.
    if (
        float(np.mean(pale_body)) < 0.45
        or float(np.mean(gold_button)) < 0.35
        or float(np.mean(left_gold)) > 0.20
    ):
        return None
    return int(round(495 * scale_x)), int(round(509 * scale_y))


def healing_auto_fill_is_checked(frame_bgr):
    """Detect the hospital auto-fill tick without relying on its caption."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    # Ignore the permanently bright checkbox border. Only the inner area can
    # contain the diagonal checkmark, so an empty box must remain unchecked.
    checkbox_inner = frame[666:687, 800:822]
    hsv = cv2.cvtColor(checkbox_inner, cv2.COLOR_BGR2HSV)
    bright_mark = (hsv[:, :, 2] >= 165) & (hsv[:, :, 1] <= 110)
    return float(np.count_nonzero(bright_mark)) / float(bright_mark.size) >= 0.08


def healing_selection_is_empty(frame_bgr):
    """Confirm that the hospital's global clear button removed every troop."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    sliders = hsv[145:465, 760:1010]
    green_fill = (
        (sliders[:, :, 0] >= 35)
        & (sliders[:, :, 0] <= 90)
        & (sliders[:, :, 1] >= 80)
        & (sliders[:, :, 2] >= 80)
    )
    if float(np.count_nonzero(green_fill)) / float(green_fill.size) > 0.005:
        return False

    # A zero selection also disables the normal Heal button. Requiring both
    # signals prevents a transient or partially rendered slider from passing.
    heal_button = hsv[592:642, 900:1155]
    colored_button = (
        (heal_button[:, :, 1] >= 45)
        & (heal_button[:, :, 2] >= 90)
    )
    return (
        float(np.count_nonzero(colored_button)) / float(colored_button.size)
        <= 0.08
    )


def healing_troop_form_is_visible(frame_bgr):
    """Detect the wounded-troop form even while its Heal button is disabled."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    def red_ratio(region):
        red = (
            ((region[:, :, 0] <= 12) | (region[:, :, 0] >= 170))
            & (region[:, :, 1] >= 80)
            & (region[:, :, 2] >= 80)
        )
        return float(np.count_nonzero(red)) / float(red.size)

    def yellow_ratio(region):
        yellow = (
            (region[:, :, 0] >= 12)
            & (region[:, :, 0] <= 38)
            & (region[:, :, 1] >= 70)
            & (region[:, :, 2] >= 80)
        )
        return float(np.count_nonzero(yellow)) / float(yellow.size)

    # The illustration on the left changes with the wounded troop type. Some
    # variants have no large red quick-heal case, so also recognize the stable
    # dark header and gold auto-fill strip that frame every troop form.
    quick_heal_case = hsv[140:380, 230:630]
    hospital_capacity = hsv[515:630, 220:330]
    troop_rows = hsv[115:500, 650:1150]
    ordinary_heal = hsv[592:642, 900:1155]
    form_header = hsv[48:96, 110:1170]
    auto_fill_bar = hsv[658:705, 575:1160]
    dark_rows = troop_rows[:, :, 2] <= 90
    dark_rows_ratio = (
        float(np.count_nonzero(dark_rows)) / float(dark_rows.size)
    )
    dark_header_ratio = float(
        np.count_nonzero(form_header[:, :, 2] <= 90)
    ) / float(form_header.shape[0] * form_header.shape[1])
    stable_form_chrome = (
        dark_header_ratio >= 0.75
        # The auto-fill strip is partially covered by dark caption text and
        # can fall below 0.45 on the current hospital skin.
        and yellow_ratio(auto_fill_bar) >= 0.30
    )
    colored_heal = (
        (ordinary_heal[:, :, 1] >= 45)
        & (ordinary_heal[:, :, 2] >= 90)
    )
    colored_heal_ratio = (
        float(np.count_nonzero(colored_heal)) / float(colored_heal.size)
    )

    return (
        (
            red_ratio(quick_heal_case) >= 0.18
            or stable_form_chrome
        )
        and dark_rows_ratio >= 0.60
        and (
            red_ratio(hospital_capacity) >= 0.16
            or yellow_ratio(hospital_capacity) >= 0.12
            or colored_heal_ratio >= 0.30
            or stable_form_chrome
        )
    )


def detect_processing_factory_target(frame_bgr):
    """Find the processing factory by its four distinctive orange furnaces.

    The ordinary image templates are sensitive to the settlement camera
    position and to reward bubbles above the building.  The four glowing
    furnace trays remain visible across those states, so use their compact
    geometric cluster as a camera-independent fallback.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array([5, 150, 140], dtype=np.uint8),
        np.array([28, 255, 255], dtype=np.uint8),
    )
    # Exclude fixed HUD controls.  A previous live attempt found an orange
    # cluster in the chat/navigation chrome at (225, 645); accepting it opened
    # chat and left the factory task waiting on a screen it had never opened.
    # The camera scan will bring a partly clipped factory into this safe field.
    mask[:135, :] = 0
    # On the zZuB1 settlement the refinery sits at the extreme south-east
    # boundary.  The scan can only expose three furnace trays before the
    # building reaches the bottom edge, so retain the narrow strip above the
    # actual bottom HUD instead of discarding it with the HUD itself.
    mask[660:, :] = 0
    mask[:, :300] = 0
    mask[:, 1240:] = 0
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        np.ones((2, 2), dtype=np.uint8),
    )

    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    candidates = []
    for index in range(1, count):
        left, top, width, height, area = map(int, stats[index])
        if not (180 <= area <= 1250):
            continue
        if not (18 <= width <= 58 and 12 <= height <= 48):
            continue
        center_x, center_y = map(float, centroids[index])
        candidates.append((center_x, center_y, area, width, height))

    best_cluster = []
    for center_x, center_y, _area, _width, _height in candidates:
        cluster = [
            candidate
            for candidate in candidates
            if abs(candidate[0] - center_x) <= 145
            and abs(candidate[1] - center_y) <= 95
        ]
        if len(cluster) > len(best_cluster):
            best_cluster = cluster

    if len(best_cluster) < 3:
        return None

    # Orange lamps along the shelter wall can form three or four components
    # with exactly the same spacing as the furnace trays.  Unlike the real
    # factory, those components lie on one near-perfect diagonal.  Require a
    # genuinely two-dimensional cluster before clicking it; otherwise the bot
    # repeatedly selects the wall and never advances its camera scan.
    cluster_points = np.array(
        [[item[0], item[1]] for item in best_cluster],
        dtype=np.float32,
    )
    hull_area = float(cv2.contourArea(cv2.convexHull(cluster_points)))
    singular_values = np.linalg.svd(
        cluster_points - np.mean(cluster_points, axis=0),
        compute_uv=False,
    )
    invalid_two_dimensional_cluster = (
        hull_area < 850.0
        or len(singular_values) < 2
        or float(singular_values[1]) < float(singular_values[0]) * 0.20
    )
    if invalid_two_dimensional_cluster:
        # A clipped south-east refinery exposes only three large, evenly
        # staggered furnace trays.  They are necessarily almost collinear, but
        # are much larger and lower than the orange shelter-wall lamps that the
        # two-dimensional guard above rejects.  Keep this exception tightly
        # constrained to that edge geometry so fixed HUD chrome remains inert.
        large_trays = sorted(
            (
                item
                for item in best_cluster
                if 350 <= item[2] <= 1250
                and 28 <= item[3] <= 48
                and 20 <= item[4] <= 36
            ),
            key=lambda item: item[0],
        )
        clipped_refinery = False
        for start in range(max(0, len(large_trays) - 2)):
            trio = large_trays[start : start + 3]
            if len(trio) < 3:
                continue
            x_values = [item[0] for item in trio]
            y_values = [item[1] for item in trio]
            x_steps = np.diff(x_values)
            y_steps = np.diff(y_values)
            if (
                float(np.mean(x_values)) >= 980.0
                and float(np.mean(y_values)) >= 535.0
                and np.all((x_steps >= 20.0) & (x_steps <= 50.0))
                and np.all((y_steps >= 12.0) & (y_steps <= 35.0))
            ):
                best_cluster = trio
                clipped_refinery = True
                break
        if not clipped_refinery:
            return None

    target_x = int(round(np.mean([item[0] for item in best_cluster]) * scale_x))
    target_y = int(
        round((np.mean([item[1] for item in best_cluster]) + 18) * scale_y)
    )
    return target_x, target_y


def detect_finished_healing_target(frame_bgr):
    """Find a verified red or medic marker above a finished hospital."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    def has_troop_portrait(left, top, right, bottom):
        padding = 8
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(hsv.shape[1], right + padding)
        bottom = min(hsv.shape[0], bottom + padding)
        portrait = hsv[top:bottom, left:right]
        if portrait.size == 0:
            return False
        cool_pixels = (
            (portrait[:, :, 0] >= 95)
            & (portrait[:, :, 0] <= 169)
            & (portrait[:, :, 1] >= 45)
            & (portrait[:, :, 2] >= 35)
        )
        return (
            float(np.count_nonzero(cool_pixels)) / float(cool_pixels.size)
            >= 0.06
        )

    def is_finished_single_portrait(
        left,
        top,
        right,
        bottom,
        require_medic=False,
    ):
        padding = 2
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(hsv.shape[1], right + padding)
        bottom = min(hsv.shape[0], bottom + padding)
        portrait = hsv[top:bottom, left:right]
        if portrait.size == 0:
            return False
        red_pixels = (
            ((portrait[:, :, 0] <= 12) | (portrait[:, :, 0] >= 170))
            & (portrait[:, :, 1] >= 80)
            & (portrait[:, :, 2] >= 70)
        )
        white_pixels = (
            (portrait[:, :, 1] <= 55)
            & (portrait[:, :, 2] >= 150)
        )
        bronze_pixels = (
            (portrait[:, :, 0] >= 8)
            & (portrait[:, :, 0] <= 25)
            & (portrait[:, :, 1] >= 60)
            & (portrait[:, :, 2] >= 60)
        )
        red_ratio = float(np.count_nonzero(red_pixels)) / float(red_pixels.size)
        white_ratio = float(np.count_nonzero(white_pixels)) / float(
            white_pixels.size
        )
        bronze_ratio = float(np.count_nonzero(bronze_pixels)) / float(
            bronze_pixels.size
        )
        medic_collection_marker = (
            red_ratio >= 0.12
            and white_ratio >= 0.12
            and bronze_ratio >= 0.20
        )
        if require_medic:
            return medic_collection_marker
        return (
            red_ratio >= 0.25
            and white_ratio <= 0.10
        ) or medic_collection_marker

    red_mask = cv2.inRange(
        hsv,
        np.array([0, 80, 70], dtype=np.uint8),
        np.array([12, 255, 255], dtype=np.uint8),
    )
    red_mask |= cv2.inRange(
        hsv,
        np.array([170, 80, 70], dtype=np.uint8),
        np.array([179, 255, 255], dtype=np.uint8),
    )
    bronze_mask = cv2.inRange(
        hsv,
        np.array([8, 60, 60], dtype=np.uint8),
        np.array([25, 255, 255], dtype=np.uint8),
    )
    # Finished-healing portraits appear over shelter buildings. Excluding the
    # HUD keeps red notification badges and bottom navigation out of the scan.
    # Only red frames may seed a cluster: adjacent bronze roof details stay
    # visible after collection and otherwise cause repeated hospital clicks.
    portrait_boxes = []
    for marker_mask in (red_mask,):
        marker_mask[:120, :] = 0
        marker_mask[520:, :] = 0
        # The persistent quest panel occupies the left edge and contains bronze
        # square icons that resemble a single finished-healing portrait.
        marker_mask[:, :230] = 0
        marker_mask[:, 1100:] = 0
        # Rotating event tiles permanently occupy this upper-right strip.
        # Their red frames and character art can look like a medic portrait,
        # while a shelter marker underneath the strip would not be clickable.
        marker_mask[120:240, 750:1100] = 0

        contours, _hierarchy = cv2.findContours(
            marker_mask,
            cv2.RETR_LIST,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            area = float(cv2.contourArea(contour))
            if (
                18 <= width <= 48
                and 30 <= height <= 48
                and area >= 80.0
            ):
                portrait_boxes.append((x, y, width, height, area))

    # RETR_LIST may return both edges of the same frame. Keep only the larger
    # contour when two boxes substantially overlap.
    deduplicated = []
    for candidate in sorted(portrait_boxes, key=lambda box: box[4], reverse=True):
        x, y, width, height, _area = candidate
        candidate_area = width * height
        duplicate = False
        for kept in deduplicated:
            kept_x, kept_y, kept_width, kept_height, _kept_area = kept
            intersection_width = max(
                0,
                min(x + width, kept_x + kept_width) - max(x, kept_x),
            )
            intersection_height = max(
                0,
                min(y + height, kept_y + kept_height) - max(y, kept_y),
            )
            intersection = intersection_width * intersection_height
            if intersection >= 0.65 * min(
                candidate_area,
                kept_width * kept_height,
            ):
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(candidate)

    # The real medic portrait has a bronze outer frame. Keep bronze boxes only
    # for the stricter single-portrait signature below, never for clustering.
    single_portrait_boxes = [
        (box, False)
        for box in deduplicated
    ]
    bronze_mask[:120, :] = 0
    bronze_mask[520:, :] = 0
    bronze_mask[:, :230] = 0
    bronze_mask[:, 1100:] = 0
    bronze_mask[120:240, 750:1100] = 0
    contours, _hierarchy = cv2.findContours(
        bronze_mask,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = float(cv2.contourArea(contour))
        if (
            18 <= width <= 48
            and 30 <= height <= 48
            and area >= 80.0
        ):
            single_portrait_boxes.append(
                ((x, y, width, height, area), True)
            )

    # Portrait frames in one collection marker touch or nearly touch and share
    # a baseline. Requiring a cluster rejects isolated red game controls.
    clusters = []
    remaining = set(range(len(deduplicated)))
    while remaining:
        component = {remaining.pop()}
        changed = True
        while changed:
            changed = False
            for index in list(remaining):
                x, y, width, height, _area = deduplicated[index]
                center_y = y + height / 2.0
                for member in component:
                    other_x, other_y, other_width, other_height, _other_area = (
                        deduplicated[member]
                    )
                    other_center_y = other_y + other_height / 2.0
                    horizontal_gap = max(
                        0,
                        max(x, other_x)
                        - min(x + width, other_x + other_width),
                    )
                    if (
                        abs(center_y - other_center_y) <= 8.0
                        and horizontal_gap <= 12
                    ):
                        component.add(index)
                        remaining.remove(index)
                        changed = True
                        break
        if len(component) >= 2:
            clusters.append([deduplicated[index] for index in component])

    candidates = []
    for cluster in clusters:
        left = min(box[0] for box in cluster)
        top = min(box[1] for box in cluster)
        right = max(box[0] + box[2] for box in cluster)
        bottom = max(box[1] + box[3] for box in cluster)
        if (
            40 <= right - left <= 150
            and 30 <= bottom - top <= 55
            and has_troop_portrait(left, top, right, bottom)
        ):
            candidates.append(
                (
                    len(cluster),
                    top,
                    left,
                    (left + right) / 2.0,
                    (top + bottom) / 2.0,
                )
            )

    # A lone dark troop portrait means that wounded troops are available. Only
    # a red or white-red medic signature is safe to treat as a collection icon.
    for (
        (x, y, width, height, area),
        require_medic,
    ) in single_portrait_boxes:
        if (
            35 <= width <= 48
            and 35 <= height <= 48
            and area >= 1100.0
            and is_finished_single_portrait(
                x,
                y,
                x + width,
                y + height,
                require_medic=require_medic,
            )
        ):
            candidates.append(
                (
                    4,
                    y,
                    x,
                    x + width / 2.0,
                    y + height / 2.0,
                )
            )

    if not candidates:
        return None

    _count, _top, _left, target_x, target_y = min(
        candidates,
        key=lambda item: (-item[0], item[1], item[2]),
    )
    return (
        int(round(target_x * scale_x)),
        int(round(target_y * scale_y)),
    )


def healing_number_editor_is_open(frame_bgr):
    """Detect the Android numeric editor shown after tapping a troop amount."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    editor_footer = frame[625:705, 20:1260]
    hsv = cv2.cvtColor(editor_footer, cv2.COLOR_BGR2HSV)
    neutral_bright = (hsv[:, :, 2] >= 215) & (hsv[:, :, 1] <= 45)
    return float(np.count_nonzero(neutral_bright)) / float(neutral_bright.size) >= 0.80


def imread_unicode(image_path, flags=cv2.IMREAD_COLOR):
    """Read images reliably from Windows paths containing non-ASCII characters."""
    try:
        encoded = np.fromfile(Path(image_path), dtype=np.uint8)
    except (OSError, ValueError):
        return None
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, flags)


@dataclass
class TemplateOrbData:
    keypoints: list
    descriptors: object


class TemplateCache:
    def __init__(self):
        self._color = {}
        self._gray = {}
        self._size = {}
        self._orb = {}
        self._scaled_gray = {}

    def invalidate(self, template_path):
        self._color.pop(template_path, None)
        self._gray.pop(template_path, None)
        self._size.pop(template_path, None)
        self._orb.pop(template_path, None)
        keys_to_remove = [key for key in self._scaled_gray if key[0] == template_path]
        for key in keys_to_remove:
            self._scaled_gray.pop(key, None)

    def get_color(self, template_path):
        if template_path not in self._color:
            self._color[template_path] = imread_unicode(template_path)
        return self._color[template_path]

    def get_gray(self, template_path):
        if template_path not in self._gray:
            self._gray[template_path] = imread_unicode(template_path, cv2.IMREAD_GRAYSCALE)
        return self._gray[template_path]

    def get_size(self, template_path):
        if template_path not in self._size:
            gray = self.get_gray(template_path)
            self._size[template_path] = None if gray is None else (gray.shape[1], gray.shape[0])
        return self._size[template_path]

    def get_scaled_gray(self, template_path, scale):
        scale_key = (template_path, round(float(scale), 4))
        if scale_key not in self._scaled_gray:
            template = self.get_gray(template_path)
            if template is None:
                self._scaled_gray[scale_key] = None
            else:
                new_w = int(template.shape[1] * scale)
                new_h = int(template.shape[0] * scale)
                if new_w < 5 or new_h < 5:
                    self._scaled_gray[scale_key] = None
                else:
                    self._scaled_gray[scale_key] = cv2.resize(
                        template,
                        (new_w, new_h),
                        interpolation=cv2.INTER_LINEAR,
                    )
        return self._scaled_gray[scale_key]

    def get_orb(self, template_path):
        if template_path not in self._orb:
            template = self.get_gray(template_path)
            if template is None:
                self._orb[template_path] = TemplateOrbData([], None)
            else:
                orb = cv2.ORB_create()
                keypoints, descriptors = orb.detectAndCompute(template, None)
                self._orb[template_path] = TemplateOrbData(keypoints or [], descriptors)
        return self._orb[template_path]
