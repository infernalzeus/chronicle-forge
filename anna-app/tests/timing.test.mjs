import test from 'node:test';
import assert from 'node:assert/strict';
import {timingHistory,formatTime,quotaFailure} from '../bundle/timing.mjs';
test('timing history has no invented estimate before a completion',()=>assert.equal(timingHistory().average('image','test','low'),null));
test('averages are separated by model and quality',()=>{const h=timingHistory();h.record('image','test','low',1000);h.record('image','test','low',3000);assert.deepEqual(h.average('image','test','low'),{ms:2000,count:2});assert.equal(h.average('image','test','high'),null);});
test('only twenty recent completion timings are retained',()=>{const h=timingHistory();for(let i=1;i<=30;i++)h.record('image','test','low',i*1000);assert.deepEqual(h.average('image','test','low'),{ms:20500,count:20});});
test('storage denial cannot break generation timing',()=>{const storage={getItem(){throw Error('denied');},setItem(){throw Error('denied');}};const h=timingHistory(storage);assert.doesNotThrow(()=>h.record('voice','test','default',2500));assert.equal(h.average('voice','test','default').count,1);});
test('quota errors are distinguished from permission failures',()=>{assert.ok(quotaFailure({code:'APP_QUOTA_EXCEEDED'}));assert.ok(quotaFailure({message:'Insufficient credits'}));assert.equal(quotaFailure({code:'APP_NOT_GRANTED'}),false);});
test('elapsed time remains readable beyond a minute',()=>assert.equal(formatTime(92000),'1m 32s'));
