// The one door for writing query params. The app's URL carries two kinds of
// state — the `#view` hash picks the page, query params hold shareable state
// like `?api=` — and a param write done by hand tends to drop one or the
// other. Routing every write through here keeps sibling params and the hash
// intact, so a refresh or a shared link lands exactly where the user was.
export function setUrlParam(key: string, value: string | null): void {
  const params = new URLSearchParams(window.location.search);
  if (value === null) {
    params.delete(key);
  } else {
    params.set(key, value);
  }
  const query = params.toString();
  // pathname is spelled out so deleting the last param drops the "?" cleanly.
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`,
  );
}
