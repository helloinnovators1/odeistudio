/** Tracks async UI requests and invalidates results from obsolete selections. */
export class RequestGeneration {
  private generation = 0;

  begin(): number {
    this.generation += 1;
    return this.generation;
  }

  invalidate(): void {
    this.generation += 1;
  }

  isCurrent(generation: number): boolean {
    return Number.isSafeInteger(generation) && generation === this.generation;
  }
}
