/** Short, human label for a template package (e.g. for a badge). */
export function packageLabel(pkg: string): string {
  if (pkg.startsWith("backend")) return "backend";
  if (pkg.startsWith("text_adventure_games")) return "engine";
  return pkg;
}
