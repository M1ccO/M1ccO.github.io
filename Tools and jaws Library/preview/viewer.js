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

const transformControl = new TransformControls(camera, renderer.domElement);
transformControl.setSize(0.8);
transformControl.visible = false;
scene.add(transformControl);

transformControl.addEventListener('dragging-changed', (event) => {
  controls.enabled = !event.value;
  if (!event.value) {
    _gizmoDragJustEnded = true;
    setTimeout(() => { _gizmoDragJustEnded = false; }, 100);
  }
});

transformControl.addEventListener('objectChange', () => {
  _syncSelectedTransform();
  _renderMeasurements();
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
let partTransforms = [];
let measurementOverlays = [];
let measurementsVisible = false;
let measurementFilter = '';
let _gizmoDragJustEnded = false;
const _tcRaycaster = new THREE.Raycaster();
const _tcPointer = new THREE.Vector2();

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

  _renderMeasurements();
}

function _syncSelectedTransform() {
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

function _selectPartByIndex(idx) {
  if (selectedMeshIndex >= 0 && selectedMeshIndex < currentMeshes.length) {
    _highlightMesh(currentMeshes[selectedMeshIndex], false);
  }
  if (idx < 0 || idx >= currentMeshes.length || !currentMeshes[idx]) {
    transformControl.detach();
    selectedMeshIndex = -1;
    document.title = 'PART_SELECTED:-1';
    return;
  }
  selectedMeshIndex = idx;
  _highlightMesh(currentMeshes[idx], true);
  transformControl.attach(currentMeshes[idx]);
  document.title = 'PART_SELECTED:' + idx;
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
  if (requestedSelectedMeshIndex < 0) {
    _selectPartByIndex(-1);
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

function _resolveAnchorPoint(partName, point) {
  const targetName = String(partName || '').trim();
  const localPoint = new THREE.Vector3(
    Number(point?.[0]) || 0,
    Number(point?.[1]) || 0,
    Number(point?.[2]) || 0,
  );

  const mesh = _findPartMeshByName(targetName);
  if (mesh) {
    return mesh.localToWorld(localPoint);
  }
  if (targetName) {
    return null;
  }
  if (currentGroup) {
    return currentGroup.localToWorld(localPoint);
  }
  return localPoint;
}

function _resolveAxisDirection(partName, axis) {
  const targetName = String(partName || '').trim();
  const localAxis = new THREE.Vector3(
    Number(axis?.[0]) || 0,
    Number(axis?.[1]) || 0,
    Number(axis?.[2]) || 0,
  );
  if (localAxis.lengthSq() <= 1e-8) {
    localAxis.set(0, 1, 0);
  }
  localAxis.normalize();

  const mesh = _findPartMeshByName(targetName);
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

function _makeMeasurementLabel(text) {
  const canvasEl = document.createElement('canvas');
  const ctx = canvasEl.getContext('2d');
  const paddingX = 22;
  const paddingY = 14;
  const fontSize = 38;
  const font = `600 ${fontSize}px Segoe UI, Arial, sans-serif`;
  ctx.font = font;
  const metrics = ctx.measureText(text);
  const width = Math.ceil(metrics.width + paddingX * 2);
  const height = Math.ceil(fontSize + paddingY * 2);
  canvasEl.width = width;
  canvasEl.height = height;

  const draw = canvasEl.getContext('2d');
  draw.font = font;
  draw.fillStyle = 'rgba(17, 25, 35, 0.92)';
  draw.strokeStyle = 'rgba(80, 157, 255, 0.95)';
  draw.lineWidth = 4;
  const radius = 14;
  draw.beginPath();
  draw.moveTo(radius, 0);
  draw.lineTo(width - radius, 0);
  draw.quadraticCurveTo(width, 0, width, radius);
  draw.lineTo(width, height - radius);
  draw.quadraticCurveTo(width, height, width - radius, height);
  draw.lineTo(radius, height);
  draw.quadraticCurveTo(0, height, 0, height - radius);
  draw.lineTo(0, radius);
  draw.quadraticCurveTo(0, 0, radius, 0);
  draw.closePath();
  draw.fill();
  draw.stroke();
  draw.fillStyle = '#ffffff';
  draw.textBaseline = 'middle';
  draw.fillText(text, paddingX, height / 2);

  const texture = new THREE.CanvasTexture(canvasEl);
  texture.needsUpdate = true;
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  const worldScale = Math.max(currentMaxDim * 0.07, 14);
  sprite.scale.set((width / 110) * worldScale, (height / 110) * worldScale, 1);
  sprite.renderOrder = 1000;
  return sprite;
}

function _makeArrowCone(tip, direction, size, color) {
  const geometry = new THREE.ConeGeometry(size * 0.32, size, 18);
  const material = new THREE.MeshBasicMaterial({
    color,
    depthTest: false,
    depthWrite: false,
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

function _makeDistanceMeasurement(definition) {
  const start = _resolveAnchorPoint(definition.start_part, definition.start_xyz);
  const end = _resolveAnchorPoint(definition.end_part, definition.end_xyz);
  if (!start || !end) {
    return null;
  }
  const span = end.clone().sub(start);
  const length = span.length();
  if (!Number.isFinite(length) || length <= 1e-6) {
    return null;
  }

  const direction = span.clone().normalize();
  const group = new THREE.Group();
  const color = 0xf8fbff;
  const headSize = THREE.MathUtils.clamp(length * 0.08, Math.max(currentMaxDim * 0.015, 1.8), Math.max(currentMaxDim * 0.09, 4));
  const midpoint = start.clone().lerp(end, 0.5);
  const offsetDirection = _measurementOffsetDirection(direction, midpoint);
  const offsetDistance = THREE.MathUtils.clamp(
    length * 0.16,
    Math.max(currentMaxDim * 0.08, 8),
    Math.max(currentMaxDim * 0.22, 24)
  );
  const offsetVector = offsetDirection.clone().multiplyScalar(offsetDistance);
  const dimensionStart = start.clone().add(offsetVector);
  const dimensionEnd = end.clone().add(offsetVector);

  const lineMaterial = new THREE.LineBasicMaterial({
    color,
    depthTest: false,
    depthWrite: false,
  });
  const extensionMaterial = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.7,
    depthTest: false,
    depthWrite: false,
  });

  const startExtension = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([start, dimensionStart]),
    extensionMaterial
  );
  startExtension.renderOrder = 998;
  group.add(startExtension);

  const endExtension = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([end, dimensionEnd]),
    extensionMaterial.clone()
  );
  endExtension.renderOrder = 998;
  group.add(endExtension);

  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([dimensionStart, dimensionEnd]),
    lineMaterial
  );
  line.renderOrder = 999;
  group.add(line);
  group.add(_makeArrowCone(dimensionStart, direction.clone().negate(), headSize, color));
  group.add(_makeArrowCone(dimensionEnd, direction, headSize, color));

  const labelText = `${definition.name}: ${length.toFixed(3)} mm`;
  const label = _makeMeasurementLabel(labelText);
  const labelOffset = offsetDirection.clone().multiplyScalar(Math.max(currentMaxDim * 0.06, headSize * 2.2));
  label.position.copy(dimensionStart).lerp(dimensionEnd, 0.5).add(labelOffset);
  group.add(label);
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
  const color = 0x5db3ff;

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
    depthTest: false,
    depthWrite: false,
  });
  const ring = new THREE.Line(ringGeometry, ringMaterial);
  ring.renderOrder = 999;
  group.add(ring);

  const label = _makeMeasurementLabel(`${definition.name}: ${diameter.toFixed(3)} mm`);
  const radialToCamera = _measurementOffsetDirection(axis, center);
  const sideDirection = new THREE.Vector3().crossVectors(axis, radialToCamera).normalize();
  const labelRadius = radius + Math.max(currentMaxDim * 0.12, diameter * 0.18, 14);
  label.position.copy(center)
    .add(radialToCamera.clone().multiplyScalar(labelRadius))
    .add(sideDirection.multiplyScalar(Math.max(currentMaxDim * 0.04, 6)));
  group.add(label);
  return group;
}

function _renderMeasurements() {
  _clearMeasurements();
  if (!measurementsVisible || !currentGroup || measurementOverlays.length === 0) {
    measurementGroup.visible = false;
    return;
  }

  for (const overlay of measurementOverlays) {
    if (!overlay || (measurementFilter && String(overlay.name || '') !== measurementFilter)) {
      continue;
    }
    const node = overlay.type === 'diameter_ring'
      ? _makeDiameterRing(overlay)
      : _makeDistanceMeasurement(overlay);
    if (node) {
      measurementGroup.add(node);
    }
  }

  measurementGroup.visible = measurementGroup.children.length > 0;
}

function clearCurrentMeshes() {
  transformControl.detach();
  if (selectedMeshIndex >= 0 && selectedMeshIndex < currentMeshes.length) {
    _highlightMesh(currentMeshes[selectedMeshIndex], false);
  }
  selectedMeshIndex = -1;
  requestedSelectedMeshIndex = -1;
  partTransforms = [];
  _clearMeasurements();

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
  if (!transformEditEnabled || _gizmoDragJustEnded) return;
  if (currentMeshes.length === 0) return;

  const rect = canvas.getBoundingClientRect();
  _tcPointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  _tcPointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

  _tcRaycaster.setFromCamera(_tcPointer, camera);
  const meshes = currentMeshes.filter((m) => m != null);
  const intersects = _tcRaycaster.intersectObjects(meshes, false);

  if (intersects.length > 0) {
    const hit = intersects[0].object;
    const idx = hit._partIndex != null ? hit._partIndex : currentMeshes.indexOf(hit);
    _selectPartByIndex(idx);
  } else {
    _selectPartByIndex(-1);
  }
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

window.setTransformEditEnabled = function (enabled) {
  transformEditEnabled = !!enabled;
  if (!transformEditEnabled) {
    requestedSelectedMeshIndex = -1;
    _selectPartByIndex(-1);
    return;
  }
  _restoreRequestedSelection();
};

window.setTransformMode = function (mode) {
  if (mode === 'translate' || mode === 'rotate') {
    transformControl.setMode(mode);
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
  if (selectedMeshIndex >= 0) {
    _syncSelectedTransform();
  }
  _renderMeasurements();
};

window.selectPart = function (index) {
  requestedSelectedMeshIndex = typeof index === 'number' ? index : -1;
  if (!transformEditEnabled) return;
  _restoreRequestedSelection();
};

window.resetSelectedPartTransform = function () {
  if (selectedMeshIndex < 0 || selectedMeshIndex >= currentMeshes.length) return;
  const mesh = currentMeshes[selectedMeshIndex];
  if (!mesh) return;
  mesh.position.set(0, 0, 0);
  mesh.rotation.set(0, 0, 0);
  partTransforms[selectedMeshIndex] = { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 };
  _syncSelectedTransform();
  _renderMeasurements();
};

window.setMeasurements = function (definitions) {
  measurementOverlays = Array.isArray(definitions) ? definitions : [];
  _renderMeasurements();
};

window.setMeasurementsVisible = function (visible) {
  measurementsVisible = !!visible;
  _renderMeasurements();
};

window.setMeasurementFilter = function (name) {
  measurementFilter = String(name || '').trim();
  _renderMeasurements();
};

function animate() {
  requestAnimationFrame(animate);
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
