// 세이브 / 로드. localStorage 한 슬롯 + 수동 백업용 직렬화.

import { SAVE_VERSION } from './state.js';

const KEY = 'lostworldmap.save.v1';
const SETTINGS_KEY = 'lostworldmap.settings.v1';

export function saveGame(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ savedAt: Date.now(), state }));
    return true;
  } catch {
    return false;
  }
}

export function loadGame() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data?.state || data.state.version !== SAVE_VERSION) return null;
    return data;
  } catch {
    return null;
  }
}

export function clearGame() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* 저장소를 못 쓰는 환경이면 조용히 넘어간다 */
  }
}

export function hasSave() {
  return !!loadGame();
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
