INSERT INTO cinema (name, slug, url) VALUES 
("Cinemateca Capitólio", "capitolio", "http://www.capitolio.org.br/"),
("Sala Redenção", "sala-redencao", "https://www.ufrgs.br/difusaocultural/salaredencao/"),
("CineBancários", "cinebancarios","http://cinebancarios.blogspot.com/"),
("Cinemateca Paulo Amorim", "paulo-amorim", "https://www.cinematecapauloamorim.com.br/");

INSERT INTO screening (
    cinema_id,
    screening_date,
    screening_time,
    movie_title,
    screening_url,
    image,
    description
) VALUES (
    1,
    "2023-09-29",
    "14h30/ 18h30",
    "A CASA DOS PRAZERES",
    "https://www.cinematecapauloamorim.com.br/programacao/1866/a-casa-dos-prazeres",
    "MV5BYTc0MDdiM2QtNjhiMi00MTU2LWI2MDYtMmI4NTNiZmI1MTFkXkEyXkFqcGdeQXVyMTU3NDcwMzc4._V1_.jpg",
    "La Maison - França, 2023, 89min | Sala Norberto Lubisco | Drama

14h30/ 18h30

Direção: DE Anissa Bonnefont

18 anos

Aos 27 anos, a escritora Emma decide dedicar um livro ao universo da prostituição. Para entender melhor a vida destas “mulheres que ninguém se atreve a olhar nos olhos”, ela começa a trabalhar em um bordel chamado La Maison. Além de elementos para uma crônica realista, a experiência de Emma traz reflexões sobre a condição feminina, sororidade e machismo. O filme é baseado na experiência pessoal da escritora francesa Emma Becker, que trabalhou em dois bordeis da Alemanha durante quase dois anos."
), (
    1,
    "2023-09-29",
    "15h00",
    "OLDBOY",
    "https://www.cinematecapauloamorim.com.br/programacao/1845/oldboy",
    "MV5BMTI3NTQyMzU5M15BMl5BanBnXkFtZTcwMTM2MjgyMQ@@._V1_.jpg",
    "Coréia do Sul, 2023, 120min | Sala Eduardo Hirtz | Drama

15h00

Direção: DE Park Chan-wook

16 anos

Oh Dae-su passou 15 anos em um cativeiro, tendo somente uma televisão como entretenimento. Quando finalmente é liberto, ele tem cinco dias para identificar seu raptor e realizar sua vingança. Lançado há 20 anos, o filme foi um grande sucesso de público, ganhou muitos prêmios internacionais e abriu caminho para que outros títulos do cinema coreano ganhassem popularidade e estreassem pelo mundo afora. OLDBOY volta a cartaz em cópia restaurada e remasterizada a partir do negativo original em 35mm, sob supervisão do próprio diretor Park Chan-wook."
);