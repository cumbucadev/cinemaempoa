from flask_backend.service.title_cleaning import clean_title, is_known_junk


class TestCleanTitlePrefixes:
    def test_cinema_pipe(self):
        result = clean_title("Cinema | Oldboy")
        assert result.cleaned_title == "Oldboy"
        assert result.matched_rules == ["cinema_pipe"]

    def test_cinema_pipe_double_space(self):
        result = clean_title(" Cinema |  Orféa Apaixonada")
        assert result.cleaned_title == "Orféa Apaixonada"

    def test_fantaspoa(self):
        result = clean_title("FANTASPOA – GAUA")
        assert result.cleaned_title == "GAUA"
        assert result.matched_rules == ["fantaspoa"]

    def test_fantaspoa_typo(self):
        result = clean_title("FASTASPOA – Cielo")
        assert result.cleaned_title == "Cielo"
        assert result.matched_rules == ["fantaspoa"]

    def test_sessao_strand_colon(self):
        result = clean_title("Sessão Vagalume: A História Sem Fim")
        assert result.cleaned_title == "A História Sem Fim"
        assert result.matched_rules == ["sessao_strand"]

    def test_sessao_strand_all_caps_dash(self):
        result = clean_title("SESSÃO VAGALUME – Toy Story 2")
        assert result.cleaned_title == "Toy Story 2"
        assert result.matched_rules == ["sessao_strand"]

    def test_sessao_strand_poadoc(self):
        result = clean_title("Sessão POADOC: Copan")
        assert result.cleaned_title == "Copan"

    def test_sessao_strand_roman_numeral(self):
        result = clean_title("Sessão Black Horror I: Blácula, o Vampiro Negro")
        assert result.cleaned_title == "Blácula, o Vampiro Negro"

    def test_projeto_raros(self):
        result = clean_title("Projeto Raros: Deadlock")
        assert result.cleaned_title == "Deadlock"

    def test_projeto_raros_especial(self):
        result = clean_title("Projeto Raros Especial: Território Inimigo")
        assert result.cleaned_title == "Território Inimigo"

    def test_cinelimite(self):
        result = clean_title("Cinelimite: A Onda de Filmes Queer em Super-8 da Paraíba")
        assert result.cleaned_title == "A Onda de Filmes Queer em Super-8 da Paraíba"

    def test_semana_cinema_gaucho(self):
        result = clean_title("Semana do Cinema Gaúcho: Sem Saída")
        assert result.cleaned_title == "Sem Saída"

    def test_mostra_classicos_franceses(self):
        result = clean_title("Mostra Clássicos Franceses: As Coisas da Vida")
        assert result.cleaned_title == "As Coisas da Vida"

    def test_cine_esquema_novo(self):
        result = clean_title("CINE ESQUEMA NOVO: MOSTRA COMPETITIVA BRASIL 05")
        assert result.cleaned_title == "MOSTRA COMPETITIVA BRASIL 05"

    def test_cen_abbrev(self):
        result = clean_title("CEN - MOSTRA OUTROS ESQUEMAS 1")
        assert result.cleaned_title == "MOSTRA OUTROS ESQUEMAS 1"

    def test_cen_abbrev_does_not_match_unrelated_words(self):
        result = clean_title("Cendrillon")
        assert result.cleaned_title == "Cendrillon"
        assert result.matched_rules == []

    def test_malkovich_3x(self):
        result = clean_title("3x John Malkovich: Ligações Perigosas")
        assert result.cleaned_title == "Ligações Perigosas"

    def test_glued_showtime_no_space(self):
        result = clean_title("19hA sexta fase do Pentágono")
        assert result.cleaned_title == "A sexta fase do Pentágono"

    def test_glued_showtime_dash(self):
        result = clean_title("18h – 15 MOSTRA DE DIREITOS HUMANOS")
        assert result.cleaned_title == "15 MOSTRA DE DIREITOS HUMANOS"


class TestCleanTitleSuffixes:
    def test_debate_suffix(self):
        result = clean_title("No Céu da Pátria Nesse Instante + debate")
        assert result.cleaned_title == "No Céu da Pátria Nesse Instante"
        assert result.matched_rules == ["debate_suffix"]

    def test_debate_suffix_capitalized(self):
        result = clean_title("Ato Noturno + Debate")
        assert result.cleaned_title == "Ato Noturno"

    def test_conversa_suffix_with_parens(self):
        result = clean_title("KICKFLIP (+ Conversa)")
        assert result.cleaned_title == "KICKFLIP"

    def test_conversa_suffix_lowercase_no_parens(self):
        result = clean_title("Cinema | KICKFLIP (+ conversa)")
        assert result.cleaned_title == "KICKFLIP"

    def test_conversa_suffix_trailing_space_inside_parens(self):
        result = clean_title("Cinema | Eu, Mamâe e Os Meninos (+ conversa )")
        assert result.cleaned_title == "Eu, Mamâe e Os Meninos"

    def test_sessao_comentada_suffix(self):
        result = clean_title("FANTASPOA – Sacrifícios + Sessão Comentada")
        assert result.cleaned_title == "Sacrifícios"

    def test_performance_suffix(self):
        result = clean_title("Cinema | A SORRIDENTE MADAME BEUDET (+ performance)")
        assert result.cleaned_title == "A SORRIDENTE MADAME BEUDET"

    def test_year_duration_suffix(self):
        result = clean_title("Eu sou Raiz (2022, 7')")
        assert result.cleaned_title == "Eu sou Raiz"

    def test_year_duration_suffix_with_seconds_and_quote(self):
        result = clean_title("Ainda Há Moradores Aqui (2025, 42'50\")")
        assert result.cleaned_title == "Ainda Há Moradores Aqui"


class TestCleanTitleStackedAnnotations:
    def test_stacked_prefix_and_suffix(self):
        result = clean_title("Cinema | Sessão Vagalume: Foo + debate")
        assert result.cleaned_title == "Foo"
        assert set(result.matched_rules) == {
            "cinema_pipe",
            "sessao_strand",
            "debate_suffix",
        }


class TestCleanTitleAmbiguousPlus:
    def test_compilation_title_untouched(self):
        result = clean_title("Ilha das Flores + Saneamento Básico")
        assert result.cleaned_title == "Ilha das Flores + Saneamento Básico"
        assert result.matched_rules == []

    def test_another_compilation_title_untouched(self):
        result = clean_title("Vicious + Uma Pistola para Ringo")
        assert result.cleaned_title == "Vicious + Uma Pistola para Ringo"
        assert result.matched_rules == []


class TestCleanTitleWhitespace:
    def test_trims_whitespace_with_no_pattern_match(self):
        result = clean_title("  Oldboy  ")
        assert result.cleaned_title == "Oldboy"
        assert result.matched_rules == []

    def test_trims_zero_width_space(self):
        result = clean_title("​Oldboy​")
        assert result.cleaned_title == "Oldboy"


class TestCleanTitleJunk:
    def test_direcao_title_left_untouched_by_clean_title(self):
        result = clean_title("Direção: Antonio Pitanga")
        assert result.cleaned_title == "Direção: Antonio Pitanga"
        assert result.matched_rules == []

    def test_technical_sheet_fragment_left_untouched(self):
        result = clean_title("Brasil/ Documentário/ 2022/")
        assert result.cleaned_title == "Brasil/ Documentário/ 2022/"

    def test_classificacao_left_untouched(self):
        result = clean_title("Classificação Livre")
        assert result.cleaned_title == "Classificação Livre"

    def test_all_caps_label_left_untouched(self):
        result = clean_title("ESTREIAS:")
        assert result.cleaned_title == "ESTREIAS:"

    def test_lone_symbol_left_untouched(self):
        result = clean_title("→")
        assert result.cleaned_title == "→"

    def test_is_known_junk_flags_expected_titles(self):
        assert is_known_junk("Direção: Antonio Pitanga") is True
        assert is_known_junk("Brasil/ Documentário/ 2022/") is True
        assert is_known_junk("Classificação Livre") is True
        assert is_known_junk("ESTREIAS:") is True
        assert is_known_junk("→") is True

    def test_is_known_junk_does_not_flag_real_titles(self):
        assert is_known_junk("Oldboy") is False
        assert is_known_junk("O AGENTE SECRETO") is False


class TestCleanTitleIdempotency:
    def test_cleaning_a_cleaned_title_is_a_no_op(self):
        titles = [
            "Cinema | Sessão Vagalume: Foo + debate",
            "FANTASPOA – Sacrifícios + Sessão Comentada",
            "KICKFLIP (+ Conversa)",
            "Ilha das Flores + Saneamento Básico",
            "  Oldboy  ",
        ]
        for title in titles:
            once = clean_title(title).cleaned_title
            twice = clean_title(once).cleaned_title
            assert once == twice
