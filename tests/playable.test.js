// 실제로 화면에 뜨는 선택지를 센다.
//
// 콘텐츠 파일에 선택지를 네 개 적어 두어도, 그중 셋이 조건부라면
// 플레이어는 하나만 본다. 정적 개수가 아니라 GM 이 내주는 개수를 세야 한다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { createState } from '../src/engine/state.js';
import { createGM } from '../src/engine/gm.js';
import { advanceEpisode } from '../src/engine/campaign.js';
import { EPISODES, FIRST_EPISODE } from '../src/content/episodes/index.js';
import { PROFESSIONS } from '../src/content/professions.js';

/** 해당 에피소드에 막 도착한, 아무것도 모르는 탐사자의 상태. */
function freshFor(episodeId, professionId) {
  const state = createState({ professionId, seed: 1 });
  createGM({ state, episode: EPISODES[FIRST_EPISODE] }).start();
  if (episodeId !== FIRST_EPISODE) {
    while (state.episode !== episodeId) {
      const moved = advanceEpisode(state);
      if (!moved.ok) break;
      createGM({ state, episode: moved.episode }).start();
    }
  }
  return state;
}

test('어느 장면에서도 선택지가 3개 미만으로 내려가지 않는다', () => {
  for (const ep of Object.values(EPISODES)) {
    for (const [id, scene] of Object.entries(ep.scenes)) {
      if (scene.end) continue; // 결말 장면은 종료 버튼만 있으면 된다

      const state = freshFor(ep.id, 'archaeologist');
      const gm = createGM({ state, episode: ep });
      gm.enterScene(id, []);

      const open = gm.choices().filter((c) => !c.locked);
      assert.ok(
        open.length >= 3,
        `${ep.id}/${id}: 아무것도 모르는 상태에서 선택지가 ${open.length}개뿐`,
      );
    }
  }
});

test('어느 직업으로 들어와도 장면이 막히지 않는다', () => {
  for (const ep of Object.values(EPISODES)) {
    for (const [id, scene] of Object.entries(ep.scenes)) {
      if (scene.end) continue;
      for (const prof of PROFESSIONS) {
        const state = freshFor(ep.id, prof.id);
        const gm = createGM({ state, episode: ep });
        gm.enterScene(id, []);
        const open = gm.choices().filter((c) => !c.locked);
        assert.ok(
          open.length >= 3,
          `${ep.id}/${id}: ${prof.name} 로는 선택지가 ${open.length}개뿐`,
        );
      }
    }
  }
});

test('장면이 소진되지 않는다', () => {
  // 소프트락 방지. 어떤 장면이든 (a) 지금 바로 나갈 수 있는 선택지가 있거나,
  // (b) 몇 번이고 다시 시도할 수 있는 선택지가 남아 있어야 한다.
  // 한 번뿐인 선택지만 남은 장면은 전부 써버리면 갇힌다.
  for (const ep of Object.values(EPISODES)) {
    for (const [id, scene] of Object.entries(ep.scenes)) {
      if (scene.end) continue;

      const state = freshFor(ep.id, 'patron'); // 능력치가 가장 치우친 직업
      const gm = createGM({ state, episode: ep });
      gm.enterScene(id, []);
      const openIds = new Set(gm.choices().filter((c) => !c.locked).map((c) => c.id));

      // 나아가는 선택지: 지금 바로 장면을 옮기거나, 다시 시도할 수 있는 판정으로
      // 잠긴 문을 여는 플래그를 세운다. 되돌아가기만 되는 선택지는 진행이 아니다.
      // 전투 장면은 조우의 출구가 길을 낸다 (combat.test.js 가 검사한다).
      if (scene.combat) continue;

      const progressing = (scene.choices || []).some((c) => {
        if (!openIds.has(c.id)) return false;
        const branches = Object.values(c.outcomes || {});
        const leaves = [c.goto, c.effects?.goto, ...branches.flatMap((b) => [b.goto, b.effects?.goto])];
        const forward = leaves.filter(Boolean).some((t) => t !== id);
        if (forward) return true;
        // 반복 가능한 조사 판정이 무언가를 열어 주는가
        const opensSomething = branches.some((b) => b.effects?.flags || b.effects?.clues?.length);
        return !c.once && opensSomething;
      });
      assert.ok(progressing, `${ep.id}/${id}: 나아갈 수 있는 선택지가 없다`);
    }
  }
});
