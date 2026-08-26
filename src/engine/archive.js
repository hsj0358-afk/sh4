// 회차 계승 — 탐사가 끝나도 남는 기록 (기획서 18절).
//
// 세이브(save.js)는 진행 중인 한 판이다. 아카이브는 그 위의 층으로,
// 여러 판을 가로질러 "이 계정이 지금까지 무엇을 보았는가"를 쌓는다.
// 도감이 이 위에 선다. 죽어서 끝난 판도 본 것은 도감에 남는다 —
// 그래야 실패한 회차가 버려지는 시간이 아니게 된다.
//
// 계승되는 것은 지식뿐이다. 능력치도 장비도 넘어가지 않는다.
// 넘겨주면 회차가 쌓일수록 쉬워지고, 쉬워지면 1897년이 아니게 된다.

const KEY = 'lostworldmap.archive.v1';

/** 로그북에 남기는 회차 수. 그 이상은 아무도 되짚지 않는다. */
const LOG_LIMIT = 20;

export function emptyArchive() {
  return {
    version: 1,
    runs: 0,
    finished: 0,
    clues: [],
    items: [],
    endings: [],
    encounters: [],
    companions: [],
    episodes: [],
    professions: [],
    bestClueCount: 0,
    runLog: [],
  };
}

export function loadArchive() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return emptyArchive();
    const data = JSON.parse(raw);
    if (data?.version !== 1) return emptyArchive();
    return { ...emptyArchive(), ...data };
  } catch {
    return emptyArchive();
  }
}

export function saveArchive(archive) {
  try {
    localStorage.setItem(KEY, JSON.stringify(archive));
    return true;
  } catch {
    return false;
  }
}

export function clearArchive() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* 저장소를 못 쓰는 환경이면 조용히 넘어간다 */
  }
}

const merge = (list, incoming) => [...new Set([...list, ...incoming])];

/**
 * 한 판의 상태를 아카이브에 반영한다.
 * 중간에 여러 번 불러도 안전하다 — 수집 목록은 전부 집합 연산이다.
 *
 * `ended`는 판이 끝났다는 뜻이고(죽어서 끝난 것도 포함), 그때 로그북에 한 줄이 남는다.
 * `completed`는 캠페인을 끝까지 갔다는 뜻이다. 둘은 같지 않다.
 * 카운터를 올리므로 한 판당 한 번만 참으로 넘긴다.
 *
 * @returns {{ archive: object, firsts: object }} 갱신된 아카이브와 '이번에 처음 본 것'
 */
export function record(archive, state, { ended = false, completed = false } = {}) {
  const next = { ...archive };

  const items = state.inventory.map((i) => i.name);
  const companionIds = Object.keys(state.companions);
  const endingId = state.ended?.ending || null;

  const firsts = {
    clues: state.clues.filter((c) => !archive.clues.includes(c)),
    items: items.filter((n) => !archive.items.includes(n)),
    companions: companionIds.filter((c) => !archive.companions.includes(c)),
    ending: endingId && !archive.endings.includes(endingId) ? endingId : null,
  };

  next.clues = merge(archive.clues, state.clues);
  next.items = merge(archive.items, items);
  next.companions = merge(archive.companions, companionIds);
  next.episodes = merge(archive.episodes, [
    ...(state.visitedEpisodes || []),
    ...(state.episode ? [state.episode] : []),
  ]);
  next.professions = merge(archive.professions, [state.char.professionId]);
  next.encounters = merge(archive.encounters, seenEncounters(state));
  if (endingId) next.endings = merge(archive.endings, [endingId]);
  next.bestClueCount = Math.max(archive.bestClueCount, state.clues.length);

  if (completed) next.finished = archive.finished + 1;
  if (ended) {
    next.runLog = [runEntry(next.runs, state), ...archive.runLog].slice(0, LOG_LIMIT);
  }

  return { archive: next, firsts };
}

/** 로그북 한 줄. 이 회차가 누구였고 어디서 끝났는지. */
function runEntry(runNumber, state) {
  return {
    n: runNumber,
    name: state.char.name,
    profession: state.char.profession,
    difficulty: state.difficulty,
    outcome: state.ended?.type || 'unknown',
    title: state.ended?.title || '기록되지 않음',
    ending: state.ended?.ending || null,
    clues: state.clues.length,
    episode: state.episode,
    chapters: (state.visitedEpisodes?.length || 0) + 1,
  };
}

/** 새 판이 시작될 때 회차를 센다. */
export function countRun(archive) {
  return { ...archive, runs: archive.runs + 1 };
}

/**
 * 이번 판에서 마주친 조우.
 * 전투에 들어가면 `encountered:<id>` 플래그가 남으므로 그것으로 되짚는다.
 */
function seenEncounters(state) {
  return Object.keys(state.flags || {})
    .filter((k) => k.startsWith('encountered:'))
    .map((k) => k.slice('encountered:'.length));
}

/** 도감 진행률. */
export function progress(archive, totals) {
  const pct = (have, all) => (all ? Math.round((have / all) * 100) : 0);
  const row = (key) => {
    const have = (archive[key] || []).length;
    const all = totals[key] || 0;
    return { have, all, pct: pct(have, all) };
  };
  return {
    clues: row('clues'),
    items: row('items'),
    endings: row('endings'),
    companions: row('companions'),
    encounters: row('encounters'),
    professions: row('professions'),
  };
}
