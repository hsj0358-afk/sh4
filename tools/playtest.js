// 자동 플레이테스트.
// 무작위 플레이어를 여러 번 굴려 (1) 크래시 (2) 막다른 길 (3) 난이도 균형을 본다.
//   npm run playtest -- --runs 500

import { createState } from '../src/engine/state.js';
import { createGM } from '../src/engine/gm.js';
import episode from '../src/content/episodes/luxor.js';
import { PROFESSIONS } from '../src/content/professions.js';
import { createRng } from '../src/engine/rng.js';

const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? Number(process.argv[i + 1]) : def;
};

const RUNS = arg('runs', 300);
const MAX_STEPS = arg('steps', 120);

const tally = {
  outcomes: {},
  endings: {},
  professions: {},
  stuck: 0,
  reachedEpilogue: 0,
  clueCounts: [],
  steps: [],
};

for (let run = 0; run < RUNS; run++) {
  const rng = createRng(run * 7919 + 13);
  const prof = PROFESSIONS[run % PROFESSIONS.length];
  const state = createState({ professionId: prof.id, seed: run });
  const gm = createGM({ state, episode });
  gm.start();

  let steps = 0;
  while (!state.ended && steps < MAX_STEPS) {
    steps++;
    if (gm.pending) {
      for (const ev of gm.roll()) {
        if (ev.type === 'roll') {
          tally.outcomes[ev.result.outcome] = (tally.outcomes[ev.result.outcome] || 0) + 1;
        }
      }
      continue;
    }
    const options = gm.choices().filter((c) => !c.locked);
    if (!options.length) {
      // 선택지가 없으면 자유 입력으로 빠져나갈 수 있어야 한다.
      const events = gm.freeAct('주변을 살펴본다');
      if (!events.length) {
        tally.stuck++;
        console.error(`[막힘] run=${run} scene=${state.scene}`);
        break;
      }
      continue;
    }
    gm.act(rng.pick(options).id);
  }

  if (steps >= MAX_STEPS && !state.ended) {
    tally.stuck++;
    console.error(`[미종료] run=${run} scene=${state.scene} steps=${steps}`);
  }

  const kind = state.ended?.type || 'unfinished';
  tally.endings[kind] = (tally.endings[kind] || 0) + 1;
  tally.professions[prof.name] = tally.professions[prof.name] || { runs: 0, died: 0 };
  tally.professions[prof.name].runs++;
  if (kind === 'death' || kind === 'broken') tally.professions[prof.name].died++;
  if (state.scene === 'epilogue') tally.reachedEpilogue++;
  tally.clueCounts.push(state.clues.length);
  tally.steps.push(steps);
}

const avg = (a) => (a.reduce((x, y) => x + y, 0) / a.length).toFixed(1);
const totalRolls = Object.values(tally.outcomes).reduce((a, b) => a + b, 0);

console.log(`\n《잃어버린 세계의 지도》 자동 플레이테스트 — ${RUNS}회\n`);

console.log('판정 결과 분포');
for (const key of ['fumble', 'fail', 'partial', 'success', 'crit']) {
  const n = tally.outcomes[key] || 0;
  const pct = ((n / totalRolls) * 100).toFixed(1);
  console.log(`  ${key.padEnd(8)} ${String(n).padStart(6)}  ${pct.padStart(5)}%  ${'▇'.repeat(Math.round(pct / 2))}`);
}

console.log('\n종료 유형');
for (const [k, v] of Object.entries(tally.endings)) {
  console.log(`  ${k.padEnd(12)} ${String(v).padStart(4)}  (${((v / RUNS) * 100).toFixed(1)}%)`);
}

console.log('\n직업별 사망/붕괴율');
for (const [name, s] of Object.entries(tally.professions)) {
  console.log(`  ${name.padEnd(10)} ${((s.died / s.runs) * 100).toFixed(0)}%`);
}

console.log(`\n에필로그 도달   ${((tally.reachedEpilogue / RUNS) * 100).toFixed(1)}%`);
console.log(`평균 단서 수    ${avg(tally.clueCounts)} / 9`);
console.log(`평균 행동 수    ${avg(tally.steps)}`);
console.log(`막힌 세션       ${tally.stuck}`);

if (tally.stuck > 0) {
  console.error('\n막다른 세션이 있습니다.');
  process.exit(1);
}
