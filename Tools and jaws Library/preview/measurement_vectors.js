import * as THREE from './three.module.js';

function _toFiniteNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function parseOverlayVector(value) {
  if (Array.isArray(value) && value.length >= 3) {
    const x = _toFiniteNumber(value[0]);
    const y = _toFiniteNumber(value[1]);
    const z = _toFiniteNumber(value[2]);
    if (x == null || y == null || z == null) {
      return null;
    }
    return new THREE.Vector3(x, y, z);
  }
  const text = String(value || '').trim();
  if (!text) {
    return null;
  }
  const parts = text.split(/[;,\s]+/).filter(Boolean);
  if (parts.length < 3) {
    return null;
  }
  const x = _toFiniteNumber(parts[0]);
  const y = _toFiniteNumber(parts[1]);
  const z = _toFiniteNumber(parts[2]);
  if (x == null || y == null || z == null) {
    return null;
  }
  return new THREE.Vector3(x, y, z);
}

export function formatVec3(value) {
  const x = Number.isFinite(Number(value?.x)) ? Number(value.x) : 0;
  const y = Number.isFinite(Number(value?.y)) ? Number(value.y) : 0;
  const z = Number.isFinite(Number(value?.z)) ? Number(value.z) : 0;
  return `${x.toFixed(4)}, ${y.toFixed(4)}, ${z.toFixed(4)}`;
}
