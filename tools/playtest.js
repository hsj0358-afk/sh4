// 자동 플레이테스트.
// 무작위 플레이어를 여러 번 굴려 (1) 크래시 (2) 막다른 길 (3) 난이도 균형을 본다.
//   npm run playtest -- --runs 500

import { createState } from '../src/engine/state.js';
import { createGM } from '../src/engine/gm.js';
import { EPISODES, FIRST_EPISODE, getEpisode } from '../src/content/episodes/index.js';
import { advanceEpisode, hasNextEpisode } from '../src/engine/campaign.js';
import { PROFESSIONS } from '../src/content/professions.js';
import { createRng } from '../src/engine/rng.js';
import { CLUES } from '../src/content/clues.js';
import { ITEMS } from '../src/content/items.js';

const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? Number(process.argv[i + 1]) : def;
};

const RUNS = arg('runs', 300);
const MAX_STEPS = arg('steps', 260);

const diffIndex = process.argv.indexOf('--difficulty');
const DIFFICULTY = diffIndex >= 0 ? process.argv[diffIndex + 1] : 'standard';

// --cautious: 몸과 정신이 상하면 먼저 회복하고, 위험도가 높으면 서두르는 플레이어.
// 아무 선택지나 누르는 봇과 달리, 실제 플레이어가 하는 최소한의 판단을 흉내낸다.
const CAUTIOUS = process.argv.includes('--cautious');

const RESTFUL = /쉰다|숨을 고른|밤을|야영|기록을 남|셈을 치른|보급|장비를 산/;

const retreated = new Set();

function chooseCautious(state, options, rng) {
  const hurt = state.hp / state.maxHp < 0.5 || state.san / state.maxSan < 0.5;
  if (hurt) {
    const heal = options.find((c) => RESTFUL.test(c.label));
    if (heal) return heal;
  }
  // 심하게 상했으면 깊이 들어가는 선택을 피한다.
  // 다만 같은 장면에서 두 번 물러서지는 않는다 — 그건 후퇴가 아니라 제자리걸음이다.
  if (state.hp / state.maxHp < 0.3 || state.san / state.maxSan < 0.3) {
    const retreat = options.find((c) => /돌아|물러|나간다|마친다|출발|떠난다/.test(c.label));
    if (retreat && !retreated.has(state.scene)) {
      retreated.add(state.scene);
      return retreat;
    }
  }
  return rng.pick(options);
}

const tally = {
  outcomes: {},
  endings: {},
  professions: {},
  stuck: 0,
  timedOut: 0,
  reachedEpilogue: 0,
  clueCounts: [],
  chapters: [],
  steps: [],
};

for (let run = 0; run < RUNS; run++) {
  const rng = createRng(run * 7919 + 13);
  retreated.clear();
  const prof = PROFESSIONS[run % PROFESSIONS.length];
  const state = createState({ professionId: prof.id, difficulty: DIFFICULTY, seed: run });
  let episode = getEpisode(FIRST_EPISODE);
  let gm = createGM({ state, episode });
  gm.start();

  let steps = 0;
  while (steps < MAX_STEPS) {
    // 장이 끝났고 다음 장이 있으면 이어서 간다.
    if (state.ended) {
      if (state.ended.type !== 'chapter' || !hasNextEpisode(state)) break;
      const moved = advanceEpisode(state);
      episode = moved.episode;
      gm = createGM({ state, episode });
      gm.start();
      continue;
    }
    steps++;
    if (gm.pending) {
      for (const ev of gm.roll()) {
        if (ev.type === 'roll') {
          tally.outcomes[ev.result.outcome] = (tally.outcomes[ev.result.outcome] || 0) + 1;
        }
      }
      continue;
    }
    // 신중한 플레이어는 다치면 약을 쓴다. 소지품 사용은 자유 입력으로 간다.
    if (CAUTIOUS && state.hp / state.maxHp < 0.45) {
      const kit = state.inventory.find((i) => ITEMS[i.name]?.use);
      if (kit) {
        gm.freeAct(`${kit.name} 사용`);
        continue;
      }
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
    gm.act((CAUTIOUS ? chooseCautious(state, options, rng) : rng.pick(options)).id);
  }

  if (steps >= MAX_STEPS && !state.ended) {
    tally.timedOut++;
    console.error(`[상한 도달] run=${run} scene=${state.scene} steps=${steps}`);
  }

  const kind = state.ended?.type || 'unfinished';
  tally.endings[kind] = (tally.endings[kind] || 0) + 1;
  tally.professions[prof.name] = tally.professions[prof.name] || { runs: 0, died: 0 };
  tally.professions[prof.name].runs++;
  if (kind === 'death' || kind === 'broken') tally.professions[prof.name].died++;
  if (state.ended?.type === 'chapter') tally.reachedEpilogue++;
  tally.chapters.push((state.visitedEpisodes?.length || 0) + 1);
  tally.clueCounts.push(state.clues.length);
  tally.steps.push(steps);
}

const avg = (a) => (a.reduce((x, y) => x + y, 0) / a.length).toFixed(1);
const totalRolls = Object.values(tally.outcomes).reduce((a, b) => a + b, 0);
const TOTAL_CLUES = Object.keys(CLUES).length;

console.log(
  `\n《잃어버린 세계의 지도》 자동 플레이테스트 — ${RUNS}회 · 난이도 ${DIFFICULTY}` +
    ` · ${CAUTIOUS ? '신중한' : '무작위'} 플레이어\n`,
);

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

console.log(`\n장 완주          ${((tally.reachedEpilogue / RUNS) * 100).toFixed(1)}%`);
console.log(`평균 도달 장      ${avg(tally.chapters)} / ${Object.keys(EPISODES).length}`);
console.log(`평균 단서 수      ${avg(tally.clueCounts)} / ${TOTAL_CLUES}`);
console.log(`평균 행동 수      ${avg(tally.steps)}`);
console.log(`막힌 세션         ${tally.stuck}`);
console.log(`상한 도달         ${tally.timedOut}  (봇이 제자리를 돈 횟수 — 게임의 결함은 아니다)`);

if (tally.stuck > 0) {
  console.error('\n선택지도 자유 입력도 통하지 않는 세션이 있습니다.');
  process.exit(1);
}
