"""Bounded chronological RR research using the existing Pine-rules translation.

This module never changes Pine or makes a promotion decision. Out-of-sample
windows preserve continuous replay state from past bars, including positions
opened before a scored window; those positions are excluded from its metrics.
"""
import hashlib
import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path

spec=importlib.util.spec_from_file_location('walk_forward_replay',Path(__file__).with_name('pine_replay.py'))
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)


def wilson(wins,total):
    if not total:return None
    z=1.959963984540054;p=wins/total;den=1+z*z/total
    mid=(p+z*z/(2*total))/den
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [max(0,mid-half),min(1,mid+half)]


def summary(trades):
    result=engine.metrics(trades)
    result['resolved_win_rate_wilson95']=wilson(result['wins'],result['resolved'])
    result['uncertainty_scope']='resolved trades only; excludes ambiguous/unresolved; independence not verified'
    return result


def run(candles,tick_size,source,now=None,config=None,costs=None,min_train=480,test_bars=120,max_folds=4):
    now=now or datetime.now(timezone.utc)
    cfg=engine.configuration(config)
    if cfg['enable_smt']:raise ValueError('synchronized_peer_history_required')
    if any(type(v) is not int for v in (min_train,test_bars,max_folds)) or min_train<120 or test_bars<60 or not 1<=max_folds<=4:
        raise ValueError('walk_forward_budget')
    if not isinstance(source,dict) or not isinstance(source.get('source_sha256'),str) or len(source['source_sha256'])!=64:
        raise ValueError('source_hash_required')
    if not min_train+test_bars+60<=len(candles)<=10000:raise ValueError('insufficient_history_or_budget')
    # Validate the complete dataset before planning. No future/open/duplicate bars.
    rows,quality=engine._quality.validate_candles(candles,now)
    holdout_start=int(len(rows)*.8)
    starts=list(range(min_train,holdout_start-test_bars+1,test_bars))[-max_folds:]
    if not starts:raise ValueError('insufficient_pre_holdout_windows')
    candidates=sorted(set([1.5,2.0,2.5,3.0,cfg['rr']]))
    if len(candidates)>4:raise ValueError('baseline_rr_outside_research_budget')
    folds=[];combined=[];last_rr=cfg['rr']

    def replay(end,rr):
        return engine.replay(rows[:end],tick_size,{**cfg,'rr':rr},costs=costs,now=now)

    for start in starts:
        end=start+test_bars;training=[]
        for rr in candidates:
            result=replay(start,rr)
            metric=summary(result['trades'])
            score=(metric['net_r']/metric['resolved'] if metric['net_r'] is not None and metric['resolved'] else metric['expectancy_r'])
            training.append({'rr':rr,'metrics':metric,'score':score,
                             'eligible':metric['resolved']>=30 and score is not None})
        eligible=[x for x in training if x['eligible']]
        # Training only; neither this fold's test nor the final holdout selects RR.
        selected=max(eligible,key=lambda x:(x['score'],-abs(x['rr']-cfg['rr'])))['rr'] if eligible else cfg['rr']
        tested=replay(end,selected)
        trades=[t for t in tested['trades'] if start<=t['entry_index']<end]
        baseline=replay(end,cfg['rr']) if selected!=cfg['rr'] else tested
        base_trades=[t for t in baseline['trades'] if start<=t['entry_index']<end]
        folds.append({'train_range':[0,start],'test_range':[start,end],
                      'training_last_open':rows[start-1]['time'],'test_first_open':rows[start]['time'],
                      'training_candidates':training,'selected_rr':selected,
                      'selection':'training_only' if eligible else 'baseline_retained_insufficient_training_trades',
                      'test_metrics':summary(trades),'baseline_test_metrics':summary(base_trades),
                      'test_trades':trades})
        combined.extend(trades);last_rr=selected
    # Freeze the candidate before viewing the final20%.
    candidate=replay(len(rows),last_rr)
    baseline=replay(len(rows),cfg['rr']) if last_rr!=cfg['rr'] else candidate
    held=[t for t in candidate['trades'] if t['entry_index']>=holdout_start]
    base_held=[t for t in baseline['trades'] if t['entry_index']>=holdout_start]
    insufficient=any(f['selection']!='training_only' for f in folds) or summary(held)['resolved']<30
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
    return {'kind':'chronological_walk_forward_research','created_at':now.isoformat(),
            'status':'INSUFFICIENT_EVIDENCE' if insufficient else 'RESEARCH_ONLY',
            'pine_source_sha256':source['source_sha256'],'engine_sha256':engine.ENGINE_SHA256,
            'dataset_sha256':digest,'candles':len(rows),'start':rows[0]['time'],'end':rows[-1]['time'],
            'baseline_parameters':cfg,'tick_size':tick_size,'cost_assumptions':engine.cost_model(costs),
            'quality':quality,'folds':folds,'out_of_sample_metrics':summary(combined),
            'holdout':{'range':[holdout_start,len(rows)],'selection_uses_holdout':False,
                       'frozen_rr':last_rr,'candidate_metrics':summary(held),
                       'baseline_metrics':summary(base_held),'trades':held},
            'promotion_allowed':False,'pine_parity_verified':False,'automatic_updates':False,
            'limitations':['Historical research snapshot, not live execution or ongoing scheduled validation',
                'RR candidates only; original production strategy is unchanged',
                'Continuous candidate replay retains pre-window position/cooldown state; only new entries are scored',
                'At least30 resolved training trades are required to select a candidate; otherwise retain baseline',
                'No verified spread/slippage/commission feed when costs are null; gross results are not net returns',
                'Same-feed Pine parity, exchange session boundaries, contract rolls and reference video remain unverified',
                'Small correlated samples and repeated RR comparisons do not establish profitability']}
