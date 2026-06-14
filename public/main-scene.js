/* main-scene.js — Pantheon Floor walking scene (Three.js r128) */
const PantheonFloor = (() => {
  'use strict';

  let _renderer = null, _animId = null, _scene = null, _camera = null;
  let _raycaster = null, _mouse = null, _agents = [];
  let _canvas = null, _container = null;

  // Agent configs
  const AGENT_DEFS = [
    { name:'HEIMDALL', body:0x5ec8e0, accent:0x00d4ff, skinCol:0xffd0a0, z:-0.5 },
    { name:'VULCAN',   body:0xff6600, accent:0xffaa00, skinCol:0xffd0a0, z: 0.8 },
    { name:'LOKI',     body:0x1a6b2f, accent:0x2dff6f, skinCol:0xffd0a0, z:-1.2 },
    { name:'VAULT',    body:0xd4a017, accent:0xffd700, skinCol:0xffd0a0, z: 0.2 },
    { name:'GUARDIAN', body:0x8b1a1a, accent:0xff2222, skinCol:0xffd0a0, z:-0.8 },
  ];

  // ── helpers ──────────────────────────────────────────────────────────────
  const T = () => window.THREE;
  function mat(color, opts = {}) {
    return new (T().MeshToonMaterial)({ color, ...opts });
  }
  function box(w, h, d, color, opts) {
    const m = new (T().Mesh)(new (T().BoxGeometry)(w, h, d), mat(color, opts));
    m.castShadow = true;
    return m;
  }
  function sph(r, color, opts) {
    const m = new (T().Mesh)(new (T().SphereGeometry)(r, 14, 14), mat(color, opts));
    m.castShadow = true;
    return m;
  }
  function cyl(rt, rb, h, color, opts, segs = 10) {
    const m = new (T().Mesh)(new (T().CylinderGeometry)(rt, rb, h, segs), mat(color, opts));
    m.castShadow = true;
    return m;
  }
  function tor(r, t, color, opts) {
    const m = new (T().Mesh)(new (T().TorusGeometry)(r, t, 8, 20), mat(color, opts));
    m.castShadow = true;
    return m;
  }
  function grp(...children) {
    const g = new (T().Group)();
    children.forEach(c => g.add(c));
    return g;
  }

  // ── character builder ─────────────────────────────────────────────────────
  function buildAgent(def) {
    const { body, accent, skinCol } = def;
    const root = new (T().Group)();

    // torso
    const torso = box(0.35, 0.42, 0.20, body);
    torso.position.y = 0.72;
    root.add(torso);

    // head
    const head = sph(0.18, skinCol);
    head.position.y = 1.10;
    root.add(head);

    // eyes
    const eyeL = sph(0.04, accent, { emissive: new (T().Color)(accent), emissiveIntensity: 1.5 });
    eyeL.position.set(-0.07, 1.13, 0.16);
    const eyeR = sph(0.04, accent, { emissive: new (T().Color)(accent), emissiveIntensity: 1.5 });
    eyeR.position.set(0.07, 1.13, 0.16);
    root.add(eyeL, eyeR);

    // upper arms (pivot at shoulder)
    const armPivotL = new (T().Group)();
    armPivotL.position.set(-0.23, 0.9, 0);
    const armL = cyl(0.055, 0.045, 0.30, body);
    armL.position.y = -0.15;
    armPivotL.add(armL);
    root.add(armPivotL);

    const armPivotR = new (T().Group)();
    armPivotR.position.set(0.23, 0.9, 0);
    const armR = cyl(0.055, 0.045, 0.30, body);
    armR.position.y = -0.15;
    armPivotR.add(armR);
    root.add(armPivotR);

    // hands
    const handL = sph(0.06, skinCol);
    handL.position.y = -0.30;
    armPivotL.add(handL);
    const handR = sph(0.06, skinCol);
    handR.position.y = -0.30;
    armPivotR.add(handR);

    // hips
    const hips = box(0.32, 0.12, 0.18, body);
    hips.position.y = 0.48;
    root.add(hips);

    // leg pivots at hip
    const legPivotL = new (T().Group)();
    legPivotL.position.set(-0.11, 0.44, 0);
    const legL = cyl(0.07, 0.055, 0.38, body);
    legL.position.y = -0.19;
    const footL = box(0.10, 0.06, 0.16, 0x222222);
    footL.position.y = -0.40;
    footL.position.z = 0.04;
    legPivotL.add(legL, footL);
    root.add(legPivotL);

    const legPivotR = new (T().Group)();
    legPivotR.position.set(0.11, 0.44, 0);
    const legR = cyl(0.07, 0.055, 0.38, body);
    legR.position.y = -0.19;
    const footR = box(0.10, 0.06, 0.16, 0x222222);
    footR.position.y = -0.40;
    footR.position.z = 0.04;
    legPivotR.add(legR, footR);
    root.add(legPivotR);

    // per-agent accessories
    if (def.name === 'HEIMDALL') {
      // bifrost horn ring on head
      const horn = tor(0.12, 0.025, accent, { emissive: new (T().Color)(accent), emissiveIntensity: 0.8 });
      horn.position.y = 1.26;
      horn.rotation.x = Math.PI / 2;
      root.add(horn);
    } else if (def.name === 'VULCAN') {
      // hard hat
      const brim = cyl(0.24, 0.24, 0.04, 0xffcc00, {}, 12);
      brim.position.y = 1.26;
      const crown = cyl(0.16, 0.20, 0.15, 0xffcc00, {}, 12);
      crown.position.y = 1.36;
      root.add(brim, crown);
    } else if (def.name === 'LOKI') {
      // two curved horns
      [-0.10, 0.10].forEach((xo, i) => {
        const h1 = cyl(0.025, 0.035, 0.14, 0x111111);
        h1.position.set(xo, 1.24, 0);
        h1.rotation.z = (i === 0 ? 1 : -1) * 0.35;
        const h2 = cyl(0.018, 0.025, 0.10, 0x111111);
        h2.position.set(xo + (i===0?-0.07:0.07), 1.36, 0);
        h2.rotation.z = (i === 0 ? 1 : -1) * 0.65;
        root.add(h1, h2);
      });
    } else if (def.name === 'VAULT') {
      // top hat
      const hatBrim = cyl(0.22, 0.22, 0.04, 0x111111, {}, 12);
      hatBrim.position.y = 1.26;
      const hatBody = cyl(0.14, 0.14, 0.22, 0x111111, {}, 12);
      hatBody.position.y = 1.41;
      const band = cyl(0.145, 0.145, 0.04, accent, {}, 12);
      band.position.y = 1.28;
      root.add(hatBrim, hatBody, band);
    } else if (def.name === 'GUARDIAN') {
      // military helmet
      const helm = sph(0.20, 0x333333);
      helm.position.y = 1.14;
      helm.scale.y = 0.75;
      const visor = box(0.22, 0.06, 0.22, accent, { emissive: new (T().Color)(accent), emissiveIntensity: 1.2 });
      visor.position.set(0, 1.09, 0.10);
      root.add(helm, visor);
    }

    // name sprite (canvas texture label)
    const labelCanvas = document.createElement('canvas');
    labelCanvas.width = 256; labelCanvas.height = 64;
    const ctx = labelCanvas.getContext('2d');
    ctx.fillStyle = 'rgba(0,0,0,0.7)';
    ctx.roundRect(4, 8, 248, 48, 8);
    ctx.fill();
    ctx.fillStyle = '#' + accent.toString(16).padStart(6, '0');
    ctx.font = 'bold 28px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(def.name, 128, 32);
    const tex = new (T().CanvasTexture)(labelCanvas);
    const labelMat = new (T().SpriteMaterial)({ map: tex, transparent: true });
    const label = new (T().Sprite)(labelMat);
    label.scale.set(0.8, 0.2, 1);
    label.position.y = 1.50;
    root.add(label);

    // hitbox (invisible, for raycasting)
    const hitbox = new (T().Mesh)(
      new (T().BoxGeometry)(0.5, 1.4, 0.4),
      new (T().MeshBasicMaterial)({ visible: false })
    );
    hitbox.position.y = 0.7;
    hitbox.userData.agentName = def.name;
    root.add(hitbox);

    return {
      root,
      legPivotL, legPivotR,
      armPivotL, armPivotR,
      hitbox,
      // walking state
      x: (AGENT_DEFS.indexOf(def) - 2) * 1.8,
      z: def.z,
      dir: (AGENT_DEFS.indexOf(def) % 2 === 0) ? 1 : -1,
      speed: 0.6 + Math.random() * 0.3,
      phase: Math.random() * Math.PI * 2,
      name: def.name,
    };
  }

  // ── init ─────────────────────────────────────────────────────────────────
  function init(container) {
    dispose();
    _container = container;
    if (!window.THREE) {
      container.innerHTML = '<div style="color:#00d4ff;font-family:monospace;font-size:11px;padding:20px;text-align:center;letter-spacing:2px;">LOADING THREE.JS...</div>';
      const check = setInterval(() => { if (window.THREE) { clearInterval(check); init(container); } }, 200);
      return;
    }

    const w = container.clientWidth || 800;
    const h = container.clientHeight || 280;

    // renderer
    _renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    _renderer.setSize(w, h);
    _renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    _renderer.shadowMap.enabled = true;
    _renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    _renderer.toneMapping = THREE.ACESFilmicToneMapping;
    _renderer.toneMappingExposure = 0.9;
    _renderer.outputEncoding = THREE.sRGBEncoding;
    _canvas = _renderer.domElement;
    container.innerHTML = '';
    container.appendChild(_canvas);

    // scene
    _scene = new THREE.Scene();
    _scene.background = new THREE.Color(0x000510);
    _scene.fog = new THREE.FogExp2(0x000510, 0.12);

    // camera — slightly angled down, wide view
    _camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 60);
    _camera.position.set(0, 3.2, 7.5);
    _camera.lookAt(0, 0.5, 0);

    // lighting
    const amb = new THREE.AmbientLight(0x1a2a4a, 1.2);
    _scene.add(amb);
    const sun = new THREE.DirectionalLight(0x88ccff, 1.8);
    sun.position.set(5, 10, 5);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    _scene.add(sun);
    // accent fill lights
    _scene.add(Object.assign(new THREE.PointLight(0x00d4ff, 0.8, 20), { position: new THREE.Vector3(-8, 3, 0) }));
    _scene.add(Object.assign(new THREE.PointLight(0xff6600, 0.5, 20), { position: new THREE.Vector3(8, 3, 0) }));

    // floor
    const floorGeo = new THREE.PlaneGeometry(24, 8, 24, 8);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x050e1f,
      metalness: 0.3,
      roughness: 0.8,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    _scene.add(floor);

    // floor grid lines
    const gridHelper = new THREE.GridHelper(24, 24, 0x003355, 0x001a33);
    gridHelper.position.y = 0.01;
    _scene.add(gridHelper);

    // back wall with glowing strips
    const wallGeo = new THREE.PlaneGeometry(24, 4);
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x02080f, roughness: 1 });
    const wall = new THREE.Mesh(wallGeo, wallMat);
    wall.position.set(0, 2, -4);
    _scene.add(wall);

    // glowing horizontal strips on wall
    [0.6, 1.8, 3.0].forEach((y, i) => {
      const strip = new THREE.Mesh(
        new THREE.PlaneGeometry(22, 0.04),
        new THREE.MeshBasicMaterial({ color: i === 1 ? 0x00d4ff : 0x003366 })
      );
      strip.position.set(0, y, -3.95);
      _scene.add(strip);
    });

    // PANTHEON text on wall
    const tCanvas = document.createElement('canvas');
    tCanvas.width = 1024; tCanvas.height = 128;
    const tc = tCanvas.getContext('2d');
    tc.fillStyle = 'rgba(0,0,0,0)';
    tc.fillRect(0, 0, 1024, 128);
    tc.fillStyle = '#00d4ff';
    tc.font = 'bold 64px monospace';
    tc.textAlign = 'center';
    tc.textBaseline = 'middle';
    tc.letterSpacing = '12px';
    tc.fillText('ASGARDMADE PANTHEON', 512, 64);
    const tTex = new THREE.CanvasTexture(tCanvas);
    const tSprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tTex, transparent: true }));
    tSprite.scale.set(9, 1.1, 1);
    tSprite.position.set(0, 3.2, -3.9);
    _scene.add(tSprite);

    // build agents
    _agents = AGENT_DEFS.map(def => {
      const ag = buildAgent(def);
      ag.root.position.set(ag.x, 0, ag.z);
      ag.root.rotation.y = ag.dir > 0 ? 0 : Math.PI;
      _scene.add(ag.root);
      return ag;
    });

    // raycaster + click
    _raycaster = new THREE.Raycaster();
    _mouse = new THREE.Vector2();

    _canvas.addEventListener('click', onCanvasClick, false);
    _canvas.addEventListener('mousemove', onCanvasHover, false);

    // resize observer
    const ro = new ResizeObserver(() => {
      const nw = container.clientWidth;
      const nh = container.clientHeight;
      if (nw > 0 && nh > 0) {
        _renderer.setSize(nw, nh);
        _camera.aspect = nw / nh;
        _camera.updateProjectionMatrix();
      }
    });
    ro.observe(container);
    _renderer._ro = ro;

    // loop
    let last = performance.now();
    function loop(now) {
      _animId = requestAnimationFrame(loop);
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      const t = now / 1000;
      update(dt, t);
      _renderer.render(_scene, _camera);
    }
    _animId = requestAnimationFrame(loop);
  }

  // ── update ────────────────────────────────────────────────────────────────
  const WALK_RANGE = 9.5;
  function update(dt, t) {
    _agents.forEach(ag => {
      ag.phase += dt;
      const walkT = ag.phase * ag.speed * 2.5;
      const swing = Math.sin(walkT) * 0.45;

      // leg swing
      ag.legPivotL.rotation.x = swing;
      ag.legPivotR.rotation.x = -swing;

      // arm counter-swing
      ag.armPivotL.rotation.x = -swing * 0.6;
      ag.armPivotR.rotation.x = swing * 0.6;

      // body bob
      ag.root.position.y = Math.abs(Math.sin(walkT)) * 0.04;

      // move
      ag.x += ag.dir * ag.speed * dt;

      // turn around at edges
      if (ag.x > WALK_RANGE) { ag.x = WALK_RANGE; ag.dir = -1; ag.root.rotation.y = Math.PI; }
      if (ag.x < -WALK_RANGE) { ag.x = -WALK_RANGE; ag.dir = 1; ag.root.rotation.y = 0; }

      ag.root.position.x = ag.x;
      ag.root.position.z = ag.z;
    });

    // slow camera drift
    _camera.position.x = Math.sin(t * 0.05) * 1.2;
    _camera.lookAt(0, 0.5, 0);
  }

  // ── interaction ───────────────────────────────────────────────────────────
  function getHitAgent(event) {
    const rect = _canvas.getBoundingClientRect();
    _mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    _mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    _raycaster.setFromCamera(_mouse, _camera);
    const hitboxes = _agents.map(a => a.hitbox);
    const hits = _raycaster.intersectObjects(hitboxes, false);
    if (hits.length > 0) return hits[0].object.userData.agentName;
    return null;
  }

  function onCanvasClick(e) {
    const name = getHitAgent(e);
    if (name && typeof openChat === 'function') openChat(name);
  }

  function onCanvasHover(e) {
    const name = getHitAgent(e);
    _canvas.style.cursor = name ? 'pointer' : 'crosshair';
  }

  // ── dispose ───────────────────────────────────────────────────────────────
  function dispose() {
    cancelAnimationFrame(_animId);
    _animId = null;
    if (_canvas) {
      _canvas.removeEventListener('click', onCanvasClick);
      _canvas.removeEventListener('mousemove', onCanvasHover);
    }
    if (_renderer) {
      if (_renderer._ro) _renderer._ro.disconnect();
      _renderer.dispose();
      _renderer = null;
    }
    _scene = null;
    _camera = null;
    _agents = [];
    _canvas = null;
  }

  return { init, dispose };
})();
