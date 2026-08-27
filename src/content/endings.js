// 결말.
//
// 캠페인의 끝은 마지막 선택 하나로 정해지지 않는다. 세 대륙을 지나오며 무엇을 알아냈고,
// 누구를 잃지 않았고, 무엇을 손에 쥐고 있는지가 함께 정한다.
//
// 각 결말은 조건(when)을 갖고, 목록의 위에서부터 처음 맞는 것이 선택된다.
// 그래서 순서가 곧 우선순위다 — 특수한 것이 위에, 기본이 아래에.
//
// coda 는 상태를 읽어 마지막 몇 줄을 덧붙인다. 같은 결말이라도 혼자 도착한 사람과
// 셋이 도착한 사람이 같은 문장으로 끝나서는 안 된다.

import { subj, and } from '../korean.js';

const has = (state, clue) => state.clues.includes(clue);
const holds = (state, item) => state.inventory.some((i) => i.name === item);
const alive = (state, id) => !!state.companions[id]?.present;

export const ENDINGS = [
  {
    id: 'sealed',
    title: '여덟 번째 문은 닫힌 채로 남았다',
    when: (state) => state.flags.gateSealed,
    text:
      '두 조각을 맞물려 원반에 끼운 순간, 그것이 열쇠가 아니라는 것이 손끝으로 전해졌다.\n' +
      '자물쇠였다. 누군가 오래전에 반으로 갈라 두 대륙에 숨겨 둔 자물쇠.\n\n' +
      '문이 닫히는 소리는 나지 않았다. 대신 회랑 전체가 한 번 숨을 내쉬었고,\n' +
      '그 뒤로는 아무 소리도 나지 않았다.\n\n' +
      '당신은 이제 닫는 쪽의 사람이 되었다. 아무도 그것을 알아주지 않을 것이다.\n' +
      '그것이 이 일의 조건이라는 것을, 회랑을 나오면서 이해했다.',
  },
  {
    id: 'opened',
    title: '문은 안에서 열렸다',
    when: (state) => state.flags.gateOpened,
    text:
      '당신은 밀지 않았다. 문장이 말한 대로, 손바닥을 대고 기다렸다.\n' +
      '차가움이 팔을 타고 올라와 어깨에서 멈추지 않았다.\n\n' +
      '문 너머에는 계단이 없었다. 회랑이 있었다.\n' +
      '당신이 방금 걸어온 것과 똑같은 회랑이. 다만 아직 밀림이 삼키지 않은.\n\n' +
      '그리고 그 회랑 저편에서, 누군가 거리와 각도와 날짜를 적고 있었다.\n' +
      '고개를 들지 않은 채로, 그가 말했다. — "여덟 번째로군."',
  },
  {
    id: 'exposed',
    title: '학회는 그것을 정중하게 거절했다',
    when: (state) =>
      state.flags.wentPublic && has(state, 'first_civilization') && has(state, 'third_record'),
    text:
      '1898년 3월, 왕립 지리학회 대강당.\n' +
      '세 대륙의 탁본이 나란히 걸렸고, 같은 문체가 세 번 반복되는 것을 모두가 보았다.\n\n' +
      '질문은 두 개뿐이었다. 출처가 확실한가. 그리고 — 이것으로 무엇을 하자는 것인가.\n\n' +
      '기록은 학회지 부록에 실렸다. 부록은 아무도 읽지 않는다.\n' +
      '그러나 그해 겨울, 세 통의 편지가 도착했다. 리마에서, 아테네에서, 그리고 호바트에서.\n' +
      '전부 같은 문장으로 시작했다. — "우리 쪽에도 하나 있습니다."',
  },
  {
    id: 'kept',
    title: '수첩은 금고에 들어갔다',
    when: (state) => has(state, 'first_civilization') || has(state, 'third_record'),
    text:
      '증거는 충분했다. 발표하지 않기로 한 것은 증거가 부족해서가 아니었다.\n\n' +
      '당신은 세 대륙의 기록을 한 권으로 묶어 은행 금고에 넣었다.\n' +
      '열쇠는 둘로 만들어 하나를 다른 도시에 두었다.\n\n' +
      '그것이 옳은 일인지는 모른다. 다만 문을 여는 자는 밖에서 오지 않는다는 문장을\n' +
      '읽은 이상, 아무에게나 지도를 줄 수는 없었다.\n\n' +
      '가끔 밤에 그 금고를 생각한다. 그리고 여덟 번째 문이 아직 거기 있다는 것도.',
  },
  {
    id: 'walked_away',
    title: '당신은 회랑에서 걸어 나왔다',
    when: () => true, // 마지막 그물. 아무 조건도 못 맞춘 사람도 결말은 갖는다
    text:
      '밀림은 당신이 들어갈 때와 똑같이 시끄러웠다.\n' +
      '매미, 새, 이름 모르는 것들. 아무것도 달라지지 않았다.\n\n' +
      '손에 쥔 것은 몇 장의 탁본과, 증명되지 않는 확신 하나뿐이다.\n' +
      '그것을 들고 런던으로 돌아가면 사람들은 정중하게 웃을 것이다.\n\n' +
      '그래도 당신은 그 문 앞에 서 봤다.\n' +
      '서 봤다는 것과 읽었다는 것은 다르지만, 아무것도 아닌 것보다는 낫다.',
  },
];

/** 상태에 맞는 결말을 고른다. 위에서부터 처음 맞는 것. */
export function resolveEnding(state) {
  return ENDINGS.find((e) => e.when(state)) || ENDINGS[ENDINGS.length - 1];
}

/**
 * 결말 뒤에 붙는 몇 줄. 누가 남았고 무엇을 쥐고 있는지를 읽는다.
 * 같은 결말이라도 혼자 도착한 사람과 셋이 도착한 사람이 같은 문장으로 끝나지 않는다.
 */
export function endingCoda(state) {
  const lines = [];

  const survivors = Object.values(state.companions).filter((c) => c.present);
  if (survivors.length >= 3) {
    lines.push(
      `${survivors.map((c) => c.name).join(', ')}.`,
      `${survivors.length}명 전부 제 발로 걸어 나왔다.`,
      '이 탐사에서 가장 있을 법하지 않은 결과가 그것이다.',
    );
  } else if (survivors.length === 2) {
    lines.push(`${and(survivors[0].name)} ${subj(survivors[1].name)} 함께 나왔다.`);
  } else if (survivors.length === 1) {
    lines.push(`${subj(survivors[0].name)} 끝까지 옆에 있었다.`);
  } else {
    lines.push('나올 때 당신은 혼자였다. 들어갈 때는 아니었다.');
  }

  const fallen = Object.values(state.companions).filter((c) => !c.present);
  if (fallen.length) {
    lines.push(
      `돌아오지 못한 이름을 적는다. ${fallen.map((c) => c.name).join(', ')}.`,
      '수첩의 그 장은 다시 펴지 않는다.',
    );
  }

  if (alive(state, 'crane')) {
    lines.push('크레인은 알렉산드리아행 배를 탔다. 헤어질 때 악수는 하지 않았다.');
  } else if (state.flags.craneAlly) {
    lines.push('크레인의 마지막 전보는 사이공에서 끊겼다. 그 뒤로 소식이 없다.');
  }

  if (holds(state, '검은 태양의 열쇠') && holds(state, '문의 각인')) {
    lines.push('두 조각은 아직 당신에게 있다. 맞물린 채로, 서로 떨어지지 않는다.');
  }

  if (has(state, 'who_counts')) {
    lines.push(
      '그리고 가끔, 거리와 각도와 날짜를 적는 자기 손을 내려다보다가',
      '그 필체가 누구의 것인지 잠깐 헷갈린다.',
    );
  }

  // 마지막 줄에 이름을 적는다. 기록이란 결국 누가 다녀갔는지를 남기는 일이고,
  // 이 판을 굴린 사람의 이름은 여기 말고 적힐 자리가 없다.
  const who = state.char?.name;
  lines.push(
    `단서 ${state.clues.length}개. 세 대륙. 1897년 겨울.`,
    who ? `기록자: ${who}, ${state.char.profession}.` : '기록자의 이름은 비어 있다.',
  );
  return lines;
}
