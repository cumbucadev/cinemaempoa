const reelsCards = document.querySelectorAll(".reels-feed .reels-card");

if (reelsCards.length > 1) {
    const reelsScrollObserver = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                if (window.goatcounter) {
                    window.goatcounter.count({
                        path: window.location.pathname,
                        title: "Reels scrolled past first card",
                        event: true,
                    });
                }
                reelsScrollObserver.disconnect();
            });
        },
        { threshold: 0.5 }
    );
    reelsScrollObserver.observe(reelsCards[1]);
}
