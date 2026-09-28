"""Exercise the installed GUI and OCR in a temporary database, without touching user data."""
import json
from pathlib import Path
import tempfile
import shutil
import time
import traceback


def check_installation(report_path, image_path=None, auction_image=None):
    report = {'ok': False}
    root = None
    try:
        import tkinter as tk
        from gear_value.desktop import DesktopApp, ASSETS
        from gear_value.storage import Store
        from gear_value.valuation import estimate
        with tempfile.TemporaryDirectory(prefix='gear-install-check-') as folder:
            root = tk.Tk(); root.withdraw()
            store = Store(folder, ASSETS / 'seed.json')
            app = DesktopApp(root, store)
            assert len(app.stat_rows['base_stats']) == 2
            assert len(app.stat_rows['stats']) == 3
            assert all(not row[2].get() for rows in app.stat_rows.values() for row in rows)
            report['default_fields'] = {'base_stats':2, 'stats':3, 'rarity':'legendary'}
            rows = store.read()
            elite = next((row for row in rows if row['rarity'] == 'elite'), None)
            if elite:
                app.fill_item(elite)
                try:
                    app.get_item()
                except ValueError as exc:
                    assert 'только золотые' in str(exc)
                else:
                    raise AssertionError('Non-gold equipment was accepted for evaluation')
            app.fill_item(rows[0])
            assert app.get_item()['stats'] == rows[0]['stats']
            app.calculate()
            for row in rows:
                result = estimate(row, rows, exclude_id=row['id'])
                assert 'market_signals' in result
            renamed = {**rows[0], 'name': ''}
            original = estimate(rows[0], rows, exclude_id=rows[0]['id'])
            renamed_result = estimate(renamed, rows, exclude_id=rows[0]['id'])
            assert original == renamed_result, 'Item name changed the valuation'
            report.update(window='ok', pricing='ok', bundled_records=len(rows))
            if image_path:
                app.load_path(image_path)
                deadline = time.monotonic() + 60
                while app.busy and time.monotonic() < deadline:
                    root.update(); time.sleep(.03)
                assert not app.busy, 'OCR timeout'
                assert app.preview_image is not None, app.status.get()
                assert not app.evidence
                assert not (Path(folder) / 'screenshots').exists(), 'Evaluation image was persisted'
                item = app.get_item()
                app.calculate()
                report.update(ocr='ok', name=item['name'], level=item['level'], stats=item['stats'],
                              base_stats=item['base_stats'],
                              displayed_labels=[row[1].get() for row in app.stat_rows['stats']],
                              displayed_base_labels=[row[1].get() for row in app.stat_rows['base_stats']],
                              displayed_stat_values=[row[2].get() for row in app.stat_rows['stats']],
                              displayed_base_values=[row[2].get() for row in app.stat_rows['base_stats']],
                              result=app.output.get('1.0', 'end').strip())
            assert store.read() == rows, 'Check changed observations'
            if auction_image:
                incoming = app.importer.inbox / 'installation-check.png'
                shutil.copy2(auction_image, incoming)
                deadline = time.monotonic() + 60
                while (incoming.exists() or app.busy) and time.monotonic() < deadline:
                    root.update(); time.sleep(.03)
                assert not incoming.exists(), app.importer.snapshot()
                entry = app.importer.snapshot()[0]
                assert entry['status'] in ('saved', 'duplicate'), entry
                if entry['status'] == 'saved':
                    assert entry['record']['evidence'] == ''
                assert not (Path(folder) / 'screenshots').exists(), 'Importer stored an image copy'
                report.update(automatic_import='ok', import_status=entry['status'], import_price=entry['record']['price'], processed_copy_deleted=True)
            root.destroy(); root = None
            report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if root:
            root.destroy()
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
