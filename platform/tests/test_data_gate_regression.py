"""No trade from mismatched providers, local timestamps or a closed FX weekend."""
import importlib.util
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'backend'/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

market=load('connected_market')
sessions=load('market_sessions')

class DataGateRegressionTests(unittest.TestCase):
    def plan(self,now):
        return dict(symbol='OANDA:EURUSD',provider='Twelve Data',status='READY',
                    source_time=(now-timedelta(minutes=5)).isoformat())

    def test_new_york_weekend_in_winter_and_summer(self):
        for stamp in ('2026-11-20T22:00:00+00:00','2026-11-21T10:00:00+00:00',
                      '2026-11-22T21:59:00+00:00','2026-07-03T21:00:00+00:00',
                      '2026-07-05T20:59:00+00:00'):
            now=datetime.fromisoformat(stamp)
            with self.subTest(stamp=stamp):
                self.assertTrue(market.forex_weekly_closed(now))
                self.assertFalse(market.gate(self.plan(now),now)['open'])
        for stamp in ('2026-11-22T22:00:00+00:00','2026-07-05T21:00:00+00:00'):
            self.assertFalse(market.forex_weekly_closed(datetime.fromisoformat(stamp)))

    def test_wrong_provider_and_naive_time_are_blocked(self):
        now=datetime(2026,11,23,12,tzinfo=timezone.utc)
        self.assertFalse(market.gate(dict(self.plan(now),provider='Bitstamp'),now)['open'])
        self.assertFalse(market.gate(dict(self.plan(now),symbol='BITSTAMP:BTCUSD'),now)['open'])
        self.assertFalse(market.gate(dict(self.plan(now),source_time='2026-11-23T11:55:00'),now)['open'])

    def test_saturday_clock_never_claims_open(self):
        for hour in (0,12,23):
            now=datetime(2026,11,21,hour,tzinfo=timezone.utc)
            self.assertEqual(sessions.status(now)['state'],'CLOSED')

if __name__=='__main__':unittest.main()
