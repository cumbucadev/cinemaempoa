let shownAddedHint = false;

function setWantToWatchState(button, wanted) {
    button.dataset.wanted = wanted ? "true" : "false";
    button.setAttribute("aria-pressed", wanted ? "true" : "false");
    button.setAttribute(
        "aria-label",
        wanted ? "Remover dos meus filmes" : "Adicionar aos meus filmes"
    );
    button.querySelector("span").textContent = wanted ? "★" : "☆";
}

function showAddedToast() {
    const toastEl = document.getElementById("reels-wtw-toast");
    if (!toastEl) return;
    bootstrap.Toast.getOrCreateInstance(toastEl).show();
}

document.addEventListener("click", (event) => {
    const button = event.target.closest('[data-function="want-to-watch"]');
    if (!button || button.disabled) return;

    const wasWanted = button.dataset.wanted === "true";
    setWantToWatchState(button, !wasWanted);
    button.classList.add("reels-want-to-watch-pop");
    button.disabled = true;

    fetch(`/movie/${button.dataset.movieId}/want-to-watch`, { method: "POST" })
        .then((response) => {
            if (!response.ok) throw new Error("want-to-watch request failed");
            return response.json();
        })
        .then((data) => {
            setWantToWatchState(button, data.wanted);
            if (data.wanted) {
                if (window.goatcounter) {
                    window.goatcounter.count({
                        path: window.location.pathname,
                        title: "Marked movie as want-to-watch",
                        event: true,
                    });
                }
                if (!shownAddedHint) {
                    shownAddedHint = true;
                    showAddedToast();
                }
            }
        })
        .catch((error) => {
            console.error("Error:", error);
            setWantToWatchState(button, wasWanted);
        })
        .finally(() => {
            button.disabled = false;
            setTimeout(() => button.classList.remove("reels-want-to-watch-pop"), 300);
        });
});
