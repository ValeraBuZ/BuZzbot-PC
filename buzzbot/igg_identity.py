"""Read the account ID from the SDK and the game's account panel locally."""

from pathlib import Path

import cv2
import numpy as np

from buzzbot.matching import _reference_frame, detect_account_settings_back_target, detect_igg_id_selection_target
from buzzbot.accounts import extract_igg_id_targets


def selected_sdk_igg_id(xml, chooser_index=1):
    """Read the ID of the selected SDK row, not the game's loaded identity."""
    rows = extract_igg_id_targets(xml)
    if not isinstance(chooser_index, int) or not 1 <= chooser_index <= len(rows):
        return None
    return rows[chooser_index - 1]["igg_id"]


def account_id_glyphs(frame):
    gray = cv2.cvtColor(frame[150:180, 178:465], cv2.COLOR_BGR2GRAY)
    mask = (gray >= 200).astype(np.uint8) * 255
    occupied = np.any(mask, axis=0)
    edges = np.diff(np.pad(occupied.astype(int), (1, 1)))
    glyphs = []
    for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        ys = np.flatnonzero(np.any(mask[:, start:end], axis=1))
        if not 3 <= end - start <= 20 or not 14 <= len(ys) <= 26:
            return []
        glyph = mask[ys[0]:ys[-1] + 1, start:end]
        glyphs.append(cv2.resize(glyph, (20, 28), interpolation=cv2.INTER_NEAREST))
    return glyphs


def read_game_igg_id(frame_bgr):
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None or detect_account_settings_back_target(frame) is None:
        return None
    glyphs = account_id_glyphs(frame)
    if not 6 <= len(glyphs) <= 20:
        return None
    directory = Path(__file__).parent / "assets/accounts/digits"
    templates = [cv2.imread(str(directory / f"{digit}.png"), 0) for digit in range(10)]
    if any(template is None for template in templates):
        return None
    digits = []
    for glyph in glyphs:
        scores = sorted(
            ((float(np.mean((glyph > 0) == (template > 0))), str(digit))
             for digit, template in enumerate(templates)), reverse=True
        )
        if scores[0][0] < 0.90 or scores[0][0] - scores[1][0] < 0.06:
            return None
        digits.append(scores[0][1])
    return "".join(digits)


def read_sdk_igg_id(frame_bgr):
    """Read the sole SDK row when WebView omits its accessibility children.

    Callers must compare two fresh readings against an existing profile binding.
    The page detector requires the single-row layout and the New ID link below it.
    """
    frame, _sx, _sy = _reference_frame(frame_bgr)
    if frame is None or detect_igg_id_selection_target(frame) is None:
        return None
    gray = cv2.cvtColor(frame[147:176, 335:740], cv2.COLOR_BGR2GRAY)
    mask = (gray < 140).astype(np.uint8)*255
    edges = np.diff(np.pad(np.any(mask, axis=0).astype(int), (1, 1)))
    templates = [cv2.imread(str(Path(__file__).parent / 'assets/accounts/digits' / f'{n}.png'), 0)
                 for n in range(10)]
    if any(t is None for t in templates):
        return None
    digits, previous = [], None
    for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        ys = np.flatnonzero(np.any(mask[:, start:end], axis=1))
        if previous is not None and start-previous > 6:
            break  # Chevron after the numeric ID.
        if not 3 <= end-start <= 19 or not 14 <= len(ys) <= 25:
            return None
        glyph = cv2.resize(mask[ys[0]:ys[-1]+1, start:end], (20, 28), interpolation=cv2.INTER_NEAREST)
        scores = sorted(((float(np.mean((glyph > 0) == (t > 0))), str(n))
                         for n,t in enumerate(templates)), reverse=True)
        if scores[0][0] < .82 or scores[0][0]-scores[1][0] < .075:
            return None
        digits.append(scores[0][1]); previous=end
    return ''.join(digits) if 6 <= len(digits) <= 20 else None
