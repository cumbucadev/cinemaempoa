function setWantToWatchState(button, wanted) {
    button.dataset.wanted = wanted ? "true" : "false";
    button.setAttribute("aria-pressed", wanted ? "true" : "false");
    button.setAttribute(
        "aria-label",
        wanted ? "Remover dos meus filmes" : "Adicionar aos meus filmes"
    );
    button.querySelector("span").textContent = wanted ? "★" : "☆";
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
