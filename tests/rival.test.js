// 경쟁자 시계 — 시간에 값을 붙이는 규칙 (engine/rival.js).
//
// 여기서 확인하는 것은 「크레인이 몇 점인가」가 아니라 세 가지다.
//   1. 시간을 쓰면 그가 앞선다 — 위험도와 달리 식지 않는다
//   2. 같은 편이 되면 경주가 끝난다 — 협상 노선의 값
//   3. 앞선 채로 장을 마치면 잃는다 — 그리고 그 전에 예고된다

import test from 'node:test';
import assert from 'node:assert/strict';
import { createState, applyEffects } from '../src/engine/state.js';
import {
  RIVAL_MAX,
  RIVAL_TOLL,
  racing,
  tickRival,
  rivalStart,
  rivalLabel,
  rivalStage,
  rivalCrossing,
  rivalToll,
} from '../src/engine/rival.js';
import { advanceEpisode } from '../src/engine/campaign.js';
import { getInterlude } from '../src/content/interludes.js';

function run(opts = {}) {
  const s = createState({ professionId: 'archaeologist', seed: 11 });
  s.episode = 'luxor';
  Object.assign(s, opts);
  return s;
}

test('새 판은 0 에서 시작한다', () => {
  assert.equal(run().rival, 0);
});

test('시간을 쓰면 그가 앞선다', () => {
  const s = run();
  applyEffects(s, { time: 20 });
  assert.ok(s.rival > 0, '시간이 흘렀는데 경쟁자가 그대로다');
  const after20 = s.rival;
  applyEffects(s, { time: 20 });
  assert.ok(s.rival > after20, '같은 시간을 또 썼는데 안 늘었다');
});

test('위험도와 달리 식지 않는다', () => {
  // 위험도는 조용한 시간이 흐르면 내려간다. 이것은 내려가면 안 된다 —
  // 내려가면 「기다렸다가 다시 누르기」가 다시 최적이 된다.
  const s = run();
  applyEffects(s, { time: 40 });
  const peak = s.rival;
  applyEffects(s, { time: 40 });
  assert.ok(s.rival >= peak, '시간이 더 흘렀는데 경쟁자가 뒤로 갔다');
});

test('상한을 넘지 않는다', () => {
  const s = run();
  applyEffects(s, { time: 100000 });
  assert.equal(s.rival, RIVAL_MAX);
});

test('같은 편이 되면 경주가 끝난다', () => {
  const s = run({ flags: { craneAlly: true } });
  assert.equal(racing(s), false);
  applyEffects(s, { time: 200 });
  assert.equal(s.rival, 0, '동맹인데도 경주가 돌아간다');
  assert.equal(rivalToll(s), null);
  assert.equal(rivalCrossing(s), null);
});

test('느린 배를 타면 뒤에서 시작한다', () => {
  const inter = getInterlude('mesopotamia');
  const s = run();
  const byId = Object.fromEntries(inter.routes.map((r) => [r.id, r]));
  const fast = rivalStart(inter, byId.fast, s);
  const steady = rivalStart(inter, byId.steady, s);
  const london = rivalStart(inter, byId.london, s);
  assert.equal(fast, 0, '가장 빠른 배는 0 에서 시작해야 한다');
  assert.ok(steady > fast, '5주가 3주보다 앞서 있다');
  assert.ok(london > steady, '8주가 5주보다 앞서 있다');
});

test('문턱을 넘을 때 한 번만 알려 준다', () => {
  // 배신과 같은 원칙 — 예고된다. 다만 매 턴 같은 말을 반복하지는 않는다.
  const s = run({ rival: 50 });
  assert.ok(rivalCrossing(s), '경고 문턱을 넘었는데 아무 말이 없다');
  assert.equal(rivalCrossing(s), null, '같은 경고를 두 번 했다');

  s.rival = RIVAL_TOLL + 5;
  assert.ok(rivalCrossing(s), '다음 문턱은 따로 알려야 한다');
  assert.equal(rivalCrossing(s), null);
});

test('여유가 있으면 아무 말도 하지 않는다', () => {
  assert.equal(rivalCrossing(run({ rival: 10 })), null);
});

test('앞선 채로 장을 마치면 유물을 먼저 가져간다', () => {
  const s = run({ rival: RIVAL_TOLL });
  s.inventory.push({ name: '별자리 기호판', uses: null });
  const toll = rivalToll(s);
  assert.ok(toll, '문턱을 넘었는데 정산이 없다');
  assert.deepEqual(toll.effects.removeItems, ['별자리 기호판']);
  assert.equal(toll.effects.flags.craneAhead, true);
});

test('가져갈 유물이 없으면 잃지 않는다', () => {
  // 값을 치를 것이 없는 사람에게 없는 것을 빼앗을 수는 없다.
  const s = run({ rival: RIVAL_MAX });
  const toll = rivalToll(s);
  assert.ok(toll);
  assert.equal(toll.effects.removeItems, undefined);
});

test('문턱 아래면 정산하지 않는다', () => {
  const s = run({ rival: RIVAL_TOLL - 1 });
  s.inventory.push({ name: '별자리 기호판', uses: null });
  assert.equal(rivalToll(s), null);
});

test('일반 장비는 노리지 않는다 — 유적에서 나온 것만', () => {
  const s = run({ rival: RIVAL_MAX });
  s.inventory = [{ name: '횃불', uses: 6 }, { name: '나침반', uses: null }];
  const toll = rivalToll(s);
  assert.equal(toll.effects.removeItems, undefined);
});

test('장이 바뀌면 경주가 다시 시작한다', () => {
  // 같은 문을 향해 두 배가 다시 떠나는 것이므로.
  const s = run({ rival: 60 });
  s.flags['rivalWarned:near'] = true;
  const moved = advanceEpisode(s, { routeId: 'fast' });
  assert.equal(moved.ok, true);
  assert.equal(s.rival, 0, '가장 빠른 배를 탔는데 앞의 장 점수가 남아 있다');
  assert.equal(s.flags['rivalWarned:near'], undefined, '경고 기록이 안 지워졌다');
});

test('여정의 몇 주가 시계를 꽉 채우지 않는다', () => {
  // 항로 효과의 time 은 1000틱이 넘는다. 그대로 흘려보내면 첫 장면 전에 끝난다.
  const s = run();
  const moved = advanceEpisode(s, { routeId: 'london' });
  assert.ok(moved.ok);
  assert.ok(s.rival < RIVAL_MAX, `여정만으로 시계가 꽉 찼다 (${s.rival})`);
  assert.ok(s.rival > 0, '가장 느린 배인데 앞서 있지 않다');
});

test('장을 넘을 때 정산이 결과에 실려 온다', () => {
  const s = run({ rival: RIVAL_MAX });
  s.inventory.push({ name: '별자리 기호판', uses: null });
  const moved = advanceEpisode(s, { routeId: 'fast' });
  assert.ok(moved.toll, '정산이 호출자에게 전달되지 않았다');
  assert.ok(!s.inventory.some((i) => i.name === '별자리 기호판'), '정산했는데 유물이 남아 있다');
});

test('표시 문구와 단계가 어긋나지 않는다', () => {
  assert.equal(rivalStage(0), 'calm');
  assert.equal(rivalStage(RIVAL_TOLL), 'lost');
  assert.notEqual(rivalLabel(0), rivalLabel(RIVAL_MAX));
  for (const v of [0, 30, 60, 90, 100]) assert.ok(rivalLabel(v).length > 0);
});
