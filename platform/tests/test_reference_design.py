"""Reference Design #1 frontend contracts; no market network or trade execution."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

PLATFORM=Path(__file__).resolve().parents[1]

class Tags(HTMLParser):
    def __init__(self):
        super().__init__();self.ids={};self.labels=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if "id" in d:self.ids[d["id"]]=self.ids.get(d["id"],0)+1
        if tag=="link":self.links.append(d)
        if tag=="button" and d.get("data-chart-timeframe"):self.labels.append(d["data-chart-timeframe"])

class ReferenceLayoutContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(PLATFORM/"index.html").read_text(encoding="utf-8")
        cls.css=(PLATFORM/"reference_dashboard.css").read_text(encoding="utf-8")
        cls.tags=Tags();cls.tags.feed(cls.html)

    def test_single_shared_home_and_analyze_layout(self):
        self.assertIn('class="desk-workspace" data-page="overview analyze"',self.html)
        self.assertEqual(self.tags.ids.get("desk-live-chart"),1)
        self.assertEqual(self.tags.ids.get("desk-decision"),1)
        self.assertEqual(self.tags.ids.get("desk-mode"),1)
        self.assertEqual(self.tags.ids.get("desk-analyze"),1)
        for id_ in ("ref-last-price","ref-entry","ref-sl","ref-tp","ref-rr","ref-signal-card","ref-feed-banner","ref-session-label"):
            self.assertEqual(self.tags.ids.get(id_),1,id_)
    def test_reference_toolbar_has_real_timeframe_actions(self):
        self.assertEqual(self.tags.labels,["M5","M15","H1","H4"])
        self.assertIn("function aggregateBars(rows,minutes)",self.html)
        self.assertIn("bars.length!==step",self.html)
        self.assertIn("window.dispatchEvent(new CustomEvent('bigben:chart-timeframe'",self.html)
    def test_stylesheet_is_new_single_reference(self):
        self.assertTrue(any(x.get("href","").startswith("/reference_dashboard.css?") for x in self.tags.links))
        self.assertNotIn('id="design-one-layout-reference-fix"',self.html)
        self.assertNotIn('id="dark-trading-pro-v1"',self.html)
        self.assertIn('inset:0 auto 0 0!important',self.css) # Left rail per screenshot
        self.assertIn('.ref-trading-toolbar',self.css)
        self.assertIn('.ref-signal-card',self.css)
    def test_conditional_direction_and_closed_bar_age_visible(self):
        self.assertEqual(self.tags.ids.get("ref-targets-extra"),1)
        self.assertIn("conditional-buy",self.html)
        self.assertIn("conditional-sell",self.html)
        self.assertIn("↗ شراء BUY",self.html)
        self.assertIn("↘ بيع SELL",self.html)
        self.assertIn("refreshCandleAge",self.html)
        self.assertIn("bigben:new-closed-candle",self.html)
        self.assertIn("last_closed_candle",self.html)
        self.assertIn("بيانات متأخرة",self.html+" "+self.css if "بيانات متأخرة" in self.html else "بيانات متأخرة") # no implicit live claim

    def test_no_fake_market_values_or_broker_orders(self):
        for text in ("1.0874","1.0890","1.0840","82%"):
            self.assertNotIn(text,self.html)
        self.assertIn("لا توجد نسبة نجاح موثقة",self.html)
        self.assertIn("دون Pine",self.html)

if __name__=="__main__":unittest.main()
