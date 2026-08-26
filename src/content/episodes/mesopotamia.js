// 에피소드 2 — 두 강 사이의 문
// 바스라에서 습지로, 지구라트의 서고를 지나 물 아래의 문까지.
//
// 이 에피소드는 에피소드 1의 결과를 읽는다.
//   flags.craneAlly / craneHasTablet / escapedClean — 크레인과의 관계
//   companions.nadia / finch — 누가 따라왔는가
//   clues.not_first / black_sun / door_opener / wrong_sky — 무엇을 알고 왔는가
//
// 그리고 이집트의 단서와 이곳의 단서가 만나야만 열리는 결론이 하나 있다.

import { subj } from '../../korean.js';
import { CLUE_TITLES } from '../clues.js';

const ep = {
  id: 'mesopotamia',
  title: '에피소드 2 — 두 강 사이의 문',
  region: '오스만 · 바스라 / 남부 습지',
  clueTitles: CLUE_TITLES,
  start: 'basra_arrival',

  // 이집트에서 여기까지. 홍해와 인도양을 돌아 3주가 걸린다.
  // 몸은 배 위에서 낫는다. 본 것은 낫지 않는다 — 그래서 체력은 크게, 정신력은 조금만.
  arrival: { time: 24 * 2 * 21, hp: 12, san: 10 },

  map: {
    groundY: 40,
    surfaceLabel: '수면 위',
    depthLabel: '수면 아래',
    nodes: [
      { scene: 'basra_arrival', label: '바스라 항', x: 12, y: 12 },
      { scene: 'basra_bazaar', label: '대상 시장', x: 38, y: 8 },
      { scene: 'marsh_camp', label: '갈대 습지', x: 64, y: 18 },
      { scene: 'zigg_base', label: '지구라트 기단', x: 86, y: 30 },
      { scene: 'zigg_archive', label: '점토판 서고', x: 88, y: 52 },
      { scene: 'black_canal', label: '검은 수로', x: 68, y: 66 },
      { scene: 'gate_chamber', label: '문의 방', x: 48, y: 82 },
      { scene: 'crane_reckoning', label: '재대면', x: 26, y: 62 },
      { scene: 'reckoning_break', label: '무너지는 계단', x: 14, y: 48 },
      { scene: 'basra_finale', label: '갈대밭 가장자리', x: 22, y: 26 },
      { scene: 'basra_epilogue', label: '샤트알아랍', x: 7, y: 30 },
    ],
    links: [
      ['basra_arrival', 'basra_bazaar'],
      ['basra_arrival', 'marsh_camp'],
      ['basra_bazaar', 'marsh_camp'],
      ['marsh_camp', 'zigg_base'],
      ['zigg_base', 'zigg_archive'],
      ['zigg_archive', 'black_canal'],
      ['black_canal', 'gate_chamber'],
      ['gate_chamber', 'crane_reckoning'],
      ['crane_reckoning', 'reckoning_break'],
      ['crane_reckoning', 'basra_finale'],
      ['reckoning_break', 'basra_finale'],
      ['basra_finale', 'basra_epilogue'],
    ],
  },

  pressureEvents: [
    {
      id: 'mosquito',
      minDanger: 5,
      scenes: ['marsh_camp', 'zigg_base'],
      text: [
        '해가 지자 공기가 소리를 갖는다. 모기다. 벽처럼 두껍다.',
        '갈대를 태운 연기 속으로 들어가지 않으면 잠을 잘 수 없다.',
      ],
      effects: { hp: -1, danger: 1 },
    },
    {
      id: 'water_rising',
      minDanger: 6,
      scenes: ['black_canal', 'gate_chamber', 'zigg_archive'],
      text: [
        '발목에 닿던 물이 정강이에 닿는다.',
        '어디선가 수문이 열렸거나, 이 유적이 물을 부르고 있거나.',
      ],
      effects: { danger: 1 },
    },
    {
      id: 'reed_boats',
      minDanger: 8,
      scenes: ['marsh_camp', 'zigg_base', 'basra_finale'],
      text: [
        '갈대 사이로 배 세 척이 미끄러진다. 노를 젓지 않는다. 장대로 민다.',
        '마단의 배가 아니다. 마단은 저렇게 조용히 오지 않는다.',
      ],
      effects: { danger: 1 },
    },
    {
      id: 'counting',
      minDanger: 10,
      text: [
        '물속에서 무언가 규칙적인 소리가 난다. 세 번, 쉬고, 다시 세 번.',
        '숫자를 세는 소리 같다. 무엇이 무엇을 세는지는 알 수 없다.',
      ],
      effects: { san: -2 },
    },
  ],

  scenes: {
    // ── 1. 도착 ────────────────────────────────────────────────
    basra_arrival: {
      id: 'basra_arrival',
      location: '바스라 항 · 샤트알아랍',
      exits: ['대상 시장', '습지로 가는 물길'],
      onEnter(state, visits) {
        if (visits > 1) return {};
        const eff = { companions: ['seraphina'] };
        // 나디아는 룩소르 사람이다. 정을 붙인 만큼만 멀리 온다.
        const nadia = state.companions.nadia;
        if (nadia && nadia.affinity >= 4) {
          eff.companion = { id: 'nadia', present: true };
        } else if (nadia) {
          eff.companionChanges = [{ id: 'nadia', present: false }];
        }
        return eff;
      },
      body: (state) => {
        const out = [
          '3주. 홍해를 내려가 인도양을 돌고, 다시 강을 거슬러 올라왔다.',
          '바스라의 물은 나일과 다르다. 두 강이 여기서 섞이며 흙탕과 소금이 함께 흐른다. ' +
            '공기가 무겁고, 숨을 쉬면 물을 마시는 것 같다.',
        ];

        if (state.companions.nadia?.present) {
          out.push(
            '나디아가 난간에 팔을 얹고 강을 본다. "여기까지 올 생각은 없었어요."',
            '"그런데 그 방을 본 사람이 저 말고 또 있어야 할 것 같아서요."',
          );
        } else if (state.companions.nadia) {
          out.push(
            '나디아는 알렉산드리아에서 배를 내렸다. 악수는 짧았고, 눈은 마주치지 않았다.',
            '"서쪽 지류까지가 제 일이었습니다." 그것이 마지막 말이었다.',
          );
        }

        out.push(
          '부두에서 한 여자가 우산을 들고 서 있다. 이 습기에 우산은 볕을 가리는 물건이 아니다. ' +
            '단지 손에 무언가를 쥐고 있고 싶은 것이다.',
          '세라피나 볼트. 대영박물관 지하 보관고에서 8년을 보낸 필사가.',
          '"전보를 받고 3일 만에 출발했습니다." 그녀가 말한다. ' +
            '"검은 태양이라고 쓰셨더군요. 저는 그 단어를 12년 동안 기다렸습니다."',
        );

        if (state.flags.craneAlly) {
          out.push(
            '"그리고 크레인 경이 먼저 도착해 있습니다. 총독부와 이야기 중이라더군요."',
            '적은 아니지만, 앞서 있다는 사실은 변하지 않는다.',
          );
        } else if (state.flags.craneHasTablet) {
          out.push(
            '"크레인 경의 배가 나흘 먼저 들어왔습니다." 그녀가 우산 손잡이를 고쳐 쥔다.',
            '"기호판을 가져갔다고 하셨죠. 그렇다면 그는 이미 습지에 있을 겁니다."',
          );
        } else {
          out.push(
            '"영국인 발굴단이 하나 들어와 있습니다. 이름은 밝히지 않았고요."',
            '"당신이 아는 이름일 가능성이 높다고 생각합니다."',
          );
        }
        return out;
      },
      revisitBody: [
        '부두는 여전히 붐빈다. 대추야자 자루와 아스팔트 통이 번갈아 실린다.',
        '세라피나가 수첩에서 눈을 든다. "결정하셨어요?"',
      ],
      ambientCheck: {
        label: '부두를 살핀다',
        check: { stat: '관찰', tags: ['조사', '정보'], target: 13, label: '관찰 판정' },
        outcomes: {
          crit: {
            text: [
              '하역품 중에 어울리지 않는 것이 있다. 잠수 장비다.',
              '헬멧, 공기 펌프, 납 신발. 사막 발굴대가 가져올 물건이 아니다.',
              '누군가 물 아래로 들어갈 계획을 하고 있다. 그리고 그것은 당신이 아니다.',
            ],
            effects: { clues: ['crane_expedition'], flags: { knowsDivingGear: true }, time: 2 },
          },
          success: {
            text: [
              '궤짝 하나에 영국 세관 봉인이 붙어 있다. 날짜는 나흘 전.',
              '무게 표기가 이상하다. 측량 장비가 이렇게 무거울 리 없다.',
            ],
            effects: { clues: ['crane_expedition'], time: 2 },
          },
          partial: {
            text: [
              '짐꾼들의 동선이 한 창고를 피한다. 그 이상은 읽히지 않는다.',
              '습기 탓에 눈이 자꾸 감긴다.',
            ],
            effects: { time: 2 },
          },
          fail: {
            text: [
              '부두는 그저 부두다. 대추야자, 아스팔트, 소금, 사람.',
              '한 시간을 서 있었고 셔츠가 등에 붙었다.',
            ],
            effects: { time: 3 },
          },
          fumble: {
            text: [
              '창고 그늘로 들어선 순간, 안쪽에서 누군가 램프를 든다.',
              '얼굴은 보이지 않는다. 그러나 그 사람은 당신의 얼굴을 충분히 오래 봤다.',
              '세라피나가 팔을 잡아끈다. "지금은 아닙니다."',
            ],
            effects: { danger: 2, time: 3 },
          },
        },
      },
      choices: [
        {
          id: 'brief_seraphina',
          label: '세라피나에게 이집트에서 본 것을 말한다',
          keys: ['세라피나에게 말', '이집트', '보고', '설명한다'],
          once: true,
          check: {
            stat: '지식',
            tags: ['해독', '기록'],
            target: 12,
            label: '지식 판정',
            prompt: [
              '당신은 수첩을 펴고 그 방을 다시 그린다. 원형의 돔. 어긋난 별. 문 위의 검은 원반.',
              '세라피나는 말을 끊지 않는다. 다만 손이 점점 빨라진다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '그녀가 자기 가방에서 종이 한 장을 꺼내 당신의 스케치 옆에 놓는다.',
                '보관고에서 몰래 뜬 탁본. 수메르 점토판의 일부다.',
                '두 그림에서 같은 기호가 같은 자리에 있다. 원. 그 아래 엎드린 것들.',
                '"이걸 12년 동안 혼자 봤습니다." 그녀의 목소리가 처음으로 흔들린다.',
                '"이제 둘이 보는군요."',
              ],
              effects: {
                clues: ['same_hand'],
                companion: { id: 'seraphina', trust: 2, affinity: 2 },
                flags: { seraphinaOpened: true },
                time: 2,
              },
            },
            success: {
              text: [
                '"측량사의 문체." 그녀가 당신의 말을 되풀이한다. "그 표현이 정확합니다."',
                '"저도 같은 인상을 받은 적이 있어요. 다른 대륙의 점토판에서."',
              ],
              effects: {
                clues: ['same_hand'],
                companion: { id: 'seraphina', trust: 1 },
                time: 2,
              },
            },
            partial: {
              text: [
                '설명이 자꾸 미끄러진다. 본 것을 말로 옮기는 일은 생각보다 어렵다.',
                '그녀는 끝까지 듣고 고개를 끄덕인다. "직접 보면 알겠지요."',
              ],
              effects: { time: 2 },
            },
            fail: {
              text: [
                '당신의 설명은 스스로 듣기에도 헛소리에 가깝다.',
                '세라피나는 예의 바르게 침묵한다. 그 침묵이 더 아프다.',
              ],
              effects: { san: -1, time: 2 },
            },
            fumble: {
              text: [
                '말하는 도중에 당신은 그 방을 다시 본다. 눈앞의 부두가 아니라 그 방을.',
                '정신을 차렸을 때 세라피나가 당신의 어깨를 붙들고 있다.',
                '"…같은 문장을 여섯 번 반복하셨습니다." 그녀가 조심스럽게 말한다.',
              ],
              effects: { san: -2, time: 2 },
            },
          },
        },
        {
          id: 'to_bazaar',
          label: '대상 시장에서 습지 사정을 알아본다',
          keys: ['시장', '대상', '알아본다', '정보'],
          text: ['부두를 등지고 좁은 아케이드로 들어간다. 향신료와 아스팔트 냄새가 뒤섞인다.'],
          effects: { time: 2, goto: 'basra_bazaar' },
        },
        {
          id: 'straight_to_marsh',
          label: '배를 구해 곧장 습지로 향한다',
          keys: ['습지', '곧장', '출발', '배를 구'],
          hint: '준비는 줄지만, 물이 빠지는 계절은 짧다',
          text: [
            '"지금요?" 세라피나가 우산을 접는다. "…좋습니다. 저는 반대하지 않겠습니다."',
            '나룻배 한 척을 빌린다. 뱃사공은 값을 두 배로 부르고, 서쪽이라는 말에 세 배로 올린다.',
          ],
          effects: { time: 6, flags: { rushedMarsh: true }, goto: 'marsh_camp' },
        },
      ],
      freeform: [
        {
          keys: ['강', '두 강', '물을 본다', '샤트'],
          text: [
            '유프라테스와 티그리스가 여기서 하나가 된다.',
            '두 강 사이. 기호판의 좌표가 가리킨 곳에 실제로 서 있다는 사실이, 이제야 몸에 닿는다.',
          ],
          effects: {},
        },
        {
          keys: ['우산', '세라피나를 본다'],
          text: [
            '그녀는 우산을 펴지 않는다. 접은 채로 손잡이만 계속 고쳐 쥔다.',
            '무기를 든 적 없는 사람이 무기를 쥐는 방식이다.',
          ],
          effects: {},
        },
      ],
    },

    // ── 2. 시장 · 정보 ─────────────────────────────────────────
    basra_bazaar: {
      id: 'basra_bazaar',
      location: '바스라 · 대상 시장',
      exits: ['항구', '습지로 가는 물길'],
      body: [
        '아케이드는 어둡고 서늘하다. 바깥의 빛이 갈대 발 사이로 잘려 들어온다.',
        '이곳은 룩소르의 시장과 다르다. 관광객에게 파는 물건이 없다. ' +
          '대추야자, 아스팔트, 양모, 그리고 소문.',
        '차 좌판 뒤에 앉은 노인이 당신을 오래 본다. 그가 먼저 자리를 권한다.',
        '"서쪽으로 가시려는 분이군요." 그가 말한다. "그 얼굴을 여러 번 봤습니다."',
        '"돌아온 얼굴은 두 번 봤고요."',
      ],
      revisitBody: [
        '노인은 여전히 같은 자리에 앉아 있다.',
        '"아직 안 가셨습니까." 그가 찻잔을 밀어 준다.',
      ],
      ambientCheck: {
        label: '좌판과 사람들을 살핀다',
        check: { stat: '관찰', tags: ['조사', '정보'], target: 13, label: '관찰 판정' },
        outcomes: {
          crit: {
            text: [
              '아스팔트 통 사이에 점토 조각들이 섞여 있다. 값을 매기지 않은 채로.',
              '하나를 집어 든다. 쐐기문자다. 그런데 문자 사이사이에 다른 것이 있다.',
              '숫자다. 거리와 각도. 그리고 원 하나.',
            ],
            effects: { items: ['점토 원통'], clues: ['same_hand'], time: 2 },
          },
          success: {
            text: [
              '점토 조각 몇 개가 상품 취급도 받지 못한 채 굴러다닌다.',
              '하나를 집는다. 손톱만 한 원이 새겨져 있다. 안쪽이 파여 있다.',
            ],
            effects: { items: ['점토 원통'], time: 2 },
          },
          partial: {
            text: [
              '점토 조각을 사려 하자 노인이 손을 젓는다. "그건 팔 물건이 아닙니다."',
              '값을 치르지 않고 하나를 얻었지만, 대신 그의 표정을 얻었다.',
            ],
            effects: { items: ['점토 원통'], san: -1, time: 2 },
          },
          fail: {
            text: [
              '눈에 들어오는 것은 대추야자와 양모뿐이다.',
              '땀이 눈에 들어가 시야가 흐리다.',
            ],
            effects: { time: 2 },
          },
          fumble: {
            text: [
              '당신이 집어 든 조각이 손안에서 부서진다. 점토는 마르면 그렇게 된다.',
              '노인이 부스러기를 오래 본다. "저건 사천 년을 견뎠습니다."',
              '"당신 손에서 4초를 못 견뎠고요."',
            ],
            effects: { san: -1, danger: 1, time: 2 },
          },
        },
      },
      choices: [
        {
          id: 'ask_permit',
          label: '총독부의 발굴 금지에 대해 묻는다',
          keys: ['총독', '허가', '금지', '오스만'],
          once: true,
          check: {
            stat: '설득',
            tags: ['사교', '정보'],
            target: 13,
            label: '설득 판정',
            prompt: ['노인은 찻잔을 두 번 채우고 나서야 입을 연다.'],
          },
          outcomes: {
            crit: {
              text: [
                '"콜레라라고 적혀 있지요." 그가 웃지 않고 웃는 표정을 짓는다.',
                '"그 습지에 콜레라는 없었습니다. 물이 흐르니까요."',
                '"두 달 전에 인부 열둘이 서쪽 언덕에서 일했습니다. 총독부가 보낸 사람들이었죠."',
                '"넷이 돌아왔고, 그중 둘은 자기 이름을 잊었습니다. 금지령은 그다음 주에 나왔고요."',
                '그가 목소리를 낮춘다. "그리고 영국인들은 지난주에 허가를 받았습니다. 돈이었겠지요."',
              ],
              effects: {
                clues: ['ottoman_permit', 'crane_expedition'],
                flags: { knowsPermit: true },
                time: 2,
              },
            },
            success: {
              text: [
                '"금지령의 이유는 콜레라입니다." 그가 어깨를 으쓱한다.',
                '"그 습지에 콜레라는 없었습니다. 그게 답이 될 겁니다."',
              ],
              effects: { clues: ['ottoman_permit'], flags: { knowsPermit: true }, time: 2 },
            },
            partial: {
              text: [
                '"저는 차를 팝니다." 그가 말한다. "총독부 일은 총독부에 물으십시오."',
                '그러나 그가 서쪽을 흘끗 본다. 그것으로 절반은 들은 셈이다.',
              ],
              effects: { time: 2 },
            },
            fail: {
              text: [
                '노인의 입이 닫힌다. 찻잔만 두 번 더 채워진다.',
                '"차는 값을 받겠습니다."',
              ],
              effects: { time: 2 },
            },
            fumble: {
              text: [
                '당신은 총독부라는 단어를 아케이드에서 소리 내어 말했다.',
                '두 좌판 건너에서 누군가 자리를 뜬다. 서두르지 않는 걸음이 더 불길하다.',
                '노인이 찻잔을 치운다. "오늘은 닫겠습니다."',
              ],
              effects: { danger: 2, time: 2 },
            },
          },
        },
        {
          id: 'buy_lamp',
          label: '역청 램프와 보급품을 산다',
          keys: ['램프', '보급', '장비', '산다', '구매'],
          once: true,
          text: [
            '노인이 조카를 부른다. 소년이 램프 두 개와 기름통을 들고 온다.',
            '"역청입니다. 물가에서는 이게 낫습니다. 젖어도 꺼지지 않아요."',
            '"그리고 이건 값을 받지 않겠습니다." 그가 마른 대추야자 한 봉지를 얹는다.',
            '소년이 로프 한 타래를 더 가져온다. "물에서는 이게 손보다 낫습니다."',
          ],
          effects: { items: ['역청 램프', '의료 키트', '등반 로프'], time: 2 },
        },
        {
          id: 'hire_basim',
          label: '습지 뱃사공을 구한다',
          keys: ['뱃사공', '배', '안내인', '고용'],
          once: true,
          hint: '갈대밭에서 길을 아는 사람은 마단뿐이다',
          text: [
            '아케이드 끝, 갈대 다발을 손질하던 남자가 고개를 든다.',
            '바심 알마단. 삼대째 이 습지에서 배를 민다.',
            '"서쪽 언덕이요." 그가 갈대를 내려놓는다. "값은 두 배 받겠습니다."',
            '"돈이 아까워서가 아니라, 제 어머니가 아시면 세 배를 물리실 거라서요."',
          ],
          effects: { companions: ['basim'], time: 2 },
        },
        {
          id: 'to_marsh',
          label: '습지로 출발한다',
          keys: ['습지', '출발', '떠난다', '나간다'],
          text: ['아케이드를 빠져나오자 습기가 다시 얼굴을 덮는다. 서쪽이다.'],
          effects: { time: 4, goto: 'marsh_camp' },
        },
      ],
      freeform: [
        {
          keys: ['차', '마신다', '찻잔'],
          text: [
            '홍차에 카다멈이 들어 있다. 지나치게 진하고, 그래서 좋다.',
            '노인은 당신이 다 마실 때까지 아무 말도 하지 않는다.',
          ],
          effects: { san: 1, time: 1 },
        },
        {
          keys: ['아스팔트', '역청', '냄새'],
          text: [
            '역청 통이 줄지어 있다. 이 땅은 바닥에서 검은 것이 배어 나온다.',
            '노아의 방주도 이걸로 틈을 메웠다고, 누군가 말한 적이 있다.',
          ],
          effects: {},
        },
      ],
    },

    // ── 3. 습지 ────────────────────────────────────────────────
    marsh_camp: {
      id: 'marsh_camp',
      location: '남부 습지 · 갈대의 바다',
      exits: ['바스라', '서쪽 언덕'],
      onEnter(state, visits) {
        if (visits > 1) return { danger: -3 };
        return { danger: 1 };
      },
      body: (state) => {
        const out = [
          '갈대가 사람 키의 두 배로 자란다. 물길은 갈대 사이로만 나 있고, 그 물길은 지도에 없다.',
          '해가 어디 있는지 알 수 없다. 위를 봐도 갈대뿐이다.',
        ];
        if (state.companions.basim?.present) {
          out.push(
            '바심이 장대를 물속에 꽂아 배를 민다. 그는 갈림길에서 한 번도 망설이지 않는다.',
            '"길이 아니라 물 색으로 봅니다." 그가 묻지도 않은 말에 답한다.',
          );
        } else {
          out.push(
            '뱃사공 없이 들어온 물길은 세 번 갈라지고, 세 번 모두 같아 보인다.',
            '노를 저을 때마다 방향이 조금씩 어긋나는 것을 당신은 알고 있다.',
          );
        }
        out.push(
          '갈대 섬 하나에 마단의 게스트하우스가 서 있다. 갈대만으로 지은 아치형 건물. ' +
            '못도 나무도 쓰지 않았다.',
          '노인 하나가 문간에 앉아 당신들이 오는 것을 오래전부터 보고 있었다는 얼굴로 본다.',
        );
        return out;
      },
      revisitBody: [
        '갈대의 벽이 배를 다시 삼킨다. 게스트하우스의 아치가 물 위에 그림자를 눕힌다.',
        '물이 어제보다 조금 낮다. 아니면 조금 높거나.',
      ],
      ambientCheck: {
        label: '물과 갈대를 살핀다',
        check: { stat: '탐험', tags: ['조사', '방향'], target: 13, label: '탐험 판정' },
        outcomes: {
          crit: {
            text: [
              '물 색이 한 줄기만 다르다. 탁하지 않고, 검다.',
              '손을 담근다. 차갑다. 습지의 물은 이렇게 차가울 수 없다.',
              '어딘가에서 지하수가 올라오고 있다. 그리고 지하수는 반드시 어딘가를 지나온다.',
            ],
            effects: { flags: { foundColdCurrent: true }, clues: ['madan_warning'], time: 2 },
          },
          success: {
            text: [
              '물길 하나가 다른 것들보다 곧다. 자연이 만든 곡선이 아니다.',
              '누군가 수천 년 전에 판 수로 위를 갈대가 덮은 것이다.',
            ],
            effects: { flags: { foundColdCurrent: true }, time: 2 },
          },
          partial: {
            text: [
              '갈대를 헤치다 손바닥이 베인다. 이 풀은 날이 서 있다.',
              '방향은 잡았다. 정확하지는 않다.',
            ],
            effects: { hp: -1, time: 2 },
          },
          fail: {
            text: [
              '한 시간을 돌아 같은 자리로 돌아온다. 표식으로 꺾어둔 갈대가 눈앞에 있다.',
              '갈대밭은 발자국을 남기지 않는다.',
            ],
            effects: { time: 3 },
          },
          fumble: {
            text: [
              '배가 기운다. 물속에서 무언가 뱃전을 스쳤다.',
              '물소일 것이다. 이 습지에는 물소가 많다.',
              '다만 물소의 등은 그렇게 매끄럽지 않다.',
            ],
            effects: { san: -2, danger: 2, time: 3 },
          },
        },
      },
      choices: [
        {
          id: 'madan_elder',
          label: '마단 노인에게 서쪽 언덕을 묻는다',
          keys: ['노인', '마단', '언덕', '묻는다'],
          once: true,
          check: {
            stat: '설득',
            tags: ['사교', '정보'],
            target: 14,
            bonus: 0,
            label: '설득 판정',
            prompt: [
              '노인은 갈대를 엮던 손을 멈추지 않는다.',
              '통역이 필요하다. 바심이 있다면 그가, 없다면 몸짓이.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '노인이 갈대 한 가닥을 들어 물에 세운다. 그리고 손가락으로 그 아래를 가리킨다.',
                '"숨 쉬는 곳." 통역이 그렇게 옮긴다.',
                '"물이 빠지는 계절에만 드러납니다. 드러난 해에는 반드시 누가 사라지고요."',
                '"올해가 그 해입니다. 두 달 전에 열둘이 갔고, 넷이 돌아왔습니다."',
                '노인이 처음으로 당신의 눈을 본다. "돌아온 넷은 물을 무서워하게 됐습니다. ' +
                  '평생 물 위에서 산 사람들이요."',
              ],
              effects: {
                clues: ['madan_warning', 'ottoman_permit'],
                flags: { elderSpoke: true },
                time: 3,
              },
            },
            success: {
              text: [
                '"숨 쉬는 곳." 노인이 그 말만 반복한다.',
                '"물이 빠지면 드러나고, 드러나면 누가 사라집니다."',
                '그가 서쪽을 가리킨다. 정확한 방향이다.',
              ],
              effects: { clues: ['madan_warning'], flags: { elderSpoke: true }, time: 3 },
            },
            partial: {
              text: [
                '노인은 갈대만 엮는다. 대답 대신 게스트하우스 안쪽을 가리킨다.',
                '거기 걸린 것이 있다. 말린 갈대로 엮은 원 하나. 안쪽이 검게 그을렸다.',
              ],
              effects: { san: -1, time: 3 },
            },
            fail: {
              text: [
                '노인이 손을 젓는다. 통역은 그것을 옮기지 않는다.',
                '"옮길 말이 아닙니다." 그것이 통역의 설명 전부였다.',
              ],
              effects: { time: 3 },
            },
            fumble: {
              text: [
                '당신은 서쪽 언덕을 손가락으로 가리켰다.',
                '게스트하우스 안의 사람들이 일제히 조용해진다. 아이 하나가 밖으로 뛰어나간다.',
                '노인이 일어선다. 그리고 당신들의 배를 향해 짧게 말한다.',
                '"오늘 밤은 여기서 주무실 수 없습니다."',
              ],
              effects: { danger: 2, san: -1, time: 3 },
            },
          },
        },
        {
          id: 'rest_marsh',
          label: '게스트하우스에서 밤을 보낸다',
          keys: ['잔다', '밤', '쉰다', '머문다'],
          once: true,
          hint: '회복하지만, 물이 빠지는 시기는 기다려 주지 않는다',
          text: [
            '갈대로 엮은 천장 아래에 누우면 소리가 이상하게 울린다. 배 안에서 자는 것 같다.',
            '밤새 물이 건물 아래를 지나간다. 건물 전체가 아주 천천히 흔들린다.',
            '새벽에 잠깐 깼을 때, 서쪽 갈대 위로 램프 불빛 여러 개가 지나갔다.',
          ],
          effects: {
            hp: 4,
            san: 3,
            time: 14,
            danger: 1,
            clues: ['crane_expedition'],
            companionChanges: [
              { id: 'seraphina', affinity: 1 },
              { id: 'basim', affinity: 1 },
            ],
          },
        },
        {
          id: 'basim_shortcut',
          label: '바심에게 지름길을 부탁한다',
          keys: ['지름길', '빨리', '바심에게'],
          requires: { companions: ['basim'] },
          once: true,
          text: [
            '바심이 갈대를 두 손으로 벌린다. 그 사이에 물길이 있다. 배 한 척 폭.',
            '"어머니가 아시면 안 됩니다." 그가 장대를 고쳐 쥔다.',
            '갈대가 양쪽에서 얼굴을 스친다. 40분 뒤, 배 앞이 트인다.',
            '물이 넓어지고, 그 가운데에 흙 언덕 하나가 솟아 있다. 각이 진 언덕이.',
          ],
          effects: {
            time: 2,
            companion: { id: 'basim', trust: 1 },
            flags: { foundColdCurrent: true },
            goto: 'zigg_base',
          },
        },
        {
          id: 'to_mound',
          label: '서쪽 언덕으로 배를 민다',
          keys: ['서쪽', '언덕', '간다', '전진'],
          check: {
            stat: '탐험',
            tags: ['이동', '방향'],
            target: 13,
            label: '독도 판정',
            prompt: [
              '갈대는 어디서나 똑같이 생겼다.',
              '방향을 잡는 방법은 물의 흐름과 해의 각도뿐이다. 둘 다 지금은 모호하다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '물 색이 검게 바뀌는 줄기를 따라간다. 흐름을 거스르지 않고, 흐름이 오는 쪽으로.',
                '한 시간 만에 갈대가 끊긴다.',
                '넓은 물 가운데 흙 언덕이 있다. 자연은 이런 각도로 무너지지 않는다.',
              ],
              effects: { flags: { foundColdCurrent: true }, goto: 'zigg_base' },
            },
            success: {
              text: [
                '두 번 잘못 들고, 세 번째에 갈대가 트인다.',
                '물 가운데 언덕 하나. 사면이 지나치게 반듯하다.',
              ],
              effects: { time: 2, goto: 'zigg_base' },
            },
            partial: {
              text: [
                '해가 기울 때까지 갈대 속을 돈다. 모기가 팔을 덮는다.',
                '언덕에 닿았을 때는 이미 어두웠고, 물이 무릎까지 올라와 있었다.',
              ],
              effects: { hp: -2, time: 5, danger: 1, goto: 'zigg_base' },
            },
            fail: {
              text: [
                '같은 곳을 세 번 돈다. 배 안의 물이 발목까지 찼다.',
                '결국 언덕에 닿기는 했다. 반나절을 잃고서.',
              ],
              effects: { hp: -2, time: 8, danger: 2, goto: 'zigg_base' },
            },
            fumble: {
              text: [
                '갈대가 갑자기 끊기고, 배가 열린 물로 미끄러진다.',
                '그리고 그 물 한가운데에 배 세 척이 서 있다. 장대를 든 사람들이 당신을 본다.',
                '한 사람이 손을 든다. 인사가 아니다. 신호다.',
                '당신은 갈대 속으로 다시 배를 밀어 넣는다. 심장이 귀에서 뛴다.',
              ],
              effects: { san: -2, danger: 3, time: 6, goto: 'zigg_base' },
            },
          },
        },
      ],
      freeform: [
        {
          keys: ['갈대', '만진다', '엮'],
          text: [
            '갈대는 손안에서 서늘하다. 마단은 이것으로 집을 짓고, 배를 짓고, 무덤도 짓는다.',
            '오천 년 동안 같은 방식으로.',
          ],
          effects: {},
        },
        {
          keys: ['물소', '동물', '새'],
          text: [
            '물소 떼가 갈대 사이에 몸을 담그고 있다. 눈만 물 위에 떠 있다.',
            '새는 없다. 아까부터 없었다.',
          ],
          effects: { san: -1 },
        },
      ],
    },

    // ── 4. 지구라트 기단 ───────────────────────────────────────
    zigg_base: {
      id: 'zigg_base',
      location: '서쪽 언덕 · 무너진 기단',
      exits: ['습지', '아래로'],
      onEnter(state, visits) {
        if (visits > 1) return {};
        return { danger: 1 };
      },
      body: (state) => {
        const out = [
          '언덕이 아니다. 계단이다.',
          '물이 빠지면서 드러난 것은 구운 벽돌의 층이다. 한 층, 두 층, 세 층. ' +
            '위쪽 세 층은 무너졌고, 무너진 자리에 흙이 얹혀 언덕이 되었다.',
          '벽돌마다 도장이 찍혀 있다. 이름과 연도. 사천 년 전에 누군가 이걸 자기 이름으로 서명했다.',
        ];
        if (state.flags.knowsDivingGear) {
          out.push(
            '기단 동쪽에 최근 세운 도르래가 있다. 밧줄이 물 아래로 곧게 내려간다.',
            '잠수 장비. 크레인은 이미 아래를 보고 있다.',
          );
        }
        out.push(
          '기단 한쪽에 물이 고여 있다. 고인 것이 아니라, 빨려 들어가고 있다.',
          '아래에 빈 공간이 있다는 뜻이다.',
        );
        return out;
      },
      revisitBody: [
        '기단의 벽돌은 낮 동안 열을 먹었다가 밤에 그것을 뱉는다.',
        '물이 빨려 들어가는 소리가 여전히 난다.',
      ],
      ambientCheck: {
        label: '벽돌의 도장을 읽는다',
        check: { stat: '지식', tags: ['해독', '조사'], target: 14, label: '해독 판정' },
        outcomes: {
          crit: {
            text: [
              '도장은 세 종류다. 왕의 이름 둘, 그리고 이름이 아닌 것 하나.',
              '세 번째 도장에는 이름이 없다. 대신 숫자가 있다. 층수와 각도와 방위.',
              '건축가의 서명이 아니라 측량사의 기록이다. 룩소르의 그 문체다.',
              '사천 년 전 이 벽돌을 찍은 손과, 삼천 년 전 이집트의 벽을 새긴 손이 같다.',
              '둘 중 하나는 불가능하다. 둘 다 사실이라면, 그 손은 사람의 손이 아니다.',
            ],
            effects: { clues: ['same_hand'], san: -2, time: 2 },
          },
          success: {
            text: [
              '두 왕의 이름과, 이름이 아닌 도장 하나.',
              '세 번째 도장에는 숫자만 있다. 거리, 각도, 방위.',
              '어디서 본 문체다. 아주 최근에.',
            ],
            effects: { clues: ['same_hand'], san: -1, time: 2 },
          },
          partial: {
            text: [
              '도장의 절반은 물에 먹혔다. 읽히는 것은 왕의 이름뿐이다.',
              '그 이름은 이미 알려진 이름이고, 알려진 이름은 흥미롭지 않다.',
            ],
            effects: { time: 2 },
          },
          fail: {
            text: [
              '벽돌은 벽돌이다. 도장은 흙에 눌린 자국이고, 자국은 자국일 뿐이다.',
              '해가 기울도록 쭈그려 앉아 있다가 무릎만 상했다.',
            ],
            effects: { time: 3 },
          },
          fumble: {
            text: [
              '도장 하나를 손톱으로 긁어 흙을 걷어낸다.',
              '벽돌이 통째로 빠진다. 그리고 그 뒤에서 물이 뿜어져 나온다.',
              '차갑다. 습지의 물이 아니다. 아래에서 올라온 물이다.',
              '구멍을 막는 데 20분이 걸렸고, 그동안 당신은 계속 젖어 있었다.',
            ],
            effects: { hp: -2, danger: 2, time: 3 },
          },
        },
      },
      choices: [
        {
          id: 'find_entrance',
          label: '물이 빨려 드는 곳을 찾는다',
          keys: ['물이 빨려', '구멍', '입구', '찾는다'],
          hint: '찾을 때까지 몇 번이고 다시 볼 수 있다',
          check: {
            stat: '관찰',
            tags: ['조사', '함정'],
            target: 13,
            label: '관찰 판정',
            prompt: ['소용돌이는 작다. 손바닥만 하다. 그러나 소리는 그보다 훨씬 크다.'],
          },
          outcomes: {
            crit: {
              text: [
                '벽돌 세 장을 걷어내자 아래가 드러난다. 계단이다.',
                '그리고 계단 첫 단에 발자국이 있다. 진흙 위에 찍힌 유럽식 부츠.',
                '하나가 아니라 여럿. 들어간 수와 나온 수가 맞지 않는다.',
              ],
              effects: {
                flags: { foundZiggEntrance: true },
                clues: ['crane_expedition'],
                time: 2,
              },
            },
            success: {
              text: [
                '벽돌 몇 장을 걷어내자 아래로 내려가는 계단이 드러난다.',
                '입에서 나오는 공기가 차갑다. 그리고 아주 미세하게 달다.',
                '어디서 맡은 냄새인지, 몸이 먼저 안다.',
              ],
              effects: { flags: { foundZiggEntrance: true }, san: -1, time: 2 },
            },
            partial: {
              text: [
                '구멍은 찾았지만 사람이 지나기엔 좁다. 벽돌을 더 걷어내야 한다.',
                '손톱 두 개가 부러졌다.',
              ],
              effects: { hp: -1, flags: { foundZiggEntrance: true }, time: 3 },
            },
            fail: {
              text: [
                '소용돌이를 따라가면 물은 매번 다른 곳으로 사라진다.',
                '기단 전체가 스펀지처럼 물을 먹고 있다. 한 곳이 아니다.',
                '다시 볼 수는 있다. 물은 어디로든 빠지고 있으니까.',
              ],
              effects: { time: 3 },
            },
            fumble: {
              text: [
                '당신이 딛고 선 벽돌 층이 통째로 내려앉는다.',
                '허리까지 물에 빠지고, 발밑에서 무언가가 발목을 스친다.',
                '끌어올려졌을 때 손에 쥐고 있던 램프는 없었다.',
              ],
              effects: {
                hp: -3,
                san: -1,
                danger: 2,
                removeItems: ['역청 램프'],
                flags: { foundZiggEntrance: true },
                time: 3,
              },
            },
          },
        },
        {
          id: 'seraphina_bricks',
          label: '세라피나에게 벽돌을 읽어 달라고 한다',
          keys: ['세라피나에게 벽돌', '읽어 달라', '필사'],
          requires: { companions: ['seraphina'] },
          once: true,
          text: [
            '세라피나가 무릎을 꿇고 벽돌에 종이를 댄다. 목탄이 아니라 연필이다.',
            '"탁본은 시간이 걸립니다. 필사가 빨라요."',
            '20분 뒤 그녀가 종이를 내민다. 그리고 그 종이를 든 손이 떨린다.',
            '"이 도장 말인데요. 이건 왕의 것도 신관의 것도 아닙니다."',
            '"이건 검수 도장입니다. 누군가 이 건물을 검사하고 승인했어요."',
            '"사천 년 전에, 누가 누구에게 승인을 받습니까?"',
          ],
          effects: {
            clues: ['same_hand'],
            companion: { id: 'seraphina', trust: 1, affinity: 1 },
            san: -1,
            time: 3,
          },
        },
        {
          id: 'enter_zigg',
          label: '계단을 따라 내려간다',
          keys: ['내려간다', '계단', '진입', '들어간다'],
          requires: { flags: { foundZiggEntrance: true } },
          lockedText:
            '내려갈 구멍을 아직 못 찾았다. 물이 어디로 빠지는지부터 알아내야 한다.',
          text: (state) => {
            const out = [
              '계단은 좁고, 벽돌이 아니라 깎은 돌이다. 기단보다 오래된 것이다.',
              '한 층 내려갈 때마다 공기가 차가워진다.',
            ];
            if (state.companions.basim?.present) {
              out.push(
                '바심이 입구에서 멈춘다. "저는 물 위에서만 갑니다."',
                '"배는 여기 묶어두겠습니다. 밤이 되면… 아침까지는 기다리죠."',
              );
            }
            return out;
          },
          effects: { time: 1, goto: 'zigg_archive' },
        },
        {
          id: 'back_to_marsh',
          label: '습지로 물러난다',
          keys: ['돌아간다', '물러', '후퇴'],
          text: ['당신은 기단에서 배로 돌아간다. 언덕은 그 자리에 남는다.'],
          effects: { time: 2, goto: 'marsh_camp' },
        },
      ],
      freeform: [
        {
          keys: ['벽돌', '만진다', '도장'],
          text: [
            '벽돌은 손바닥보다 크고, 생각보다 가볍다. 짚을 섞어 구웠다.',
            '사천 년 전 누군가 이걸 들어 올렸다. 같은 자세로, 같은 무게를.',
          ],
          effects: {},
        },
        {
          keys: ['도르래', '밧줄', '잠수'],
          when: (s) => s.flags.knowsDivingGear,
          text: [
            '도르래의 밧줄은 젖어 있다. 최근에 썼다는 뜻이다.',
            '그리고 밧줄 끝에는 아무것도 매달려 있지 않다.',
          ],
          effects: { san: -1, clues: ['crane_expedition'] },
        },
      ],
    },

    // ── 5. 점토판 서고 ─────────────────────────────────────────
    zigg_archive: {
      id: 'zigg_archive',
      location: '기단 아래 · 점토판 서고',
      exits: ['기단', '수로'],
      onEnter(state, visits) {
        if (visits > 1) return {};
        return { danger: 1 };
      },
      body: [
        '방은 낮고 길다. 천장에 손이 닿는다.',
        '벽마다 선반이 있고, 선반마다 점토판이 꽂혀 있다. 수천 장.',
        '물이 발목까지 차 있다. 아래쪽 두 단은 이미 진흙이 되었고, ' +
          '진흙이 된 것들은 다시 흙으로 돌아가는 중이다.',
        '위쪽 선반은 아직 살아 있다. 살아 있는 것들이 몇 년이나 더 버틸지는 알 수 없다.',
        '방 끝에 문이 하나 있다. 문 위에 원반이 새겨져 있다.',
        '빛을 내지 않는 원반이.',
      ],
      revisitBody: [
        '서고의 물이 조금 더 올라왔다.',
        '문 위의 원반은 그대로다. 원반은 언제나 그대로다.',
      ],
      ambientCheck: {
        label: '점토판을 훑는다',
        check: { stat: '지식', tags: ['해독', '기록'], target: 14, label: '해독 판정' },
        outcomes: {
          crit: {
            text: [
              '대부분은 장부다. 보리 몇 말, 양 몇 마리, 누가 누구에게 빚졌는지.',
              '문명의 첫 문자가 시(詩)가 아니라 회계였다는 사실은 언제나 조금 웃기다.',
              '그러나 위쪽 선반 한 칸은 다르다. 목록이다. 왕들의 목록.',
              '첫 여덟 명의 재위 기간을 더한다. 이십사만 년.',
              '필사자의 손은 그 숫자를 적으면서 한 번도 흔들리지 않았다.',
            ],
            effects: { clues: ['sumerian_list'], items: ['왕 목록 사본'], san: -2, time: 3 },
          },
          success: {
            text: [
              '장부, 장부, 또 장부. 그러다 한 칸이 다르다.',
              '왕들의 이름과 재위 기간. 숫자가 지나치게 크다. 단위를 잘못 읽었나 싶을 만큼.',
            ],
            effects: { clues: ['sumerian_list'], time: 3 },
          },
          partial: {
            text: [
              '점토판 하나를 선반에서 빼자, 옆의 세 장이 함께 무너져 물에 떨어진다.',
              '건져 올린 것은 한 장뿐이다. 나머지는 손안에서 풀어졌다.',
            ],
            effects: { items: ['점토 원통'], san: -1, time: 3 },
          },
          fail: {
            text: [
              '램프 빛으로는 쐐기의 깊이가 읽히지 않는다. 각도를 바꿔도 마찬가지다.',
              '읽는 것이 아니라 짐작하고 있다는 것을 깨닫고 손을 뗀다.',
            ],
            effects: { time: 3 },
          },
          fumble: {
            text: [
              '선반 한 단이 통째로 무너진다.',
              '사천 년을 견딘 것들이 물에 닿아 조용히 풀어진다. 소리도 나지 않는다.',
              '당신은 무릎을 꿇고 진흙 속에서 조각을 건지려 한다. 건져지는 것은 없다.',
              '이 방에 있던 무언가가, 방금 영원히 사라졌다.',
            ],
            effects: { san: -3, danger: 1, time: 3 },
          },
        },
      },
      choices: [
        {
          id: 'search_shelves',
          label: '선반을 훑어 장부가 아닌 것을 찾는다',
          keys: ['선반', '훑는다', '찾는다', '점토판을'],
          hint: '수천 장이다. 몇 번이고 다시 볼 수 있다',
          check: {
            stat: '지식',
            tags: ['해독', '기록'],
            target: 14,
            label: '해독 판정',
            prompt: [
              '선반을 한 칸씩 짚어 나간다. 램프를 든 팔이 저릴 때까지.',
              '대부분은 장부다. 보리 몇 말, 양 몇 마리, 누가 누구에게 빚졌는지.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '문명의 첫 문자가 시(詩)가 아니라 회계였다는 사실은 언제나 조금 웃기다.',
                '그러나 위쪽 선반 한 칸은 다르다. 목록이다. 왕들의 목록.',
                '첫 여덟 명의 재위 기간을 더한다. 이십사만 년.',
                '필사자의 손은 그 숫자를 적으면서 한 번도 흔들리지 않았다.',
              ],
              effects: { clues: ['sumerian_list'], items: ['왕 목록 사본'], san: -2, time: 3 },
            },
            success: {
              text: [
                '장부, 장부, 또 장부. 그러다 한 칸이 다르다.',
                '왕들의 이름과 재위 기간. 숫자가 지나치게 크다. 단위를 잘못 읽었나 싶을 만큼.',
              ],
              effects: { clues: ['sumerian_list'], time: 3 },
            },
            partial: {
              text: [
                '선반 한 칸이 다르다는 것까지는 알았다. 무엇이 다른지는 아직 모른다.',
                '팔이 저려 램프를 반대 손으로 옮긴다. 다시 볼 수는 있다.',
              ],
              effects: { time: 3 },
            },
            fail: {
              text: [
                '램프 빛으로는 쐐기의 깊이가 읽히지 않는다. 각도를 바꿔도 마찬가지다.',
                '읽는 것이 아니라 짐작하고 있다는 것을 깨닫고 손을 뗀다.',
              ],
              effects: { time: 3 },
            },
            fumble: {
              text: [
                '선반 한 단이 통째로 무너진다.',
                '사천 년을 견딘 것들이 물에 닿아 조용히 풀어진다. 소리도 나지 않는다.',
                '이 방에 있던 무언가가, 방금 영원히 사라졌다.',
              ],
              effects: { san: -2, danger: 1, time: 3 },
            },
          },
        },
        {
          id: 'read_kinglist',
          label: '왕들의 목록을 끝까지 읽는다',
          keys: ['왕 목록', '목록', '끝까지', '읽는다'],
          requires: { clues: ['sumerian_list'] },
          lockedText: '먼저 그 목록을 찾아야 한다. 선반은 수천 장이다.',
          once: true,
          check: {
            stat: '지식',
            tags: ['해독'],
            target: 15,
            label: '해독 판정',
            prompt: [
              '목록은 한 줄에서 끊긴다. 그 줄만 다른 크기로 새겨져 있다.',
              '읽기 전에, 읽고 나면 되돌릴 수 없다는 예감이 먼저 온다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '"그리고 홍수가 왔다."',
                '그 한 줄 위와 아래는 같은 언어다. 그러나 같은 세계의 기록이 아니다.',
                '위쪽의 왕들은 수만 년을 다스렸고, 아래쪽의 왕들은 수십 년을 다스렸다.',
                '필사자는 이것을 신화로 적지 않았다. 장부를 적던 손 그대로 적었다.',
                '그에게 이것은 기록이었다. 있었던 일의 기록.',
              ],
              effects: { clues: ['flood_before', 'sumerian_list'], san: -2, time: 3 },
            },
            success: {
              text: [
                '"그리고 홍수가 왔다." 목록은 그 줄에서 갈린다.',
                '위와 아래는 다른 세계다. 그리고 필사자는 그것을 신화가 아니라 사실로 적었다.',
              ],
              effects: { clues: ['flood_before'], san: -2, time: 3 },
            },
            partial: {
              text: [
                '절반쯤 읽었을 때 램프의 기름이 흔들린다.',
                '읽은 것은 숫자뿐이다. 숫자만으로도 충분히 이상하다.',
              ],
              effects: { san: -1, time: 3 },
            },
            fail: {
              text: [
                '쐐기가 뭉개진 구간이 하필 그 줄이다.',
                '앞뒤로 무엇이 있었는지는 짐작만 남는다.',
              ],
              effects: { time: 3 },
            },
            fumble: {
              text: [
                '당신은 소리 내어 읽고 있었다. 언제부터인지 모른다.',
                '물이 발목에서 종아리로 올라온다. 어딘가에서 수문이 열렸다.',
                '그리고 방 끝의 원반이, 아주 잠깐, 더 검어진다.',
              ],
              effects: { san: -3, danger: 3, clues: ['flood_before'], time: 3 },
            },
          },
        },
        {
          id: 'combine_clues',
          label: '이집트의 기록과 나란히 놓는다',
          keys: ['나란히', '비교', '이집트와', '연결'],
          requires: { clues: ['not_first', 'sumerian_list'] },
          hideIfLocked: true,
          once: true,
          hint: '두 지역의 기록이 만난다',
          check: {
            stat: '지식',
            tags: ['해독', '신비'],
            target: 15,
            label: '추론 판정',
            prompt: [
              '당신은 수첩을 편다. 룩소르의 벽에서 뜬 아래층 문자. 그리고 이 방의 왕 목록.',
              '두 장을 물 위 선반에 나란히 놓는다.',
              '세라피나가 옆에서 램프를 든다. 아무도 말하지 않는다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '두 기록은 서로를 몰랐다. 대륙이 다르고, 천 년이 다르다.',
                '그런데 같은 자리에서 같은 방식으로 끊긴다. 무언가가 왔고, 그 전은 지워졌다.',
                '이집트의 벽은 무덤 아래 무덤을 말했고, 여기 목록은 홍수 이전의 왕을 말한다.',
                '둘을 겹치면 한 문장이 남는다.',
                '문명은 여러 번 시작되었고, 여러 번 끝났다. ' +
                  '우리가 역사라고 부르는 것은 마지막 시도의 기록일 뿐이다.',
                '"…그리고 마지막이라는 보장은 어디에도 없습니다." 세라피나가 말한다.',
              ],
              effects: {
                clues: ['first_civilization', 'flood_before'],
                san: -2,
                companion: { id: 'seraphina', trust: 2 },
                flags: { deduced: true },
                time: 3,
              },
            },
            success: {
              text: [
                '두 기록이 같은 자리에서 끊긴다. 대륙이 다른데 끊긴 자리가 같다.',
                '문명은 한 번 시작된 것이 아니다. 여러 번 시작되었고, 여러 번 끝났다.',
                '우리가 아는 역사는 그중 마지막 것이다.',
              ],
              effects: {
                clues: ['first_civilization'],
                san: -2,
                companion: { id: 'seraphina', trust: 1 },
                flags: { deduced: true },
                time: 3,
              },
            },
            partial: {
              text: [
                '두 기록은 닮았다. 그러나 닮았다는 것과 같다는 것은 다르다.',
                '증명이 되려면 하나가 더 필요하다. 세 번째 대륙의 기록이.',
              ],
              effects: { san: -1, flags: { needThirdSite: true }, time: 3 },
            },
            fail: {
              text: [
                '아무리 겹쳐 놓아도 두 장은 두 장이다.',
                '연결은 당신의 머릿속에만 있고, 머릿속에 있는 것은 증거가 아니다.',
              ],
              effects: { time: 3 },
            },
            fumble: {
              text: [
                '겹쳐 놓은 두 장을 보다가, 당신은 세 번째 것을 떠올린다.',
                '아무도 보여주지 않았고 어디서도 읽지 않은 것을.',
                '그것이 어떻게 머릿속에 있는지 설명할 수 없다는 사실이, 가장 무섭다.',
              ],
              effects: { san: -4, clues: ['first_civilization'], flags: { deduced: true }, time: 3 },
            },
          },
        },
        {
          id: 'salvage_tablets',
          label: '가라앉기 전에 몇 장이라도 건진다',
          keys: ['건진다', '챙긴다', '가져간다', '구한다'],
          once: true,
          check: {
            stat: '민첩',
            tags: ['기록', '조사'],
            target: 12,
            label: '민첩 판정',
            prompt: [
              '물이 조금씩 올라온다. 아래 선반의 것들은 이미 늦었다.',
              '가져갈 수 있는 것은 두 손에 들어오는 만큼이다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '가장 마른 것들만 고른다. 손이 빠르고 정확하다.',
                '여섯 장. 그중 하나는 목록의 사본이고, 하나는 원통형 인장이다.',
              ],
              effects: { items: ['왕 목록 사본', '점토 원통'], time: 2 },
            },
            success: {
              text: ['네 장을 건진다. 물기를 옷으로 닦고 품에 넣는다.'],
              effects: { items: ['점토 원통'], time: 2 },
            },
            partial: {
              text: [
                '두 장을 건지고, 세 번째를 잡다가 놓친다.',
                '물에 닿은 점토는 붙잡을수록 빨리 풀어진다.',
              ],
              effects: { items: ['점토 원통'], san: -1, time: 2 },
            },
            fail: {
              text: [
                '손에 쥔 것들이 차례로 풀어진다. 진흙이 손가락 사이로 빠져나간다.',
                '아무것도 건지지 못했다.',
              ],
              effects: { san: -2, time: 2 },
            },
            fumble: {
              text: [
                '선반을 붙잡은 순간 구조 전체가 기운다.',
                '당신은 물러섰고, 서고의 절반이 물속으로 미끄러졌다.',
                '사천 년이 3초 만에 끝난다.',
              ],
              effects: { san: -3, danger: 2, time: 2 },
            },
          },
        },
        {
          id: 'to_canal',
          label: '문 옆의 수로로 내려간다',
          keys: ['수로', '내려간다', '문 옆', '아래로'],
          text: [
            '문은 열리지 않는다. 룩소르의 그것처럼, 손잡이도 이음매도 없다.',
            '대신 문 왼편의 바닥이 꺼져 있다. 물이 그리로 빨려 들어간다.',
            '사람이 지날 수 있는 폭이다. 물살을 거스르지 않는다면.',
          ],
          effects: { time: 1, goto: 'black_canal' },
        },
      ],
      freeform: [
        {
          keys: ['원반', '문을 본다', '검은 태양'],
          text: [
            '문 위의 원반은 룩소르의 것과 같은 크기, 같은 재질이다.',
            '벽과 다른 물질. 손을 대면 차갑고, 떼어도 차가움이 남는다.',
            '두 대륙에서 같은 손이 같은 것을 박아 넣었다.',
          ],
          effects: { san: -1, clues: ['black_sun'] },
        },
        {
          keys: ['물', '수위', '발목'],
          text: [
            '물이 종아리에 닿는다. 아까는 발목이었다.',
            '이 방이 얼마나 오래 열려 있을지, 아무도 정하지 않았다.',
          ],
          effects: { danger: 1 },
        },
      ],
    },

    // ── 6. 검은 수로 ───────────────────────────────────────────
    black_canal: {
      id: 'black_canal',
      location: '기단 아래 · 검은 수로',
      exits: ['서고', '더 아래로'],
      onEnter(state, visits) {
        if (visits > 1) return {};
        return { danger: 1 };
      },
      body: [
        '수로는 사람이 판 것이다. 벽면에 정 자국이 남아 있다.',
        '물은 검고, 검은 이유는 어둠이 아니라 역청이다. 벽에 발린 역청이 물에 녹아 있다.',
        '천장이 낮아 허리를 굽혀야 한다. 물은 허벅지까지 온다.',
        '물살은 안쪽으로 흐른다. 밖으로가 아니라 안으로.',
        '어딘가에서 이 물을 마시고 있다.',
      ],
      revisitBody: [
        '수로의 물이 여전히 안쪽으로 흐른다.',
        '역청 냄새가 목구멍에 들러붙는다.',
      ],
      ambientCheck: {
        label: '벽면을 더듬는다',
        check: { stat: '관찰', tags: ['암흑', '조사'], target: 14, label: '관찰 판정' },
        outcomes: {
          crit: {
            text: [
              '역청 아래에 새김이 있다. 손끝으로만 읽힌다.',
              '숫자다. 일정한 간격으로 반복된다. 거리를 표시한 것이다.',
              '그리고 마지막 숫자 옆에 다른 기호가 있다. 문(門)을 세는 기호.',
              '일곱. 또는 아홉. 새긴 사람이 도중에 고쳐 새겼다.',
            ],
            effects: { clues: ['gate_pair'], san: -1, time: 2 },
          },
          success: {
            text: [
              '역청 아래에 새김이 있다. 숫자와, 반복되는 기호 하나.',
              '기호는 문을 뜻한다. 그리고 그 옆의 수는 하나가 아니다.',
            ],
            effects: { clues: ['gate_pair'], time: 2 },
          },
          partial: {
            text: [
              '손끝에 무언가 걸리지만 읽어낼 수 없다.',
              '역청이 손가락에 들러붙어 떨어지지 않는다.',
            ],
            effects: { time: 2 },
          },
          fail: {
            text: ['벽은 미끄럽고 균일하다. 아무것도 없다. 아무것도 없어야 한다.'],
            effects: { time: 2 },
          },
          fumble: {
            text: [
              '손끝이 벽의 틈에 들어간다. 그리고 그 안에서 무언가가 손가락을 감싼다.',
              '차갑고, 부드럽고, 힘이 없다. 뿌리치자 쉽게 떨어진다.',
              '램프를 비춘다. 틈은 비어 있다.',
            ],
            effects: { san: -3, danger: 1, time: 2 },
          },
        },
      },
      choices: [
        {
          id: 'wade_deep',
          label: '물살을 따라 안쪽으로 나아간다',
          keys: ['안쪽', '나아간다', '전진', '따라간다'],
          check: {
            stat: '체력',
            tags: ['이동', '탈출'],
            target: 13,
            label: '체력 판정',
            prompt: [
              '물이 가슴까지 온다. 천장은 더 낮아진다.',
              '남은 공간은 손바닥 두 개 높이다. 그 안에서 숨을 쉬며 나아가야 한다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '고개를 옆으로 눕히고 천장과 물 사이의 틈으로 숨을 쉰다.',
                '열 걸음, 스무 걸음. 그리고 갑자기 천장이 사라진다.',
                '넓은 공간이다. 소리가 되돌아오는 데 시간이 걸린다.',
              ],
              effects: { goto: 'gate_chamber' },
            },
            success: {
              text: [
                '물을 밀며 나아간다. 두 번 미끄러지고, 한 번은 완전히 잠긴다.',
                '천장이 트였을 때 폐가 뜨거웠다.',
              ],
              effects: { hp: -2, goto: 'gate_chamber' },
            },
            partial: {
              text: [
                '중간에서 램프가 꺼진다. 어둠 속에서 벽만 붙잡고 나아간다.',
                '얼마나 걸렸는지 알 수 없다. 트인 곳에 닿았을 때 몸이 떨리고 있었다.',
              ],
              effects: { hp: -3, san: -2, spend: { '역청 램프': 1 }, goto: 'gate_chamber' },
            },
            fail: {
              text: [
                '물이 코까지 올라온다. 되돌아갈지 나아갈지 판단할 시간이 3초뿐이었다.',
                '당신은 나아갔다. 마지막 열 걸음은 기억나지 않는다.',
              ],
              effects: { hp: -5, san: -2, danger: 1, goto: 'gate_chamber' },
            },
            fumble: {
              text: [
                '발이 바닥의 무언가에 걸린다. 부드럽고, 옷을 입고 있다.',
                '벗어나려 몸부림치다 완전히 잠긴다. 검은 물 속에서 위아래가 사라진다.',
                '누군가 당신의 옷깃을 잡아 끌어올린다.',
                '숨이 돌아왔을 때, 당신은 이미 트인 공간에 있었다. 누가 끌어올렸는지는 알 수 없다.',
              ],
              effects: { hp: -6, san: -3, danger: 2, goto: 'gate_chamber' },
            },
          },
        },
        {
          id: 'rope_across',
          label: '로프를 몸에 묶고 건넌다',
          keys: ['로프', '밧줄', '묶고', '묶는다'],
          requires: { items: ['등반 로프'] },
          hint: '힘이 아니라 버티는 문제가 된다',
          check: {
            stat: '의지',
            tags: ['탈출', '등반'],
            target: 13,
            label: '의지 판정',
            prompt: [
              '로프의 한쪽 끝을 수로 입구의 돌기에 묶고, 다른 쪽을 허리에 감는다.',
              '이제 이것은 힘의 문제가 아니다. 물이 얼굴을 덮을 때 손을 놓지 않는 문제다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '로프를 한 손씩 옮겨 잡으며 나아간다. 물이 얼굴을 덮을 때마다 세 번씩 센다.',
                '넷, 다섯, 여섯 번째에 천장이 사라진다.',
                '뒤를 돌아본다. 로프는 팽팽하게 어둠 속으로 이어져 있다. 돌아갈 길이 생겼다.',
              ],
              effects: { flags: { ropeLine: true }, goto: 'gate_chamber' },
            },
            success: {
              text: [
                '물이 두 번 얼굴을 덮는다. 두 번 다 손을 놓지 않았다.',
                '그것이 이 판정의 전부였다.',
              ],
              effects: { hp: -1, flags: { ropeLine: true }, goto: 'gate_chamber' },
            },
            partial: {
              text: [
                '중간에서 로프가 벽의 틈에 걸린다. 풀어내는 동안 물이 계속 밀려든다.',
                '풀어냈을 때는 이미 반쯤 정신이 나가 있었다.',
              ],
              effects: { hp: -2, san: -2, goto: 'gate_chamber' },
            },
            fail: {
              text: [
                '매듭이 허리에서 미끄러진다. 로프를 놓치고, 어둠 속에서 벽만 붙잡고 나아간다.',
                '트인 곳에 닿았을 때 로프는 뒤에 남아 있었다.',
              ],
              effects: { hp: -3, san: -1, removeItems: ['등반 로프'], goto: 'gate_chamber' },
            },
            fumble: {
              text: [
                '로프가 무언가에 걸리고, 걸린 채로 당겨진다. 당신이 당긴 것이 아니다.',
                '허리의 매듭이 조인다. 물속에서 몸이 뒤집힌다.',
                '칼로 로프를 끊고 나서야 숨을 쉴 수 있었다.',
              ],
              effects: {
                hp: -5,
                san: -2,
                danger: 1,
                removeItems: ['등반 로프'],
                goto: 'gate_chamber',
              },
            },
          },
        },
        {
          id: 'seal_lamp',
          label: '램프를 역청으로 봉해 물에 견디게 한다',
          keys: ['램프를 봉', '역청으로', '방수'],
          requires: { items: ['역청 램프'] },
          once: true,
          text: [
            '벽의 역청을 손톱으로 긁어 램프의 이음매에 눌러 바른다.',
            '조악하지만, 이 물건은 원래 이 재료로 만들어졌다.',
            '불이 물에 닿아도 꺼지지 않는다. 적어도 한 번은.',
          ],
          effects: { flags: { lampSealed: true }, time: 1 },
        },
        {
          id: 'steady_breath',
          label: '벽에 등을 대고 숨을 고른다',
          keys: ['숨', '쉰다', '진정', '멈춘다'],
          once: true,
          hint: '물은 그동안에도 차오른다',
          text: (state) => {
            const out = [
              '허리까지 잠긴 채로 벽에 등을 붙인다. 역청이 셔츠에 들러붙는다.',
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
          effects: { san: 4, time: 2, danger: 1 },
        },
        {
          id: 'mark_way',
          label: '돌아갈 길을 표시해 둔다',
          keys: ['표시', '길을 남', '표식'],
          once: true,
          text: [
            '손에 잡히는 것으로 벽에 자국을 낸다. 열 걸음마다 하나씩.',
            '나올 때 이 자국들이 있을지는 알 수 없다. 역청은 스스로 아문다.',
            '그래도 하지 않는 것보다는 낫다.',
          ],
          effects: { flags: { wayMarked: true }, time: 2, san: 1 },
        },
        {
          id: 'canal_back',
          label: '서고로 돌아간다',
          keys: ['돌아간다', '후퇴', '위로'],
          text: ['물살을 거슬러 오른다. 들어올 때보다 두 배가 힘들다.'],
          effects: { hp: -1, time: 2, goto: 'zigg_archive' },
        },
      ],
      freeform: [
        {
          keys: ['역청', '검은 물', '냄새'],
          text: [
            '역청은 이 땅이 스스로 뱉어내는 것이다. 배의 틈을 메우고, 벽돌을 붙이고, 시체를 감싼다.',
            '이 수로를 만든 사람들은 물이 새는 것을 몹시 두려워했던 것 같다.',
            '혹은, 무언가가 새어 나오는 것을.',
          ],
          effects: {},
        },
        {
          keys: ['소리', '듣는다', '귀'],
          text: [
            '숨을 멈추고 듣는다.',
            '물소리 아래에 다른 소리가 있다. 규칙적이고, 아주 느리다.',
            '세 번, 쉬고, 다시 세 번.',
          ],
          effects: { san: -2 },
        },
      ],
    },

    // ── 7. 문의 방 ─────────────────────────────────────────────
    gate_chamber: {
      id: 'gate_chamber',
      location: '수면 아래 · 문의 방',
      exits: ['수로'],
      onEnter(state, visits) {
        if (visits > 1) return {};
        return { danger: 2, san: -1 };
      },
      body: (state) => {
        const out = [
          '방은 원형이다. 룩소르의 그 방과 지름까지 같아 보인다.',
          '천장은 돔이고, 그 안쪽에 금속 조각이 박혀 있다. 별이다. 그리고 그 배열은 지금의 하늘이 아니다.',
          '벽 한 면에 문이 있다. 문 위의 원반은 이곳에서 더 크다. 사람 키만 하다.',
          '문 앞의 물은 얕다. 무릎 아래다. 방 전체가 물을 밀어내고 있는 것처럼.',
        ];
        if (state.clues.includes('wrong_sky')) {
          out.push(
            '당신은 천장을 올려다보며 오리온을 찾는다. 있다.',
            '그리고 그 위치는 룩소르의 돔에서 본 것과 정확히 같다.',
            '두 대륙의 두 천장이 같은 밤을 새기고 있다. 만 이천 년 전의 같은 밤을.',
          );
        }
        out.push(
          '문 앞 바닥에 장비가 널려 있다. 잠수 헬멧 하나. 공기 호스는 끊겨 있다.',
          '그리고 벽에 기대앉은 형태 하나. 이번에는 덮개가 없다.',
        );
        return out;
      },
      revisitBody: [
        '문의 방은 조용하다. 물이 무릎 아래에서 멈춰 있다.',
        '천장의 별들이 램프를 받아 아주 느리게 반짝인다.',
      ],
      ambientCheck: {
        label: '방을 살핀다',
        check: { stat: '관찰', tags: ['조사'], target: 14, label: '관찰 판정' },
        outcomes: {
          crit: {
            text: [
              '바닥에 홈이 파여 있다. 문에서 방 가장자리로, 방사형으로.',
              '배수구가 아니다. 반대다. 무언가를 문 쪽으로 흘려보내기 위한 홈이다.',
              '홈의 끝은 전부 문 아래로 사라진다.',
              '이 방은 무언가를 문에 먹이기 위해 만들어졌다.',
            ],
            effects: { san: -2, clues: ['gate_pair'], time: 2 },
          },
          success: {
            text: [
              '바닥에 방사형 홈이 파여 있다. 전부 문 쪽으로 기울어 있다.',
              '무언가를 문으로 흘려보내기 위한 구조다.',
            ],
            effects: { san: -2, time: 2 },
          },
          partial: {
            text: [
              '바닥에 무언가 파여 있지만 물과 진흙이 덮고 있다.',
              '손으로 걷어내다가 그만둔다. 걷어내고 싶지 않다는 마음이 먼저 왔다.',
            ],
            effects: { san: -1, time: 2 },
          },
          fail: {
            text: ['램프의 원 안쪽만 보인다. 그 바깥은 전부 같은 검은색이다.'],
            effects: { time: 2 },
          },
          fumble: {
            text: [
              '방을 한 바퀴 돌던 중, 당신은 자신의 발자국을 발견한다.',
              '아직 그쪽으로 가지 않았는데.',
            ],
            effects: { san: -4, time: 2 },
          },
        },
      },
      choices: [
        {
          id: 'gate_breathe',
          label: '벽에 등을 대고 숨을 고른다',
          keys: ['숨', '쉰다', '진정', '앉는다'],
          once: true,
          hint: '시간과 위험을 내주고 정신을 되찾는다',
          text: (state) => {
            const out = [
              '물이 무릎 아래에서 멈춰 있다. 그 자리에 그대로 선다.',
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
          id: 'examine_diver',
          label: '벽에 기댄 사람을 확인한다',
          keys: ['시신', '사람', '잠수', '확인'],
          once: true,
          check: {
            stat: '관찰',
            tags: ['의료', '조사'],
            target: 13,
            label: '검시 판정',
            prompt: ['가까이 가면서 당신은 이미 알고 있다. 이 자세는 앉은 것이 아니라 놓인 것이다.'],
          },
          outcomes: {
            crit: {
              text: [
                '크레인 원정대의 잠수부다. 익사가 아니다. 물은 여기까지 오지 않는다.',
                '손에 수첩이 쥐여 있다. 방수 케이스. 크레인은 준비가 철저한 사람이다.',
                '마지막 장 — "문은 하나가 아니다. 목록에 일곱이 적혀 있고 여덟 번째가 새로 새겨졌다."',
                '"새로 새겨졌다는 것은, 지금도 누군가 세고 있다는 뜻이다."',
                '그 아래에 좌표. 동쪽으로 더 멀리. 밀림.',
              ],
              effects: { clues: ['gate_pair', 'angkor_lead'], san: -2, time: 2 },
            },
            success: {
              text: [
                '크레인의 잠수부다. 익사는 아니다.',
                '손에 쥔 방수 수첩의 마지막 줄 — "문은 하나가 아니다."',
                '그 아래에 좌표가 하나. 동쪽.',
              ],
              effects: { clues: ['angkor_lead'], san: -2, time: 2 },
            },
            partial: {
              text: [
                '수첩은 얻었지만 케이스가 열리지 않는다. 손가락이 말을 듣지 않는다.',
                '나중에. 여기서 말고.',
              ],
              effects: { san: -2, flags: { hasSealedNotebook: true }, time: 2 },
            },
            fail: {
              text: [
                '당신은 그 얼굴을 보고, 아무것도 확인하지 못한 채 물러선다.',
                '확인하지 못한 것과 보지 않은 것은 다르다.',
              ],
              effects: { san: -2, time: 1 },
            },
            fumble: {
              text: [
                '헬멧의 유리를 닦는다. 안쪽에서.',
                '아니다. 안쪽은 닦을 수 없다. 그런데 당신의 손은 유리 안쪽에 있었다.',
                '뒤로 물러서다 물에 주저앉는다. 헬멧은 그대로 벽에 기대어 있다. 비어 있다.',
              ],
              effects: { san: -4, danger: 1, time: 2 },
            },
          },
        },
        {
          id: 'read_gate',
          label: '문의 원반을 해독한다',
          keys: ['원반', '해독', '문을 읽'],
          check: {
            stat: '신비',
            tags: ['신비', '해독'],
            target: 15,
            label: '신비 판정',
            prompt: [
              '원반 둘레에 띠가 있다. 룩소르에는 없던 것이다.',
              '띠에는 같은 기호가 반복된다. 문을 세는 기호가.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '띠의 기호를 센다. 일곱. 그리고 여덟 번째가 있다.',
                '여덟 번째는 다른 도구로, 다른 시대에 새겨졌다. 훨씬 최근에.',
                '문장이 읽힌다. — "문을 여는 자는 밖에서 오지 않는다. 문이 늘어나면, 그는 이미 안에 있다."',
                '그리고 마지막 줄. — "우리는 여섯 번째였다."',
              ],
              effects: {
                clues: ['gate_pair', 'door_opener', 'first_civilization'],
                flags: { gateRead: true },
                san: -2,
                time: 2,
              },
            },
            success: {
              text: [
                '띠의 기호는 문을 센다. 일곱, 그리고 뒤늦게 새겨진 여덟 번째.',
                '"문을 여는 자는 밖에서 오지 않는다."',
                '룩소르에서 읽은 것과 같은 문장이다. 다른 언어로.',
              ],
              effects: { clues: ['gate_pair', 'door_opener'], flags: { gateRead: true }, san: -2, time: 2 },
            },
            partial: {
              text: [
                '기호는 세어지는데 문장은 읽히지 않는다.',
                '세는 동안 몇 번이나 숫자를 놓쳤다. 일곱이었다가 아홉이었다가.',
              ],
              effects: { clues: ['gate_pair'], san: -2, time: 2 },
            },
            fail: {
              text: [
                '원반은 아무것도 내주지 않는다.',
                '오래 보면 볼수록, 보고 있는 쪽이 당신이 아닌 것 같다. 그래도 다시 볼 수는 있다.',
              ],
              effects: { time: 2 },
            },
            fumble: {
              text: [
                '당신의 손이 원반에 닿는다. 닿을 생각은 없었다.',
                '차가움이 팔을 타고 어깨까지 올라온다. 그리고 어깨에서 멈추지 않는다.',
                '문 안쪽에서 무언가가 자세를 바꾼다. 아주 크고, 아주 조용하게.',
                '물이 문 쪽으로 빨려 들어가기 시작한다. 바닥의 홈을 따라서.',
              ],
              effects: { san: -4, danger: 4, flags: { gateStirred: true }, time: 2 },
            },
          },
        },
        {
          id: 'take_seal',
          label: '문 옆 벽감의 각인판을 꺼낸다',
          keys: ['각인', '벽감', '꺼낸다', '유물'],
          once: true,
          hint: '핵심 유물',
          check: {
            stat: '민첩',
            tags: ['함정', '잠입'],
            target: 14,
            label: '민첩 판정',
            prompt: [
              '벽감에 청동판이 하나 놓여 있다. 문의 목록이 새겨져 있다.',
              '받침이 물에 잠겨 있다. 무게를 재는 장치가 물속에서도 작동하는지는 알 수 없다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '한 손으로 각인판을 들면서 다른 손으로 젖은 진흙을 받침에 눌러 넣는다.',
                '받침은 움직이지 않는다. 방은 조용하다.',
                '각인판은 무겁고, 가장자리에 좌표가 새겨져 있다. 동쪽. 밀림.',
                '그리고 뒷면에 이집트의 그 열쇠와 맞물리는 홈이 있다.',
              ],
              effects: { items: ['문의 각인'], clues: ['angkor_lead', 'gate_pair'], time: 1 },
            },
            success: {
              text: [
                '각인판을 들어 올린다. 받침이 올라오고, 물속에서 둔한 소리가 난다.',
                '아무 일도 일어나지 않는다. 아직은.',
                '가장자리의 좌표가 동쪽을 가리킨다.',
              ],
              effects: { items: ['문의 각인'], clues: ['angkor_lead'], danger: 1, time: 1 },
            },
            partial: {
              text: [
                '각인판은 손에 들어왔다. 대신 물이 다시 밀려든다.',
                '무릎에서 허벅지로. 이 방은 더 이상 물을 밀어내지 않는다.',
              ],
              effects: { items: ['문의 각인'], clues: ['angkor_lead'], danger: 2, hp: -1, time: 1 },
            },
            fail: {
              text: [
                '받침이 완전히 올라온다. 벽 안에서 무거운 것이 굴러간다.',
                '문 위의 원반이 아주 잠깐 더 검어지고, 물이 문 쪽으로 흐르기 시작한다.',
                '각인판은 손에 있다. 값은 나중에 청구될 것이다.',
              ],
              effects: {
                items: ['문의 각인'],
                clues: ['angkor_lead'],
                danger: 3,
                san: -2,
                flags: { gateStirred: true },
                time: 1,
              },
            },
            fumble: {
              text: [
                '손이 미끄러진다. 각인판이 물에 떨어지며 받침을 통째로 밀어낸다.',
                '방 전체가 한 번 기울고, 천장의 별 몇 개가 물로 떨어진다.',
                '각인판은 건졌다. 물은 이제 허리까지 왔다.',
                '그리고 문 아래 틈에서, 물이 아닌 무언가가 흘러나오고 있다.',
              ],
              effects: {
                items: ['문의 각인'],
                clues: ['angkor_lead'],
                hp: -4,
                san: -3,
                danger: 4,
                flags: { gateStirred: true },
                time: 1,
              },
            },
          },
        },
        {
          id: 'match_key',
          label: '이집트의 열쇠를 각인판에 맞춰 본다',
          keys: ['열쇠', '맞춘다', '끼운다', '결합'],
          requires: { items: ['문의 각인', '검은 태양의 열쇠'] },
          hideIfLocked: true,
          once: true,
          hint: '두 유물이 만난다',
          text: [
            '열쇠의 뒷면과 각인판의 홈이 맞물린다. 소리 없이, 저항 없이.',
            '두 유물은 서로를 위해 만들어졌다. 대륙 두 개와 천 년을 사이에 두고.',
            '맞물린 순간 둘 다 차가워진다. 손이 아니라 팔꿈치까지.',
            '그리고 당신은 이것이 열쇠가 아니라는 것을 이해한다.',
            '이것은 자물쇠의 절반이다. 누군가 이 문을 잠그기 위해 두 대륙에 나눠 숨긴 것이다.',
          ],
          effects: {
            clues: ['first_civilization', 'gate_pair'],
            flags: { keyMatched: true },
            san: -2,
            time: 2,
          },
        },
        {
          id: 'leave_gate',
          label: '더 건드리지 않고 물러난다',
          keys: ['나간다', '물러', '돌아', '포기'],
          hint: '가지고 나온 것만이 당신의 것이 된다',
          text: [
            '당신은 문에서 등을 돌린다.',
            '룩소르에서도 같은 선택을 한 적이 있다면, 이번에는 더 쉬웠을 것이다.',
            '더 쉽지 않았다.',
          ],
          effects: { goto: 'crane_reckoning' },
        },
      ],
      freeform: [
        {
          keys: ['천장', '별', '하늘'],
          text: [
            '천장의 별을 센다. 룩소르에서 세던 것과 같은 배열이다.',
            '두 개의 돔이 같은 밤을 기억하고 있다. 누구도 그 밤을 본 적이 없는데.',
          ],
          effects: { san: -2, clues: ['wrong_sky'] },
        },
        {
          keys: ['문을 민다', '연다', '두드'],
          text: [
            '문에 손바닥을 댄다. 밀리지 않는다.',
            '그러나 미는 힘에 대해 문이 아주 미세하게 반응한다. 밀려나는 것이 아니라, 응하는 방식으로.',
            '당신은 손을 뗀다.',
          ],
          effects: { san: -2, danger: 1 },
        },
      ],
    },

    // ── 8. 재대면 ──────────────────────────────────────────────
    crane_reckoning: {
      id: 'crane_reckoning',
      location: '기단 아래 · 수로 입구',
      exits: ['위로'],
      onEnter(state, visits) {
        if (visits > 1) return {};
        return { danger: 1 };
      },
      body: (state) => {
        const out = [];
        if (state.flags.craneAlly) {
          out.push(
            '수로 입구에 램프가 걸려 있다. 사람이 아니라 램프만.',
            '그 아래 방수포에 싸인 짐과 쪽지 하나.',
            '"먼저 올라갑니다. 물이 차기 시작했습니다. — A.C."',
            '"내 사람 하나가 저 아래 남았습니다. 데리고 나오지 못했습니다."',
            '"당신이 무엇을 봤든, 밖에서 이야기합시다. 이번에는 총을 들지 않겠습니다."',
          );
        } else {
          out.push(
            '수로 입구에 램프 다섯 개가 걸려 있다.',
            '아셔 크레인이 물속에 무릎까지 담근 채 서 있다. 모자는 없다. 이번에는 젖어 있다.',
            '"나올 줄 알았습니다." 그가 말한다. "저 아래에서 나온 사람은 당신이 두 번째입니다."',
            '"첫 번째는 내 조카였고, 그 애는 이집트에서 나왔죠. 여기서는 아무도 나오지 못했습니다."',
          );
          if (state.inventory.some((i) => i.name === '문의 각인')) {
            out.push('"그 손에 든 것을 봅니다. 이번에도 같은 대화를 해야 합니까?"');
          }
        }
        out.push('물이 발목에서 종아리로 올라오고 있다. 대화에 쓸 시간은 길지 않다.');
        return out;
      },
      revisitBody: ['수로 입구는 조용하다. 물만 계속 올라온다.'],
      choices: [
        {
          id: 'share_findings',
          label: '알아낸 것을 전부 말한다',
          keys: ['말한다', '공유', '전부', '알려준다'],
          check: {
            stat: '설득',
            tags: ['사교', '정보'],
            target: 14,
            bonusLabel: '증거',
            bonus: 0,
            label: '설득 판정',
            prompt: [
              '당신은 수첩을 편다. 왕 목록. 문의 수. 두 대륙의 같은 손.',
              '크레인의 램프가 종이 위로 기운다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '크레인은 끝까지 듣는다. 그리고 자기 가방에서 종이 뭉치를 꺼내 물 위 벽돌에 올린다.',
                '런던 박물관 지하 보관고의 목록. 반출 기록. 그리고 반출한 적 없는 물건들의 목록.',
                '"우리 쪽이 가진 것은 이겁니다. 당신 쪽이 가진 것은 방금 들었고요."',
                '"나는 이걸 독점하려고 왔습니다. 지금은 그냥 살아서 나가고 싶습니다."',
                '그가 손을 내민다. "다음은 동쪽이라고 하셨죠. 배는 내가 냅니다."',
              ],
              effects: {
                clues: ['angkor_lead'],
                flags: { craneAlly: true, craneAllied2: true },
                goto: 'basra_finale',
              },
            },
            success: {
              text: [
                '크레인이 오래 침묵한다. 물이 그의 무릎을 넘는다.',
                '"…여덟 번째 문." 그가 되뇐다. "그건 우리 기록에도 없었습니다."',
                '"길은 비켜드리죠. 이 이야기는 밖에서 계속합시다."',
              ],
              effects: { flags: { craneAlly: true }, goto: 'basra_finale' },
            },
            partial: {
              text: [
                '크레인은 절반만 믿는다. 절반만으로도 그는 움직인다.',
                '"증거의 절반을 두고 가십시오. 나머지 절반은 당신이 가지고요."',
                '당신은 점토판 몇 장을 그의 손에 놓는다.',
              ],
              effects: { removeItems: ['점토 원통'], goto: 'basra_finale' },
            },
            fail: {
              text: [
                '"당신은 지금 사천 년 전 사람들이 사람이 아니었다고 말하고 있습니다."',
                '크레인이 손을 든다. 램프 두 개가 앞으로 나온다.',
                '"그 손에 든 것부터 내려놓으시죠."',
              ],
              effects: { danger: 2, goto: 'reckoning_break' },
            },
            fumble: {
              text: [
                '당신은 그의 조카 이야기를 꺼냈다. 위로하려던 것이었다.',
                '크레인의 얼굴에서 표정이 사라진다.',
                '"그 애 이름을 당신 입으로 부르지 마십시오."',
                '물소리 위로 공이치기 소리가 난다.',
              ],
              effects: { danger: 3, goto: 'reckoning_break' },
            },
          },
        },
        {
          id: 'trade_seal',
          label: '각인판을 넘기고 좌표만 챙긴다',
          keys: ['넘긴다', '거래', '준다', '각인판을'],
          requires: { items: ['문의 각인'] },
          text: [
            '당신은 각인판을 물 위 벽돌에 올려놓는다.',
            '크레인이 그것을 집어 든다. 램프 아래에서 가장자리의 좌표를 확인하고, 손이 멈춘다.',
            '"…동쪽." 그가 중얼거린다. "당신도 봤군요."',
            '"가십시오. 물이 차고 있습니다."',
            '각인판은 잃었다. 좌표는 이미 당신의 수첩에 있다.',
          ],
          effects: {
            removeItems: ['문의 각인'],
            clues: ['angkor_lead'],
            flags: { craneHasSeal: true },
            goto: 'basra_finale',
          },
        },
        {
          id: 'warn_water',
          label: '물이 차고 있다고 알리고 함께 나간다',
          keys: ['물', '경고', '함께', '나가자'],
          check: {
            stat: '의지',
            tags: ['사교'],
            target: 12,
            label: '의지 판정',
            prompt: [
              '당신은 각인판도 수첩도 꺼내지 않는다.',
              '대신 수로 안쪽을 가리킨다. 물이 밀려오는 쪽을.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '크레인이 뒤를 돌아본다. 그리고 자기 사람들에게 짧게 명령한다.',
                '"전원 철수. 장비는 버려."',
                '좁은 계단에서 여덟 명이 한 줄로 오른다. 아무도 밀지 않는다.',
                '밖으로 나왔을 때, 그가 당신의 어깨를 한 번 친다. 그게 전부였고, 충분했다.',
              ],
              effects: { flags: { craneAlly: true, savedCrane: true }, goto: 'basra_finale' },
            },
            success: {
              text: [
                '크레인이 물을 본다. 그리고 램프를 든 사람들에게 손짓한다.',
                '"올라갑니다."',
                '대화는 없었다. 대화가 필요 없는 종류의 합의였다.',
              ],
              effects: { flags: { craneAlly: true }, goto: 'basra_finale' },
            },
            partial: {
              text: [
                '"물은 원래 찹니다." 그가 말한다. 그러나 그의 사람들은 이미 뒤를 보고 있다.',
                '대열이 흐트러진다. 당신은 그 틈으로 나간다.',
              ],
              effects: { goto: 'basra_finale' },
            },
            fail: {
              text: [
                '"수작 부리지 마십시오."',
                '크레인이 당신의 시선을 따라가지 않는다. 훈련된 사람이다.',
                '"그 손에 든 것부터."',
              ],
              effects: { danger: 2, goto: 'reckoning_break' },
            },
            fumble: {
              text: [
                '당신이 손을 든 순간, 뒤쪽 사람 하나가 반사적으로 총을 든다.',
                '좁은 수로에서 격발음은 소리가 아니라 충격이다.',
                '탄은 빗나갔다. 대신 천장 벽돌이 무너져 내린다.',
              ],
              effects: { hp: -3, danger: 3, goto: 'reckoning_break' },
            },
          },
        },
        {
          id: 'slip_past',
          label: '램프를 끄고 어둠 속으로 빠져나간다',
          keys: ['불을 끈다', '어둠', '몰래', '빠져나'],
          check: {
            stat: '민첩',
            tags: ['잠입', '탈출'],
            target: 14,
            bonus: 2,
            bonusLabel: '표시해 둔 길',
            label: '잠입 판정',
            prompt: [
              '당신은 램프의 심지를 손가락으로 눌러 끈다.',
              '어둠은 그들에게도 똑같이 어둡다. 다만 당신은 이 길을 한 번 지나왔다.',
            ],
          },
          outcomes: {
            crit: {
              text: [
                '벽을 짚고 물속을 걷는다. 소리를 내지 않는 방법은 천천히 가는 것뿐이다.',
                '램프 다섯 개가 당신이 있던 자리를 비춘다. 당신은 이미 거기 없다.',
                '계단에 발이 닿았을 때, 위에서 갈대 냄새가 내려왔다.',
              ],
              effects: { flags: { escapedClean2: true }, goto: 'basra_finale' },
            },
            success: {
              text: [
                '두 번 부딪히고 한 번 넘어진다. 물소리에 묻힌다.',
                '뒤에서 고함이 들렸을 때는 이미 계단이었다.',
              ],
              effects: { hp: -1, goto: 'basra_finale' },
            },
            partial: {
              text: [
                '중간에 램프 빛이 어깨를 스친다. 당신은 물속으로 몸을 낮춘다.',
                '차가운 물이 목까지 찬다. 빛이 지나갈 때까지 그대로 있는다.',
              ],
              effects: { hp: -2, san: -1, goto: 'basra_finale' },
            },
            fail: {
              text: [
                '어둠 속에서 방향을 잃는다. 벽을 짚고 돌다가 램프 앞으로 나온다.',
                '"거기 계셨군요." 크레인의 목소리는 놀라지 않았다.',
              ],
              effects: { danger: 2, goto: 'reckoning_break' },
            },
            fumble: {
              text: [
                '발이 잠수부의 장비에 걸린다. 금속이 벽돌에 부딪히는 소리가 수로를 채운다.',
                '램프 다섯 개가 동시에 돌아온다.',
              ],
              effects: { danger: 3, san: -1, goto: 'reckoning_break' },
            },
          },
        },
      ],
      freeform: [
        {
          keys: ['조카', '홀트'],
          text: [
            '홀트라는 이름을 꺼낼지 말지, 당신은 3초 동안 고민한다.',
            '크레인은 그 3초를 알아본다. "…말씀하십시오."',
          ],
          effects: {},
        },
      ],
    },

    // ── 8-b. 결렬 ──────────────────────────────────────────────
    // crane_flooded 조우. 물이 차는 계단은 왕가의 계곡의 통로와 같은 규칙 위에서
    // 다르게 읽힌다 — 압박이 빠르고, 협상이 쉽고, 도주가 어렵다.
    reckoning_break: {
      id: 'reckoning_break',
      location: '기단 아래 · 무너지는 계단',
      exits: ['위로'],
      combat: 'crane_flooded',
      body: ['물이 한 단 더 올라온다.'],
      revisitBody: ['계단은 비어 있다. 물만 계속 오른다.'],
      choices: [
        {
          id: 'break_leave',
          label: '계단을 올라 밖으로 나간다',
          keys: ['나간다', '위로', '오른다'],
          text: ['젖은 계단을 한 단씩 오른다. 뒤에서 물소리가 따라온다.'],
          effects: { goto: 'basra_finale' },
        },
      ],
    },

    // ── 9. 마무리 ──────────────────────────────────────────────
    basra_finale: {
      id: 'basra_finale',
      location: '서쪽 언덕 · 갈대밭 가장자리',
      exits: [],
      onEnter(state) {
        const waited = state.companions.basim
          ? (state.companions.basim.trust || 0) >= 2
          : false;
        return { flags: { basimWaited: waited }, danger: -3 };
      },
      body: (state) => {
        const out = [
          '기단 위로 나오자 물소리가 멀어진다.',
          '동쪽 하늘이 회색으로 밝아 온다. 밤을 통째로 아래에서 보냈다.',
          '뒤를 돌아본다. 언덕은 다시 언덕처럼 보인다. 물이 계단을 덮고 있다.',
          '올해의 계절은 끝났다. 저 아래는 다시 몇 년쯤 물속에 있을 것이다.',
        ];
        if (state.flags.basimWaited) {
          out.push(
            '갈대 사이에 배 한 척이 떠 있다. 바심이 장대에 기대 앉아 졸고 있다.',
            '인기척에 눈을 뜨고, 당신들의 몰골을 본다.',
            '"…어머니께는 말하지 않겠습니다." 그가 배를 대며 말한다.',
          );
        } else if (state.companions.basim) {
          out.push(
            '배는 없다. 밧줄을 묶었던 자리에 매듭 자국만 남아 있다.',
            '바심은 아침까지 기다린다고 했다. 아침이 되었으니, 그는 약속을 지킨 것이다.',
          );
        }
        if (state.companions.seraphina?.present) {
          out.push(
            '세라피나가 젖은 종이 뭉치를 품에서 꺼내 갈대 위에 하나씩 펼친다.',
            '"마르면 읽을 수 있습니다." 그녀가 말한다. "저는 마르기를 기다리는 일을 잘합니다."',
          );
        }
        return out;
      },
      choices: [
        {
          id: 'write_log2',
          label: '수첩에 오늘의 기록을 남긴다',
          keys: ['수첩', '기록', '적는다'],
          once: true,
          text: (state) => {
            const lines = ['갈대에 등을 대고 앉아 수첩을 편다. 손이 아직 떨린다.'];
            if (state.clues.includes('first_civilization')) {
              lines.push(
                '한 문장을 적는다. — 문명은 여러 번 시작되었고, 여러 번 끝났다.',
                '그리고 그 아래에 한 줄 더 적었다가, 지운다.',
                '지운 자리에 자국이 남는다. "우리는 여섯 번째다."',
              );
            } else if (state.clues.includes('flood_before')) {
              lines.push('한 문장만 적는다. — 홍수 이전에도 왕이 있었다.');
            } else {
              lines.push(
                '무엇을 적어야 할지 모르겠다.',
                '본 것은 많은데, 문장이 되는 것은 하나도 없다.',
              );
            }
            return lines;
          },
          effects: { san: 3 },
        },
        {
          id: 'thank_party',
          label: '동행에게 셈을 치른다',
          keys: ['셈', '보수', '인사', '고맙'],
          once: true,
          text: (state) => {
            const out = [];
            if (state.companions.basim?.present) {
              out.push(
                '바심은 값을 세 배 부르지 않았다. 두 배만 받고, 나머지는 손을 저었다.',
                '"저 아래는 제 값에 안 들어갑니다."',
              );
            }
            if (state.companions.seraphina?.present) {
              out.push(
                '세라피나는 봉투를 받지 않는다.',
                '"저는 12년을 기다렸습니다. 이건 임금을 받을 일이 아니에요."',
                '그리고 잠시 뒤 덧붙인다. "다음에도 부르십시오. 어디든."',
              );
            }
            if (state.companions.nadia?.present) {
              out.push(
                '나디아가 갈대를 한 가닥 꺾어 손에 쥔다.',
                '"룩소르의 갈대랑 다르네요." 그것이 그녀가 한 말 전부였다.',
              );
            }
            if (!out.length) out.push('셈을 치를 사람이 없다. 당신은 혼자 갈대밭에 앉아 있다.');
            return out;
          },
          effects: {
            san: 1,
            companionChanges: [
              { id: 'basim', affinity: 1 },
              { id: 'seraphina', affinity: 1 },
              { id: 'nadia', affinity: 1 },
            ],
          },
        },
        {
          id: 'end_episode2',
          label: '바스라로 돌아간다',
          keys: ['돌아간다', '바스라', '떠난다', '마친다'],
          text: ['갈대가 배 뒤로 닫힌다. 언덕이 보이지 않게 될 때까지 아무도 말하지 않았다.'],
          effects: { goto: 'basra_epilogue' },
        },
      ],
      freeform: [
        {
          keys: ['해', '아침', '하늘'],
          text: [
            '해가 갈대 위로 올라온다. 빛이 물에 부딪혀 흩어진다.',
            '두 번째다. 유적에서 나와 아침을 보는 것이.',
            '세 번째가 있을 것이라는 예감은, 위로가 되지 않는다.',
          ],
          effects: { san: 1 },
        },
      ],
    },

    basra_epilogue: {
      id: 'basra_epilogue',
      location: '바스라 · 샤트알아랍',
      exits: [],
      body: (state) => {
        const out = [
          '증기선이 강을 내려간다. 두 강이 하나가 된 물 위를.',
          '갑판에서 당신은 지난 한 달을 센다. 이집트에서 여기까지, 그리고 여기서 어디로.',
        ];
        if (state.flags.craneAllied2 || state.flags.savedCrane) {
          out.push(
            '크레인은 알렉산드리아행 배를 탔다. 헤어지기 전에 그가 봉투 하나를 건넸다.',
            '동쪽 항로의 선표 두 장. 그리고 쪽지. "먼저 가 있겠습니다. 이번에는 같은 편으로."',
          );
        } else if (state.flags.craneHasSeal) {
          out.push(
            '크레인은 각인판을 가졌고, 당신은 좌표를 가졌다.',
            '어느 쪽이 먼저 도착할지는 아직 모른다. 다만 둘 다 같은 곳으로 간다.',
          );
        } else if (state.flags.escapedClean2) {
          out.push('크레인은 당신이 무엇을 들고 나왔는지 모른다. 이번에도.');
        }
        if (state.clues.includes('first_civilization')) {
          out.push(
            '수첩에는 이제 두 대륙의 기록이 나란히 붙어 있다.',
            '그리고 그 사이에 당신이 적은 한 문장이 있다. 지웠다가 다시 적은 문장이.',
          );
        }
        out.push(
          '동쪽으로 더 멀리. 밀림이 삼킨 회랑.',
          '거기에도 돔이 있을 것이고, 돔에는 같은 밤이 새겨져 있을 것이다.',
        );
        return out;
      },
      end: {
        type: 'chapter',
        next: 'angkor',
        title: '에피소드 2 종료 — 두 강 사이의 문',
        text:
          '다음 목적지: 앙코르. 밀림이 삼킨 회랑.\n\n' +
          '「문을 여는 자는 밖에서 오지 않는다.\n문이 늘어나면, 그는 이미 안에 있다.」\n— 문의 방, 원반의 띠',
      },
      choices: [],
    },
  },
};

export default ep;
