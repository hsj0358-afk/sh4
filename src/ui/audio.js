// 사운드. 외부 에셋 없이 WebAudio 로 합성한다.
// 종이, 주사위, 성공/실패. 성공과 실패의 차이는 과장되어야 한다(기획서 16절).

let ctx = null;
let enabled = true;

/**
 * 오디오 컨텍스트 하나를 만들어 두고 돌려 쓴다.
 * 배경음(music.js)도 이것을 쓴다 — 브라우저마다 만들 수 있는 개수에 한도가 있고,
 * 둘로 나눠 봐야 얻는 것이 없다.
 */
export function ac() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}

export function setAudioEnabled(v) {
  enabled = v;
}

export function audioEnabled() {
  return enabled;
}

/** 짧은 노이즈 버스트 — 종이, 모래, 주사위 충돌음의 재료. */
function noise(duration, filterFreq, gainValue, type = 'bandpass') {
  const a = ac();
  if (!a || !enabled) return;
  const frames = Math.floor(a.sampleRate * duration);
  const buf = a.createBuffer(1, frames, a.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < frames; i++) {
    const env = 1 - i / frames;
    d[i] = (Math.random() * 2 - 1) * env * env;
  }
  const src = a.createBufferSource();
  src.buffer = buf;
  const flt = a.createBiquadFilter();
  flt.type = type;
  flt.frequency.value = filterFreq;
  flt.Q.value = 0.8;
  const g = a.createGain();
  g.gain.value = gainValue;
  src.connect(flt).connect(g).connect(a.destination);
  src.start();
}

function tone(freq, duration, gainValue = 0.12, type = 'sine', slideTo = null) {
  const a = ac();
  if (!a || !enabled) return;
  const osc = a.createOscillator();
  const g = a.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, a.currentTime);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, a.currentTime + duration);
  g.gain.setValueAtTime(0.0001, a.currentTime);
  g.gain.exponentialRampToValueAtTime(gainValue, a.currentTime + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + duration);
  osc.connect(g).connect(a.destination);
  osc.start();
  osc.stop(a.currentTime + duration + 0.05);
}

export const sfx = {
  page() {
    noise(0.12, 2600, 0.16, 'highpass');
  },
  tap() {
    noise(0.05, 1400, 0.1);
  },
  /** 주사위가 구르는 소리 — 불규칙한 충돌 여러 번. */
  diceRoll() {
    const a = ac();
    if (!a || !enabled) return;
    let t = 0;
    for (let i = 0; i < 9; i++) {
      t += 40 + Math.random() * 70;
      setTimeout(() => noise(0.05, 900 + Math.random() * 1200, 0.14), t);
    }
  },
  diceLand() {
    noise(0.09, 700, 0.22);
  },
  success() {
    tone(523.25, 0.14, 0.1);
    setTimeout(() => tone(783.99, 0.3, 0.1), 90);
  },
  crit() {
    tone(523.25, 0.12, 0.11);
    setTimeout(() => tone(659.25, 0.12, 0.11), 80);
    setTimeout(() => tone(1046.5, 0.5, 0.12), 170);
  },
  fail() {
    tone(180, 0.35, 0.12, 'triangle', 120);
  },
  fumble() {
    tone(140, 0.7, 0.16, 'sawtooth', 55);
    noise(0.4, 220, 0.12, 'lowpass');
  },
  danger() {
    tone(90, 0.5, 0.1, 'sine', 70);
  },
  clue() {
    tone(880, 0.1, 0.07);
    setTimeout(() => tone(1174.66, 0.22, 0.07), 70);
  },
};
