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
const MAX_STEPS = arg('steps', 400);

const diffIndex = process.argv.indexOf('--difficulty');
const DIFFICULTY = diffIndex >= 0 ? process.argv[diffIndex + 1] : 'standard';

// --cautious: 몸과 정신이 상하면 먼저 회복하고, 위험도가 높으면 서두르는 플레이어.
// 아무 선택지나 누르는 봇과 달리, 실제 플레이어가 하는 최소한의 판단을 흉내낸다.
const CAUTIOUS = process.argv.includes('--cautious');

// --golden: 미스터리를 쫓는 플레이어. 각 장의 본줄기 행동을 우선해서 고른다.
// 무작위 봇이 도달하지 못하는 결말(봉인·공개)이 실제로 열려 있는지 확인하는 용도다.
const GOLDEN = process.argv.includes('--golden');

// --trace: 첫 판을 한 수씩 따라가며 정신력이 어디서 깎이는지 찍는다.
const TRACE = process.argv.includes('--trace');

// 순서대로 우선순위. 위에 있을수록 먼저 고른다.
const GOLDEN_PATH = [
  // 1장 — 문을 열고 자물쇠의 절반을 얻는다
  'ask_nadia', 'inspect_dock', 'go_market', 'buy_supplies', 'hire_finch',
  'ask_crane', 'leave_market', 'go_valley',
  'dig_floor', 'survey_slope', 'talk_finch', 'enter_temple',
  'study_relief', 'rub_wall', 'descend', 'inspect_shaft', 'rope_down', 'freeclimb',
  'hall_breathe', 'examine_body', 'read_door', 'take_tablet', 'open_door',
  'negotiate', 'parley', 'write_log', 'settle_up', 'end_episode',
  // 2장 — 왕 목록을 읽고 각인을 얻는다
  'brief_seraphina', 'ask_permit', 'buy_lamp', 'hire_basim', 'to_marsh',
  'madan_elder', 'rest_marsh', 'basim_shortcut', 'to_mound',
  'find_entrance', 'seraphina_bricks', 'enter_zigg',
  'search_shelves', 'read_kinglist', 'combine_clues', 'salvage_tablets', 'to_canal',
  'steady_breath', 'mark_way', 'rope_across', 'wade_deep',
  'gate_breathe', 'examine_diver', 'read_gate', 'take_seal', 'match_key',
  'share_findings', 'warn_water', 'write_log2', 'thank_party', 'end_episode2',
  // 3장 — 세 번째 기록을 증명하고 문을 봉인한다
  'ask_sokha', 'to_post', 'ask_duchene', 'buy_kit', 'crane_letters', 'to_jungle',
  'follow_sokha', 'jungle_camp', 'cut_through', 'push_on',
  'rubbing_naga', 'crane_council', 'to_gallery',
  'gallery_leave', 'read_ceiling', 'read_third', 'ask_sealers', 'record_chamber', 'to_door',
  'chamber_breathe', 'steady_together', 'read_final', 'seal_gate',
  'final_log', 'settle_all', 'end_campaign', 'go_public',
];

function chooseGolden(state, options, rng, combat) {
  if (combat) return chooseCombat(state, combat, options, rng);

  // 위험도가 꽉 차면 일단 물러난다. 밖에 나갔다 오면 추적이 끊긴다.
  if (state.danger >= 8) {
    const out = options.find((c) => /돌아간다|물러|후퇴|밖으로/.test(c.label));
    if (out && !retreated.has(`${state.scene}:${state.danger}`)) {
      retreated.add(`${state.scene}:${state.danger}`);
      return out;
    }
  }

  // 본줄기를 쫓는 플레이어도 쉬기는 쉰다. 안 쉬면 알아낸 것을 들고 나갈 몸이 없다.
  if (state.san / state.maxSan < 0.5 || state.hp / state.maxHp < 0.5) {
    const rest = options.find((c) => RESTFUL.test(c.label));
    if (rest) return rest;
  }
  // 목록은 진행 순서다. 뒤에서부터 찾으면 '지금 갈 수 있는 가장 앞선 행동'이 잡힌다.
  // 앞에서부터 찾으면 반복 가능한 조사 판정에 갇혀 영원히 같은 자리를 판다.
  for (let i = GOLDEN_PATH.length - 1; i >= 0; i--) {
    const hit = options.find((o) => o.id === GOLDEN_PATH[i]);
    if (!hit) continue;
    // 같은 판정을 세 번 넘게 되풀이하지는 않는다. 사람은 그러지 않는다.
    const key = `${state.scene}:${hit.id}`;
    const tries = repeats.get(key) || 0;
    if (tries >= 3) continue;
    repeats.set(key, tries + 1);
    return hit;
  }
  // 목록에 없는 장면. 아직 세 번 넘게 되풀이하지 않은 것 중에서 고른다.
  const untried = options.filter((o) => (repeats.get(`${state.scene}:${o.id}`) || 0) < 3);
  const pool = untried.length ? untried : options;
  const pick = pool.find((o) => !/돌아|물러|후퇴/.test(o.label)) || pool[pool.length - 1];
  const key = `${state.scene}:${pick.id}`;
  repeats.set(key, (repeats.get(key) || 0) + 1);
  return pick;
}

const RESTFUL = /쉰다|숨을 고른|밤을|야영|기록을 남|셈을 치른|보급|장비를 산|동행을 돌아본다/;

const retreated = new Set();
const repeats = new Map(); // 장면+행동 → 시도 횟수

/**
 * 전투에서의 최소한의 판단.
 * 압박이 차면 엄폐하고, 전의가 꺾이면 말을 걸고, 몸이 상하면 도망친다.
 * 실제 플레이어가 하는 정도이지, 최적 플레이는 아니다.
 */
function chooseCombat(state, combat, options, rng) {
  const pick = (action) => options.find((o) => o.action === action);

  if (combat.pressure >= combat.maxPressure - 4 && pick('cover')) return pick('cover');
  if (combat.round >= 2 && pick('terrain')) return pick('terrain');
  if (state.hp / state.maxHp < 0.35 && pick('flee')) return pick('flee');
  if (combat.resolve <= Math.ceil(combat.maxResolve * 0.35) && pick('parley')) return pick('parley');
  if (pick('ally') && combat.pressure >= 4) return pick('ally');
  return pick('attack') || rng.pick(options);
}

function chooseCautious(state, options, rng, combat) {
  if (combat) return chooseCombat(state, combat, options, rng);
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
  exits: {},
  combatRounds: [],
  finales: {},
  brokeAt: {},
  steps: [],
};

for (let run = 0; run < RUNS; run++) {
  const rng = createRng(run * 7919 + 13);
  retreated.clear();
  repeats.clear();
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
      const sanWas = state.san;
      const sceneWas = state.scene;
      for (const ev of gm.roll()) {
        if (ev.type === 'roll') {
          tally.outcomes[ev.result.outcome] = (tally.outcomes[ev.result.outcome] || 0) + 1;
        }
        if (ev.type === 'combatEnd') {
          tally.exits[ev.exit] = (tally.exits[ev.exit] || 0) + 1;
          tally.combatRounds.push(ev.status.round);
        }
      }
      if (TRACE && run === 0 && state.san !== sanWas) {
        console.log(
          `  ${state.episode.padEnd(12)} ${sceneWas.padEnd(20)} ${'(판정 결과)'.padEnd(24)}` +
            ` 정신 ${state.san - sanWas} → ${state.san}  (위험 ${state.danger})`,
        );
      }
      continue;
    }
    // 신중한 플레이어는 다치면 약을 쓴다. 소지품 사용은 자유 입력으로 간다.
    if ((CAUTIOUS || GOLDEN) && !gm.combat && state.hp / state.maxHp < 0.45) {
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
    const sanBefore = state.san;
    const sceneBefore = state.scene;
    const choice = GOLDEN
      ? chooseGolden(state, options, rng, gm.combat)
      : CAUTIOUS
        ? chooseCautious(state, options, rng, gm.combat)
        : rng.pick(options);
    const evs = gm.act(choice.id);
    if (TRACE && run === 0 && state.san !== sanBefore) {
      console.log(
        `  ${state.episode.padEnd(12)} ${sceneBefore.padEnd(20)} ` +
          `${String(choice.label).slice(0, 22).padEnd(24)} 정신 ${state.san - sanBefore} → ${state.san}` +
          `  (위험 ${state.danger})`,
      );
    }
    for (const ev of evs) {
      if (ev.type === 'combatEnd') {
        tally.exits[ev.exit] = (tally.exits[ev.exit] || 0) + 1;
        tally.combatRounds.push(ev.status.round);
      }
    }
  }

  if (steps >= MAX_STEPS && !state.ended) {
    tally.timedOut++;
    console.error(`[상한 도달] run=${run} scene=${state.scene} steps=${steps}`);
  }

  if (process.argv.includes('--where') && (kindOf(state) === 'broken' || kindOf(state) === 'death')) {
    tally.brokeAt[`${state.episode}/${state.scene}`] =
      (tally.brokeAt[`${state.episode}/${state.scene}`] || 0) + 1;
  }
  if (state.ended?.ending) {
    tally.finales[state.ended.ending] = (tally.finales[state.ended.ending] || 0) + 1;
  }
  const kind = state.ended?.type || 'unfinished';
  tally.endings[kind] = (tally.endings[kind] || 0) + 1;
  tally.professions[prof.name] = tally.professions[prof.name] || { runs: 0, died: 0 };
  tally.professions[prof.name].runs++;
  if (kind === 'death' || kind === 'broken') tally.professions[prof.name].died++;
  if (state.ended?.type === 'chapter' || state.ended?.type === 'finale') tally.reachedEpilogue++;
  tally.chapters.push((state.visitedEpisodes?.length || 0) + 1);
  tally.clueCounts.push(state.clues.length);
  tally.steps.push(steps);
}

function kindOf(st) {
  return st.ended?.type || 'unfinished';
}

const avg = (a) => (a.reduce((x, y) => x + y, 0) / a.length).toFixed(1);
const totalRolls = Object.values(tally.outcomes).reduce((a, b) => a + b, 0);
const TOTAL_CLUES = Object.keys(CLUES).length;

console.log(
  `\n《잃어버린 세계의 지도》 자동 플레이테스트 — ${RUNS}회 · 난이도 ${DIFFICULTY}` +
    ` · ${GOLDEN ? '본줄기를 쫓는' : CAUTIOUS ? '신중한' : '무작위'} 플레이어\n`,
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
const totalFinales = Object.values(tally.finales).reduce((a, b) => a + b, 0);
if (totalFinales) {
  console.log(`\n캠페인 결말 (완주 ${totalFinales}회 기준)`);
  for (const [k, v] of Object.entries(tally.finales).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${k.padEnd(12)} ${String(v).padStart(4)}  (${((v / totalFinales) * 100).toFixed(1)}%)`);
  }
}

const totalExits = Object.values(tally.exits).reduce((a, b) => a + b, 0);
if (totalExits) {
  console.log('\n전투 결말');
  const label = { win: '물러남', parley: '협상', escape: '도주', overrun: '제압당함' };
  for (const key of ['win', 'parley', 'escape', 'overrun']) {
    const n = tally.exits[key] || 0;
    console.log(
      `  ${label[key].padEnd(6)} ${String(n).padStart(4)}  (${((n / totalExits) * 100).toFixed(1)}%)`,
    );
  }
  console.log(`  평균 ${avg(tally.combatRounds)}라운드`);
}

if (Object.keys(tally.brokeAt).length) {
  console.log('\n쓰러진 자리');
  for (const [k, v] of Object.entries(tally.brokeAt).sort((a, b) => b[1] - a[1]).slice(0, 12)) {
    console.log(`  ${k.padEnd(34)} ${v}`);
  }
}

console.log(`\n막힌 세션         ${tally.stuck}`);
console.log(`상한 도달         ${tally.timedOut}  (봇이 제자리를 돈 횟수 — 게임의 결함은 아니다)`);

if (tally.stuck > 0) {
  console.error('\n선택지도 자유 입력도 통하지 않는 세션이 있습니다.');
  process.exit(1);
}
