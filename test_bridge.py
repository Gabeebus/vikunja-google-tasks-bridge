import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from bridge import State, Vikunja, Google, synchronize

BASE = dict(title='Example', notes='Notes', due=None, status='Next')


class Fake:
    def __init__(self, tasks=None):
        self.tasks = tasks or {}
        self.writes = 0
        self.fail_after_create = False

    def snapshot(self):
        return copy.deepcopy(self.tasks)

    def write(self, ident, value, key, current=None):
        self.writes += 1
        ident = ident or str(len(self.tasks) + 100)
        self.tasks[ident] = dict(value=copy.deepcopy(value), key=key)
        if self.fail_after_create:
            self.fail_after_create = False
            raise RuntimeError('Simulated disconnect after remote commit')
        return ident


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = State(str(Path(self.temp.name) / 'state.sqlite'))

    def tearDown(self):
        self.state.db.close()
        self.temp.cleanup()

    def test_interrupted_create_recovers_by_marker_without_duplicate(self):
        v, g = Fake({'1': dict(value=BASE, key=None)}), Fake()
        synchronize(v, g, self.state)
        g.fail_after_create = True
        with self.assertRaises(RuntimeError):
            synchronize(v, g, self.state)
        synchronize(v, g, self.state)
        synchronize(v, g, self.state)
        self.assertEqual(len(g.tasks), 1)
        self.assertEqual(g.writes, 1)
        self.assertIsNone(self.state.rows()[0][4])

    def test_missing_task_is_held_without_recreation(self):
        self.state.save('abc', '1', '2', BASE)
        v, g = Fake({'1': dict(value=BASE, key='abc')}), Fake()
        synchronize(v, g, self.state)
        self.assertEqual(g.writes, 0)
        self.assertIn('Missing', self.state.rows()[0][4])

    def test_conflicts_hold_both_sides(self):
        self.state.save('abc', '1', '2', BASE)
        v = Fake({'1': dict(value=dict(BASE, title='Local'), key='abc')})
        g = Fake({'2': dict(value=dict(BASE, title='Google'), key='abc')})
        synchronize(v, g, self.state)
        self.assertEqual(v.writes + g.writes, 0)
        self.assertIn('title', self.state.rows()[0][4])

    def test_read_failure_does_not_write(self):
        v, g = Fake({'1': dict(value=BASE, key=None)}), Fake()
        g.snapshot = Mock(side_effect=RuntimeError('API unavailable'))
        with self.assertRaises(RuntimeError):
            synchronize(v, g, self.state)
        self.assertEqual(v.writes, 0)
        self.assertEqual(self.state.rows(), [])

    def test_check_is_read_only(self):
        v, g = Fake({'1': dict(value=BASE, key=None)}), Fake()
        synchronize(v, g, self.state, check=True)
        self.assertEqual(self.state.rows(), [])
        self.assertEqual(v.writes + g.writes, 0)

    def test_check_detects_new_conflicts_without_persisting_or_writing(self):
        self.state.save('abc','1','2',BASE)
        before=self.state.rows()
        v=Fake({'1':dict(value=dict(BASE,title='Left'),key='abc')})
        g=Fake({'2':dict(value=dict(BASE,title='Right'),key='abc')})
        synchronize(v,g,self.state,check=True)
        self.assertEqual(self.state.detected_issues,{'abc'})
        self.assertEqual(self.state.rows(),before)
        self.assertEqual(v.writes+g.writes,0)

    def test_check_detects_missing_counterpart_without_recreation(self):
        self.state.save('abc','1','2',BASE)
        before=self.state.rows()
        v=Fake({'1':dict(value=BASE,key='abc')});g=Fake()
        synchronize(v,g,self.state,check=True)
        self.assertEqual(self.state.detected_issues,{'abc'})
        self.assertEqual(self.state.rows(),before)
        self.assertEqual(v.writes+g.writes,0)

    def test_google_reads_completed_hidden_and_all_pages(self):
        g = object.__new__(Google)
        g.lists = {'Next': 'managed'}
        g.call = Mock(side_effect=[({'items': [dict(id='1', title='A', status='completed')], 'nextPageToken': 'next'}, {}),
                                   ({'items': [dict(id='2', title='B', status='needsAction')]}, {})])
        tasks = g.snapshot()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks['1']['value']['status'], 'Completed')
        self.assertEqual(g.call.call_args_list[1].kwargs['params']['pageToken'], 'next')
        self.assertEqual(g.call.call_args_list[0].kwargs['params']['showHidden'], 'true')

    def test_kanban_pagination_includes_completed(self):
        from zoneinfo import ZoneInfo
        v = object.__new__(Vikunja)
        v.project, v.view, v.zone = 2, 12, ZoneInfo('America/New_York')
        a = dict(id=1, project_id=2, title='A', done=False, description='')
        b = dict(id=2, project_id=2, title='B', done=True, description='')
        v.call = Mock(side_effect=[([dict(id=7, count=2, title='Next', tasks=[a])], {}),
                                   ([dict(id=7, count=2, title='Next', tasks=[b])], {})])
        tasks = v.snapshot()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks['2']['value']['status'], 'Completed')
        self.assertEqual(v.call.call_args_list[1].kwargs['params']['page'], 2)

    def test_incomplete_snapshot_fails_before_sync(self):
        v = object.__new__(Vikunja)
        v.project, v.view = 2, 12
        v.call = Mock(return_value=([dict(id=7, count=2, title='Next', tasks=[])], {}))
        with self.assertRaises(ValueError):
            v.snapshot()


if __name__ == '__main__':
    unittest.main()
