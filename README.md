# CINEMA EM POA

Rode com

    TODAY=$(date +%F); ./scrape.py -r capitolio sala-redencao cinebancarios | tee "$TODAY.json" | ./build.py > "$TODAY.html"

E depois abra o html criado com seu navegador de preferência ♥‿♥