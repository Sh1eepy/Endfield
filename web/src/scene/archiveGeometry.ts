/** Decorative geometry only. These coordinates never represent knowledge records. */
export const ARCHIVE_FACE = { width:3.2, height:1.6, depth:.42 }
export const HELIX_RADIUS = 5.1
export function helixPoint(y:number, strand:number, time:number): [number,number,number] {
  const angle=y*.34+strand*Math.PI
  const wave=y*.52-time*.95
  const radius=HELIX_RADIUS+.32*Math.sin(wave)
  return [Math.cos(angle)*radius,y+.22*Math.sin(wave),Math.sin(angle)*radius]
}
