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


def stamina_dialog_is_visible(frame_bgr):
    """Return whether the insufficient-stamina item dialog is visible."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
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
    if middle_x < max(top_x, bottom_x) + 2.5:
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

    # A prepared-but-not-started truck is resumed before opening another slot.
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    unsent = hsv[430:472, 70:345]
    red = (
        ((unsent[:, :, 0] < 12) | (unsent[:, :, 0] > 170))
        & (unsent[:, :, 1] > 90)
        & (unsent[:, :, 2] > 85)
    )
    if float(np.mean(red)) >= 0.008:
        return int(round(207 * scale_x)), int(round(410 * scale_y))

    candidates = ((207, 410), (752, 410))
    for center in candidates:
        if _bright_cross_ratio(frame, center) >= 0.10:
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
    for center_x in (207, 752):
        region = hsv[310:485, max(0, center_x - 145):min(1280, center_x + 145)]
        unsent_region = hsv[430:472, max(0, center_x - 137):min(1280, center_x + 138)]
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
                (int(round(center_x * scale_x)), int(round(410 * scale_y)))
            )
    return targets


def truck_alliance_escort_is_visible(frame_bgr):
    """Recognise Alliance Escort so it cannot be mistaken for a personal truck."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
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
    if frame is None:
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
        and _bright_cross_ratio(frame, (640, 190)) >= 0.18
    )


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


def detect_truck_start_dispatch_target(frame_bgr):
    """Return the enabled gold Start Escort button on a personal shipment."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
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
    if frame is None:
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


def detect_shop_radial_action_target(frame_bgr, building_target=None):
    """Return the middle Shop action after the building is selected.

    Selection centres the building and places four bright-green direction
    arrows around it.  Its three radial actions then appear below: Information,
    Shop, and Beast Shop.  The ordinary Shop is the middle action.  Requiring
    all four arrows prevents bottom navigation buttons from being mistaken for
    the radial menu.
    """
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
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
    return (
        int(round(building_center_x * scale_x)),
        int(round((bottom_arrow_y + 45.0) * scale_y)),
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
    """Recognise the Mysterious Merchant offer grid."""
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


def detect_mysterious_merchant_non_gem_offer_targets(frame_bgr):
    """Return only resource-priced merchant offers, never purple gem prices."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None or not mysterious_merchant_screen_is_visible(frame):
        return []
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    candidates = []
    for center_y in (270, 460, 640):
        for center_x in (320, 620, 920):
            x1, x2 = center_x - 105, center_x + 105
            y1, y2 = center_y - 34, center_y + 34
            region = hsv[y1:y2, x1:x2]
            purple = (
                (region[:, :, 0] >= 115)
                & (region[:, :, 0] <= 170)
                & (region[:, :, 1] >= 35)
                & (region[:, :, 2] >= 65)
            )
            resource = (
                (region[:, :, 0] >= 3)
                & (region[:, :, 0] <= 42)
                & (region[:, :, 1] >= 45)
                & (region[:, :, 2] >= 70)
            )
            # Any meaningful purple price area vetoes the offer. Ambiguous
            # buttons are skipped; this intentionally favours safety over
            # exhausting every offer.
            if float(np.mean(purple)) <= 0.08 and float(np.mean(resource)) >= 0.10:
                candidates.append(
                    (int(round(center_x * scale_x)), int(round(center_y * scale_y)))
                )
    return candidates


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
    outside = gray[0:150, :]
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
        float(np.mean(outside <= 70)) < 0.75
        or float(np.mean(dialog >= 145)) < 0.55
        or float(np.mean(neutral_cancel)) < 0.45
        or float(np.mean(gold_ok)) < 0.55
    ):
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


def detect_commander_profile_back_target(frame_bgr):
    """Detect the commander profile screen that remains under Settings."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

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


def detect_alliance_marked_project_target(frame_bgr):
    """Find the alliance technology card carrying the compact red marker."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array([0, 120, 140], dtype=np.uint8),
        np.array([12, 255, 255], dtype=np.uint8),
    )
    mask |= cv2.inRange(
        hsv,
        np.array([170, 120, 140], dtype=np.uint8),
        np.array([179, 255, 255], dtype=np.uint8),
    )

    # Technology cards occupy the center of the tree. Excluding the title bar,
    # navigation and right-side controls prevents unrelated red HUD badges.
    mask[:90, :] = 0
    mask[660:, :] = 0
    mask[:, :170] = 0
    mask[:, 1100:] = 0

    compact_candidates = []
    ribbon_candidates = []
    component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    for index in range(1, component_count):
        x, y, width, height, area = stats[index]
        aspect = width / float(height) if height else 0.0
        extent = area / float(width * height) if width and height else 0.0
        if (
            1200 <= area <= 6000
            and 90 <= width <= 230
            and 20 <= height <= 70
            and 2.0 <= aspect <= 8.0
            and extent >= 0.35
        ):
            center_x, center_y = centroids[index]
            ribbon_candidates.append((int(area), float(center_x), float(center_y)))
            continue
        if not (
            70 <= area <= 220
            and 9 <= width <= 18
            and 9 <= height <= 18
            and 0.7 <= aspect <= 1.4
            and extent >= 0.45
        ):
            continue
        center_x, center_y = centroids[index]
        compact_candidates.append((int(area), float(center_x), float(center_y)))

    if ribbon_candidates:
        _area, marker_x, marker_y = max(ribbon_candidates)
        # The wide "Marked" ribbon starts above the right half of the card.
        target_x = (marker_x - 95.0) * scale_x
        target_y = marker_y * scale_y
        return int(round(target_x)), int(round(target_y))

    if not compact_candidates:
        return None

    _area, marker_x, marker_y = max(compact_candidates)
    # The marker is attached to the right edge of the project card.
    target_x = (marker_x - 55.0) * scale_x
    target_y = marker_y * scale_y
    return int(round(target_x)), int(round(target_y))


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
    """Recognize the HH:MM:SS timer on an already-running radar card.

    Radar task artwork and text vary between accounts, but the six dark timer
    digits always occupy the same narrow strip in the left card. Detecting
    aligned digit components is more stable than matching one duration.
    """
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
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


def zombie_camp_checkbox_is_checked(frame_bgr):
    """Detect the optional 'set up camp after attack' checkmark."""
    frame, _scale_x, _scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return False
    checkbox_inner = frame[506:530, 809:831]
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
    """Return the right-hand retreat action for a selected world-map squad."""
    frame, scale_x, scale_y = _reference_frame(frame_bgr)
    if frame is None:
        return None

    # Selecting a march card centers its camp at a camera-dependent position.
    # The two action circles (emoji, retreat) therefore move together instead
    # of staying at one fixed coordinate. Detect the pair and use the right one.
    roi_left, roi_top, roi_right, roi_bottom = 280, 360, 920, 590
    action_roi = frame[roi_top:roi_bottom, roi_left:roi_right]
    if action_roi.size == 0:
        return None
    gray = cv2.cvtColor(action_roi, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=45,
        param1=90,
        param2=26,
        minRadius=22,
        maxRadius=45,
    )
    if circles is None:
        return None

    hsv = cv2.cvtColor(action_roi, cv2.COLOR_BGR2HSV)
    gold = (
        (hsv[:, :, 0] >= 5)
        & (hsv[:, :, 0] <= 45)
        & (hsv[:, :, 1] >= 70)
        & (hsv[:, :, 2] >= 70)
    )
    candidates = np.round(circles[0]).astype(int).tolist()
    best_pair = None
    best_score = -1.0
    yy, xx = np.ogrid[:action_roi.shape[0], :action_roi.shape[1]]
    for index, first in enumerate(candidates):
        for second in candidates[index + 1:]:
            left_circle, right_circle = sorted((first, second), key=lambda item: item[0])
            delta_x = right_circle[0] - left_circle[0]
            average_radius = (left_circle[2] + right_circle[2]) / 2.0
            if average_radius <= 0 or not 2.85 <= delta_x / average_radius <= 3.20:
                continue
            if abs(right_circle[1] - left_circle[1]) > 3:
                continue
            if abs(right_circle[2] - left_circle[2]) > 3:
                continue

            gold_scores = []
            bright_scores = []
            green_scores = []
            for center_x, center_y, radius in (left_circle, right_circle):
                mask = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= radius ** 2
                inner_mask = (
                    (xx - center_x) ** 2 + (yy - center_y) ** 2
                    <= (radius * 0.68) ** 2
                )
                gold_scores.append(float(np.mean(gold[mask])))
                bright_scores.append(
                    float(np.mean(hsv[:, :, 2][inner_mask] >= 170))
                )
                green_scores.append(
                    float(
                        np.mean(
                            (
                                (hsv[:, :, 0][inner_mask] >= 45)
                                & (hsv[:, :, 0][inner_mask] <= 110)
                                & (hsv[:, :, 1][inner_mask] >= 90)
                                & (hsv[:, :, 2][inner_mask] >= 80)
                            )
                        )
                    )
                )
            score = sum(gold_scores)
            if (
                min(gold_scores) >= 0.25
                and min(bright_scores) >= 0.20
                and max(green_scores) <= 0.08
                and score > best_score
            ):
                best_score = score
                best_pair = right_circle

    if best_pair is None:
        return None
    return (
        int(round((roi_left + best_pair[0]) * scale_x)),
        int(round((roi_top + best_pair[1]) * scale_y)),
    )


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
    right_hsv = cv2.cvtColor(right_button, cv2.COLOR_BGR2HSV)
    pale_body = (body_hsv[:, :, 1] <= 55) & (body_hsv[:, :, 2] >= 135)
    gold_button = (
        (right_hsv[:, :, 0] >= 8)
        & (right_hsv[:, :, 0] <= 40)
        & (right_hsv[:, :, 1] >= 70)
        & (right_hsv[:, :, 2] >= 120)
    )
    if float(np.mean(pale_body)) < 0.45 or float(np.mean(gold_button)) < 0.35:
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
    mask[600:, :] = 0
    mask[:, :300] = 0
    mask[:, 1140:] = 0
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
        candidates.append((center_x, center_y, area))

    best_cluster = []
    for center_x, center_y, _area in candidates:
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
