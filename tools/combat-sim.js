// 전투 균형 시뮬레이터.
//
// 조우 하나를 여러 '정책'으로 400번씩 굴려, 어떤 전략이 어떤 결말로 이어지는지 본다.
// 새 조우를 쓸 때 수치를 정하는 도구다. 보고 싶은 그림은 이렇다.
//
//   - 공격만 해서는 이기지 못한다 (그러면 엄폐가 의미를 잃는다)
//   - 지형과 협상은 각각 절반쯤 통한다 (둘 다 살아 있는 길이어야 한다)
//   - 도주는 빠르고 확실하다 (대신 아무것도 못 얻는다)
//
//   npm run combat-sim

import { startCombat, applyAction, enemyTurn, checkExit, parleyReady } from '../src/engine/combat.js';
import { ENCOUNTERS } from '../src/content/encounters.js';
import { createRng } from '../src/engine/rng.js';
import { resolve as resolveRoll } from '../src/engine/dice.js';

const RUNS = 400;
const MODIFIER = 4; // 평범한 탐사자의 보정치

const POLICIES = {
  '공격 일변도': () => 'attack',
  '공격+엄폐': (c) => (c.pressure >= c.maxPressure - 4 ? 'cover' : 'attack'),
  '지형 우선': (c) =>
    !c.used.terrain && c.round >= 2
      ? 'terrain'
      : c.pressure >= c.maxPressure - 4
        ? 'cover'
        : 'attack',
  '협상 노림': (c) =>
    parleyReady(c) ? 'parley' : c.pressure >= c.maxPressure - 4 ? 'cover' : 'attack',
  '즉시 도주': (c) => (c.pressure >= c.maxPressure - 3 ? 'cover' : 'flee'),
};

function targetFor(enc, key) {
  if (key === 'attack') return enc.defense;
  if (key === 'parley') return enc.parleyTarget;
  if (key === 'flee') return enc.fleeTarget;
  if (key === 'terrain') return enc.terrain.target;
  return 12;
}

for (const [encId, enc] of Object.entries(ENCOUNTERS)) {
  console.log(
    `\n[${encId}] ${enc.name} — 전의 ${enc.resolve} · 압박한계 ${enc.maxPressure ?? 10} · 위협 ${enc.threat}`,
  );

  for (const [name, policy] of Object.entries(POLICIES)) {
    const tally = {};
    const rounds = [];

    for (let seed = 0; seed < RUNS; seed++) {
      const rng = createRng(seed * 31 + 7);
      const c = startCombat(enc);
      let guard = 0;

      while (!checkExit(c) && guard++ < 40) {
        const key = policy(c);
        const bonus = key === 'parley' && parleyReady(c) ? 3 : 0;
        const r = resolveRoll(rng.int(1, 20), MODIFIER + bonus, targetFor(enc, key));
        applyAction(c, enc, key, r.outcome);
        if (checkExit(c)) break;
        enemyTurn(c, enc);
      }

      const exit = checkExit(c) || 'unfinished';
      tally[exit] = (tally[exit] || 0) + 1;
      rounds.push(c.round);
    }

    const pct = (k) => (((tally[k] || 0) / RUNS) * 100).toFixed(0).padStart(3);
    const avg = (rounds.reduce((a, b) => a + b, 0) / rounds.length).toFixed(1);
    console.log(
      `  ${name.padEnd(12)} 물러남 ${pct('win')}%  협상 ${pct('parley')}%` +
        `  도주 ${pct('escape')}%  제압 ${pct('overrun')}%   평균 ${avg}라운드`,
    );
  }
}

console.log('\n(보정 +4 기준. 실제 판정에는 능력치·장비·동료·상태가 더 붙는다.)');
