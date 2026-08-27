// 배경음.
//
// 음악 파일을 넣을 수가 없다 — 효과음과 같은 이유다. 그래서 합성한다.
//
// 다만 여기서 만드는 것은 '곡'이 아니라 '공기'다. 30초짜리 루프는 텍스트 게임에서
// 세 번째 반복부터 거슬리기 시작한다. 이 게임은 한 시간씩 읽는 게임이고, 읽는 동안
// 귀에 걸리는 것이 있으면 안 된다.
//
// 그래서 세 겹으로 쌓는다.
//   1. 드론 — 겹쳐 놓은 저음. 거의 변하지 않는다. 이것이 '방의 크기'를 정한다.
//   2. 결   — 아주 느리게 열리고 닫히는 필터. 숨 쉬는 것처럼 들린다.
//   3. 낱음 — 4~10초에 하나씩, 음계에서 무작위로. 이것이 '시간이 흐른다'를 만든다.
//
// 반복 마디가 없으므로 같은 구간이 두 번 오지 않는다.

import { ac as sharedContext } from './audio.js';

let ac = null;
let master = null;
let enabled = false;
let current = null; // { mood, nodes, timer }
let ducked = false;

/** 장면 종류 → 분위기. backdrop.kindFor 의 결과를 그대로 받는다. */
const MOOD_OF = {
  desert: 'travel',
  river: 'travel',
  sea: 'travel',
  market: 'town',
  underground: 'ruin',
  chamber: 'sacred',
  marsh: 'wild',
  jungle: 'wild',
};

export function moodFor(kind) {
  return MOOD_OF[kind] || 'travel';
}

/*
 * 음높이는 헤르츠로 직접 적는다. 음이름 표를 만들 만큼 많이 쓰지 않는다.
 *
 * scale 은 낱음이 고르는 음들. 조성이 분위기를 절반쯤 정한다 —
 * 도리안은 여행자의 조성이고, 프리지안은 지하의 조성이다.
 */
const MOODS = {
  // 사막·강·항해. 낮고 따뜻하다. 계속 가고 있다는 느낌.
  travel: {
    drone: [73.42, 110.0, 146.83], // D2 A2 D3
    cutoff: [260, 620],
    breath: 26,
    scale: [293.66, 329.63, 349.23, 440.0, 493.88, 587.33], // D 도리안
    gap: [5, 11],
    voice: 'triangle',
    gain: 0.05,
  },
  // 시장. 조금 밝고 조금 분주하다.
  town: {
    drone: [82.41, 123.47, 164.81], // E2 B2 E3
    cutoff: [340, 900],
    breath: 18,
    scale: [329.63, 369.99, 415.3, 493.88, 554.37, 659.26],
    gap: [3, 7],
    voice: 'triangle',
    gain: 0.045,
  },
  // 지하. 아주 낮고 좁다. 낱음이 드물게, 그리고 늦게 사라진다.
  ruin: {
    drone: [55.0, 82.41, 87.31], // A1 E2 F2 — 반음 부딪침이 불안을 만든다
    cutoff: [140, 380],
    breath: 34,
    scale: [220.0, 233.08, 261.63, 329.63, 349.23], // A 프리지안
    gap: [7, 15],
    voice: 'sine',
    gain: 0.055,
  },
  // 원형의 방. 5도만 남긴 순한 음. 사람이 만든 소리 같지 않게.
  sacred: {
    drone: [65.41, 98.0, 196.0], // C2 G2 G3
    cutoff: [420, 1100],
    breath: 40,
    scale: [261.63, 293.66, 329.63, 369.99, 415.3], // 온음음계 — 어디에도 안 걸린다
    gap: [8, 18],
    voice: 'sine',
    gain: 0.05,
  },
  // 습지·밀림. 드론 위에 벌레 소리를 얹는다.
  wild: {
    drone: [61.74, 92.5, 123.47], // B1 F#2 B2
    cutoff: [240, 700],
    breath: 22,
    scale: [246.94, 277.18, 311.13, 369.99, 415.3],
    gap: [4, 9],
    voice: 'triangle',
    gain: 0.045,
    insects: true,
  },
  // 전투. 낱음 대신 심장 박동. 조성은 그대로 두어 같은 세계로 들리게.
  combat: {
    drone: [55.0, 77.78, 110.0], // A1 + 감5도 — 풀리지 않는다
    cutoff: [200, 520],
    breath: 9,
    scale: [],
    gap: [0, 0],
    voice: 'sine',
    gain: 0.06,
    pulse: 1.15,
  },
};

function audio() {
  if (!ac) {
    ac = sharedContext();
    if (!ac) return null;
    master = ac.createGain();
    master.gain.value = 1;
    master.connect(ac.destination);
  }
  return ac;
}

// ── 층 만들기 ────────────────────────────────────────────────────

/** 겹쳐 놓은 저음. 살짝씩 어긋나게 튜닝해야 죽은 소리가 안 난다. */
function buildDrone(a, spec, out) {
  const nodes = [];
  spec.drone.forEach((freq, i) => {
    const osc = a.createOscillator();
    osc.type = i === 0 ? 'sine' : spec.voice;
    osc.frequency.value = freq;
    // 맥놀이 — 두 음이 아주 조금 어긋나면 소리가 천천히 흔들린다
    osc.detune.value = (i - 1) * 6;
    const g = a.createGain();
    g.gain.value = i === 0 ? 0.5 : 0.24 / i;
    osc.connect(g).connect(out);
    osc.start();
    nodes.push(osc, g);
  });
  return nodes;
}

/** 아주 느리게 열리고 닫히는 필터. 숨처럼. */
function buildBreath(a, spec, out) {
  const flt = a.createBiquadFilter();
  flt.type = 'lowpass';
  flt.Q.value = 1.4;
  flt.frequency.value = spec.cutoff[0];

  const lfo = a.createOscillator();
  lfo.frequency.value = 1 / spec.breath;
  const depth = a.createGain();
  depth.gain.value = (spec.cutoff[1] - spec.cutoff[0]) / 2;
  flt.frequency.value = (spec.cutoff[0] + spec.cutoff[1]) / 2;
  lfo.connect(depth).connect(flt.frequency);
  lfo.start();

  flt.connect(out);
  return { flt, nodes: [lfo, depth] };
}

/** 낱음 하나. 길게 남는다. */
function pluck(a, freq, spec, out) {
  const osc = a.createOscillator();
  osc.type = spec.voice;
  osc.frequency.value = freq;
  const g = a.createGain();
  const t = a.currentTime;
  const len = 3.4;
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(0.05, t + 0.5);
  g.gain.exponentialRampToValueAtTime(0.0001, t + len);
  osc.connect(g).connect(out);
  osc.start(t);
  osc.stop(t + len + 0.1);
}

/** 심장 박동 — 전투에서만. */
function beat(a, spec, out) {
  const osc = a.createOscillator();
  osc.type = 'sine';
  const t = a.currentTime;
  osc.frequency.setValueAtTime(72, t);
  osc.frequency.exponentialRampToValueAtTime(44, t + 0.16);
  const g = a.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(0.16, t + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t + 0.3);
  osc.connect(g).connect(out);
  osc.start(t);
  osc.stop(t + 0.35);
}

/** 벌레 — 좁게 거른 잡음 한 점. */
function chirp(a, out) {
  const frames = Math.floor(a.sampleRate * 0.09);
  const buf = a.createBuffer(1, frames, a.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < frames; i++) {
    const env = Math.sin((Math.PI * i) / frames);
    d[i] = (Math.random() * 2 - 1) * env * env;
  }
  const src = a.createBufferSource();
  src.buffer = buf;
  const flt = a.createBiquadFilter();
  flt.type = 'bandpass';
  flt.frequency.value = 2600 + Math.random() * 2200;
  flt.Q.value = 14;
  const g = a.createGain();
  g.gain.value = 0.05;
  src.connect(flt).connect(g).connect(out);
  src.start();
}

// ── 켜고 끄고 바꾸기 ─────────────────────────────────────────────

function teardown(layer, fadeSec = 2.2) {
  if (!layer) return;
  layer.alive = false;
  clearInterval(layer.timer);
  clearTimeout(layer.timer);
  const t = ac.currentTime;
  try {
    layer.gain.gain.cancelScheduledValues(t);
    layer.gain.gain.setValueAtTime(layer.gain.gain.value, t);
    layer.gain.gain.linearRampToValueAtTime(0.0001, t + fadeSec);
  } catch {
    /* 이미 멈춘 노드는 조용히 넘어간다 */
  }
  setTimeout(() => {
    for (const n of layer.nodes) {
      try {
        n.stop?.();
        n.disconnect?.();
      } catch {
        /* 마찬가지 */
      }
    }
    try {
      layer.gain.disconnect();
    } catch {
      /* 마찬가지 */
    }
  }, fadeSec * 1000 + 200);
}

function build(mood) {
  const a = audio();
  if (!a) return null;
  const spec = MOODS[mood] || MOODS.travel;

  const gain = a.createGain();
  gain.gain.value = 0.0001;
  gain.connect(master);

  const breath = buildBreath(a, spec, gain);
  const nodes = buildDrone(a, spec, breath.flt).concat(breath.nodes);

  const t = a.currentTime;
  gain.gain.linearRampToValueAtTime(spec.gain, t + 3);

  // 낱음 / 박동 / 벌레
  const layer = { mood, gain, nodes, timer: null, alive: true };

  if (spec.pulse) {
    // 박동만은 규칙적이어야 한다. 심장은 즉흥으로 뛰지 않는다.
    layer.timer = setInterval(() => beat(a, spec, gain), spec.pulse * 1000);
  } else if (spec.scale.length) {
    // 낱음은 매번 간격을 다시 뽑는다.
    //
    // 평균값으로 setInterval 을 걸었더니 정확히 8초마다 소리가 났다. 그건
    // 메트로놈이고, 메트로놈이 있으면 마디가 생기고, 마디가 생기면 반복이
    // 들린다 — 이 파일이 피하려던 바로 그것이다.
    const [lo, hi] = spec.gap;
    const next = () => {
      if (!layer.alive) return;
      if (Math.random() < 0.82) {
        pluck(a, spec.scale[Math.floor(Math.random() * spec.scale.length)], spec, gain);
      }
      if (spec.insects && Math.random() < 0.6) chirp(a, gain);
      layer.timer = setTimeout(next, (lo + Math.random() * (hi - lo)) * 1000);
    };
    layer.timer = setTimeout(next, (lo + Math.random() * (hi - lo)) * 400);
  }

  return layer;
}

/** 지금 이 분위기로 바꾼다. 같은 분위기면 아무것도 하지 않는다. */
export function setMood(mood) {
  if (!enabled) {
    current = current || { mood };
    if (current) current.mood = mood;
    return;
  }
  if (current?.mood === mood && current.gain) return;

  const old = current;
  current = build(mood) || { mood };
  // 앞의 것을 뒤에서 지운다 — 겹치는 동안 소리가 끊기지 않는다
  if (old?.gain) teardown(old);
}

export function setMusicEnabled(v) {
  enabled = v;
  if (!v) {
    if (current?.gain) teardown(current, 1.2);
    current = current ? { mood: current.mood } : null;
    return;
  }
  const a = audio();
  if (a) master.gain.linearRampToValueAtTime(ducked ? 0.3 : 1, a.currentTime + 0.6);
  if (current && !current.gain) setMood(current.mood);
}

export function musicEnabled() {
  return enabled;
}

/** 주사위 연출처럼 잠깐 앞으로 나서야 하는 소리가 있을 때 뒤로 물린다. */
export function duck(on) {
  ducked = on;
  if (!ac || !enabled) return;
  master.gain.linearRampToValueAtTime(on ? 0.3 : 1, ac.currentTime + 0.25);
}

export function stopMusic() {
  if (current?.gain) teardown(current, 1.2);
  current = null;
}
