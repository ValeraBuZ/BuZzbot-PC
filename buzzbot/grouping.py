from __future__ import annotations

from collections import OrderedDict


def parse_time_to_minutes(time_value):
    if not isinstance(time_value, str) or ":" not in time_value:
        return None
    try:
        hours, minutes = map(int, time_value.split(":"))
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def validate_hour_min(hour_value, minute_value):
    hour_value = (hour_value or "").strip()
    minute_value = (minute_value or "").strip()
    if not hour_value and not minute_value:
        return True, None
    if not hour_value or not minute_value:
        return False, None
    try:
        hours = int(hour_value)
        minutes = int(minute_value)
    except ValueError:
        return False, None
    if 0 <= hours <= 23 and 0 <= minutes <= 59:
        return True, f"{hours:02d}:{minutes:02d}"
    return False, None


def parse_click_sequence(sequence_text):
    result = []
    sequence_text = (sequence_text or "").strip()
    if not sequence_text:
        return result
    for part in sequence_text.split(";"):
        chunk = part.strip()
        if not chunk:
            continue
        dx_value, dy_value = map(int, chunk.split(","))
        result.append((dx_value, dy_value))
    return result


def build_group_iteration_plan(images, group_execution, cycle_mode=False, cycle_groups=None, current_cycle_index=0):
    if cycle_mode and cycle_groups:
        current_group = cycle_groups[current_cycle_index % len(cycle_groups)]
        cycle_images = [img for img in images if img.get("group") == current_group]
        return [
            {
                "group": current_group,
                "images": cycle_images,
                "delay_between": float(group_execution.get(current_group, {}).get("delay_between", 0.0)),
                "delay_after": float(group_execution.get(current_group, {}).get("delay_after", 0.0)),
            }
        ]

    grouped = OrderedDict()
    ungrouped = []
    first_seen = {}

    for index, image in enumerate(images):
        group_name = image.get("group")
        if group_name:
            grouped.setdefault(group_name, []).append(image)
            first_seen.setdefault(group_name, index)
        else:
            ungrouped.append(image)

    ordered_groups = sorted(
        grouped.keys(),
        key=lambda group_name: (
            group_execution.get(group_name, {}).get("order", 10**9),
            first_seen.get(group_name, 10**9),
            group_name.lower(),
        ),
    )

    plan = []
    for group_name in ordered_groups:
        plan.append(
            {
                "group": group_name,
                "images": grouped[group_name],
                "delay_between": float(group_execution.get(group_name, {}).get("delay_between", 0.0)),
                "delay_after": float(group_execution.get(group_name, {}).get("delay_after", 0.0)),
            }
        )

    if ungrouped:
        plan.append(
            {
                "group": None,
                "images": ungrouped,
                "delay_between": 0.0,
                "delay_after": 0.0,
            }
        )

    return plan
