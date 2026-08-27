// 장면 배경.
//
// 그림을 파일로 넣을 수가 없다. 이 게임은 의존성도 빌드도 없고, 배포되는 곳의
// 보안 정책은 외부 이미지를 막는다. 데이터 URI 로 넣으면 장면 하나에 수백 KB 다.
//
// 그래서 그린다. 캔버스에 실루엣 몇 겹을 얹는 방식이라 코드 몇백 줄이면 되고,
// 장면 id 로 시드를 잡으니 같은 장소는 늘 같은 모습이다.
//
// 원칙은 하나다 — **글자를 방해하지 않는다** (기획서 15절). 배경은 종이색보다
// 조금 밝거나 어두운 정도로만 존재하고, 아래로 갈수록 종이색에 잠긴다.
// 배경을 보려고 눈을 찡그리게 되면 그 배경은 실패한 것이다.

import { createRng } from '../engine/rng.js';

/** 이 아래로는 그림이 종이색에 잠긴다 — 띠와 본문 사이의 이음매를 지운다. */
const SINK = 0.78;

/*
 * 실루엣은 종이색보다 밝다. 처음에는 더 어둡게 잡았는데, 그러면 어두운 바탕에
 * 어두운 그림이라 아무것도 보이지 않았다 — 배경이 있다는 것조차 몰랐다.
 * 먼 것일수록 밝다(대기 원근). 가까운 것은 거의 검다.
 */
/*
 * 실루엣은 종이색보다 밝다. 먼 것일수록 밝다(대기 원근). 가까운 것은 거의 검다.
 *
 * 두 번 올렸다. 처음에는 종이색과 거의 같게 잡아서 배경이 있다는 것조차 몰랐고,
 * 한 번 올린 뒤에도 데스크톱 스크린샷에서만 보였다 — 휴대폰 화면에서는 여전히
 * 옅었다. 어두운 색끼리의 차이는 큰 화면에서 훨씬 잘 보인다.
 * 이 게임은 휴대폰에서 하는 게임이므로 그쪽에 맞춘다.
 */
const PALETTE = {
  paper: '#14110d',
  far: '#59492c',
  mid: '#3d3220',
  near: '#1a160f',
  gold: 'rgba(200, 162, 74, ',
  haze: 'rgba(200, 162, 74, 0.05)',
};

/**
 * 장면이 어떤 그림인가.
 * 콘텐츠가 `backdrop` 을 직접 지정하면 그것을 쓰고, 아니면 지명에서 읽는다.
 */
export function kindFor(scene) {
  if (scene?.backdrop) return scene.backdrop;
  const at = scene?.location || '';

  if (/회랑|밀림|나가|숲/.test(at)) return 'jungle';
  if (/원형의 방|별의 방|문의 방|여덟 번째 문/.test(at)) return 'chamber';
  if (/수로|서고|기단 아래|갱도|통로|유적 내부|최하층|수면 아래/.test(at)) return 'underground';
  if (/습지|갈대/.test(at)) return 'marsh';
  if (/시장|골목/.test(at)) return 'market';
  if (/계곡|지류|언덕|기단/.test(at)) return 'desert';
  if (/항|부두|동안|서안|샤트/.test(at)) return 'river';
  return 'desert';
}

// ── 붓 ───────────────────────────────────────────────────────────

/** 들쭉날쭉한 능선 하나. */
function ridge(ctx, w, h, { base, amp, step, color, jag = 0.5 }, rng) {
  ctx.beginPath();
  ctx.moveTo(0, h);
  let y = base + rng.range(-amp, amp);
  ctx.lineTo(0, y);
  for (let x = step; x <= w + step; x += step) {
    y += rng.range(-amp, amp) * (rng.chance(jag) ? 1.6 : 0.4);
    y = Math.max(h * 0.06, Math.min(base + amp * 2.4, y));
    ctx.lineTo(x, y);
  }
  ctx.lineTo(w, h);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
}

/** 세로로 선 것들 — 갈대, 나무, 기둥. */
function verticals(ctx, w, h, { count, top, bottom, width, color, lean = 0 }, rng) {
  ctx.fillStyle = color;
  for (let i = 0; i < count; i++) {
    const x = rng.range(-0.05, 1.05) * w;
    const t = rng.range(top, top + (bottom - top) * 0.45) * h;
    const b = rng.range(bottom * 0.94, bottom * 1.06) * h;
    const wd = rng.range(width * 0.6, width * 1.4);
    const dx = rng.range(-lean, lean) * w;
    ctx.beginPath();
    ctx.moveTo(x, b);
    ctx.lineTo(x + dx - wd / 2, t);
    ctx.lineTo(x + dx + wd / 2, t);
    ctx.lineTo(x + wd, b);
    ctx.closePath();
    ctx.fill();
  }
}

/**
 * 대지(mesa) — 평평한 꼭대기와 수직에 가까운 벽.
 *
 * 무작위 걸음(ridge)으로는 절벽이 나오지 않았다. 걸음마다 조금씩 움직이니
 * 언덕이 되고, 걸음을 크게 하면 톱니가 된다. 왕가의 계곡의 석회암은 둘 다 아니다 —
 * 평평하게 잘린 꼭대기와 곧게 선 벽이다. 그 형태는 직접 그려야 나온다.
 */
function mesas(ctx, w, h, { count, top, spread, color, base = 1.02 }, rng) {
  ctx.fillStyle = color;
  let x = -w * 0.1;
  for (let i = 0; i < count; i++) {
    const wd = rng.range(0.14, 0.42) * w;
    const crest = rng.range(top, top + spread) * h;
    const slope = wd * rng.range(0.06, 0.2);
    ctx.beginPath();
    ctx.moveTo(x, h * base);
    ctx.lineTo(x + slope, crest);
    ctx.lineTo(x + wd - slope, crest + rng.range(-0.03, 0.03) * h);
    ctx.lineTo(x + wd, h * base);
    ctx.closePath();
    ctx.fill();
    x += wd * rng.range(0.55, 0.9);
    if (x > w) break;
  }
}

/** 빛 무리. 램프, 해, 달. */
function glow(ctx, x, y, r, alpha) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `${PALETTE.gold}${alpha})`);
  g.addColorStop(0.45, `${PALETTE.gold}${alpha * 0.35})`);
  g.addColorStop(1, `${PALETTE.gold}0)`);
  ctx.fillStyle = g;
  ctx.fillRect(x - r, y - r, r * 2, r * 2);
}

function specks(ctx, w, h, { count, alpha, size, until = 1 }, rng) {
  for (let i = 0; i < count; i++) {
    const x = rng.range(0, 1) * w;
    const y = rng.range(0, until) * h;
    ctx.fillStyle = `${PALETTE.gold}${rng.range(alpha * 0.3, alpha).toFixed(3)})`;
    const s = rng.range(size * 0.6, size * 1.6);
    ctx.fillRect(x, y, s, s);
  }
}

// ── 장면 ─────────────────────────────────────────────────────────

const SCENES = {
  // 석회암 절벽. 각이 진 능선 세 겹이 뒤에서 앞으로 겹친다.
  desert(ctx, w, h, rng) {
    // 석회암은 부드럽게 흐르지 않는다. 단이 지고 각이 선다 — step 을 크게,
    // amp 를 크게 잡아야 언덕이 아니라 절벽으로 읽힌다.
    // 실루엣은 밝은 하늘을 배경으로 서야 읽힌다. 마루를 위쪽에 두고
    // 몸통이 아래 어둠으로 내려오게 한다 — 아래쪽에 그리면 어둠에 묻힌다.
    glow(ctx, w * rng.range(0.15, 0.85), h * 0.36, h * 1.1, 0.3);
    mesas(ctx, w, h, { count: 5, top: 0.14, spread: 0.2, color: PALETTE.far }, rng);
    mesas(ctx, w, h, { count: 4, top: 0.42, spread: 0.18, color: PALETTE.mid }, rng);
    ridge(ctx, w, h, { base: h * 0.78, amp: h * 0.06, step: w / 3, color: PALETTE.near, jag: 0.6 }, rng);
  },

  // 강. 낮은 둔덕과 삼각돛, 그리고 물 위의 잔선.
  river(ctx, w, h, rng) {
    glow(ctx, w * 0.5, h * 0.34, h * 0.95, 0.22);
    ridge(ctx, w, h, { base: h * 0.58, amp: h * 0.07, step: w / 5, color: PALETTE.far, jag: 0.4 }, rng);

    ctx.fillStyle = PALETTE.mid;
    for (let i = 0; i < 3; i++) {
      const x = rng.range(0.1, 0.9) * w;
      const b = h * 0.64;
      const sh = rng.range(0.16, 0.3) * h;
      ctx.beginPath();
      ctx.moveTo(x, b - sh);
      ctx.lineTo(x + sh * 0.5, b);
      ctx.lineTo(x - sh * 0.14, b);
      ctx.closePath();
      ctx.fill();
    }

    for (let i = 0; i < 7; i++) {
      ctx.fillStyle = `${PALETTE.gold}${(0.11 - i * 0.014).toFixed(3)})`;
      ctx.fillRect(rng.range(0, 0.45) * w, h * (0.68 + i * 0.045), rng.range(0.2, 0.55) * w, 1);
    }
  },

  // 차양이 겹치고 그 아래 등이 매달렸다. 앞에는 사람들.
  market(ctx, w, h, rng) {
    for (let i = 0; i < 4; i++) {
      const y = h * rng.range(0.1, 0.42);
      ctx.fillStyle = i % 2 ? PALETTE.far : PALETTE.mid;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.quadraticCurveTo(w * 0.5, y + h * rng.range(0.1, 0.22), w, y);
      ctx.lineTo(w, y - h * 0.16);
      ctx.lineTo(0, y - h * 0.16);
      ctx.closePath();
      ctx.fill();
    }
    for (let i = 0; i < 6; i++) {
      glow(ctx, rng.range(0.05, 0.95) * w, rng.range(0.3, 0.52) * h, h * 0.28, 0.2);
    }
    verticals(ctx, w, h, { count: 16, top: 0.62, bottom: 1.02, width: w * 0.03, color: PALETTE.near }, rng);
  },

  // 통로. 원근선이 한 점으로 모이고 그 자리에 램프가 있다.
  underground(ctx, w, h, rng) {
    const cx = w * rng.range(0.42, 0.58);
    const cy = h * 0.52;
    glow(ctx, cx, cy, h * 1.2, 0.3);

    ctx.strokeStyle = `${PALETTE.gold}0.1)`;
    ctx.lineWidth = 1;
    for (const t of [0.16, 0.34, 0.56, 0.82]) {
      ctx.beginPath();
      ctx.moveTo(cx - w * t, h);
      ctx.lineTo(cx - w * t * 0.1, cy);
      ctx.moveTo(cx + w * t, h);
      ctx.lineTo(cx + w * t * 0.1, cy);
      ctx.moveTo(cx - w * t, 0);
      ctx.lineTo(cx - w * t * 0.1, cy);
      ctx.moveTo(cx + w * t, 0);
      ctx.lineTo(cx + w * t * 0.1, cy);
      ctx.stroke();
    }
    // 좁혀 드는 천장
    ctx.fillStyle = PALETTE.near;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(w, 0);
    ctx.lineTo(w, h * 0.1);
    ctx.quadraticCurveTo(cx, h * 0.4, 0, h * 0.1);
    ctx.closePath();
    ctx.fill();

    specks(ctx, w, h, { count: 30, alpha: 0.16, size: 1.4 }, rng);
  },

  // 돔 천장에 박아 넣은 별들. 그 아래 빛을 내지 않는 원반.
  chamber(ctx, w, h, rng) {
    const cx = w / 2;
    const cy = h * 1.05;
    ctx.strokeStyle = `${PALETTE.gold}0.12)`;
    ctx.lineWidth = 1;
    for (const r of [0.5, 0.72, 0.94]) {
      ctx.beginPath();
      ctx.arc(cx, cy, h * r, Math.PI, 0);
      ctx.stroke();
    }
    for (let i = 0; i < 70; i++) {
      const a = rng.range(Math.PI, Math.PI * 2);
      const r = h * rng.range(0.2, 1.0);
      ctx.fillStyle = `${PALETTE.gold}${rng.range(0.1, 0.4).toFixed(3)})`;
      ctx.fillRect(cx + Math.cos(a) * r, cy + Math.sin(a) * r, 1.6, 1.6);
    }
    // 검은 태양 — 빛이 아니라 자리로만 있다
    ctx.beginPath();
    ctx.arc(cx, h * 0.46, h * 0.26, 0, Math.PI * 2);
    ctx.fillStyle = '#070605';
    ctx.fill();
    ctx.strokeStyle = `${PALETTE.gold}0.28)`;
    ctx.stroke();
  },

  // 갈대. 사람 키의 두 배로 서서 화면을 세로로 가른다.
  marsh(ctx, w, h, rng) {
    glow(ctx, w * rng.range(0.2, 0.8), h * 0.3, h * 0.9, 0.2);
    ctx.fillStyle = `${PALETTE.gold}0.07)`;
    ctx.fillRect(0, h * 0.78, w, h * 0.04);
    verticals(ctx, w, h, { count: 34, top: -0.1, bottom: 0.86, width: w * 0.007, color: PALETTE.far, lean: 0.02 }, rng);
    verticals(ctx, w, h, { count: 40, top: 0.05, bottom: 1.02, width: w * 0.01, color: PALETTE.near, lean: 0.03 }, rng);
  },

  // 밀림. 위를 덮은 잎과 굵은 줄기.
  jungle(ctx, w, h, rng) {
    for (let i = 0; i < 7; i++) {
      ctx.fillStyle = i % 2 ? PALETTE.far : PALETTE.mid;
      ctx.beginPath();
      ctx.ellipse(
        rng.range(-0.1, 1.1) * w, rng.range(-0.1, 0.3) * h,
        rng.range(0.16, 0.4) * w, rng.range(0.16, 0.34) * h,
        0, 0, Math.PI * 2,
      );
      ctx.fill();
    }
    verticals(ctx, w, h, { count: 8, top: -0.1, bottom: 1.05, width: w * 0.03, color: PALETTE.near, lean: 0.012 }, rng);
    ctx.strokeStyle = `${PALETTE.gold}0.08)`;
    for (let i = 0; i < 10; i++) {
      const x = rng.range(0, 1) * w;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.quadraticCurveTo(x + rng.range(-0.05, 0.05) * w, h * 0.45, x + rng.range(-0.08, 0.08) * w, h * rng.range(0.6, 1));
      ctx.stroke();
    }
  },

  // 항해. 수평선 하나와 멀리 배 한 척.
  sea(ctx, w, h, rng) {
    glow(ctx, w * rng.range(0.25, 0.75), h * 0.36, h * 1.1, 0.26);
    // 수평선 — 이 그림에서 가장 확실한 선 하나
    ctx.fillStyle = PALETTE.mid;
    ctx.fillRect(0, h * 0.6, w, h);
    ctx.fillStyle = `${PALETTE.gold}0.18)`;
    ctx.fillRect(0, h * 0.6, w, 1);

    // 증기선 한 척. 굴뚝에서 연기가 눕는다.
    const sx = rng.range(0.24, 0.76) * w;
    const hull = h * 0.6;
    ctx.fillStyle = PALETTE.near;
    ctx.beginPath();
    ctx.moveTo(sx - w * 0.11, hull - h * 0.12);
    ctx.lineTo(sx + w * 0.11, hull - h * 0.12);
    ctx.lineTo(sx + w * 0.08, hull);
    ctx.lineTo(sx - w * 0.08, hull);
    ctx.closePath();
    ctx.fill();
    ctx.fillRect(sx - w * 0.012, hull - h * 0.42, w * 0.024, h * 0.3);
    ctx.fillRect(sx + w * 0.05, hull - h * 0.34, w * 0.006, h * 0.22);
    ctx.fillStyle = `${PALETTE.gold}0.06)`;
    ctx.beginPath();
    ctx.ellipse(sx + w * 0.1, hull - h * 0.46, w * 0.14, h * 0.09, 0, 0, Math.PI * 2);
    ctx.fill();

    for (let i = 0; i < 9; i++) {
      ctx.fillStyle = `${PALETTE.gold}${(0.13 - i * 0.013).toFixed(3)})`;
      ctx.fillRect(rng.range(0, 0.5) * w, h * (0.65 + i * 0.04), rng.range(0.22, 0.55) * w, 1);
    }
  },
};

// ── 그리기 ───────────────────────────────────────────────────────

/**
 * 캔버스에 장면을 그린다.
 * @param {HTMLCanvasElement} canvas
 * @param {string} kind SCENES 의 키
 * @param {string} seed 같은 장소는 늘 같은 모습이 되도록
 */
export function paint(canvas, kind, seed = '') {
  const draw = SCENES[kind] || SCENES.desert;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (!w || !h) return false;

  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const rng = createRng(`${kind}:${seed}`);

  // 하늘 — 위가 조금 밝다
  const sky = ctx.createLinearGradient(0, 0, 0, h);
  sky.addColorStop(0, '#3a2f1e');
  sky.addColorStop(0.78, PALETTE.paper);
  sky.addColorStop(1, PALETTE.paper);
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, w, h);

  draw(ctx, w, h, rng);

  // 글자가 앉는 자리부터는 종이색에 잠긴다. 이 한 겹이 가독성을 지킨다.
  // 아래 끝만 종이색에 잠긴다. 띠와 본문 사이의 이음매를 없애는 정도.
  const sink = ctx.createLinearGradient(0, h * SINK, 0, h);
  sink.addColorStop(0, 'rgba(20,17,13,0)');
  sink.addColorStop(1, 'rgba(20,17,13,0.7)');
  ctx.fillStyle = sink;
  ctx.fillRect(0, 0, w, h);

  return true;
}

export const KINDS = Object.keys(SCENES);
