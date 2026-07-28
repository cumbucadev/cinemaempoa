document.addEventListener("click", (event) => {
  if (event.target.closest('[data-function="want-to-watch"]')) {
    event.preventDefault(); // suppress <summary>'s native open/close toggle
  }
});

document.addEventListener("click", (event) => {
  const button = event.target.closest('[data-function="want-to-watch"]');
  if (!button) return;
  const tile = button.closest(".favorites-tile");
  if (!tile) return;
  // reels-want-to-watch.js's own handler (loaded before this file) does the
  // fetch/toggle; once it resolves, data-wanted becomes "false" - a page
  // that only lists favorites shouldn't keep showing an unfavorited tile.
  const observer = new MutationObserver(() => {
    if (button.dataset.wanted === "false") {
      tile.remove();
      observer.disconnect();
    }
  });
  observer.observe(button, { attributes: true, attributeFilter: ["data-wanted"] });
});

document.querySelectorAll('[data-function="publish"]').forEach((btn) => {
  btn.addEventListener("click", () => {
    fetch(`/screening/${btn.dataset.screeningId}/publish`, { method: "POST" })
      .then((response) => { if (response.ok) window.location.reload(); })
      .catch((error) => console.error("Error:", error));
  });
});

document.querySelectorAll('[data-function="delete"]').forEach((btn) => {
  btn.addEventListener("click", () => {
    fetch(`/screening/${btn.dataset.screeningId}/delete`, { method: "POST" })
      .then((response) => { if (response.ok) window.location.reload(); })
      .catch((error) => console.error("Error:", error));
  });
});
