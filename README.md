# Calyps'HOME - Intégration Home Assistant (Cloud)

Intégration personnalisée pour contrôler vos volets roulants Calyps'HOME via Home Assistant et le cloud Calyps'HOME.

## ⚠️ Avertissement / Disclaimer

**Ce composant personnalisé est indépendant et n'est en aucun cas affilié à la marque Calyps'HOME.**

- ✋ **Projet non officiel** : Ce composant a été développé de manière indépendante et n'est pas supporté par le fabricant Calyps'HOME
- 🚫 **Aucune garantie** : Ce logiciel est fourni "tel quel", sans aucune garantie de fonctionnement
- ⚠️ **Utilisation à vos risques** : L'auteur ne peut être tenu responsable de tout dysfonctionnement, dommage matériel ou perte de données résultant de l'utilisation de ce composant
- 🔧 **Support limité** : Le support technique est fourni sur la base du volontariat et sans engagement
- 📝 **Licence MIT** : Ce projet est fourni sous licence MIT - voir le fichier LICENSE pour plus de détails

**En utilisant ce composant, vous acceptez ces conditions.**

## Origine du projet

Ce dépôt est un fork du projet original [saniho/calypshome](https://github.com/saniho/calypshome).

Le projet original fonctionnait **en mode local uniquement** : il communiquait directement avec la box Calyps'HOME sur le réseau local.

Ce fork a été réécrit pour basculer vers un **fonctionnement entièrement cloud** : l'intégration communique désormais avec l'API cloud d'Avidsen (`calypshome.avidsen.one`) exactement comme le fait l'application mobile officielle. Cela permet d'utiliser l'intégration depuis n'importe où, sans dépendance au réseau local.

Merci à l'auteur original pour le travail de base et les idées initiales.

## Fonctionnalités

- ✅ Découverte automatique de tous les volets roulants
- ✅ Découverte automatique des sondes (température et luminosité)
- ✅ Ouverture / Fermeture / Arrêt
- ✅ Positionnement précis (0-100%)
- ✅ Mise à jour en temps réel via WebSocket (volets, température, luminosité)
- ✅ Configuration via l'interface utilisateur
- ✅ Compatible avec toutes les automatisations Home Assistant
- ✅ Fonctionne depuis n'importe quel réseau (cloud)

## Installation

### Méthode 1 : Installation via HACS

1. Ajoutez ce dépôt comme dépôt personnalisé dans HACS (catégorie : Integration)
2. Installez l'intégration Calyps'HOME
3. Redémarrez Home Assistant
4. Allez dans **Paramètres** → **Appareils et services**
5. Cliquez sur **+ Ajouter une intégration**
6. Recherchez "Calyps'HOME"
7. Entrez vos informations de connexion :
   - **Email** : Votre email de connexion au cloud Calyps'HOME
   - **Mot de passe** : Votre mot de passe

### Méthode 2 : Installation manuelle

1. Copiez le dossier `custom_components/calypshome_cloud` dans votre dossier `config/custom_components/` de Home Assistant
2. Redémarrez Home Assistant
3. Allez dans **Paramètres** → **Appareils et services**
4. Cliquez sur **+ Ajouter une intégration**
5. Recherchez "Calyps'HOME"
6. Entrez vos identifiants de connexion au cloud Calyps'HOME

## Configuration

Après l'installation, tous vos volets roulants seront automatiquement découverts et ajoutés comme entités `cover.*` dans Home Assistant.

## Utilisation

### Dans l'interface Lovelace

Les volets apparaîtront automatiquement dans votre interface avec les contrôles standard :
- Bouton Ouvrir
- Bouton Fermer
- Bouton Stop
- Curseur de position

### Dans les automatisations

```yaml
# Exemple : Fermer tous les volets au coucher du soleil
automation:
  - alias: "Fermer volets au coucher du soleil"
    trigger:
      platform: sun
      event: sunset
    action:
      - service: cover.close_cover
        target:
          entity_id: all
```

### Dans les scripts

```yaml
# Exemple : Ouvrir la cuisine à 50%
script:
  cuisine_mi_ouvert:
    sequence:
      - service: cover.set_cover_position
        target:
          entity_id: cover.cuisine
        data:
          position: 50
```

### Via les services

```yaml
# Ouvrir un volet (remplacez par le nom de votre volet)
service: cover.open_cover
target:
  entity_id: cover.votre_volet

# Fermer un volet
service: cover.close_cover
target:
  entity_id: cover.votre_volet

# Position spécifique (0 = fermé, 100 = ouvert)
service: cover.set_cover_position
target:
  entity_id: cover.votre_volet
data:
  position: 75

# Arrêter un volet en mouvement
service: cover.stop_cover
target:
  entity_id: cover.votre_volet
```

## Entités créées

Pour chaque volet, une entité `cover.*` sera créée avec :
- **État** : open, closed, opening, closing
- **Position** : 0-100%

## Dépannage

### Les volets ne sont pas découverts

1. Vérifiez vos identifiants de connexion au cloud
2. Consultez les logs : **Paramètres** → **Journaux** → Recherchez "calypshome_cloud"
3. Vérifiez que votre compte Calyps'HOME contient bien des volets

### Les commandes ne fonctionnent pas

1. Vérifiez que vos commandes fonctionnent sur l'interface ou l'application d'origine
2. Vérifiez les logs Home Assistant
3. Assurez-vous que votre compte cloud est valide

### Logs

Pour activer les logs détaillés, ajoutez dans `configuration.yaml` :

```yaml
logger:
  default: info
  logs:
    custom_components.calypshome_cloud: debug
```

## Développement

Ce composant a été développé en analysant le trafic HTTP de l'application mobile officielle Calyps'HOME afin de reproduire fidèlement les appels vers l'API cloud Avidsen.

## À propos de ce projet

Ce composant est un projet **communautaire non officiel** créé pour permettre l'intégration des volets roulants Calyps'HOME dans Home Assistant via le cloud.

**Relation avec la marque** :
- ❌ Non développé par Calyps'HOME
- ❌ Non validé par Calyps'HOME
- ❌ Non supporté officiellement par Calyps'HOME
- ✅ Développé par la communauté pour la communauté

**Crédits** :
- Projet original (mode local) : [saniho/calypshome](https://github.com/saniho/calypshome)
- Ce fork : réécriture complète en mode cloud

**Responsabilités** :
- L'auteur de ce composant n'est pas responsable des dysfonctionnements de votre installation
- Calyps'HOME n'est pas responsable des problèmes liés à l'utilisation de ce composant
- Toute modification de la configuration de votre compte se fait sous votre responsabilité

## Licence

MIT License - Ce logiciel est fourni sans aucune garantie.

## Support

Pour toute question ou problème :
- 📖 Consultez d'abord la documentation
- 🔍 Vérifiez les issues existantes sur GitHub
- 💬 Ouvrez une nouvelle issue si nécessaire

**Note** : Pour les problèmes matériels ou liés au service Calyps'HOME lui-même, contactez directement le support officiel de Calyps'HOME.