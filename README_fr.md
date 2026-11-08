![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/36fb04e4-cc75-4454-bd8b-049d11aa86f9)

<div align="center">

<a href="./README.md">English</a> ｜ <a href="./README_zh.md">简体中文</a> ｜ <a href="./README_zh-TW.md">繁體中文</a> ｜ <a href="./README_ja.md">日本語</a> ｜ Français ｜ <a href="./README_es.md">Español</a> ｜ <a href="./README_ru.md">Русский</a>

<br>
<br>

[![version](https://img.shields.io/badge/version-4.29.4%2Bmtn1-blue)](https://github.com/Chenamel/astrbot-maintained/releases)
[![license](https://img.shields.io/badge/license-AGPL--3.0-green)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

</div>

Il s'agit d'une branche maintenue d'AstrBot, dont la référence est verrouillée sur la version amont `v4.29.4`. Le dépôt est maintenu de manière indépendante et ne fait pas partie du réseau de forks de GitHub. Les paquets de distribution ne contiennent que le core lui-même, sans aucun plugin. La licence est AGPL-3.0-or-later, sans aucune affiliation avec les auteurs amont.

## Différences fondamentales et nouvelles API

La version officielle en amont ne rend pas publics certains états sous-jacents. Ce fork ajoute des interfaces sous `astrbot/api/**` afin d'exposer ces états.

Le répertoire `astrbot/api/` compte 10 fichiers nouveaux ou modifiés au total, dont 8 modules fonctionnels et 2 fichiers auxiliaires. Chaque module fonctionnel fournit une fonction `available()`. Dans l'environnement d'origine en amont, `available()` renvoie `False`.

| Module | Description des responsabilités | Interfaces principales |
|---|---|---|
| `api.turns` | Évaluation de l'état du tour, récupération du texte brut fusionné et des images | `is_current` / `merged_text` / `merged_image_urls` / `mark_sent` |
| `api.proactive` | Génération de réponses proactives intégrée au persona et à la chaîne de mémoire | `generate_with_persona` / `persona_available` |
| `api.delivery` | Détermination de la stratégie de livraison, distinction entre messages texte et livraison de fichiers | `resolve` / `has_code_delivery` / `code_task_spec` |
| `api.permissions` | Détermination de l'autorisation d'exécution, distinction entre statut d'administrateur et autorisation par exécution | `execution_denial` / `is_admin` |
| `api.media` | Détermination de la disponibilité de l'entrée visuelle et détection des légendes d'images | `has_visual_input` / `image_input_available` / `has_image_caption` |
| `api.content` | Détermination du type de segment de message | `is_text_part` / `is_image_part` |
| `api.runtime` | Chemins d'exécution, formatage de l'heure, téléchargement d'images et mode temporel | `get_astrbot_data_path` / `download_image_by_url` / `hook_timing_mode` |
| `api.embedding` | Détermination du fournisseur d'embedding | `is_embedding_provider` |
| `api.event.extras` | Vecteur d'informations supplémentaires d'événement | Voir protocole d'informations supplémentaires d'événement |
| `api._bridge` | Couche de pont interne pour la coordination inter-modules ; les plugins ne doivent pas l'appeler directement | — |

Dans la version originale en amont, `Context.llm_generate` appelle directement le fournisseur de modèle sous-jacent, contournant le hook `on_llm_request`, ce qui rend inopérants les plugins de persona et de mémoire. `generate_with_persona` exécute d'abord le hook de requête, permettant à ces deux plugins d'intervenir normalement.

## Options de configuration

4 nouvelles options de configuration ont été ajoutées, dont les valeurs par défaut sont toutes conformes au comportement officiel en amont.

| Clé de configuration | Valeur par défaut | Description |
|---|---|---|
| `execution_gate_mode` | `legacy` | Mode d'autorisation d'exécution. Par défaut identique à l'amont ; défini sur `strict` pour exiger que les messages demandent explicitement l'exécution |
| `hook_timing_mode` | `legacy` | Chronologie de déclenchement du hook de complétion. Défini sur `enhanced`, le hook se déclenche avant l'envoi de la réponse |
| `direct_turn_quiet_sec` | `4` | Fenêtre de silence d'agrégation des messages QQ en secondes. Défini sur `0` pour désactiver l'agrégation et traiter immédiatement |
| `lightweight_proactive_tools` | Liste (29 éléments au total) | Liste blanche d'outils proactifs légers |

## Compatibilité

Le numéro de version est `4.29.4+mtn1`. La mention `+mtn1` correspond au segment local de PEP 440, qui est ignoré lors des comparaisons d'intervalles de versions.

| Style de déclaration | Exemple | Décision de compatibilité |
|---|---|---|
| Déclaration d'intervalle | `>=4.16,<5` | Compatible |
| Correspondance de référence | `==4.29.4`, `~=4.28.0` | Compatible |
| Exigence de version supérieure | `>=4.29` | Rejetée |
| Correspondance stricte d'égalité | `===4.29.4` | Rejetée (les règles de PEP 440 exigent l'égalité stricte des chaînes) |

Lors des tests par rapport à la version de référence, les deux suites (version maintenue et version amont) passent ; les quelques écarts connus en amont sont enregistrés séparément.

## Installation et exécution

Nécessite Python 3.12 ou supérieur.

Pas encore publié sur PyPI ; `pip install astrbot-maintained` ne fonctionnera pas.

Le paquet de distribution s'appelle `astrbot-maintained`, tandis que le nom d'importation Python est également `astrbot`. Désinstallez la version officielle avant l'installation pour éviter les conflits de nom d'importation.

### Installation via wheel

Téléchargez le fichier `.whl` depuis la page Releases. Le nom de fichier contient le caractère `+`, ce qui nécessite des guillemets ou un échappement dans certains shells :

```bash
pip uninstall -y astrbot
pip install ./astrbot_maintained-4.29.4+mtn1-py3-none-any.whl
astrbot run
```

Après l'installation, lancez l'application et accédez à `http://localhost:6185` dans votre navigateur pour ouvrir le panneau d'administration.

### Exécution depuis les sources

Après avoir cloné ce dépôt, lancez avec `uv` :

```bash
uv sync && uv run main.py
```

### Construire le wheel soi-même

Lors de la création d'un artefact wheel incluant le panneau WebUI par vous-même, vous devez spécifier la variable d'environnement de build :

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

Si cette variable d'environnement n'est pas définie, les fichiers statiques de WebUI ne seront pas inclus dans le livrable de build.

## Vérification des mises à jour et synchronisation avec l'amont

La vérification des mises à jour du panneau pointe par défaut vers les Releases de ce dépôt :

- `update_source`: `https://api.github.com/repos/Chenamel/astrbot-maintained/releases`
- `update_repository`: `https://github.com/Chenamel/astrbot-maintained`

L'architecture en amont de `v4.29+` a changé et ne contient pas les API sous-jacentes ajoutées ici. Une mise à jour directe vers la version officielle depuis le panneau écrasera les fichiers centraux modifiés, entraînant l'absence d'interfaces et des erreurs d'exécution.

Si vous devez rétablir le suivi des mises à jour officielles, modifiez `update_source` par `https://api.soulter.top/releases` et `update_repository` par `https://github.com/AstrBotDevs/AstrBot` dans le panneau d'administration.

## Documentation

- Détails d'installation, déploiement par conteneur, comment vérifier que vous utilisez ce fork : [`docs/maintained/install.md`](./docs/maintained/install.md)
- Guide de démarrage en 5 minutes pour les auteurs de plugins : [`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md)
- Paramètres, valeurs de retour et exemples d'appel pour chaque API : [`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md)
- Contraintes de conception des API et mécanismes de dégradation : [`docs/maintained/api-contract.md`](./docs/maintained/api-contract.md)
- Pourquoi une telle séparation en couches : [`docs/maintained/design.md`](./docs/maintained/design.md)
- Ce qui a changé par rapport à l'amont : [`CHANGELOG.md`](./CHANGELOG.md)
- Registre des modifications du core (SHA-256, vérifiable par script) : [`maintained/installed_manifest.json`](./maintained/installed_manifest.json)

## À propos de la terminologie historique

Une version antérieure de ce README désignait cette couche d'interfaces sous le terme de « porte dérobée » (backdoor) ; elles sont désormais désignées uniformément comme « interfaces ».

Les sites miroirs et les caches des moteurs de recherche peuvent encore afficher l'ancienne formulation, ce qui ne reflète pas la position actuelle.

Ces modules sont des API Python publiques, documentées et consultables ligne par ligne, ne contenant aucun point d'accès dissimulé contournant l'authentification.

## Licence

Ce projet est open source sous licence AGPL-3.0-or-later, conformément à l'amont. Voir le fichier LICENSE pour plus de détails.

Ce projet est une branche maintenue indépendante et n'a aucun lien d'affiliation avec les auteurs amont.
