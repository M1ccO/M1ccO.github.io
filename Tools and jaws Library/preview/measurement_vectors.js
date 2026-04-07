import * as THREE from './three.module.js';

export function parseOverlayVector(value) {
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

export function formatVec3(value) {
  return `${value.x.toFixed(4)}, ${value.y.toFixed(4)}, ${value.z.toFixed(4)}`;
}
