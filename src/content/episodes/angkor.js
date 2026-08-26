// 에피소드 3 — 밀림이 삼킨 회랑
// 시엠레아프 상륙부터 여덟 번째 문 앞의 마지막 선택까지.
//
// 캠페인의 마지막 장이다. 그래서 두 가지가 앞의 둘과 다르다.
//
//   1. 세 번째 대륙이다. 2장의 조합 추론이 "증명하려면 하나가 더 필요하다"고
//      말했던 그 하나가 여기 있다. 세 기록이 나란히 놓이면 추론이 사실이 된다.
//   2. 결말이 갈린다. 마지막 선택 하나가 아니라, 세 대륙을 지나오며 무엇을 알아냈고
//      누구를 잃지 않았는지가 함께 정한다. content/endings.js 를 참조.

import { subj } from '../../korean.js';
import { CLUE_TITLES } from '../clues.js';
import { ticksUntil } from '../../clock.js';

const ep = {
  id: 'angkor',
  title: '에피소드 3 — 밀림이 삼킨 회랑',
  region: '프랑스령 인도차이나 · 앙코르',
  clueTitles: CLUE_TITLES,
  start: 'siem_landing',

  // 바스라에서 여기까지. 인도양을 건너 사이공, 다시 강을 거슬러 5주.
  arrival: { time: 24 * 2 * 35, hp: 14, san: 12 },

  map: {
    groundY: 46,
    surfaceLabel: '회랑',
    depthLabel: '그 아래',
    nodes: [
      { scene: 'siem_landing', label: '톤레사프 선착장', x: 10, y: 14 },
      { scene: 'french_post', label: '측량대 주둔지', x: 33, y: 8 },
      { scene: 'jungle_march', label: '보리수의 길', x: 56, y: 18 },
      { scene: 'causeway', label: '서쪽 참배로', x: 80, y: 14 },
      { scene: 'naga_gallery', label: '나가 회랑', x: 88, y: 34 },
      { scene: 'star_chamber', label: '별의 방', x: 66, y: 58 },
      { scene: 'the_door', label: '여덟 번째 문', x: 44, y: 78 },
      { scene: 'angkor_finale', label: '회랑 바깥', x: 22, y: 40 },
      { scene: 'angkor_epilogue', label: '돌아가는 배', x: 8, y: 34 },
    ],
    links: [
      ['siem_landing', 'french_post'],
      ['siem_landing', 'jungle_march'],
      ['french_post', 'jungle_march'],
      ['jungle_march', 'causeway'],
      ['causeway', 'naga_gallery'],
      ['naga_gallery', 'star_chamber'],
      ['star_chamber', 'the_door'],
      ['the_door', 'angkor_finale'],
      ['angkor_finale', 'angkor_epilogue'],
    ],
  },

  pressureEvents: [
    {
      id: 'fever',
      minDanger: 5,
      scenes: ['jungle_march', 'causeway'],
      text: [
        '오한이 등을 타고 올라온다. 볕은 그대로인데 이가 부딪힌다.',
        '밀림에서 이것이 시작되면, 이틀 안에 결판이 난다.',
      ],
      effects: { hp: -2, danger: 1 },
    },
    {
      id: 'roots',
      minDanger: 6,
      scenes: ['naga_gallery', 'star_chamber'],
      text: [
        '머리 위에서 뿌리가 움직인다. 바람이 아니다. 이 안에 바람은 없다.',
        '돌 사이에서 뿌리가 자라는 소리는, 아주 느린 발소리와 구별되지 않는다.',
      ],
      effects: { san: -1, danger: 1 },
    },
    {
      id: 'the_third',
      minDanger: 8,
      text: [
        '앞서가는 사람의 수를 센다. 둘. 다시 센다. 셋.',
        '세 번째 사람은 세 번째로 세어질 때만 있다.',
      ],
      effects: { san: -2 },
    },
    {
      id: 'measured',
      minDanger: 10,
      scenes: ['naga_gallery', 'star_chamber', 'the_door'],
      text: [
        '벽에 등을 대고 쉬다가, 등 뒤의 새김이 손에 닿는다.',
        '숫자다. 그리고 그 숫자는 당신의 키와 같다.',
      ],
      effects: { san: -2, danger: 1 },
    },
  ],

  scenes: {
    // ── 1. 상륙 ────────────────────────────────────────────────
    siem_landing: {
      id: 'siem_landing',
      location: '톤레사프 · 선착장',
      exits: ['측량대 주둔지', '보리수의 길'],
      onEnter(state, visits) {
        if (visits > 1) return {};
        const eff = { companions: ['sokha'] };
        // 크레인은 두 번 총을 겨눴고 두 번 물러섰다. 세 번째에는 같은 배를 탄다.
        if (state.flags.craneAlly || state.flags.craneAllied2 || state.flags.savedCrane) {
          eff.companions.push('crane');
        }
        // 세라피나는 마르기를 기다리는 일을 잘한다. 5주를 배 위에서 보냈다.
        if (state.companions.seraphina && !state.companions.seraphina.present) {
          eff.companionChanges = [{ id: 'seraphina', present: true }];
        }
        return eff;
      },
      body: (state) => {
        const out = [
          '5주. 인도양을 건너 사이공에 닿고, 다시 강을 거슬러 호수까지 올라왔다.',
          '톤레사프는 계절마다 크기가 변하는 호수다. 지금은 물이 빠지는 철이라 ' +
            '선착장이 뭍 한가운데 서 있다. 배를 대려면 진흙을 삼백 보 걸어야 한다.',
        ];

        if (state.companions.crane?.present) {
          out.push(
            '크레인이 먼저 내린다. 진흙에 부츠가 발목까지 잠기는데 표정을 바꾸지 않는다.',
            '"두 번은 당신 앞을 막았고," 그가 뒤도 돌아보지 않고 말한다.',
            '"세 번째는 옆에 서 보려고 합니다. 어느 쪽이 더 성가실지는 두고 봅시다."',
          );
        } else {
          out.push(
            '크레인의 전보는 사이공에서 끊겼다. 알렉산드리아로 돌아갔다는 소문도,',
            '이미 여기 와 있다는 소문도 있다. 둘 다 확인할 방법이 없다.',
          );
        }

        out.push(
          '선착장 끝에 젊은 여자가 서 있다. 손에 접은 도면을 들고 있고, ' +
            '그 도면은 프랑스 측량대의 것이다.',
          '"속하입니다." 그녀가 프랑스어로 말하고, 당신이 알아듣는 것을 확인한 뒤 이어 간다.',
          '"서편 회랑을 찾으신다고 들었습니다. 그쪽은 이 도면에 없습니다."',
          '"없는 게 아니라, 지워졌습니다."',
        );
        return out;
      },
      revisitBody: [
        '선착장의 진흙이 낮 동안 굳었다가 다시 물러진다.',
        '속하가 도면을 접었다 펴며 기다린다.',
      ],
      ambientCheck: {
        label: '선착장을 살핀다',
        check: { stat: '관찰', tags: ['조사', '정보'], target: 13, label: '관찰 판정' },
        outcomes: {
          crit: {
            text: [
              '뭍에 올려둔 배들 사이에 한 척이 다르다. 흘수가 깊고, 바닥에 진흙이 없다.',
              '최근에 물에서 올린 것이 아니라, 언제든 다시 내릴 준비가 되어 있는 배다.',
              '뱃전에 표식이 하나 새겨져 있다. 원. 안쪽이 검게 그을린 원.',
            ],
            effects: { clues: ['banyan_road'], flags: { sawSealerMark: true }, san: -1, time: 2 },
          },
          success: {
            text: [
              '배 한 척이 다른 것들과 다르게 놓여 있다. 언제든 내릴 수 있게.',
              '누군가 이 호수를 급하게 떠날 준비를 하고 있다.',
            ],
            effects: { clues: ['banyan_road'], time: 2 },
          },
          partial: {
            text: [
              '진흙 위의 발자국을 따라가다 놓친다. 물이 빠진 자리는 발자국을 오래 두지 않는다.',
            ],
            effects: { time: 2 },
          },
          fail: {
            text: [
              '볕이 진흙에 반사되어 눈을 찌른다.',
              '삼백 보를 걸어 나갔다가 삼백 보를 걸어 돌아왔다.',
            ],
            effects: { time: 3 },
          },
          fumble: {
            text: [
              '진흙에 무릎까지 빠진다. 빼내는 데 20분이 걸렸다.',
              '빠져나왔을 때 부츠 한 짝이 아래에 남았고, 그것은 끝내 찾지 못했다.',
            ],
            effects: { hp: -1, time: 3 },
          },
        },
      },
      choices: [
        {
          id: 'ask_sokha',
          label: '속하에게 지워진 구역을 묻는다',
          keys: ['속하', '지워진', '도면', '구역'],
          once: true,
          check: {
            stat: '설득',
            tags: ['사교', '정보'],
            target: 12,
            label: '설득 판정',
            prompt: [
              '그녀는 도면을 펴서 서편을 짚는다. 그 자리에 종이가 한 번 긁힌 자국이 있다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '"아버지가 측량대에서 3년 일했습니다. 저는 그 뒤로 3년이고요."',
                '"1894년에 서편 구역을 측량했습니다. 도면을 그렸고, 그해 겨울에 지웠습니다."',
                '"지운 건 프랑스인이 아닙니다. 측량대장이 지우라고 했고, 그 사람에게 그렇게 ' +
                  '말한 사람은 크메르인이었어요."',
                '그녀가 잠시 멈춘다. "그 사람 손바닥에 원이 그을려 있었습니다."',
              ],
              effects: {
                clues: ['french_survey', 'banyan_road'],
                companion: { id: 'sokha', trust: 2, affinity: 1 },
                flags: { knowsErasure: true },
                time: 2,
              },
            },
            success: {
              text: [
                '"1894년에 측량했고, 그해 겨울에 지웠습니다."',
                '"왜 지웠는지는 아무도 설명하지 않았고, 아무도 묻지 않았습니다."',
                '그녀가 도면을 접는다. "저는 물었습니다. 그래서 지금 여기 있고요."',
              ],
              effects: {
                clues: ['french_survey'],
                companion: { id: 'sokha', trust: 1 },
                flags: { knowsErasure: true },
                time: 2,
              },
            },
            partial: {
              text: [
                '"도면에 없는 곳은 안내할 수 없습니다." 그녀가 말한다.',
                '그러나 도면을 접는 손이 서편을 한 번 더 짚는다. 습관처럼.',
              ],
              effects: { time: 2 },
            },
            fail: {
              text: [
                '"저는 안내인입니다. 도면은 제가 그린 게 아니고요."',
                '대화는 거기서 끝난다.',
              ],
              effects: { time: 2 },
            },
            fumble: {
              text: [
                '당신은 돈을 얹으며 물었다.',
                '속하가 도면을 접어 겨드랑이에 끼운다.',
                '"프랑스인들도 그렇게 시작했습니다. 그다음에 지우라고 하더군요."',
              ],
              effects: { companion: { id: 'sokha', trust: -1 }, time: 2 },
            },
          },
        },
        {
          id: 'to_post',
          label: '측량대 주둔지에 들른다',
          keys: ['측량대', '주둔지', '프랑스'],
          text: ['호수를 등지고 붉은 흙길을 오른다. 삼색기가 축 늘어져 있다.'],
          effects: { time: 3, goto: 'french_post' },
        },
        {
          id: 'straight_jungle',
          label: '바로 밀림으로 들어간다',
          keys: ['밀림', '바로', '출발', '들어간다'],
          hint: '준비는 줄지만, 우기가 오기 전에 도착한다',
          text: [
            '"지금요?" 속하가 하늘을 본다. "…나쁘지 않습니다. 우기까지 열흘이니까요."',
            '진흙길이 곧 흙길이 되고, 흙길이 곧 사라진다.',
          ],
          effects: { time: 6, flags: { rushedJungle: true }, goto: 'jungle_march' },
        },
      ],
      freeform: [
        {
          keys: ['호수', '톤레사프', '물을 본다'],
          text: [
            '호수는 계절마다 다섯 배로 부풀었다가 줄어든다.',
            '이 땅의 모든 것이 그 리듬에 맞춰져 있다. 사람도, 물고기도, 그리고 아마 저 회랑도.',
          ],
          effects: {},
        },
      ],
    },

    // ── 2. 측량대 ─────────────────────────────────────────────
    french_post: {
      id: 'french_post',
      location: '앙코르 · 프랑스 측량대 주둔지',
      exits: ['선착장', '보리수의 길'],
      body: [
        '주둔지는 나무 기둥 위에 올린 방갈로 세 채가 전부다. 아래로 물이 지나가게 지었다.',
        '측량대장 뒤셴 대위는 마흔쯤이고, 여기서 6년을 보냈다. 그것이 얼굴에 다 나와 있다.',
        '"영국인이시군요." 그가 럼을 두 잔 따른다. "학회에서 오셨습니까, 아니면 개인적으로?"',
        '벽에 커다란 도면이 걸려 있다. 서편 구역이 흰 종이 그대로다.',
      ],
      revisitBody: [
        '뒤셴은 같은 자리에 같은 자세로 앉아 있다.',
        '"또 오셨군요. 럼은 남아 있습니다."',
      ],
      ambientCheck: {
        label: '벽의 도면을 살핀다',
        check: { stat: '관찰', tags: ['조사', '방향'], target: 13, label: '관찰 판정' },
        outcomes: {
          crit: {
            text: [
              '흰 종이는 원래 흰 것이 아니었다. 긁어낸 자국이 볕의 각도에 따라 드러난다.',
              '지워진 선을 눈으로 잇는다. 회랑 하나, 계단 하나, 그리고 원형의 무언가.',
              '원형. 이집트의 그 방과 같은 지름으로 보인다.',
            ],
            effects: { clues: ['french_survey'], items: ['프랑스 측량도'], san: -1, time: 2 },
          },
          success: {
            text: [
              '흰 종이 위로 긁어낸 자국이 남아 있다. 지운 것이지 비운 것이 아니다.',
              '지워진 구역의 윤곽만은 읽힌다.',
            ],
            effects: { clues: ['french_survey'], time: 2 },
          },
          partial: {
            text: ['무언가 있었다는 것까지는 알겠다. 무엇이었는지는 아니다.'],
            effects: { time: 2 },
          },
          fail: {
            text: ['도면은 도면이다. 흰 곳은 희다. 럼이 한 잔 줄었다.'],
            effects: { time: 2 },
          },
          fumble: {
            text: [
              '도면에 너무 가까이 다가섰다. 뒤셴이 조용히 일어나 도면 앞에 선다.',
              '"측량대 자산입니다." 그가 웃으며 말한다. 웃는 얼굴로 하는 경고가 가장 분명하다.',
            ],
            effects: { danger: 1, time: 2 },
          },
        },
      },
      choices: [
        {
          id: 'ask_duchene',
          label: '뒤셴에게 지워진 이유를 묻는다',
          keys: ['뒤셴', '지운', '이유', '묻는다'],
          once: true,
          check: {
            stat: '설득',
            tags: ['사교', '정보'],
            target: 14,
            label: '설득 판정',
            prompt: ['그는 두 번째 잔을 따르고, 자기 잔은 채우지 않는다.'],
          },
          outcomes: {
            crit: {
              text: [
                '"1894년 11월입니다." 그가 마침내 말한다. "제가 지우라고 했습니다."',
                '"측량병 넷을 서편에 보냈고, 셋이 돌아왔습니다. 돌아온 셋은 같은 말을 했어요."',
                '"자기들이 잰 거리가 매번 달랐다고. 같은 회랑을 세 번 재면 세 번 다 다르게 나온다고."',
                '"저는 그걸 열병이라고 기록했습니다. 그렇게 기록해야 파리에서 사람이 안 옵니다."',
                '그가 처음으로 자기 잔을 채운다. "그리고 그해 겨울에, 한 노인이 저를 찾아왔습니다."',
              ],
              effects: {
                clues: ['french_survey', 'the_sealers'],
                flags: { duchenetalked: true },
                san: -1,
                time: 3,
              },
            },
            success: {
              text: [
                '"측량병 넷을 보냈고 셋이 돌아왔습니다." 그가 잔을 본다.',
                '"돌아온 셋이 잰 거리가 서로 맞지 않았어요. 같은 회랑인데."',
                '"그래서 지웠습니다. 틀린 도면보다 없는 도면이 낫습니다."',
              ],
              effects: { clues: ['french_survey'], flags: { duchenetalked: true }, time: 3 },
            },
            partial: {
              text: [
                '"열병이었습니다." 그가 말한다. "여기서는 흔한 일이죠."',
                '흔한 일을 말하는 사람의 목소리가 아니다.',
              ],
              effects: { time: 3 },
            },
            fail: {
              text: [
                '"측량은 행정입니다. 행정에는 이유가 없고 결정만 있습니다."',
                '럼이 비었다. 그가 병을 치운다.',
              ],
              effects: { time: 3 },
            },
            fumble: {
              text: [
                '당신은 그의 기록이 거짓이라고 말했다.',
                '뒤셴이 오래 침묵한다. 그리고 아주 정중하게 문을 가리킨다.',
                '"영국인들은 늘 남의 나라 서류를 읽고 싶어 하더군요."',
              ],
              effects: { danger: 2, time: 3 },
            },
          },
        },
        {
          id: 'buy_kit',
          label: '측량대에서 밀림 장비를 얻는다',
          keys: ['장비', '벌목도', '키니네', '보급'],
          once: true,
          text: [
            '뒤셴이 창고를 연다. 벌목도 하나, 키니네 한 병, 그리고 낡은 측량도 사본.',
            '"값은 안 받겠습니다." 그가 말한다.',
            '"대신 돌아오시면 들러 주십시오. 무엇을 보셨는지 안 물어도 됩니다. ' +
              '돌아왔다는 것만 알면 됩니다."',
          ],
          effects: { items: ['벌목도', '키니네', '프랑스 측량도'], time: 2 },
        },
        {
          id: 'crane_letters',
          label: '크레인의 런던 도면과 대조한다',
          keys: ['크레인', '도면', '대조', '런던'],
          requires: { companions: ['crane'] },
          once: true,
          text: [
            '크레인이 가방에서 종이 뭉치를 꺼내 벽의 도면 옆에 나란히 편다.',
            '런던 박물관 지하 보관고의 반출 기록. 그리고 반출된 적 없는 물건들의 목록.',
            '"1894년." 그가 짚는다. "여기 서편 회랑의 부조 탁본이 세 장 들어옵니다. 반출자 불명."',
            '"그런데 이건 그해 겨울에 지웠다는 구역이죠."',
            '뒤셴이 두 도면을 번갈아 본다. 그리고 자기 럼을 마신다.',
            '"…누군가 지우기 전에 가져갔군요."',
          ],
          effects: {
            clues: ['french_survey', 'the_sealers'],
            companion: { id: 'crane', trust: 2, affinity: 1 },
            flags: { londonMatch: true },
            time: 3,
          },
        },
        {
          id: 'to_jungle',
          label: '보리수의 길로 향한다',
          keys: ['밀림', '출발', '떠난다', '보리수'],
          text: ['뒤셴이 방갈로 계단까지 따라 나온다. 아무 말도 하지 않는다.'],
          effects: { time: 3, goto: 'jungle_march' },
        },
      ],
      freeform: [
        {
          keys: ['럼', '마신다', '술'],
          text: [
            '럼은 미지근하고 지나치게 달다.',
            '뒤셴은 자기 잔을 채우지 않는다. 6년 동안 그 습관을 지켰을 것이다.',
          ],
          effects: { san: 1, time: 1 },
        },
      ],
    },

    // ── 3. 밀림 ────────────────────────────────────────────────
    jungle_march: {
      id: 'jungle_march',
      location: '앙코르 서편 · 보리수의 길',
      exits: ['주둔지', '서쪽 참배로'],
      onEnter(state, visits) {
        if (visits > 1) return { danger: -3 };
        return { danger: 1 };
      },
      body: (state) => {
        const out = [
          '밀림은 조용하지 않다. 매미와 새와 이름 모르는 것들이 층층이 운다.',
          '무서운 것은 그 소리가 아니라, 그것이 한꺼번에 멎는 순간이다.',
        ];
        if (state.companions.sokha?.present) {
          out.push(
            '속하가 앞장선다. 그녀는 나무를 보지 않고 발밑을 본다.',
            '"길은 위가 아니라 아래에 있습니다. 사람이 지나간 자리는 흙이 다릅니다."',
          );
        } else {
          out.push(
            '안내인 없이 들어온 밀림에서는 방향이 열 걸음마다 사라진다.',
            '나무는 전부 같은 나무처럼 보이고, 실제로 같은 나무일 때도 있다.',
          );
        }
        out.push(
          '한 시간쯤 걸었을 때, 나무 사이로 각진 것이 스친다.',
          '돌이다. 그리고 그 돌은 뿌리에 삼켜진 채로도 여전히 직선을 유지하고 있다.',
        );
        return out;
      },
      revisitBody: [
        '밀림은 같은 자리를 두 번 지나가는 것을 허락하지 않는다.',
        '어제의 길이 오늘은 조금 다르게 나 있다.',
      ],
      ambientCheck: {
        label: '길의 흔적을 읽는다',
        check: { stat: '탐험', tags: ['조사', '방향'], target: 13, label: '탐험 판정' },
        outcomes: {
          crit: {
            text: [
              '흙이 다른 자리가 한 줄로 이어진다. 사람이 지나간 자리다.',
              '한 사람이 아니다. 여럿이, 오랫동안, 같은 폭으로.',
              '그리고 그 줄은 회랑 쪽이 아니라 회랑을 빙 둘러 간다. 지키는 사람들의 순찰로다.',
            ],
            effects: { clues: ['banyan_road'], flags: { foundPatrolPath: true }, time: 2 },
          },
          success: {
            text: [
              '누군가 정기적으로 지나다니는 길이 있다.',
              '이 밀림에 그런 규칙적인 것이 있다는 사실 자체가 정보다.',
            ],
            effects: { clues: ['banyan_road'], time: 2 },
          },
          partial: {
            text: [
              '흔적은 있는데 방향이 읽히지 않는다.',
              '오는 길인지 가는 길인지 모르는 흔적은 절반만 쓸모 있다.',
            ],
            effects: { time: 2 },
          },
          fail: {
            text: ['밀림 바닥은 하루면 모든 것을 덮는다. 어제 것도 남지 않는다.'],
            effects: { time: 3 },
          },
          fumble: {
            text: [
              '흔적을 따라가다 개미 언덕을 밟는다.',
              '붉은개미가 정강이를 타고 오른다. 물을 찾아 30분을 뛰었다.',
            ],
            effects: { hp: -2, time: 3 },
          },
        },
      },
      choices: [
        {
          id: 'cut_through',
          label: '벌목도로 길을 낸다',
          keys: ['벌목도', '길을 낸', '자른다', '헤친다'],
          requires: { items: ['벌목도'] },
          check: {
            stat: '체력',
            tags: ['이동', '완력'],
            target: 12,
            label: '체력 판정',
            prompt: ['덩굴이 사람 팔 굵기다. 한 번에 하나씩 끊는 수밖에 없다.'],
          },
          outcomes: {
            crit: {
              text: [
                '리듬이 잡힌다. 어깨가 아니라 허리로 휘두르면 힘이 절반만 든다.',
                '한 시간 만에 참배로의 서쪽 끝이 나온다.',
              ],
              effects: { time: 2, goto: 'causeway' },
            },
            success: {
              text: ['땀이 눈에 들어간다. 그래도 길은 난다.'],
              effects: { hp: -1, time: 3, goto: 'causeway' },
            },
            partial: {
              text: [
                '덩굴 하나가 튕겨 얼굴을 친다. 뺨이 찢어진다.',
                '피가 턱까지 흐르는 채로 계속 휘두른다.',
              ],
              effects: { hp: -2, time: 4, goto: 'causeway' },
            },
            fail: {
              text: [
                '자른 자리마다 다른 덩굴이 내려온다.',
                '반나절을 쓰고 나서야 방향이 틀렸다는 것을 안다. 되짚어 다시 시작한다.',
              ],
              effects: { hp: -2, time: 6, danger: 1, goto: 'causeway' },
            },
            fumble: {
              text: [
                '벌목도가 나무가 아니라 벌집을 친다.',
                '다음 20분은 기억나지 않는다. 정신을 차렸을 때 물속에 서 있었다.',
                '참배로는 눈앞에 있었다. 어떻게 왔는지는 모른다.',
              ],
              effects: { hp: -4, san: -1, danger: 2, time: 6, goto: 'causeway' },
            },
          },
        },
        {
          id: 'follow_sokha',
          label: '속하의 길을 따라간다',
          keys: ['속하', '따라간다', '안내'],
          requires: { companions: ['sokha'] },
          once: true,
          text: [
            '속하가 벌목도를 쓰지 않는다. 대신 나무 사이의 빈틈만 골라 걷는다.',
            '"자르면 자국이 남습니다." 그녀가 말한다. "자국이 남으면 따라옵니다."',
            '두 시간 뒤, 나무가 끊기고 눈앞에 돌이 깔린 길이 나타난다.',
            '참배로다. 폭이 스무 걸음이고, 양쪽으로 나가(蛇)의 몸이 이어져 있다.',
          ],
          effects: {
            time: 4,
            companion: { id: 'sokha', trust: 1, affinity: 1 },
            flags: { quietApproach: true },
            goto: 'causeway',
          },
        },
        {
          id: 'jungle_camp',
          label: '해가 지기 전에 야영지를 만든다',
          keys: ['야영', '쉰다', '밤', '캠프'],
          once: true,
          hint: '회복하지만, 우기가 하루 가까워진다',
          text: [
            '덩굴을 걷어 바닥을 만들고, 젖은 나무로 연기를 피운다. 불보다 연기가 중요하다.',
            '밤의 밀림은 낮보다 시끄럽다. 시끄러운 동안은 오히려 안심이 된다.',
            '새벽 두 시, 소리가 한꺼번에 멎었다. 아무도 그 이야기를 꺼내지 않았다.',
          ],
          effects: (state) => ({
            hp: 4,
            san: 2,
            time: ticksUntil(state.tick, 6),
            danger: 1,
            companionChanges: [
              { id: 'sokha', affinity: 1 },
              { id: 'crane', trust: 1 },
            ],
          }),
        },
        {
          id: 'push_on',
          label: '방향만 잡고 밀고 나아간다',
          keys: ['밀고', '나아간다', '전진', '간다'],
          check: {
            stat: '탐험',
            tags: ['이동', '방향'],
            target: 14,
            label: '독도 판정',
            prompt: [
              '나침반은 여기서 두 번에 한 번 거짓말을 한다.',
              '해도 보이지 않는다. 남은 것은 감각과 지형뿐이다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '물이 흐르는 방향을 따라간다. 밀림에서 물은 늘 낮은 곳을 알고 있다.',
                '낮은 곳 끝에 돌이 깔린 참배로가 있었다.',
              ],
              effects: { time: 3, goto: 'causeway' },
            },
            success: {
              text: ['두 번 돌아 나오고 세 번째에 방향을 잡는다.'],
              effects: { hp: -1, time: 4, goto: 'causeway' },
            },
            partial: {
              text: [
                '해가 기울 때까지 걷는다. 밀림의 밤은 예고 없이 온다.',
                '참배로에 닿았을 때는 이미 손을 뻗어야 앞이 보였다.',
              ],
              effects: { hp: -2, time: 6, danger: 1, goto: 'causeway' },
            },
            fail: {
              text: [
                '같은 보리수를 세 번 지난다. 세 번째에 그것이 같은 나무라는 것을 인정한다.',
                '밤을 밀림에서 보냈다. 아무 일도 일어나지 않았고, 그것이 더 오래 남았다.',
              ],
              effects: { hp: -3, san: -2, time: 12, danger: 2, goto: 'causeway' },
            },
            fumble: {
              text: [
                '앞서가는 사람의 등을 따라 걷다가, 문득 그 사람이 누구인지 확인한다.',
                '아무도 없다. 일행은 전부 뒤에 있다.',
                '참배로에 닿았을 때 아무도 그 이야기를 꺼내지 않았다.',
              ],
              effects: { hp: -2, san: -3, danger: 2, time: 8, goto: 'causeway' },
            },
          },
        },
      ],
      freeform: [
        {
          keys: ['소리', '조용', '멎'],
          text: [
            '걸음을 멈추고 듣는다. 매미, 새, 물, 잎.',
            '전부 있다. 하나도 빠지지 않았다. 그런데도 무언가 빠진 것 같다.',
          ],
          effects: { san: -1 },
        },
        {
          keys: ['나무', '보리수', '뿌리'],
          text: [
            '보리수는 돌을 부수지 않는다. 감싼다.',
            '수백 년에 걸쳐 아주 천천히, 돌이 원래 자기 것이었다는 듯이.',
          ],
          effects: {},
        },
      ],
    },

    // ── 4. 참배로 ─────────────────────────────────────────────
    causeway: {
      id: 'causeway',
      location: '앙코르 서편 · 참배로',
      exits: ['밀림', '나가 회랑'],
      body: [
        '참배로는 폭이 스무 걸음이고, 양쪽으로 나가의 몸이 이어진다.',
        '난간이 아니라 뱀이다. 백 미터짜리 뱀 두 마리를 돌로 깎아 길 양옆에 눕혀 놓았다.',
        '머리는 저 끝에 있고, 머리에는 아홉 개의 목이 부챗살처럼 펼쳐져 있다.',
        '아홉. 당신은 그 수를 두 번 센다.',
      ],
      revisitBody: [
        '나가의 몸이 낮의 열을 머금고 있다. 손을 대면 미지근하다.',
        '아홉 개의 목은 그대로다.',
      ],
      ambientCheck: {
        label: '나가의 목을 센다',
        check: { stat: '지식', tags: ['해독', '신비'], target: 14, label: '지식 판정' },
        outcomes: {
          crit: {
            text: [
              '아홉이다. 그런데 앙코르의 나가는 일곱이다. 어디서나 일곱이다.',
              '가까이 가서 본다. 여덟 번째와 아홉 번째 목은 나중에 붙였다.',
              '돌의 색이 다르고, 조각의 손이 다르고, 이음매에 회반죽이 남아 있다.',
              '누군가 나중에 와서 둘을 더 세어 붙였다.',
            ],
            effects: { clues: ['eighth_gate'], san: -2, time: 2 },
          },
          success: {
            text: [
              '아홉이다. 앙코르의 나가는 일곱이어야 한다.',
              '둘은 나중에 붙였다. 색이 다르다.',
            ],
            effects: { clues: ['eighth_gate'], san: -1, time: 2 },
          },
          partial: {
            text: [
              '세다가 놓친다. 일곱이었다가 아홉이었다가.',
              '다시 세면 또 달라진다. 세는 것을 그만둔다.',
            ],
            effects: { san: -1, time: 2 },
          },
          fail: {
            text: ['돌은 돌이다. 목은 목이다. 아홉이든 일곱이든 뱀은 뱀이다.'],
            effects: { time: 2 },
          },
          fumble: {
            text: [
              '아홉 번째 목의 눈을 오래 들여다본다.',
              '돌에는 눈동자가 새겨져 있지 않다. 그런데 당신은 그것과 눈이 마주쳤다고 느낀다.',
            ],
            effects: { san: -3, time: 2 },
          },
        },
      },
      choices: [
        {
          id: 'rubbing_naga',
          label: '나가의 이음매를 탁본으로 뜬다',
          keys: ['탁본', '이음매', '뜬다', '베낀다'],
          once: true,
          check: {
            stat: '지식',
            tags: ['기록', '해독'],
            target: 13,
            label: '기록 판정',
            prompt: ['이음매의 회반죽 위에 새김이 있다. 회반죽에 새겼다는 것은 최근이라는 뜻이다.'],
          },
          outcomes: {
            crit: {
              text: [
                '종이 위에 선이 뜬다. 크메르 문자가 아니다. 숫자다.',
                '거리와 각도와 날짜. 그리고 마지막에 한 줄.',
                '"여덟 번째를 찾았다. 아홉 번째를 찾는 중이다."',
                '날짜는 1861년. 앙리 무오가 이 유적을 유럽에 알린 해다.',
              ],
              effects: {
                clues: ['eighth_gate', 'who_counts'],
                items: ['회랑 탁본첩'],
                san: -2,
                time: 3,
              },
            },
            success: {
              text: [
                '숫자가 뜬다. 거리와 각도와 날짜. 그리고 세는 기호.',
                '이 필체를 두 대륙에서 이미 봤다.',
              ],
              effects: { clues: ['eighth_gate'], items: ['회랑 탁본첩'], san: -1, time: 3 },
            },
            partial: {
              text: ['회반죽이 부스러진다. 절반만 떴다. 절반은 가루가 되어 날아갔다.'],
              effects: { time: 3 },
            },
            fail: {
              text: ['습기에 종이가 눅어 목탄이 먹지 않는다.'],
              effects: { time: 3 },
            },
            fumble: {
              text: [
                '문지르던 회반죽이 통째로 떨어진다.',
                '그 아래에 더 오래된 새김이 있다. 그리고 그것은 회반죽으로 덮여 있던 것이 아니라,',
                '회반죽이 덮으려다 실패한 것처럼 보인다.',
              ],
              effects: { clues: ['eighth_gate'], san: -2, danger: 1, time: 3 },
            },
          },
        },
        {
          id: 'crane_council',
          label: '크레인과 앞으로의 수를 정한다',
          keys: ['크레인과', '상의', '의논', '수를 정'],
          requires: { companions: ['crane'] },
          once: true,
          text: [
            '크레인이 나가의 몸에 걸터앉아 담배를 만다. 손이 능숙하고, 그래서 오래 걸린다.',
            '"묻고 싶은 게 있습니다." 그가 말한다. "당신은 저 안에서 뭘 하려는 겁니까."',
            '"열려는 겁니까, 아니면 확인하려는 겁니까."',
            '당신이 대답하기 전에 그가 손을 젓는다.',
            '"지금 대답하지 마십시오. 저 안에서 대답하시면 됩니다. 저는 그때 옆에 있겠습니다."',
            '"두 번이나 총을 겨눈 사람이 할 말은 아니지만."',
          ],
          effects: {
            companion: { id: 'crane', trust: 2, affinity: 1 },
            san: 2,
            flags: { craneCounsel: true },
            time: 2,
          },
        },
        {
          id: 'to_gallery',
          label: '회랑으로 들어간다',
          keys: ['회랑', '들어간다', '진입', '전진'],
          text: [
            '참배로 끝에서 회랑이 시작된다. 지붕이 있고, 그래서 안은 어둡다.',
            '벽 양면에 부조가 이어진다. 끝이 보이지 않는다.',
          ],
          effects: { time: 1, goto: 'naga_gallery' },
        },
        {
          id: 'back_jungle',
          label: '밀림으로 물러난다',
          keys: ['물러', '돌아간다', '후퇴'],
          text: ['당신은 참배로를 등진다. 나가의 아홉 목이 등 뒤에 남는다.'],
          effects: { time: 2, goto: 'jungle_march' },
        },
      ],
      freeform: [
        {
          keys: ['나가', '뱀', '만진다'],
          text: [
            '나가의 비늘은 손바닥으로 쓸면 결이 느껴진다.',
            '천 년 동안 비가 이 결을 깎았는데도 아직 결이 남아 있다.',
          ],
          effects: {},
        },
      ],
    },

    // ── 5. 나가 회랑 · 세 번째 기록 ──────────────────────────
    naga_gallery: {
      id: 'naga_gallery',
      location: '앙코르 서편 · 나가 회랑',
      exits: ['참배로', '아래로'],
      combat: 'sealkeepers_gallery',
      onEnter(state, visits) {
        if (visits > 1) return {};
        return { danger: 1 };
      },
      body: [
        '회랑은 길고 낮고 어둡다. 부조가 벽 양면을 끝까지 채운다.',
        '군대의 행렬, 배, 물고기, 춤추는 사람들. 익숙한 것들이다.',
        '그러다 한 지점에서 조각의 손이 바뀐다.',
        '당신은 이 감각을 두 번 겪었다. 룩소르에서 한 번, 두 강 사이에서 한 번.',
      ],
      revisitBody: [
        '회랑은 조용하다. 부조는 여전히 벽 양면을 채우고 있다.',
        '조각의 손이 바뀌는 지점은 여전히 거기 있다.',
      ],
      choices: [
        {
          id: 'gallery_leave',
          label: '회랑을 지나 아래로 내려간다',
          keys: ['아래로', '내려간다', '지나간다'],
          text: ['회랑 끝에서 계단이 아래로 꺾인다.'],
          effects: { goto: 'star_chamber' },
        },
      ],
    },

    // ── 6. 별의 방 ────────────────────────────────────────────
    star_chamber: {
      id: 'star_chamber',
      location: '회랑 아래 · 별의 방',
      exits: ['회랑', '문'],
      onEnter(state, visits) {
        if (visits > 1) return {};
        return { danger: 1, san: -1 };
      },
      body: (state) => {
        const out = [
          '방은 원형이다. 지름이 눈에 익다.',
          '천장은 돔이고, 그 안쪽에 금속 조각이 박혀 있다. 별이다.',
        ];
        if (state.clues.includes('wrong_sky')) {
          out.push(
            '당신은 이제 세지 않아도 안다. 오리온의 위치가 룩소르의 돔, ',
            '두 강 사이의 돔과 정확히 같다. 세 개의 천장이 같은 밤을 새기고 있다.',
            '만 이천 년 전의 같은 밤을.',
          );
        } else {
          out.push('별자리의 배열이 지금의 하늘과 맞지 않는다. 한참 어긋나 있다.');
        }
        out.push(
          '방 한쪽 벽에 문이 있다. 문 위의 원반은 세 곳 중 가장 크다.',
          '그리고 원반 둘레의 띠에, 문을 세는 기호가 새겨져 있다.',
          '세어 본다. 여덟.',
        );
        if (state.flags.sealersAllied) {
          out.push(
            '노인이 뒤에서 조용히 말한다. "저희는 일곱까지만 알고 있었습니다."',
            '"여덟 번째는 1861년에 나타났습니다. 우리가 새긴 것이 아닙니다."',
          );
        }
        return out;
      },
      revisitBody: [
        '별의 방은 그대로다. 천장의 금속 조각이 램프를 받아 아주 느리게 반짝인다.',
        '문 위의 원반도 그대로다.',
      ],
      ambientCheck: {
        label: '세 천장을 대조한다',
        check: { stat: '지식', tags: ['해독', '신비'], target: 15, label: '천문 판정' },
        outcomes: {
          crit: {
            text: [
              '수첩을 펴고 세 장의 스케치를 나란히 놓는다. 룩소르, 수메르, 앙코르.',
              '별의 위치가 세 곳에서 완전히 일치한다. 오차가 없다.',
              '오차가 없다는 것이 문제다. 손으로 새긴 것에는 오차가 있어야 한다.',
              '세 대륙에서, 천 년씩 어긋난 시대에, 오차 없이 같은 하늘을 새기려면 —',
              '새긴 사람이 그 하늘을 직접 보고 있었어야 한다. 세 번 다.',
            ],
            effects: { clues: ['who_counts', 'third_record'], san: -2, time: 2 },
          },
          success: {
            text: [
              '세 천장의 별이 같은 자리에 있다. 오차 없이.',
              '손으로 새긴 것에 오차가 없다는 것은, 보고 새겼다는 뜻이다.',
            ],
            effects: { clues: ['third_record'], san: -2, time: 2 },
          },
          partial: {
            text: [
              '같은 별자리인 것은 알겠다. 정확히 같은지는 도구 없이 확인할 수 없다.',
              '확인할 수 없다는 사실이 오히려 다행스럽다.',
            ],
            effects: { san: -1, time: 2 },
          },
          fail: {
            text: ['천장은 너무 높고 램프는 너무 약하다. 별은 반짝이기만 한다.'],
            effects: { time: 2 },
          },
          fumble: {
            text: [
              '천장을 올려다보다 중심을 잃는다.',
              '넘어지는 짧은 순간, 위가 아래 같고 돔이 바닥 같다.',
              '일어났을 때 무릎이 까졌고, 방향 감각이 한동안 돌아오지 않았다.',
            ],
            effects: { hp: -1, san: -2, time: 2 },
          },
        },
      },
      choices: [
        {
          id: 'read_third',
          label: '세 대륙의 기록을 나란히 놓는다',
          keys: ['나란히', '세 대륙', '대조', '증명'],
          requires: { clues: ['first_civilization'] },
          hideIfLocked: true,
          once: true,
          hint: '두 곳은 우연일 수 있다. 세 곳은 아니다',
          check: {
            stat: '지식',
            tags: ['해독', '기록'],
            target: 14,
            label: '추론 판정',
            prompt: [
              '두 강 사이에서 당신은 두 기록을 겹쳐 놓고 하나의 문장을 얻었다.',
              '그때 세라피나가 말했다. 증명이 되려면 하나가 더 필요하다고.',
              '지금 그 하나가 손에 있다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '세 장을 나란히 놓는다. 이집트의 아래층 문자, 수메르의 왕 목록, 그리고 이 회랑의 숫자.',
                '같은 자리에서 끊기고, 같은 손이 이어 붙였다.',
                '이제 이것은 인상이 아니라 자료다. 자료는 반박당할 수 있고, 반박당할 수 있는 것만이 사실이다.',
                '문은 나가는 문이 아니었다. 들어오는 문이었다.',
                '일곱 번 열렸고 일곱 번 닫혔다. 그때마다 세계는 처음부터 다시 시작했다.',
                '그리고 우리는 여덟 번째 앞에 서 있다.',
              ],
              effects: { clues: ['third_record', 'final_truth', 'who_counts'], san: -2, time: 3 },
            },
            success: {
              text: [
                '세 기록이 같은 자리에서 끊기고 같은 손이 이어 붙였다.',
                '두 곳은 우연일 수 있다. 세 곳은 아니다.',
                '이제 이것은 증명할 수 있는 것이 되었다.',
              ],
              effects: { clues: ['third_record', 'final_truth'], san: -2, time: 3 },
            },
            partial: {
              text: [
                '세 장이 닮았다는 것까지는 확실하다.',
                '그러나 손이 떨려 선이 겹쳐 보인다. 조금 뒤에 다시 봐야 한다.',
              ],
              effects: { clues: ['third_record'], san: -1, time: 3 },
            },
            fail: {
              text: [
                '램프 아래에서 세 장을 몇 번이나 바꿔 놓는다.',
                '연결은 보이는데 말로 옮겨지지 않는다. 말로 옮겨지지 않는 것은 아직 증명이 아니다.',
              ],
              effects: { time: 3 },
            },
            fumble: {
              text: [
                '세 장을 겹쳐 놓고 보다가, 네 번째 자리가 비어 있다는 것을 깨닫는다.',
                '비어 있는 것이 아니라, 아직 안 채워진 것처럼 보인다.',
                '누가 채우는지 생각하지 않으려 애쓴다.',
              ],
              effects: { clues: ['third_record'], san: -3, time: 3 },
            },
          },
        },
        {
          id: 'ask_sealers',
          label: '봉인단에게 무엇을 지켜 왔는지 묻는다',
          keys: ['봉인단', '노인', '묻는다', '지켜'],
          requires: { flags: { sealersAllied: true } },
          hideIfLocked: true,
          once: true,
          text: [
            '노인이 벽에 등을 대고 앉는다. 오래 서 있었던 사람의 앉는 방식이다.',
            '"저희는 여는 방법을 모릅니다." 그가 말한다. "한 번도 안 적이 없으니까요."',
            '"저희가 아는 건 닫는 방법뿐입니다. 그것도 전해 들은 거고요."',
            '"이집트에 하나, 두 강 사이에 하나, 여기 하나. 서로 만난 적은 없습니다."',
            '"같은 날 같은 말을 배웠을 뿐입니다. 그게 몇 대 전인지는 아무도 모릅니다."',
            '그가 당신을 본다. "당신은 셋을 다 봤군요. 우리 중 누구도 못 한 일입니다."',
            '"그래서 겁이 납니다."',
          ],
          effects: { clues: ['the_sealers', 'eighth_gate'], san: -1, time: 2 },
        },
        {
          id: 'chamber_breathe',
          label: '벽에 등을 대고 숨을 고른다',
          keys: ['숨', '쉰다', '진정', '앉는다'],
          once: true,
          hint: '시간과 위험을 내주고 정신을 되찾는다',
          text: (state) => {
            const out = [
              '돔 아래에 앉는다. 별이 천장에 박힌 채로 움직이지 않는다.',
              '열까지 센다. 스물까지 센다. 손의 떨림이 조금 줄어든다.',
            ];
            const ally = Object.values(state.companions).find((c) => c.present);
            if (ally) {
              out.push(
                `${subj(ally.name)} 옆에서 같은 자세로 선다. 아무 말도 하지 않는다.`,
                '그것이 지금 할 수 있는 가장 친절한 일이라는 것을, 둘 다 알고 있다.',
              );
            } else {
              out.push('아무도 없다. 세는 소리도 당신 것뿐이다.');
            }
            return out;
          },
          effects: { san: 5, time: 2, danger: 1 },
        },
        {
          id: 'read_ceiling',
          label: '천장의 별을 세 번째로 읽는다',
          keys: ['천장', '별을 읽', '별자리', '대조'],
          hint: '앞의 두 돔과 같은지 확인한다',
          check: {
            stat: '지식',
            tags: ['해독', '신비'],
            target: 15,
            label: '천문 판정',
            prompt: [
              '램프를 최대한 높이 든다. 돔은 여전히 멀다.',
              '오리온을 먼저 찾는다. 세 번째로 찾는 것이라 손이 먼저 방향을 안다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '수첩을 펴고 세 장의 스케치를 나란히 놓는다. 룩소르, 수메르, 앙코르.',
                '별의 위치가 세 곳에서 완전히 일치한다. 오차가 없다.',
                '오차가 없다는 것이 문제다. 손으로 새긴 것에는 오차가 있어야 한다.',
                '세 대륙에서, 천 년씩 어긋난 시대에, 오차 없이 같은 하늘을 새기려면 —',
                '새긴 사람이 그 하늘을 직접 보고 있었어야 한다. 세 번 다.',
              ],
              effects: { clues: ['who_counts', 'third_record'], san: -2, time: 2 },
            },
            success: {
              text: [
                '세 천장의 별이 같은 자리에 있다. 오차 없이.',
                '손으로 새긴 것에 오차가 없다는 것은, 보고 새겼다는 뜻이다.',
              ],
              effects: { clues: ['third_record'], san: -2, time: 2 },
            },
            partial: {
              text: [
                '같은 별자리인 것은 알겠다. 정확히 같은지는 도구 없이 확인할 수 없다.',
                '확인할 수 없다는 사실이 오히려 다행스럽다. 다시 볼 수는 있다.',
              ],
              effects: { san: -1, time: 2 },
            },
            fail: {
              text: [
                '천장은 너무 높고 램프는 너무 약하다. 별은 반짝이기만 한다.',
                '팔을 내리고 잠시 쉰다. 다시 들 수는 있다.',
              ],
              effects: { time: 2 },
            },
            fumble: {
              text: [
                '천장을 올려다보다 중심을 잃는다.',
                '넘어지는 짧은 순간, 위가 아래 같고 돔이 바닥 같다.',
                '일어났을 때 무릎이 까졌고, 방향 감각이 한동안 돌아오지 않았다.',
              ],
              effects: { hp: -1, san: -2, time: 2 },
            },
          },
        },
        {
          id: 'record_chamber',
          label: '별의 방을 기록으로 남긴다',
          keys: ['기록', '스케치', '남긴다', '그린다'],
          once: true,
          check: {
            stat: '지식',
            tags: ['기록'],
            target: 12,
            label: '기록 판정',
            prompt: ['손이 떨린다. 떨리는 손으로도 선은 그을 수 있다.'],
          },
          outcomes: {
            crit: {
              text: [
                '돔의 별을 좌표로 옮긴다. 램프를 세 위치에 놓고 그림자로 각도를 잡는다.',
                '완성된 도면은 당신이 그린 것 중 가장 정확하다.',
                '이 종이 한 장이면, 누구든 이 방을 다시 찾을 수 있다.',
              ],
              effects: { items: ['회랑 탁본첩'], flags: { chamberRecorded: true }, time: 2 },
            },
            success: {
              text: ['별의 배열과 문의 위치를 옮겨 적는다. 나중에 쓸 수 있을 만큼은 된다.'],
              effects: { flags: { chamberRecorded: true }, time: 2 },
            },
            partial: {
              text: ['절반쯤 그리다 램프가 흔들린다. 남은 절반은 기억으로 채워야 한다.'],
              effects: { time: 2 },
            },
            fail: {
              text: ['그린 것을 다시 보니 앞뒤가 맞지 않는다. 찢는다.'],
              effects: { time: 2 },
            },
            fumble: {
              text: [
                '한참을 그리다 손을 멈춘다.',
                '종이 위의 것은 이 방이 아니다. 다른 방이다. 본 적 없는 방이다.',
                '그리고 그것을 그린 것은 분명히 당신의 손이다.',
              ],
              effects: { san: -3, time: 2 },
            },
          },
        },
        {
          id: 'to_door',
          label: '문 앞으로 나아간다',
          keys: ['문', '앞으로', '나아간다', '다가간다'],
          hint: '되돌릴 수 없다',
          text: [
            '문까지 열 걸음. 걷는 동안 아무도 말하지 않는다.',
            '원반이 가까워질수록 공기가 차가워진다. 그리고 아주 미세하게 달다.',
            '이 냄새를 세 번째로 맡는다.',
          ],
          effects: { time: 1, goto: 'the_door' },
        },
      ],
      freeform: [
        {
          keys: ['별', '천장', '올려다'],
          text: [
            '천장의 별을 올려다본다. 세 번째 돔이다.',
            '이제는 세지 않는다. 세면 같을 것을 알고, 같으면 무슨 뜻인지도 안다.',
          ],
          effects: { san: -1 },
        },
      ],
    },

    // ── 7. 여덟 번째 문 ──────────────────────────────────────
    the_door: {
      id: 'the_door',
      location: '회랑 아래 · 여덟 번째 문',
      exits: ['별의 방'],
      nonLethal: true, // 여기까지 온 사람은 자기 결말을 본다
      onEnter(state, visits) {
        if (visits > 1) return {};
        return { danger: 1, san: -1 };
      },
      body: (state) => {
        const out = [
          '문 앞이다.',
          '원반은 사람 키의 두 배다. 손을 대면 차갑고, 떼어도 차가움이 팔에 남는다.',
        ];
        if (state.clues.includes('final_truth')) {
          out.push(
            '당신은 이제 이것이 무엇인지 안다.',
            '나가는 문이 아니라 들어오는 문이다. 일곱 번 열렸고 일곱 번 닫혔다.',
            '그때마다 세계는 처음부터 다시 시작했다.',
          );
        } else {
          out.push(
            '무엇인지는 아직 모른다. 다만 세 대륙에서 같은 것을 보았고,',
            '그 셋이 우연이 아니라는 것만은 안다.',
          );
        }
        const hasBoth =
          state.inventory.some((i) => i.name === '검은 태양의 열쇠') &&
          state.inventory.some((i) => i.name === '문의 각인');
        if (hasBoth) {
          out.push(
            '가방 속에서 두 조각이 서로를 향해 기울어 있다.',
            '이집트의 열쇠와 두 강 사이의 각인. 맞물리면 자물쇠가 된다.',
          );
        }
        out.push('선택은 셋이다. 그리고 셋 다 되돌릴 수 없다.');
        return out;
      },
      revisitBody: ['문은 그대로다. 문은 언제나 그대로다.'],
      choices: [
        {
          id: 'steady_together',
          label: '결정하기 전에 동행을 돌아본다',
          keys: ['동행', '돌아본다', '함께', '이야기'],
          once: true,
          hint: '여기까지 함께 온 사람들이 있다',
          text: (state) => {
            const here = Object.values(state.companions).filter((c) => c.present);
            if (!here.length) {
              return [
                '뒤를 돌아본다. 아무도 없다.',
                '세 대륙을 건너오는 동안 하나씩 줄었고, 마지막 열 걸음은 혼자다.',
                '그래도 여기까지 왔다. 그것을 두 번 되뇐다.',
              ];
            }
            const out = ['뒤를 돌아본다.'];
            for (const c of here) {
              if (c.id === 'crane') {
                out.push('"저는 두 번 틀렸습니다." 크레인이 말한다. "세 번째는 안 틀리겠습니다."');
              } else if (c.id === 'sokha') {
                out.push('속하가 고개를 끄덕인다. "여기 있겠습니다. 어느 쪽이든."');
              } else if (c.id === 'seraphina') {
                out.push('세라피나는 아무 말도 하지 않는다. 대신 수첩을 펴서 받아 적을 준비를 한다.');
              } else {
                out.push(`${subj(c.name)} 한 걸음 앞으로 나선다. 그것이 대답이다.`);
              }
            }
            out.push('아무도 재촉하지 않고 아무도 말리지 않는다. 이 결정이 당신 것이라는 데 모두가 동의한 얼굴들이다.');
            out.push('숨이 한 번 깊게 들어온다.');
            return out;
          },
          // 곁에 남은 사람 수만큼 버틸 힘이 돌아온다.
          // 세 대륙을 지나며 관계를 지킨 플레이어가 마지막 문 앞에서 그 값을 받는다.
          effects: (state) => {
            const here = Object.values(state.companions).filter((c) => c.present).length;
            return { san: 2 + here * 2 };
          },
        },
        {
          id: 'read_final',
          label: '결정하기 전에 원반을 끝까지 읽는다',
          keys: ['읽는다', '원반을 읽', '문장', '해독'],
          hint: '알고 고르는 것과 모르고 고르는 것은 다르다',
          check: {
            stat: '신비',
            tags: ['신비', '해독'],
            target: 15,
            label: '신비 판정',
            prompt: [
              '원반 둘레의 띠를 따라 문장이 이어진다. 세 곳 중 가장 길다.',
              '읽고 나면 되돌릴 수 없다는 예감이 먼저 온다. 그 예감도 세 번째다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '문장이 끝까지 읽힌다.',
                '문은 나가는 문이 아니다. 들어오는 문이다.',
                '일곱 번 열렸고 일곱 번 닫혔다. 그때마다 세계는 처음부터 다시 시작했다.',
                '닫은 것은 매번 사람이었다. 여는 것은 매번 사람이 아니었다.',
                '마지막 줄은 짧다. — "우리는 여섯 번째였다. 다음은 너희다."',
              ],
              effects: { clues: ['final_truth', 'who_counts', 'eighth_gate'], san: -3, time: 2 },
            },
            success: {
              text: [
                '문은 나가는 문이 아니라 들어오는 문이다.',
                '일곱 번 열렸고 일곱 번 닫혔다. 닫은 것은 매번 사람이었다.',
                '그리고 여덟 번째 앞에 지금 당신이 서 있다.',
              ],
              effects: { clues: ['final_truth'], san: -2, time: 2 },
            },
            partial: {
              text: [
                '절반쯤 읽고 눈을 뗀다. 뗀 것이 아니라 떼어졌다.',
                '읽은 절반만으로도 방향은 안다. 다시 볼 수는 있다.',
              ],
              effects: { clues: ['eighth_gate'], san: -2, time: 2 },
            },
            fail: {
              text: [
                '문장이 읽히다가 흩어진다. 배운 어떤 체계와도 맞지 않는 구간이 나온다.',
                '오래 본 대가로 눈 안쪽이 아프다. 다시 볼 수는 있다.',
              ],
              effects: { time: 2 },
            },
            fumble: {
              text: [
                '읽는 동안 당신의 입이 움직인다. 소리는 나지 않는다.',
                '멈추려 하는데 멈춰지지 않는다. 누군가 당신의 턱을 붙잡고 나서야 멎었다.',
                '붙잡은 손을 보니, 그 손도 떨고 있었다.',
              ],
              effects: { clues: ['final_truth'], san: -4, danger: 2, time: 2 },
            },
          },
        },
        {
          id: 'seal_gate',
          label: '문을 봉인한다',
          keys: ['봉인', '닫는다', '잠근다'],
          requires: { items: ['검은 태양의 열쇠', '문의 각인'] },
          hideIfLocked: true,
          hint: '두 조각이 자물쇠가 된다',
          check: {
            stat: '의지',
            tags: ['신비', '공포'],
            target: 15,
            label: '의지 판정',
            prompt: [
              '두 조각을 맞물린다. 소리 없이, 저항 없이.',
              '원반의 중심에 홈이 있다. 크기가 정확히 맞는다.',
              '끼우는 데 필요한 것은 힘이 아니라, 끼우고 나서 손을 떼는 일이다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '자물쇠가 들어가고, 한 번 돌아간다.',
                '회랑 전체가 숨을 내쉰다. 그리고 아무 소리도 나지 않는다.',
                '손을 뗀다. 뗄 수 있다.',
              ],
              effects: {
                flags: { gateSealed: true, sealedClean: true },
                clues: ['final_truth'],
                san: -2,
                goto: 'angkor_finale',
              },
            },
            success: {
              text: [
                '자물쇠가 들어간다. 돌리는 데 두 손이 다 필요했다.',
                '돌아가는 순간 손목까지 감각이 사라졌다가 천천히 돌아온다.',
                '문은 닫힌 채로 남았다.',
              ],
              effects: {
                flags: { gateSealed: true },
                san: -2,
                hp: -2,
                goto: 'angkor_finale',
              },
            },
            partial: {
              text: [
                '자물쇠가 반쯤 들어가고 멈춘다.',
                '온 힘으로 밀어 넣는다. 들어간다. 다만 무언가가 반대편에서 밀고 있었다는 감각이 남는다.',
              ],
              effects: {
                flags: { gateSealed: true },
                san: -3,
                hp: -3,
                goto: 'angkor_finale',
              },
            },
            fail: {
              text: [
                '손이 원반에서 떨어지지 않는다.',
                '자물쇠는 들어갔다. 그러나 손을 빼는 데 살갗이 남았다.',
                '문은 닫혔고, 당신의 손바닥에는 원의 자국이 남았다.',
              ],
              effects: {
                flags: { gateSealed: true },
                hp: -5,
                san: -3,
                goto: 'angkor_finale',
              },
            },
            fumble: {
              text: [
                '자물쇠를 끼우는 순간, 반대편에서 무언가가 그것을 붙잡는다.',
                '당신은 놓지 않았다. 그것도 놓지 않았다.',
                '얼마나 그러고 있었는지 모른다. 먼저 놓은 쪽은 저쪽이었다.',
                '문은 닫혔다. 당신은 그 뒤로 왼손을 오래 쓰지 못했다.',
              ],
              effects: {
                flags: { gateSealed: true, sealedHard: true },
                hp: -6,
                san: -5,
                goto: 'angkor_finale',
              },
            },
          },
        },
        {
          id: 'open_gate',
          label: '문을 연다',
          keys: ['연다', '열어', '민다'],
          hint: '문장이 말한 대로. 미는 것이 아니라 기다리는 것',
          check: {
            stat: '신비',
            tags: ['신비', '공포'],
            target: 16,
            label: '신비 판정',
            prompt: [
              '손바닥을 원반에 댄다. 밀지 않는다.',
              '문을 여는 자는 밖에서 오지 않는다. 그러니 이쪽에서 할 수 있는 일은 기다리는 것뿐이다.',
              '차가움이 팔을 타고 올라온다. 어깨에서 멈추지 않는다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '문이 열린다. 안쪽에서, 아주 부드럽게.',
                '그리고 당신은 끝까지 서 있었다. 그것이 이 판정의 전부였다.',
              ],
              effects: {
                flags: { gateOpened: true, stoodFirm: true },
                clues: ['final_truth', 'who_counts'],
                san: -4,
                goto: 'angkor_finale',
              },
            },
            success: {
              text: [
                '문이 안쪽으로 물러난다. 경첩도 도르래도 없이.',
                '당신은 한 걸음 물러섰다. 물러선 것을 부끄러워하지 않기로 한다.',
              ],
              effects: {
                flags: { gateOpened: true },
                clues: ['final_truth'],
                san: -5,
                goto: 'angkor_finale',
              },
            },
            partial: {
              text: [
                '문이 손가락 두 마디쯤 열리다 멈춘다.',
                '그 틈으로 공기가 빠져나간다. 아니, 빨려 들어간다.',
                '당신은 손을 뗀다. 문은 그 상태로 남는다. 닫히지도 열리지도 않은 채로.',
              ],
              effects: {
                flags: { gateAjar: true },
                san: -4,
                danger: 2,
                goto: 'angkor_finale',
              },
            },
            fail: {
              text: [
                '아무 일도 일어나지 않는다.',
                '당신은 오래 서 있었고, 문은 오래 문이었다.',
                '손을 떼고 나서야 손바닥이 얼어 감각이 없다는 것을 안다.',
              ],
              effects: { hp: -3, san: -3, goto: 'angkor_finale' },
            },
            fumble: {
              text: [
                '문이 열린다. 당신이 연 것이 아니다.',
                '안쪽에서, 무언가 나오려다 마음을 바꾼 것처럼 다시 닫힌다.',
                '그 짧은 사이에 당신은 보았다. 회랑. 그리고 회랑 저편에서 무언가를 적고 있는 형태.',
                '그것은 고개를 들지 않았다. 들 필요가 없었기 때문이다.',
              ],
              effects: {
                flags: { gateOpened: true, sawTheScribe: true },
                clues: ['who_counts', 'final_truth'],
                san: -7,
                goto: 'angkor_finale',
              },
            },
          },
        },
        {
          id: 'walk_away',
          label: '건드리지 않고 돌아선다',
          keys: ['돌아선다', '떠난다', '나간다', '건드리지'],
          hint: '가지고 나온 것만이 당신의 것이 된다',
          text: (state) => {
            const out = ['당신은 문에서 등을 돌린다.'];
            if (state.flags.gateSealed || state.flags.gateOpened) {
              out.push('이미 한 일은 되돌릴 수 없다. 다만 더 하지 않기로 한다.');
            } else {
              out.push(
                '세 대륙을 건너 여기까지 왔고, 마지막 열 걸음을 걷지 않기로 한다.',
                '그것이 오늘 한 일 중 가장 어려운 일이었다.',
              );
            }
            return out;
          },
          effects: { san: 2, goto: 'angkor_finale' },
        },
      ],
      freeform: [
        {
          keys: ['원반', '만진다', '손을 댄'],
          text: [
            '원반에 손끝만 댄다. 세 대륙에서 같은 것을 만졌다.',
            '차가움의 정도까지 같다. 재료가 같다는 뜻이고, 재료가 같다는 것은 —',
            '거기까지 생각하고 손을 뗀다.',
          ],
          effects: { san: -2 },
        },
        {
          keys: ['동행', '본다', '돌아본'],
          text: [
            '뒤를 돌아본다. 여기까지 함께 온 사람들이 당신을 보고 있다.',
            '아무도 재촉하지 않는다. 아무도 말리지도 않는다.',
            '이 결정이 당신 것이라는 데 모두가 동의한 얼굴들이다.',
          ],
          effects: { san: 1 },
        },
      ],
    },

    // ── 8. 마무리 ────────────────────────────────────────────
    angkor_finale: {
      id: 'angkor_finale',
      location: '앙코르 서편 · 회랑 바깥',
      exits: [],
      onEnter(state) {
        return { danger: -5, flags: { reachedEnd: true } };
      },
      body: (state) => {
        const out = [
          '밀림은 당신이 들어갈 때와 똑같이 시끄럽다.',
          '매미, 새, 이름 모르는 것들. 아무것도 달라지지 않았다.',
        ];
        if (state.flags.gateSealed) {
          out.push('등 뒤의 회랑에서는 이제 아무 소리도 나지 않는다. 그것만 달라졌다.');
        } else if (state.flags.gateOpened) {
          out.push(
            '등 뒤의 회랑에서 아주 낮은 소리가 계속 난다.',
            '아무도 그것을 언급하지 않고, 아무도 걸음을 늦추지 않는다.',
          );
        } else if (state.flags.gateAjar) {
          out.push('문은 반쯤 열린 채로 남았다. 그 사실을 아는 사람은 여기 있는 사람들뿐이다.');
        } else {
          out.push('회랑은 당신이 들어가기 전과 같은 상태로 남았다. 그것도 하나의 결정이다.');
        }
        return out;
      },
      choices: [
        {
          id: 'final_log',
          label: '수첩에 마지막 기록을 남긴다',
          keys: ['수첩', '기록', '적는다'],
          once: true,
          text: (state) => {
            const lines = ['참배로의 돌 위에 앉아 수첩을 편다. 연필이 짧아졌다.'];
            if (state.clues.includes('final_truth')) {
              lines.push(
                '한 문장을 적는다. — 문은 나가는 문이 아니었다.',
                '그리고 그 아래에 날짜를 적는다. 1897년 12월 19일.',
                '날짜를 적으면서, 그것이 누군가에게는 세어지는 숫자라는 생각이 든다.',
              );
            } else if (state.clues.includes('third_record')) {
              lines.push('한 문장을 적는다. — 세 곳에서 같은 손을 보았다.');
            } else {
              lines.push(
                '적을 것이 많은데 손이 움직이지 않는다.',
                '결국 날짜만 적고 덮는다.',
              );
            }
            return lines;
          },
          effects: { san: 3 },
        },
        {
          id: 'settle_all',
          label: '동행에게 셈을 치른다',
          keys: ['셈', '보수', '인사', '고맙'],
          once: true,
          text: (state) => {
            const out = [];
            if (state.companions.sokha?.present) {
              out.push(
                '속하는 봉투를 받고 세지 않는다. 대신 도면을 꺼내 서편 구역에 선을 긋는다.',
                '"이제 여기 있습니다." 그녀가 말한다. "지워진 채로 두지는 않겠습니다."',
              );
            }
            if (state.companions.crane?.present) {
              out.push(
                '크레인은 악수를 청하지 않는다. 대신 담배를 하나 말아 건넨다.',
                '"두 번 겨눴던 사람한테서 받는 건 좀 그렇겠지만." 그가 어깨를 으쓱한다.',
                '"그래도 세 번째는 옆에 서 있었습니다. 그걸로 셈은 됐다고 칩시다."',
              );
            }
            if (state.companions.seraphina?.present) {
              out.push(
                '세라피나는 이미 탁본을 정리하고 있다. 순서대로, 대륙별로.',
                '"12년을 기다렸고, 석 달 만에 다 봤습니다." 그녀가 고개를 든다.',
                '"이제 뭘 해야 할지 모르겠어요. 그건 좋은 문제죠."',
              );
            }
            if (!out.length) out.push('셈을 치를 사람이 없다. 당신은 혼자 돌 위에 앉아 있다.');
            return out;
          },
          effects: {
            san: 2,
            companionChanges: [
              { id: 'sokha', affinity: 1 },
              { id: 'crane', affinity: 1 },
              { id: 'seraphina', affinity: 1 },
              { id: 'nadia', affinity: 1 },
              { id: 'finch', affinity: 1 },
              { id: 'basim', affinity: 1 },
            ],
          },
        },
        {
          id: 'go_public',
          label: '학회에 전부 공개하기로 한다',
          keys: ['공개', '학회', '발표', '알린다'],
          requires: { clues: ['third_record'] },
          hideIfLocked: true,
          once: true,
          hint: '증거가 있어야 할 수 있는 결정이다',
          text: (state) => {
            const out = [
              '당신은 탁본첩을 무릎에 올려놓고 오래 본다.',
              '숨기는 편이 안전하다. 안전한 것과 옳은 것이 같지 않을 때가 있다.',
            ];
            if (state.companions.crane?.present) {
              out.push(
                '"학회는 웃을 겁니다." 크레인이 말한다. "제가 웃는 쪽에 있어 봐서 압니다."',
                '"그래도 기록에는 남습니다. 기록에 남으면, 다음 사람이 처음부터 시작하지 않아도 되고요."',
              );
            }
            if (state.flags.sealersAllied) {
              out.push(
                '노인은 반대하지 않는다. 다만 이렇게 말한다.',
                '"이름은 빼 주십시오. 저희 일은 알려지면 못 하는 일이라서요."',
              );
            }
            out.push('당신은 결정한다.');
            return out;
          },
          effects: { flags: { wentPublic: true }, san: 1 },
        },
        {
          id: 'end_campaign',
          label: '돌아가는 배를 탄다',
          keys: ['배', '돌아간다', '떠난다', '마친다'],
          text: ['호수까지 사흘. 사이공까지 열흘. 런던까지는 세지 않기로 한다.'],
          effects: { goto: 'angkor_epilogue' },
        },
      ],
      freeform: [
        {
          keys: ['하늘', '해', '아침'],
          text: [
            '해가 보리수 위로 올라온다. 세 번째다.',
            '유적에서 나와 아침을 보는 것이.',
            '이번에는 네 번째가 없을 것이라는 예감이 든다. 그것이 안심인지 아쉬움인지는 모르겠다.',
          ],
          effects: { san: 1 },
        },
      ],
    },

    // 결말 — 본문은 endings.js 가 상태를 읽어 채운다.
    angkor_epilogue: {
      id: 'angkor_epilogue',
      location: '톤레사프 · 돌아가는 배',
      exits: [],
      ending: true,
      body: [
        '배가 호수를 가로지른다. 물이 빠지는 철이라 수면이 낮고, 낮은 만큼 하늘이 넓다.',
      ],
      choices: [],
    },
  },
};

export default ep;
