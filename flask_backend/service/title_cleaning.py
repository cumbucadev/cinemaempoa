"""Registry of known title-annotation patterns scraped from cinema sites and
festivals (venue tags, festival names, curated-strand labels, post-screening
event suffixes...), and the function that strips them to produce a clean
movie title.

To add a new pattern: append one TitleCleaningRule to TITLE_CLEANING_RULES
below. Nothing else needs to change.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Pattern, Tuple

_EDGE_JUNK_RE = re.compile(r"^[\s\u200b]+|[\s\u200b]+$")

_MAX_PASSES = 10


def _strip_edges(title: str) -> str:
    """Removes leading/trailing whitespace and zero-width spaces (U+200B)."""
    return _EDGE_JUNK_RE.sub("", title)


@dataclass(frozen=True)
class TitleCleaningRule:
    name: str
    category: str
    pattern: Pattern

    def apply(self, title: str) -> Tuple[str, bool]:
        new_title, n = self.pattern.subn("", title)
        return new_title, n > 0


_STRAND_NAMES = [
    r"Vagalume(?: Férias)?",
    r"AAMICCA",
    r"POADOC",
    r"Reconto",
    r"Black Horror(?: I{1,3})?",
    r"México Macabro(?: I{1,3})?",
    r"Malditos Insetos(?: I{1,3})?",
    r"Shoot or Die(?: I{1,3})?",
    r"Vingancinha",
    r"da Vingança",
    r"Comemorativa(?:\s+\d+\s+Anos)?",
    r"Clássicos",
    r"Especial",
    r"em homenagem a [^:–—-]+",
    r"de curtas",
    r"ABRACCINE",
]
_STRAND_ALTERNATION = "|".join(_STRAND_NAMES)

TITLE_CLEANING_RULES: List[TitleCleaningRule] = [
    # --- prefixes ---
    TitleCleaningRule(
        "cinema_pipe",
        "Prefixo: Cinema |",
        re.compile(r"^\s*Cinema\s*\|\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "fantaspoa",
        "Prefixo: FANTASPOA –",
        re.compile(r"^\s*FA[NS]TASPOA\s*[–—-]\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "sessao_strand",
        "Prefixo: Sessão <mostra>",
        re.compile(
            rf"^\s*Sess[ãa]o\s+(?:{_STRAND_ALTERNATION})\s*[:–—-]\s*", re.IGNORECASE
        ),
    ),
    TitleCleaningRule(
        "projeto_raros",
        "Prefixo: Projeto Raros",
        re.compile(r"^\s*Projeto Raros(?:\s+Especial)?:\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "cinelimite",
        "Prefixo: Cinelimite",
        re.compile(r"^\s*Cinelimite:\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "semana_cinema_gaucho",
        "Prefixo: Semana do Cinema Gaúcho",
        re.compile(r"^\s*Semana do Cinema Gaúcho:\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "mostra_classicos_franceses",
        "Prefixo: Mostra Clássicos Franceses",
        re.compile(r"^\s*Mostra Clássicos Franceses:\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "cine_esquema_novo",
        "Prefixo: CINE ESQUEMA NOVO",
        re.compile(r"^\s*CINE ESQUEMA NOVO:\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "cen_abbrev",
        "Prefixo: CEN -",
        re.compile(r"^\s*CEN\b\s*[-–]\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "malkovich_3x",
        "Prefixo: 3x John Malkovich",
        re.compile(r"^\s*3x John Malkovich:\s*", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "glued_showtime_no_space",
        "Prefixo: horário colado (19h...)",
        re.compile(r"^\d{2}h(?=[A-ZÀ-Ÿ])"),
    ),
    TitleCleaningRule(
        "glued_showtime_dash",
        "Prefixo: horário colado (18h – ...)",
        re.compile(r"^\d{1,2}h\s+[-–—]\s+"),
    ),
    # --- suffixes ---
    # NOTE: the "+"-suffix rules only match when the literal keyword is
    # anchored at the end ($). This is what distinguishes decorative
    # suffixes from legitimate multi-film compilation titles that also
    # contain a bare "+" (e.g. "Ilha das Flores + Saneamento Básico"),
    # which must be left untouched.
    TitleCleaningRule(
        "debate_suffix",
        "Sufixo: + debate",
        re.compile(r"\s*\+\s*debate\s*$", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "conversa_suffix",
        "Sufixo: + conversa",
        re.compile(r"\s*\(?\+\s*conversa\s*\)?\s*$", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "sessao_comentada_suffix",
        "Sufixo: + Sessão Comentada",
        re.compile(r"\s*\+\s*sess[ãa]o comentada\s*$", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "performance_suffix",
        "Sufixo: (+ performance)",
        re.compile(r"\s*\(?\+\s*performance\s*\)?\s*$", re.IGNORECASE),
    ),
    TitleCleaningRule(
        "year_duration_suffix",
        "Sufixo: (ano, duração)",
        re.compile(r"\s*\(\d{4},\s*[^()]*\)\s*$"),
    ),
]

RULE_CATEGORIES: Dict[str, str] = {
    rule.name: rule.category for rule in TITLE_CLEANING_RULES
}


def is_known_junk(title: str) -> bool:
    """Best-effort heuristic for titles that are entirely wrong (technical
    -sheet fragments, director names stored as the title, etc.) rather than
    a real title with an annotation glued on. Used only for reporting -
    these are never auto-stripped, since there's no real title left after
    removing the junk."""
    if re.match(r"^Dire[çc][ãa]o:\s*.+$", title, re.IGNORECASE):
        return True
    if title.count("/") >= 2 and re.search(r"\b(19|20)\d{2}\b", title):
        return True
    if re.match(r"^Classifica[çc][ãa]o\b", title, re.IGNORECASE):
        return True
    if re.match(r"^[A-ZÀ-Ÿ\s]+:\s*$", title):
        return True
    if len(title) <= 3 and not any(ch.isalnum() for ch in title):
        return True
    return False


@dataclass
class CleanTitleResult:
    raw_title: str
    cleaned_title: str
    matched_rules: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.cleaned_title != _strip_edges(self.raw_title)


def clean_title(raw_title: str) -> CleanTitleResult:
    trimmed = _strip_edges(raw_title)

    if is_known_junk(trimmed):
        return CleanTitleResult(
            raw_title=raw_title, cleaned_title=trimmed, matched_rules=[]
        )

    title = trimmed
    matched: List[str] = []
    for _ in range(_MAX_PASSES):
        changed_this_pass = False
        for rule in TITLE_CLEANING_RULES:
            new_title, did_match = rule.apply(title)
            if not did_match:
                continue
            new_title = _strip_edges(new_title)
            if not new_title:
                # refuse to erase the whole title
                continue
            title = new_title
            matched.append(rule.name)
            changed_this_pass = True
        if not changed_this_pass:
            break

    return CleanTitleResult(
        raw_title=raw_title, cleaned_title=title, matched_rules=matched
    )
