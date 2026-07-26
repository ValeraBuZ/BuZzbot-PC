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
            and 450 <= center_y <= 560
        ):
            candidates.append((width * height, center_x, center_y))
    if not candidates:
        return None

    _area, center_x, center_y = max(candidates)
    return int(round(center_x * scale_x)), int(round(center_y * scale_y))


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

    candidates = []
    component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    for index in range(1, component_count):
        x, y, width, height, area = stats[index]
        aspect = width / float(height) if height else 0.0
        extent = area / float(width * height) if width and height else 0.0
        if not (
            70 <= area <= 220
            and 9 <= width <= 18
            and 9 <= height <= 18
            and 0.7 <= aspect <= 1.4
            and extent >= 0.45
        ):
            continue
        center_x, center_y = centroids[index]
        candidates.append((int(area), float(center_x), float(center_y)))

    if not candidates:
        return None

    _area, marker_x, marker_y = max(candidates)
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


def detect_finished_healing_target(frame_bgr):
    """Find a red or bronze troop portrait marker above a finished hospital."""
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
    portrait_boxes = []
    bronze_core_boxes = []
    for marker_mask, collect_bronze_cores in (
        (red_mask, False),
        (bronze_mask, True),
    ):
        marker_mask[:120, :] = 0
        marker_mask[520:, :] = 0
        # The persistent quest panel occupies the left edge and contains bronze
        # square icons that resemble a single finished-healing portrait.
        marker_mask[:, :230] = 0
        marker_mask[:, 1100:] = 0

        contours, _hierarchy = cv2.findContours(
            marker_mask,
            cv2.RETR_LIST,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            area = float(cv2.contourArea(contour))
            if (
                collect_bronze_cores
                and 20 <= width <= 25
                and 29 <= height <= 32
                and 450.0 <= area <= 650.0
            ):
                bronze_core_boxes.append((x, y, width, height, area))
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

    # The outer frame color depends on the healed troop type. The compact
    # bronze portrait core remains stable when red framing is absent.
    for x, y, width, height, _area in bronze_core_boxes:
        if not has_troop_portrait(x, y, x + width, y + height):
            continue
        candidates.append(
            (
                5,
                y,
                x,
                x + width / 2.0,
                y + height / 2.0,
            )
        )

    # Some accounts show one portrait per hospital instead of a three-portrait
    # group. Its bronze frame produces a compact, nearly square outer contour;
    # the high contour-area threshold excludes ordinary building decorations.
    for x, y, width, height, area in deduplicated:
        if (
            35 <= width <= 48
            and 35 <= height <= 48
            and area >= 1200.0
            and has_troop_portrait(x, y, x + width, y + height)
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
