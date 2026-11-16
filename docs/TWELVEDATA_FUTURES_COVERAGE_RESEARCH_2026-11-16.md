# Twelve Data coverage research — 2026-11-16

- The official Twelve Data documentation describes its market-data REST/WebSocket coverage as equities, forex, crypto and ETFs across exchanges; it also provides reference catalogs and commodities endpoints. It does not establish that CME/CBOT/NYMEX futures roots used by this project are available under the current account.
  Source: https://twelvedata.com/docs
- Twelve Data's official symbol-discovery article documents `/forex_pairs`, `/stocks`, `/cryptocurrencies`, `/etf`, and `/commodities`. The commodities catalog includes spot-style instruments such as gold, copper and crude oil examples, which must not be mislabeled as exchange-traded futures contracts.
  Source: https://support.twelvedata.com/en/articles/5620513-how-to-find-all-available-symbols-at-twelve-data
- Twelve Data's commodities page claims real-time and historical commodity prices, but this does not prove CME/CBOT/NYMEX futures-contract entitlement for ES, NQ, CL, GC, or their micro contracts.
  Source: https://twelvedata.com/commodities

Project decision: keep TradingView futures symbols available for authenticated live webhook events, expand the catalog conservatively, and leave Twelve Data futures coverage unverified until a real supported symbol and entitlement are tested. Never substitute CFDs or spot commodities for futures.
