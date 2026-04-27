import * as THREE from './three.module.js';
import { OrbitControls } from './OrbitControls.js';
import { STLLoader } from './STLLoader.js';
import { TransformControls } from './TransformControls.js';
import { emitPreviewEvent, getPreviewBridgeStats } from './bridge_adapter.js';
import { parseOverlayVector, formatVec3 } from './measurement_vectors.js';
import { createMeasurementFactories } from './measurement_types.js';
import { createMeasurementDragController } from './measurement_drag_controller.js';
import { createSelectionProxyDragState } from './transform_state.js';
import { applySelectionProxyTransformDelta } from './transform_delta_engine.js';

const canvas = document.getElementById('viewport');
const status = document.getElementById('status');
const hintElement = document.getElementById('hint');
const axisOrbitCanvas = document.getElementById('axis-orbit');
const defaultControlHintText = hintElement ? hintElement.textContent : '';
const axisOrbitCtx = axisOrbitCanvas ? axisOrbitCanvas.getContext('2d') : null;
let axisOrbitVisible = false;
let _axisOrbitLastDpr = 0;
let _axisOrbitLastWidth = 0;
let _axisOrbitLastHeight = 0;
const _axisOrbitInvQuat = new THREE.Quaternion();
const _axisOrbitRefQuat = new THREE.Quaternion();
const _overlayVectorQuat = new THREE.Quaternion();
const _overlayVectorInvQuat = new THREE.Quaternion();
const _axisOrbitAxes = [
  { key: 'X', color: '#d64545', world: new THREE.Vector3(1, 0, 0), camera: new THREE.Vector3() },
  { key: 'Y', color: '#29a34a', world: new THREE.Vector3(0, 1, 0), camera: new THREE.Vector3() },
  { key: 'Z', color: '#2f66d2', world: new THREE.Vector3(0, 0, 1), camera: new THREE.Vector3() },
];

function _axisOrbitMeshByPartReference(partIndexValue, partNameValue) {
  const partIndex = Number(partIndexValue);
  const partName = String(partNameValue || '').trim();
  return (
    _findPartMeshByIndex(Number.isInteger(partIndex) ? partIndex : null)
    || _findPartMeshByName(partName)
  );
}

function _axisOrbitReferenceMeshForOverlay(overlay) {
  if (!overlay || typeof overlay !== 'object') {
    return null;
  }

  // Most overlay types use part/part_index directly.
  let mesh = _axisOrbitMeshByPartReference(overlay.part_index, overlay.part);
  if (mesh) {
    return mesh;
  }

  // Distance overlays anchor to start/end parts.
  const overlayType = String(overlay.type || '').trim().toLowerCase();
  if (overlayType === 'distance') {
    mesh = _axisOrbitMeshByPartReference(overlay.start_part_index, overlay.start_part);
    if (mesh) {
      return mesh;
    }
    mesh = _axisOrbitMeshByPartReference(overlay.end_part_index, overlay.end_part);
    if (mesh) {
      return mesh;
    }
  }

  return null;
}

function _overlayVectorLocalToWorld(overlay, vector) {
  if (!vector || !(vector instanceof THREE.Vector3)) {
    return null;
  }
  const refMesh = _axisOrbitReferenceMeshForOverlay(overlay);
  if (!refMesh) {
    return vector.clone();
  }
  refMesh.getWorldQuaternion(_overlayVectorQuat);
  return vector.clone().applyQuaternion(_overlayVectorQuat);
}

function _overlayVectorWorldToLocal(overlay, vector) {
  if (!vector || !(vector instanceof THREE.Vector3)) {
    return null;
  }
  const refMesh = _axisOrbitReferenceMeshForOverlay(overlay);
  if (!refMesh) {
    return vector.clone();
  }
  refMesh.getWorldQuaternion(_overlayVectorQuat);
  _overlayVectorInvQuat.copy(_overlayVectorQuat).invert();
  return vector.clone().applyQuaternion(_overlayVectorInvQuat);
}

function _axisOrbitReferenceObject() {
  const focusedIndex = _normalizeMeasurementFocusIndex(measurementFocusIndex);
  if (focusedIndex >= 0 && focusedIndex < measurementOverlays.length) {
    const focusedOverlay = measurementOverlays[focusedIndex];
    if (focusedOverlay && typeof focusedOverlay === 'object') {
      const focusedMesh = _axisOrbitReferenceMeshForOverlay(focusedOverlay);
      if (focusedMesh) {
        return focusedMesh;
      }
    }
  }

  if (selectedMeshIndex >= 0 && selectedMeshIndex < currentMeshes.length && currentMeshes[selectedMeshIndex]) {
    return currentMeshes[selectedMeshIndex];
  }
  for (const mesh of currentMeshes) {
    if (mesh) {
      return mesh;
    }
  }
  if (currentGroup) {
    return currentGroup;
  }
  return null;
}

function _setControlHintText(text) {
  if (!hintElement) return;
  const normalized = typeof text === 'string' ? text.trim() : '';
  hintElement.textContent = normalized || defaultControlHintText;
}

function _hexToRgba(hex, alpha = 1) {
  const normalized = String(hex || '').replace('#', '').trim();
  if (normalized.length !== 6) {
    return `rgba(0,0,0,${alpha})`;
  }
  const r = Number.parseInt(normalized.slice(0, 2), 16);
  const g = Number.parseInt(normalized.slice(2, 4), 16);
  const b = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function _syncAxisOrbitCanvasSize() {
  if (!axisOrbitCanvas || !axisOrbitCtx) return false;
  const rect = axisOrbitCanvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return false;
  const dpr = Math.max(window.devicePixelRatio || 1, 1);
  const targetW = Math.max(1, Math.round(rect.width * dpr));
  const targetH = Math.max(1, Math.round(rect.height * dpr));
  const changed = (
    axisOrbitCanvas.width !== targetW
    || axisOrbitCanvas.height !== targetH
    || _axisOrbitLastDpr !== dpr
    || _axisOrbitLastWidth !== rect.width
    || _axisOrbitLastHeight !== rect.height
  );
  if (changed) {
    axisOrbitCanvas.width = targetW;
    axisOrbitCanvas.height = targetH;
    _axisOrbitLastDpr = dpr;
    _axisOrbitLastWidth = rect.width;
    _axisOrbitLastHeight = rect.height;
  }
  return true;
}

function _drawAxisOrbit() {
  if (!axisOrbitVisible || !axisOrbitCanvas || !axisOrbitCtx) return;
  if (!_syncAxisOrbitCanvasSize()) return;

  const dpr = Math.max(window.devicePixelRatio || 1, 1);
  const w = axisOrbitCanvas.width;
  const h = axisOrbitCanvas.height;
  const cx = w * 0.5;
  const cy = h * 0.5;
  const orbitRadius = Math.min(w, h) * 0.36;
  const axisRadius = orbitRadius * 0.78;

  axisOrbitCtx.clearRect(0, 0, w, h);

  const sphereGradient = axisOrbitCtx.createRadialGradient(
    cx - orbitRadius * 0.35,
    cy - orbitRadius * 0.35,
    orbitRadius * 0.08,
    cx,
    cy,
    orbitRadius * 1.08
  );
  sphereGradient.addColorStop(0, 'rgba(255, 255, 255, 0.98)');
  sphereGradient.addColorStop(1, 'rgba(219, 228, 238, 0.92)');
  axisOrbitCtx.fillStyle = sphereGradient;
  axisOrbitCtx.beginPath();
  axisOrbitCtx.arc(cx, cy, orbitRadius, 0, Math.PI * 2);
  axisOrbitCtx.fill();
  axisOrbitCtx.strokeStyle = 'rgba(151, 165, 181, 0.85)';
  axisOrbitCtx.lineWidth = 1 * dpr;
  axisOrbitCtx.stroke();

  // Show local axes of the active model/part so helper matches transformed geometry.
  _axisOrbitInvQuat.copy(camera.quaternion).invert();
  const refObject = _axisOrbitReferenceObject();
  if (refObject) {
    refObject.getWorldQuaternion(_axisOrbitRefQuat);
  } else {
    _axisOrbitRefQuat.identity();
  }
  for (const axis of _axisOrbitAxes) {
    axis.camera.copy(axis.world);
    axis.camera.applyQuaternion(_axisOrbitRefQuat);
    axis.camera.applyQuaternion(_axisOrbitInvQuat).normalize();
  }

  // Draw back-facing axes first so front-facing axes stay readable.
  const sortedAxes = [..._axisOrbitAxes].sort((a, b) => b.camera.z - a.camera.z);
  const fontPx = Math.max(10, Math.round(11 * dpr));
  axisOrbitCtx.font = `700 ${fontPx}px "Segoe UI", Arial, sans-serif`;
  axisOrbitCtx.textAlign = 'center';
  axisOrbitCtx.textBaseline = 'middle';

  for (const axis of sortedAxes) {
    const sx = axis.camera.x;
    const sy = -axis.camera.y;
    const ex = cx + sx * axisRadius;
    const ey = cy + sy * axisRadius;
    const towardViewer = axis.camera.z < 0;
    const alpha = towardViewer ? 1.0 : 0.5;
    const lineWidth = towardViewer ? 2.3 * dpr : 1.45 * dpr;
    const color = _hexToRgba(axis.color, alpha);

    axisOrbitCtx.strokeStyle = color;
    axisOrbitCtx.lineWidth = lineWidth;
    axisOrbitCtx.beginPath();
    axisOrbitCtx.moveTo(cx, cy);
    axisOrbitCtx.lineTo(ex, ey);
    axisOrbitCtx.stroke();

    const len = Math.max(1e-6, Math.hypot(ex - cx, ey - cy));
    const ux = (ex - cx) / len;
    const uy = (ey - cy) / len;
    const endpointRadius = towardViewer ? (3.2 * dpr) : (2.5 * dpr);
    axisOrbitCtx.fillStyle = color;
    axisOrbitCtx.beginPath();
    axisOrbitCtx.arc(ex, ey, endpointRadius, 0, Math.PI * 2);
    axisOrbitCtx.fill();

    const labelOffset = 11 * dpr;
    const lx = ex + ux * labelOffset;
    const ly = ey + uy * labelOffset;
    axisOrbitCtx.strokeStyle = 'rgba(255, 255, 255, 0.92)';
    axisOrbitCtx.lineWidth = 2.8 * dpr;
    axisOrbitCtx.strokeText(axis.key, lx, ly);
    axisOrbitCtx.fillStyle = _hexToRgba(axis.color, towardViewer ? 1.0 : 0.84);
    axisOrbitCtx.fillText(axis.key, lx, ly);
  }

  axisOrbitCtx.fillStyle = 'rgba(43, 56, 72, 0.9)';
  axisOrbitCtx.beginPath();
  axisOrbitCtx.arc(cx, cy, 2.7 * dpr, 0, Math.PI * 2);
  axisOrbitCtx.fill();
}

function _setAxisOrbitVisible(visible) {
  axisOrbitVisible = !!visible;
  if (!axisOrbitCanvas) return;
  axisOrbitCanvas.style.display = axisOrbitVisible ? 'block' : 'none';
  if (axisOrbitVisible) {
    _drawAxisOrbit();
  }
}

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: true,
});
renderer.setClearColor(0xd6d9de, 1.0);

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
controls.enablePan = true;
controls.panSpeed = 1.0;
controls._orbitSnappingMm = 1.0;

const transformControl = new TransformControls(camera, renderer.domElement);
transformControl.setSize(0.8);
transformControl.visible = false;
scene.add(transformControl);

const TRANSLATE_DRAG_GAIN = 0.35;
const FINE_DRAG_GAIN = 0.02;
const ROTATE_DRAG_GAIN = 0.2;
const FINE_ROTATE_DRAG_GAIN = 0.05;

// Adaptive per-drag translation gains, recomputed at drag start based on camera
// distance so that the snapping step (1 mm regular / 0.1 mm fine) always
// corresponds to roughly the same number of screen pixels regardless of zoom.
let _activeDragFineGain = FINE_DRAG_GAIN;
let _activeDragRegularGain = TRANSLATE_DRAG_GAIN;

let fineTransformSnapEnabled = false;

function _updateTransformSnap() {
  const translationStep = fineTransformSnapEnabled ? 0.1 : 1;
  const rotationStep = fineTransformSnapEnabled ? 0.1 : 1;
  const translationGain = fineTransformSnapEnabled ? _activeDragFineGain : _activeDragRegularGain;
  const rotationGain = fineTransformSnapEnabled ? FINE_ROTATE_DRAG_GAIN : ROTATE_DRAG_GAIN;

  transformControl.setTranslationSnap(translationStep);
  transformControl.setRotationSnap(THREE.MathUtils.degToRad(rotationStep));
  transformControl.setTranslationGain(translationGain);
  transformControl.setRotationGain(rotationGain);
}

_updateTransformSnap();
const selectionProxy = new THREE.Group();
selectionProxy.visible = false;
scene.add(selectionProxy);

transformControl.addEventListener('dragging-changed', (event) => {
  controls.enabled = !event.value;
  if (event.value && transformControl.object) {
    // Compute camera-adaptive translation gains so step size is consistent
    // regardless of zoom level (~5 px of mouse drag per logical step).
    const _vFovHalfTan = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    const _camDist = Math.max(camera.position.distanceTo(controls.target), 1);
    const _wPerPx = 2 * _camDist * _vFovHalfTan / Math.max(renderer.domElement.clientHeight, 1);
    const _targetPxPerStep = 5;
    _activeDragFineGain = 0.1 / (_targetPxPerStep * _wPerPx);
    _activeDragRegularGain = 1.0 / (_targetPxPerStep * _wPerPx);
    _updateTransformSnap();
  }
  if (event.value && transformControl.object === selectionProxy) {
    _selectionProxyDragState = createSelectionProxyDragState(selectionProxy);
  }
  if (!event.value) {
    _selectionProxyDragState = null;
    _updateTransformSnap();
    _markShadowMapDirty();
    _gizmoDragJustEnded = true;
    setTimeout(() => { _gizmoDragJustEnded = false; }, 100);
  }
});

transformControl.addEventListener('objectChange', () => {
  const mesh = transformControl.object;
  if (mesh === selectionProxy && selectedMeshIndices.length >= 1) {
    _applySelectionProxyTransform();
    return;
  }
  if (mesh && typeof mesh._partIndex === 'number') {
    const index = mesh._partIndex;
    if (index >= 0 && index < partTransforms.length) {
      const t = partTransforms[index];
      const snapMm = fineTransformSnapEnabled ? _snapFineMm : _snapMm;
      const snapDegrees = fineTransformSnapEnabled ? _snapFineDegrees : _snapDegrees;
      if (transformControl.getMode() === 'translate') {
        t.x = snapMm(mesh.position.x);
        t.y = snapMm(mesh.position.y);
        t.z = snapMm(mesh.position.z);
      } else {
        t.rx = snapDegrees(THREE.MathUtils.radToDeg(mesh.rotation.x));
        t.ry = snapDegrees(THREE.MathUtils.radToDeg(mesh.rotation.y));
        t.rz = snapDegrees(THREE.MathUtils.radToDeg(mesh.rotation.z));
      }
    }
  }
  _syncSelectedTransform();
  _scheduleMeasurementsRender();
});

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

const measurementGroup = new THREE.Group();
measurementGroup.visible = false;
scene.add(measurementGroup);

const loader = new STLLoader();

let currentMeshes = [];
let currentGroup = null;
let currentMaxDim = 1;
let wheelZoomEnabled = false;
let alignmentPlane = 'XZ';
const manualRotation = new THREE.Vector3(0, 0, 0);
let _lockedBaseRotation = null; // {x,y,z} in radians — skips orientObjectVertically when set
const frameDirection = new THREE.Vector3(1, 0.62, 1).normalize();
let transformEditEnabled = false;
let selectedMeshIndex = -1;
let requestedSelectedMeshIndex = -1;
let selectedMeshIndices = [];
let requestedSelectedMeshIndices = [];
let partTransforms = [];
let measurementOverlays = [];
let measurementsVisible = false;
let measurementFilter = '';
let measurementDragEnabled = false;
let measurementRenderQueued = false;
let measurementFocusIndex = -1;
let _measurementListContainer = null;
let _measurementListSignature = '';
let renderingEnabled = true;
let _gizmoDragJustEnded = false;
let _cameraDragJustEnded = false;
let _cameraPointerDown = null;
let _cameraPointerMoved = false;
const _CAMERA_DRAG_THRESHOLD_PX = 3;
let pointPickingEnabled = false;
let _pickMarker = null;
const _tcRaycaster = new THREE.Raycaster();
const _tcPointer = new THREE.Vector2();
const _measurementDragRaycaster = new THREE.Raycaster();
const _measurementDragPointer = new THREE.Vector2();
let _selectionProxyDragState = null;
const _missingAnchorWarningKeys = new Set();

function _markCameraDragJustEnded() {
  _cameraDragJustEnded = true;
  setTimeout(() => { _cameraDragJustEnded = false; }, 120);
}

let statusOverlayEnabled = false;
let _activeLoadRequestId = 0;

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

// Measurement color scheme - distinctive colors for each type
const measurementColors = {
  distance: 0x00b7ff,       // Electric cyan-blue
  diameter_ring: 0xff483b,  // Bright red
  radius: 0x2b87ff,         // Bright blue
  angle: 0xff32d6,          // Bright magenta
};
const MEAS_OVERLAY_RENDER_ORDER = 1600;
const MEAS_OVERLAY_MIN_TRANSPARENT_OPACITY = 0.9;
const MEAS_DISTANCE_BEAM_BASE_RADIUS_FACTOR = 0.0018;
const MEAS_DISTANCE_BEAM_MIN_RADIUS = 0.08;
const MEAS_DISTANCE_BEAM_MAX_RADIUS_FACTOR = 0.0042;

// 3D measurement value label styling (rendered as depth-tested sprites)
const MEAS_LABEL_FONT_PX = 16;
const MEAS_LABEL_TARGET_PX_HEIGHT = 18;
const MEAS_LABEL_MIN_PX_HEIGHT = 14;
const MEAS_LABEL_MAX_PX_HEIGHT = 28;
const MEAS_LABEL_PADDING_X = 10;
const MEAS_LABEL_PADDING_Y = 5;
const MEAS_LABEL_RADIUS = 8;
const MEAS_LABEL_BORDER_PX = 1.8;
const MEAS_LABEL_LINE_CLEARANCE_PX = 4;
const _measurementLabelWorldPos = new THREE.Vector3();
const _measurementLabelRight = new THREE.Vector3();
const _measurementLabelUp = new THREE.Vector3();
const _measurementLabelCenter = new THREE.Vector3();
const _measurementLabelDelta = new THREE.Vector3();
const _measurementLeaderEnd = new THREE.Vector3();

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

function _prepareForIncomingModel() {
  transformControl.detach();
  _missingAnchorWarningKeys.clear();
  for (const selectedIdx of selectedMeshIndices) {
    if (selectedIdx >= 0 && selectedIdx < currentMeshes.length) {
      _highlightMesh(currentMeshes[selectedIdx], false);
    }
  }
  selectedMeshIndex = -1;
  requestedSelectedMeshIndex = -1;
  selectedMeshIndices = [];
  requestedSelectedMeshIndices = [];
  selectionProxy.visible = false;
  _clearMeasurements();
  _clearPickMarker();
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

function _disposeMeasurementNode(node) {
  if (!node) return;
  if (node.geometry) {
    node.geometry.dispose();
  }
  if (node.material) {
    if (Array.isArray(node.material)) {
      node.material.forEach((material) => {
        if (material?.map) material.map.dispose();
        if (material?.dispose) material.dispose();
      });
    } else {
      if (node.material.map) node.material.map.dispose();
      if (node.material.dispose) node.material.dispose();
    }
  }
  if (node.children && node.children.length) {
    const children = [...node.children];
    for (const child of children) {
      _disposeMeasurementNode(child);
      node.remove(child);
    }
  }
}

function _clearMeasurements() {
  const children = [...measurementGroup.children];
  for (const child of children) {
    _disposeMeasurementNode(child);
    measurementGroup.remove(child);
  }
  measurementGroup.visible = false;
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

  if (_lockedBaseRotation !== null) {
    currentGroup.rotation.set(
      _lockedBaseRotation.x,
      _lockedBaseRotation.y,
      _lockedBaseRotation.z
    );
  } else {
    orientObjectVertically(currentGroup);
  }
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

  _scheduleMeasurementsRender();
}

function _scheduleMeasurementsRender() {
  if (measurementRenderQueued) return;
  measurementRenderQueued = true;
  requestAnimationFrame(() => {
    measurementRenderQueued = false;
    _renderMeasurements();
  });
}

function _syncSelectedTransform() {
  if (selectedMeshIndices.length > 1) {
    const payload = selectedMeshIndices
      .filter((idx) => idx >= 0 && idx < currentMeshes.length && currentMeshes[idx])
      .map((idx) => {
        const mesh = currentMeshes[idx];
        partTransforms[idx] = {
          x: parseFloat(mesh.position.x.toFixed(4)),
          y: parseFloat(mesh.position.y.toFixed(4)),
          z: parseFloat(mesh.position.z.toFixed(4)),
          rx: parseFloat(THREE.MathUtils.radToDeg(mesh.rotation.x).toFixed(2)),
          ry: parseFloat(THREE.MathUtils.radToDeg(mesh.rotation.y).toFixed(2)),
          rz: parseFloat(THREE.MathUtils.radToDeg(mesh.rotation.z).toFixed(2)),
        };
        return { index: idx, transform: partTransforms[idx] };
      });
    emitPreviewEvent('TRANSFORM_BATCH', payload);
    return;
  }
  if (selectedMeshIndex < 0 || selectedMeshIndex >= currentMeshes.length) return;
  const mesh = currentMeshes[selectedMeshIndex];
  if (!mesh) return;
  partTransforms[selectedMeshIndex] = {
    x: parseFloat(mesh.position.x.toFixed(4)),
    y: parseFloat(mesh.position.y.toFixed(4)),
    z: parseFloat(mesh.position.z.toFixed(4)),
    rx: parseFloat(THREE.MathUtils.radToDeg(mesh.rotation.x).toFixed(2)),
    ry: parseFloat(THREE.MathUtils.radToDeg(mesh.rotation.y).toFixed(2)),
    rz: parseFloat(THREE.MathUtils.radToDeg(mesh.rotation.z).toFixed(2)),
  };
  emitPreviewEvent('TRANSFORM', {
    index: selectedMeshIndex,
    transform: partTransforms[selectedMeshIndex],
  });
}

function _highlightMesh(mesh, on) {
  if (!mesh || !mesh.material) return;
  if (on) {
    mesh.material._origEmissive = mesh.material.emissive.clone();
    mesh.material.emissive.setHex(0x444444);
  } else if (mesh.material._origEmissive) {
    mesh.material.emissive.copy(mesh.material._origEmissive);
    delete mesh.material._origEmissive;
  }
}

function _emitSelectionChanged() {
  emitPreviewEvent('PART_SELECTIONS', selectedMeshIndices.slice());
}

function _updateSelectionProxyFromSelection() {
  if (selectedMeshIndices.length === 0) {
    selectionProxy.visible = false;
    return;
  }

  if (selectedMeshIndices.length === 1) {
    const mesh = currentMeshes[selectedMeshIndices[0]];
    if (!mesh) {
      selectionProxy.visible = false;
      return;
    }
    // Keep gizmo at the visible part center in single selection so it stays
    // on the part in both translate and rotate modes.
    const box = new THREE.Box3().setFromObject(mesh);
    box.getCenter(selectionProxy.position);
    const parent = mesh.parent || scene;
    parent.getWorldQuaternion(selectionProxy.quaternion);
    selectionProxy.visible = true;
    return;
  }

  const center = new THREE.Vector3();
  const worldPos = new THREE.Vector3();
  let count = 0;
  for (const idx of selectedMeshIndices) {
    const mesh = currentMeshes[idx];
    if (!mesh) continue;
    mesh.getWorldPosition(worldPos);
    center.add(worldPos);
    count += 1;
  }
  if (count <= 0) {
    selectionProxy.visible = false;
    return;
  }

  center.multiplyScalar(1 / count);
  selectionProxy.position.copy(center);
  selectionProxy.quaternion.identity();
  selectionProxy.visible = true;
}

function _applySelectionProxyTransform() {
  const didApply = applySelectionProxyTransformDelta({
    mode: transformControl.getMode(),
    selectionProxy,
    selectionProxyDragState: _selectionProxyDragState,
    selectedMeshIndices,
    currentMeshes,
    scene,
    THREE,
  });
  if (!didApply) {
    return;
  }
  _syncSelectedTransform();
  _scheduleMeasurementsRender();
}

function _selectPartByIndex(idx) {
  for (const selectedIdx of selectedMeshIndices) {
    if (selectedIdx >= 0 && selectedIdx < currentMeshes.length) {
      _highlightMesh(currentMeshes[selectedIdx], false);
    }
  }
  if (idx < 0 || idx >= currentMeshes.length || !currentMeshes[idx]) {
    transformControl.detach();
    selectedMeshIndex = -1;
    selectedMeshIndices = [];
    selectionProxy.visible = false;
    _emitSelectionChanged();
    return;
  }
  selectedMeshIndex = idx;
  selectedMeshIndices = [idx];
  _highlightMesh(currentMeshes[idx], true);
  _updateSelectionProxyFromSelection();
  transformControl.attach(selectionProxy);
  transformControl.setSpace('local');
  _emitSelectionChanged();
}

function _setSelectedPartIndices(indices) {
  for (const selectedIdx of selectedMeshIndices) {
    if (selectedIdx >= 0 && selectedIdx < currentMeshes.length) {
      _highlightMesh(currentMeshes[selectedIdx], false);
    }
  }

  const normalized = Array.from(new Set((indices || [])
    .map((idx) => Number(idx))
    .filter((idx) => Number.isInteger(idx) && idx >= 0 && idx < currentMeshes.length && currentMeshes[idx])));

  selectedMeshIndices = normalized;
  selectedMeshIndex = normalized.length > 0 ? normalized[normalized.length - 1] : -1;

  for (const selectedIdx of selectedMeshIndices) {
    _highlightMesh(currentMeshes[selectedIdx], true);
  }

  if (selectedMeshIndices.length <= 0) {
    selectionProxy.visible = false;
    transformControl.detach();
  } else if (selectedMeshIndices.length === 1) {
    _updateSelectionProxyFromSelection();
    transformControl.attach(selectionProxy);
    transformControl.setSpace('local');
  } else {
    _updateSelectionProxyFromSelection();
    transformControl.attach(selectionProxy);
    transformControl.setSpace('world');
  }

  _emitSelectionChanged();
}

function _togglePartSelection(idx) {
  if (idx < 0 || idx >= currentMeshes.length || !currentMeshes[idx]) {
    return;
  }
  if (selectedMeshIndices.includes(idx)) {
    _setSelectedPartIndices(selectedMeshIndices.filter((value) => value !== idx));
    return;
  }
  _setSelectedPartIndices(selectedMeshIndices.concat([idx]));
}

function _normalizedPartTransform(transform) {
  return {
    x: Number(transform?.x) || 0,
    y: Number(transform?.y) || 0,
    z: Number(transform?.z) || 0,
    rx: Number(transform?.rx) || 0,
    ry: Number(transform?.ry) || 0,
    rz: Number(transform?.rz) || 0,
  };
}

function _restoreRequestedSelection() {
  if (!transformEditEnabled) {
    return;
  }
  if (requestedSelectedMeshIndices.length > 0) {
    _setSelectedPartIndices(requestedSelectedMeshIndices);
    return;
  }
  if (requestedSelectedMeshIndex < 0) {
    _setSelectedPartIndices([]);
    return;
  }
  if (requestedSelectedMeshIndex >= currentMeshes.length) {
    return;
  }
  if (!currentMeshes[requestedSelectedMeshIndex]) {
    return;
  }
  _selectPartByIndex(requestedSelectedMeshIndex);
}

function _findPartMeshByName(partName) {
  const target = String(partName || '').trim();
  if (!target) {
    return null;
  }

  const normalizePartKey = (value) => {
    let text = String(value || '').trim().toLowerCase();
    if (!text) {
      return '';
    }

    if (typeof text.normalize === 'function') {
      text = text.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }

    text = text
      .replace(/\(meshed\)/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/[^a-z0-9 ]+/g, '');

    return text;
  };
  const compactPartKey = (value) => normalizePartKey(value).replace(/[aeiouyÃ¥Ã¤Ã¶Ãµ]/g, '').replace(/\s+/g, '');

  const targetLower = target.toLowerCase();
  const exact = currentMeshes.find((mesh) => mesh && String(mesh._partName || '').trim().toLowerCase() === targetLower);
  if (exact) {
    return exact;
  }

  const targetKey = normalizePartKey(target);
  if (!targetKey) {
    return null;
  }

  const normalizedExact = currentMeshes.find((mesh) => {
    if (!mesh) {
      return false;
    }
    const meshKey = normalizePartKey(mesh._partName || '');
    return meshKey === targetKey;
  });
  if (normalizedExact) {
    return normalizedExact;
  }

  const targetCompact = compactPartKey(target);
  if (targetCompact) {
    const compactExact = currentMeshes.find((mesh) => {
      if (!mesh) {
        return false;
      }
      return compactPartKey(mesh._partName || '') === targetCompact;
    });
    if (compactExact) {
      return compactExact;
    }
  }

  return currentMeshes.find((mesh) => {
    if (!mesh) {
      return false;
    }
    const meshKey = normalizePartKey(mesh._partName || '');
    return meshKey && (meshKey.includes(targetKey) || targetKey.includes(meshKey));
  }) || null;
}

function _findPartMeshByIndex(partIndex) {
  if (partIndex === null || partIndex === undefined || partIndex === '') {
    return null;
  }
  const idx = Number(partIndex);
  if (!Number.isInteger(idx) || idx < 0 || idx >= currentMeshes.length) {
    return null;
  }
  return currentMeshes[idx] || null;
}

function _resolveAnchorPoint(partName, point, pointSpace = '', partIndex = null) {
  const targetName = String(partName || '').trim();
  // Use _parseOverlayVector so string coordinates like "10.5, 25.3, 0.0"
  // (as emitted by Python json.dumps) are correctly parsed.
  // Direct index access (point[0]) only works for arrays, not strings.
  const parsed = _parseOverlayVector(point);
  const coordPoint = parsed ? parsed.clone() : new THREE.Vector3(0, 0, 0);
  const normalizedSpace = String(pointSpace || '').trim().toLowerCase();
  const partIndexNum = Number(partIndex);
  const hasPartIndexRef = Number.isInteger(partIndexNum) && partIndexNum >= 0;

  if (!targetName && !hasPartIndexRef) {
    return coordPoint;
  }

  const mesh =
    _findPartMeshByIndex(hasPartIndexRef ? partIndexNum : null)
    || _findPartMeshByName(targetName);
  if (mesh) {
    if (normalizedSpace === 'world') {
      return coordPoint;
    }
    return mesh.localToWorld(coordPoint);
  }

  const warningKey = `${targetName || '<index>'}|${hasPartIndexRef ? partIndexNum : partIndex}|${normalizedSpace}`;
  if (window?.__previewDebugAnchorWarnings && !_missingAnchorWarningKeys.has(warningKey)) {
    _missingAnchorWarningKeys.add(warningKey);
    console.warn(
      `[viewer] Measurement anchor fallback: part not found (name="${targetName}", index=${hasPartIndexRef ? partIndexNum : partIndex}, space="${normalizedSpace || 'local'}")`
    );
  }

  if (currentGroup) {
    if (normalizedSpace === 'world') {
      return coordPoint;
    }
    return currentGroup.localToWorld(coordPoint);
  }

  return coordPoint;
}

function _resolveAxisDirection(partName, axis, partIndex = null) {
  const targetName = String(partName || '').trim();
  const parsedAxis = _parseOverlayVector(axis);
  const localAxis = parsedAxis ? parsedAxis.clone() : new THREE.Vector3(0, 0, 0);
  const localAxisFinite = Number.isFinite(localAxis.x) && Number.isFinite(localAxis.y) && Number.isFinite(localAxis.z);
  if (!localAxisFinite || localAxis.lengthSq() <= 1e-8) {
    localAxis.set(0, 1, 0);
  }
  localAxis.normalize();
  if (!Number.isFinite(localAxis.x) || !Number.isFinite(localAxis.y) || !Number.isFinite(localAxis.z)) {
    localAxis.set(0, 1, 0);
  }

  const mesh = _findPartMeshByIndex(partIndex) || _findPartMeshByName(targetName);
  if (mesh) {
    return localAxis.transformDirection(mesh.matrixWorld).normalize();
  }
  if (targetName) {
    return null;
  }
  if (currentGroup) {
    return localAxis.transformDirection(currentGroup.matrixWorld).normalize();
  }
  return localAxis;
}

function _traceRoundedRectPath(ctx, x, y, width, height, radius) {
  const r = Math.max(0, Math.min(radius, Math.min(width, height) * 0.5));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function _createMeasurementLabelTexture(text, colorHex = 0x00dd00) {
  const colorStr = '#' + colorHex.toString(16).padStart(6, '0').toUpperCase();
  const valueText = String(text || '').trim();
  if (!valueText) {
    return null;
  }

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return null;
  }

  const dpr = Math.max(window.devicePixelRatio || 1, 1);
  const fontPx = MEAS_LABEL_FONT_PX * dpr;
  ctx.font = `600 ${fontPx}px "Segoe UI", Arial, sans-serif`;
  const metrics = ctx.measureText(valueText);
  const textWidth = Math.ceil(metrics.width);
  const textHeight = Math.ceil(fontPx * 1.05);
  const padX = Math.round(MEAS_LABEL_PADDING_X * dpr);
  const padY = Math.round(MEAS_LABEL_PADDING_Y * dpr);
  const border = Math.max(1, Math.round(MEAS_LABEL_BORDER_PX * dpr));
  const width = Math.max(8, textWidth + (padX * 2));
  const height = Math.max(8, textHeight + (padY * 2));

  canvas.width = width;
  canvas.height = height;

  ctx.clearRect(0, 0, width, height);
  const radius = Math.round(MEAS_LABEL_RADIUS * dpr);
  _traceRoundedRectPath(ctx, border * 0.5, border * 0.5, width - border, height - border, radius);
  ctx.fillStyle = 'rgba(255, 255, 255, 0.985)';
  ctx.fill();
  ctx.strokeStyle = colorStr;
  ctx.lineWidth = border;
  ctx.stroke();

  ctx.font = `600 ${fontPx}px "Segoe UI", Arial, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#182533';
  ctx.fillText(valueText, width * 0.5, height * 0.5);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  texture.generateMipmaps = false;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;

  return {
    texture,
    aspect: width / Math.max(height, 1),
    cssHeight: height / dpr,
  };
}

function _boostMeasurementMaterial(material) {
  if (!material) {
    return;
  }
  material.toneMapped = false;
  if (material.transparent && typeof material.opacity === 'number') {
    material.opacity = Math.max(material.opacity, MEAS_OVERLAY_MIN_TRANSPARENT_OPACITY);
  }
  material.needsUpdate = true;
}

function _boostMeasurementOverlayVisuals(root) {
  if (!root || typeof root.traverse !== 'function') {
    return;
  }
  root.traverse((node) => {
    node.renderOrder = Math.max(Number(node.renderOrder) || 0, MEAS_OVERLAY_RENDER_ORDER);
    if (!node.material) {
      return;
    }
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    for (const material of materials) {
      _boostMeasurementMaterial(material);
    }
  });
}

function _updateMeasurementLabelScale(sprite) {
  if (!sprite?.userData?.measurementLabel) return;
  sprite.getWorldPosition(_measurementLabelWorldPos);
  const distance = Math.max(camera.position.distanceTo(_measurementLabelWorldPos), 0.001);
  const worldPerPixel =
    (2 * distance * Math.tan(THREE.MathUtils.degToRad(camera.fov) * 0.5))
    / Math.max(renderer.domElement.clientHeight, 1);
  const targetPx = THREE.MathUtils.clamp(
    Number(sprite.userData.cssHeight || MEAS_LABEL_TARGET_PX_HEIGHT),
    MEAS_LABEL_MIN_PX_HEIGHT,
    MEAS_LABEL_MAX_PX_HEIGHT
  );
  const worldHeight = targetPx * worldPerPixel;
  const aspect = Math.max(Number(sprite.userData.aspect || 1), 0.1);
  sprite.scale.set(worldHeight * aspect, worldHeight, 1);

  const midpoint = sprite.userData.distanceMidpoint;
  const lineDirection = sprite.userData.distanceDirection;
  if (midpoint instanceof THREE.Vector3 && lineDirection instanceof THREE.Vector3 && lineDirection.lengthSq() > 1e-8) {
    const sideDirection = _measurementOffsetDirection(lineDirection, midpoint);
    const clearancePx = Number(sprite.userData.lineClearancePx || MEAS_LABEL_LINE_CLEARANCE_PX);
    const clearanceWorld = (worldHeight * 0.5) + (Math.max(1, clearancePx) * worldPerPixel);
    sprite.position.copy(midpoint).add(sideDirection.multiplyScalar(clearanceWorld));
  }

  _updateMeasurementLabelLeader(sprite);
}

function _measurementLabelEdgePointToward(sprite, fromPoint, outPoint) {
  if (!sprite?.isSprite || !(fromPoint instanceof THREE.Vector3)) {
    return null;
  }
  const center = sprite.getWorldPosition(_measurementLabelCenter);
  const halfWidth = Math.max(Number(sprite.scale.x) * 0.5, 1e-6);
  const halfHeight = Math.max(Number(sprite.scale.y) * 0.5, 1e-6);

  _measurementLabelRight.set(1, 0, 0).applyQuaternion(camera.quaternion).normalize();
  _measurementLabelUp.set(0, 1, 0).applyQuaternion(camera.quaternion).normalize();
  _measurementLabelDelta.copy(fromPoint).sub(center);

  let localX = _measurementLabelDelta.dot(_measurementLabelRight);
  let localY = _measurementLabelDelta.dot(_measurementLabelUp);
  if (!Number.isFinite(localX) || !Number.isFinite(localY)) {
    return null;
  }
  if (Math.abs(localX) < 1e-8 && Math.abs(localY) < 1e-8) {
    localX = 1;
    localY = 0;
  }

  const edgeScale = 1 / Math.max(Math.abs(localX) / halfWidth, Math.abs(localY) / halfHeight, 1e-8);
  let edgeX = localX * edgeScale;
  let edgeY = localY * edgeScale;

  const dirLength = Math.hypot(localX, localY);
  if (dirLength > 1e-8) {
    const distance = Math.max(camera.position.distanceTo(center), 0.001);
    const worldPerPixel =
      (2 * distance * Math.tan(THREE.MathUtils.degToRad(camera.fov) * 0.5))
      / Math.max(renderer.domElement.clientHeight, 1);
    const outsideClearance = Math.max(1, MEAS_LABEL_BORDER_PX) * worldPerPixel;
    edgeX += (localX / dirLength) * outsideClearance;
    edgeY += (localY / dirLength) * outsideClearance;
  }

  const target = outPoint || new THREE.Vector3();
  target.copy(center);
  target.addScaledVector(_measurementLabelRight, edgeX);
  target.addScaledVector(_measurementLabelUp, edgeY);
  return target;
}

function _updateMeasurementLabelLeader(sprite) {
  const leaderLine = sprite?.userData?.leaderLine;
  const leaderAnchor = sprite?.userData?.leaderAnchor;
  if (!(leaderLine?.isLine) || !(leaderAnchor instanceof THREE.Vector3)) {
    return;
  }
  const leaderEnd = _measurementLabelEdgePointToward(sprite, leaderAnchor, _measurementLeaderEnd);
  if (!(leaderEnd instanceof THREE.Vector3)) {
    return;
  }
  const positions = leaderLine.geometry?.getAttribute('position');
  if (!positions || positions.count < 2) {
    return;
  }
  positions.setXYZ(0, leaderAnchor.x, leaderAnchor.y, leaderAnchor.z);
  positions.setXYZ(1, leaderEnd.x, leaderEnd.y, leaderEnd.z);
  positions.needsUpdate = true;
}

function _updateMeasurementLabelScales() {
  measurementGroup.traverse((node) => {
    if (node?.isSprite && node.userData?.measurementLabel) {
      _updateMeasurementLabelScale(node);
    }
  });
}

function _normalizeMeasurementFocusIndex(index) {
  const numeric = Number(index);
  if (!Number.isInteger(numeric)) {
    return -1;
  }
  if (numeric < 0 || numeric >= measurementOverlays.length) {
    return -1;
  }
  return numeric;
}

function _measurementColorForOverlay(overlay) {
  const overlayType = String(overlay?.type || 'distance').trim().toLowerCase();
  return measurementColors[overlayType] || measurementColors.distance;
}

function _measurementValueText(overlay, index) {
  const overlayType = String(overlay?.type || 'distance').trim().toLowerCase();
  if (overlayType === 'distance') {
    const measured = Number(overlay?.measured_value);
    if (Number.isFinite(measured)) {
      return `${measured.toFixed(3)} mm`;
    }
    return `${Number(index) + 1}`;
  }
  if (overlayType === 'diameter_ring') {
    const measured = Number(overlay?.measured_value);
    if (Number.isFinite(measured) && measured > 0) {
      return `${measured.toFixed(3)} mm`;
    }
    const diameter = Number(overlay?.diameter);
    return Number.isFinite(diameter) && diameter > 0 ? `${diameter.toFixed(3)} mm` : `${Number(index) + 1}`;
  }
  if (overlayType === 'radius') {
    const radius = Number(overlay?.radius);
    return Number.isFinite(radius) && radius > 0 ? `R ${radius.toFixed(3)} mm` : `${Number(index) + 1}`;
  }
  if (overlayType === 'angle') {
    const deg = Number(overlay?.measured_value);
    return Number.isFinite(deg) && deg >= 0 ? `${deg.toFixed(2)} deg` : `${Number(index) + 1}`;
  }
  return `${Number(index) + 1}`;
}

function _measurementChipText(overlay, index) {
  const name = String(overlay?.name || '').trim();
  const value = _measurementValueText(overlay, index);
  return name ? `${name}: ${value}` : value;
}

function _ensureMeasurementListContainer() {
  if (_measurementListContainer && _measurementListContainer.isConnected) {
    return _measurementListContainer;
  }
  const host = document.createElement('div');
  host.style.position = 'absolute';
  host.style.top = '10px';
  host.style.right = '12px';
  host.style.display = 'none';
  host.style.flexDirection = 'column';
  host.style.gap = '8px';
  host.style.alignItems = 'flex-end';
  host.style.pointerEvents = 'none';
  host.style.zIndex = '60';
  document.body.appendChild(host);
  _measurementListContainer = host;
  return host;
}

function _clearMeasurementListContainer() {
  if (!_measurementListContainer) return;
  _measurementListContainer.replaceChildren();
  _measurementListContainer.style.display = 'none';
  _measurementListSignature = '';
}

function _setMeasurementFocusIndex(index) {
  const nextIndex = _normalizeMeasurementFocusIndex(index);
  const currentlyFocused = _normalizeMeasurementFocusIndex(measurementFocusIndex);
  const shouldToggleOff = currentlyFocused >= 0 && nextIndex === currentlyFocused;

  measurementFocusIndex = shouldToggleOff ? -1 : nextIndex;
  _scheduleMeasurementsRender();
}

function _renderMeasurementList(items) {
  const host = _ensureMeasurementListContainer();
  if (!measurementsVisible || !Array.isArray(items) || items.length <= 0) {
    host.style.display = 'none';
    _measurementListSignature = '';
    return;
  }

  const focused = _normalizeMeasurementFocusIndex(measurementFocusIndex);
  const renderedItems = focused >= 0
    ? items.filter((item) => item.index === focused)
    : items;

  if (!renderedItems.length) {
    host.style.display = 'none';
    _measurementListSignature = '';
    return;
  }

  const signature = JSON.stringify({
    focused,
    items: renderedItems.map((item) => ({
      index: item.index,
      text: _measurementChipText(item.overlay, item.index),
      color: item.color,
    })),
  });
  if (_measurementListSignature === signature && host.childElementCount === renderedItems.length) {
    host.style.display = 'flex';
    return;
  }
  _measurementListSignature = signature;
  host.replaceChildren();

  for (const item of renderedItems) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = _measurementChipText(item.overlay, item.index);
    btn.title = focused >= 0
      ? 'Click again to show all measurements'
      : 'Click to isolate this measurement';
    btn.style.pointerEvents = 'auto';
    btn.style.cursor = 'pointer';
    btn.style.whiteSpace = 'nowrap';
    btn.style.background = 'rgba(255, 255, 255, 0.96)';
    btn.style.color = '#2f3a45';
    btn.style.border = `1px solid #${item.color.toString(16).padStart(6, '0')}`;
    btn.style.borderRadius = '9px';
    btn.style.padding = '9px 14px';
    btn.style.fontFamily = '"Segoe UI", Arial, sans-serif';
    btn.style.fontSize = '14px';
    btn.style.fontWeight = focused >= 0 ? '700' : '650';
    btn.style.boxShadow = focused >= 0
      ? '0 2px 8px rgba(0, 0, 0, 0.12)'
      : '0 1px 6px rgba(0, 0, 0, 0.10)';
    btn.style.transition = 'transform 90ms ease, box-shadow 120ms ease, opacity 120ms ease';
    btn.style.opacity = focused >= 0 ? '1' : '0.96';

    btn.addEventListener('mouseenter', () => {
      btn.style.transform = 'translateY(-1px)';
      btn.style.boxShadow = '0 3px 10px rgba(0, 0, 0, 0.16)';
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = 'translateY(0px)';
      btn.style.boxShadow = focused >= 0
        ? '0 2px 8px rgba(0, 0, 0, 0.12)'
        : '0 1px 6px rgba(0, 0, 0, 0.10)';
    });
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      _setMeasurementFocusIndex(item.index);
    });
    host.appendChild(btn);
  }

  host.style.display = 'flex';
}

function _makeMeasurementLabel(text, colorHex = 0x00dd00, anchorPoint = null, options = null) {
  if (!anchorPoint) {
    return null;
  }
  const labelTexture = _createMeasurementLabelTexture(text, colorHex);
  if (!labelTexture) {
    return null;
  }
  const material = new THREE.SpriteMaterial({
    map: labelTexture.texture,
    transparent: true,
    depthTest: true,
    depthWrite: false,
    sizeAttenuation: true,
  });
  const sprite = new THREE.Sprite(material);
  sprite.position.copy(anchorPoint);
  sprite.userData.measurementLabel = true;
  sprite.userData.aspect = labelTexture.aspect;
  sprite.userData.cssHeight = labelTexture.cssHeight;
  if (options && options.distanceMidpoint instanceof THREE.Vector3 && options.distanceDirection instanceof THREE.Vector3) {
    sprite.userData.distanceMidpoint = options.distanceMidpoint.clone();
    sprite.userData.distanceDirection = options.distanceDirection.clone().normalize();
    sprite.userData.lineClearancePx = Number(options.lineClearancePx || MEAS_LABEL_LINE_CLEARANCE_PX);
  }
  _updateMeasurementLabelScale(sprite);
  return sprite;
}

function _makeArrowCone(tip, direction, size, color) {
  const geometry = new THREE.ConeGeometry(size * 0.38, size * 1.08, 20);
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.96,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
    blending: THREE.NormalBlending,
  });
  const cone = new THREE.Mesh(geometry, material);
  cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize());
  cone.position.copy(tip).sub(direction.clone().normalize().multiplyScalar(size * 0.5));
  cone.renderOrder = 1000;
  return cone;
}

function _distanceBeamRadius(multiplier = 1.0) {
  const base = currentMaxDim * MEAS_DISTANCE_BEAM_BASE_RADIUS_FACTOR * Math.max(multiplier, 0);
  const minRadius = Math.max(currentMaxDim * 0.0008, MEAS_DISTANCE_BEAM_MIN_RADIUS);
  const maxRadius = Math.max(currentMaxDim * MEAS_DISTANCE_BEAM_MAX_RADIUS_FACTOR, minRadius);
  return THREE.MathUtils.clamp(base, minRadius, maxRadius);
}

function _makeMeasurementBeam(start, end, color, radius, opacity = 0.9) {
  if (!(start instanceof THREE.Vector3) || !(end instanceof THREE.Vector3)) {
    return null;
  }
  const segment = end.clone().sub(start);
  const length = segment.length();
  if (!Number.isFinite(length) || length <= 1e-6) {
    return null;
  }
  const beamRadius = Math.max(Number(radius) || 0, 1e-4);
  const geometry = new THREE.CylinderGeometry(beamRadius, beamRadius, length, 14, 1, true);
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: THREE.MathUtils.clamp(Number(opacity) || 0.9, 0.1, 1.0),
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
    blending: THREE.NormalBlending,
  });
  const beam = new THREE.Mesh(geometry, material);
  beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), segment.normalize());
  beam.position.copy(start).add(end).multiplyScalar(0.5);
  beam.renderOrder = 1000;
  return beam;
}

function _measurementOffsetDirection(direction, center) {
  const axis = direction.clone().normalize();
  const toCamera = camera.position.clone().sub(center);
  const projectedCamera = toCamera.clone().sub(axis.clone().multiplyScalar(toCamera.dot(axis)));
  if (projectedCamera.lengthSq() > 1e-8) {
    return projectedCamera.normalize();
  }

  const projectedUp = camera.up.clone().sub(axis.clone().multiplyScalar(camera.up.dot(axis)));
  if (projectedUp.lengthSq() > 1e-8) {
    return projectedUp.normalize();
  }

  const fallbacks = [
    new THREE.Vector3(1, 0, 0),
    new THREE.Vector3(0, 1, 0),
    new THREE.Vector3(0, 0, 1),
  ];
  for (const fallback of fallbacks) {
    const projected = fallback.clone().sub(axis.clone().multiplyScalar(fallback.dot(axis)));
    if (projected.lengthSq() > 1e-8) {
      return projected.normalize();
    }
  }

  return new THREE.Vector3(0, 1, 0);
}

function _distanceLabelValue(definition, measuredLength) {
  const mode = String(definition?.label_value_mode || 'measured').trim().toLowerCase();
  if (mode === 'custom') {
    const customValue = String(definition?.label_custom_value || '').trim();
    if (customValue) {
      return customValue;
    }
  }
  return `${measuredLength.toFixed(3)}`;
}

function _parseOverlayVector(value) {
  return parseOverlayVector(value);
}

function _formatVec3(value) {
  return formatVec3(value);
}

function _snapMm(value) {
  return Math.round(Number(value) || 0);
}

function _snapDegrees(value) {
  return Math.round(Number(value) || 0);
}

function _snapFineMm(value) {
  return Math.round((Number(value) || 0) * 10) / 10;
}

function _snapFineDegrees(value) {
  return Math.round((Number(value) || 0) * 10) / 10;
}

function _snapVec3Mm(value) {
  return new THREE.Vector3(_snapMm(value.x), _snapMm(value.y), _snapMm(value.z));
}

function _distanceDirectionForOverlay(definition) {
  const start = _resolveAnchorPoint(definition.start_part, definition.start_xyz, definition.start_space, definition.start_part_index);
  const end = _resolveAnchorPoint(definition.end_part, definition.end_xyz, definition.end_space, definition.end_part_index);
  if (!start || !end) {
    return null;
  }
  const span = end.clone().sub(start);
  if (span.lengthSq() <= 1e-10) {
    return null;
  }
  const axisName = String(definition.distance_axis || 'z').trim().toLowerCase();
  if (axisName === 'direct') {
    return span.clone().normalize();
  }
  const localAxis = axisName === 'x' ? [1, 0, 0] : (axisName === 'y' ? [0, 1, 0] : [0, 0, 1]);
  const axisDirection =
    _resolveAxisDirection(definition.start_part, localAxis, definition.start_part_index)
    || _resolveAxisDirection(definition.end_part, localAxis, definition.end_part_index)
    || _resolveAxisDirection('', localAxis);
  if (!axisDirection || axisDirection.lengthSq() <= 1e-10) {
    return span.clone().normalize();
  }
  const axialLength = span.dot(axisDirection);
  if (!Number.isFinite(axialLength) || Math.abs(axialLength) <= 1e-6) {
    return span.clone().normalize();
  }
  return axisDirection.clone().multiplyScalar(axialLength >= 0 ? 1 : -1).normalize();
}

function _normalizeDiameterAxisMode(rawMode, axisLocal) {
  const mode = String(rawMode || '').trim().toLowerCase();
  if (mode === 'x' || mode === 'y' || mode === 'z' || mode === 'direct') {
    return mode;
  }
  if (!axisLocal || axisLocal.lengthSq() <= 1e-10) {
    return 'z';
  }
  const unit = axisLocal.clone().normalize();
  const tol = 1e-3;
  if (Math.abs(Math.abs(unit.x) - 1.0) <= tol && Math.abs(unit.y) <= tol && Math.abs(unit.z) <= tol) {
    return 'x';
  }
  if (Math.abs(Math.abs(unit.y) - 1.0) <= tol && Math.abs(unit.x) <= tol && Math.abs(unit.z) <= tol) {
    return 'y';
  }
  if (Math.abs(Math.abs(unit.z) - 1.0) <= tol && Math.abs(unit.x) <= tol && Math.abs(unit.y) <= tol) {
    return 'z';
  }
  return 'direct';
}

function _diameterAxisInfoForOverlay(definition) {
  if (!definition) {
    return null;
  }
  const parsedAxis = _parseOverlayVector(definition.axis_xyz);
  const axisMode = _normalizeDiameterAxisMode(definition.diameter_axis_mode, parsedAxis);
  let axisLocal;
  if (axisMode === 'x') {
    axisLocal = new THREE.Vector3(1, 0, 0);
  } else if (axisMode === 'y') {
    axisLocal = new THREE.Vector3(0, 1, 0);
  } else if (axisMode === 'z') {
    axisLocal = new THREE.Vector3(0, 0, 1);
  } else if (parsedAxis && parsedAxis.lengthSq() > 1e-10) {
    axisLocal = parsedAxis.clone().normalize();
  } else {
    axisLocal = new THREE.Vector3(0, 0, 1);
  }
  if (!Number.isFinite(axisLocal.x) || !Number.isFinite(axisLocal.y) || !Number.isFinite(axisLocal.z)) {
    axisLocal = new THREE.Vector3(0, 0, 1);
  }

  const axisWorld = axisLocal.clone().normalize();
  if (
    !axisWorld
    || !Number.isFinite(axisWorld.x)
    || !Number.isFinite(axisWorld.y)
    || !Number.isFinite(axisWorld.z)
    || axisWorld.lengthSq() <= 1e-10
  ) {
    return null;
  }
  definition.diameter_axis_mode = axisMode;
  definition.axis_xyz = _formatVec3(axisLocal);
  return {
    axisMode,
    axisLocal: axisLocal.clone().normalize(),
    axisWorld: axisWorld.clone().normalize(),
  };
}

function _diameterAxisForOverlay(definition) {
  const info = _diameterAxisInfoForOverlay(definition);
  if (!info) {
    return null;
  }
  return info.axisWorld.clone();
}

function _distanceDragObjects() {
  const objects = [];
  measurementGroup.traverse((node) => {
    if (node?.userData?.dragKind) {
      objects.push(node);
    }
  });
  return objects;
}

const _measurementDragController = createMeasurementDragController({
  THREE,
  canvas,
  camera,
  raycaster: _measurementDragRaycaster,
  pointer: _measurementDragPointer,
  getMeasurementOverlays: () => measurementOverlays,
  getMeasurementDragObjects: _distanceDragObjects,
  distanceDirectionForOverlay: _distanceDirectionForOverlay,
  diameterAxisForOverlay: _diameterAxisForOverlay,
  parseOverlayVector: _parseOverlayVector,
  overlayVectorLocalToWorld: _overlayVectorLocalToWorld,
  overlayVectorWorldToLocal: _overlayVectorWorldToLocal,
  defaultDistanceOffsetForOverlay: _defaultDistanceOffsetForOverlay,
  defaultDiameterOffsetForOverlay: _defaultDiameterOffsetForOverlay,
  snapMm: _snapMm,
  snapVec3Mm: _snapVec3Mm,
  formatVec3: _formatVec3,
  emitMeasurementUpdated: _emitMeasurementUpdated,
  scheduleMeasurementsRender: _scheduleMeasurementsRender,
  isMeasurementsVisible: () => measurementsVisible,
  isMeasurementDragEnabled: () => measurementDragEnabled,
  setControlsEnabled: (enabled) => {
    controls.enabled = !!enabled;
  },
  setCanvasCursor: (cursor) => {
    canvas.style.cursor = cursor;
  },
});

function _defaultDistanceOffsetForOverlay(definition) {
  const start = _resolveAnchorPoint(definition.start_part, definition.start_xyz, definition.start_space, definition.start_part_index);
  const end = _resolveAnchorPoint(definition.end_part, definition.end_xyz, definition.end_space, definition.end_part_index);
  const direction = _distanceDirectionForOverlay(definition);
  if (!start || !end || !direction) {
    return new THREE.Vector3(0, 0, 0);
  }

  const startShift = Number(definition.start_shift) || 0;
  const endShift = Number(definition.end_shift) || 0;
  const shiftedStart = start.clone().add(direction.clone().multiplyScalar(startShift));
  const shiftedEnd = end.clone().add(direction.clone().multiplyScalar(endShift));
  const span = shiftedEnd.clone().sub(shiftedStart);
  const measuredLength = Math.max(span.length(), 1e-6);
  const midpoint = shiftedStart.clone().lerp(shiftedEnd, 0.5);
  const offsetDirection = _measurementOffsetDirection(direction, midpoint);
  const offsetDistance = THREE.MathUtils.clamp(
    measuredLength * 0.16,
    Math.max(currentMaxDim * 0.08, 8),
    Math.max(currentMaxDim * 0.22, 24)
  );
  return offsetDirection.multiplyScalar(offsetDistance);
}

function _normalizeDiameterVisualOffsetMm(definition) {
  const raw = Number(definition?.diameter_visual_offset_mm);
  const normalized = Number.isFinite(raw) ? raw : 1.0;
  if (definition && typeof definition === 'object') {
    definition.diameter_visual_offset_mm = Number(normalized.toFixed(6));
  }
  return normalized;
}

function _resolveDiameterGeometry(definition) {
  const centerValue = _parseOverlayVector(definition?.center_xyz);
  if (!centerValue) {
    return null;
  }

  const partName = definition?.part;
  const partIndex = definition?.part_index;
  const center = _resolveAnchorPoint(partName, definition.center_xyz, '', partIndex);
  const axisInfo = _diameterAxisInfoForOverlay(definition);
  if (!center || !axisInfo) {
    return null;
  }
  const axis = axisInfo.axisWorld;

  const rawMode = String(definition?.diameter_mode || '').trim().toLowerCase();
  const mode = rawMode === 'measured' ? 'measured' : 'manual';
  let resolvedDiameter = Number(definition?.diameter) || 0;
  const visualOffsetMm = _normalizeDiameterVisualOffsetMm(definition);
  let projectedEdgeDirection = null;
  const edgeValue = _parseOverlayVector(definition?.edge_xyz);
  if (edgeValue) {
    const edge = _resolveAnchorPoint(partName, definition.edge_xyz, '', partIndex);
    if (!edge) {
      if (mode === 'measured') {
        return null;
      }
    } else {
      const radialVector = edge.clone().sub(center);
      const axialComponent = axis.clone().multiplyScalar(radialVector.dot(axis));
      const projected = radialVector.clone().sub(axialComponent);
      const projectedLength = projected.length();
      if (Number.isFinite(projectedLength) && projectedLength > 1e-6) {
        projectedEdgeDirection = projected.clone().normalize();
        if (mode === 'measured') {
          resolvedDiameter = projectedLength * 2;
        }
      } else if (mode === 'measured') {
        return null;
      }
    }
  } else if (mode === 'measured') {
    return null;
  }

  if (!Number.isFinite(resolvedDiameter) || resolvedDiameter <= 0) {
    return null;
  }

  const renderDiameter = mode === 'manual'
    ? (resolvedDiameter + visualOffsetMm)
    : resolvedDiameter;
  if (!Number.isFinite(renderDiameter) || renderDiameter <= 0) {
    return null;
  }

  const radius = renderDiameter / 2;
  let tangent = projectedEdgeDirection ? projectedEdgeDirection.clone() : null;
  if (!tangent || tangent.lengthSq() <= 1e-8) {
    const reference = Math.abs(axis.dot(new THREE.Vector3(0, 1, 0))) > 0.9
      ? new THREE.Vector3(1, 0, 0)
      : new THREE.Vector3(0, 1, 0);
    tangent = new THREE.Vector3().crossVectors(axis, reference);
  }
  if (tangent.lengthSq() <= 1e-8) {
    return null;
  }
  tangent.normalize();
  const bitangent = new THREE.Vector3().crossVectors(axis, tangent);
  if (bitangent.lengthSq() <= 1e-8) {
    return null;
  }
  bitangent.normalize();

  return {
    center,
    axis,
    radius,
    resolvedDiameter,
    renderDiameter,
    visualOffsetMm,
    mode,
    tangent,
    bitangent,
  };
}

function _defaultDiameterOffsetForOverlay(definition) {
  const geometry = _resolveDiameterGeometry(definition);
  if (!geometry) {
    return new THREE.Vector3(0, 0, 0);
  }
  return _measurementOffsetDirection(geometry.axis, geometry.center)
    .multiplyScalar(Math.max(geometry.radius * 0.12, currentMaxDim * 0.02));
}

function _emitMeasurementUpdated(index) {
  if (!Number.isInteger(index) || index < 0 || index >= measurementOverlays.length) {
    return;
  }
  emitPreviewEvent('MEASUREMENT_UPDATED', {
    index,
    overlay: measurementOverlays[index],
  });
}

function _makeDistanceMeasurement(definition, measurmentIndex = 0) {
  const start = _resolveAnchorPoint(definition.start_part, definition.start_xyz, definition.start_space, definition.start_part_index);
  const end = _resolveAnchorPoint(definition.end_part, definition.end_xyz, definition.end_space, definition.end_part_index);
  if (!start || !end) {
    return null;
  }
  const span = end.clone().sub(start);
  const length = span.length();
  if (!Number.isFinite(length) || length <= 1e-6) {
    return null;
  }

  const axisName = String(definition.distance_axis || 'z').trim().toLowerCase();
  const baseColor = measurementColors.distance;
  const color = baseColor;
  const activePoint = String(definition.active_point || '').trim().toLowerCase();
  const parsedOffset = _parseOverlayVector(definition.offset_xyz);
  const offsetFromDefinition = parsedOffset ? _overlayVectorLocalToWorld(definition, parsedOffset) : null;
  const startShift = Number(definition.start_shift) || 0;
  const endShift = Number(definition.end_shift) || 0;

  const makeDragHandle = (position, dragKind) => {
    const isActivePoint = (
      (activePoint === 'start' && dragKind === 'distance-start')
      || (activePoint === 'end' && dragKind === 'distance-end')
    );
    const handleSize = Math.max(currentMaxDim * (isActivePoint ? 0.03 : 0.018), isActivePoint ? 3.2 : 1.8);
    const handleColor = isActivePoint ? 0xffd400 : color;
    const geometry = new THREE.SphereGeometry(handleSize, 12, 10);
    const material = new THREE.MeshBasicMaterial({ color: handleColor, depthTest: true, depthWrite: true });
    const handle = new THREE.Mesh(geometry, material);
    handle.position.copy(position);
    handle.visible = measurementDragEnabled;
    handle.userData = {
      dragKind,
      measurementIndex: measurmentIndex,
    };
    return handle;
  };
  
  if (axisName === 'direct') {
    const direction = span.clone().normalize();
    const shiftedStart = start.clone().add(direction.clone().multiplyScalar(startShift));
    const shiftedEnd = end.clone().add(direction.clone().multiplyScalar(endShift));
    const measuredLength = shiftedEnd.distanceTo(shiftedStart);

    const group = new THREE.Group();
    const headSize = THREE.MathUtils.clamp(measuredLength * 0.11, Math.max(currentMaxDim * 0.02, 2.2), Math.max(currentMaxDim * 0.12, 5.4));
    const midpoint = shiftedStart.clone().lerp(shiftedEnd, 0.5);
    const offsetDirection = _measurementOffsetDirection(direction, midpoint);
    const defaultOffsetDistance = THREE.MathUtils.clamp(
      measuredLength * 0.16,
      Math.max(currentMaxDim * 0.08, 8),
      Math.max(currentMaxDim * 0.22, 24)
    );
    const offsetVector = offsetFromDefinition || offsetDirection.clone().multiplyScalar(defaultOffsetDistance);
    const dimensionStart = shiftedStart.clone().add(offsetVector);
    const dimensionEnd = shiftedEnd.clone().add(offsetVector);

    const lineMaterial = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 1.0,
      depthTest: false,
      depthWrite: false,
      toneMapped: false,
      blending: THREE.NormalBlending,
    });
    const extensionMaterial = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.95,
      depthTest: false,
      depthWrite: false,
      toneMapped: false,
      blending: THREE.NormalBlending,
    });

    const startExtension = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([shiftedStart, dimensionStart]),
      extensionMaterial
    );
    group.add(startExtension);
    const startExtensionBeam = _makeMeasurementBeam(
      shiftedStart,
      dimensionStart,
      color,
      _distanceBeamRadius(0.8),
      0.78
    );
    if (startExtensionBeam) {
      group.add(startExtensionBeam);
    }

    const endExtension = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([shiftedEnd, dimensionEnd]),
      extensionMaterial.clone()
    );
    group.add(endExtension);
    const endExtensionBeam = _makeMeasurementBeam(
      shiftedEnd,
      dimensionEnd,
      color,
      _distanceBeamRadius(0.8),
      0.78
    );
    if (endExtensionBeam) {
      group.add(endExtensionBeam);
    }

    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([dimensionStart, dimensionEnd]),
      lineMaterial
    );
    line.userData = {
      dragKind: 'distance-offset',
      measurementIndex: measurmentIndex,
    };
    group.add(line);
    const mainBeam = _makeMeasurementBeam(
      dimensionStart,
      dimensionEnd,
      color,
      _distanceBeamRadius(1.0),
      0.92
    );
    if (mainBeam) {
      mainBeam.userData = {
        dragKind: 'distance-offset',
        measurementIndex: measurmentIndex,
      };
      group.add(mainBeam);
    }
    group.add(_makeArrowCone(dimensionStart, direction.clone().negate(), headSize, color));
    group.add(_makeArrowCone(dimensionEnd, direction, headSize, color));
    group.add(makeDragHandle(dimensionStart, 'distance-start'));
    group.add(makeDragHandle(dimensionEnd, 'distance-end'));

    definition.measured_value = Number(measuredLength.toFixed(6));
    const labelValue = _distanceLabelValue(definition, measuredLength);
    const labelAnchor = dimensionStart.clone().lerp(dimensionEnd, 0.5);
    const labelSprite = _makeMeasurementLabel(labelValue, color, labelAnchor, {
      distanceMidpoint: labelAnchor,
      distanceDirection: direction,
      lineClearancePx: 4,
    });
    if (labelSprite) {
      group.add(labelSprite);
    }
    return group;
  }

  const localAxis = axisName === 'x'
    ? [1, 0, 0]
    : (axisName === 'y' ? [0, 1, 0] : [0, 0, 1]);
  const axisDirection =
    _resolveAxisDirection(definition.start_part, localAxis, definition.start_part_index)
    || _resolveAxisDirection(definition.end_part, localAxis, definition.end_part_index)
    || _resolveAxisDirection('', localAxis);
  const axialLength = axisDirection ? span.dot(axisDirection) : 0;
  const hasAxialDirection = Number.isFinite(axialLength) && Math.abs(axialLength) > 1e-6;
  const direction = hasAxialDirection
    ? axisDirection.clone().multiplyScalar(axialLength >= 0 ? 1 : -1).normalize()
    : span.clone().normalize();
  const shiftedStart = start.clone().add(direction.clone().multiplyScalar(startShift));
  const shiftedEnd = end.clone().add(direction.clone().multiplyScalar(endShift));
  const shiftedSpan = shiftedEnd.clone().sub(shiftedStart);
  const measuredLength = hasAxialDirection ? Math.abs(shiftedSpan.dot(direction)) : shiftedSpan.length();

  const group = new THREE.Group();
  const headSize = THREE.MathUtils.clamp(measuredLength * 0.11, Math.max(currentMaxDim * 0.02, 2.2), Math.max(currentMaxDim * 0.12, 5.4));
  const midpoint = shiftedStart.clone().lerp(shiftedEnd, 0.5);
  const offsetDirection = _measurementOffsetDirection(direction, midpoint);
  const defaultOffsetDistance = THREE.MathUtils.clamp(
    measuredLength * 0.16,
    Math.max(currentMaxDim * 0.08, 8),
    Math.max(currentMaxDim * 0.22, 24)
  );
  const offsetVector = offsetFromDefinition || offsetDirection.clone().multiplyScalar(defaultOffsetDistance);
  const dimensionStart = shiftedStart.clone().add(offsetVector);
  const dimensionEnd = dimensionStart.clone().add(direction.clone().multiplyScalar(measuredLength));

  const lineMaterial = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 1.0,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
    blending: THREE.NormalBlending,
  });
  const extensionMaterial = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.95,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
    blending: THREE.NormalBlending,
  });

  const startExtension = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([shiftedStart, dimensionStart]),
    extensionMaterial
  );
  group.add(startExtension);
  const startExtensionBeam = _makeMeasurementBeam(
    shiftedStart,
    dimensionStart,
    color,
    _distanceBeamRadius(0.8),
    0.78
  );
  if (startExtensionBeam) {
    group.add(startExtensionBeam);
  }

  const endExtension = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([shiftedEnd, dimensionEnd]),
    extensionMaterial.clone()
  );
  group.add(endExtension);
  const endExtensionBeam = _makeMeasurementBeam(
    shiftedEnd,
    dimensionEnd,
    color,
    _distanceBeamRadius(0.8),
    0.78
  );
  if (endExtensionBeam) {
    group.add(endExtensionBeam);
  }

  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([dimensionStart, dimensionEnd]),
    lineMaterial
  );
  line.userData = {
    dragKind: 'distance-offset',
    measurementIndex: measurmentIndex,
  };
  group.add(line);
  const mainBeam = _makeMeasurementBeam(
    dimensionStart,
    dimensionEnd,
    color,
    _distanceBeamRadius(1.0),
    0.92
  );
  if (mainBeam) {
    mainBeam.userData = {
      dragKind: 'distance-offset',
      measurementIndex: measurmentIndex,
    };
    group.add(mainBeam);
  }
  group.add(_makeArrowCone(dimensionStart, direction.clone().negate(), headSize, color));
  group.add(_makeArrowCone(dimensionEnd, direction, headSize, color));
  group.add(makeDragHandle(dimensionStart, 'distance-start'));
  group.add(makeDragHandle(dimensionEnd, 'distance-end'));

  definition.measured_value = Number(measuredLength.toFixed(6));
  const labelValue = _distanceLabelValue(definition, measuredLength);
  const labelAnchor = dimensionStart.clone().lerp(dimensionEnd, 0.5);
  const labelSprite = _makeMeasurementLabel(labelValue, color, labelAnchor, {
    distanceMidpoint: labelAnchor,
    distanceDirection: direction,
    lineClearancePx: 4,
  });
  if (labelSprite) {
    group.add(labelSprite);
  }
  return group;
}

function _makeDiameterRing(definition, options = {}, measurementIndex = 0) {
  const includeLabel = options.includeLabel !== false;
  const geometry = _resolveDiameterGeometry(definition);
  if (!geometry) {
    return null;
  }
  const {
    center,
    axis,
    radius,
    resolvedDiameter,
    mode,
    tangent,
    bitangent,
  } = geometry;
  const group = new THREE.Group();
  const baseColor = measurementColors.diameter_ring;
  const color = baseColor;

  const ringPoints = [];
  for (let i = 0; i <= 64; i += 1) {
    const angle = (i / 64) * Math.PI * 2;
    const point = center.clone()
        .add(tangent.clone().multiplyScalar(Math.cos(angle) * radius))
        .add(bitangent.clone().multiplyScalar(Math.sin(angle) * radius));
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || !Number.isFinite(point.z)) {
      return null;
    }
    ringPoints.push(point);
  }

  const ringGeometry = new THREE.BufferGeometry().setFromPoints(ringPoints);
  const ringMaterial = new THREE.LineBasicMaterial({
    color,
    depthTest: true,
    depthWrite: true,
  });
  const ring = new THREE.Line(ringGeometry, ringMaterial);
  ring.userData = {
    dragKind: 'diameter-axis-position',
    measurementIndex,
  };
  group.add(ring);
  if (mode === 'measured') {
    definition.diameter = Number(resolvedDiameter.toFixed(6));
  }
  definition.measured_value = Number(resolvedDiameter.toFixed(6));

  if (includeLabel) {
    const defaultAnchor = center.clone().add(tangent.clone().multiplyScalar(radius));
    const parsedLabelOffset = _parseOverlayVector(definition.offset_xyz);
    const labelOffset =
      (parsedLabelOffset ? _overlayVectorLocalToWorld(definition, parsedLabelOffset) : null)
      || _defaultDiameterOffsetForOverlay(definition);
    const labelAnchor = defaultAnchor.clone().add(labelOffset);
    let ringAnchor = defaultAnchor.clone();
    const radialToLabel = labelAnchor.clone().sub(center);
    const axial = axis.clone().multiplyScalar(radialToLabel.dot(axis));
    const radialProjected = radialToLabel.clone().sub(axial);
    if (radialProjected.lengthSq() > 1e-8) {
      radialProjected.normalize().multiplyScalar(radius);
      ringAnchor = center.clone().add(radialProjected);
    }
    const labelSprite = _makeMeasurementLabel(`${resolvedDiameter.toFixed(3)}`, color, labelAnchor);
    if (labelSprite) {
      labelSprite.userData = {
        ...(labelSprite.userData || {}),
        dragKind: 'diameter-offset',
        measurementIndex,
      };
      if (labelOffset.lengthSq() > 1e-8) {
        const leaderLine = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints([ringAnchor, labelAnchor]),
          new THREE.LineBasicMaterial({
            color,
            transparent: true,
            opacity: 0.9,
            depthTest: true,
            depthWrite: true,
          })
        );
        leaderLine.frustumCulled = false;
        leaderLine.userData = {
          dragKind: 'diameter-offset',
          measurementIndex,
        };
        group.add(leaderLine);
        labelSprite.userData.leaderLine = leaderLine;
        labelSprite.userData.leaderAnchor = ringAnchor.clone();
        _updateMeasurementLabelLeader(labelSprite);
      }
      group.add(labelSprite);
    }
  }
  return group;
}

function _makeRadiusMeasurement(definition) {
  const radius = Number(definition.radius) || 0;
  if (!Number.isFinite(radius) || radius <= 0) {
    return null;
  }
  const center = _resolveAnchorPoint(definition.part, definition.center_xyz);
  const axis = _resolveAxisDirection(definition.part, definition.axis_xyz);
  if (!center || !axis) {
    return null;
  }

  const group = new THREE.Group();
  const color = measurementColors.radius;
  definition.measured_value = Number(radius.toFixed(6));
  const radial = _measurementOffsetDirection(axis, center).normalize();
  const edge = center.clone().add(radial.clone().multiplyScalar(radius));

  const lineMaterial = new THREE.LineBasicMaterial({ color, depthTest: true, depthWrite: true });
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([center, edge]),
    lineMaterial
  );
  group.add(line);
  group.add(_makeArrowCone(edge, radial, Math.max(radius * 0.15, currentMaxDim * 0.02), color));

  const ringDef = {
    part: definition.part,
    center_xyz: definition.center_xyz,
    axis_xyz: definition.axis_xyz,
    diameter: radius * 2,
    name: definition.name,
  };
  const ring = _makeDiameterRing(ringDef, { includeLabel: false });
  if (ring) {
    ring.children.forEach((child) => {
      if (!(child instanceof THREE.Sprite) && !(child.style)) {
        group.add(child);
      }
    });
  }

  const labelAnchor = center.clone()
    .lerp(edge, 0.66)
    .add(radial.clone().multiplyScalar(Math.max(currentMaxDim * 0.014, 1.4)));
  const labelSprite = _makeMeasurementLabel(`R ${radius.toFixed(3)}`, color, labelAnchor);
  if (labelSprite) {
    group.add(labelSprite);
  }
  return group;
}

function _makeAngleMeasurement(definition) {
  const center = _resolveAnchorPoint(definition.part, definition.center_xyz);
  const start = _resolveAnchorPoint(definition.part, definition.start_xyz);
  const end = _resolveAnchorPoint(definition.part, definition.end_xyz);
  if (!center || !start || !end) {
    return null;
  }

  const v1 = start.clone().sub(center);
  const v2 = end.clone().sub(center);
  const len1 = v1.length();
  const len2 = v2.length();
  if (len1 <= 1e-6 || len2 <= 1e-6) {
    return null;
  }
  const d1 = v1.clone().normalize();
  const d2 = v2.clone().normalize();
  const dot = THREE.MathUtils.clamp(d1.dot(d2), -1, 1);
  const angleRad = Math.acos(dot);
  const angleDeg = THREE.MathUtils.radToDeg(angleRad);
  definition.measured_value = Number(angleDeg.toFixed(6));

  const normal = new THREE.Vector3().crossVectors(d1, d2);
  if (normal.lengthSq() <= 1e-8) {
    return null;
  }
  normal.normalize();
  const tangent = new THREE.Vector3().crossVectors(normal, d1).normalize();

  const group = new THREE.Group();
  const color = measurementColors.angle;
  const rayLen = Math.max(Math.min(len1, len2), currentMaxDim * 0.15);
  const rayMaterial = new THREE.LineBasicMaterial({ color, depthTest: true, depthWrite: true });
  group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([center, center.clone().add(d1.clone().multiplyScalar(rayLen))]), rayMaterial));
  group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([center, center.clone().add(d2.clone().multiplyScalar(rayLen))]), rayMaterial.clone()));

  const arcRadius = rayLen * 0.45;
  const arcPoints = [];
  const segments = 48;
  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments;
    const a = angleRad * t;
    const p = center.clone()
      .add(d1.clone().multiplyScalar(Math.cos(a) * arcRadius))
      .add(tangent.clone().multiplyScalar(Math.sin(a) * arcRadius));
    arcPoints.push(p);
  }
  const arc = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(arcPoints),
    new THREE.LineBasicMaterial({ color, depthTest: true, depthWrite: true })
  );
  group.add(arc);

  const bisector = d1.clone()
    .multiplyScalar(Math.cos(angleRad * 0.5))
    .add(tangent.clone().multiplyScalar(Math.sin(angleRad * 0.5)));
  if (bisector.lengthSq() > 1e-8) {
    bisector.normalize();
  } else {
    bisector.copy(_measurementOffsetDirection(normal, center));
  }
  const labelAnchor = center.clone().add(bisector.multiplyScalar(arcRadius * 1.1));
  const labelSprite = _makeMeasurementLabel(`${angleDeg.toFixed(2)} deg`, color, labelAnchor);
  if (labelSprite) {
    group.add(labelSprite);
  }
  return group;
}

const _measurementFactories = createMeasurementFactories({
  makeDistanceMeasurement: _makeDistanceMeasurement,
  makeDiameterRing: _makeDiameterRing,
  makeRadiusMeasurement: _makeRadiusMeasurement,
  makeAngleMeasurement: _makeAngleMeasurement,
});

function _renderMeasurements() {
  _clearMeasurements();
  if (!measurementsVisible || !currentGroup || measurementOverlays.length === 0) {
    measurementGroup.visible = false;
    _clearMeasurementListContainer();
    return;
  }

  const focusedIndex = _normalizeMeasurementFocusIndex(measurementFocusIndex);
  if (measurementFocusIndex !== focusedIndex) {
    measurementFocusIndex = focusedIndex;
  }

  const measurementListItems = [];

  for (let overlayIndex = 0; overlayIndex < measurementOverlays.length; overlayIndex += 1) {
    const overlay = measurementOverlays[overlayIndex];
    if (!overlay || (measurementFilter && String(overlay.name || '') !== measurementFilter)) {
      continue;
    }
    if (focusedIndex >= 0 && overlayIndex !== focusedIndex) {
      continue;
    }
    const overlayType = String(overlay.type || 'distance').trim().toLowerCase();
    const factory = _measurementFactories[overlayType] || _measurementFactories.distance;
    const node = factory(overlay, overlayIndex);
    if (node) {
      node.userData = node.userData || {};
      node.userData.measurementIndex = overlayIndex;
      _boostMeasurementOverlayVisuals(node);
      measurementGroup.add(node);
      measurementListItems.push({
        index: overlayIndex,
        overlay,
        color: _measurementColorForOverlay(overlay),
      });
    }
  }

  measurementGroup.visible = measurementGroup.children.length > 0;
  _renderMeasurementList(measurementListItems);
}

function _clearPickMarker() {
  if (_pickMarker) {
    scene.remove(_pickMarker);
    if (_pickMarker.geometry) _pickMarker.geometry.dispose();
    if (_pickMarker.material) _pickMarker.material.dispose();
    _pickMarker = null;
  }
}

function _placePickMarker(position) {
  _clearPickMarker();
  const markerSize = Math.max(currentMaxDim * 0.012, 1.5);
  const geo = new THREE.SphereGeometry(markerSize, 12, 8);
  const mat = new THREE.MeshBasicMaterial({ color: 0x00ff00, depthTest: false });
  _pickMarker = new THREE.Mesh(geo, mat);
  _pickMarker.renderOrder = 2000;
  _pickMarker.position.copy(position);
  scene.add(_pickMarker);
}

function clearCurrentMeshes() {
  transformControl.detach();
  _missingAnchorWarningKeys.clear();
  for (const selectedIdx of selectedMeshIndices) {
    if (selectedIdx >= 0 && selectedIdx < currentMeshes.length) {
      _highlightMesh(currentMeshes[selectedIdx], false);
    }
  }
  selectedMeshIndex = -1;
  requestedSelectedMeshIndex = -1;
  selectedMeshIndices = [];
  requestedSelectedMeshIndices = [];
  selectionProxy.visible = false;
  partTransforms = [];
  _clearMeasurements();
  _clearPickMarker();

  for (const mesh of currentMeshes) {
    if (!mesh) continue;
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
  _lockedBaseRotation = null;
  clearCurrentMeshes();
  _markShadowMapDirty();
  hideStatus();
};

window.setWheelZoomEnabled = function (enabled) {
  wheelZoomEnabled = !!enabled;
};

window.setControlHintText = function (text) {
  _setControlHintText(text);
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
  _prepareForIncomingModel();

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
      mesh._partName = label || 'Model';
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
  const nextMeshes = new Array(parts.length).fill(null);
  partTransforms = parts.map((p) => ({
    x: p.offset_x || 0, y: p.offset_y || 0, z: p.offset_z || 0,
    rx: p.rot_x || 0, ry: p.rot_y || 0, rz: p.rot_z || 0,
  }));
  const loadEntries = parts
    .map((part, index) => ({
      part,
      index,
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

    _prepareForIncomingModel();
    scene.add(nextGroup);

    _transitionToGroup(
      nextGroup,
      nextMeshes,
      { refit: true, readyKind: 'assembly', requestId: normalizedRequestId },
    );
    _restoreRequestedSelection();
    hideStatus();
  };

  loadEntries.forEach(({ part, index, file, color }) => {
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
        mesh._partIndex = index;
        mesh._partName = part?.name || `Part ${index + 1}`;

        const t = _normalizedPartTransform(partTransforms[index]);
        mesh.position.set(t.x, t.y, t.z);
        mesh.rotation.set(
          THREE.MathUtils.degToRad(t.rx),
          THREE.MathUtils.degToRad(t.ry),
          THREE.MathUtils.degToRad(t.rz)
        );
        nextMeshes[index] = mesh;
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

canvas.addEventListener('click', (event) => {
  if (_gizmoDragJustEnded) return;
  if (_cameraDragJustEnded) return;
  if (_measurementDragController.didJustEnd()) return;
  if (currentMeshes.length === 0) return;

  const rect = canvas.getBoundingClientRect();
  _tcPointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  _tcPointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

  _tcRaycaster.setFromCamera(_tcPointer, camera);
  const meshes = currentMeshes.filter((m) => m != null);
  const intersects = _tcRaycaster.intersectObjects(meshes, false);

  if (pointPickingEnabled) {
    if (intersects.length > 0) {
      const hit = intersects[0];
      const mesh = hit.object;
      const worldPos = hit.point.clone();
      const localPos = mesh.worldToLocal(hit.point.clone());
      const idx = mesh._partIndex != null ? mesh._partIndex : currentMeshes.indexOf(mesh);
      _placePickMarker(worldPos);
      emitPreviewEvent('POINT_PICKED', {
        partIndex: idx,
        partName: mesh._partName || '',
        x: parseFloat(_snapMm(worldPos.x).toFixed(4)),
        y: parseFloat(_snapMm(worldPos.y).toFixed(4)),
        z: parseFloat(_snapMm(worldPos.z).toFixed(4)),
        local_x: parseFloat(localPos.x.toFixed(4)),
        local_y: parseFloat(localPos.y.toFixed(4)),
        local_z: parseFloat(localPos.z.toFixed(4)),
      });
    }
    return;
  }

  if (!transformEditEnabled) return;

  if (intersects.length > 0) {
    const hit = intersects[0].object;
    const idx = hit._partIndex != null ? hit._partIndex : currentMeshes.indexOf(hit);
    if (event.ctrlKey || event.metaKey) {
      _togglePartSelection(idx);
    } else {
      _selectPartByIndex(idx);
    }
  } else {
    _setSelectedPartIndices([]);
  }
});

canvas.addEventListener('mousedown', (event) => {
  if (event.button === 0 || event.button === 2) {
    _cameraPointerDown = { x: event.clientX, y: event.clientY };
    _cameraPointerMoved = false;
  }
  _measurementDragController.onMouseDown(event);
});

canvas.addEventListener('mousemove', (event) => {
  if (_cameraPointerDown && !_cameraPointerMoved) {
    const dx = event.clientX - _cameraPointerDown.x;
    const dy = event.clientY - _cameraPointerDown.y;
    if ((dx * dx + dy * dy) >= (_CAMERA_DRAG_THRESHOLD_PX * _CAMERA_DRAG_THRESHOLD_PX)) {
      _cameraPointerMoved = true;
    }
  }
  _measurementDragController.onMouseMove(event);
});

document.addEventListener('mouseup', () => {
  if (_cameraPointerDown) {
    if (_cameraPointerMoved) {
      _markCameraDragJustEnded();
    }
    _cameraPointerDown = null;
    _cameraPointerMoved = false;
  }
  _measurementDragController.onMouseUp();
});

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

// Measurement labels are depth-tested 3D sprites attached to their helpers.

window.setPointPickingEnabled = function (enabled) {
  pointPickingEnabled = !!enabled;
  if (!pointPickingEnabled) {
    _clearPickMarker();
  }
};

window.setTransformEditEnabled = function (enabled) {
  transformEditEnabled = !!enabled;
  if (!transformEditEnabled) {
    requestedSelectedMeshIndex = -1;
    requestedSelectedMeshIndices = [];
    _setSelectedPartIndices([]);
    return;
  }
  _restoreRequestedSelection();
};

window.setTransformMode = function (mode) {
  if (mode === 'translate' || mode === 'rotate') {
    transformControl.setMode(mode);
    if (transformControl.object === selectionProxy) {
      if (selectedMeshIndices.length <= 1) {
        _updateSelectionProxyFromSelection();
      }
      transformControl.setSpace(selectedMeshIndices.length > 1 ? 'world' : 'local');
    } else {
      transformControl.setSpace('local');
    }
  }
};

window.setFineTransformEnabled = function (enabled) {
  fineTransformSnapEnabled = !!enabled;
  _updateTransformSnap();
};

window.getPartTransforms = function () {
  return JSON.parse(JSON.stringify(partTransforms));
};

window.getBaseRotation = function () {
  if (!currentGroup) return {x: 0, y: 0, z: 0};
  return {
    x: currentGroup.rotation.x,
    y: currentGroup.rotation.y,
    z: currentGroup.rotation.z,
  };
};

window.setBaseRotation = function (rx, ry, rz) {
  _lockedBaseRotation = {x: rx || 0, y: ry || 0, z: rz || 0};
  if (currentGroup) {
    applyModelTransformAndFrame(false);
  }
};

window.clearBaseRotation = function () {
  _lockedBaseRotation = null;
  if (currentGroup) {
    applyModelTransformAndFrame(false);
  }
};

window.setPartTransforms = function (transforms) {
  if (!Array.isArray(transforms)) return;
  for (let i = 0; i < currentMeshes.length && i < transforms.length; i++) {
    const t = _normalizedPartTransform(transforms[i]);
    partTransforms[i] = t;
    const mesh = currentMeshes[i];
    if (!mesh) continue;
    mesh.position.set(t.x || 0, t.y || 0, t.z || 0);
    mesh.rotation.set(
      THREE.MathUtils.degToRad(t.rx || 0),
      THREE.MathUtils.degToRad(t.ry || 0),
      THREE.MathUtils.degToRad(t.rz || 0)
    );
  }
  _markShadowMapDirty();
  if (selectedMeshIndices.length > 0) {
    _updateSelectionProxyFromSelection();
    if (transformControl.object === selectionProxy) {
      _selectionProxyDragState = {
        position: selectionProxy.position.clone(),
        quaternion: selectionProxy.quaternion.clone(),
      };
    }
    _syncSelectedTransform();
  } else if (selectedMeshIndex >= 0) {
    _syncSelectedTransform();
  }
  _scheduleMeasurementsRender();
};

window.setPartColors = function (colors) {
  if (!Array.isArray(colors)) return;
  for (let i = 0; i < currentMeshes.length && i < colors.length; i++) {
    const mesh = currentMeshes[i];
    if (!mesh || !mesh.material || !mesh.material.color) continue;
    const colorValue = colors[i] || '#9ea7b3';
    applyMaterialFinish(mesh.material, colorValue);
  }
};

window.setPartNames = function (names) {
  if (!Array.isArray(names)) return;
  for (let i = 0; i < currentMeshes.length && i < names.length; i++) {
    const mesh = currentMeshes[i];
    if (!mesh) continue;
    mesh._partName = String(names[i] || mesh._partName || `Part ${i + 1}`);
  }
  _scheduleMeasurementsRender();
};

window.selectPart = function (index) {
  requestedSelectedMeshIndex = typeof index === 'number' ? index : -1;
  requestedSelectedMeshIndices = requestedSelectedMeshIndex >= 0 ? [requestedSelectedMeshIndex] : [];
  if (!transformEditEnabled) return;
  _restoreRequestedSelection();
};

window.selectParts = function (indices) {
  requestedSelectedMeshIndices = Array.isArray(indices)
    ? indices.map((idx) => Number(idx)).filter((idx) => Number.isInteger(idx) && idx >= 0)
    : [];
  requestedSelectedMeshIndex = requestedSelectedMeshIndices.length > 0
    ? requestedSelectedMeshIndices[requestedSelectedMeshIndices.length - 1]
    : -1;
  if (!transformEditEnabled) return;
  _restoreRequestedSelection();
};

window.resetSelectedPartTransform = function () {
  if (selectedMeshIndices.length <= 0) return;
  for (const idx of selectedMeshIndices) {
    if (idx < 0 || idx >= currentMeshes.length) continue;
    const mesh = currentMeshes[idx];
    if (!mesh) continue;
    mesh.position.set(0, 0, 0);
    mesh.rotation.set(0, 0, 0);
    partTransforms[idx] = { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 };
  }
  if (selectedMeshIndices.length > 0) {
    _updateSelectionProxyFromSelection();
    if (transformControl.object === selectionProxy) {
      transformControl.attach(selectionProxy);
    }
  }
  _syncSelectedTransform();
  _scheduleMeasurementsRender();
};

window.setMeasurements = function (definitions) {
  measurementOverlays = Array.isArray(definitions) ? definitions : [];
  measurementFocusIndex = -1;
  _scheduleMeasurementsRender();
};

window.setMeasurementsVisible = function (visible) {
  measurementsVisible = !!visible;
  if (!measurementsVisible) {
    measurementFocusIndex = -1;
  }
  _scheduleMeasurementsRender();
};

window.setMeasurementVisibilityOverride = function (forceHidden) {
  if (forceHidden) {
    measurementGroup.visible = false;
  }
};

window.setMeasurementDragEnabled = function (enabled) {
  measurementDragEnabled = !!enabled;
  _scheduleMeasurementsRender();
};

window.setMeasurementFilter = function (name) {
  measurementFilter = String(name || '').trim();
  _scheduleMeasurementsRender();
};

window.setMeasurementFocusIndex = function (index) {
  _setMeasurementFocusIndex(index);
};

window.getDistanceMeasuredValue = function (index) {
  const idx = Number(index);
  if (!Number.isInteger(idx) || idx < 0 || idx >= measurementOverlays.length) {
    return null;
  }
  const overlay = measurementOverlays[idx];
  if (!overlay || String(overlay.type || '').toLowerCase() !== 'distance') {
    return null;
  }
  const measured = Number(overlay.measured_value);
  return Number.isFinite(measured) ? measured : null;
};

window.getMeasurementResolvedValue = function (index) {
  const idx = Number(index);
  if (!Number.isInteger(idx) || idx < 0 || idx >= measurementOverlays.length) {
    return null;
  }
  const overlay = measurementOverlays[idx];
  if (!overlay) {
    return null;
  }
  const measured = Number(overlay.measured_value);
  return Number.isFinite(measured) ? measured : null;
};

window.getMeasurementsSnapshot = function () {
  try {
    return JSON.parse(JSON.stringify(measurementOverlays || []));
  } catch (_err) {
    return null;
  }
};

window.setRenderingEnabled = function (enabled) {
  renderingEnabled = !!enabled;
  if (renderingEnabled) {
    _markShadowMapDirty();
    renderer.render(scene, camera);
  }
};

window.setAxisOrbitVisible = function (enabled) {
  _setAxisOrbitVisible(enabled);
};

window.getPreviewBridgeStats = function () {
  return getPreviewBridgeStats();
};

function animate() {
  requestAnimationFrame(animate);
  if (!renderingEnabled) {
    return;
  }
  controls.update();
  _updateMeasurementLabelScales();
  if (axisOrbitVisible) {
    _drawAxisOrbit();
  }
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
  if (axisOrbitVisible) {
    _drawAxisOrbit();
  }
});

showStatus('Viewer ready.');
hideStatus();
