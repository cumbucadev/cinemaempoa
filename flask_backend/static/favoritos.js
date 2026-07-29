document.addEventListener("click", (event) => {
  const button = event.target.closest('[data-function="want-to-watch"]');
  if (!button) return;
  const tile = button.closest(".favorites-tile");
  if (!tile) return;
  // reels-want-to-watch.js's own handler (loaded before this file, registered
  // first) does the fetch/toggle and disables/re-enables the button around
  // the request. We key off `disabled` going back to false rather than
  // `data-wanted` alone, since data-wanted flips optimistically and
  // synchronously before this observer even attaches - watching `disabled`
  // too means we only act once the request has actually settled (success OR
  // failure), so a failed request correctly leaves the tile in place instead
  // of removing it before the server confirms.
  const observer = new MutationObserver(() => {
    if (button.disabled) return; // request still in flight
    if (button.dataset.wanted === "false") tile.remove();
    observer.disconnect(); // terminal in both outcomes - success or failure
  });
  observer.observe(button, { attributes: true, attributeFilter: ["data-wanted", "disabled"] });
});
