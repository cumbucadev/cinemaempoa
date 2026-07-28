function trackShare() {
    if (window.goatcounter && window.goatcounter.count) {
        window.goatcounter.count({
            path: "reels-share",
            title: "Shared movie card",
            event: true,
        });
    }
}

function showShareToast() {
    const toastEl = document.getElementById("reels-share-toast");
    if (!toastEl) return;
    bootstrap.Toast.getOrCreateInstance(toastEl).show();
}

document.addEventListener("click", (event) => {
    const button = event.target.closest('[data-function="share"]');
    if (!button) return;

    const shareData = {
        title: button.dataset.movieTitle,
        text: button.dataset.shareText,
        url: button.dataset.shareUrl,
    };

    if (navigator.share) {
        navigator.share(shareData).then(trackShare).catch(() => {});
        return;
    }

    navigator.clipboard.writeText(shareData.url).then(() => {
        trackShare();
        showShareToast();
    });
});
