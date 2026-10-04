(function () {
  'use strict';

  const W = 480;
  const H = 640;
  const GROUND_H = 90;
  const GRAVITY = 1900;      // px/с²
  const FLAP_V = -540;       // px/с
  const MAX_FALL = 900;      // px/с
  const PIPE_W = 72;
  const PIPE_GAP = 170;      // высота проёма
  const PIPE_SPACING = 250;  // расстояние между трубами
  const SPEED = 185;         // px/с
  const BIRD_X = 130;
  const BIRD_R = 15;

  const STATE = { READY: 'ready', PLAYING: 'playing', OVER: 'over' };

  const canvas = document.getElementById('game');
  const ctx = canvas.getContext('2d');
  const overlay = document.getElementById('overlay');
  const overlayTitle = document.getElementById('overlay-title');
  const overlayText = document.getElementById('overlay-text');
  const overlayBtn = document.getElementById('overlay-btn');
  const statusEl = document.getElementById('status');

  // ---- Состояние игры ----
  let state = STATE.READY;
  let birdY = H * 0.42;
  let birdVy = 0;
  let pipes = [];
  let score = 0;
  let best = Number(localStorage.getItem('botapp_best') || 0);
  let overAt = 0;
  let groundOffset = 0;
  let clouds = [];
  let lastTs = 0;

  for (let i = 0; i < 4; i++) {
    clouds.push({ x: Math.random() * W, y: 60 + Math.random() * 180, s: 26 + Math.random() * 26, v: 12 + Math.random() * 14 });
  }

  // ---- Ассеты: спрайт героя и фон.----
  const sprite = { image: null, loaded: false };
  const backdrop = { image: null, loaded: false };
  const stone = { image: null, pattern: null, loaded: false };

  // ---- Кто играет: id из Telegram Web App, из ?user=, иначе локальный ----
  function currentUser() {
    try {
      const tg = window.Telegram && window.Telegram.WebApp;
      const id = tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.id;
      if (id) return String(id);
    } catch (_) { }
    const fromUrl = new URLSearchParams(location.search).get('user');
    if (fromUrl) {
      try { localStorage.setItem('botapp_user', fromUrl); } catch (_) { }
      return fromUrl;
    }
    let saved = null;
    try { saved = localStorage.getItem('botapp_user'); } catch (_) { }
    if (!saved) {
      saved = 'local-' + Math.random().toString(36).slice(2, 8);
      try { localStorage.setItem('botapp_user', saved); } catch (_) { }
    }
    return saved;
  }

  const userId = currentUser();

  // ---- Звук: короткие бипы через WebAudio, без файлов ----
  let audioCtx = null;
  function beep(freq, dur) {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'square';
      osc.frequency.value = freq;
      gain.gain.value = 0.05;
      gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + dur);
      osc.connect(gain).connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + dur);
    } catch (_) { }
  }

  // ---- Высокое DPI ----
  function fitCanvas() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  fitCanvas();
  window.addEventListener('resize', fitCanvas);

  // ---- Логика ----
  function spawnPipe(x) {
    const margin = 80;
    const maxTop = H - GROUND_H - PIPE_GAP - margin;
    const top = margin + Math.random() * (maxTop - margin);
    pipes.push({ x: x, top: top, scored: false });
  }

  function reset() {
    birdY = H * 0.42;
    birdVy = 0;
    pipes = [];
    score = 0;
    groundOffset = 0;
    spawnPipe(W + 60);
  }

  function startGame() {
    reset();
    state = STATE.PLAYING;
    birdVy = FLAP_V;
    hideOverlay();
    setStatus('');
  }

  function gameOver() {
    state = STATE.OVER;
    overAt = performance.now();
    beep(160, 0.28);
    if (score > best) {
      best = score;
      try { localStorage.setItem('botapp_best', String(best)); } catch (_) { }
    }
    showOverlay('Игра окончена', 'Счёт: ' + score + '  ·  Рекорд: ' + best, 'Ещё раз');
    submitScore(score);
  }

  function flap() {
    if (state === STATE.READY) { startGame(); return; }
    if (state === STATE.PLAYING) { birdVy = FLAP_V; beep(520, 0.05); return; }
    if (performance.now() - overAt > 500) startGame();
  }

  function circleHitsRect(cx, cy, r, rx, ry, rw, rh) {
    const nx = Math.max(rx, Math.min(cx, rx + rw));
    const ny = Math.max(ry, Math.min(cy, ry + rh));
    const dx = cx - nx;
    const dy = cy - ny;
    return dx * dx + dy * dy <= r * r;
  }

  function hitsPipe(p) {
    const bottomY = p.top + PIPE_GAP;
    const bottomH = H - GROUND_H - bottomY;
    const hitTop = circleHitsRect(BIRD_X, birdY, BIRD_R - 1, p.x, 0, PIPE_W, p.top);
    const hitBottom = circleHitsRect(BIRD_X, birdY, BIRD_R - 1, p.x, bottomY, PIPE_W, bottomH);
    return hitTop || hitBottom;
  }

  function update(dt) {
    groundOffset = (groundOffset + SPEED * dt) % 40;
    for (const c of clouds) {
      c.x -= c.v * dt;
      if (c.x < -70) { c.x = W + 70; c.y = 60 + Math.random() * 180; }
    }

    if (state === STATE.READY) {
      birdY = H * 0.42 + Math.sin(performance.now() / 340) * 9;
      for (const p of pipes) p.x -= SPEED * dt;
      if (pipes.length && pipes[0].x + PIPE_W < -20) pipes.shift();
      return;
    }

    if (state === STATE.OVER) {
      birdVy = Math.min(birdVy + GRAVITY * dt, MAX_FALL);
      birdY += birdVy * dt;
      const floor = H - GROUND_H - BIRD_R;
      if (birdY > floor) { birdY = floor; birdVy = 0; }
      return;
    }

    // PLAYING
    birdVy = Math.min(birdVy + GRAVITY * dt, MAX_FALL);
    birdY += birdVy * dt;

    for (const p of pipes) p.x -= SPEED * dt;

    const last = pipes[pipes.length - 1];
    if (!last || last.x <= W - PIPE_SPACING) {
      spawnPipe(last ? last.x + PIPE_SPACING : W + 60);
    }

    for (const p of pipes) {
      if (!p.scored && p.x + PIPE_W < BIRD_X) {
        p.scored = true;
        score += 1;
        beep(900, 0.06);
      }
    }
    while (pipes.length && pipes[0].x + PIPE_W < -20) pipes.shift();

    if (birdY + BIRD_R >= H - GROUND_H) {
      birdY = H - GROUND_H - BIRD_R;
      gameOver();
      return;
    }
    if (birdY - BIRD_R <= 0) { birdY = BIRD_R; birdVy = 0; }

    for (const p of pipes) {
      if (hitsPipe(p)) { gameOver(); return; }
    }
  }

  // ---- Загрузка ассетов ----

  function loadImage(src) {
    return new Promise(function (resolve) {
      const img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () { resolve(null); };
      img.src = src;
    });
  }

  function chromaKey(source) {
    const buffer = document.createElement('canvas');
    buffer.width = source.naturalWidth;
    buffer.height = source.naturalHeight;
    const bx = buffer.getContext('2d');
    bx.drawImage(source, 0, 0);

    const frame = bx.getImageData(0, 0, buffer.width, buffer.height);
    const px = frame.data;
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i], g = px[i + 1], b = px[i + 2];
      if (r > 120 && b > 120 && g < 130 && Math.abs(r - b) < 120) {
        px[i + 3] = 0;                                   // чистый фон
      } else if (r > 100 && b > 100 && g < 150 && Math.abs(r - b) < 130) {
        px[i + 3] = Math.min(px[i + 3], 90);             // кромка — полупрозрачная
      }
    }
    bx.putImageData(frame, 0, 0);
    return buffer;
  }

  function cropToContent(source) {
    const sx = source.getContext('2d');
    const width = source.width;
    const height = source.height;
    const px = sx.getImageData(0, 0, width, height).data;

    let minX = width, minY = height, maxX = -1, maxY = -1;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (px[(y * width + x) * 4 + 3] > 24) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    if (maxX < 0) return source;

    const pad = 6;
    minX = Math.max(0, minX - pad);
    minY = Math.max(0, minY - pad);
    maxX = Math.min(width - 1, maxX + pad);
    maxY = Math.min(height - 1, maxY + pad);

    const out = document.createElement('canvas');
    out.width = maxX - minX + 1;
    out.height = maxY - minY + 1;
    out.getContext('2d').drawImage(source, minX, minY, out.width, out.height, 0, 0, out.width, out.height);
    return out;
  }

  function loadAssets() {
    loadImage('assets/background.png').then(function (img) {
      if (img) { backdrop.image = img; backdrop.loaded = true; }
    });

    loadImage('assets/stone.png').then(function (img) {
      if (!img) return;
      stone.image = img;
      stone.pattern = ctx.createPattern(img, 'repeat');
      stone.loaded = !!stone.pattern;
    });

    loadImage('assets/meepo.png').then(function (img) {
      if (!img) return;
      try {
        sprite.image = cropToContent(chromaKey(img));
        sprite.loaded = true;
      } catch (_) {
        sprite.loaded = false;
      }
    });
  }

  // ---- Рисование ----
  function drawSky() {
    if (backdrop.loaded) {
      ctx.drawImage(backdrop.image, 0, 0, W, H);
      ctx.fillStyle = 'rgba(10, 14, 26, .16)';
      ctx.fillRect(0, 0, W, H - GROUND_H);
      return;
    }

    const g = ctx.createLinearGradient(0, 0, 0, H - GROUND_H);
    g.addColorStop(0, '#4ec0ca');
    g.addColorStop(1, '#8fe3e8');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H - GROUND_H);

    ctx.fillStyle = 'rgba(255,255,255,.72)';
    for (const c of clouds) {
      ctx.beginPath();
      ctx.arc(c.x, c.y, c.s, 0, Math.PI * 2);
      ctx.arc(c.x + c.s * 0.9, c.y + 6, c.s * 0.75, 0, Math.PI * 2);
      ctx.arc(c.x - c.s * 0.9, c.y + 8, c.s * 0.65, 0, Math.PI * 2);
      ctx.fill();
    }
  }


  function pipeFill(x, w) {
    if (stone.loaded) {
      const shade = ctx.createLinearGradient(x, 0, x + w, 0);
      shade.addColorStop(0, 'rgba(255, 255, 255, .16)');
      shade.addColorStop(0.45, 'rgba(255, 255, 255, 0)');
      shade.addColorStop(1, 'rgba(0, 0, 0, .42)');
      return { pattern: stone.pattern, shade: shade };
    }

    const green = ctx.createLinearGradient(x, 0, x + w, 0);
    green.addColorStop(0, '#3f9e3f');
    green.addColorStop(0.35, '#86e05a');
    green.addColorStop(1, '#357c33');
    return { pattern: null, shade: green };
  }

  function fillStone(x, y, w, h, fill) {
    if (h <= 0) return;

    if (fill.pattern) {
      ctx.save();
      ctx.translate(x, y);
      ctx.fillStyle = fill.pattern;
      ctx.fillRect(0, 0, w, h);
      ctx.restore();
      ctx.fillStyle = fill.shade;
    } else {
      ctx.fillStyle = fill.shade;
    }
    ctx.fillRect(x, y, w, h);
  }

  function drawPipe(p) {
    const bottomY = p.top + PIPE_GAP;
    const limit = H - GROUND_H;
    const capH = 26;
    const capOver = 6;

    const body = pipeFill(p.x, PIPE_W);
    const cap = pipeFill(p.x - capOver, PIPE_W + capOver * 2);

    fillStone(p.x, 0, PIPE_W, p.top, body);
    fillStone(p.x, bottomY, PIPE_W, limit - bottomY, body);
    fillStone(p.x - capOver, p.top - capH, PIPE_W + capOver * 2, capH, cap);
    fillStone(p.x - capOver, bottomY, PIPE_W + capOver * 2, capH, cap);

    if (stone.loaded) {
      ctx.fillStyle = 'rgba(0, 0, 0, .3)';
      ctx.fillRect(p.x - capOver, p.top - capH, PIPE_W + capOver * 2, 3);
      ctx.fillRect(p.x - capOver, bottomY + capH - 3, PIPE_W + capOver * 2, 3);
    }

    ctx.strokeStyle = stone.loaded ? 'rgba(0, 0, 0, .45)' : 'rgba(0, 0, 0, .22)';
    ctx.lineWidth = 2;
    ctx.strokeRect(p.x - capOver, p.top - capH, PIPE_W + capOver * 2, capH);
    ctx.strokeRect(p.x - capOver, bottomY, PIPE_W + capOver * 2, capH);
  }

  function drawGround() {
    const y = H - GROUND_H;

    if (backdrop.loaded) {
      const g = ctx.createLinearGradient(0, y, 0, H);
      g.addColorStop(0, 'rgba(74, 55, 36, .84)');
      g.addColorStop(1, 'rgba(32, 23, 15, .94)');
      ctx.fillStyle = g;
      ctx.fillRect(0, y, W, GROUND_H);

      ctx.fillStyle = 'rgba(150, 190, 120, .5)';
      ctx.fillRect(0, y, W, 5);

      ctx.fillStyle = 'rgba(0, 0, 0, .22)';
      for (let x = -groundOffset; x < W + 46; x += 46) {
        ctx.fillRect(x, y + 16, 22, 9);
      }
      return;
    }

    ctx.fillStyle = '#ded895';
    ctx.fillRect(0, y, W, GROUND_H);
    ctx.fillStyle = '#c9c07a';
    for (let x = -groundOffset; x < W + 40; x += 40) {
      ctx.fillRect(x, y, 20, 14);
    }
    ctx.fillStyle = '#5a9c46';
    ctx.fillRect(0, y, W, 10);
    ctx.fillStyle = 'rgba(0,0,0,.12)';
    ctx.fillRect(0, y + 10, W, 3);
  }

  function drawBird() {
    ctx.save();
    ctx.translate(BIRD_X, birdY);
    const angle = state === STATE.READY ? 0 : Math.max(-0.45, Math.min(0.9, birdVy / 900));
    ctx.rotate(angle);

    if (sprite.loaded) {
      const drawH = 48;
      const ratio = sprite.image.width / sprite.image.height;
      const drawW = drawH * ratio;
      const bob = state === STATE.PLAYING ? Math.sin(performance.now() / 130) * 2 : 0;
      ctx.drawImage(sprite.image, -drawW / 2, -drawH / 2 + bob, drawW, drawH);
      ctx.restore();
      return;
    }

    ctx.fillStyle = '#ffd23f';
    ctx.beginPath();
    ctx.ellipse(0, 0, 19, 15, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#f2b01e';
    ctx.beginPath();
    ctx.ellipse(-3, 4, 12, 8, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(7, -5, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#22262e';
    ctx.beginPath();
    ctx.arc(9, -5, 2.6, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#f76b1c';
    ctx.beginPath();
    ctx.moveTo(15, 1);
    ctx.lineTo(27, 5);
    ctx.lineTo(15, 9);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawScore() {
    if (state === STATE.READY) return;
    ctx.font = 'bold 54px "Segoe UI", system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.lineWidth = 6;
    ctx.strokeStyle = 'rgba(0,0,0,.45)';
    ctx.strokeText(String(score), W / 2, 88);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(String(score), W / 2, 88);
  }

  function render() {
    drawSky();
    for (const p of pipes) drawPipe(p);
    drawGround();
    drawBird();
    drawScore();
  }

  function loop(ts) {
    const dt = Math.min((ts - lastTs) / 1000 || 0, 0.033);
    lastTs = ts;
    update(dt);
    render();
    requestAnimationFrame(loop);
  }

  // ---- UI ----
  function hideOverlay() { overlay.classList.add('hidden'); }
  function showOverlay(title, text, btn) {
    overlayTitle.textContent = title;
    overlayText.innerHTML = text;
    overlayBtn.textContent = btn;
    overlay.classList.remove('hidden');
  }
  function setStatus(msg) { statusEl.textContent = msg; }

  // ---- Сохранение результата ----
  async function submitScore(value) {
    setStatus('Сохраняю результат…');
    try {
      const res = await fetch('/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: userId, score: value })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      setStatus('Сохранено. Личный рекорд: ' + data.best + ' · место ' + data.rank + ' из ' + data.total);
    } catch (_) {
      setStatus('Результат не сохранён: сервер /score не отвечает.');
    }
  }

  // ---- Ввод ----
  canvas.addEventListener('pointerdown', function (e) {
    e.preventDefault();
    if (state === STATE.PLAYING) flap();
  });

  document.addEventListener('keydown', function (e) {
    if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'KeyW') {
      e.preventDefault();
      flap();
    }
  });

  overlayBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    if (state === STATE.READY || state === STATE.OVER) startGame();
  });

  // ---- Старт ----
  reset();
  showOverlay('Flappy Meepo', 'Клик, тап или Пробел — взмах лопатой.<br>Пролетай между трубами.', 'Играть');
  loadAssets();
  requestAnimationFrame(loop);
})();
