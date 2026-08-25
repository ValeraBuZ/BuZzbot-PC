from __future__ import annotations

from copy import deepcopy
import re
import uuid
import xml.etree.ElementTree as ET


_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _account_id(name):
    value = str(name or "account").strip().lower()
    safe = "".join(char if char.isalnum() else "_" for char in value).strip("_")
    return safe or uuid.uuid4().hex[:8]


def default_account_profiles(serial="emulator-5564"):
    return [
        {
            "id": "phoenix675",
            "name": "Phoenix675",
            "enabled": True,
            "ldplayer_index": 5,
            "adb_serial": str(serial or "emulator-5564"),
            "session_minutes": 30.0,
            "login_method": "igg",
            "chooser_index": 2,
            "google_login": "",
            "igg_login": "",
            "auto_login": False,
            "switch_group": "Аккаунт: Phoenix675",
            "switch_completion_uid": "",
            "task_enabled": {},
            "task_settings": {},
            "routine_next_run": {},
        }
    ]


def _number(value, default, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    return min(float(maximum), max(float(minimum), parsed))


def normalize_account_profiles(raw_profiles, serial="emulator-5564"):
    if not isinstance(raw_profiles, list) or not raw_profiles:
        return default_account_profiles(serial)

    normalized = []
    used_ids = set()
    for index, source in enumerate(raw_profiles):
        if not isinstance(source, dict):
            continue
        name = str(source.get("name") or f"Аккаунт {index + 1}").strip()
        account_id = str(source.get("id") or _account_id(name)).strip()
        if account_id in used_ids:
            account_id = f"{account_id}_{index + 1}"
        used_ids.add(account_id)
        task_enabled = source.get("task_enabled")
        task_settings = source.get("task_settings")
        login_method = str(source.get("login_method") or "igg").strip().lower()
        if login_method not in {"igg", "google"}:
            login_method = "igg"
        normalized.append(
            {
                "id": account_id,
                "name": name,
                "enabled": bool(source.get("enabled", True)),
                "ldplayer_index": int(_number(source.get("ldplayer_index"), 5, 0, 99)),
                "adb_serial": str(source.get("adb_serial") or serial or "emulator-5564"),
                "session_minutes": _number(source.get("session_minutes"), 30.0, 1.0, 1440.0),
                "login_method": login_method,
                "chooser_index": int(_number(source.get("chooser_index"), index + 1, 1, 20)),
                "google_login": str(source.get("google_login") or "").strip(),
                "igg_login": str(source.get("igg_login") or "").strip(),
                "auto_login": bool(source.get("auto_login", False)),
                "switch_group": str(source.get("switch_group") or f"Аккаунт: {name}"),
                "switch_completion_uid": str(source.get("switch_completion_uid") or ""),
                "task_enabled": deepcopy(task_enabled) if isinstance(task_enabled, dict) else {},
                "task_settings": deepcopy(task_settings) if isinstance(task_settings, dict) else {},
                "routine_next_run": deepcopy(source.get("routine_next_run", {}))
                if isinstance(source.get("routine_next_run"), dict) else {},
            }
        )
    return normalized or default_account_profiles(serial)


def recover_account_profiles(raw_profiles, credential_keys, serial="emulator-5564"):
    """Restore local profiles from DPAPI key names without exposing credentials."""
    profiles = normalize_account_profiles(raw_profiles, serial)
    keys = {str(key or "").strip() for key in credential_keys or ()}
    methods_by_id = {}
    for key in keys:
        match = re.fullmatch(r"login:(igg|google):(.+)", key)
        if match is None:
            continue
        method, account_id = match.groups()
        password_keys = (
            (f"igg:{account_id}",)
            if method == "igg"
            else (f"google:{account_id}", account_id)
        )
        if any(password_key in keys for password_key in password_keys):
            methods_by_id.setdefault(account_id, set()).add(method)

    def display_name(account_id):
        special = {
            "zzub1": "zZuB1",
            "buzz": "BuZz",
            "luckynoob": "LuckyNoob",
        }
        if account_id in special:
            return special[account_id]
        numbered = re.fullmatch(r"igg_(\d+)", account_id)
        if numbered:
            return f"IGG {numbered.group(1)}"
        return account_id.replace("_", " ").strip().title() or "Account"

    existing = {str(profile.get("id") or ""): profile for profile in profiles}
    for account_id in sorted(methods_by_id):
        methods = methods_by_id[account_id]
        preferred_method = "google" if methods == {"google"} else "igg"
        profile = existing.get(account_id)
        if profile is not None:
            current_method = str(profile.get("login_method") or "igg")
            if current_method not in methods:
                profile["login_method"] = preferred_method
            profile["auto_login"] = True
            if preferred_method == "igg":
                profile["chooser_index"] = 1
            if account_id.casefold() == "buzz":
                profile["enabled"] = False
            continue

        profiles.append(
            {
                "id": account_id,
                "name": display_name(account_id),
                "enabled": account_id.casefold() != "buzz",
                "ldplayer_index": 5,
                "adb_serial": str(serial or "emulator-5564"),
                "session_minutes": 30.0,
                "login_method": preferred_method,
                "chooser_index": 1,
                "google_login": "",
                "igg_login": "",
                "auto_login": True,
                "switch_group": f"Аккаунт: {display_name(account_id)}",
                "switch_completion_uid": "",
                "task_enabled": {},
                "task_settings": {},
                "routine_next_run": {},
            }
        )
    return profiles


def find_account(profiles, account_id):
    return next((profile for profile in profiles if profile.get("id") == account_id), None)


def snapshot_tasks(profile, tasks):
    profile["task_enabled"] = {
        task["id"]: bool(task.get("enabled", False))
        for task in tasks
    }
    profile["task_settings"] = {
        task["id"]: deepcopy(task.get("settings", {}))
        for task in tasks
    }
    return profile


def apply_tasks(profile, tasks):
    enabled = profile.get("task_enabled", {})
    settings = profile.get("task_settings", {})
    for task in tasks:
        task_id = task["id"]
        if task_id in enabled:
            task["enabled"] = bool(enabled[task_id])
        if isinstance(settings.get(task_id), dict):
            task.setdefault("settings", {}).update(deepcopy(settings[task_id]))
    return tasks


def next_enabled_account(profiles, current_id):
    enabled = [profile for profile in profiles if profile.get("enabled", True)]
    if len(enabled) <= 1:
        return None
    current_index = next(
        (index for index, profile in enumerate(enabled) if profile.get("id") == current_id),
        -1,
    )
    return enabled[(current_index + 1) % len(enabled)]


def requires_google_reauthentication(ui_xml):
    text = str(ui_xml or "").casefold()
    markers = (
        "подтвердите свою личность",
        "подтвердите, что это вы",
        "verify it's you",
        "verify it’s you",
        "confirm your identity",
    )
    return any(marker in text for marker in markers)


def requires_manual_google_verification(ui_xml):
    text = str(ui_xml or "").casefold()
    markers = (
        "recaptcha",
        "captcha",
        "security verification",
        "complete the puzzle",
        "slide to complete",
        "verify you are human",
        "verify you're human",
        "подтвердите, что вы не робот",
        "проверка безопасности",
        "пройдите проверку",
        "перетащите ползунок",
    )
    return any(marker in text for marker in markers)


def extract_google_accounts(ui_xml):
    """Return Google accounts in the same top-to-bottom order as the chooser."""
    try:
        root = ET.fromstring(str(ui_xml or ""))
    except ET.ParseError:
        return []

    accounts = []
    seen = set()
    for node in root.iter():
        values = (node.attrib.get("text", ""), node.attrib.get("content-desc", ""))
        for value in values:
            for email in _EMAIL_RE.findall(str(value or "")):
                normalized = email.casefold()
                if normalized in seen:
                    continue
                seen.add(normalized)
                accounts.append({"chooser_index": len(accounts) + 1, "email": email})
    return accounts


def extract_google_account_targets(ui_xml):
    """Return Google chooser rows with their safe clickable centers."""
    try:
        root = ET.fromstring(str(ui_xml or ""))
    except ET.ParseError:
        return []

    targets = []
    seen = set()
    for node in root.iter():
        resource_id = str(node.attrib.get("resource-id", ""))
        if not resource_id.endswith("/container") or node.attrib.get("clickable") != "true":
            continue
        email = ""
        for descendant in node.iter():
            descendant_id = str(descendant.attrib.get("resource-id", ""))
            value = str(descendant.attrib.get("text", ""))
            if descendant_id.endswith("/account_name") and _EMAIL_RE.fullmatch(value):
                email = value
                break
        normalized = email.casefold()
        bounds = _BOUNDS_RE.fullmatch(str(node.attrib.get("bounds", "")))
        if not email or normalized in seen or bounds is None:
            continue
        left, top, right, bottom = map(int, bounds.groups())
        if right <= left or bottom <= top:
            continue
        seen.add(normalized)
        targets.append(
            {
                "chooser_index": len(targets) + 1,
                "email": email,
                "center": ((left + right) // 2, (top + bottom) // 2),
            }
        )
    return targets


def extract_android_google_accounts(account_dump):
    """Return Google accounts reported by Android AccountManager."""
    accounts = []
    seen = set()
    pattern = re.compile(r"Account \{name=([^,}]+), type=([^}]+)\}")
    for name, account_type in pattern.findall(str(account_dump or "")):
        if account_type.strip() != "com.google":
            continue
        email = name.strip()
        normalized = email.casefold()
        if not email or normalized in seen:
            continue
        seen.add(normalized)
        accounts.append(email)
    return accounts


def extract_igg_login_form(ui_xml):
    """Return safe input/button centers when the IGG Account form is visible."""
    try:
        root = ET.fromstring(str(ui_xml or ""))
    except ET.ParseError:
        return None

    title_visible = False
    login_title_visible = False
    for node in root.iter():
        label = " ".join(
            (
                str(node.attrib.get("text", "")),
                str(node.attrib.get("content-desc", "")),
            )
        ).casefold()
        if "igg account" not in label:
            continue
        title_visible = True
        bounds = _BOUNDS_RE.fullmatch(str(node.attrib.get("bounds", "")))
        if bounds is not None:
            _left, top, _right, bottom = map(int, bounds.groups())
            if top <= 20 and bottom <= 80:
                login_title_visible = True
    if not title_visible:
        return None

    login_target = None
    password_target = None
    submit_targets = []
    for node in root.iter():
        attributes = node.attrib
        bounds = _BOUNDS_RE.fullmatch(str(attributes.get("bounds", "")))
        if bounds is None:
            continue
        left, top, right, bottom = map(int, bounds.groups())
        if right <= left or bottom <= top:
            continue
        center = ((left + right) // 2, (top + bottom) // 2)
        node_class = attributes.get("class")
        if node_class == "android.widget.EditText":
            if attributes.get("password") == "true":
                password_target = password_target or center
            else:
                login_target = login_target or center
        elif node_class == "android.widget.Button" and attributes.get("clickable") == "true":
            submit_targets.append((top, center))

    if login_target is not None and password_target is not None and submit_targets:
        submit_target = next(
            (center for top, center in sorted(submit_targets) if top >= password_target[1]),
            sorted(submit_targets)[0][1],
        )
        return {
            "login": login_target,
            "password": password_target,
            "submit": submit_target,
        }

    # Recent IGG builds expose the form as one non-accessible WebView. The
    # native title and WebView bounds still provide a stable, verifiable frame
    # for the three controls across LDPlayer resolutions.
    if not login_title_visible:
        return None
    for node in root.iter():
        if node.attrib.get("class") != "android.webkit.WebView":
            continue
        bounds = _BOUNDS_RE.fullmatch(str(node.attrib.get("bounds", "")))
        if bounds is None:
            continue
        left, top, right, bottom = map(int, bounds.groups())
        width = right - left
        height = bottom - top
        if width < 500 or height < 300:
            continue
        return {
            "login": (left + round(width * 0.50), top + round(height * 0.083)),
            "password": (left + round(width * 0.50), top + round(height * 0.215)),
            "submit": (left + round(width * 0.42), top + round(height * 0.347)),
        }
    return None


def extract_igg_unregistered_cancel_target(ui_xml):
    """Return the safe cancel target from IGG's unregistered-email dialog."""
    try:
        root = ET.fromstring(str(ui_xml or ""))
    except ET.ParseError:
        return None

    labels = " ".join(
        " ".join(
            (
                str(node.attrib.get("text", "")),
                str(node.attrib.get("content-desc", "")),
            )
        )
        for node in root.iter()
    ).casefold()
    if "not registered" not in labels and "не зарегистрирован" not in labels:
        return None

    candidates = []
    for node in root.iter():
        if node.attrib.get("clickable") != "true":
            continue
        bounds = _BOUNDS_RE.fullmatch(str(node.attrib.get("bounds", "")))
        if bounds is None:
            continue
        left, top, right, bottom = map(int, bounds.groups())
        width = right - left
        height = bottom - top
        if 300 <= top <= 520 and 80 <= width <= 400 and 30 <= height <= 100:
            candidates.append(((left + right) // 2, (top + bottom) // 2))
    if len(candidates) < 2:
        return None
    return min(candidates, key=lambda point: (point[0], point[1]))


def extract_igg_id_targets(ui_xml):
    """Return saved IGG ID rows from the account-selection WebView."""
    try:
        root = ET.fromstring(str(ui_xml or ""))
    except ET.ParseError:
        return []

    page_title_visible = any(
        "igg id" in " ".join(
            (
                str(node.attrib.get("text", "")),
                str(node.attrib.get("content-desc", "")),
            )
        ).casefold()
        for node in root.iter()
        if node.attrib.get("class") == "android.widget.TextView"
    )
    if not page_title_visible:
        return []

    centers = []
    seen = set()
    for node in root.iter():
        if node.attrib.get("class") != "android.widget.TextView":
            continue
        label = str(node.attrib.get("text", "")).strip()
        if re.match(r"^IGG\s*ID\s*:\s*\d+", label, re.IGNORECASE) is None:
            continue
        bounds = _BOUNDS_RE.fullmatch(str(node.attrib.get("bounds", "")))
        if bounds is None:
            continue
        left, top, right, bottom = map(int, bounds.groups())
        if right <= left or bottom <= top or top < 68:
            continue
        center = ((left + right) // 2, (top + bottom) // 2)
        if center not in seen:
            seen.add(center)
            centers.append(center)

    centers.sort(key=lambda point: (point[1], point[0]))
    return [
        {"chooser_index": index, "center": center}
        for index, center in enumerate(centers, start=1)
    ]


def mask_google_account(email):
    value = str(email or "").strip()
    if "@" not in value:
        return value
    local, domain = value.split("@", 1)
    visible = local[:1]
    return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"


def mask_account_login(login):
    value = str(login or "").strip()
    if "@" in value:
        return mask_google_account(value)
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[:1]}{'*' * max(3, len(value) - 2)}{value[-1:]}"
