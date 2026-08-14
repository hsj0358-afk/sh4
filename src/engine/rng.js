// 시드 기반 난수 생성기.
// 세션을 재현 가능하게 만들어 테스트와 세이브/로드에서 동일한 흐름을 보장한다.

export function hashSeed(str) {
  let h = 1779033703 ^ String(str).length;
  for (let i = 0; i < String(str).length; i++) {
    h = Math.imul(h ^ String(str).charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return h >>> 0;
}

/** mulberry32 — 작고 빠르고 분포가 균일하다. */
export function createRng(seed = Date.now()) {
  let a = typeof seed === 'number' ? seed >>> 0 : hashSeed(seed);

  const rng = {
    /** [0, 1) */
    next() {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    },
    /** min 이상 max 이하 정수 */
    int(min, max) {
      return min + Math.floor(rng.next() * (max - min + 1));
    },
    pick(arr) {
      return arr[rng.int(0, arr.length - 1)];
    },
    chance(p) {
      return rng.next() < p;
    },
    /** 현재 내부 상태 — 세이브에 기록한다. */
    getState() {
      return a >>> 0;
    },
    setState(v) {
      a = v >>> 0;
    },
  };

  return rng;
}
