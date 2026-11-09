# Progression

Projet personnel independant ? 2026-11-06.

## Phase 1

- Dossier initial vide ; PDF local Agent Smith v1.1 present et lu.
- Python systeme 3.14.0, uv 0.13.7 et Git 2.54.0 detectes.
- Cible projet Python 3.10 ; verification PyPI avant installation.
- Configuration Pydantic, CLI de verification, structure modulaire et documentation prepares.
- Aucun graphe, fournisseur, outil MCP, sandbox ou benchmark implemente.
- Installation reussie avec uv sync --python 3.10 : CPython 3.10.22, 16 packages, uv.lock genere.
- uv run --locked pytest : 12 tests reussis en 4.00 secondes (7 unitaires, 5 integration).
- Tests : valeurs par defaut, dotenv UTF-8, priorite environnement, valeurs invalides, faute de cle, desactivation dotenv, immutabilite, module installe, entry point, erreur sans fuite de valeur, fichier personnalise et encodage invalide.
- git check-ignore confirme que .env, .env.local et .venv sont ignores ; .env.example reste visible.
- Depot Git initialise, aucun commit cree.
- Phase 1 terminee ; phase 2 en attente de validation.

## Phases suivantes (non commencees)

2. Integration LLM via LangChain : terminee hors ligne (voir ci-dessous).
3. Graphe LangGraph.
4. Tool calling.
5. MCP.
6. Execution controlee.
7. MBPP.
8. SWE-bench.
9. Metriques et benchmark.
10. Documentation et comparaison finale.

Chaque phase exige la validation de l'utilisatrice avant son demarrage. Aucun resultat de benchmark disponible.


## Phase 2 - 2026-11-06

Etat : implementation terminee, verifications hors ligne reussies ; validation avec une vraie API non effectuee volontairement. Phase 3 non commencee, autorisation requise.

- Modele confirme par documentation officielle : gemini-3.1-flash-lite, configurable sans remplacement automatique.
- Compatibilite Python 3.10 verifiee sur PyPI puis par uv sync : langchain-core 1.7.6, langchain-google-genai 4.4.3 ; google-genai 2.33.0 resolu.
- Ajouts : Settings LLM et SecretStr ; contrat ChatProvider ; LLMResponse/TokenUsage ; GeminiProvider ; erreurs publiques sans chaine d'exception originale ; timeout ; une seule tentative ; tracing desactive.
- CLI conserve ses commandes ; --llm-smoke-test et --prompt sont les seules options declenchant une requete explicite. Aucun appel reel execute.
- Mesures : latence locale et compteurs disponibles, aucune estimation. Les zeros potentiellement substitues par LangChain sont exposes comme inconnus ; limite documentee.
- git check-ignore : .env, .env.local et .venv ignores ; aucun vrai secret ajoute.

### Commandes reellement executees

- uv sync : reussi, 52 packages resolus pour Python 3.10.
- uv run --locked pytest : resultat final 65 passed in 3.31s.
- uv lock --check : reussi, 52 packages resolus, verrou coherent.

### Repartition des tests (code lu et execute)

| Fichier | Cas | Couverture |
|---|---|---|
| tests/unit/test_settings.py | 7 | Configuration Phase 1 conservee |
| tests/integration/test_cli.py | 5 | CLI Phase 1 conservee |
| tests/unit/test_llm_settings.py | 12 | Defauts, dotenv/environnement, secret et bornes invalides |
| tests/unit/test_gemini.py | 28 | Cle absente/vide, construction, envoi HumanMessage, texte/blocs, latence, usage complet/absent/partiel/zero, reponse vide, auth/quota/modele/timeout/reseau/httpx2/inattendu, erreur initialisation et absence de fuite |
| tests/integration/test_llm_cli.py | 6 | Aucun modele par defaut, options explicites simulees, cle absente, quota et redaction |
| tests/integration/test_gemini_sdk_boundary.py | 7 | Vrai formatage LangChain avec SDK simule : modele, timeout 30000 ms, attempts=1, reponse, erreurs 401/403/429/404, metadonnees absentes/partielles |

Tous les nouveaux appels LLM sont remplaces par fakes/mocks ; fixture socket de refus reseau dans pytest. Les sous-processus existants ne lancent que la CLI hors ligne. Aucune cle reelle, aucune facturation modifiee, aucun resultat de benchmark.

### Fichiers Phase 2

Crees : ARCHITECTURE_DECISIONS.md, providers/base.py, providers/gemini.py, tests/unit/test_llm_settings.py, tests/unit/test_gemini.py, tests/integration/test_llm_cli.py, tests/integration/test_gemini_sdk_boundary.py.

Modifies : pyproject.toml, uv.lock, .env.example, src/agent_smith/config/settings.py, src/agent_smith/providers/__init__.py, src/agent_smith/cli.py, tests/conftest.py, README.md, PROJECT_PROGRESS.md, FRAMEWORK_ARCHITECTURE.md, FRAMEWORK_COMPARISON.md. Les fichiers de tests Phase 1 ne sont pas modifies ; leur preparation commune est enrichie.

Action manuelle facultative : renseigner SMITH_LLM_API_KEY localement, puis uv run --locked agent-smith --env-file .env --llm-smoke-test. Resultat attendu : reponse IndexError et latence, ou erreur explicite sans secret ; code 0 en cas de succes, 2 en cas d'echec. Ne pas activer la facturation. Aucun commit cree.


## Phase 2 - validation reelle ulterieure autorisee

Apres autorisation explicite de l'utilisatrice, un seul smoke test Gemini a ete execute : reponse IndexError correcte en deux phrases, code de sortie 0, latence 1.187 seconde. Cette validation est distincte des tests simules et aucun resultat de benchmark n'en est deduit. La cle locale a ete deplacee de .env.example vers .env sur demande ; l'exemple est vide et .env ignore par Git. Aucun secret n'est reproduit ici.

## Phase 3 - orchestration LangGraph (2026-11-06)

Etat : implementation et validation hors ligne terminees ; aucun nouvel appel reel Gemini. Phase 4 non commencee et soumise a validation.

### Travail realise

- langgraph 1.2.20 ajoute apres verification PyPI Requires-Python >=3.10 ; uv resout 57 paquets avec les dependances existantes.
- Vrai StateGraph compile : START -> generate -> verify -> retry/finish -> finalize -> END.
- Contrats Pydantic VerificationResult, AttemptRecord, AgentState et AgentResult ; etat interne TypedDict.
- Generation obligatoire, budget 1 ou 2 (defaut 2), correction uniquement apres erreur statique ou reponse vide.
- Syntaxe valide : unverified / syntax_passed_functionality_unverified. Deux echecs : failed / budget_exhausted. Erreur fournisseur : arret immediat sans retry de syntaxe.
- Extraction Python brut/bloc Markdown unique, ast.parse sans execution, historique et metriques disponibles sans estimation.
- CLI --agent-task explicite, mode par defaut et options Phase 2 conserves ; adaptation Gemini et configuration Phase 2 non modifies.
- Mermaid exporte localement du graphe compile dans docs/phase3_graph.mmd ; demonstration dans examples/phase3_offline.py.

### Verifications executees

- uv sync : premier essai bloque par Windows os error 1450 lors d'ecriture du cache de build ; nouvelle tentative reussie sans changement d'architecture. 57 paquets resolus, LangGraph et dependances installes.
- uv run --locked pytest : 148 passed in 8.73s sous Python 3.10.22.
- uv lock --check : reussi, 57 paquets resolus.
- uv run --locked python examples/phase3_offline.py : trois scenarios reussis, vrais parcours de noeuds affiches et faux fournisseur uniquement.

| Fichiers de tests | Cas | Resultat |
|---|---|---|
| Six fichiers Phases 1-2 | 65 | Tous conserves et reussis |
| tests/unit/test_agent_models.py | 22 | Contrats, budgets, statuts, historique, collections et latence |
| tests/unit/test_agent_verifier.py | 19 | Extraction, ambiguite, syntaxe, structure, limites fonctionnelles et prompts |
| tests/integration/test_agent_graph.py | 34 | Graphe compile, parcours exacts, erreurs, budget, metriques, reutilisation, reseau bloque et nonexecution |
| tests/integration/test_agent_cli.py | 8 | Mode explicite, resultats, erreurs, confidentialite et compatibilite |
| Total | 148 | Tous reussis |

### Demonstration hors ligne observee

- Proposition valide : generate -> verify -> finalize ; 1 appel ; unverified.
- Erreur puis correction : generate -> verify -> generate -> verify -> finalize ; 2 appels ; unverified.
- Deux erreurs : meme parcours de deux tentatives ; 2 appels ; failed / budget_exhausted.
- Latences de cette demonstration : valeurs synthetiques 0.000 s explicitement etiquetees, pas des mesures Gemini.

### Fichiers Phase 3

Crees : src/agent_smith/agent/{__init__,models,prompts,verifier,nodes,graph}.py ; tests/unit/test_agent_models.py ; tests/unit/test_agent_verifier.py ; tests/integration/test_agent_graph.py ; tests/integration/test_agent_cli.py ; examples/phase3_offline.py ; docs/phase3_graph.mmd.

Modifies : pyproject.toml, uv.lock, src/agent_smith/cli.py, README.md, PROJECT_PROGRESS.md, ARCHITECTURE_DECISIONS.md, FRAMEWORK_ARCHITECTURE.md et FRAMEWORK_COMPARISON.md. Aucun fichier de test existant, fournisseur Gemini, parametre Phase 2 ou secret modifie pendant cette phase. Aucun commit cree.

### Limites

AST valide ne veut pas dire programme correct, executable ou sur. Aucune execution, sandbox, MCP, outil ou benchmark. Pas de delai absolu de processus ni de protection contre toute entree AST hostile. L'equivalence avec From Scratch est celle des regles fournies, pas une comparaison de ses fichiers. Nouvelle commande reelle non executee : attendre une autorisation explicite distincte.
