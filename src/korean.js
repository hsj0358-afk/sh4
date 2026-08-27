// 조사 붙이기.
//
// 동료 이름은 콘텐츠가 정하고 문장은 엔진이 만든다. 그래서 "${c.name}가 떠났다" 같은
// 문장이 생기고, 이름이 '나디아 하룬'이면 "하룬가 떠났다"가 된다.
// 받침이 있는지는 유니코드가 알고 있으니 물어보면 된다.
//
// 엔진도 콘텐츠도 UI도 쓰는 순수 함수라서 어느 쪽에도 두지 않고 여기 둔다.

const HANGUL_START = 0xac00;
const HANGUL_END = 0xd7a3;

/** 마지막 글자에 받침이 있는가. 한글 음절이 아니면 없는 것으로 본다. */
export function hasBatchim(word) {
  const s = String(word ?? '').trim();
  if (!s) return false;
  const code = s.charCodeAt(s.length - 1);
  if (code < HANGUL_START || code > HANGUL_END) return false;
  return (code - HANGUL_START) % 28 !== 0;
}

const pick = (word, withB, withoutB) => `${word}${hasBatchim(word) ? withB : withoutB}`;

/** 이/가 */
export const subj = (word) => pick(word, '이', '가');
/** 은/는 */
export const topic = (word) => pick(word, '은', '는');
/** 을/를 */
export const obj = (word) => pick(word, '을', '를');
/** 과/와 */
export const and = (word) => pick(word, '과', '와');
/**
 * 으로/로. ㄹ 받침은 예외다 — '횃불로'이지 '횃불으로'가 아니다.
 * 종성 ㄹ 의 색인은 8.
 */
export function to(word) {
  const s = String(word ?? '').trim();
  const code = s.charCodeAt(s.length - 1);
  const jong =
    code >= HANGUL_START && code <= HANGUL_END ? (code - HANGUL_START) % 28 : 0;
  return `${s}${jong === 0 || jong === 8 ? '로' : '으로'}`;
}
/** 아/야 — 부르는 말 */
export const call = (word) => pick(word, '아', '야');
/** 이에게/에게 는 받침과 무관하다. 헷갈리지 않도록 여기 적어 둔다. */

// ── 자리표 채우기 ──────────────────────────────────────────────
//
// 탐사자 이름은 사람마다 다르니 콘텐츠가 문장에 박아 둘 수 없다.
// 그렇다고 문장마다 함수로 바꾸면 읽기 어려워진다. 그래서 자리표를 쓴다:
//
//   '{이름은} 부두에 내려선다.'  →  '몰리는 부두에 내려선다.'
//
// 조사를 자리표 안에 넣는 이유는, 밖에 두면 치환한 뒤에 다시 고쳐야 하기 때문이다.
// 안에 두면 채울 때 한 번에 맞는 조사를 고른다.

const PARTICLE = {
  은: topic, 는: topic,
  이: subj, 가: subj,
  을: obj, 를: obj,
  과: and, 와: and,
  아: call, 야: call,
  으로: to, 로: to,
};

const TOKEN = /\{([^{}\s]+)\}/g;
const TAIL = /^(.+?)(으로|로|은|는|이|가|을|를|과|와|아|야)$/;

/**
 * 문장 속 `{키}` 를 값으로 바꾼다. `{키+조사}` 형태면 받침에 맞는 조사를 붙인다.
 * 모르는 키는 건드리지 않고 그대로 둔다 — 조용히 지워 버리면 빈 자리만 남는다.
 */
export function fill(text, vars = {}) {
  return String(text ?? '').replace(TOKEN, (whole, token) => {
    if (token in vars) return String(vars[token]);
    const m = token.match(TAIL);
    if (m && m[1] in vars) return PARTICLE[m[2]](String(vars[m[1]]));
    return whole;
  });
}
