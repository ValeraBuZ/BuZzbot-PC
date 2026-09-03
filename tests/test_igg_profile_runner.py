import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import tools.run_igg_profile_tasks as runner


class IggProfileRunnerTests(unittest.TestCase):
    def test_task_failure_stops_only_the_current_profile(self):
        class Switcher:
            def __init__(self):
                self.account_profiles = [
                    {"id": "first", "name": "First", "login_method": "igg"},
                    {"id": "second", "name": "Second", "login_method": "igg"},
                ]
                self._thread = None

            def stop_schedule_thread(self):
                return None

            def _refresh_adb_client(self):
                return None

            def _return_to_main_screen(self, **_kwargs):
                return True

            def stop(self):
                return None

        switcher = Switcher()
        switched = []
        task_accounts = []

        def switch_account(_bot, account_id, timeout_seconds):
            switched.append((account_id, timeout_seconds))
            return True, f"switched {account_id}"

        def run_task(_serial, account_id, task_id, *_args):
            task_accounts.append((account_id, task_id))
            if account_id == "first":
                return {"task": task_id, "settled": False, "error": "probe failure"}
            return {"task": task_id, "settled": True, "error": ""}

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            argv = [
                "run_igg_profile_tasks.py",
                "--accounts",
                "first,second",
                "--tasks",
                "food",
                "--output",
                str(output),
            ]
            with (
                patch("sys.argv", argv),
                patch.object(runner, "find_ldconsole", return_value="ldconsole"),
                patch.object(
                    runner,
                    "list_instances",
                    return_value=[SimpleNamespace(index=5, running=True)],
                ),
                patch.object(runner, "AdbClient", return_value=object()),
                patch.object(runner, "_wait_for_adb", return_value="emulator-5564"),
                patch.object(runner, "_new_read_only_bot", return_value=switcher),
                patch.object(runner, "_switch_account", side_effect=switch_account),
                patch.object(runner, "_wait_for_main_screen", return_value=True),
                patch.object(runner, "run_task", side_effect=run_task),
            ):
                exit_code = runner.main()

            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual([item[0] for item in switched], ["first", "second"])
        self.assertEqual(task_accounts, [("first", "food"), ("second", "food")])
        self.assertEqual(len(summary), 2)
        self.assertIn("strict pass stopped after food", summary[0]["switch_detail"])
        self.assertTrue(summary[1]["tasks"][0]["settled"])


if __name__ == "__main__":
    unittest.main()
