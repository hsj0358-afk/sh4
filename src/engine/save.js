// 세이브 / 로드.
//
// 슬롯 셋. 하나로 두면 새 직업을 시험해 보려다 진행 중인 판을 지우게 된다 —
// 이 게임은 한 판이 한 시간짜리라 그 실수의 값이 크다.
//
// 도감(archive.js)은 슬롯과 무관하게 하나다. 슬롯은 '지금 굴리고 있는 판'이고
// 도감은 '이 계정이 지금까지 본 것'이라, 나뉘어야 할 이유가 없다.

import { SAVE_VERSION } from './state.js';

export const SLOTS = 3;

const SLOT_KEY = (n) => `lostworldmap.slot.v1.${n}`;
const SETTINGS_KEY = 'lostworldmap.settings.v1';

/** 슬롯이 하나뿐이던 시절의 키. 남아 있으면 1번 슬롯으로 옮긴다. */
const LEGACY_KEY = 'lostworldmap.save.v1';

const read = (key) => {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data?.state || data.state.version !== SAVE_VERSION) return null;
    return data;
  } catch {
    return null;
  }
};

const write = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
};

const drop = (key) => {
  try {
    localStorage.removeItem(key);
  } catch {
    /* 저장소를 못 쓰는 환경이면 조용히 넘어간다 */
  }
};

/**
 * 옛 단일 슬롯 세이브를 1번으로 옮긴다.
 *
 * 슬롯을 늘리면서 키가 바뀌었다. 옮기지 않으면 업데이트한 사람의 진행 중인 판이
 * 그냥 사라진다 — 게임이 지웠다는 표시조차 없이.
 */
export function migrateLegacy() {
  const old = read(LEGACY_KEY);
  if (!old) return false;
  if (!read(SLOT_KEY(0))) write(SLOT_KEY(0), old);
  drop(LEGACY_KEY);
  return true;
}

export function saveGame(state, slot = 0) {
  return write(SLOT_KEY(slot), { savedAt: Date.now(), state });
}

export function loadGame(slot = 0) {
  return read(SLOT_KEY(slot));
}

export function clearGame(slot = 0) {
  drop(SLOT_KEY(slot));
}

export function hasSave(slot = 0) {
  return !!loadGame(slot);
}

/** 어느 슬롯에든 저장된 판이 있는가. */
export function hasAnySave() {
  return slotList().some((s) => !s.empty);
}

/** 첫 번째 빈 슬롯. 전부 차 있으면 -1. */
export function firstEmptySlot() {
  const found = slotList().find((s) => s.empty);
  return found ? found.index : -1;
}

/**
 * 슬롯 목록. 화면에 그대로 그릴 수 있는 형태로 돌려준다.
 *
 * 엔진이 UI 문구를 만드는 것이 아니라, UI 가 필요로 하는 사실만 추려 준다 —
 * 이름·직업·몇 번째 장·어디·언제 저장했는지.
 */
export function slotList() {
  const out = [];
  for (let i = 0; i < SLOTS; i++) {
    const data = loadGame(i);
    if (!data) {
      out.push({ index: i, empty: true });
      continue;
    }
    const s = data.state;
    out.push({
      index: i,
      empty: false,
      savedAt: data.savedAt,
      name: s.char?.name || '이름 없는 탐사자',
      profession: s.char?.profession || '',
      chapter: (s.visitedEpisodes?.length || 0) + 1,
      episode: s.episode,
      tick: s.tick,
      hp: s.hp,
      maxHp: s.maxHp,
      san: s.san,
      maxSan: s.maxSan,
      clues: s.clues?.length || 0,
      ended: s.ended?.type || null,
    });
  }
  return out;
}

export function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
  } catch {
    return {};
  }
}

export function saveSettings(s) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    /* 무시 */
  }
}
