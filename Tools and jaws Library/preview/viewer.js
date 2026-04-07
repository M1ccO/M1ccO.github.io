import * as THREE from './three.module.js';
import { OrbitControls } from './OrbitControls.js';
import { STLLoader } from './STLLoader.js';
import { TransformControls } from './TransformControls.js';

const canvas = document.getElementById('viewport');
const status = document.getElementById('status');

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

let fineTransformSnapEnabled = false;

function _updateTransformSnap() {
  if (fineTransformSnapEnabled) {
    transformControl.setTranslationSnap(0.1);
    transformControl.setRotationSnap(THREE.MathUtils.degToRad(0.1));
    return;
  }
  transformControl.setTranslationSnap(1);
  transformControl.setRotationSnap(THREE.MathUtils.degToRad(1));
}

_updateTransformSnap();
const selectionProxy = new THREE.Group();
selectionProxy.visible = false;
scene.add(selectionProxy);

transformControl.addEventListener('dragging-changed', (event) => {
  controls.enabled = !event.value;
  if (event.value && transformControl.object) {
    const object = transformControl.object;
    _fineDragState = {
      object,
      startPosition: object.position.clone(),
      startRotation: object.rotation.clone(),
    };
  }
  if (event.value && transformControl.object === selectionProxy) {
    _selectionProxyDragState = {
      position: selectionProxy.position.clone(),
      quaternion: selectionProxy.quaternion.clone(),
    };
  }
  if (!event.value) {
    _fineDragState = null;
    _selectionProxyDragState = null;
    _gizmoDragJustEnded = true;
    setTimeout(() => { _gizmoDragJustEnded = false; }, 100);
  }
});

transformControl.addEventListener('objectChange', () => {
  const mesh = transformControl.object;
  if (_fineDragState && mesh === _fineDragState.object) {
    _applyFineDragDamping(mesh);
  }
  if (mesh === selectionProxy && selectedMeshIndices.length > 1) {
    _applySelectionProxyTransform();
    return;
  }
  if (mesh && typeof mesh._partIndex === 'number') {
    const index = mesh._partIndex;
    if (index >= 0 && index < partTransforms.length) {
      const t = partTransforms[index];
      if (transformControl.getMode() === 'translate') {
        t.x = _snapMm(mesh.position.x);
        t.y = _snapMm(mesh.position.y);
        t.z = _snapMm(mesh.position.z);
      } else {
        t.rx = _snapDegrees(THREE.MathUtils.radToDeg(mesh.rotation.x));
        t.ry = _snapDegrees(THREE.MathUtils.radToDeg(mesh.rotation.y));
        t.rz = _snapDegrees(THREE.MathUtils.radToDeg(mesh.rotation.z));
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
let renderingEnabled = true;
let _gizmoDragJustEnded = false;
let pointPickingEnabled = false;
let _pickMarker = null;
const _tcRaycaster = new THREE.Raycaster();
const _tcPointer = new THREE.Vector2();
const _measurementDragRaycaster = new THREE.Raycaster();
const _measurementDragPointer = new THREE.Vector2();
let _measurementDragState = null;
let _measurementDragJustEnded = false;
let _selectionProxyDragState = null;
let _fineDragState = null;

const FINE_DRAG_GAIN = 0.005;
const TRANSFORM_PAN_GAIN = 0.35;
const TRANSFORM_FINE_PAN_GAIN = 0.015;

function _updateTransformPanGain() {
  if (!transformEditEnabled) {
    controls.panSpeed = 1.0;
    return;
  }
  controls.panSpeed = fineTransformSnapEnabled ? TRANSFORM_FINE_PAN_GAIN : TRANSFORM_PAN_GAIN;
}

_updateTransformPanGain();

window.addEventListener('keydown', (event) => {
  const ctrlNow = !!event.ctrlKey;
  if (ctrlNow === fineTransformSnapEnabled) {
    return;
  }
  fineTransformSnapEnabled = ctrlNow;
  _updateTransformSnap();
  _updateTransformPanGain();
});

window.addEventListener('keyup', (event) => {
  const ctrlNow = !!event.ctrlKey;
  if (ctrlNow === fineTransformSnapEnabled) {
    return;
  }
  fineTransformSnapEnabled = ctrlNow;
  _updateTransformSnap();
  _updateTransformPanGain();
});

window.addEventListener('blur', () => {
  fineTransformSnapEnabled = false;
  _updateTransformSnap();
  _updateTransformPanGain();
});

// Measurement color scheme - distinctive colors for each type
const measurementColors = {
  distance: 0x00dd00,      // Green
  diameter_ring: 0xff6b35,  // Orange
  radius: 0x004aff,         // Blue
  angle: 0xff00ff,          // Magenta
};

// HUD labels container and positioning
let _hudLabelsContainer = null;
const _hudLabels = [];
const HUD_PADDING = 12;
const HUD_LABEL_HEIGHT = 60;

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
  _clearHudLabels();
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
    document.title = 'TRANSFORM_BATCH:' + JSON.stringify(payload);
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
  document.title = 'TRANSFORM:' + JSON.stringify({
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
  document.title = 'PART_SELECTIONS:' + JSON.stringify(selectedMeshIndices.slice());
}

function _updateSelectionProxyFromSelection() {
  if (selectedMeshIndices.length <= 1) {
    selectionProxy.visible = false;
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
  if (!_selectionProxyDragState || selectedMeshIndices.length <= 1) {
    return;
  }

  const previousPosition = _selectionProxyDragState.position.clone();
  const previousQuaternion = _selectionProxyDragState.quaternion.clone();
  const deltaPosition = selectionProxy.position.clone().sub(previousPosition);
  const deltaQuaternion = selectionProxy.quaternion.clone().multiply(previousQuaternion.clone().invert());

  if (transformControl.getMode() === 'translate') {
    const worldPos = new THREE.Vector3();
    const targetWorldPos = new THREE.Vector3();
    for (const idx of selectedMeshIndices) {
      const mesh = currentMeshes[idx];
      if (!mesh) continue;
      const parent = mesh.parent || scene;
      mesh.getWorldPosition(worldPos);
      targetWorldPos.copy(worldPos).add(deltaPosition);
      mesh.position.copy(parent.worldToLocal(targetWorldPos.clone()));
    }
  } else {
    const worldPos = new THREE.Vector3();
    const targetWorldPos = new THREE.Vector3();
    const worldQuat = new THREE.Quaternion();
    const targetWorldQuat = new THREE.Quaternion();
    const parentWorldQuat = new THREE.Quaternion();
    const parentWorldQuatInv = new THREE.Quaternion();
    for (const idx of selectedMeshIndices) {
      const mesh = currentMeshes[idx];
      if (!mesh) continue;
      const parent = mesh.parent || scene;

      mesh.getWorldPosition(worldPos);
      targetWorldPos.copy(worldPos).sub(previousPosition).applyQuaternion(deltaQuaternion).add(previousPosition);
      mesh.position.copy(parent.worldToLocal(targetWorldPos.clone()));

      mesh.getWorldQuaternion(worldQuat);
      targetWorldQuat.copy(deltaQuaternion).multiply(worldQuat);
      parent.getWorldQuaternion(parentWorldQuat);
      parentWorldQuatInv.copy(parentWorldQuat).invert();
      mesh.quaternion.copy(parentWorldQuatInv.multiply(targetWorldQuat));
    }
  }

  _selectionProxyDragState.position.copy(selectionProxy.position);
  _selectionProxyDragState.quaternion.copy(selectionProxy.quaternion);
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
  transformControl.attach(currentMeshes[idx]);
  selectionProxy.visible = false;
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
    selectionProxy.visible = false;
    transformControl.attach(currentMeshes[selectedMeshIndex]);
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
  return currentMeshes.find((mesh) => mesh && String(mesh._partName || '').trim() === target) || null;
}

function _findPartMeshByIndex(partIndex) {
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

function _makeMeasurementLabel(text, colorHex = 0x00dd00) {
  // Convert hex color to CSS color
  const colorStr = '#' + colorHex.toString(16).padStart(6, '0').toUpperCase();
  
  // Create HTML for HUD overlay instead of 3D sprite
  const labelEl = document.createElement('div');
  labelEl.style.position = 'fixed';
  labelEl.style.background = 'rgba(255,255,255,.9)';
  labelEl.style.border = `1px solid ${colorStr}`;
  labelEl.style.borderRadius = '8px';
  labelEl.style.color = '#4a4a4a';
  labelEl.style.padding = '6px 10px';
  labelEl.style.fontSize = '12px';
  labelEl.style.fontWeight = '400';
  labelEl.style.fontFamily = 'Segoe UI, Arial, sans-serif';
  labelEl.style.whiteSpace = 'nowrap';
  labelEl.style.pointerEvents = 'none';
  labelEl.style.zIndex = '1000';
  labelEl.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.08)';
  labelEl.textContent = text;
  
  // Position in upper right corner with stack layout
  const yOffset = HUD_PADDING + (_hudLabels.length * HUD_LABEL_HEIGHT);
  labelEl.style.top = yOffset + 'px';
  labelEl.style.right = HUD_PADDING + 'px';
  
  document.body.appendChild(labelEl);
  _hudLabels.push(labelEl);
  
  return labelEl;
}

function _clearHudLabels() {
  for (const label of _hudLabels) {
    if (label && label.parentNode) {
      label.parentNode.removeChild(label);
    }
  }
  _hudLabels.length = 0;
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
  return `${measuredLength.toFixed(3)} mm`;
}

function _parseOverlayVector(value) {
  if (Array.isArray(value) && value.length >= 3) {
    return new THREE.Vector3(Number(value[0]) || 0, Number(value[1]) || 0, Number(value[2]) || 0);
  }
  const text = String(value || '').trim();
  if (!text) {
    return null;
  }
  const parts = text.split(/[;,\s]+/).filter(Boolean);
  if (parts.length < 3) {
    return null;
  }
  return new THREE.Vector3(Number(parts[0]) || 0, Number(parts[1]) || 0, Number(parts[2]) || 0);
}

function _formatVec3(value) {
  return `${value.x.toFixed(4)}, ${value.y.toFixed(4)}, ${value.z.toFixed(4)}`;
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

function _applyFineDragDamping(object) {
  if (!_fineDragState || _fineDragState.object !== object) {
    return;
  }

  if (!fineTransformSnapEnabled) {
    return;
  }

  // Apply custom gain only to translation. Rotation stays on native
  // TransformControls snapping to prevent fine-mode jump artifacts.
  if (transformControl.getMode() !== 'translate') {
    return;
  }

  const gain = FINE_DRAG_GAIN;
  const snapMm = _snapFineMm;
  const rawDelta = object.position.clone().sub(_fineDragState.startPosition);
  rawDelta.multiplyScalar(gain);
  const snappedDelta = new THREE.Vector3(
    snapMm(rawDelta.x),
    snapMm(rawDelta.y),
    snapMm(rawDelta.z),
  );
  object.position.copy(_fineDragState.startPosition.clone().add(snappedDelta));
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

function _distanceDragObjects() {
  const objects = [];
  measurementGroup.traverse((node) => {
    if (node?.userData?.dragKind) {
      objects.push(node);
    }
  });
  return objects;
}

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

function _emitMeasurementUpdated(index) {
  if (!Number.isInteger(index) || index < 0 || index >= measurementOverlays.length) {
    return;
  }
  document.title = 'MEASUREMENT_UPDATED:' + JSON.stringify({
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
  const offsetFromDefinition = _parseOverlayVector(definition.offset_xyz);
  const startShift = Number(definition.start_shift) || 0;
  const endShift = Number(definition.end_shift) || 0;

  const makeDragHandle = (position, dragKind) => {
    const handleSize = Math.max(currentMaxDim * 0.018, 1.8);
    const geometry = new THREE.SphereGeometry(handleSize, 12, 10);
    const material = new THREE.MeshBasicMaterial({ color, depthTest: true, depthWrite: true });
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
    const labelText = `${definition.name}: ${_distanceLabelValue(definition, measuredLength)}`;
    _makeMeasurementLabel(labelText, color);
    return group;
  }

  const localAxis = axisName === 'x'
    ? [1, 0, 0]
    : (axisName === 'y' ? [0, 1, 0] : [0, 0, 1]);
  const axisDirection =
    _resolveAxisDirection(definition.start_part, localAxis)
    || _resolveAxisDirection(definition.end_part, localAxis)
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
  const labelText = `${definition.name}: ${_distanceLabelValue(definition, measuredLength)}`;
  _makeMeasurementLabel(labelText, color);
  return group;
}

function _makeDiameterRing(definition) {
  const diameter = Number(definition.diameter) || 0;
  if (!Number.isFinite(diameter) || diameter <= 0) {
    return null;
  }

  const center = _resolveAnchorPoint(definition.part, definition.center_xyz);
  const axis = _resolveAxisDirection(definition.part, definition.axis_xyz);
  if (!center || !axis) {
    return null;
  }
  const radius = diameter / 2;
  const group = new THREE.Group();
  const color = measurementColors.diameter_ring;

  const reference = Math.abs(axis.dot(new THREE.Vector3(0, 1, 0))) > 0.9
    ? new THREE.Vector3(1, 0, 0)
    : new THREE.Vector3(0, 1, 0);
  const tangent = new THREE.Vector3().crossVectors(axis, reference).normalize();
  const bitangent = new THREE.Vector3().crossVectors(axis, tangent).normalize();

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
  group.add(ring);

  _makeMeasurementLabel(`${definition.name}: ${diameter.toFixed(3)} mm`, color);
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
  const ring = _makeDiameterRing(ringDef);
  if (ring) {
    ring.children.forEach((child) => {
      if (!(child instanceof THREE.Sprite) && !(child.style)) {
        group.add(child);
      }
    });
  }

  _makeMeasurementLabel(`${definition.name}: R ${radius.toFixed(3)} mm`, color);
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

  _makeMeasurementLabel(`${definition.name}: ${angleDeg.toFixed(2)} deg`, color);
  return group;
}

function _renderMeasurements() {
  _clearMeasurements();
  if (!measurementsVisible || !currentGroup || measurementOverlays.length === 0) {
    measurementGroup.visible = false;
    return;
  }

  for (let overlayIndex = 0; overlayIndex < measurementOverlays.length; overlayIndex += 1) {
    const overlay = measurementOverlays[overlayIndex];
    if (!overlay || (measurementFilter && String(overlay.name || '') !== measurementFilter)) {
      continue;
    }
    const node = overlay.type === 'diameter_ring'
      ? _makeDiameterRing(overlay)
      : (overlay.type === 'radius'
        ? _makeRadiusMeasurement(overlay)
        : (overlay.type === 'angle'
          ? _makeAngleMeasurement(overlay)
          : _makeDistanceMeasurement(overlay, overlayIndex)));
    if (node) {
      measurementGroup.add(node);
    }
  }

  measurementGroup.visible = measurementGroup.children.length > 0;
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
  if (_measurementDragJustEnded) return;
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
      document.title = 'POINT_PICKED:' + JSON.stringify({
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
  if (!measurementsVisible || !measurementDragEnabled || event.button !== 0) {
    return;
  }
  const rect = canvas.getBoundingClientRect();
  _measurementDragPointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  _measurementDragPointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  _measurementDragRaycaster.setFromCamera(_measurementDragPointer, camera);

  const dragTargets = _distanceDragObjects();
  if (dragTargets.length === 0) {
    return;
  }

  const intersects = _measurementDragRaycaster.intersectObjects(dragTargets, false);
  if (intersects.length === 0) {
    return;
  }

  const hit = intersects[0];
  const dragKind = String(hit.object?.userData?.dragKind || '');
  const measurementIndex = Number(hit.object?.userData?.measurementIndex);
  if (!Number.isInteger(measurementIndex) || measurementIndex < 0 || measurementIndex >= measurementOverlays.length) {
    return;
  }

  const overlay = measurementOverlays[measurementIndex];
  if (!overlay || String(overlay.type || '').toLowerCase() !== 'distance') {
    return;
  }

  const axisDir = _distanceDirectionForOverlay(overlay);
  if (!axisDir) {
    return;
  }

  const plane = new THREE.Plane();
  const planeNormal = camera.getWorldDirection(new THREE.Vector3()).normalize();
  plane.setFromNormalAndCoplanarPoint(planeNormal, hit.point.clone());

  const planeStartPoint = new THREE.Vector3();
  if (!_measurementDragRaycaster.ray.intersectPlane(plane, planeStartPoint)) {
    return;
  }

  _measurementDragState = {
    dragKind,
    measurementIndex,
    axisDir,
    plane,
    planeStartPoint,
    originalOffset: _parseOverlayVector(overlay.offset_xyz) || _defaultDistanceOffsetForOverlay(overlay),
    originalStartShift: Number(overlay.start_shift) || 0,
    originalEndShift: Number(overlay.end_shift) || 0,
  };
  controls.enabled = false;
  event.preventDefault();
});

canvas.addEventListener('mousemove', (event) => {
  const rect = canvas.getBoundingClientRect();
  _measurementDragPointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  _measurementDragPointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  _measurementDragRaycaster.setFromCamera(_measurementDragPointer, camera);

  if (!_measurementDragState) {
    if (!measurementsVisible || !measurementDragEnabled) {
      canvas.style.cursor = '';
      return;
    }
    const hoverTargets = _distanceDragObjects();
    if (hoverTargets.length === 0) {
      canvas.style.cursor = '';
      return;
    }
    const hoverIntersects = _measurementDragRaycaster.intersectObjects(hoverTargets, false);
    canvas.style.cursor = hoverIntersects.length > 0 ? 'grab' : '';
    return;
  }

  canvas.style.cursor = 'grabbing';

  const currentPoint = new THREE.Vector3();
  if (!_measurementDragRaycaster.ray.intersectPlane(_measurementDragState.plane, currentPoint)) {
    return;
  }

  const delta = currentPoint.clone().sub(_measurementDragState.planeStartPoint);
  const overlay = measurementOverlays[_measurementDragState.measurementIndex];
  if (!overlay) {
    return;
  }

  // Ctrl held = 0.1 mm precision; normal = 1 mm snap
  const snap = event.ctrlKey
    ? (v) => Math.round(Number(v) * 10) / 10
    : _snapMm;
  const snapVec = event.ctrlKey
    ? (v) => new THREE.Vector3(snap(v.x), snap(v.y), snap(v.z))
    : _snapVec3Mm;

  if (_measurementDragState.dragKind === 'distance-offset') {
    const alongAxis = _measurementDragState.axisDir.clone().multiplyScalar(delta.dot(_measurementDragState.axisDir));
    const sidewaysDelta = delta.clone().sub(alongAxis);
    const newOffset = snapVec(_measurementDragState.originalOffset.clone().add(sidewaysDelta));
    overlay.offset_xyz = _formatVec3(newOffset);
  } else if (_measurementDragState.dragKind === 'distance-start') {
    const shift = delta.dot(_measurementDragState.axisDir);
    overlay.start_shift = String(snap(_measurementDragState.originalStartShift + shift));
  } else if (_measurementDragState.dragKind === 'distance-end') {
    const shift = delta.dot(_measurementDragState.axisDir);
    overlay.end_shift = String(snap(_measurementDragState.originalEndShift + shift));
  }

  _scheduleMeasurementsRender();
  event.preventDefault();
});

document.addEventListener('mouseup', () => {
  if (!_measurementDragState) {
    return;
  }
  const updatedIndex = _measurementDragState.measurementIndex;
  _measurementDragState = null;
  controls.enabled = true;
  _emitMeasurementUpdated(updatedIndex);
  _measurementDragJustEnded = true;
  canvas.style.cursor = '';
  setTimeout(() => {
    _measurementDragJustEnded = false;
  }, 120);
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

// Measurement labels are fixed HUD overlays, while distance helpers are draggable in 3D.

window.setPointPickingEnabled = function (enabled) {
  pointPickingEnabled = !!enabled;
  if (!pointPickingEnabled) {
    _clearPickMarker();
  }
};

window.setTransformEditEnabled = function (enabled) {
  transformEditEnabled = !!enabled;
  _updateTransformPanGain();
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
      transformControl.setSpace('world');
    } else {
      transformControl.setSpace('local');
    }
  }
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
  if (selectedMeshIndices.length > 1) {
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
  if (selectedMeshIndices.length > 1) {
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
  _scheduleMeasurementsRender();
};

window.setMeasurementsVisible = function (visible) {
  measurementsVisible = !!visible;
  _scheduleMeasurementsRender();
};

window.setMeasurementVisibilityOverride = function (forceHidden) {
  if (forceHidden) {
    measurementGroup.visible = false;
  }
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

window.setRenderingEnabled = function (enabled) {
  renderingEnabled = !!enabled;
  if (renderingEnabled) {
    renderer.render(scene, camera);
  }
};

function animate() {
  requestAnimationFrame(animate);
  if (!renderingEnabled) {
    return;
  }
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

showStatus('Viewer ready.');
