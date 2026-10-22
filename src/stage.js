// 讀者劇場的舞台：木地板、紅色布幕、譜架、聚光燈，以及跟著講者移動的鏡頭。
// 全部用 Three.js 幾何與程式產生的貼圖，不需要外部素材。
import * as THREE from 'three';

// 演員站位（公尺）：旁白在舞台左側的講台，其他角色在中間排成淺弧形，面向觀眾
const NARRATOR_SPOT = { x: -2.6, z: 0.4, turn: 0.35 };
const ROW_Z = 0.0;
const ROW_SPACING = 1.0;
const ROW_CURVE = 0.12;

// 鏡頭：垂直視角 25 度；各景別的取景高度與距離
const FOV = 25;
const SHOTS = {
  full: { height: 1.0, distance: 9.0, wide: true },
  mid: { height: 1.0, distance: 6.0 },
  upper: { height: 1.35, distance: 2.6 },
  head: { height: 1.55, distance: 1.5 },
};
// 鏡頭移動的平滑時間常數（毫秒）
const CAMERA_EASE_MS = 450;
const SPOT_ON = 60;
const SPOT_OFF = 6;

function woodTexture() {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 512;
  const g = c.getContext('2d');
  const planks = 8;
  for (let i = 0; i < planks; i++) {
    const shade = 120 + ((i * 37) % 30);
    g.fillStyle = `rgb(${shade}, ${Math.round(shade * 0.62)}, ${Math.round(shade * 0.38)})`;
    g.fillRect(0, (i * c.height) / planks, c.width, c.height / planks);
    g.fillStyle = 'rgba(0,0,0,0.35)';
    g.fillRect(0, ((i + 1) * c.height) / planks - 2, c.width, 2);
    for (let k = 0; k < 40; k++) {
      g.fillStyle = `rgba(60,30,10,${0.05 + ((k * 13) % 7) / 100})`;
      g.fillRect((k * 97) % c.width, (i * c.height) / planks + ((k * 7) % 50), 80 + ((k * 31) % 120), 1);
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(3, 2);
  return tex;
}

// 有皺褶的布幕：平面沿寬度方向做正弦起伏
function curtain(width, height, color, folds) {
  const geo = new THREE.PlaneGeometry(width, height, folds * 8, 1);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    pos.setZ(i, 0.12 * Math.sin((x / width) * folds * Math.PI * 2));
  }
  geo.computeVertexNormals();
  return new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color, roughness: 0.85, side: THREE.DoubleSide }));
}

function musicStand(paperColor = 0xf4f1e8) {
  const group = new THREE.Group();
  const metal = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.6, roughness: 0.4 });
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 1.05, 8), metal);
  pole.position.y = 0.525;
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.02, 16), metal);
  const desk = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.35, 0.015), metal);
  desk.position.set(0, 1.12, 0);
  desk.rotation.x = -0.9;
  const paper = new THREE.Mesh(
    new THREE.PlaneGeometry(0.42, 0.3),
    new THREE.MeshStandardMaterial({ color: paperColor, roughness: 0.9 }),
  );
  paper.position.set(0, 1.125, 0.012);
  paper.rotation.x = -0.9;
  group.add(pole, base, desk, paper);
  return group;
}

function lectern() {
  const wood = new THREE.MeshStandardMaterial({ color: 0x5b3a21, roughness: 0.7 });
  const group = new THREE.Group();
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.6, 1.0, 0.4), wood);
  body.position.y = 0.5;
  const top = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.05, 0.5), wood);
  top.position.set(0, 1.05, 0.02);
  top.rotation.x = -0.25;
  group.add(body, top);
  return group;
}

// 依角色順序決定站位：第一個角色（旁白）站講台，"all" 不站位，其他人排成弧形
export function blocking(characters) {
  const actors = characters.filter((c, i) => i > 0 && c.id !== 'all');
  const spots = { [characters[0].id]: NARRATOR_SPOT };
  actors.forEach((c, i) => {
    const offset = i - (actors.length - 1) / 2;
    const x = offset * ROW_SPACING + 0.5;
    spots[c.id] = { x, z: ROW_Z - ROW_CURVE * offset * offset, turn: -0.08 * offset };
  });
  return spots;
}

// 建出舞台，回傳控制聚光燈與鏡頭的導演
export function buildStage(head, spots) {
  const { scene, camera } = head;
  scene.background = new THREE.Color(0x0a0a0f);
  head.setLighting({ lightAmbientIntensity: 0.5, lightDirectIntensity: 0.3, lightSpotIntensity: 0 });

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(12, 6),
    new THREE.MeshStandardMaterial({ map: woodTexture(), roughness: 0.6 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.z = -0.5;
  const apron = new THREE.Mesh(
    new THREE.BoxGeometry(12, 0.4, 0.1),
    new THREE.MeshStandardMaterial({ color: 0x1b120b, roughness: 0.8 }),
  );
  apron.position.set(0, -0.2, 2.5);
  scene.add(floor, apron);

  const red = 0x7a0f1a;
  const back = curtain(12, 6, red, 18);
  back.position.set(0, 3, -3);
  const left = curtain(2.2, 6, red, 4);
  left.position.set(-5.2, 3, 1.2);
  const right = left.clone();
  right.position.x = 5.2;
  const valance = curtain(12, 0.9, 0x5c0a14, 24);
  valance.position.set(0, 5.6, 1.3);
  scene.add(back, left, right, valance);

  // 每個站位：譜架（旁白是講台）與一盞聚光燈
  const lights = {};
  const ids = Object.keys(spots);
  ids.forEach((id, i) => {
    const s = spots[id];
    const prop = i === 0 ? lectern() : musicStand();
    prop.position.set(s.x + Math.sin(s.turn) * 0.55, 0, s.z + Math.cos(s.turn) * 0.55);
    prop.rotation.y = s.turn + Math.PI;
    scene.add(prop);

    const spot = new THREE.SpotLight(0xfff1d6, SPOT_OFF, 12, 0.32, 0.5, 1.2);
    spot.position.set(s.x, 6, s.z + 3);
    spot.target.position.set(s.x, 1.0, s.z);
    scene.add(spot, spot.target);
    lights[id] = spot;
  });
  const wash = new THREE.HemisphereLight(0xffe6c7, 0x2a1408, 0.6);
  scene.add(wash);

  camera.fov = FOV;
  camera.updateProjectionMatrix();

  const camPos = new THREE.Vector3(0, 1.4, 9);
  const camTarget = new THREE.Vector3(0, 1.0, 0);
  const wantPos = camPos.clone();
  const wantTarget = camTarget.clone();
  const spotLevel = Object.fromEntries(ids.map((id) => [id, SPOT_OFF]));
  const spotWant = { ...spotLevel };

  return {
    // 換鏡頭：景別 + 主角（講者 id 或 "all"）
    shot(view, speaker) {
      const s = SHOTS[view] ?? SHOTS.upper;
      const focus = spots[speaker];
      if (!focus || s.wide) {
        wantTarget.set(0, s.height, -0.2);
        wantPos.set(0, s.height + 0.6, s.distance);
      } else {
        const dir = new THREE.Vector3(Math.sin(focus.turn), 0, Math.cos(focus.turn));
        wantTarget.set(focus.x, s.height, focus.z);
        wantPos.copy(wantTarget).addScaledVector(dir, s.distance);
        wantPos.y += 0.08;
      }
    },
    // 只亮講者；"all" 全亮
    light(speaker) {
      for (const id of ids) spotWant[id] = speaker === 'all' || speaker === id ? SPOT_ON : SPOT_OFF;
    },
    update(dt) {
      const k = 1 - Math.exp(-dt / CAMERA_EASE_MS);
      camPos.lerp(wantPos, k);
      camTarget.lerp(wantTarget, k);
      camera.position.copy(camPos);
      head.controls?.target.copy(camTarget);
      camera.lookAt(camTarget);
      for (const id of ids) {
        spotLevel[id] += (spotWant[id] - spotLevel[id]) * k;
        lights[id].intensity = spotLevel[id];
      }
    },
  };
}

// 角色外觀：上衣、褲子、髮色換成純色，可隱藏眼鏡、縮放身高
export function dress(head, look = {}) {
  const colors = { Wolf3D_Outfit_Top: look.top, Wolf3D_Outfit_Bottom: look.bottom, Wolf3D_Hair: look.hair };
  head.armature.traverse((o) => {
    if (!o.isMesh) return;
    if (o.name === 'Wolf3D_Glasses' && look.glasses === false) o.visible = false;
    const color = colors[o.name];
    if (color) {
      o.material = o.material.clone();
      o.material.map = null;
      o.material.color = new THREE.Color(color);
      o.material.needsUpdate = true;
    }
  });
  if (look.scale) head.armature.scale.setScalar(look.scale);
}

// 把角色放到站位
export function place(head, spot) {
  head.armature.position.set(spot.x, 0, spot.z);
  head.armature.rotation.y = spot.turn;
}
