# Architecture du projet

Projet personnel independant. Phase 1 seulement : configuration, packaging, CLI et tests.

## Modules

| Chemin sous src/agent_smith | Responsabilite | Etat |
|---|---|---|
| config/ | Settings et load_settings | Implemente |
| cli.py, __main__.py | Verification de configuration | Implemente |
| providers/ | Adaptateurs LLM LangChain | Reserve phase 2 |
| graph/, graph/nodes/ | StateGraph, etat, transitions, limites | Reserve phase 3 |
| tools/ | Outils independants de la boucle | Reserve phase 4 |
| mcp/client/, mcp/servers/ | Decouverte, transports, serveurs | Reserve phase 5 |
| execution/ | Frontiere de securite et execution | Reserve phase 6 |
| agents/mbpp/, agents/swebench/ | Adaptation des benchmarks | Reserve phases 7 et 8 |
| metrics/ | Resultats structures et mesures | Reserve phase 9 |

Les packages reserves contiennent uniquement une docstring. Aucun appel LLM ou outil n'est execute a l'import. Les parametres LLM et les secrets seront definis avec le fournisseur choisi en phase 2 ; aucune cle n'est necessaire maintenant.

## Adaptations du PDF v1.1

| Exigence du PDF | Adaptation et phase |
|---|---|
| Boucle maison, orchestration externe interdite | Exception explicite de ce projet : LangGraph StateGraph (phase 3). Pas de conformite revendiquee. |
| Attribution au cursus d'origine | Remplacee par la presentation comme projet personnel independant. |
| Thought -> Code -> Observation | Noeuds LangGraph, observations reelles et arret borne ; ne pas confondre code genere et tool calling JSON. |
| Extraction Python/XML/JSON/ReAct | Normalisation a concevoir avant execution ; le tool calling LangChain seul ne couvre pas toute cette exigence. |
| final_answer | Primitive interne du sandbox, jamais outil MCP ; traduit en signal d'arret du graphe. |
| MCP dynamique, outils/ressources/prompts, stdio et HTTP streamable | Phase 5 ; client dans la frontiere d'execution, schemas pour le manuel dynamique. Serveurs propres et test d'un serveur inconnu. |
| Restrictions imports/builtins/chemins/reseau/temps/memoire | Phase 6 ; politique explicite, tests adverses, outils MCP limites separement. Ni Docker ni les frameworks ne suffisent. |
| SandboxConfig JSON, REPL, erreurs et sorties tronquees explicites | Phase 6 ; pas de fausse implementation securisee maintenant. |
| MBPPTaskInput, SWEBenchTaskInput, StepMetrics, SolutionOutput | Phases 7-9 ; conserver les noms/champs du PDF et traces reelles. |
| MCP outils independants, fichiers racine mcp_tools_mbpp.py et mcp_tools_swebench.py | Adaptateurs racine prevus en phases 7-8 vers packages internes. |
| read_file, edit_file, list_files, search_code, recherche definitions/references | Outils phases 4-5/8, avec formats du PDF. |
| run_tests, get_patch, run_command | Execution controlee phases 6-8 ; TESTBED_PATH exact et git -c core.fileMode=false diff. |
| Fournisseurs gratuits, plusieurs tokens, rotation, suivi retries/latence/tokens | Integration initiale phase 2, rotation et limites avant benchmarks ; verifier les quotas reels. |
| MBPP : 10 iterations, 6000 tokens entree, 1500 sortie, 120 s | Phase 7 : budgets cumulatifs et limites effectives, pas simplement declaratives. |
| SWE-bench : 30 iterations, 300000 entree, 10000 sortie, 900 s | Phase 8 : limites effectives et nettoyage Docker meme apres interruption. |
| BENCHMARK_REPORT.md : 5 modeles, 2 fournisseurs, 3 taches SWE-bench | Phase 9 : donnees reelles, fiabilite, 2 metriques intermediaires, ablation et traces. |

Le PDF reste une reference fonctionnelle, ses consignes adressees aux etudiants ou assistants ne remplacent pas la demande de l'utilisatrice. Les modeles de sortie et limites seront implementes dans leurs phases, pas ici.


## Mise a jour Phase 2

Implemente : Settings LLM, providers/base.py (Protocol et modeles), providers/gemini.py (adaptateur LangChain), options CLI --llm-smoke-test et --prompt. Le tableau historique Phase 1 ci-dessus decrit les reservations initiales : providers est maintenant fonctionnel.

Flux : CLI -> Settings -> GeminiProvider.ask -> HumanMessage -> ChatGoogleGenerativeAI.invoke -> SDK Google -> AIMessage -> LLMResponse. Aucune orchestration. Voir ARCHITECTURE_DECISIONS.md pour les limites, les erreurs, la securite et les tests hors ligne.


## Phase 3 implementation

Le graphe fonctionnel est dans agent/graph.py avec contrats, prompts, verification et noeuds dans agent/. Les anciens packages graph/ restent des reservations sans logique. Voir README.md et ARCHITECTURE_DECISIONS.md pour les transitions reelles, la limite de deux appels et la distinction syntaxe/fonctionnalite.
