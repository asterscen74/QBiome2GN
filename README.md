# QBiome2GN

PyQGIS script to transfer data from a QBiome project to a GeoNature instance.

## What you get

A Python script only usable in a QBiome project on QGIS (you need a `Flore` and a `Relevé Phytosociologique` layer).
It will import data from the QBiome project to the Occtax Module (you need phytosociological added field in your occtax module).

Every observation point create a survey with one observation (not logical, but for know a survey in GeoNature can only have one geometry).
Waiting for the Phytosociological Module.

Based on your GeoNature's nomenclature to get your dataset and user list.

## How it works

### Setting the script

Inside a QBiome project on QGIS:

- open the Python Console
- inside the console, opent the script editor
- open the script `QBiome2GN.py` file in the script editor
- change the variables principally `geonature_domain`

### Launch the script

Once the variables are set, launch the script.
A first dialog will appear asking for your GeoNature credentials, you can save it to QGIS Authentication Database if needed.
Once you're authenticated, a second window will appear asking you to select a dataset and one or mutliple observers (they are fetched from your GeoNature's instance threw the API).
After clicking "OK" all selected data from the 'Flore' layer will be sent to Occtax.

### Specific parameters

A attribute join is made with the `Flore` layer and the `Relevé Phytosociologique` layer, all fields frome the second layer are added to the first one with a prefix, you can modify this prefix in the script variables.

The script is checking some fields in your layers and stops if it finds NULL values inside those fields.
You can modify the checked fields in the list `fields_to_check` in the script variables.

## What's missing

For now some fields from QBiome are not treated, here is a list of those fields :

- Autre
- Doute
- Unite
- Statut
- Altitude (GeoNature is used to calculate altitude)
- Phenologie
- uuid (uuid is recreated in GeoNature)
- Zone Humide
- Recouvrement de la ZH en %
- Habitat
- releve_type
- Stade de dégradation

All observations are added with the same observer(s) and determiner(s)
