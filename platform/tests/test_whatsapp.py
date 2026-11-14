"""Synthetic Meta API contract and privacy regressions; no external messages."""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

spec=importlib.util.spec_from_file_location("test_whatsapp_adapter",Path(__file__).resolve().parents[1]/"backend"/"whatsapp.py")
wa=importlib.util.module_from_spec(spec);spec.loader.exec_module(wa)


class WhatsAppTests(unittest.TestCase):
    def setUp(self):
        wa.LAST_CHECK=None
        self.env=patch.dict(os.environ,{'BIGBEN_WHATSAPP_ENABLED':'1','WHATSAPP_ACCESS_TOKEN':'synthetic-secret',
            'WHATSAPP_PHONE_NUMBER_ID':'123456789','WHATSAPP_API_VERSION':'v27.0',
            'WHATSAPP_TEMPLATE_NAME':'bigben_trade_v1','WHATSAPP_TEMPLATE_LANGUAGE':'ar'})
        self.env.start()

    def tearDown(self):self.env.stop()

    def test_disabled_or_missing_settings_never_send(self):
        with patch.dict(os.environ,{'BIGBEN_WHATSAPP_ENABLED':'0'}),patch.object(wa.urllib.request,'urlopen') as fetch:
            self.assertEqual(wa.send_template('+96891234567',['fixture']*9),'disabled');fetch.assert_not_called()
        with patch.dict(os.environ,{'WHATSAPP_ACCESS_TOKEN':''}),patch.object(wa.urllib.request,'urlopen') as fetch:
            self.assertEqual(wa.send_template('+96891234567',['fixture']*9),'not_configured');fetch.assert_not_called()

    def test_template_parameters_and_destination_must_be_valid(self):
        for recipient,params in [('91234567',['fixture']*9),('+96891234567',['fixture']*8),('+96891234567',['x'*513]*9)]:
            with patch.object(wa.urllib.request,'urlopen') as fetch:
                self.assertNotEqual(wa.send_template(recipient,params),'accepted');fetch.assert_not_called()

    def test_acceptance_is_recorded_without_claiming_delivery(self):
        response=MagicMock();response.__enter__.return_value.status=200
        response.__enter__.return_value.read.return_value=b'{"messages":[{"id":"synthetic-message-id"}]}'
        with patch.object(wa.urllib.request,'urlopen',return_value=response) as fetch:
            result=wa.send_template('+96891234567',[str(n) for n in range(1,10)])
        self.assertEqual(result,'accepted');self.assertFalse(wa.status()['delivery_verified'])
        self.assertTrue(wa.status()['provider_connection_verified'])
        request=fetch.call_args.args[0];body=json.loads(request.data)
        self.assertEqual(body['type'],'template');self.assertEqual(body['to'],'96891234567')
        self.assertEqual(len(body['template']['components'][0]['parameters']),9)
        self.assertEqual(fetch.call_args.kwargs['timeout'],8)
        self.assertNotIn('synthetic-secret',json.dumps(wa.status()))
        self.assertNotIn('synthetic-message-id',json.dumps(wa.status()))

    def test_http_failures_are_sanitized_and_not_retried(self):
        error=urllib.error.HTTPError('https://example.invalid',429,'synthetic-secret',{},io.BytesIO(b'synthetic-secret'))
        with patch.object(wa.urllib.request,'urlopen',side_effect=error) as fetch:
            self.assertEqual(wa.send_template('+96891234567',['fixture']*9),'provider_http_429')
        self.assertEqual(fetch.call_count,1);self.assertFalse(wa.status()['provider_connection_verified'])
        self.assertNotIn('synthetic-secret',json.dumps(wa.status()))

    def test_empty_or_malformed_response_never_connects(self):
        for raw in (b'{}',b'{"messages":[]}',b'not json',b'{"messages":[{"id":true}]}'):
            response=MagicMock();response.__enter__.return_value.status=200;response.__enter__.return_value.read.return_value=raw
            with patch.object(wa.urllib.request,'urlopen',return_value=response):
                self.assertEqual(wa.send_template('+96891234567',['fixture']*9),'provider_unavailable')
            self.assertFalse(wa.status()['provider_connection_verified'])
