// 조사 붙이기.
//
// 동료 이름을 엔진이 만든 문장에 끼워 넣으면 "하룬가 떠났다" 같은 것이 나온다.
// 받침이 있는지 없는지로 조사가 갈린다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { hasBatchim, subj, topic, obj, and, to, fill } from '../src/korean.js';
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

// ── 자리표 채우기 ──────────────────────────────────────────────

test('자리표에 값을 넣는다', () => {
  assert.equal(fill('{이름}이 도착했다.', { 이름: '몰리' }), '몰리이 도착했다.');
  assert.equal(fill('안녕하세요, {이름} 선생.', { 이름: '에드워드 몰리' }), '안녕하세요, 에드워드 몰리 선생.');
});

test('자리표 안의 조사는 받침을 따라간다', () => {
  assert.equal(fill('{이름은} 부두에 내려선다.', { 이름: '몰리' }), '몰리는 부두에 내려선다.');
  assert.equal(fill('{이름은} 부두에 내려선다.', { 이름: '하룬' }), '하룬은 부두에 내려선다.');
  assert.equal(fill('{이름이} 말한다.', { 이름: '핀치' }), '핀치가 말한다.');
  assert.equal(fill('{이름을} 부른다.', { 이름: '볼트' }), '볼트를 부른다.');
  assert.equal(fill('{이름으로} 적는다.', { 이름: '횃불' }), '횃불로 적는다.');
});

test('모르는 자리표는 그대로 둔다', () => {
  // 조용히 지우면 문장에 빈 자리만 남는다. 눈에 보이는 편이 낫다.
  assert.equal(fill('{직업은} 무엇인가.', { 이름: '몰리' }), '{직업은} 무엇인가.');
});

test('자리표가 없으면 문장을 건드리지 않는다', () => {
  const line = '증기선이 진흙 부두에 닿는다.';
  assert.equal(fill(line, { 이름: '몰리' }), line);
});

test('값이 여러 번 나와도 전부 채운다', () => {
  assert.equal(fill('{이름}, {이름은} 듣고 있나.', { 이름: '속하' }), '속하, 속하는 듣고 있나.');
});
