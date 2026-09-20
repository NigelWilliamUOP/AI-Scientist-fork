from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from research_campaigns.agents import OpportunityScout, ProgrammeSteward, StudyProducer, analyse
from research_campaigns.core import (BudgetStopped, ContractError, Denied, EvidenceBroker, Ledger,
    ReconciliationRequired, digest, instant, select_portfolio, select_sources, source_key, write_once)
from research_campaigns.demo import fixtures, snapshot, stamp
from research_campaigns.providers import BaselineProvider, Budget, Session, ResponsesProvider
from research_campaigns.replay import run_replay
from research_campaigns.connectors import capture_watchlist, validate_url


class SpyProvider(BaselineProvider):
    def __init__(self):
        self.contexts = []

    def complete(self, task, context):
        self.contexts.append((task, deepcopy(context)))
        return super().complete(task, context)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Ledger(self.root / 'state.sqlite')
        self.data = fixtures()
        self.provider = SpyProvider()
        self.session = Session(self.db, self.provider, Budget())
        self.scout = OpportunityScout(self.db, self.session)
        self.steward = ProgrammeSteward(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def scout_run(self, **kwargs):
        return self.scout.run(kwargs.pop('cards', self.data['portfolio']), kwargs.pop('sources', self.data['sources']),
                              kwargs.pop('cutoff', stamp(4, 30)), synthetic=True, **kwargs)

    def init_programme(self):
        return self.steward.initialise(self.data['baseline'])

    def test_T01_bounded_study(self):
        answer = StudyProducer(self.db, self.session).run(self.data['brief'], self.data['sources'], synthetic=True)
        self.assertEqual(answer['status'], 'review_candidate')
        self.assertEqual(answer['analysis']['result']['mean'], 25)
        self.assertEqual(answer['journal_readiness'], 'not_evaluated')
        self.assertEqual(self.db.items('programme_baselines'), [])
        self.assertIn('Synthetic payment timing', answer['manuscript_markdown'])

    def test_T02_evolving_phenomenon(self):
        outcome = self.init_programme()
        self.assertEqual(outcome['status'], 'awaiting_release')
        self.assertEqual(outcome['scientific_status'], 'unverified')
        self.assertEqual(self.db.items('study_results'), [])

    def test_T03_routine_owned_release(self):
        card = deepcopy(self.data['portfolio'][0])
        card['claims'][0]['owner_programme'] = 'PROGRAMME-DEMO'
        card['sha256'] = digest({k: v for k, v in card.items() if k != 'sha256'})
        answer = self.scout_run(cards=[card], sources=[self.data['sources'][0]])
        self.assertEqual(answer['handovers'][0]['destination'], 'programme_steward')
        self.assertEqual(answer['handovers'][0]['programme_id'], 'PROGRAMME-DEMO')
        self.assertEqual(self.db.items('programme_baselines'), [])

    def test_T04_frequency_mismatch(self):
        self.init_programme()
        answer = self.steward.update('PROGRAMME-DEMO', [self.data['programme_sources'][3]], stamp(3), synthetic=True)
        self.assertEqual(answer['status'], 'no_eligible_update')
        self.assertEqual(answer['independent_periods'], 0)
        self.assertEqual(answer['ignored_observations'][0]['reason'], 'frequency_or_unit_mismatch')

    def test_T05_duplicate_and_revision(self):
        self.init_programme()
        first = self.steward.update('PROGRAMME-DEMO', self.data['programme_sources'], stamp(2, 28), synthetic=True)
        count = self.db.verify()['events']
        duplicate = self.steward.update('PROGRAMME-DEMO', self.data['programme_sources'], stamp(2, 28), synthetic=True)
        self.assertEqual(first, duplicate)
        self.assertEqual(count, self.db.verify()['events'])
        second = self.steward.update('PROGRAMME-DEMO', self.data['programme_sources'], stamp(3, 28), synthetic=True)
        self.assertEqual(second['independent_periods'], 1)
        self.assertEqual(second['admitted_vintages'], 2)
        self.assertEqual(second['changes'][0]['change'], 'revision')

    def test_T06_future_information(self):
        answer = self.scout_run(cutoff=stamp(1, 31))
        serialised = json.dumps(self.provider.contexts)
        self.assertNotIn('counterexample-data', serialised)
        self.assertNotIn('future-data', serialised)
        self.assertTrue(any(e['reason'] == 'published_after_cutoff' for e in answer['exclusions']))

    def test_T07_invalid_proxy_or_join(self):
        answer = self.scout_run(sources=[self.data['sources'][1]])
        self.assertEqual(answer['status'], 'watch_data_gap')
        self.assertEqual(answer['candidates'], [])
        self.assertIn('unit_mismatch', answer['rejected'][0]['reasons'])

    def test_T08_contradiction(self):
        before = digest(self.data['portfolio'])
        answer = self.scout_run(sources=[self.data['sources'][3]])
        self.assertEqual(answer['candidates'][0]['extension_type'], 'contradiction')
        self.assertEqual(answer['handovers'][0]['destination'], 'verification_queue')
        self.assertEqual(before, digest(self.data['portfolio']))
        self.assertFalse(answer['candidates'][0]['pilot_authorised'])

    def test_T09_protected_baseline(self):
        self.init_programme()
        altered = deepcopy(self.data['baseline'])
        altered['predictions'][0]['interval'] = [200, 300]
        with self.assertRaises(Denied):
            self.steward.initialise(altered)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.db.execute("UPDATE facts SET payload='{}' WHERE namespace='programme_baselines'")
        self.db.verify()

    def test_T10_scientific_failure(self):
        original = self.provider.complete
        def faulty(task, context):
            reply, usage = original(task, context)
            if task == 'study_write':
                reply['fatal_defects'].append('Synthetic identification defect')
            return reply, usage
        self.provider.complete = faulty
        answer = StudyProducer(self.db, self.session).run(self.data['brief'], self.data['sources'], synthetic=True)
        self.assertEqual(answer['status'], 'abstained')
        self.assertEqual(answer['journal_readiness'], 'not_evaluated')
        self.assertTrue(self.db.get('study_drafts', 'STUDY-DEMO'))

    def test_T11_budget_limit(self):
        other = Ledger(self.root / 'limited.sqlite')
        try:
            session = Session(other, BaselineProvider(), Budget(max_calls=0))
            answer = OpportunityScout(other, session).run(self.data['portfolio'], self.data['sources'], stamp(4, 30), synthetic=True)
            self.assertEqual(answer['status'], 'stopped_budget')
            self.assertEqual(session.resources()['model_calls'], 0)
        finally:
            other.close()

    def test_T12_interruption_resume(self):
        self.init_programme()
        source = deepcopy(self.data['programme_sources'][0])
        source['payload']['observations'].append({**source['payload']['observations'][0], 'period': '2026-02', 'value': 120})
        source['sha256'] = digest(source['payload'])
        original = self.db._put
        calls = [0]
        def interrupt(namespace, *args):
            if namespace.startswith('observations:'):
                calls[0] += 1
                if calls[0] == 2:
                    raise RuntimeError('simulated process interruption')
            return original(namespace, *args)
        with patch.object(self.db, '_put', side_effect=interrupt):
            with self.assertRaises(RuntimeError):
                self.steward.update('PROGRAMME-DEMO', [source], stamp(3, 28), synthetic=True)
        self.assertEqual(len(self.db.items('observations:PROGRAMME-DEMO')), 1)
        answer = self.steward.update('PROGRAMME-DEMO', [source], stamp(3, 28), synthetic=True)
        self.assertEqual(answer['independent_periods'], 2)
        self.assertEqual(answer['admitted_vintages'], 2)
        self.assertEqual(len(answer['changes']), 2)
        self.db.verify()

    def test_T13_retrieval_outage(self):
        answer = self.scout_run(sources=[], retrieval_errors=[{'source_id': 'all', 'reason': 'outage'}])
        self.assertEqual(answer['status'], 'scan_incomplete')
        self.assertEqual(answer['candidates'], [])

    def test_T14_synthetic_evidence(self):
        self.init_programme()
        answer = self.steward.update('PROGRAMME-DEMO', self.data['programme_sources'], stamp(3, 28), synthetic=True)
        self.assertTrue(answer['prediction_tests'])
        for test in answer['prediction_tests']:
            self.assertFalse(test['empirical_confirmation'])
            self.assertEqual(test['interpretation'], 'Synthetic discrimination only')

    def test_T15_hidden_labels(self):
        hidden = self.root / 'hidden_labels.json'
        hidden.write_text('{"answer":"DO_NOT_DISCLOSE"}')
        broker = EvidenceBroker([self.data['sources'][0]], self.db)
        with self.assertRaises(Denied):
            broker.read(str(hidden))
        with self.assertRaises(Denied):
            broker.read('../../hidden_labels.json')
        self.assertNotIn('DO_NOT_DISCLOSE', json.dumps(broker.context()))
        self.assertEqual(len(self.db.items('denied_reads')), 2)

    def test_T16_known_source_revision(self):
        first = self.scout_run(sources=[self.data['sources'][0]], cutoff=stamp(1, 31))
        revised = self.scout_run(sources=[self.data['sources'][0], self.data['sources'][2]], cutoff=stamp(3, 31))
        self.assertTrue(revised['candidates'][0]['source_revision'])
        self.assertNotEqual(first['candidates'][0]['opportunity_id'], revised['candidates'][0]['opportunity_id'])

    def test_replay_future_portfolio_never_reaches_worker(self):
        self.scout_run(replay=True)
        self.assertNotIn('WITHHELD_FUTURE_PORTFOLIO_NOTE', json.dumps(self.provider.contexts))
        self.assertNotIn('FUTURE-CLAIM', json.dumps(self.provider.contexts))

    def test_replay_late_capture_excluded(self):
        answer = self.scout_run(replay=True, sources=[self.data['sources'][-1]], cutoff=stamp(2, 28))
        self.assertEqual(answer['coverage']['eligible_sources'], 0)
        self.assertEqual(answer['exclusions'][0]['reason'], 'capture_after_cutoff')
        self.assertEqual(self.provider.contexts, [])

    def test_replay_vintage_not_today_revised_series(self):
        old, _ = select_sources(self.data['sources'], stamp(2, 28), allow_synthetic=True)
        new, _ = select_sources(self.data['sources'], stamp(3, 31), allow_synthetic=True)
        self.assertEqual(next(s for s in old if s['source_id'] == 'payment-data')['version'], '1')
        self.assertEqual(next(s for s in new if s['source_id'] == 'payment-data')['version'], '2')

    def test_replay_timezone_boundary(self):
        self.assertEqual(instant('2026-01-10T13:00:00+01:00'), instant(stamp(1)))
        with self.assertRaises(ContractError):
            instant('2026-01-10')
        sources, _ = select_sources([self.data['sources'][0]], stamp(1), allow_synthetic=True)
        self.assertEqual(len(sources), 1)
        sources, _ = select_sources([self.data['sources'][0]], '2026-01-10T11:59:59Z', allow_synthetic=True)
        self.assertEqual(len(sources), 0)

    def test_replay_missing_archive_proof_fail_closed(self):
        source = deepcopy(self.data['sources'][0])
        source.update(kind='observed', access='public')
        eligible, excluded = select_sources([source], stamp(2), replay=True)
        self.assertEqual(eligible, [])
        self.assertEqual(excluded[0]['reason'], 'missing_archive_provenance')

    def test_checksum_tamper_rejected(self):
        source = deepcopy(self.data['sources'][0])
        source['payload']['rows'][0]['payment_days'] = 999
        answer = self.scout_run(sources=[source])
        self.assertEqual(answer['status'], 'scan_incomplete')
        self.assertEqual(answer['coverage']['eligible_sources'], 0)

    def test_conflicting_source_version_quarantines_both(self):
        source = deepcopy(self.data['sources'][0])
        source['payload']['rows'][0]['payment_days'] = 999
        source['sha256'] = digest(source['payload'])
        eligible, exclusions = select_sources([self.data['sources'][0], source], stamp(2), allow_synthetic=True)
        self.assertEqual(eligible, [])
        self.assertTrue(exclusions)

    def test_replay_strict_cutoff_order(self):
        with self.assertRaises(ContractError):
            run_replay([], [], [stamp(2), stamp(1)], self.root / 'replay', self.provider, Budget(), synthetic=True)
        with self.assertRaises(ContractError):
            run_replay([], [], [stamp(1), stamp(1)], self.root / 'replay', self.provider, Budget(), synthetic=True)

    def test_replay_shared_budget_and_isolated_state(self):
        report = run_replay(self.data['portfolio'], self.data['sources'], self.data['cutoffs'], self.root / 'replay',
                            self.provider, Budget(max_calls=1), synthetic=True)
        self.assertEqual(report['resources']['model_calls'], 1)
        self.assertEqual(report['steps'][-1]['status'], 'stopped_budget')
        self.assertFalse(report['candidate_quality_evaluated'])

    def test_replay_idempotent_and_no_network(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network not allowed')):
            one = run_replay(self.data['portfolio'], self.data['sources'], self.data['cutoffs'], self.root / 'replay', self.provider, Budget(), synthetic=True)
            calls = len(self.provider.contexts)
            two = run_replay(self.data['portfolio'], self.data['sources'], self.data['cutoffs'], self.root / 'replay', self.provider, Budget(), synthetic=True)
            self.assertEqual(one, two)
            self.assertEqual(calls, len(self.provider.contexts))

    def test_changed_replay_manifest_denied(self):
        directory = self.root / 'replay'
        run_replay(self.data['portfolio'], self.data['sources'], [stamp(2)], directory, self.provider, Budget(), synthetic=True)
        with self.assertRaises(Denied):
            run_replay(self.data['portfolio'], self.data['sources'], [stamp(3)], directory, self.provider, Budget(), synthetic=True)

    def test_hallucinated_source_fails_gate(self):
        original = self.provider.complete
        def hallucinate(task, context):
            answer, usage = original(task, context)
            if task == 'scout':
                answer['candidates'][0]['source_key'] = 'nonexistent-source'
            return answer, usage
        self.provider.complete = hallucinate
        answer = self.scout_run(sources=[self.data['sources'][0]])
        self.assertFalse(answer['candidates'])
        self.assertEqual(answer['rejected'][0]['status'], 'rejected')

    def test_synthetic_claim_cannot_be_laundered_as_observed(self):
        original = self.provider.complete
        def mislabel(task, context):
            answer, usage = original(task, context)
            if task == 'study_write':
                answer['claims'][0]['kind'] = 'observed'
            return answer, usage
        self.provider.complete = mislabel
        answer = StudyProducer(self.db, self.session).run(self.data['brief'], self.data['sources'], synthetic=True)
        self.assertEqual(answer['status'], 'abstained')
        self.assertIn('Claim changed its evidence category', answer['defects'])

    def test_ols_known_arithmetic(self):
        source = self.data['sources'][0]
        answer = analyse({'method': 'ols', 'source_key': source_key(source), 'x': 'payment_days', 'y': 'buffer_days'}, source)
        self.assertAlmostEqual(answer['result']['slope'], 0.5)
        self.assertEqual(answer['result']['r_squared'], 1.0)

    def test_method_code_execution_denied(self):
        with self.assertRaises(Denied):
            analyse({'method': 'shell', 'source_key': 'x', 'command': 'cat /etc/passwd'}, self.data['sources'][0])

    def test_unknown_required_dataset_blocks_study(self):
        brief = deepcopy(self.data['brief'])
        brief['source_ids'].append('missing-data')
        answer = StudyProducer(self.db, self.session).run(brief, self.data['sources'], synthetic=True)
        self.assertEqual(answer['status'], 'blocked_data')
        self.assertEqual(self.session.resources()['model_calls'], 0)

    def test_postdiction_not_confirmatory(self):
        baseline = deepcopy(self.data['baseline'])
        baseline['locked_at'] = stamp(3)
        for p in baseline['predictions']:
            p['issued_at'] = stamp(3)
        self.steward.initialise(baseline)
        answer = self.steward.update('PROGRAMME-DEMO', self.data['programme_sources'], stamp(3, 28), synthetic=True)
        self.assertTrue(all(t['timing'] == 'retrospective_not_confirmatory' for t in answer['prediction_tests']))

    def test_amendment_never_rewrites_prediction(self):
        self.init_programme()
        original = deepcopy(self.db.get('programme_baselines', 'PROGRAMME-DEMO'))
        amendment = {'amendment_id': 'A1', 'reason': 'New exploratory mechanism', 'proposed_at': stamp(3), 'change': {'hypothesis': 'H3'}}
        answer = self.steward.amend('PROGRAMME-DEMO', amendment)
        self.assertEqual(answer['status'], 'exploratory_proposal')
        self.assertEqual(original, self.db.get('programme_baselines', 'PROGRAMME-DEMO'))

    def test_remote_needs_explicit_authority(self):
        class Remote(BaselineProvider):
            remote, name = True, 'mock-remote'
        db = Ledger(self.root / 'remote.sqlite')
        try:
            session = Session(db, Remote(), Budget())
            with self.assertRaises(Denied):
                session.ask('scout', {'sources': {}, 'portfolio': []})
            self.assertEqual(session.resources()['model_calls'], 0)
        finally:
            db.close()

    def test_uncertain_call_not_retried(self):
        def fail(*args):
            raise TimeoutError('simulated timeout after provider might have charged')
        self.provider.complete = fail
        with self.assertRaises(TimeoutError):
            self.session.ask('scout', {'sources': {}, 'portfolio': []})
        with self.assertRaises(ReconciliationRequired):
            self.session.ask('scout', {'sources': {}, 'portfolio': []})
        self.assertEqual(self.session.resources()['model_calls'], 1)
        self.assertEqual(len(self.session.resources()['unreconciled_calls']), 1)

    def test_budget_cannot_change_silently(self):
        with self.assertRaises(Denied):
            Session(self.db, self.provider, Budget(max_calls=100))

    def test_private_evidence_not_sent_without_permission(self):
        class Remote(BaselineProvider):
            remote, name = True, 'mock-remote'
        db = Ledger(self.root / 'remote.sqlite')
        try:
            session = Session(db, Remote(), Budget(max_usd=1, allow_network=True, input_usd_per_million=1, output_usd_per_million=1))
            with self.assertRaises(Denied):
                session.ask('scout', {'sources': {'x': {'access': 'authorised'}}, 'portfolio': []})
            self.assertEqual(session.resources()['model_calls'], 0)
        finally:
            db.close()

    def test_production_adapter_rejects_redirect_destination(self):
        with self.assertRaises(Denied):
            ResponsesProvider('configured-model', 100, 'https://evil.example/v1/responses')

    def test_connector_denies_local_and_unapproved_urls(self):
        for url in ('file:///etc/passwd', 'http://example.org', 'https://evil.example/x'):
            with self.assertRaises(Denied):
                validate_url(url, ['example.org'])
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(Denied):
                validate_url('https://example.org/a', ['example.org'])

    def test_ingestion_opt_in(self):
        with self.assertRaises(Denied):
            capture_watchlist({'sources': []}, self.root)

    def test_write_once_and_symlink_denial(self):
        path = self.root / 'result.json'
        write_once(path, {'x': 1})
        write_once(path, {'x': 1})
        with self.assertRaises(Denied):
            write_once(path, {'x': 2})
        link = self.root / 'link.json'
        link.symlink_to(path)
        with self.assertRaises(Denied):
            write_once(link, {'x': 1})

    def test_claim_queue_limit_and_no_pilot_execution(self):
        answer = self.scout_run(queue_limit=1)
        self.assertEqual(len(answer['candidates']), 1)
        self.assertEqual(len(answer['deferred']), 1)
        self.assertEqual(answer['candidates'][0]['extension_type'], 'contradiction')
        self.assertEqual(answer['handovers'][0]['status'], 'queued_not_executed')

    def test_human_time_unique_event_and_unknown_totals(self):
        event = {'category': 'evaluation', 'active_minutes': 3, 'measurement': 'operator_recorded'}
        self.db.put('human_time', 'meeting-1', event, 'operator')
        self.db.put('human_time', 'meeting-1', event, 'operator')
        self.assertEqual(len(self.session.resources()['human_time']), 1)
        self.assertEqual(self.session.resources()['human_time_completeness'], 'not_asserted')
        with self.assertRaises(Denied):
            self.db.put('human_time', 'meeting-1', {**event, 'active_minutes': 9}, 'operator')

    def test_no_fabricated_preregistration(self):
        baseline = deepcopy(self.data['baseline'])
        baseline['protocol_status'] = 'registered'
        with self.assertRaises(Denied):
            self.steward.initialise(baseline)


if __name__ == '__main__':
    unittest.main()
