(function () {
    function downloadImage(imageUrl) {
        // Se a URL é relativa, adiciona o domínio
        const fullUrl = imageUrl.startsWith("http")
            ? imageUrl
            : window.location.origin + imageUrl;

        fetch(fullUrl)
            .then((response) => response.blob())
            .then((blob) => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                // Extrai o nome do arquivo da URL
                const urlParts = imageUrl.split("/");
                const filename = urlParts[urlParts.length - 1] || "poster.jpg";
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch((error) => {
                console.error("Erro ao baixar imagem:", error);
                // Fallback: abre a imagem em nova aba
                window.open(fullUrl, "_blank");
            });
    }

    function markImageAsLoaded(img) {
        if (!img || !img.classList) {
            return;
        }

        img.classList.add("is-loaded");
    }

    function bindPosterLoadState(img) {
        if (!img) {
            return;
        }

        if (img.complete && img.naturalWidth > 0) {
            markImageAsLoaded(img);
            return;
        }

        img.addEventListener(
            "load",
            function () {
                markImageAsLoaded(img);
            },
            { once: true }
        );
    }

    function initPosterDownloadButtons(root = document) {
        const images = root.querySelectorAll(
            ".poster-download-anchor img, .image-container .poster-image"
        );

        images.forEach(bindPosterLoadState);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initPosterDownloadButtons();
        });
    } else {
        initPosterDownloadButtons();
    }

    window.downloadImage = downloadImage;
    window.initPosterDownloadButtons = initPosterDownloadButtons;
})();
