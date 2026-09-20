from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from research_campaigns.agents import ProgrammeSteward, StudyProducer
from research_campaigns.core import BudgetStopped, Denied, Ledger, digest
from research_campaigns.demo import fixtures, stamp
from research_campaigns.providers import BaselineProvider, Budget, ResponsesProvider, Session


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = fixtures()

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'research_campaigns', *map(str, args)],
                              capture_output=True, text=True, timeout=15)

    def test_cli_help_and_demo_all_agents(self):
        self.assertEqual(self.cli('--help').returncode, 0)
        demo = self.cli('demo', '--output', self.root / 'demo')
        self.assertEqual(demo.returncode, 0, demo.stderr)
        report = json.loads(demo.stdout)
        self.assertEqual(report['programme_independent_periods'], [1, 1, 2])
        self.assertEqual(report['programme_vintages'], [1, 2, 3])
        self.assertEqual([x['candidates'] for x in report['replay']['steps']], [0, 1, 1, 1, 2])
        self.assertFalse(report['live_provider_called'])
        repeated = self.cli('demo', '--output', self.root / 'demo')
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout), report)

    def test_cli_agents_and_human_time(self):
        for name in ('sources', 'brief', 'baseline', 'programme_sources', 'portfolio'):
            (self.root / (name + '.json')).write_text(json.dumps(self.data[name]))
        study = self.cli('study', '--brief', self.root / 'brief.json', '--sources', self.root / 'sources.json',
                         '--workspace', self.root / 'study', '--synthetic')
        self.assertEqual(study.returncode, 0, study.stderr)
        audit = self.cli('audit', '--workspace', self.root / 'study')
        self.assertEqual(json.loads(audit.stdout)['integrity'], 'passed')
        initial = self.cli('programme-init', '--baseline', self.root / 'baseline.json', '--workspace', self.root / 'programme')
        self.assertEqual(initial.returncode, 0, initial.stderr)
        update = self.cli('programme-update', '--programme-id', 'PROGRAMME-DEMO', '--sources', self.root / 'programme_sources.json',
                          '--cutoff', stamp(3, 28), '--workspace', self.root / 'programme', '--synthetic')
        self.assertEqual(update.returncode, 0, update.stderr)
        self.assertIn('model_interpretation', json.loads(update.stdout))
        scout = self.cli('scout', '--portfolio', self.root / 'portfolio.json', '--sources', self.root / 'sources.json',
                         '--cutoff', stamp(4, 30), '--workspace', self.root / 'scout', '--synthetic')
        self.assertEqual(scout.returncode, 0, scout.stderr)
        human = self.cli('human-time', '--workspace', self.root / 'study', '--event-id', 'review-1',
                         '--category', 'evaluation', '--minutes', 12)
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertEqual(json.loads(human.stdout)['active_minutes'], 12)

    def test_programme_model_cannot_confirm_theory(self):
        class Confirmer(BaselineProvider):
            def complete(self, task, context):
                answer, usage = super().complete(task, context)
                if task == 'programme_review':
                    answer['empirical_confirmation'] = True
                return answer, usage
        db = Ledger(self.root / 'state.sqlite')
        try:
            agent = ProgrammeSteward(db, Session(db, Confirmer(), Budget()))
            agent.initialise(self.data['baseline'])
            with self.assertRaises(Denied):
                agent.update('PROGRAMME-DEMO', self.data['programme_sources'], stamp(3, 28), synthetic=True)
            self.assertTrue(db.items('observations:PROGRAMME-DEMO'))
            self.assertFalse(db.items('programme_updates:PROGRAMME-DEMO'))
            self.assertTrue(db.items('model_finish'))  # Original decision retained.
        finally:
            db.close()

    def test_study_changed_evidence_cannot_reuse_stale_result(self):
        db = Ledger(self.root / 'state.sqlite')
        try:
            agent = StudyProducer(db, Session(db, BaselineProvider(), Budget()))
            agent.run(self.data['brief'], self.data['sources'], synthetic=True)
            changed = deepcopy(self.data['sources'])
            changed[0]['payload']['rows'][0]['payment_days'] = 999
            changed[0]['sha256'] = digest(changed[0]['payload'])
            with self.assertRaises(Denied):
                agent.run(self.data['brief'], changed, synthetic=True)
        finally:
            db.close()

    def test_provider_overrun_stops_subsequent_calls(self):
        class Overrun(BaselineProvider):
            name, remote = 'mock-overrun', True
            def complete(self, task, context):
                return {'candidates': []}, {'input_tokens': 10_000_000, 'output_tokens': 0}
        db = Ledger(self.root / 'overrun.sqlite')
        try:
            session = Session(db, Overrun(), Budget(max_usd=100, allow_network=True, input_usd_per_million=1, output_usd_per_million=1))
            with self.assertRaises(BudgetStopped):
                session.ask('scout', {'sources': {}, 'portfolio': []})
            with self.assertRaises(BudgetStopped):
                session.ask('scout', {'sources': {}, 'portfolio': [], 'new': True})
            self.assertEqual(session.resources()['model_calls'], 1)
            self.assertIsNone(session.resources()['billed_usd'])
        finally:
            db.close()

    def test_responses_adapter_payload_without_live_api(self):
        provider = ResponsesProvider('operator-configured-model', 100)
        payload = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"candidates":[]}'}]}],
                   'usage': {'input_tokens': 100, 'output_tokens': 10}}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return json.dumps(payload).encode()
        class Opener:
            def open(self, request, timeout):
                self.request = request
                return Response()
        opener = Opener()
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'mock-not-a-real-key'}), patch('urllib.request.build_opener', return_value=opener):
            response, usage = provider.complete('scout', {'sources': {}, 'portfolio': []})
        request = json.loads(opener.request.data)
        self.assertFalse(request['store'])
        self.assertNotIn('tools', request)
        self.assertNotIn('previous_response_id', request)
        self.assertEqual(request['model'], 'operator-configured-model')
        self.assertEqual(response, {'candidates': []})
        self.assertEqual(usage['input_tokens'], 100)


if __name__ == '__main__':
    unittest.main()
