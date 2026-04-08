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
const _axisOrbitAxes = [
  { key: 'X', color: '#d64545', world: new THREE.Vector3(1, 0, 0), camera: new THREE.Vector3() },
  { key: 'Y', color: '#29a34a', world: new THREE.Vector3(0, 1, 0), camera: new THREE.Vector3() },
  { key: 'Z', color: '#2f66d2', world: new THREE.Vector3(0, 0, 1), camera: new THREE.Vector3() },
];

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
  const radius = Math.min(w, h) * 0.28;

  axisOrbitCtx.clearRect(0, 0, w, h);

  _axisOrbitInvQuat.copy(camera.quaternion).invert();
  for (const axis of _axisOrbitAxes) {
    axis.camera.copy(axis.world).applyQuaternion(_axisOrbitInvQuat).normalize();
  }

  // Draw back-facing axes first so front-facing axes stay readable.
  const sortedAxes = [..._axisOrbitAxes].sort((a, b) => b.camera.z - a.camera.z);
  const fontPx = Math.max(9, Math.round(10 * dpr));
  axisOrbitCtx.font = `700 ${fontPx}px "Segoe UI", Arial, sans-serif`;
  axisOrbitCtx.textAlign = 'center';
  axisOrbitCtx.textBaseline = 'middle';

  for (const axis of sortedAxes) {
    const sx = axis.camera.x;
    const sy = -axis.camera.y;
    const ex = cx + sx * radius;
    const ey = cy + sy * radius;
    const towardViewer = axis.camera.z < 0;
    const alpha = towardViewer ? 1.0 : 0.58;
    const lineWidth = towardViewer ? 2.15 * dpr : 1.5 * dpr;
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
    const nx = -uy;
    const ny = ux;
    const head = 5.5 * dpr;

    axisOrbitCtx.fillStyle = color;
    axisOrbitCtx.beginPath();
    axisOrbitCtx.moveTo(ex, ey);
    axisOrbitCtx.lineTo(ex - ux * head + nx * head * 0.55, ey - uy * head + ny * head * 0.55);
    axisOrbitCtx.lineTo(ex - ux * head - nx * head * 0.55, ey - uy * head - ny * head * 0.55);
    axisOrbitCtx.closePath();
    axisOrbitCtx.fill();

    const labelOffset = 8.5 * dpr;
    axisOrbitCtx.fillStyle = _hexToRgba(axis.color, towardViewer ? 1.0 : 0.78);
    axisOrbitCtx.fillText(axis.key, ex + nx * labelOffset, ey + ny * labelOffset);
  }

  axisOrbitCtx.fillStyle = 'rgba(43, 56, 72, 0.85)';
  axisOrbitCtx.beginPath();
  axisOrbitCtx.arc(cx, cy, 2.3 * dpr, 0, Math.PI * 2);
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

renderer.setPixelRatio(window.devicePixelRatio || 1);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xefefef);

const camera = new THREE.PerspectiveCamera(
  45,
  window.innerWidth / window.innerHeight,
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

const hemi = new THREE.HemisphereLight(0xffffff, 0x8c8c8c, 1.1);
hemi.position.set(0, 200, 0);
scene.add(hemi);

const dir1 = new THREE.DirectionalLight(0xffffff, 1.1);
dir1.position.set(120, 160, 100);
scene.add(dir1);

const dir2 = new THREE.DirectionalLight(0xffffff, 0.55);
dir2.position.set(-120, 100, -80);
scene.add(dir2);

const grid = new THREE.GridHelper(250, 12, 0xb5b5b5, 0xd5d5d5);
grid.position.y = 0;
scene.add(grid);

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

// Measurement color scheme - distinctive colors for each type
const measurementColors = {
  distance: 0x00dd00,      // Green
  diameter_ring: 0xff6b35,  // Orange
  radius: 0x004aff,         // Blue
  angle: 0xff00ff,          // Magenta
};

// 3D measurement value label styling (rendered as depth-tested sprites)
const MEAS_LABEL_FONT_PX = 16;
const MEAS_LABEL_TARGET_PX_HEIGHT = 18;
const MEAS_LABEL_MIN_PX_HEIGHT = 14;
const MEAS_LABEL_MAX_PX_HEIGHT = 28;
const MEAS_LABEL_PADDING_X = 10;
const MEAS_LABEL_PADDING_Y = 5;
const MEAS_LABEL_RADIUS = 8;
const MEAS_LABEL_BORDER_PX = 1.5;
const MEAS_LABEL_LINE_CLEARANCE_PX = 4;
const _measurementLabelWorldPos = new THREE.Vector3();

function showStatus(text) {
  status.textContent = text;
  status.style.display = 'block';
}

function hideStatus() {
  status.style.display = 'none';
}

function makeMaterial(colorValue) {
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(colorValue || '#9ea7b3'),
    metalness: 0.18,
    roughness: 0.62,
  });
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

  camera.near = Math.max(cameraDistance / 100, 0.1);
  camera.far = Math.max(cameraDistance * 10, 1000);
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
  const compactPartKey = (value) => normalizePartKey(value).replace(/[aeiouyåäöõ]/g, '').replace(/\s+/g, '');

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

  if (!targetName) {
    return coordPoint;
  }

  const mesh = _findPartMeshByIndex(partIndex) || _findPartMeshByName(targetName);
  if (mesh) {
    if (normalizedSpace === 'world') {
      return coordPoint;
    }
    return mesh.localToWorld(coordPoint);
  }

  const warningKey = `${targetName}|${partIndex}|${normalizedSpace}`;
  if (window?.__previewDebugAnchorWarnings && !_missingAnchorWarningKeys.has(warningKey)) {
    _missingAnchorWarningKeys.add(warningKey);
    console.warn(
      `[viewer] Measurement anchor fallback: part not found (name="${targetName}", index=${partIndex}, space="${normalizedSpace || 'local'}")`
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
  if (localAxis.lengthSq() <= 1e-8) {
    localAxis.set(0, 1, 0);
  }
  localAxis.normalize();

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
  ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
  ctx.fill();
  ctx.strokeStyle = colorStr;
  ctx.lineWidth = border;
  ctx.stroke();

  ctx.font = `600 ${fontPx}px "Segoe UI", Arial, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#2e3a46';
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
  const geometry = new THREE.ConeGeometry(size * 0.32, size, 18);
  const material = new THREE.MeshBasicMaterial({
    color,
    depthTest: true,
    depthWrite: true,
  });
  const cone = new THREE.Mesh(geometry, material);
  cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize());
  cone.position.copy(tip).sub(direction.clone().normalize().multiplyScalar(size * 0.5));
  cone.renderOrder = 1000;
  return cone;
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

function _diameterAxisForOverlay(definition) {
  const axisDirection = _resolveAxisDirection(definition?.part, definition?.axis_xyz, definition?.part_index);
  if (!axisDirection || axisDirection.lengthSq() <= 1e-10) {
    return null;
  }
  return axisDirection.clone().normalize();
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

function _resolveDiameterGeometry(definition) {
  const centerValue = _parseOverlayVector(definition?.center_xyz);
  if (!centerValue) {
    return null;
  }

  const partName = definition?.part;
  const partIndex = definition?.part_index;
  const center = _resolveAnchorPoint(partName, definition.center_xyz, '', partIndex);
  const axis = _resolveAxisDirection(partName, definition.axis_xyz, partIndex);
  if (!center || !axis) {
    return null;
  }

  const rawMode = String(definition?.diameter_mode || '').trim().toLowerCase();
  const mode = rawMode === 'measured' ? 'measured' : 'manual';
  let diameter = Number(definition?.diameter) || 0;
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
          diameter = projectedLength * 2;
        }
      } else if (mode === 'measured') {
        return null;
      }
    }
  } else if (mode === 'measured') {
    return null;
  }

  if (!Number.isFinite(diameter) || diameter <= 0) {
    return null;
  }

  const radius = diameter / 2;
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
    diameter,
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
  const color = measurementDragEnabled ? 0x19f25f : baseColor;
  const activePoint = String(definition.active_point || '').trim().toLowerCase();
  const offsetFromDefinition = _parseOverlayVector(definition.offset_xyz);
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
    const headSize = THREE.MathUtils.clamp(measuredLength * 0.08, Math.max(currentMaxDim * 0.015, 1.8), Math.max(currentMaxDim * 0.09, 4));
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
      depthTest: true,
      depthWrite: true,
    });
    const extensionMaterial = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.7,
      depthTest: true,
      depthWrite: true,
    });

    const startExtension = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([shiftedStart, dimensionStart]),
      extensionMaterial
    );
    group.add(startExtension);

    const endExtension = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([shiftedEnd, dimensionEnd]),
      extensionMaterial.clone()
    );
    group.add(endExtension);

    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([dimensionStart, dimensionEnd]),
      lineMaterial
    );
    line.userData = {
      dragKind: 'distance-offset',
      measurementIndex: measurmentIndex,
    };
    group.add(line);
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
  const headSize = THREE.MathUtils.clamp(measuredLength * 0.08, Math.max(currentMaxDim * 0.015, 1.8), Math.max(currentMaxDim * 0.09, 4));
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
    depthTest: true,
    depthWrite: true,
  });
  const extensionMaterial = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.7,
    depthTest: true,
    depthWrite: true,
  });

  const startExtension = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([shiftedStart, dimensionStart]),
    extensionMaterial
  );
  group.add(startExtension);

  const endExtension = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([shiftedEnd, dimensionEnd]),
    extensionMaterial.clone()
  );
  group.add(endExtension);

  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([dimensionStart, dimensionEnd]),
    lineMaterial
  );
  line.userData = {
    dragKind: 'distance-offset',
    measurementIndex: measurmentIndex,
  };
  group.add(line);
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
    diameter,
    tangent,
    bitangent,
  } = geometry;
  const group = new THREE.Group();
  const baseColor = measurementColors.diameter_ring;
  const color = measurementDragEnabled ? 0x19f25f : baseColor;

  const ringPoints = [];
  for (let i = 0; i <= 64; i += 1) {
    const angle = (i / 64) * Math.PI * 2;
    ringPoints.push(
      center.clone()
        .add(tangent.clone().multiplyScalar(Math.cos(angle) * radius))
        .add(bitangent.clone().multiplyScalar(Math.sin(angle) * radius))
    );
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
  definition.diameter = Number(diameter.toFixed(6));
  definition.measured_value = Number(diameter.toFixed(6));

  if (includeLabel) {
    const defaultAnchor = center.clone().add(tangent.clone().multiplyScalar(radius));
    const labelOffset = _parseOverlayVector(definition.offset_xyz) || _defaultDiameterOffsetForOverlay(definition);
    const labelAnchor = defaultAnchor.clone().add(labelOffset);
    let ringAnchor = defaultAnchor.clone();
    const radialToLabel = labelAnchor.clone().sub(center);
    const axial = axis.clone().multiplyScalar(radialToLabel.dot(axis));
    const radialProjected = radialToLabel.clone().sub(axial);
    if (radialProjected.lengthSq() > 1e-8) {
      radialProjected.normalize().multiplyScalar(radius);
      ringAnchor = center.clone().add(radialProjected);
    }
    if (labelOffset.lengthSq() > 1e-8) {
      const leaderLine = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([ringAnchor, labelAnchor]),
        new THREE.LineBasicMaterial({
          color,
          transparent: true,
          opacity: 0.7,
          depthTest: true,
          depthWrite: true,
        })
      );
      leaderLine.userData = {
        dragKind: 'diameter-offset',
        measurementIndex,
      };
      group.add(leaderLine);
    }
    const labelSprite = _makeMeasurementLabel(`${diameter.toFixed(3)}`, color, labelAnchor);
    if (labelSprite) {
      labelSprite.userData = {
        ...(labelSprite.userData || {}),
        dragKind: 'diameter-offset',
        measurementIndex,
      };
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
  clearCurrentMeshes();
  showStatus('No model loaded.');
};

window.setWheelZoomEnabled = function (enabled) {
  wheelZoomEnabled = !!enabled;
};

window.setControlHintText = function (text) {
  _setControlHintText(text);
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

window.loadModel = function (modelPath, label = null) {
  if (!modelPath) {
    window.clearModel();
    return;
  }

  showStatus('Loading STL model…');

  loader.load(
    modelPath,
    (geometry) => {
      clearCurrentMeshes();

      geometry.computeVertexNormals();
      geometry.center();

      const mesh = new THREE.Mesh(geometry, makeMaterial('#9ea7b3'));
      mesh._partName = label || 'Model';
      currentMeshes = [mesh];
      currentGroup = new THREE.Group();
      currentGroup.add(mesh);
      scene.add(currentGroup);

      applyModelTransformAndFrame(true);
      hideStatus();
    },
    undefined,
    (error) => {
      console.error('STL load failed:', error);
      showStatus('Failed to load STL model.');
    }
  );
};

window.loadAssembly = function (parts) {
  if (!Array.isArray(parts) || parts.length === 0) {
    window.clearModel();
    return;
  }

  clearCurrentMeshes();
  showStatus('Loading assembly…');

  currentGroup = new THREE.Group();
  scene.add(currentGroup);

  currentMeshes = new Array(parts.length).fill(null);
  partTransforms = parts.map((p) => ({
    x: p.offset_x || 0, y: p.offset_y || 0, z: p.offset_z || 0,
    rx: p.rot_x || 0, ry: p.rot_y || 0, rz: p.rot_z || 0,
  }));
  let remaining = parts.length;
  let loadedCount = 0;

  const finishIfDone = () => {
    remaining -= 1;

    if (remaining > 0) {
      return;
    }

    if (loadedCount === 0) {
      showStatus('Failed to load assembly.');
      return;
    }

    applyModelTransformAndFrame(true);
    hideStatus();
  };

  parts.forEach((part, index) => {
    const file = part?.file;
    const color = part?.color || '#9ea7b3';

    if (!file) {
      finishIfDone();
      return;
    }

    loader.load(
      file,
      (geometry) => {
        geometry.computeVertexNormals();

        const mesh = new THREE.Mesh(geometry, makeMaterial(color));
        mesh._partIndex = index;
        mesh._partName = part?.name || `Part ${index + 1}`;

        const t = _normalizedPartTransform(partTransforms[index]);
        mesh.position.set(t.x, t.y, t.z);
        mesh.rotation.set(
          THREE.MathUtils.degToRad(t.rx),
          THREE.MathUtils.degToRad(t.ry),
          THREE.MathUtils.degToRad(t.rz)
        );

        currentMeshes[index] = mesh;
        currentGroup.add(mesh);
        loadedCount += 1;
        _restoreRequestedSelection();
        finishIfDone();
      },
      undefined,
      (error) => {
        console.error('Assembly STL load failed:', file, error);
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
    mesh.material.color.set(colorValue);
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

window.setRenderingEnabled = function (enabled) {
  renderingEnabled = !!enabled;
  if (renderingEnabled) {
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
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  if (axisOrbitVisible) {
    _drawAxisOrbit();
  }
});

showStatus('Viewer ready.');
