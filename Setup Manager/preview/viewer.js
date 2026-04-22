import * as THREE from './three.module.js';
import { OrbitControls } from './OrbitControls.js';
import { STLLoader } from './STLLoader.js';

const canvas = document.getElementById('viewport');
const status = document.getElementById('status');

let _previewEventSeq = 0;
function emitPreviewEvent(type, payload) {
  const normalizedType = String(type || '').trim();
  if (!normalizedType) return;
  let body = '{}';
  try {
    body = JSON.stringify(payload ?? {});
  } catch (_err) {
    body = '{}';
  }
  _previewEventSeq += 1;
  document.title = `${normalizedType}:${body}`;
}

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: true,
});

renderer.setPixelRatio(window.devicePixelRatio || 1);
renderer.setSize(Math.max(1, window.innerWidth), Math.max(1, window.innerHeight));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.06;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.shadowMap.autoUpdate = false;

let _shadowMapDirty = true;
function _markShadowMapDirty() {
  _shadowMapDirty = true;
}

function createStudioEnvironmentMap(activeRenderer) {
  const width = 1024;
  const height = 512;
  const envCanvas = document.createElement('canvas');
  envCanvas.width = width;
  envCanvas.height = height;
  const ctx = envCanvas.getContext('2d');
  if (!ctx) {
    return null;
  }

  const base = ctx.createLinearGradient(0, 0, 0, height);
  base.addColorStop(0.0, '#f7f9fc');
  base.addColorStop(0.24, '#cdd4dc');
  base.addColorStop(0.56, '#77818d');
  base.addColorStop(1.0, '#1f252d');
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, width, height);

  const drawSoftVerticalStrip = (centerX, stripWidth, alpha) => {
    const x0 = centerX - stripWidth * 0.5;
    const x1 = centerX + stripWidth * 0.5;
    const g = ctx.createLinearGradient(x0, 0, x1, 0);
    g.addColorStop(0.0, 'rgba(255,255,255,0)');
    g.addColorStop(0.25, `rgba(255,255,255,${alpha * 0.38})`);
    g.addColorStop(0.5, `rgba(255,255,255,${alpha})`);
    g.addColorStop(0.75, `rgba(255,255,255,${alpha * 0.38})`);
    g.addColorStop(1.0, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x0, 0, stripWidth, height);
  };

  const drawDarkVerticalStrip = (centerX, stripWidth, alpha) => {
    const x0 = centerX - stripWidth * 0.5;
    const x1 = centerX + stripWidth * 0.5;
    const g = ctx.createLinearGradient(x0, 0, x1, 0);
    g.addColorStop(0.0, 'rgba(0,0,0,0)');
    g.addColorStop(0.22, `rgba(0,0,0,${alpha * 0.35})`);
    g.addColorStop(0.5, `rgba(0,0,0,${alpha})`);
    g.addColorStop(0.78, `rgba(0,0,0,${alpha * 0.35})`);
    g.addColorStop(1.0, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x0, 0, stripWidth, height);
  };

  drawSoftVerticalStrip(width * 0.17, width * 0.12, 0.78);
  drawSoftVerticalStrip(width * 0.50, width * 0.08, 0.66);
  drawSoftVerticalStrip(width * 0.83, width * 0.12, 0.74);

  drawDarkVerticalStrip(width * 0.33, width * 0.08, 0.42);
  drawDarkVerticalStrip(width * 0.66, width * 0.09, 0.38);

  const sideFalloff = ctx.createLinearGradient(0, 0, width, 0);
  sideFalloff.addColorStop(0.0, 'rgba(0,0,0,0.45)');
  sideFalloff.addColorStop(0.12, 'rgba(0,0,0,0)');
  sideFalloff.addColorStop(0.88, 'rgba(0,0,0,0)');
  sideFalloff.addColorStop(1.0, 'rgba(0,0,0,0.42)');
  ctx.fillStyle = sideFalloff;
  ctx.fillRect(0, 0, width, height);

  const topGlow = ctx.createRadialGradient(
    width * 0.5,
    height * 0.06,
    6,
    width * 0.5,
    height * 0.06,
    width * 0.58
  );
  topGlow.addColorStop(0.0, 'rgba(255,255,255,0.58)');
  topGlow.addColorStop(1.0, 'rgba(255,255,255,0)');
  ctx.fillStyle = topGlow;
  ctx.fillRect(0, 0, width, height);

  const bottomBand = ctx.createLinearGradient(0, height * 0.63, 0, height);
  bottomBand.addColorStop(0.0, 'rgba(0,0,0,0)');
  bottomBand.addColorStop(1.0, 'rgba(0,0,0,0.42)');
  ctx.fillStyle = bottomBand;
  ctx.fillRect(0, height * 0.63, width, height * 0.37);

  const vignette = ctx.createRadialGradient(
    width * 0.5,
    height * 0.52,
    width * 0.18,
    width * 0.5,
    height * 0.52,
    width * 0.75
  );
  vignette.addColorStop(0.0, 'rgba(0,0,0,0)');
  vignette.addColorStop(1.0, 'rgba(0,0,0,0.28)');
  ctx.fillStyle = vignette;
  ctx.fillRect(0, 0, width, height);

  const equirect = new THREE.CanvasTexture(envCanvas);
  equirect.mapping = THREE.EquirectangularReflectionMapping;
  equirect.colorSpace = THREE.SRGBColorSpace;
  equirect.needsUpdate = true;

  const pmrem = new THREE.PMREMGenerator(activeRenderer);
  pmrem.compileEquirectangularShader();
  const envRT = pmrem.fromEquirectangular(equirect);
  equirect.dispose();
  pmrem.dispose();
  return envRT;
}

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xd6d9de);
const studioEnvRT = createStudioEnvironmentMap(renderer);
if (studioEnvRT) {
  scene.environment = studioEnvRT.texture;
}

const camera = new THREE.PerspectiveCamera(
  45,
  (window.innerWidth || 1) / (window.innerHeight || 1),
  0.1,
  10000
);
camera.position.set(180, 140, 180);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.enableZoom = false;

const hemi = new THREE.HemisphereLight(0xf5f8ff, 0x78808a, 0.38);
hemi.position.set(0, 220, 0);
scene.add(hemi);

const keyLight = new THREE.DirectionalLight(0xffffff, 1.18);
keyLight.position.set(140, 185, 130);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(2048, 2048);
keyLight.shadow.bias = -0.00006;
keyLight.shadow.normalBias = 0.018;
keyLight.shadow.camera.near = 20;
keyLight.shadow.camera.far = 700;
keyLight.shadow.camera.left = -280;
keyLight.shadow.camera.right = 280;
keyLight.shadow.camera.top = 280;
keyLight.shadow.camera.bottom = -280;
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0xdce7ff, 0.24);
fillLight.position.set(-170, 120, -90);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.44);
rimLight.position.set(-90, 95, 190);
scene.add(rimLight);

const ambient = new THREE.AmbientLight(0xffffff, 0.04);
scene.add(ambient);

const grid = new THREE.GridHelper(250, 12, 0xb5b5b5, 0xd5d5d5);
grid.position.y = 0;
scene.add(grid);

const shadowCatcher = new THREE.Mesh(
  new THREE.PlaneGeometry(2600, 2600),
  new THREE.ShadowMaterial({ opacity: 0.32 })
);
shadowCatcher.rotation.x = -Math.PI / 2;
shadowCatcher.position.y = -0.02;
shadowCatcher.receiveShadow = true;
scene.add(shadowCatcher);

const loader = new STLLoader();

let currentMeshes = [];
let currentGroup = null;
let currentMaxDim = 1;
let wheelZoomEnabled = false;
let alignmentPlane = 'XZ';
let statusOverlayEnabled = false;
let _activeLoadRequestId = 0;
const manualRotation = new THREE.Vector3(0, 0, 0);
const frameDirection = new THREE.Vector3(1, 0.62, 1).normalize();

function _coerceRequestId(value, fallback = null) {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return Math.max(1, Math.floor(numeric));
  }
  return fallback;
}

function _activateLoadRequest(requestId = null) {
  const normalized = _coerceRequestId(requestId, _activeLoadRequestId + 1);
  _activeLoadRequestId = normalized;
  return normalized;
}

function _isActiveLoadRequest(requestId = null) {
  const normalized = _coerceRequestId(requestId, null);
  if (normalized == null) {
    return true;
  }
  return normalized === _activeLoadRequestId;
}

function _emitModelReady(kind, nextMeshes, requestId = null) {
  emitPreviewEvent('MODEL_READY', {
    kind,
    mesh_count: Array.isArray(nextMeshes) ? nextMeshes.length : 0,
    request_id: _coerceRequestId(requestId, null),
  });
}

function showStatus(text) {
  if (!statusOverlayEnabled) {
    return;
  }
  status.textContent = text;
  status.style.display = 'block';
}

function hideStatus() {
  status.style.display = 'none';
}

function _disposeMeshList(meshes) {
  for (const mesh of meshes || []) {
    if (!mesh) continue;
    if (mesh.geometry) {
      mesh.geometry.dispose();
    }
    if (mesh.material) {
      if (Array.isArray(mesh.material)) {
        mesh.material.forEach((m) => m?.dispose && m.dispose());
      } else if (mesh.material.dispose) {
        mesh.material.dispose();
      }
    }
  }
}

function _transitionToGroup(nextGroup, nextMeshes, { refit = true, readyKind = 'model', requestId = null } = {}) {
  if (!_isActiveLoadRequest(requestId)) {
    scene.remove(nextGroup);
    _disposeMeshList(nextMeshes);
    return;
  }

  const previousGroup = currentGroup;
  const previousMeshes = currentMeshes;

  if (!previousGroup) {
    currentGroup = nextGroup;
    currentMeshes = nextMeshes;
    applyModelTransformAndFrame(refit);
    _markShadowMapDirty();
    _emitModelReady(readyKind, nextMeshes, requestId);
    return;
  }

  currentGroup = nextGroup;
  currentMeshes = nextMeshes;
  applyModelTransformAndFrame(refit);

  if (!_isActiveLoadRequest(requestId)) {
    currentGroup = previousGroup;
    currentMeshes = previousMeshes;
    scene.remove(nextGroup);
    _disposeMeshList(nextMeshes);
    _markShadowMapDirty();
    return;
  }

  scene.remove(previousGroup);
  _disposeMeshList(previousMeshes);
  _markShadowMapDirty();
  _emitModelReady(readyKind, nextMeshes, requestId);
}

const MACHINED_SKIN_KEY = 'machined-metal-skin-v2';

function _syncMachinedSkinUniforms(material) {
  const uniforms = material?.userData?._skinUniforms;
  if (!uniforms) {
    return;
  }
  uniforms.uSkinRoughnessAmount.value = material.userData.skinRoughnessAmount || 0.0;
  uniforms.uSkinScale.value = material.userData.skinScale || 0.2;
}

function installMachinedSkin(material) {
  if (!material || material.userData?._skinInstalled) {
    _syncMachinedSkinUniforms(material);
    return;
  }

  material.userData = material.userData || {};
  material.userData._skinInstalled = true;

  material.onBeforeCompile = (shader) => {
    shader.uniforms.uSkinRoughnessAmount = { value: material.userData.skinRoughnessAmount || 0.0 };
    shader.uniforms.uSkinScale = { value: material.userData.skinScale || 0.2 };
    material.userData._skinUniforms = shader.uniforms;

    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        `#include <common>
varying vec3 vModelPos;`
      )
      .replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
vModelPos = position;`
      );

    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        `#include <common>
varying vec3 vModelPos;
uniform float uSkinRoughnessAmount;
uniform float uSkinScale;

float _skinHash(vec3 p) {
  p = fract(p * 0.3183099 + vec3(0.11, 0.17, 0.23));
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float _skinNoise(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);

  float n000 = _skinHash(i + vec3(0.0, 0.0, 0.0));
  float n100 = _skinHash(i + vec3(1.0, 0.0, 0.0));
  float n010 = _skinHash(i + vec3(0.0, 1.0, 0.0));
  float n110 = _skinHash(i + vec3(1.0, 1.0, 0.0));
  float n001 = _skinHash(i + vec3(0.0, 0.0, 1.0));
  float n101 = _skinHash(i + vec3(1.0, 0.0, 1.0));
  float n011 = _skinHash(i + vec3(0.0, 1.0, 1.0));
  float n111 = _skinHash(i + vec3(1.0, 1.0, 1.0));

  float nx00 = mix(n000, n100, f.x);
  float nx10 = mix(n010, n110, f.x);
  float nx01 = mix(n001, n101, f.x);
  float nx11 = mix(n011, n111, f.x);
  float nxy0 = mix(nx00, nx10, f.y);
  float nxy1 = mix(nx01, nx11, f.y);
  return mix(nxy0, nxy1, f.z);
}`
      )
      .replace(
        '#include <roughnessmap_fragment>',
        `#include <roughnessmap_fragment>
vec3 _skinPos = vModelPos * uSkinScale;
float _grainA = _skinNoise(_skinPos * 2.6);
float _grainB = _skinNoise(_skinPos * 6.2);
float _pixelFootprint = max(max(length(dFdx(_skinPos)), length(dFdy(_skinPos))), 1e-4);
float _aaFade = 1.0 - smoothstep(0.22, 0.85, _pixelFootprint);
float _hiFreqMix = 1.0 - smoothstep(0.18, 0.72, _pixelFootprint);
float _grain = (_grainA * (0.78 + 0.14 * _hiFreqMix) + _grainB * (0.22 * _hiFreqMix)) * 2.0 - 1.0;
float _viewDistance = length(vViewPosition);
float _detailFade = 1.0 - smoothstep(70.0, 210.0, _viewDistance);
float _grainAmount = uSkinRoughnessAmount * mix(0.12, 0.64, _detailFade) * _aaFade;
roughnessFactor = clamp(roughnessFactor + _grain * _grainAmount, 0.12, 1.0);`
      );

    _syncMachinedSkinUniforms(material);
  };

  material.customProgramCacheKey = () => MACHINED_SKIN_KEY;
  material.needsUpdate = true;
}

function applyMaterialFinish(material, colorValue) {
  if (!material || !material.color) {
    return;
  }
  material.userData = material.userData || {};

  const baseColor = new THREE.Color(colorValue || '#9ea7b3');
  const displayColor = baseColor.clone();
  const hsl = { h: 0, s: 0, l: 0 };
  baseColor.getHSL(hsl);
  const neutral = hsl.s < 0.16;
  const brightNeutral = neutral && hsl.l > 0.82;
  const darkNeutral = neutral && hsl.l < 0.2;
  const machinedMetal = neutral && !brightNeutral && !darkNeutral;
  const coloredPart = !neutral;

  if (coloredPart) {
    // Keep selected swatch colors vivid under filmic tone mapping.
    const vivid = { h: hsl.h, s: hsl.s, l: hsl.l };
    vivid.s = Math.min(1.0, vivid.s * 1.14 + 0.015);
    vivid.l = Math.min(0.92, vivid.l + 0.01);
    displayColor.setHSL(vivid.h, vivid.s, vivid.l);
  }

  material.color.copy(displayColor);
  if (brightNeutral) {
    // Polished bright steel/chrome style with stronger studio reflections.
    material.metalness = 1.0;
    material.roughness = 0.19;
    material.clearcoat = 0.0;
    material.clearcoatRoughness = 0.4;
    material.envMapIntensity = 1.52;
    material.userData.skinRoughnessAmount = 0.018;
    material.userData.skinScale = 0.09;
  } else if (machinedMetal) {
    material.metalness = 0.94;
    material.roughness = 0.24;
    material.clearcoat = 0.0;
    material.clearcoatRoughness = 0.4;
    material.envMapIntensity = 1.30;
    material.userData.skinRoughnessAmount = 0.022;
    material.userData.skinScale = 0.09;
  } else if (darkNeutral) {
    // Dark parts should keep a metallic sheen and avoid matte-plastic look.
    material.metalness = 0.72;
    material.roughness = 0.26;
    material.clearcoat = 0.0;
    material.clearcoatRoughness = 0.4;
    material.envMapIntensity = 1.05;
    material.userData.skinRoughnessAmount = 0.02;
    material.userData.skinScale = 0.09;
  } else {
    // Colored components should read as true color, not gray-metal.
    material.metalness = 0.03;
    material.roughness = 0.28;
    material.clearcoat = 0.06;
    material.clearcoatRoughness = 0.24;
    material.envMapIntensity = 0.46;
    material.userData.skinRoughnessAmount = 0.006;
    material.userData.skinScale = 0.08;
  }
  _syncMachinedSkinUniforms(material);
  material.needsUpdate = true;
}

function makeMaterial(colorValue) {
  const material = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color('#9ea7b3'),
    metalness: 0.76,
    roughness: 0.24,
    clearcoat: 0.2,
    clearcoatRoughness: 0.2,
    envMapIntensity: 1.0,
  });
  installMachinedSkin(material);
  applyMaterialFinish(material, colorValue);
  return material;
}

function fitCameraToObject(object) {
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const center = sphere.center;

  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  currentMaxDim = maxDim;
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const safeRadius = Math.max(sphere.radius, 1);
  const cameraDistance = (safeRadius / Math.sin(fov / 2)) * 1.2;

  camera.position.copy(center).addScaledVector(frameDirection, cameraDistance);

  // Keep a tighter depth range to reduce z-fighting shimmer on polished parts.
  camera.near = Math.max(cameraDistance / 80, 0.2);
  camera.far = Math.max(cameraDistance * 8, 800);
  camera.updateProjectionMatrix();

  controls.target.copy(center);
  controls.update();
}

function alignObjectOnGrid(object) {
  // Keep the model centered in X/Z and seated on the grid at Y=0.
  object.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(object);
  const center = box.getCenter(new THREE.Vector3());

  object.position.x -= center.x;
  object.position.z -= center.z;
  object.position.y -= box.min.y;
  object.updateMatrixWorld(true);
}

function updateGridForObject(object) {
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());
  const footprint = Math.max(size.x, size.z, 1);
  const targetSize = THREE.MathUtils.clamp(Math.ceil(footprint * 2.4), 120, 700);

  grid.scale.set(targetSize / 250, 1, targetSize / 250);
  grid.position.y = 0;
}

function orientObjectVertically(object) {
  // Keep original part-to-part alignment, but rotate the whole object so its
  // longest bounding-box axis is vertical (Y).
  object.rotation.set(0, 0, 0);
  object.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());

  if (size.x >= size.y && size.x >= size.z) {
    // X is longest -> rotate so X maps to Y.
    object.rotation.z = Math.PI / 2;
  } else if (size.z >= size.x && size.z >= size.y) {
    // Z is longest -> rotate so Z maps to Y.
    object.rotation.x = -Math.PI / 2;
  }

  // Keep the tool pointing in the expected direction for preview.
  object.rotateX(Math.PI);

  object.updateMatrixWorld(true);
}

function applyAlignmentPlane(object) {
  if (alignmentPlane === 'XY') {
    object.rotateX(-Math.PI / 2);
  } else if (alignmentPlane === 'YZ') {
    object.rotateZ(Math.PI / 2);
  }
}

function applyModelTransformAndFrame(refit = true) {
  if (!currentGroup) {
    return;
  }

  currentGroup.rotation.set(0, 0, 0);
  currentGroup.position.set(0, 0, 0);

  orientObjectVertically(currentGroup);
  applyAlignmentPlane(currentGroup);

  currentGroup.rotateX(manualRotation.x);
  currentGroup.rotateY(manualRotation.y);
  currentGroup.rotateZ(manualRotation.z);
  _markShadowMapDirty();

  alignObjectOnGrid(currentGroup);
  updateGridForObject(currentGroup);

  if (refit) {
    fitCameraToObject(currentGroup);
  } else {
    controls.update();
  }
}

function clearCurrentMeshes() {
  for (const mesh of currentMeshes) {
    scene.remove(mesh);

    if (mesh.geometry) {
      mesh.geometry.dispose();
    }

    if (mesh.material) {
      if (Array.isArray(mesh.material)) {
        mesh.material.forEach(m => m.dispose && m.dispose());
      } else if (mesh.material.dispose) {
        mesh.material.dispose();
      }
    }
  }

  currentMeshes = [];

  if (currentGroup) {
    scene.remove(currentGroup);
    currentGroup = null;
  }
}

window.clearModel = function () {
  _activeLoadRequestId += 1;
  clearCurrentMeshes();
  _markShadowMapDirty();
  hideStatus();
};

window.setWheelZoomEnabled = function (enabled) {
  wheelZoomEnabled = !!enabled;
};

window.setStatusOverlayEnabled = function (enabled) {
  statusOverlayEnabled = !!enabled;
  if (!statusOverlayEnabled) {
    hideStatus();
  }
};

window.setAlignmentPlane = function (plane) {
  const normalized = String(plane || 'XZ').toUpperCase();
  alignmentPlane = ['XZ', 'XY', 'YZ'].includes(normalized) ? normalized : 'XZ';
  if (currentGroup) {
    applyModelTransformAndFrame(true);
  }
};

window.rotateModel = function (axis, degrees = 90) {
  const key = String(axis || '').toLowerCase();
  const radians = THREE.MathUtils.degToRad(Number(degrees) || 0);
  if (key === 'x') {
    manualRotation.x += radians;
  } else if (key === 'y') {
    manualRotation.y += radians;
  } else if (key === 'z') {
    manualRotation.z += radians;
  } else {
    return;
  }
  if (currentGroup) {
    applyModelTransformAndFrame(false);
  }
};

window.resetModelRotation = function () {
  manualRotation.set(0, 0, 0);
  if (currentGroup) {
    applyModelTransformAndFrame(false);
  }
};

window.loadModel = function (modelPath, label = null, requestId = null) {
  if (!modelPath) {
    window.clearModel();
    return;
  }

  const normalizedRequestId = _activateLoadRequest(requestId);

  loader.load(
    modelPath,
    (geometry) => {
      if (!_isActiveLoadRequest(normalizedRequestId)) {
        geometry.dispose();
        return;
      }

      geometry.computeVertexNormals();
      geometry.center();

      const mesh = new THREE.Mesh(geometry, makeMaterial('#9ea7b3'));
      mesh.castShadow = true;
      mesh.receiveShadow = false;
      const nextGroup = new THREE.Group();
      nextGroup.add(mesh);
      scene.add(nextGroup);

      _transitionToGroup(nextGroup, [mesh], { refit: true, readyKind: 'stl', requestId: normalizedRequestId });
      hideStatus();
    },
    undefined,
    (error) => {
      if (!_isActiveLoadRequest(normalizedRequestId)) {
        return;
      }
      console.error('STL load failed:', error);
      if (statusOverlayEnabled) {
        showStatus('Failed to load STL model.');
      }
    }
  );
};

window.loadAssembly = function (parts, requestId = null) {
  if (!Array.isArray(parts) || parts.length === 0) {
    window.clearModel();
    return;
  }

  const normalizedRequestId = _activateLoadRequest(requestId);

  const nextGroup = new THREE.Group();
  const nextMeshes = [];

  const loadEntries = parts
    .map((part) => ({
      file: part?.file,
      color: part?.color || '#9ea7b3',
    }))
    .filter((entry) => !!entry.file);

  if (loadEntries.length === 0) {
    if (statusOverlayEnabled) {
      showStatus('Failed to load assembly.');
    }
    return;
  }

  let remaining = loadEntries.length;
  let loadedCount = 0;
  let failedCount = 0;

  const finishIfDone = () => {
    remaining -= 1;

    if (remaining > 0) {
      return;
    }

    if (!_isActiveLoadRequest(normalizedRequestId)) {
      _disposeMeshList(nextMeshes);
      return;
    }

    if (failedCount > 0 || loadedCount !== loadEntries.length) {
      _disposeMeshList(nextMeshes);
      if (statusOverlayEnabled) {
        showStatus('Failed to load assembly.');
      }
      return;
    }

    scene.add(nextGroup);
    _transitionToGroup(nextGroup, nextMeshes, { refit: true, readyKind: 'assembly', requestId: normalizedRequestId });
    hideStatus();
  };

  loadEntries.forEach(({ file, color }) => {
    loader.load(
      file,
      (geometry) => {
        if (!_isActiveLoadRequest(normalizedRequestId)) {
          geometry.dispose();
          finishIfDone();
          return;
        }

        geometry.computeVertexNormals();

        const mesh = new THREE.Mesh(geometry, makeMaterial(color));
        mesh.castShadow = true;
        mesh.receiveShadow = false;
        nextMeshes.push(mesh);
        nextGroup.add(mesh);
        loadedCount += 1;
        finishIfDone();
      },
      undefined,
      (error) => {
        console.error('Assembly STL load failed:', file, error);
        failedCount += 1;
        finishIfDone();
      }
    );
  });
};

canvas.addEventListener('wheel', (event) => {
  if (!wheelZoomEnabled && !event.ctrlKey) {
    return;
  }

  event.preventDefault();

  const offset = camera.position.clone().sub(controls.target);
  // Scale zoom step with wheel delta so normal mouse wheels are responsive,
  // while touchpads still remain smooth.
  const magnitude = Math.abs(event.deltaY);
  const step = Math.min(0.35, Math.max(0.05, magnitude * 0.0018));
  const zoomFactor = event.deltaY > 0 ? (1 + step) : (1 - step);
  offset.multiplyScalar(zoomFactor);

  // Clamp zoom distance so one wheel move cannot jump too far.
  const minDist = Math.max(currentMaxDim * 0.32, 2);
  const maxDist = Math.max(currentMaxDim * 22, 300);
  const dist = offset.length();
  offset.setLength(Math.min(maxDist, Math.max(minDist, dist)));

  camera.position.copy(controls.target).add(offset);
  camera.updateProjectionMatrix();
  controls.update();
}, { passive: false });

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  if (_shadowMapDirty) {
    renderer.shadowMap.needsUpdate = true;
    _shadowMapDirty = false;
  }
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  const w = window.innerWidth;
  const h = window.innerHeight;
  if (w < 1 || h < 1) return;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
});

hideStatus();
