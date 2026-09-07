from pathlib import Path
import unittest

import cv2
import numpy as np

from buzzbot.alliance_gifts import (
    AllianceGiftFlow, GiftAction, selected_gift_tab,
    detect_alliance_gift_claim, detect_alliance_activity_collect_all,
    gift_claim_is_confirmed, gift_reward_popup_is_visible,
    gift_empty_notice_is_visible, purchase_badge_digits,
    shifted_gift_claim_is_confirmed,
)


FIXTURES = Path(__file__).parent / 'assets/alliance_gifts'


def frame(name):
    result = cv2.imread(str(FIXTURES / f'{name}.png'))
    if result is None:
        raise AssertionError(f'Missing gift fixture: {name}')
    return result


class AllianceGiftTests(unittest.TestCase):
    def test_tabs_and_free_claims_are_recognized_at_supported_scales(self):
        for size in ((1280, 720), (1920, 1080)):
            with self.subTest(size=size):
                activity = cv2.resize(frame('activity_before'), size)
                purchase = cv2.resize(frame('purchase_before'), size)
                self.assertEqual(selected_gift_tab(activity), 'activity')
                self.assertEqual(selected_gift_tab(purchase), 'purchase')
                self.assertIsNotNone(detect_alliance_gift_claim(purchase))
                self.assertIsNotNone(detect_alliance_activity_collect_all(activity))
                self.assertIsNone(detect_alliance_activity_collect_all(purchase))

    def test_subscription_dialog_does_not_authorize_any_gift_action(self):
        popup = frame('purchase_subscription')
        self.assertIsNone(selected_gift_tab(popup))
        self.assertIsNone(detect_alliance_gift_claim(popup))
        self.assertFalse(gift_reward_popup_is_visible(popup))
        flow = AllianceGiftFlow({}, 0)
        self.assertEqual(flow.next_action(popup, 7).kind, 'unavailable')

    def test_tap_is_not_counted_until_receipt_is_visible(self):
        before, after = frame('purchase_before'), frame('purchase_after')
        flow = AllianceGiftFlow({'collect_activity': False}, 0)
        action = GiftAction('claim', (1144, 182))
        flow.record(action, before, 1)
        self.assertEqual(flow.next_action(before, 3).kind, 'wait')
        self.assertEqual(flow.purchase_count, 0)
        self.assertTrue(gift_claim_is_confirmed(after, action.target))
        self.assertEqual(flow.next_action(after, 4).kind, 'wait')
        self.assertEqual(flow.purchase_count, 1)

    def test_shifted_receipt_requires_changed_count_and_correct_page(self):
        before, shifted = frame('purchase_after'), frame('purchase_shifted')
        digits = purchase_badge_digits(before)
        self.assertFalse(gift_claim_is_confirmed(shifted, (1144, 586)))
        self.assertTrue(shifted_gift_claim_is_confirmed(shifted, digits))
        self.assertFalse(shifted_gift_claim_is_confirmed(before, digits))
        self.assertFalse(shifted_gift_claim_is_confirmed(frame('activity_empty'), digits))
        flow = AllianceGiftFlow({'collect_activity': False}, 0)
        flow.record(GiftAction('claim', (1144, 586)), before, 1)
        flow.next_action(shifted, 3)
        self.assertEqual(flow.purchase_count, 1)

    def test_unconfirmed_claim_stops_without_clicking_another_gift(self):
        before = frame('purchase_before')
        flow = AllianceGiftFlow({'collect_activity': False}, 0)
        flow.record(GiftAction('claim', (1144, 182)), before, 1)
        self.assertEqual(flow.next_action(before, 8).kind, 'unavailable')
        self.assertEqual(flow.purchase_count, 0)

    def test_bulk_collection_requires_received_rewards_or_empty_confirmation(self):
        before = frame('activity_before')
        flow = AllianceGiftFlow({'collect_purchase': False}, 0)
        action = flow.next_action(before, 1)
        self.assertEqual(action.kind, 'collect_all')
        flow.record(action, before, 1)
        self.assertEqual(flow.next_action(before, 3).kind, 'wait')
        reward = frame('activity_reward')
        self.assertTrue(gift_reward_popup_is_visible(reward))
        close = flow.next_action(reward, 4)
        self.assertEqual(close.kind, 'dismiss')
        flow.record(close, reward, 4)
        self.assertEqual(flow.next_action(before, 6).kind, 'complete')
        self.assertEqual(flow.activity_result, 'collected_all')

    def test_empty_activity_moves_to_purchase_tab(self):
        before, empty = frame('activity_before'), frame('activity_empty')
        flow = AllianceGiftFlow({}, 0)
        flow.record(flow.next_action(before, 1), before, 1)
        self.assertTrue(gift_empty_notice_is_visible(empty))
        flow.next_action(empty, 3)
        action = flow.next_action(empty, 4)
        self.assertEqual(action.kind, 'tap')
        self.assertGreater(action.target[0], 970)
        self.assertEqual(flow.activity_result, 'empty')

    def test_failed_tab_navigation_is_bounded(self):
        purchase = frame('purchase_before')
        flow = AllianceGiftFlow({}, 0)
        for now in (1, 3, 5):
            action = flow.next_action(purchase, now)
            self.assertEqual(action.kind, 'tap')
            flow.record(action, purchase, now)
        self.assertEqual(flow.next_action(purchase, 7).kind, 'unavailable')

    def test_claims_are_rejected_without_both_gift_tab_headers(self):
        purchase = frame('purchase_before')
        purchase[:125] = 0
        self.assertIsNone(detect_alliance_gift_claim(purchase))
        self.assertIsNone(detect_alliance_gift_claim(np.zeros((720, 1280, 3), dtype=np.uint8)))

    def test_bottom_with_remaining_gifts_triggers_a_bounded_return_to_top(self):
        page = frame('purchase_before')
        page[125:637] = 0
        flow = AllianceGiftFlow({'collect_activity': False}, 0)
        for now in (1, 3):
            action = flow.next_action(page, now)
            self.assertEqual(action.kind, 'swipe')
            self.assertGreater(action.target[1], action.target[3])
            flow.record(action, page, now)
        action = flow.next_action(page, 5)
        self.assertEqual(action.kind, 'swipe')
        self.assertLess(action.target[1], action.target[3])
        flow.record(action, page, 5)
        action = flow.next_action(page, 7)
        flow.record(action, page, 7)
        self.assertEqual(flow.next_action(page, 9).kind, 'unavailable')


if __name__ == '__main__':
    unittest.main()
