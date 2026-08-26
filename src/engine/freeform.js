// 자유 입력 해석기.
//
// 기획서 11·12의 AI GM 응답 원칙을 규칙으로 옮긴 층이다.
//   - 입력을 자연스럽게 해석한다
//   - 가능한 행동은 진행한다
//   - 불확실한 행동은 판정을 요구한다
//   - 불가능한 행동은 "안 됩니다"가 아니라 세계관 안에서 설명한다
//
// 해석 순서:
//   1) 현재 장면이 직접 정의한 freeform 핸들러 (가장 구체적)
//   2) 현재 장면의 선택지와의 키워드 일치 (선택지를 말로 부른 경우)
//   3) 전역 행동 사전 (휴식, 대화, 조사, 소지품, 이동 …)
//   4) 해석 실패 — 세계관 안에서 되묻는다

import { subj, topic, obj } from '../korean.js';

const norm = (s) => String(s || '').toLowerCase().replace(/\s+/g, '');

function hit(text, keys) {
  const t = norm(text);
  return (keys || []).some((k) => t.includes(norm(k)));
}

/** 행동의 결(intent)만 뽑아낸다. 서술 톤을 고르는 데 쓴다. */
export const VERBS = {
  조사: ['조사', '살펴', '본다', '보다', '확인', '들여다', '관찰', '뒤진', '찾아', '찾는', '수색'],
  대화: ['말한다', '말을', '묻는다', '물어', '대화', '이야기', '설득', '부른다', '얘기'],
  이동: ['간다', '이동', '들어간다', '나간다', '내려간다', '올라', '따라간다', '떠난다', '돌아간다'],
  완력: ['민다', '밀어', '당긴다', '부순다', '깨', '들어올', '치운다', '연다', '열어'],
  은밀: ['숨는다', '몰래', '조용히', '잠입', '기다린다', '엿듣'],
  사용: ['사용', '쓴다', '켠다', '비춘다', '꺼낸다', '건넨다', '준다'],
  휴식: ['쉰다', '휴식', '잔다', '앉는다', '회복', '숨을 고른'],
  공격: ['공격', '쏜다', '때린다', '벤다', '싸운다', '죽인'],
};

export function detectVerb(text) {
  for (const [verb, keys] of Object.entries(VERBS)) {
    if (hit(text, keys)) return verb;
  }
  return null;
}

/**
 * 전역 행동. 어느 장면에서나 통한다.
 * 각 항목은 { keys, build(ctx) } 이고 build 는 액션 객체를 돌려준다.
 */
const GLOBAL_ACTIONS = [
  {
    id: 'inventory',
    keys: ['소지품', '가방', '짐을', '인벤', '장비를 확인', '뭘 가지고'],
    build({ state }) {
      const list = state.inventory
        .map((i) => (i.uses === null ? i.name : `${i.name}(${i.uses})`))
        .join(', ');
      return {
        kind: 'narration',
        text: [`가방을 열어 내용물을 훑는다.`, list || '비어 있다. 손에 남은 것이 없다.'],
        effects: {},
      };
    },
  },
  {
    id: 'rest',
    keys: VERBS.휴식,
    build({ state }) {
      const risky = state.danger >= 5;
      return {
        kind: 'narration',
        text: risky
          ? [
              '벽에 등을 대고 숨을 고른다.',
              '호흡이 잦아들자, 대신 다른 소리가 들리기 시작한다. 오래 있을 곳이 아니다.',
            ]
          : [
              '잠시 앉는다. 땀이 식으면서 손끝의 떨림이 가라앉는다.',
              '시간은 그동안에도 흐른다.',
            ],
        effects: {
          hp: 1,
          san: risky ? 0 : 1,
          time: 2,
          danger: risky ? 1 : 0,
        },
      };
    },
  },
  {
    id: 'notebook',
    keys: ['수첩', '기록을', '메모', '단서를 정리', '지금까지'],
    build({ state, clueTitles }) {
      const found = state.clues.map((c) => clueTitles[c] || c);
      return {
        kind: 'narration',
        text: [
          '수첩을 펴고, 지금까지의 것을 다시 읽는다.',
          found.length
            ? found.map((f) => `— ${f}`).join('\n')
            : '아직 적어둔 것이 없다. 전부 머릿속에만 있다.',
        ],
        effects: {},
      };
    },
  },
  {
    id: 'pray',
    keys: ['기도', '빈다', '성호'],
    build() {
      return {
        kind: 'narration',
        text: [
          '무엇에게 하는지도 모르는 채로 짧게 빈다.',
          '들어주는 것이 있다면, 그것은 당신이 아는 이름이 아닐 것이다.',
        ],
        effects: { san: 1 },
      };
    },
  },
  {
    id: 'shout',
    keys: ['소리친다', '외친다', '고함', '부른다 크게', '소리를 지'],
    build({ state }) {
      return {
        kind: 'narration',
        text: [
          '목소리가 벽을 때리고 되돌아온다.',
          state.danger >= 4
            ? '그리고 되돌아온 것 중에는, 당신의 목소리가 아닌 것이 섞여 있다.'
            : '한참 뒤에야 잦아든다. 이 안에 있는 무엇이든, 이제 당신의 위치를 안다.',
        ],
        effects: { danger: 2 },
      };
    },
  },
];

/** 동료에게 말을 거는 행동. */
function companionTalk(text, state) {
  for (const c of Object.values(state.companions)) {
    if (!c.present) continue;
    const first = c.name.split(' ')[0];
    if (!hit(text, [c.name, first])) continue;

    const warm = c.affinity >= 3;
    return {
      kind: 'narration',
      speaker: c.name,
      text: warm
        ? [
            `${subj(c.name)} 당신 쪽으로 몸을 돌린다.`,
            '"먼저 물어봐 주는 사람이 드물어요." 대답은 짧지만, 등이 조금 펴진다.',
          ]
        : [
            `${topic(c.name)} 당신의 말을 끝까지 듣고, 잠시 침묵한다.`,
            '"그렇게 하죠." 그 이상은 말하지 않는다.',
          ],
      effects: { companion: { id: c.id, affinity: 1 }, time: 1 },
    };
  }
  return null;
}

/** 소지품을 쓰는 행동. */
function itemUse(text, state, getItemDef) {
  for (const inv of state.inventory) {
    if (!hit(text, [inv.name])) continue;
    const def = getItemDef(inv.name);
    if (def?.use) {
      return {
        kind: 'narration',
        text: [`${obj(inv.name)} 쓴다.`, def.use.text],
        effects: {
          hp: def.use.hp || 0,
          san: def.use.san || 0,
          spend: { [inv.name]: 1 },
          time: 1,
        },
      };
    }
    return {
      kind: 'narration',
      text: [
        `${obj(inv.name)} 손에 쥔다.`,
        def?.desc || '익숙한 무게다.',
        '쓸 자리가 오면, 알아서 손이 먼저 움직일 것이다.',
      ],
      effects: {},
    };
  }
  return null;
}

/**
 * 정신력이 낮을 때의 오독(誤讀). 기획서 7-7의 "환각 또는 오판 이벤트".
 * 입력을 무시하지는 않는다 — 한 박자 어긋난 서술을 먼저 끼워 넣을 뿐이다.
 */
export function hallucination(state, rng) {
  if (state.san > Math.ceil(state.maxSan * 0.3)) return null;
  if (!rng.chance(0.35)) return null;
  return rng.pick([
    '— 손이 먼저 움직였다가, 멈춘다. 방금 하려던 것이 무엇이었는지 잠깐 놓쳤다.',
    '— 시야 가장자리에서 무언가 지나갔다. 고개를 돌리면 아무것도 없다.',
    '— 누군가 당신의 이름을 불렀다. 이곳에 그 이름을 아는 사람은 없다.',
    '— 벽의 문양이 조금 전과 다르게 배열되어 있다. 그럴 리 없다.',
  ]);
}

/**
 * 자유 입력을 해석한다.
 * @returns {object} 액션 객체
 *   { kind: 'choice', choice }                       — 기존 선택지로 연결
 *   { kind: 'narration', text, effects }             — 즉시 서술
 *   { kind: 'check', label, check, outcomes, text }  — 판정 요구
 *   { kind: 'unknown', text }                        — 해석 실패
 */
export function interpret(input, ctx) {
  const { state, scene, getItemDef, clueTitles = {} } = ctx;
  const text = String(input || '').trim();
  if (!text) return { kind: 'unknown', text: ['...'] };

  // 1) 장면이 직접 정의한 해석기
  for (const h of scene.freeform || []) {
    if (!hit(text, h.keys)) continue;
    if (h.verb && detectVerb(text) !== h.verb) continue;
    if (h.when && !h.when(state)) continue;
    return { ...h, kind: h.check ? 'check' : 'narration' };
  }

  // 2) 선택지를 말로 부른 경우
  for (const c of scene.choices || []) {
    const keys = c.keys || [c.label];
    if (hit(text, keys)) return { kind: 'choice', choice: c };
  }

  // 3) 전역 사전
  const talk = companionTalk(text, state);
  if (talk) return talk;

  const used = itemUse(text, state, getItemDef);
  if (used) return used;

  for (const g of GLOBAL_ACTIONS) {
    if (hit(text, g.keys)) return g.build({ state, clueTitles });
  }

  // 4) 동사만 잡히는 경우 — 장면의 기본 조사/이동으로 흘려보낸다.
  const verb = detectVerb(text);
  if (verb === '조사' && scene.ambientCheck) {
    return { ...scene.ambientCheck, kind: 'check' };
  }
  if (verb === '공격') {
    return {
      kind: 'narration',
      text: [
        '손이 무기 쪽으로 갔다가 멈춘다.',
        '겨눌 대상이 없다. 여기서 휘두를 수 있는 것은 당신의 조급함뿐이다.',
      ],
      effects: { danger: 1 },
    };
  }
  if (verb === '이동' && scene.exits?.length) {
    return {
      kind: 'narration',
      text: [
        '떠날 길은 있다.',
        `지금 향할 수 있는 곳: ${scene.exits.join(', ')}.`,
      ],
      effects: {},
    };
  }

  // 5) 해석 실패 — 세계관 안에서 되묻는다
  return {
    kind: 'unknown',
    text: [
      '당신은 그렇게 하려다가, 이곳에서 그 행동이 무엇이 되어야 할지 알지 못한 채 멈춘다.',
      '조금 더 분명하게. — 무엇을 보고, 무엇을 건드릴 것인가?',
    ],
  };
}
