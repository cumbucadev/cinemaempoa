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
    window.downloadImage = downloadImage;
})();
