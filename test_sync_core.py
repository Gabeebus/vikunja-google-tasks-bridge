import unittest
from sync_core import merge, marked_notes, split_marker, validate


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(title='Task', notes='Keep this', due=None, status='Next')

    def test_independent_changes_merge(self):
        left = dict(self.base, title='Renamed')
        right = dict(self.base, status='Waiting')
        result, conflicts = merge(self.base, left, right)
        self.assertFalse(conflicts)
        self.assertEqual(result, dict(self.base, title='Renamed', status='Waiting'))

    def test_conflicting_edit_is_not_overwritten(self):
        result, conflicts = merge(self.base, dict(self.base, notes='A'), dict(self.base, notes='B'))
        self.assertEqual(conflicts, ['notes'])
        self.assertNotIn('notes', result)

    def test_convergent_changes_are_not_conflicts(self):
        updated = dict(self.base, status='Completed')
        self.assertEqual(merge(self.base, updated, updated), (updated, []))

    def test_clear_date_propagates(self):
        base = dict(self.base, due='2026-11-03')
        self.assertEqual(merge(base, dict(base, due=None), base)[0]['due'], None)

    def test_markers_are_idempotent(self):
        notes = marked_notes('Keep this', 'abc-123')
        self.assertEqual(marked_notes(notes, 'abc-123'), notes)
        self.assertEqual(split_marker(notes), ('Keep this', 'abc-123'))

    def test_oversized_notes_fail_without_truncation(self):
        with self.assertRaises(ValueError):
            validate(dict(self.base, notes='x' * 8001))


if __name__ == '__main__':
    unittest.main()
