import os
import sys
import unicodedata
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, os.path.join(os.getcwd()))

from bs4 import BeautifulSoup

from scrapers.cinebancarios import CineBancarios


class TestCineBancarios:
    @pytest.mark.parametrize(
        "input_xml_dir,expected_raw_xml",
        [
            (
                "tests/files/files_cinebancarios/2023-08-27",
                """<description>&lt;p&gt;&lt;b&gt;&lt;i&gt;Filme de Kleber Mendonça Filho, diretor de Aquarius e Bacurau, abriu o Festival de Gramado deste ano; O Acidente, longa de Bruno Carboni, ganhou três Kikitos no Festival&lt;/i&gt;&lt;/b&gt;&lt;/p&gt;&lt;p&gt;Dois destaques da 76ª edição do Festival de Cannes estreiam no
CineBancários no dia 24 de agosto. O documentário “Retratos
Fantasmas”, quinto longa-metragem do cineasta e roteirista Kleber
Mendonça Filho (“O Som ao Redor”, “Aquarius”, “Bacurau”)
divide a programação com &quot;O Acidente&quot;, de Bruno Carboni.&lt;/p&gt;&lt;p&gt;
&lt;/p&gt;&lt;p align=&quot;justify&quot; style=&quot;line-height: 100%; margin-bottom: 0cm;&quot;&gt;&lt;b&gt;Retratos
Fantasmas&lt;/b&gt;&lt;/p&gt;&lt;p align=&quot;justify&quot; style=&quot;line-height: 100%; margin-bottom: 0cm;&quot;&gt;&lt;/p&gt;&lt;div class=&quot;separator&quot; style=&quot;clear: both; text-align: center;&quot;&gt;&lt;a href=&quot;https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEigoP0TGzHrov-hyQ1BRiuu4Y5mVmfI8LdeV2YtRmryXuaL8Fnyhq-xTvxdsEGcfZPrQrBkpS363aFUIOcDLhL6gzDt6MB2fKz4ywhoLc_78B8SpuSds7t9RNiYa544Xd4oHLa_LRNmwW-5AOcMn7Yaz3OSYlc7Zx3sk5dn4yxk1ziGBDYJB53T2oDEh7A/s2665/RetratosFantasmas_64x94_web.png&quot; imageanchor=&quot;1&quot; style=&quot;clear: left; float: left; margin-bottom: 1em; margin-right: 1em;&quot;&gt;&lt;img border=&quot;0&quot; data-original-height=&quot;2665&quot; data-original-width=&quot;1814&quot; height=&quot;320&quot; src=&quot;https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEigoP0TGzHrov-hyQ1BRiuu4Y5mVmfI8LdeV2YtRmryXuaL8Fnyhq-xTvxdsEGcfZPrQrBkpS363aFUIOcDLhL6gzDt6MB2fKz4ywhoLc_78B8SpuSds7t9RNiYa544Xd4oHLa_LRNmwW-5AOcMn7Yaz3OSYlc7Zx3sk5dn4yxk1ziGBDYJB53T2oDEh7A/s320/RetratosFantasmas_64x94_web.png&quot; width=&quot;218&quot; /&gt;&lt;/a&gt;&lt;/div&gt;&lt;p&gt;&lt;/p&gt;&lt;p align=&quot;justify&quot;&gt;Fruto de sete anos de trabalho e pesquisa,
filmagens e montagem, “Retratos Fantasmas” tem o centro da cidade
do Recife como personagem principal, sendo um espaço histórico e
humano, revisitado através dos grandes cinemas que serviram como
espaços de convívio durante o século XX. Foram lugares de sonho e
de indústria, e a relação das pessoas com esse universo é um
marcador de tempo para as mudanças dos costumes em sociedade.&lt;/p&gt;
&lt;p align=&quot;justify&quot;&gt;“Palácios de cinema em centros de cidades são
comuns a muitos outros lugares do mundo, mas ocorre que eu sou
pernambucano, recifense, e parti para mostrar essa geografia da
cidade a partir de um ponto de vista pessoal”, aponta Kleber.
“Recife é também uma cidade que ainda desfruta de um cinema
espetacular como o São Luiz, um palácio de 1952. Hoje, são poucas
as cidades no mundo que ainda sabem o que isso representa”, comenta
o diretor, em relação aos cinemas de rua.&lt;/p&gt;
&lt;p align=&quot;justify&quot;&gt;Cerca de 60% do documentário é composto por
material de arquivo, com fotografias e imagens em movimento
encontradas em acervos pessoais, na produção pernambucana de
cinema, de televisão e de instituições como a Cinemateca
Brasileira, o Centro Técnico Audiovisual (CTAV) e a Fundação
Joaquim Nabuco.&lt;/p&gt;
&lt;p align=&quot;justify&quot;&gt;&lt;b&gt;O Acidente&lt;/b&gt;&lt;/p&gt;&lt;p align=&quot;justify&quot;&gt;&lt;/p&gt;&lt;div class=&quot;separator&quot; style=&quot;clear: both; text-align: center;&quot;&gt;&lt;a href=&quot;https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhgGzJBAOkuVjjTKZWD71-UYAA3f-MUXhVX25D5RbL3nFli9kOWlK2ToK1YE8FglIbzmYyvCO7aEzeWWWfzNPLcAzb0Nm3Q8KJcH2f_oUG3ZtOYTio5dB5Rh24QzZxYhyhYr4Eh2i0Jm03n137foDD3xS6HtiJxvFWYCOAQ-5G_2WH1FIhnpdnSN-HGnu4/s9933/OACIDENTE_POSTER.jpg&quot; imageanchor=&quot;1&quot; style=&quot;clear: left; float: left; margin-bottom: 1em; margin-right: 1em;&quot;&gt;&lt;img border=&quot;0&quot; data-original-height=&quot;9933&quot; data-original-width=&quot;7016&quot; height=&quot;320&quot; src=&quot;https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhgGzJBAOkuVjjTKZWD71-UYAA3f-MUXhVX25D5RbL3nFli9kOWlK2ToK1YE8FglIbzmYyvCO7aEzeWWWfzNPLcAzb0Nm3Q8KJcH2f_oUG3ZtOYTio5dB5Rh24QzZxYhyhYr4Eh2i0Jm03n137foDD3xS6HtiJxvFWYCOAQ-5G_2WH1FIhnpdnSN-HGnu4/s320/OACIDENTE_POSTER.jpg&quot; width=&quot;226&quot; /&gt;&lt;/a&gt;&lt;/div&gt;&lt;span style=&quot;text-align: left;&quot;&gt;&lt;p align=&quot;justify&quot;&gt;&lt;span style=&quot;text-align: left;&quot;&gt;&lt;br /&gt;&lt;/span&gt;&lt;/p&gt;A ciclista Joana é vítima de um atropelamento.
Ela foi carregada no capô de um carro após antagonizar com uma
motorista que a cortou. A jovem sai ilesa e decide esconder o
ocorrido de sua parceira, Cecília, temendo que isso afete os planos
do casal. Porém, um vídeo viral aparece online, obrigando-a a
prestar queixa na polícia. Relutante, a dupla entra na vida de
Elaine, a motorista, seu ex-marido Cléber e seu filho Maicon, um
introvertido cineasta iniciante. Esta é a trama de &quot;O
Acidente&quot;, de Bruno Carboni, vencedor do prêmio de Melhor
Roteiro no Festival de Beijing (China).&lt;/span&gt;&lt;p&gt;&lt;/p&gt;
&lt;p align=&quot;justify&quot;&gt;Em um cruzamento qualquer, tudo por mudar: &quot;O
Acidente&quot; explora uma ligação nascida da animosidade de uma
disputa de trânsito entre Joana (Carol Martins), e Elaine (Gabriela
Greco). O filho da última, Maicon (Luis Felipe Xavier), foi quem
registrou o viral com a câmera de seu celular e postou online. Joana
divide um apartamento com Cecília (Carina Sehn), sua sempre
atenciosa namorada. O casal tem grandes planos para o futuro. Também
participa da história Cléber (Marcello Crawshawn), pai de Maicon,
que luta pela guarda do filho na justiça.&lt;/p&gt;
&lt;p align=&quot;justify&quot;&gt;Drama intimista, &quot;O Acidente&quot; olha para
dentro de Joana, enquanto reflete sobre o desejo de formar uma
família. O incidente opõe duas delas: uma homoafetiva, formada pela
ciclista e sua namorada, e de outro, Elaine e Cléber, um casal em
processo de separação. O pai idealiza colocar o filho, um menino
sensível com aspirações artísticas, em uma escola militar. Os
contrastes também entram na rota de colisão. Desenvolvido no Torino
Script Lab, o roteiro foi escrito a quatro mãos pelo diretor e por
Marcela Bordin. Em sua carreira em festivais, o filme ainda teve
exibições no Olhar de Cinema, Festival de Torino (Itália),
Amsterdam LGBTQ+ (Holanda) e em breve no Queer Lisboa (Portugal). 
&lt;/p&gt;
&lt;p align=&quot;justify&quot;&gt;&lt;br /&gt;
&lt;span style=&quot;font-family: Liberation Serif, serif;&quot;&gt;&lt;br /&gt;
&lt;/span&gt;&lt;u&gt;&lt;b&gt;ESTREIA&lt;/b&gt;&lt;/u&gt;&lt;/p&gt;
&lt;p&gt;RETRATOS FANTASMAS&lt;/p&gt;
&lt;p&gt;Brasil/Documentário/2022/ 93min.&lt;/p&gt;
&lt;p&gt;Direção: Kleber Mendonça Filho&lt;/p&gt;
&lt;p&gt;Sinopse: O filme tem o centro da cidade do Recife como personagem
principal, sendo um espaço histórico e humano, revisitado através
dos grandes cinemas que serviram como espaços de convívio durante o
século XX. Foram lugares de sonho e de indústria, e a relação das
pessoas com esse universo é um marcador de tempo para as mudanças
dos costumes em sociedade.&lt;/p&gt;
&lt;p&gt;&lt;b&gt;O ACIDENTE&lt;/b&gt;&lt;/p&gt;
&lt;p&gt;Drama | 95 min. | Brasil 
&lt;/p&gt;
&lt;p&gt;Sinopse: A ciclista Joana é vítima de um atropelamento. Ela foi
carregada no capô de um carro após antagonizar com uma motorista
que a cortou. A jovem sai ilesa e decide esconder o ocorrido de sua
parceira, Cecília, temendo que isso afete os planos do casal. Porém,
um vídeo viral aparece online, obrigando-a a prestar queixa na
polícia. Relutante, a dupla entra na vida de Elaine, a motorista,
seu ex-marido Cléber e seu filho Maicon, um introvertido cineasta
iniciante. 
&lt;/p&gt;
&lt;p&gt;Elenco: Carol Martins (Joana), Carina Sehn (Cecília), Luis Felipe
Xavier (Maicon), Gabriela Greco (Elaine) e Marcello Crawshawn
(Cléber)&lt;/p&gt;
&lt;p&gt;&lt;b&gt;HORÁRIOS&lt;/b&gt;&lt;b&gt; &lt;/b&gt;&lt;b&gt;CINEBANCÁRIOS &lt;/b&gt;
&lt;/p&gt;
&lt;p&gt;24 a 30 de agosto&lt;/p&gt;
&lt;p style=&quot;line-height: 100%; margin-bottom: 0cm;&quot;&gt;15h: RETRATOS
FANTASMAS&lt;/p&gt;
&lt;p style=&quot;line-height: 100%; margin-bottom: 0cm;&quot;&gt;17h: O ACIDENTE&lt;/p&gt;
&lt;p style=&quot;line-height: 100%; margin-bottom: 0cm;&quot;&gt;19h: RETRATOS
FANTASMAS&lt;/p&gt;
&lt;p style=&quot;line-height: 100%; margin-bottom: 0cm;&quot;&gt;&lt;i style=&quot;font-family: &amp;quot;Liberation Serif&amp;quot;, serif;&quot;&gt;*Não há sessões nas
segundas-feiras&lt;/i&gt;&lt;/p&gt;
&lt;b&gt;&lt;br /&gt;Ingressos &lt;/b&gt;&lt;br /&gt;&lt;br /&gt;Os ingressos podem ser adquiridos a R$ 12 na bilheteria do CineBancários. Idosos (as), estudantes, bancários (as), jornalistas sindicalizados (as), portadores de ID Jovem e pessoas com deficiência pagam R$ 6. São aceitos cartões nas bandeiras Banricompras, Visa, MasterCard e Elo.&lt;b&gt;&lt;i&gt;&lt;/i&gt;&lt;/b&gt;&lt;p&gt;&lt;/p&gt;</description>""",
            ),
            (
                "tests/files/files_cinebancarios/2023-09-01",
                """<description>&lt;p&gt;&lt;span style=&quot;color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 20px;&quot;&gt;&lt;b&gt;&lt;i&gt;Retratos fantasmas, de Kleber Mendonça Filho, e O Acidente, de Bruno Carboni, seguem em cartaz&lt;/i&gt;&lt;/b&gt;&lt;/span&gt;&lt;/p&gt;&lt;p&gt;&lt;span style=&quot;color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 20px;&quot;&gt;&lt;b&gt;&lt;/b&gt;&lt;/span&gt;&lt;/p&gt;&lt;div class=&quot;separator&quot; style=&quot;clear: both; text-align: center;&quot;&gt;&lt;b&gt;&lt;a href=&quot;https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEi9cpROrUKiDb1_eR-KUAuoS42x3fvPdTjtKeOqnIFvpExIVGRqauZhotxyQSFSNNSfV-5BiOj86-6PsBn4Hj7MzM0ctuLDuSonHIIPaP93r1S3Shqc8a8qwGJ-Hu3GwPrXo07ffnZMBZRLBhngnCMgC_n9QdfsvC_Cko6o-_7oNndqB2E9y1nRS3mc33w/s2560/POVAF2.jpg&quot; imageanchor=&quot;1&quot; style=&quot;margin-left: 1em; margin-right: 1em;&quot;&gt;&lt;img border=&quot;0&quot; data-original-height=&quot;1440&quot; data-original-width=&quot;2560&quot; height=&quot;225&quot; src=&quot;https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEi9cpROrUKiDb1_eR-KUAuoS42x3fvPdTjtKeOqnIFvpExIVGRqauZhotxyQSFSNNSfV-5BiOj86-6PsBn4Hj7MzM0ctuLDuSonHIIPaP93r1S3Shqc8a8qwGJ-Hu3GwPrXo07ffnZMBZRLBhngnCMgC_n9QdfsvC_Cko6o-_7oNndqB2E9y1nRS3mc33w/w400-h225/POVAF2.jpg&quot; width=&quot;400&quot; /&gt;&lt;/a&gt;&lt;/b&gt;&lt;/div&gt;&lt;b&gt;&lt;i&gt;&lt;br /&gt;&lt;/i&gt;&lt;/b&gt;&lt;p&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;No dia 31 de agosto estreia no CineBancários o documentário “Para onde voam as feiticeiras”. “Retratos Fantasmas”, quinto longa-metragem do cineasta e roteirista Kleber Mendonça Filho (“O Som ao Redor”, “Aquarius”, “Bacurau”), e “O Acidente”, do diretor gaúcho Bruno Carboni, completam a programação da semana.&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;“Para Onde Voam as Feiticeiras” entrelaça realidade e ficção para discutir a marginalização de diferentes grupos na sociedade. O documentário foi premiado como Melhor Filme e Direção no Rio Festival LGBTQIA+ e no Festival de Vitória, Melhor Filme no Queer Porto e Melhor Direção Longa Nacional no Santos Film Fest, e tem direção coletiva assinada por Eliane Caffé, Carla Caffé e Beto Amaral.&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;O filme tem a narrativa centralizada em sete personagens LGBTQIA+, as artistas-ativistas autodenominadas “manas”: Ave Terrena Alves, Fernanda Ferreira Ailish, Gabriel Lodi, Mariano Mattos Martins, Preta Ferreira, Thata Lopes e Wan Gomez. Como forma de amplificar vozes frequentemente silenciadas, as manas transformam o centro de São Paulo em um palco aberto para a troca de ideias, talentos e revoltas pessoais. O resultado é um grande encontro de personagens de mundos diferentes, que ora se chocam e entram em contradição, ora se apaziguam e se aliam.&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;ESTREIA&lt;/span&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;PARA ONDE VOAM AS FEITICEIRAS&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;&lt;/span&gt;Brasil/ Documentário/ 2020/ 89min&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;Direção: Eliane Caffé, Carla Caffé e Beto Amaral&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;img alt=&quot;&quot; class=&quot;alignnone size-medium wp-image-144231&quot; height=&quot;300&quot; loading=&quot;lazy&quot; sizes=&quot;(max-width: 204px) 100vw, 204px&quot; src=&quot;https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-204x300.jpg&quot; srcset=&quot;https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-204x300.jpg 204w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-545x800.jpg 545w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-768x1128.jpg 768w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-1046x1536.jpg 1046w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-1394x2048.jpg 1394w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-100x147.jpg 100w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-scaled.jpg 1743w&quot; style=&quot;border: 0px none; box-sizing: border-box; height: auto; max-width: 100%; vertical-align: middle;&quot; width=&quot;204&quot; /&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;Sinopse: Para onde voam as feiticeiras acompanha a deriva de encenações e improvisos de sete artistas pelas ruas do centro de São Paulo em uma experiência cinematográfica que torna visível a persistência de preconceitos arcaicos de gênero e raça no imaginário comum. No centro desta narrativa polifônica está a importância da resistência política através das alianças de luta comum entre coletivos LGBTQIA+, negritude, indígenas e trabalhadores sem teto.&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;EM CARTAZ&lt;/span&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;RETRATOS FANTASMAS&lt;/span&gt;&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;Brasil/Documentário/2022/ 93min&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;Direção: Kleber Mendonça Filho&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;img alt=&quot;&quot; class=&quot;alignnone size-medium wp-image-144232&quot; height=&quot;300&quot; loading=&quot;lazy&quot; sizes=&quot;(max-width: 204px) 100vw, 204px&quot; src=&quot;https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3-204x300.png&quot; srcset=&quot;https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3-204x300.png 204w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3-545x800.png 545w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3-768x1128.png 768w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3-1046x1536.png 1046w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3-1394x2048.png 1394w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3-100x147.png 100w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3.png 1814w&quot; style=&quot;border: 0px none; box-sizing: border-box; height: auto; max-width: 100%; vertical-align: middle;&quot; width=&quot;204&quot; /&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;Sinopse: O filme tem o centro da cidade do Recife como personagem principal, sendo um espaço histórico e humano, revisitado através dos grandes cinemas que serviram como espaços de convívio durante o século XX. Foram lugares de sonho e de indústria, e a relação das pessoas com esse universo é um marcador de tempo para as mudanças dos costumes em sociedade.&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;O ACIDENTE&lt;/span&gt;&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;Drama | 95 min. | Brasil&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;Direção: Bruno Carboni / Roteiro: Marcela Ilha Bordin e Bruno Carboni&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;img alt=&quot;&quot; class=&quot;alignnone size-medium wp-image-144233&quot; height=&quot;300&quot; loading=&quot;lazy&quot; sizes=&quot;(max-width: 212px) 100vw, 212px&quot; src=&quot;https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-212x300.jpg&quot; srcset=&quot;https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-212x300.jpg 212w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-565x800.jpg 565w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-768x1087.jpg 768w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-1085x1536.jpg 1085w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-1447x2048.jpg 1447w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-100x142.jpg 100w, https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-scaled.jpg 1808w&quot; style=&quot;border: 0px none; box-sizing: border-box; height: auto; max-width: 100%; vertical-align: middle;&quot; width=&quot;212&quot; /&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;Sinopse: A ciclista Joana é vítima de um atropelamento. Ela foi carregada no capô de um carro após antagonizar com uma motorista que a cortou. A jovem sai ilesa e decide esconder o ocorrido de sua parceira, Cecília, temendo que isso afete os planos do casal. Porém, um vídeo viral aparece online, obrigando-a a prestar queixa na polícia. Relutante, a dupla entra na vida de Elaine, a motorista, seu ex-marido Cléber e seu filho Maicon, um introvertido cineasta iniciante.&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;Elenco: Carol Martins (Joana), Carina Sehn (Cecília), Luis Felipe Xavier (Maicon), Gabriela Greco (Elaine) e Marcello Crawshawn (Cléber)&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;HORÁRIOS CINEBANCÁRIOS&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;31 de agosto a 6 de setembro&lt;/span&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;15h: O ACIDENTE&lt;/span&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;17h:&amp;nbsp;&amp;nbsp;PARA ONDE VOAM AS FEITICEIRAS&lt;/span&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;19h:&amp;nbsp;RETRATOS FANTASMAS&lt;/span&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;em style=&quot;box-sizing: border-box;&quot;&gt;*Não há sessões nas segundas-feiras&lt;/em&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;Ingressos&lt;/span&gt;&lt;/p&gt;&lt;p style=&quot;box-sizing: border-box; color: #212529; font-family: -apple-system, BlinkMacSystemFont, &amp;quot;Segoe UI&amp;quot;, Roboto, &amp;quot;Helvetica Neue&amp;quot;, Arial, sans-serif, &amp;quot;Apple Color Emoji&amp;quot;, &amp;quot;Segoe UI Emoji&amp;quot;, &amp;quot;Segoe UI Symbol&amp;quot;; font-size: 16px; margin-bottom: 1rem; margin-top: 13px;&quot;&gt;Os ingressos podem ser adquiridos a R$ 12 na bilheteria do CineBancários. Idosos (as), estudantes, bancários (as), jornalistas sindicalizados (as), portadores de ID Jovem e pessoas com deficiência pagam R$ 6. São aceitos cartões nas bandeiras Banricompras, Visa, MasterCard e Elo.&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;Na quinta-feira, a meia-entrada é para todos e todas.&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;&lt;span style=&quot;box-sizing: border-box; font-weight: bolder;&quot;&gt;&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;CineBancários&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;&lt;/span&gt;&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;Rua General Câmara, 424 – Centro – Porto Alegre&lt;br style=&quot;box-sizing: border-box;&quot; /&gt;Mais informações pelo telefone (51) 3030.9405 ou pelo e-mail&amp;nbsp;&lt;a href=&quot;mailto:cinebancarios@sindbancarios.org.br&quot; style=&quot;box-sizing: border-box; color: #007bff; text-decoration-line: none;&quot;&gt;cinebancarios@sindbancarios.org.br&lt;/a&gt;&lt;/p&gt;</description>""",
            ),
        ],
    )
    def test_get_current_blog_post_soup(self, input_xml_dir, expected_raw_xml):
        """Test that the returned BeautifulSoup object contains
        the first item's description"""
        cinebancarios = CineBancarios()
        cinebancarios.todays_dir = os.path.join(input_xml_dir)
        expected_xml = ET.fromstring(expected_raw_xml)

        assert cinebancarios._get_current_blog_post_soup() == BeautifulSoup(
            expected_xml.text, "html.parser"
        )

    @pytest.mark.parametrize(
        "input_xml_file,expected_movie_blocks",
        [
            (
                "tests/files/files_cinebancarios/2023-07-26",
                [
                    {
                        "poster": "",
                        "title": "Capitu e o Capítulo",
                        "general_info": "Drama / 75min / Brasil / 2021",
                        "director": "Julio Bressane",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: Capitu e o Capítulo aborda de forma livre a obra de Machado de Assis, Dom Casmurro. Com a proposta de ser um ensaio, o longa apresenta a personalidade complexa de Capitu, em contraste com os diálogos inventivos de Bentinho, e o amor profundo que ele sente pela moça. A paixão visceral vista através de uma nova perspectiva. O enredo também trabalha com a inquietação dos sentimentos humanos, tal qual o ciúme primitivo de Bentinho, e todas as intrigas desenvolvidas por suas paranoias.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "",
                        "title": "Brichos 3 - Megavírus",
                        "general_info": "Animação, aventura / 74min / Brasil / 2023",
                        "director": "Paulo Munhoz",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: A maravilhosa Vila dos Brichos é atacada por um vírus terrível que atinge as mentes das pessoas e que coloca quase toda a população em estado de coma. Nessa situação, a parte ainda saudável da população se une e se organiza para salvar os doentes, enquanto Ratão (o mal elemento) aproveita o caos para saquear toda a cidade. O jaguar adolescente Tales e sua turma terão que usar de muita tecnologia e um tanto de magia, além de sua tradicional coragem, para entrar nos sonhos das pessoas e combater o Megavírus cara a cara.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "",
                        "title": "#eagoraoque",
                        "general_info": "Documentário / 70min / Brasil / 2020",
                        "director": "Jean-Claude Bernardet e Rubens Rewald",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: Como agir hoje politicamente? É possível mudar as coisas, as pessoas, a sociedade? E agora, o que fazer? Um intelectual e suas contradições.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                ],
            ),
            (
                "tests/files/files_cinebancarios/2023-08-24",
                [
                    {
                        "poster": "",
                        "title": "RETRATOS FANTASMAS",
                        "general_info": "Brasil/Documentário/2022/ 93min.",
                        "director": "Kleber Mendonça Filho",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: O filme tem o centro da cidade do Recife como personagem principal, sendo um espaço histórico e humano, revisitado através dos grandes cinemas que serviram como espaços de convívio durante o século XX. Foram lugares de sonho e de indústria, e a relação das pessoas com esse universo é um marcador de tempo para as mudanças dos costumes em sociedade.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "",
                        "title": "O ACIDENTE",
                        "general_info": "Drama | 95 min. | Brasil",
                        "director": False,
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: A ciclista Joana é vítima de um atropelamento. Ela foi carregada no capô de um carro após antagonizar com uma motorista que a cortou. A jovem sai ilesa e decide esconder o ocorrido de sua parceira, Cecília, temendo que isso afete os planos do casal. Porém, um vídeo viral aparece online, obrigando-a a prestar queixa na polícia. Relutante, a dupla entra na vida de Elaine, a motorista, seu ex-marido Cléber e seu filho Maicon, um introvertido cineasta iniciante.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                ],
            ),
            (
                "tests/files/files_cinebancarios/2023-08-31",
                [
                    {
                        "poster": "https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-scaled.jpg",
                        "title": "PARA ONDE VOAM AS FEITICEIRAS",
                        "general_info": "Brasil/ Documentário/ 2020/ 89min",
                        "director": "Eliane Caffé, Carla Caffé e Beto Amaral",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: Para onde voam as feiticeiras acompanha a deriva de encenações e improvisos de sete artistas pelas ruas do centro de São Paulo em uma experiência cinematográfica que torna visível a persistência de preconceitos arcaicos de gênero e raça no imaginário comum. No centro desta narrativa polifônica está a importância da resistência política através das alianças de luta comum entre coletivos LGBTQIA+, negritude, indígenas e trabalhadores sem teto.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3.png",
                        "title": "RETRATOS FANTASMAS",
                        "general_info": "Brasil/Documentário/2022/ 93min",
                        "director": "Kleber Mendonça Filho",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: O filme tem o centro da cidade do Recife como personagem principal, sendo um espaço histórico e humano, revisitado através dos grandes cinemas que serviram como espaços de convívio durante o século XX. Foram lugares de sonho e de indústria, e a relação das pessoas com esse universo é um marcador de tempo para as mudanças dos costumes em sociedade.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-scaled.jpg",
                        "title": "O ACIDENTE",
                        "general_info": "Drama | 95 min. | Brasil",
                        "director": "Bruno Carboni / Roteiro: Marcela Ilha Bordin e Bruno Carboni",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: A ciclista Joana é vítima de um atropelamento. Ela foi carregada no capô de um carro após antagonizar com uma motorista que a cortou. A jovem sai ilesa e decide esconder o ocorrido de sua parceira, Cecília, temendo que isso afete os planos do casal. Porém, um vídeo viral aparece online, obrigando-a a prestar queixa na polícia. Relutante, a dupla entra na vida de Elaine, a motorista, seu ex-marido Cléber e seu filho Maicon, um introvertido cineasta iniciante.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                ],
            ),
            (
                "tests/files/files_cinebancarios/2023-09-06",
                [
                    {
                        "poster": "",
                        "title": "ANGELA",
                        "general_info": "Brasil/ Drama/ 2023/ 104min",
                        "director": "Hugo Prata",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: Após uma tumultuada separação e ter que ceder a guarda dos seus três filhos, a famosa socialite Ângela Diniz conhece Raul, e acredita ter encontrado alguém que ama seu espírito livre tanto quanto ela. A atração avassaladora fez o casal largar tudo e viver o sonho de reconstruir suas vidas na casa de praia. Mas a vida tranquila rapidamente se transforma quando Raul começa a se mostrar um homem agressivo, violento e controlador. A relação declina para o abuso e a violência, dando origem a um dos casos de assassinato mais famosos de todos os tempos no Brasil.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "",
                        "title": "RETRATOS FANTASMAS",
                        "general_info": "Brasil/Documentário/2022/ 93min",
                        "director": "Kleber Mendonça Filho",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: O filme tem o centro da cidade do Recife como personagem principal, sendo um espaço histórico e humano, revisitado através dos grandes cinemas que serviram como espaços de convívio durante o século XX. Foram lugares de sonho e de indústria, e a relação das pessoas com esse universo é um marcador de tempo para as mudanças dos costumes em sociedade.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "",
                        "title": "PARA ONDE VOAM AS FEITICEIRAS",
                        "general_info": "Brasil/ Documentário/ 2020/ 89min",
                        "director": "Eliane Caffé, Carla Caffé e Beto Amaral",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: Para onde voam as feiticeiras acompanha a deriva de encenações e improvisos de sete artistas pelas ruas do centro de São Paulo em uma experiência cinematográfica que torna visível a persistência de preconceitos arcaicos de gênero e raça no imaginário comum. No centro desta narrativa polifônica está a importância da resistência política através das alianças de luta comum entre coletivos LGBTQIA+, negritude, indígenas e trabalhadores sem teto.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                ],
            ),
        ],
    )
    def test_get_current_movie_block(self, input_xml_file, expected_movie_blocks):
        cinebancarios = CineBancarios()
        cinebancarios.todays_dir = os.path.join(input_xml_file)
        soup = cinebancarios._get_current_blog_post_soup()
        movie_blocks = cinebancarios._get_current_movie_blocks(soup)
        assert movie_blocks == expected_movie_blocks

    @pytest.mark.parametrize(
        "input_xml_file,current_movie_blocks,expected_times",
        [
            (
                "tests/files/files_cinebancarios/2023-08-31",
                [
                    {
                        "poster": "https://www.sindbancarios.org.br/wp-content/uploads/2023/08/Cartaz_ParaOndeVoamAsFeiticeiras-scaled.jpg",
                        "title": "PARA ONDE VOAM AS FEITICEIRAS",
                        "general_info": "Brasil/ Documentário/ 2020/ 89min",
                        "director": "Eliane Caffé, Carla Caffé e Beto Amaral",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: Para onde voam as feiticeiras acompanha a deriva de encenações e improvisos de sete artistas pelas ruas do centro de São Paulo em uma experiência cinematográfica que torna visível a persistência de preconceitos arcaicos de gênero e raça no imaginário comum. No centro desta narrativa polifônica está a importância da resistência política através das alianças de luta comum entre coletivos LGBTQIA+, negritude, indígenas e trabalhadores sem teto.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "https://www.sindbancarios.org.br/wp-content/uploads/2023/08/RetratosFantasmas_64x94_web-3.png",
                        "title": "RETRATOS FANTASMAS",
                        "general_info": "Brasil/Documentário/2022/ 93min",
                        "director": "Kleber Mendonça Filho",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: O filme tem o centro da cidade do Recife como personagem principal, sendo um espaço histórico e humano, revisitado através dos grandes cinemas que serviram como espaços de convívio durante o século XX. Foram lugares de sonho e de indústria, e a relação das pessoas com esse universo é um marcador de tempo para as mudanças dos costumes em sociedade.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "https://www.sindbancarios.org.br/wp-content/uploads/2023/08/OACIDENTE_POSTERred-1-scaled.jpg",
                        "title": "O ACIDENTE",
                        "general_info": "Drama | 95 min. | Brasil",
                        "director": "Bruno Carboni / Roteiro: Marcela Ilha Bordin e Bruno Carboni",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: A ciclista Joana é vítima de um atropelamento. Ela foi carregada no capô de um carro após antagonizar com uma motorista que a cortou. A jovem sai ilesa e decide esconder o ocorrido de sua parceira, Cecília, temendo que isso afete os planos do casal. Porém, um vídeo viral aparece online, obrigando-a a prestar queixa na polícia. Relutante, a dupla entra na vida de Elaine, a motorista, seu ex-marido Cléber e seu filho Maicon, um introvertido cineasta iniciante.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                ],
                ["17h", "19h", "15h"],
            ),
            (
                "tests/files/files_cinebancarios/2023-09-06",
                [
                    {
                        "poster": "",
                        "title": "ANGELA",
                        "general_info": "Brasil/ Drama/ 2023/ 104min",
                        "director": "Hugo Prata",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: Após uma tumultuada separação e ter que ceder a guarda dos seus três filhos, a famosa socialite Ângela Diniz conhece Raul, e acredita ter encontrado alguém que ama seu espírito livre tanto quanto ela. A atração avassaladora fez o casal largar tudo e viver o sonho de reconstruir suas vidas na casa de praia. Mas a vida tranquila rapidamente se transforma quando Raul começa a se mostrar um homem agressivo, violento e controlador. A relação declina para o abuso e a violência, dando origem a um dos casos de assassinato mais famosos de todos os tempos no Brasil.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "",
                        "title": "RETRATOS FANTASMAS",
                        "general_info": "Brasil/Documentário/2022/ 93min",
                        "director": "Kleber Mendonça Filho",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: O filme tem o centro da cidade do Recife como personagem principal, sendo um espaço histórico e humano, revisitado através dos grandes cinemas que serviram como espaços de convívio durante o século XX. Foram lugares de sonho e de indústria, e a relação das pessoas com esse universo é um marcador de tempo para as mudanças dos costumes em sociedade.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                    {
                        "poster": "",
                        "title": "PARA ONDE VOAM AS FEITICEIRAS",
                        "general_info": "Brasil/ Documentário/ 2020/ 89min",
                        "director": "Eliane Caffé, Carla Caffé e Beto Amaral",
                        "classification": False,
                        "excerpt": unicodedata.normalize(
                            "NFKD",
                            "Sinopse: Para onde voam as feiticeiras acompanha a deriva de encenações e improvisos de sete artistas pelas ruas do centro de São Paulo em uma experiência cinematográfica que torna visível a persistência de preconceitos arcaicos de gênero e raça no imaginário comum. No centro desta narrativa polifônica está a importância da resistência política através das alianças de luta comum entre coletivos LGBTQIA+, negritude, indígenas e trabalhadores sem teto.",
                        ),
                        "time": [],
                        "read_more": "http://cinebancarios.blogspot.com/?view=classic",
                    },
                ],
                ["19h", "17h", "15h"],
            ),
        ],
    )
    def test_get_movies_show_time(
        self, input_xml_file, current_movie_blocks, expected_times
    ):
        cinebancarios = CineBancarios()
        cinebancarios.todays_dir = os.path.join(input_xml_file)
        soup = cinebancarios._get_current_blog_post_soup()
        current_movie_blocks = cinebancarios._get_movies_show_time(
            soup, current_movie_blocks
        )
        for idx, movie in enumerate(current_movie_blocks):
            assert movie["time"] == expected_times[idx]
