export function createMeasurementFactories(deps) {
  return {
    distance: (overlay, overlayIndex) => deps.makeDistanceMeasurement(overlay, overlayIndex),
    length: (overlay, overlayIndex) => deps.makeDistanceMeasurement(overlay, overlayIndex),
    diameter_ring: (overlay, overlayIndex) => deps.makeDiameterRing(overlay, {}, overlayIndex),
    radius: (overlay) => deps.makeRadiusMeasurement(overlay),
    angle: (overlay) => deps.makeAngleMeasurement(overlay),
  };
}
