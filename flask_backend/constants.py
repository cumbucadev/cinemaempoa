CINEMA_SHORT_NAMES = {
    "capitolio": "Capitólio",
    "sala-redencao": "Sala Redenção",
    "cinebancarios": "CineBancários",
    "paulo-amorim": "Paulo Amorim",
    "cine-cinco": "Cine Cinco",
}

CINEMA_COLORS = {
    "capitolio": "#911eb4",
    "sala-redencao": "#000075",
    "cinebancarios": "#9A6324",
    "paulo-amorim": "#469990",
    "cine-cinco": "#e6194b",
}

DEFAULT_CINEMA_COLOR = "#6c757d"

# request-derived _external=True is unreliable behind this app's
# nginx/traefik setup (no ProxyFix, no Host-header rewrite) — see
# scripts/sitemap.py for the same workaround in a different context.
CANONICAL_BASE_URL = "https://cinemaempoa.com.br"
