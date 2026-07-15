# Contribuindo

Obrigado por dedicar o seu tempo para contribuir! 🙇‍♀️🙇‍♂️ Toda ajuda é bem-vinda!

- [Primeira Contribuição](#primeira-contribuição)

## 💌 Quer contribuir, mas não se sente à vontade?

Você tem vontade de contribuir, mas não se sente à vontade em abrir issues, PRs
ou fazer perguntas publicamente?

Nós sabemos como pode ser difícil dar o primeiro passo em um espaço aberto. A
insegurança, o medo de errar ou até a sensação de “será que minha dúvida
é boba?” podem pesar bastante. E tá tudo bem sentir isso. 💜

Queremos que você saiba que aqui ninguém precisa enfrentar esse caminho sem
apoio. Se preferir um espaço mais reservado, você pode mandar um e-mail para
<cumbucadev@gmail.com> e teremos o maior prazer em ajudar. Seja para tirar dúvidas,
pedir orientação ou simplesmente ter alguém para conversar sobre como começar.

O importante é que você saiba: sua participação é muito bem-vinda, e cada
contribuição, por menor que pareça, faz uma grande diferença. ✨

## Primeira Contribuição

Como fazer a sua primeira contribuição:

- [Contribuindo](#contribuindo)
  - [💌 Quer contribuir, mas não se sente à vontade?](#-quer-contribuir-mas-não-se-sente-à-vontade)
  - [Primeira Contribuição](#primeira-contribuição)
    - [1. Crie uma Conta no GitHub](#1-crie-uma-conta-no-github)
    - [2. Encontre uma Issue para Trabalhar](#2-encontre-uma-issue-para-trabalhar)
    - [3. Instale o Git](#3-instale-o-git)
    - [4. Faça um Fork do Projeto](#4-faça-um-fork-do-projeto)
    - [5. Clone o Seu Fork](#5-clone-o-seu-fork)
    - [6. Crie um Novo Branch](#6-crie-um-novo-branch)
    - [7. Execute o cinemaempoa Localmente](#7-execute-o-cinemaempoa-localmente)
    - [8. Faça as Suas Alterações](#8-faça-as-suas-alterações)
    - [9. Faça o Commit e Envie as Suas Alterações](#9-faça-o-commit-e-envie-as-suas-alterações)
    - [10. Crie um PR no GitHub](#10-crie-um-pr-no-github)
      - [Escreva um Título Descritivo para o PR](#escreva-um-título-descritivo-para-o-pr)
      - [Forneça uma Descrição Detalhada do PR](#forneça-uma-descrição-detalhada-do-pr)
    - [11. Atualizar a Sua Branch se Necessário](#11-atualizar-a-sua-branch-se-necessário)
    - [12. Contribuição feita!](#12-contribuição-feita)

___

### 1. Crie uma Conta no GitHub

Certifique-se de ter uma [conta no GitHub][github-join] e de estar com a sessão
iniciada.

Caso não tenha uma conta, siga os passos de [como criar de uma conta pessoal no GitHub][github-essentials-criar-conta].

___

### 2. Encontre uma Issue para Trabalhar

Visite a [página de issues do cinemaempoa][cinemaempoa-issues] e encontre uma
issue com a qual você gostaria
de trabalhar e que ainda não tenha sido atribuída a ninguém.

Deixe um comentário na issue dizendo que tem interesse em trabalhar. Em seguida,
alguém do time vai atribuir a issue a você.

Sinta-se à vontade para fazer qualquer pergunta na página da issue antes ou
durante o processo de desenvolvimento.

Ao começar a contribuir para o projeto, é recomendável que você pegue uma
issue por vez. Isso ajuda a garantir que outras pessoas também tenham a oportunidade
de colaborar e evita que recursos fiquem inativos por muito tempo.

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

Entre na pasta do cinemaempoa:

```bash
$ cd cinemaempoa
>
```

E crie uma nova branch com o nome da issue em que você irá trabalhar através
do comando:

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

Para executar o projeto, leia a seção [rodando o projeto][readme] do arquivo
`README.md` do projeto.

Nele está explicado o passo a passo para realizar a instalação e execução
do projeto, através de instalação local ou via Docker

___

### 8. Faça as Suas Alterações

Após ter feito a instalação e executado corretamente, você poderá implementar
as suas alterações no código.

Às vezes podem existir instruções/ideias de como você pode implementar a solução
diretamente na descrição da issue. Leia atentamente tudo que está escrito na
issue para garantir que suas modificações resolvem tudo que está sendo solicitado.

### 9. Faça o Commit e Envie as Suas Alterações

Faça o commit das alterações:

```bash
$ git commit -m "<commit_message>"
...
```

Exemplo:

```bash
$ git commit -m 'Adicionando mais info aos arquivos de contribuição'
[386 173b7e6] Adicionando mais info aos arquivos de contribuição
 2 files changed, 144 insertions(+), 34 deletions(-)
```

Envie o seu commit para o GitHub:

```bash
$ git push --set-upstream origin <issue_number>
...
```

Exemplo:

```bash
$ git push --set-upstream origin 386
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

### 10. Crie um PR no GitHub

[Crie um PR no GitHub][github-creating-a-pr] para enviar suas alterações para
revisão. Para garantir que seu Pull Request (PR) seja claro, eficaz e revisado
rapidamente, siga estas boas práticas:

#### Escreva um Título Descritivo para o PR

Use títulos claros e específicos para descrever o propósito das suas alterações.

**Exemplo**: Em vez de “Nova funcionalidade”, use “Funcionalidade
`pesquisar_salas_proximas` para listar as salas de cinema próximas da pessoa usuária.”

#### Forneça uma Descrição Detalhada do PR

Inclua uma descrição completa no seu PR para explicar:

- **O que** foi feito (ex.: adicionou uma nova função, corrigiu um bug).
- **Por que** foi feito (ex.: para resolver uma issue específica ou melhorar o desempenho).
- **Quais problemas** foram resolvidos ou melhorias aplicadas (ex.: referencie a issue ou descreva a melhoria).

 **Exemplo**:

> Este PR adiciona o utilitário converter_sessao_em_lista para converter as sessões
de cinema em listas. Resolve a issue #474, melhorando a iteração das sessões
de cinema. A função inclui validação de entrada e testes atualizados.

### 11. Atualizar a Sua Branch se Necessário

[Certifique-se de que sua branch esteja atualizado com o main][github-sync-pr]

### 12. Contribuição feita

Pronto! Após você ter seguido as orientações deste documento, você acabou
contribuindo para um projeto Open Source e te agradecemos por todo tempo e
esforço dedicado!

**Tem mais ideias ou sugestões de melhorias?**

1. Abra uma [issue](https://github.com/cumbucadev/comunidade/issues/new?template=BLANK_ISSUE), ou
2. Nos envie uma mensagem por e-mail (<cumbucadev@gmail.com>) ou pelas nossas redes:
[Instagram](https://instagram.com/cumbucadev) / [LinkedIn](https://www.linkedin.com/company/cumbucadev/)

Sinta-se sempre à vontade para continuar contribuindo 💌.

_Equipe Cinemaempoa e CumbucaDev_.

[cinemaempoa-issues]: https://github.com/cumbucadev/cinemaempoa/issues
[github-cloning]: https://docs.github.com/pt/repositories/creating-and-managing-repositories/cloning-a-repository
[github-creating-a-pr]: https://git-e-github.para-humanos.cumbuca.dev/10.-pull-requests-no-github/10.3-criando-um-pull-request-no-github
[github-essentials-criar-conta]: https://github-essentials.cumbuca.dev/dia-5-contas-e-planos/criacao-de-uma-conta-pessoal-no-github
[github-essentials-instalando-o-git]: https://git-e-github.para-humanos.cumbuca.dev/2.-fundamentos-de-controle-de-versao-e-git/2.4-instalando-o-git
[github-forking]: https://git-e-github.para-humanos.cumbuca.dev/11.-fluxo-de-trabalho/11.1-fork-no-github
[github-join]: https://github.com/join
[github-sync-pr]: https://docs.github.com/pt/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/keeping-your-pull-request-in-sync-with-the-base-branch
[readme]: https://github.com/cumbucadev/cinemaempoa/tree/main?tab=readme-ov-file#rodando-o-projeto
