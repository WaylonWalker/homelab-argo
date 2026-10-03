import copy
import importlib.util
import pathlib
import unittest
import urllib.error

spec = importlib.util.spec_from_file_location('cleanup', pathlib.Path(__file__).parents[1] / 'k8s/cloudflared/pod_cleanup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def pod(number, phase='Failed'):
    return {'metadata': {'namespace': 'cloudflared', 'name': f'pod-{number:04}', 'uid': str(number),
                         'creationTimestamp': f'2026-10-02T00:{number:02}:00Z',
                         'labels': {'pod': 'cloudflared'}, 'ownerReferences': [
                             {'kind': 'ReplicaSet', 'controller': True, 'name': 'cloudflared-deployment-123'}]},
            'status': {'phase': phase}}


class FakeAPI:
    def __init__(self, pods):
        self.items = pods
        self.deleted = []
        self.changed = {}
        self.errors = {}

    def pods(self):
        return self.items

    def request(self, suffix, method='GET', body=None):
        name = suffix[1:]
        if name in self.errors:
            raise urllib.error.HTTPError('', self.errors[name], '', {}, None)
        item = next(p for p in self.items if p['metadata']['name'] == name)
        if method == 'GET':
            return self.changed.get(name, item)
        assert body['preconditions']['uid'] == item['metadata']['uid']
        self.deleted.append(name)
        return {}


class CleanupTests(unittest.TestCase):
    def test_keeps_newest_across_terminal_phases_and_excludes_other_pods(self):
        pods = [pod(i, 'Succeeded' if i % 2 else 'Failed') for i in range(30)]
        pods += [pod(40, 'Running'), pod(41, 'Pending')]
        foreign = pod(42)
        foreign['metadata']['ownerReferences'][0]['name'] = 'other-controller'
        pods.append(foreign)
        missing_label = pod(43)
        missing_label['metadata']['labels'] = {}
        pods.append(missing_label)
        api = FakeAPI(pods)
        self.assertEqual(module.cleanup(api, 20), 10)
        self.assertEqual(set(api.deleted), {f'pod-{i:04}' for i in range(10)})

    def test_rechecks_phase_and_uid_and_handles_disappearing_pods(self):
        api = FakeAPI([pod(i) for i in range(6)])
        api.changed['pod-0000'] = pod(0, 'Running')
        changed = copy.deepcopy(pod(1))
        changed['metadata']['uid'] = 'replacement'
        api.changed['pod-0001'] = changed
        api.errors = {'pod-0002': 404, 'pod-0003': 409}
        self.assertEqual(module.cleanup(api, 1), 1)
        self.assertEqual(api.deleted, ['pod-0004'])

    def test_dry_run_never_deletes(self):
        api = FakeAPI([pod(i) for i in range(4)])
        self.assertEqual(module.cleanup(api, 1, True), 3)
        self.assertEqual(api.deleted, [])

    def test_pagination_for_both_phases(self):
        api = object.__new__(module.API)
        queries = []
        def request(suffix):
            queries.append(suffix)
            return {'items': [pod(len(queries))], 'metadata': {'continue': 'next' if len(queries) == 1 else ''}}
        api.request = request
        self.assertEqual(len(api.pods()), 3)
        self.assertIn('continue=next', queries[1])
        self.assertIn('Succeeded', queries[2])


if __name__ == '__main__':
    unittest.main()
