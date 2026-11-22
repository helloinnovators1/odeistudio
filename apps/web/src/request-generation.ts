/**
 * Tracks the newest asynchronous request so stale completions cannot overwrite
 * state belonging to a newer organization, project, or authenticated session.
 */
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
    return generation === this.generation;
  }
}
