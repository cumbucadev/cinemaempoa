# Contribuindo

Obrigado por dedicar o seu tempo para contribuir! 🙇‍♀️🙇‍♂️ Toda ajuda é bem-vinda!

- [Primeira Contribuição](#primeira-contribuição)

## 💌 Quer contribuir, mas não se sente à vontade?

Você tem vontade de contribuir, mas não se sente à vontade em abrir issues, PRs ou fazer perguntas publicamente?

Nós sabemos como pode ser difícil dar o primeiro passo em um espaço aberto. A insegurança, o medo de errar ou até a sensação de “será que minha dúvida é boba?” podem pesar bastante. E tá tudo bem sentir isso. 💜

Queremos que você saiba que aqui ninguém precisa enfrentar esse caminho sem apoio. Se preferir um espaço mais reservado, você pode mandar um e-mail para cumbucadev@gmail.com e teremos o maior prazer em ajudar. Seja para tirar dúvidas, pedir orientação ou simplesmente ter alguém para conversar sobre como começar.

O importante é que você saiba: sua participação é muito bem-vinda, e cada contribuição, por menor que pareça, faz uma grande diferença. ✨

## Primeira Contribuição

Como fazer a sua primeira contribuição:

- [1. Crie uma Conta no GitHub](#1-crie-uma-conta-no-github)
- [2. Encontre uma Issue para Trabalhar](#2-encontre-uma-issue-para-trabalhar)
- [3. Instale o Git](#3-instale-o-git)
- [4. Faça um Fork do Projeto](#4-faça-um-fork-do-projeto)
- [5. Clone o Seu Fork](#5-clone-o-seu-fork)
- [6. Crie um Novo Branch](#6-crie-um-novo-branch)
- [7. Execute o cinemaempoa Localmente](#7-execute-o-cinemaempoa-localmente)
- [8. Faça as Suas Alterações](#8-faça-as-suas-alterações)
- [9. Teste as Suas Alterações](#9-teste-as-suas-alterações)
- [10. Atualizar READMEs](#10-atualizar-readmes)
- [11. Faça o Commit e Envie as Suas Alterações](#11-faça-o-commit-e-envie-as-suas-alterações)
- [12. Crie um PR no GitHub](#12-crie-um-pr-no-github)
- [13. Atualizar a Sua Branch se Necessário](#13-atualizar-a-sua-branch-se-necessário)
- [14. Contribuição feita!](#14-contribuição-feita)

___

### 1. Crie uma Conta no GitHub

Certifique-se de ter uma [conta no GitHub][github-join] e de estar com a sessão iniciada.

Caso não tenha uma conta, siga os passos de [como criar de uma conta pessoal no GitHub][github-essentials-criar-conta].

___

### 2. Encontre uma Issue para Trabalhar

Visite a [página de issues do cinemaempoa][cinemaempoa-issues] e encontre uma issue com a qual você gostaria
de trabalhar e que ainda não tenha sido atribuída a ninguém.

Deixe um comentário na issue com conteúdo "bora!" Em seguida, um bot vai atribuir a issue a você. Uma vez atribuída, você pode prosseguir para a próxima etapa.

Sinta-se à vontade para fazer qualquer pergunta na página da issue antes ou durante o processo de
desenvolvimento.

Ao começar a contribuir para o projeto, é recomendável que você pegue uma issue por vez. Isso ajuda a garantir que outras pessoas também tenham a oportunidade de colaborar e evita que recursos fiquem inativos por muito tempo.

___

### 3. Instale o Git

Certifique-se de ter o git instalado, seguindo os passos do [tutorial de instalação do git][github-essentials-instalando-o-git].

___

### 4. Faça um Fork do Projeto

[Faça um fork do repositório cinemaempoa][github-forking].

___

### 5. Clone o Seu Fork

[Clone][github-cloning] o seu fork localmente.

___

### 6. Crie um Novo Branch

Entre na pasta do brutils:

```bash
$ cd cinemaempoa
>
```

E crie uma nova branch com o nome da issue em que você irá trabalhar através do comando:

```bash
$ git checkout -b <issue_number>
>
```

Exemplo:

```bash
$ git checkout -b 386
Switched to a new branch '386'
>
```

___

### 7. Execute o cinemaempoa Localmente

Para executar o projeto, leia a seção [rodando o projeto][readme] do arquivo `README.md` do projeto.

Nele está explicado o passo a passo para realizar a instalação e execução do projeto, através de instalação local ou via Docker


___

### 8. Faça as Suas Alterações

Após ter feito a instalação e executado corretamente, você poderá implementar as suas alterações no código.


Normalmente existem instruções/ideias de como você pode implementar a solução diretamente na descrição da issue, na seção "Descreva alternativas que você considerou". Leia atentamente tudo que está escrito na issue para garantir que
suas modificações resolvem tudo que está sendo solicitado.


-----------------------------------<b style='color:red'> [INÍCIO DE SEÇÕES EM MANUTENÇÃO] </b>-------------------------------------


### 9. Teste as Suas Alterações

#### Escreva Novos Testes

Certifique-se de ter criado os testes necessários para cada nova alteração que você fez.

#### Certifique-se de que Todos os Testes Passam

Execute todos os testes com o comando `make test` e certifique-se de que todos passam.

**Os PRs não serão mesclados se houver algum teste faltando ou falhando.**

#### Teste manualmente

Abra um ambiente interativo para testar manualmente as suas mudanças:

```sh
$ python
Python 3.x.y ...
Type "help", "copyright", "credits" or "license" for more information.
>>> # Teste as suas mudanças aqui!
```

Exemplo:

```sh
$ python
Python 3.12.5 (main, Aug  6 2024, 19:08:49) [Clang 15.0.0 (clang-1500.3.9.4)] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> import brutils
>>> from brutils import cpf
>>> cpf.generate()
'13403202232'
>>> from brutils import generate_cpf
>>> generate_cpf()
'64590379228'
```

### 10. Atualizar READMEs

Atualize o arquivo `cinemaempoa/README.md` com suas alterações.

Esse arquivo é essencial para a documentação da biblioteca, ajudando os usuários a entender como utilizar os recursos oferecidos. Portanto, é importante mantê-lo sempre atualizado.


Exemplo (README.md):

````md
### format_cep

Formata um CEP (Código de Endereçamento Postal) brasileiro em um formato padrão.
Esta função recebe um CEP como entrada e, se for um CEP válido com 8 dígitos,
o formata no padrão "12345-678".

Argumentos:

- cep (str): O CEP (Código de Endereçamento Postal) de entrada a ser
              formatado.

Retorna:

- str: O CEP formatado no formato "12345-678" se for válido, None se não for
        válido.

Example:

```python
>>> from brutils import format_cep
>>> format_cep('01310200')
'01310-200'
>>> format_cep("12345678")
"12345-678"
>>> format_cep("12345")
None
````

---------------------------------------- <b style='color:red'>FIM DE SEÇÕES EM MANUTENÇÃO</b> ----------------------------------------

### 11. Faça o Commit e Envie as Suas Alterações

Formate o seu código executando utilizando o [pre-commit](https://pre-commit.com/):
- o pre-commit pode automatizar a formatação do código quando você rodar um `git commit`.

Para utilizá-lo, instale com:

    pre-commit install


Faça o commit das alterações:

```bash
$ git commit -a -m "<commit_message>"
...
```

Exemplo:

```bash
$ git commit -m 'Adicionando mais info aos arquivos de contribuição'
[386 173b7e6] Adicionando mais info aos arquivos de contribuição
 2 files changed, 144 insertions(+), 34 deletions(-)
```

Push o seu commit para o GitHub:

```bash
$ git push --set-upstream origin <issue_number>
...
```

Exemplo:

```bash
$ git push --set-upstream origin 386
Running pre-push hook checks
All checks passed!
Enumerating objects: 7, done.
Counting objects: 100% (7/7), done.
Delta compression using up to 10 threads
Compressing objects: 100% (4/4), done.
Writing objects: 100% (4/4), 2.36 KiB | 2.36 MiB/s, done.
Total 4 (delta 3), reused 0 (delta 0), pack-reused 0
remote: Resolving deltas: 100% (3/3), completed with 3 local objects.
remote:
remote: Create a pull request for '386' on GitHub by visiting:
remote:      https://github.com/cumbucadev/cinemaempoa/pull/new/386
remote:
To github.com:cumbucadev/cinemaempoa.git
 * [new branch]      386 -> 386
```

Faça as alterações e commits necessários e envie-os quando estiverem prontos.


### 12. Crie um PR no GitHub

Antes de abrir um Pull Request, valide e formate o código conforme descrito na seção [Instalando o projeto usando Docker][formatacao-pr], utilizando também da ferramenta `pre-commit`


[Crie um PR no GitHub][github-creating-a-pr] para enviar suas alterações para revisão. Para garantir que seu Pull Request (PR) seja claro, eficaz e revisado rapidamente, siga estas boas práticas:

#### Escreva um Título Descritivo para o PR
- Use títulos claros e específicos para descrever o propósito das suas alterações. Um bom título ajuda às pessoas mantenedoras a entender a intenção do PR rapidamente e melhora a rastreabilidade do projeto.
- **Exemplo**: Em vez de “Nova funcionalidade”, use “Adiciona a funcionalidade `pesquisar_salas_proximas` para listar as salas de cinema próximas da pessoa usuária.”
- **Benefícios**:
  - Títulos claros facilitam a priorização e o entendimento pelos revisores.
  - Melhoram a organização e a busca no projeto.

#### Forneça uma Descrição Detalhada do PR
- Inclua uma descrição completa no seu PR para explicar:
  - **O que** foi feito (ex.: adicionou uma nova função, corrigiu um bug).
  - **Por que** foi feito (ex.: para resolver uma issue específica ou melhorar o desempenho).
  - **Quais problemas** foram resolvidos ou melhorias aplicadas (ex.: referencie a issue ou descreva a melhoria).
- **Exemplo**:
Este PR adiciona o utilitário convert_uf_to_text para converter códigos de estados brasileiros (ex.: “SP”) em nomes completos (ex.: “São Paulo”). Resolve a issue #474, melhorando a reutilização de código para formatação de endereços. A função inclui validação de entrada e testes atualizados.
- **Benefícios**:
- Descrições detalhadas agilizam o processo de revisão ao fornecer contexto.
- Ajudam futuros mantenedores a entender o propósito e o histórico do código.

#### Vincule o PR à Issue Relacionada
- Referencie a issue que seu PR resolve usando palavras-chave como `Closes #474` ou `Fixes #474` na descrição do PR. Isso fecha a issue automaticamente quando o PR for mesclado.
- **Exemplo**: `Closes #474`
- **Benefícios**:
- Vincular issues mantém o repositório organizado e garante o rastreamento de tarefas.
- Automatiza o fechamento de issues, reduzindo trabalho manual para mantenedores.
- Para mais detalhes, consulte a [documentação do GitHub sobre fechamento automático de issues](https://docs.github.com/pt/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue).

#### Verifique o Template de Descrição do PR
- Certifique-se de que seu PR segue o template de descrição do repositório. Verifique todos os itens obrigatórios, como cobertura de testes, atualizações de documentação ou entradas no changelog.
- **Exemplo de Checklist**: (mostrando como fica quando preenchido):
- [x] Alterações no código foram testadas.
- [x] Documentação (READMEs) foi atualizada.
- [ ] Entrada no changelog foi adicionada (marque apenas se aplicável).
- **Nota sobre a Sintaxe**:
- Use [x] para marcar itens concluídos e [ ] para itens não concluídos, sem espaços dentro dos colchetes (ex.: [ x ] ou [x ] não será renderizado corretamente no GitHub).
- **Benefícios**:
- Seguir o template garante que o PR esteja completo e pronto para revisão.
- Reduz a necessidade de idas e vindas com revisores, acelerando o processo de mesclagem.

### 13. Atualizar a Sua Branch se Necessário

[Certifique-se de que sua branch esteja atualizado com o main][github-sync-pr]

### 14. Contribuição feita!

Pronto! Após você ter seguido as orientações deste documento, você acabou contribuindo para um projeto Open Source e te agradecemos por todo tempo e esforço dedicado!

**Tem mais ideias ou sugestões de melhorias?**
<br>

1. Abra uma `issue`

    OU

2. Nos envie uma mensagem por e-mail (cumbucadev@gmail.com) ou pelas nossas redes: [Instagram](https://instagram.com/cumbucadev) / [LinkedIn](https://www.linkedin.com/company/cumbucadev/)

<br>
<b>Sinta-se sempre à vontade para continuar contribuindo 💌 </b>

_- Equipe Cinemaempoa e CumbucaDev_

[cinemaempoa-issues]: https://github.com/cumbucadev/cinemaempoa/issues
[formatacao-pr]:https://github.com/cumbucadev/cinemaempoa/tree/main?tab=readme-ov-file#instalando-o-projeto-usando-docker
[github-cloning]: https://docs.github.com/pt/repositories/creating-and-managing-repositories/cloning-a-repository
[github-creating-a-pr]: https://docs.github.com/pt/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request
[github-essentials-criar-conta]: https://github-essentials.cumbuca.dev/dia-5-contas-e-planos/criacao-de-uma-conta-pessoal-no-github
[github-essentials-instalando-o-git]: https://github-essentials.cumbuca.dev/dia-2-controle-de-versao-basico-com-git/git/instalando-o-git
[github-forking]: https://git-e-github.para-humanos.cumbuca.dev/11.-fluxo-de-trabalho/11.1-fork-no-github
[github-join]: https://github.com/join
[github-sync-pr]: https://docs.github.com/pt/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/keeping-your-pull-request-in-sync-with-the-base-branch
[readme]: https://github.com/cumbucadev/cinemaempoa/tree/main?tab=readme-ov-file#rodando-o-projeto