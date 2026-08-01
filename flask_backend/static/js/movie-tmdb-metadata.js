function showError(message) {
    const errorDiv = document.getElementById("tmdb-error");
    errorDiv.textContent = message;
    errorDiv.classList.remove("d-none");
}

function clearError() {
    const errorDiv = document.getElementById("tmdb-error");
    errorDiv.textContent = "";
    errorDiv.classList.add("d-none");
}

function parseJsonResponse(response) {
    return response.json().then((data) => ({
        ok: response.ok,
        data: data
    }));
}

function createCandidateCard(candidate) {
    const col = document.createElement("div");
    col.className = "col";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-link p-0 text-start w-100";
    btn.addEventListener("click", function() {
        linkMovie(candidate.tmdb_id);
    });

    if (candidate.poster_url) {
        const img = document.createElement("img");
        img.src = candidate.poster_url;
        img.className = "img-fluid rounded mb-1";
        img.alt = candidate.title || "";
        btn.appendChild(img);
    }

    const title = document.createElement("div");
    title.textContent = candidate.title || "(sem título)";
    btn.appendChild(title);

    if (candidate.original_title && candidate.original_title !== candidate.title) {
        const originalTitle = document.createElement("div");
        originalTitle.className = "text-muted small";
        originalTitle.textContent = candidate.original_title;
        btn.appendChild(originalTitle);
    }

    if (candidate.release_year) {
        const year = document.createElement("div");
        year.className = "text-muted small";
        year.textContent = candidate.release_year;
        btn.appendChild(year);
    }

    col.appendChild(btn);
    return col;
}

function fetchTmdbCandidates() {
    const query = document.getElementById("tmdb-query").value;
    const resultsDiv = document.getElementById("tmdb-results");
    resultsDiv.innerHTML = "";

    if (query.trim().length < 2) {
        return;
    }

    fetch(`/admin/movies/${movieId}/tmdb-search?q=${encodeURIComponent(query)}`)
        .then(parseJsonResponse)
        .then(({
            ok,
            data
        }) => {
            if (!ok) {
                showError(data.error || "Erro ao buscar no TMDB.");
                return;
            }
            clearError();
            resultsDiv.innerHTML = "";
            if (data.length === 0) {
                resultsDiv.textContent = "Nenhum resultado encontrado.";
                return;
            }
            data.forEach((candidate) => {
                resultsDiv.appendChild(createCandidateCard(candidate));
            });
        })
        .catch(() => {
            showError("Falha de conexão ao buscar no TMDB. Tente novamente.");
        });
}

function updateMetadataDisplay(movie) {
    document.getElementById("field-original_title").textContent = movie.original_title || "—";
    document.getElementById("field-release_year").textContent = movie.release_year || "—";
    document.getElementById("field-original_language").textContent = movie.original_language || "—";
    document.getElementById("field-directors").textContent = movie.directors.join(", ") || "—";
    document.getElementById("field-genres").textContent = movie.genres.join(", ") || "—";
    document.getElementById("field-collection").textContent = movie.collection || "—";
    let tmdbStatus = "Não vinculado";
    if (movie.tmdb_id) {
        tmdbStatus = `Vinculado ao TMDB #${movie.tmdb_id}`;
    } else if (movie.tmdb_excluded) {
        tmdbStatus = "Não encontrado no TMDB (marcado manualmente)";
    }
    document.getElementById("field-tmdb-status").textContent = tmdbStatus;
}

function linkMovie(tmdbId) {
    fetch(`/admin/movies/${movieId}/tmdb-link`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                tmdb_id: tmdbId
            }),
        })
        .then(parseJsonResponse)
        .then(({
            ok,
            data
        }) => {
            if (!ok) {
                showError(data.error || "Erro ao vincular filme ao TMDB.");
                return;
            }
            clearError();
            updateMetadataDisplay(data);
            document.getElementById("tmdb-results").innerHTML = "";
        })
        .catch(() => {
            showError("Falha de conexão ao vincular filme. Tente novamente.");
        });
}

const unlinkBtn = document.getElementById("unlink-btn");
if (unlinkBtn) {
    unlinkBtn.addEventListener("click", function() {
        fetch(`/admin/movies/${movieId}/tmdb-unlink`, {
                method: "POST"
            })
            .then(parseJsonResponse)
            .then(({
                ok,
                data
            }) => {
                if (!ok) {
                    showError(data.error || "Erro ao remover vínculo com o TMDB.");
                    return;
                }
                clearError();
                updateMetadataDisplay(data);
                unlinkBtn.remove();
            })
            .catch(() => {
                showError("Falha de conexão ao remover vínculo. Tente novamente.");
            });
    });
}
