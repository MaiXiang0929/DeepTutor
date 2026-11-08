export class ProximityWindow {
  private readings: { at: number; strength: number }[] = [];

  add(strength: number, at: number): boolean {
    if (strength <= -42 || (this.readings.length && at - this.readings[this.readings.length - 1].at > 600)) {
      this.readings = [];
      if (strength <= -42) return false;
    }
    this.readings = this.readings.filter(reading => at - reading.at <= 800);
    this.readings.push({at, strength});
    const average = this.readings.reduce((sum, reading) => sum + reading.strength, 0) / this.readings.length;
    return this.readings.length >= 2 && at - this.readings[0].at >= 400 && average > -42;
  }
}

export function mayInitiateBlePair(localId: string, otherId: string): boolean {
  return /^[a-f0-9]{32}$/.test(otherId) && localId < otherId;
}
