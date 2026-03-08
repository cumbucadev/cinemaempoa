#!/bin/bash

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' 

echo -e "${BLUE}=== Bootstrapping Cinema em POA ===${NC}"

# Cria ambiente virtual (.venv)
echo -e "${GREEN}>> Criando ambiente virtual...${NC}"
python3 -m venv .venv

# Ativa o ambiente e instala dependências
echo -e "${GREEN}>> Instalando dependências (requirements.txt)...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
source .venv/bin/activate

# Inicializa a database
echo -e "${GREEN}>> Inicializando tabelas do banco de dados...${NC}"
flask --app flask_backend init-db

# 4. (Opcional) Popular banco com dados iniciais
read -p "Deseja popular o banco com dados iniciais (seed)? [y/N]: " confirm
if [[ $confirm == [yY] ]]; then
    echo -e "${GREEN}>> Populando banco...${NC}"
    flask --app flask_backend seed-db
    echo -e "${BLUE}Nota: Login 'cinemaempoa' e senha '123123' criados.${NC}"
fi

echo -e "${BLUE}=== Setup concluído com sucesso! ===${NC}"
echo -e "Para rodar o projeto, use:"
echo -e "${GREEN}source .venv/bin/activate${NC}"
echo -e "${GREEN}flask --app flask_backend run --debug${NC}"
