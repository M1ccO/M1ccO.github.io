export function createMeasurementFactories(deps) {
  return {
    distance: (overlay, overlayIndex) => deps.makeDistanceMeasurement(overlay, overlayIndex),
    length: (overlay, overlayIndex) => deps.makeDistanceMeasurement(overlay, overlayIndex),
    diameter_ring: (overlay) => deps.makeDiameterRing(overlay),
    radius: (overlay) => deps.makeRadiusMeasurement(overlay),
    angle: (overlay) => deps.makeAngleMeasurement(overlay),
  };
}
