const _eventState = {
  seq: 0,
  lastByType: new Map(),
};

function _stableJson(value) {
  try {
    return JSON.stringify(value);
  } catch (_err) {
    return '{}';
  }
}

export function emitPreviewEvent(type, payload) {
  const normalizedType = String(type || '').trim();
  if (!normalizedType) {
    return;
  }

  const body = _stableJson(payload);
  const fingerprint = `${normalizedType}:${body}`;
  if (_eventState.lastByType.get(normalizedType) === fingerprint) {
    return;
  }

  _eventState.lastByType.set(normalizedType, fingerprint);
  _eventState.seq += 1;
  document.title = `${normalizedType}:${body}`;
}

export function getPreviewBridgeStats() {
  return {
    seq: _eventState.seq,
    trackedTypes: _eventState.lastByType.size,
  };
}
