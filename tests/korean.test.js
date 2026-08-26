// 조사 붙이기.
//
// 동료 이름을 엔진이 만든 문장에 끼워 넣으면 "하룬가 떠났다" 같은 것이 나온다.
// 받침이 있는지 없는지로 조사가 갈린다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { hasBatchim, subj, topic, obj, and, to } from '../src/korean.js';
import { COMPANIONS } from '../src/content/companions.js';

test('받침을 읽는다', () => {
  assert.equal(hasBatchim('나디아 하룬'), true);
  assert.equal(hasBatchim('올리버 핀치'), false);
  assert.equal(hasBatchim('속하'), false);
  assert.equal(hasBatchim('바심 알마단'), true);
  assert.equal(hasBatchim('아셔 크레인'), true);
  assert.equal(hasBatchim('세라피나 볼트'), false);
});

test('한글이 아니면 받침이 없는 것으로 본다', () => {
  assert.equal(hasBatchim('Crane'), false);
  assert.equal(hasBatchim(''), false);
  assert.equal(hasBatchim(undefined), false);
});

test('조사가 이름을 따라간다', () => {
  assert.equal(subj('나디아 하룬'), '나디아 하룬이');
  assert.equal(subj('올리버 핀치'), '올리버 핀치가');
  assert.equal(topic('나디아 하룬'), '나디아 하룬은');
  assert.equal(topic('속하'), '속하는');
  assert.equal(obj('아셔 크레인'), '아셔 크레인을');
  assert.equal(obj('세라피나 볼트'), '세라피나 볼트를');
  assert.equal(and('바심 알마단'), '바심 알마단과');
  assert.equal(and('속하'), '속하와');
  assert.equal(to('횃불'), '횃불로');
  assert.equal(to('탁본'), '탁본으로');
});

test('앞뒤 공백은 무시한다', () => {
  assert.equal(hasBatchim(' 하룬 '), true);
});

test('모든 동료 이름에 조사가 제대로 붙는다', () => {
  const expected = {
    nadia: '이',
    finch: '가',
    seraphina: '가',
    basim: '이',
    sokha: '가',
    crane: '이',
  };
  for (const [id, tail] of Object.entries(expected)) {
    assert.equal(subj(COMPANIONS[id].name).slice(-1), tail, `${COMPANIONS[id].name} 조사가 틀렸다`);
  }
});
