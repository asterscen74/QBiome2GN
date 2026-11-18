# -*- coding: utf-8 -*-

# Standard libs
import json

# PyQt libs
from qgis.PyQt.QtWidgets import (
    QLineEdit,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QComboBox,
    QCheckBox,
    QMessageBox,
)
from qgis.PyQt.QtCore import (
    pyqtSignal,
    QObject,
    QJsonDocument,
    QByteArray,
    Qt,
)
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.PyQt.Qt import QUrl

# QGIS lib
from qgis.gui import (
    QgsAuthConfigSelect,
    QgsCheckableComboBox,
)
from qgis.core import (
    QgsProject,
    QgsNetworkAccessManager,
    QgsWkbTypes,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    NULL,
    QgsApplication,
    QgsAuthMethodConfig,
    QgsDataSourceUri,
    QgsVectorLayerJoinInfo,
    QgsVectorLayerUtils,
)
from qgis.utils import iface

# VARIABLE DECLARATION
geonature_crs = 4326
geonature_domain = ""
layer_name_releve = "Relevé Phytosociologique"
layer_name_flore = "Flore"
join_field_prefix = "releve_"
fields_to_check = [
            "Releve",
            "Nom",
            "CD_REF",
            # "Denombrement",
            # "Nombre",
            "Strate",
            "Releve_Recouvrement",
            "Date",
            # "Heure",
            # join_field_prefix + "Precision",
            # join_field_prefix + "Exposition",
            # join_field_prefix + "Pente",
            # join_field_prefix + "Topographie",
            # join_field_prefix + "Roche_Mere",
            # join_field_prefix + "Etat_Ecologique",
            # join_field_prefix + "Gestion",
            # join_field_prefix + "Dynamique",
            # join_field_prefix + "Commentaire",
            # join_field_prefix + "Surface",
            # join_field_prefix + "Recouvrement_arboree",
            # join_field_prefix + "Hauteur_arboree",
            # join_field_prefix + "Recouvrement_arbustive",
            # join_field_prefix + "Hauteur_arbustive",
            # join_field_prefix + "Recouvrement_herbacee",
            # join_field_prefix + "Hauteur_herbacee",
            # join_field_prefix + "Recouvrement_muscinale",
            # join_field_prefix + "Hauteur_muscinale",
            # join_field_prefix + "Recouvrement_sol_nu",
            # join_field_prefix + "Recouvrement_litiere",
        ]


# Check if layers exists
if QgsProject.instance().mapLayersByName(
    layer_name_releve
) and QgsProject.instance().mapLayersByName(layer_name_flore):
    releve_phyto_layer = QgsProject.instance().mapLayersByName(
        layer_name_releve
    )[0]
    flore_layer = QgsProject.instance().mapLayersByName(
        layer_name_flore
    )[0]
    network_manager = QgsNetworkAccessManager()


# Global FUNCTION
def get_coord(layer, geometry_type, feature_id):
    """Transform a point geometry to reproject it to geonature's crs
    """
    if geometry_type == "Point":
        feature = layer.getFeature(feature_id)
        geom = feature.geometry()
        if layer.crs().postgisSrid() != geonature_crs:
            sourceCrs = QgsCoordinateReferenceSystem(layer.crs().postgisSrid())
            destCrs = QgsCoordinateReferenceSystem(geonature_crs)
            tr = QgsCoordinateTransform(
                sourceCrs, destCrs, QgsProject.instance()
            )
            geom.transform(tr)
        coord = [geom.asPoint().x(), geom.asPoint().y()]
        return coord


def join_attributes(
    layer,
    attribute_layer,
    join_field,
    target_field,
    join_field_prefix,
):
    """Create an attribute join between 2 layers
    https://gis.stackexchange.com/a/267784
    """
    joinObject = QgsVectorLayerJoinInfo()
    joinObject.setJoinLayerId(attribute_layer.id())
    joinObject.setJoinLayer(attribute_layer)
    joinObject.setJoinFieldName(join_field)
    joinObject.setTargetFieldName(target_field)
    joinObject.setUsingMemoryCache(True)
    joinObject.setPrefix(join_field_prefix)
    layer.addJoin(joinObject)


def launch_dlg(network_manager, properties, iface, flore_layer):
    """Launch the second dialog after the nomenclatures are downloaded
    """
    dialog = Dialog(
        network_manager,
        properties,
        flore_layer,
    )
    dialog.exec_()


class GetProperties(QObject):
    finished_dl_users = pyqtSignal()
    finished_dl = pyqtSignal()
    """Get nomenclatures from GeoNature
    The arguments are :
    - a network manager to realize the web request : QNetworkManager
    """

    def __init__(
        self,
        network_manager=None,
    ):
        super().__init__()
        self.network_manager = network_manager

        self.users = None
        self.datasets = None

        # This can be removed, it is used when multiple web request are made
        # at the same time QNetworkRequest is asynchronous so they can be
        # launch all at the same time from the same class.
        # In this script they are launch separetely
        self._pending_downloads = 0

        # Login to GeoNature with a Login class
        self.login = Login(network_manager)

        # Connect a function to the finished signal of the login request to
        # launch the nomenclature's download with the login info.
        # The download only starts if the login infos are correct.
        self.login.finished_login.connect(lambda: self.get_users())
        if not self.login.accepted:
            self.login.exec_()

        self.finished_dl_users.connect(lambda: self.get_datasets())

    @property
    def pending_downloads(self):
        return self._pending_downloads

    def get_users(self):
        self._pending_downloads += 1
        url = QUrl("https://" + geonature_domain + "/api/users/menu/1")
        request = QNetworkRequest(url)
        # Define request properties (cookie, header)
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
        )
        request.setRawHeader(
            QByteArray("Cookie".encode()),
            QByteArray(
                str(
                    "token="
                    + str(
                        self.login.cookies.cookiesForUrl(
                            QUrl("https://" + geonature_domain)
                        )[0]
                        .value()
                        .data()
                        .decode()
                    )
                ).encode()
            ),
        )
        # Start the request
        reply = self.network_manager.get(request)
        # Connect a function to the finished signal of the request to get the
        # result or the error
        reply.finished.connect(lambda: self.handle_finished_users(reply))

    def handle_finished_users(self, reply):
        self._pending_downloads -= 1
        # Print the error if the request is aborted
        if reply.error() != QNetworkReply.NetworkError.NoError:
            print(f"code: {reply.error()} message: {reply.errorString()}")
        else:
            # Get the reply data as json and emit a signal when the request is
            # over.
            data_request = reply.readAll().data().decode()
            data = json.loads(data_request)
            if self.pending_downloads == 0:
                self.users = data
                self.finished_dl_users.emit()
        reply.deleteLater()

    def get_datasets(self):
        self._pending_downloads += 1
        url = QUrl(
            "https://" + geonature_domain + "/api/meta/datasets?orderby=dataset_name"  # noqa: E501
        )
        request = QNetworkRequest(url)
        # Define request properties (cookie, header)
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
        )
        request.setRawHeader(
            QByteArray("Cookie".encode()),
            QByteArray(
                str(
                    "token="
                    + str(
                        self.login.cookies.cookiesForUrl(
                            QUrl("https://" + geonature_domain)
                        )[0]
                        .value()
                        .data()
                        .decode()
                    )
                ).encode()
            ),
        )
        json = {"active": True, "module_code": "OCCTAX", "create": "OCCTAX"}
        document = QJsonDocument(json)
        # Start the request
        reply = self.network_manager.post(request, document.toJson())
        # Connect a function to the finished signal of the request to get
        # the result or the error
        reply.finished.connect(lambda: self.handle_finished_ds(reply))

    def handle_finished_ds(self, reply):
        self._pending_downloads -= 1
        # Print the error if the request is aborted
        if reply.error() != QNetworkReply.NetworkError.NoError:
            print(f"code: {reply.error()} message: {reply.errorString()}")
        else:
            # Get the reply data as json and emit a signal when the request is
            # over
            data_request = reply.readAll().data().decode()
            data = json.loads(data_request)
            if self.pending_downloads == 0:
                self.datasets = data
                self.finished_dl.emit()
        reply.deleteLater()


class Login(QDialog):
    finished_login = pyqtSignal()

    def __init__(self, network_manager=None):
        """
        Constructor

        Login window used to connect to a GeoNature instance.
        The cookie fetched from the connection is kept into the
        network_manager.
        """
        QDialog.__init__(self)
        self.network_manager = network_manager

        self.accepted = None
        self.cookies = None
        self.success = None
        self._pending_downloads = 0
        self.role_id = 0

        # QGIS authentification manager
        self.manager = QgsApplication.authManager()
        auth_configs = self.manager.availableAuthMethodConfigs()
        for config_id in auth_configs:
            if auth_configs[config_id].name() == "geonature":
                self.success, self.manager_config = (
                    self.manager.loadAuthenticationConfig(
                        config_id, QgsAuthMethodConfig(), full=True
                    )
                )
            else:
                pass

        # Set dialog minimum size
        self.setMinimumSize(250, 150)
        # Set layout
        self.layout = QVBoxLayout()

        self.setWindowTitle(self.tr("Connect to GeoNature"))

        # Label for the wrong password error message.
        self.wrongPasswordLabel = QLabel(self)
        self.wrongPasswordLabel.setText("")
        self.layout.addWidget(self.wrongPasswordLabel)

        # Checkbox to save credential in QGIS
        self.save_credentials = QCheckBox(self)
        self.save_credentials.setChecked(True)
        self.save_credentials.setText(
            self.tr("Save GeoNature's credentials to QGIS")
        )
        self.layout.addWidget(self.save_credentials)

        self.mAuthConfigSelect = QgsAuthConfigSelect()
        self.layout.addWidget(self.mAuthConfigSelect)

        # User login informations
        self.user_layout = QHBoxLayout()
        self.user_label = QLabel(self)
        self.user_label.setText(self.tr("Username :"))
        self.user_layout.addWidget(self.user_label)
        self.lne_user = QLineEdit(self)
        self.lne_user.setText("")
        self.user_layout.addWidget(self.lne_user)
        self.layout.addLayout(self.user_layout)

        # User password informations
        self.password_layout = QHBoxLayout()
        self.password_label = QLabel(self)
        self.password_label.setText(self.tr("Password :"))
        self.password_layout.addWidget(self.password_label)
        self.lne_password = QLineEdit(self)
        self.lne_password.setText("")
        self.lne_password.setEchoMode(QLineEdit.Password)
        self.password_layout.addWidget(self.lne_password)
        self.layout.addLayout(self.password_layout)

        if self.success:
            # If the authentification configuration already exists in QGIS
            # just use it and complete the logins
            self.lne_user.setText(self.manager_config.configMap()["username"])
            self.lne_password.setText(
                self.manager_config.configMap()["password"]
            )

        # Button to validate the login and password.
        ok_button = QPushButton(self.tr("OK"), self)
        ok_button.clicked.connect(self.check_password)
        ok_button.resize(100, 25)
        ok_button.move(350, 170)
        self.layout.addWidget(ok_button)

        self.setLayout(self.layout)

    @property
    def pending_downloads(self):
        return self._pending_downloads

    def decript_AuthConfigSelect(self):
        if self.mAuthConfigSelect.configId():
            authCfg = self.mAuthConfigSelect.configId()
            quri = QgsDataSourceUri()
            quri.setParam("authcfg", authCfg)
            quri.setParam(
                "url", "https://" + geonature_domain + "/api/auth/login"
            )
            self.usr = quri.uri().split("user='")[1].split("' ", 1)[0]
            self.pwd = quri.uri().split("password='")[1].split("' ", 1)[0]

    def check_password(self):
        # Test if the user wrote something
        if self.lne_password.text() != "" or self.mAuthConfigSelect.configId():
            self.decript_AuthConfigSelect()
            url = QUrl(
                "https://" + geonature_domain + "/api/auth/login"
            )
            data_json = {
                "login": (
                    self.usr
                    if self.mAuthConfigSelect.configId()
                    else self.lne_user.text()
                ),
                "password": (
                    self.pwd
                    if self.mAuthConfigSelect.configId()
                    else self.lne_password.text()
                ),
            }
            request = QNetworkRequest(url)
            request.setHeader(
                QNetworkRequest.ContentTypeHeader, "application/json"
            )
            document = QJsonDocument(data_json)
            reply = self.network_manager.post(request, document.toJson())
            reply.finished.connect(lambda: self.handle_finished(reply))
            self._pending_downloads += 1

    def handle_finished(self, reply):
        self._pending_downloads -= 1
        # If reply is an error or reply is a redirection, login is not accepted
        if (
            reply.error() != QNetworkReply.NoError
            or reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) != 200
        ):
            # Error code 299 means the logins are invalid
            # Redirection not equal to 200 means a redirection happened
            if reply.error() == 299:
                self.wrongPasswordLabel.setText(self.tr("Invalid login info"))
                self.lne_password.setText("")
                print(f"code: {reply.error()} message: {reply.errorString()}")
            else:
                print(f"code: {reply.error()} message: {reply.errorString()}")
        else:
            self.cookies = self.network_manager.cookieJar()
            if self.lne_password.text() != "":
                if self.save_credentials.isChecked():
                    if self.success:
                        # If the authenfication configuration already exists,
                        # modify it with the new values
                        self.manager_config.setConfigMap(
                            {
                                "password": self.lne_password.text(),
                                "username": self.lne_user.text(),
                            }
                        )
                        self.manager.storeAuthenticationConfig(
                            self.manager_config, True
                        )
                        self.role_id = json.loads(
                            reply.readAll().data().decode()
                        )[
                            "user"
                        ]["id_role"]
                    else:
                        # If the authenfication configuration doesn't exists,
                        # create it
                        cfg = QgsAuthMethodConfig()
                        cfg.setConfig("password", self.lne_password.text())
                        cfg.setName("geonature")
                        cfg.setMethod("Basic")
                        cfg.setConfig("username", self.lne_user.text())
                        self.manager.storeAuthenticationConfig(cfg)
                else:
                    pass
                # delete sensitive informations...
                # even if it's in the database now...
                del self.lne_user
                del self.lne_password
                self.accepted = True
                # Add the cookie created with the login to the request
                self.network_manager.setCookieJar(self.cookies)
                self.close()
            if self.pending_downloads == 0:
                self.finished_login.emit()
        reply.deleteLater()


class Dialog(QDialog):
    def __init__(
        self,
        network_manager,
        properties,
        flore_layer,
    ):
        """
        Simple Dialog to select the observer and the dataset.
        All features or selected features will be imported with
        the same observer/determiner and dataset.
        """
        QDialog.__init__(self)

        self.setWindowTitle("QBiome2GN")

        if len(flore_layer.selectedFeatureIds()) == 0:
            selection = False
        else:
            selection = True
        qflore_datasets = QgsVectorLayerUtils.getValues(
            flore_layer, "Projet", selectedOnly=selection
        )[0]
        qflore_users = QgsVectorLayerUtils.getValues(
            flore_layer, "Observateur", selectedOnly=selection
        )[0]
        self.resize(600, 204)

        self.layout = QVBoxLayout()
        self.variable_layout = QGridLayout()

        self.select_obs_label = QLabel(self)
        self.select_obs_label.setText(
            "Choix de l'observateur & déterminateur : "
        )
        self.variable_layout.addWidget(self.select_obs_label, 0, 0)

        self.select_user_combo_box = QgsCheckableComboBox(self)
        n = 0
        for user in properties.users:
            cap = "".join([c for c in user["nom_complet"] if c.isupper()])
            words = user["nom_complet"].split(" ")
            famille = ""
            prenom = ""
            for word in words:
                if word.replace("-", "") in cap:
                    if famille == "":
                        famille = word
                    else:
                        famille = famille + " " + word
                else:
                    if prenom == "":
                        prenom = word
                    else:
                        prenom = prenom + " " + word
            self.select_user_combo_box.insertItem(
                n, user["nom_complet"], user["id_role"]
            )
            if qflore_users[0] == prenom + " " + famille.title():
                self.select_user_combo_box.setItemCheckState(
                    n, Qt.CheckState.Checked
                )
            n = n + 1
        self.variable_layout.addWidget(self.select_user_combo_box, 0, 1)

        self.select_ds_label = QLabel(self)
        self.select_ds_label.setText("Choix du jeu de données : ")
        self.variable_layout.addWidget(self.select_ds_label, 1, 0)

        self.select_ds_combo_box = QComboBox(self)
        n = 0
        select_index = n
        for dataset in properties.datasets:
            self.select_ds_combo_box.insertItem(
                n, dataset["dataset_name"], dataset["id_dataset"]
            )
            if qflore_datasets[0] == dataset["dataset_name"]:
                select_index = n
            n = n + 1
        self.variable_layout.addWidget(self.select_ds_combo_box, 1, 1)
        self.select_ds_combo_box.setCurrentIndex(select_index)

        self.layout.addLayout(self.variable_layout)

        # Button to validate the login and far_study_area_path.
        self.ok_button = QPushButton("OK", self)
        self.ok_button.clicked.connect(
            lambda: self.init_data_request(
                properties, network_manager, flore_layer
            )
        )
        self.layout.addWidget(self.ok_button)

        self.setLayout(self.layout)

    def init_data_request(
        self, properties, network_manager, flore_layer
    ):
        self.data_request = ImportData(
            self,
            properties.login,
            network_manager,
            flore_layer,
        )

        self.accept()
        self.close()


class ImportData(QObject):
    finished_dl = pyqtSignal()
    """ Class to import all features or selected features from a layer
    into the Occtax Module. It will create a survey and an observation
    for every feature.
    """

    def __init__(
        self,
        parent=None,
        login=None,
        network_manager=None,
        flore_layer=None,
    ):
        super().__init__()
        self.login = login
        self.network_manager = network_manager
        self.flore_layer = flore_layer

        self.user_id = list(
            map(
                int, parent.select_user_combo_box.checkedItemsData()
            )
        )
        self.user_name = ", ".join(
            parent.select_user_combo_box.checkedItems()
        )

        self.dataset_id = parent.select_ds_combo_box.currentData()

        if len(self.flore_layer.selectedFeatureIds()) == 0:
            self.flore_layer.selectAll()
        self.list_id = self.flore_layer.selectedFeatureIds()

        valid_fields = self.verif()
        if valid_fields is True:
            self.flore_layer.removeSelection()
            self._pending_downloads = 0
            self._pending_features = len(self.list_id)
            self.geo_download(self.list_id[self.pending_features - 1])
        else:
            self.flore_layer.removeSelection()
            msg = QMessageBox()
            msg.warning(
                None,
                "Champ avec valeur NULL",
                "Le champ {field} à une valeur NULL".format(
                    field=valid_fields,
                )
            )

    @property
    def pending_downloads(self):
        return self._pending_downloads

    @property
    def pending_features(self):
        return self._pending_features

    def verif(self):
        """Check NULL values in fields in the list fields.
        If one NULL value is spoted, script is stopped.
        """
        for field in fields_to_check:
            values_in_field = QgsVectorLayerUtils.getValues(
                self.flore_layer,
                field,
                selectedOnly=True,
            )[0]
            if NULL in values_in_field:
                return field
        return True

    def check_if_value_is_not_null(self, value, label, comment):
        """Check NULL value in a field.
        If the field is not NULL, it is used to create a survey comment.
        """
        if value != NULL:
            comment = comment + "\n" + label + " " + str(value)
        else:
            pass
        return comment

    def create_comment(self, feature):
        """Create a survey comment based on some fields.
        Every value of a field is tested.
        """
        comment = "Releve Phytosocio : " + str(feature["Releve"])
        comment_content = {
            "Exposition :": feature[join_field_prefix + "Exposition"],
            "Pente (en °):": feature[join_field_prefix + "Pente"],
            "Topographie :": feature[join_field_prefix + "Topographie"],
            "Roche mère :": feature[join_field_prefix + "Roche_Mere"],
            "Etat écologique :": feature[join_field_prefix + "Etat_Ecologique"],  # noqa: E501
            "Gestion :": feature[join_field_prefix + "Gestion"],
            "Dynamique :": feature[join_field_prefix + "Dynamique"],
            "Commentaire :": feature[join_field_prefix + "Commentaire"],
        }
        for label in comment_content:
            comment = self.check_if_value_is_not_null(
                comment_content[label], label, comment
            )
        return comment

    def geo_download(self, feature_id):
        """Get altitude from GeoNature's API.
        """
        geom_type_text = QgsWkbTypes.geometryDisplayString(
            self.flore_layer.geometryType()
        )
        url = QUrl("https://" + geonature_domain + "/api/geo/altitude")
        request = QNetworkRequest(url)
        request.setHeader(
            QNetworkRequest.ContentTypeHeader, "application/json"
        )
        coord = get_coord(
            self.flore_layer, geom_type_text, feature_id
        )
        json = {"geometry": {"type": geom_type_text, "coordinates": coord}}
        document = QJsonDocument(json)
        self.network_manager.setCookieJar(self.login.cookies)
        reply = self.network_manager.post(request, document.toJson())
        reply.finished.connect(
            lambda: self.creation_survey(
                geom_type_text,
                coord,
                feature_id,
                reply,
            )
        )

    def creation_survey(
        self,
        geometry_type,
        coordinates,
        feature_id,
        geo_reply,
    ):
        """POST Request to create a survey in the OCCTAX Module
        """
        feature = self.flore_layer.getFeature(feature_id)
        altitude = json.loads(geo_reply.readAll().data().decode())
        url = QUrl(
            "https://" + geonature_domain + "/api/occtax/OCCTAX/only/releve"  # noqa: E501
        )
        request = QNetworkRequest(url)
        request.setHeader(
            QNetworkRequest.ContentTypeHeader, "application/json"
        )
        comment = self.create_comment(feature)
        json_data = {
            "geometry": {"type": geometry_type, "coordinates": coordinates},
            "properties": {
                "id_dataset": self.dataset_id,
                "id_digitiser": self.login.role_id,
                "id_module": 4,
                "date_min": (
                    None
                    if feature["Date"] == NULL
                    else feature["Date"].toString("yyyy-MM-dd")
                ),
                "date_max": (
                    None
                    if feature["Date"] == NULL
                    else feature["Date"].toString("yyyy-MM-dd")
                ),
                "hour_min": (
                    None
                    if feature["Heure"] == NULL
                    else feature["Heure"].toString("hh:mm")
                ),
                "hour_max": (
                    None
                    if feature["Heure"] == NULL
                    else feature["Heure"].toString("hh:mm")
                ),
                "altitude_min": altitude["altitude_min"],
                "altitude_max": altitude["altitude_max"],
                "depth_min": None,
                "depth_max": None,
                "place_name": (
                    None
                    if feature["Releve"] == NULL
                    else feature["Releve"]
                ),
                "meta_device_entry": "web",
                "comment": comment,
                "cd_hab": None,
                "id_nomenclature_tech_collect_campanule": 316,
                "observers": self.user_id,
                "observers_txt": None,
                "id_nomenclature_grp_typ": 132,
                "grp_method": None,
                "id_nomenclature_geo_object_nature": 173,
                "precision": (
                    None
                    if feature[join_field_prefix + "Precision"] == NULL
                    else feature[join_field_prefix + "Precision"]
                ),
                "additional_fields": {
                    "surface_releve": (
                        None
                        if feature[join_field_prefix + "Surface"] == NULL
                        else feature[join_field_prefix + "Surface"]
                    ),
                    "arboree_recouvrement": (
                        None
                        if feature[join_field_prefix + "Recouvrement_arboree"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Recouvrement_arboree"]  # noqa: E501
                    ),
                    "arboree_hmoy": (
                        None
                        if feature[join_field_prefix + "Hauteur_arboree"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Hauteur_arboree"] / 100  # noqa: E501
                    ),
                    "arbustive_recouvrement": (
                        None
                        if feature[join_field_prefix + "Recouvrement_arbustive"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Recouvrement_arbustive"]  # noqa: E501
                    ),
                    "arbustive_hmoy": (
                        None
                        if feature[join_field_prefix + "Hauteur_arbustive"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Hauteur_arbustive"] / 100  # noqa: E501
                    ),
                    "herbacee_recouvrement": (
                        None
                        if feature[join_field_prefix + "Recouvrement_herbacee"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Recouvrement_herbacee"]  # noqa: E501
                    ),
                    "herbacee_hmoy": (
                        None
                        if feature[join_field_prefix + "Hauteur_herbacee"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Hauteur_herbacee"] / 100  # noqa: E501
                    ),
                    "muscinale_recouvrement": (
                        None
                        if feature[join_field_prefix + "Recouvrement_muscinale"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Recouvrement_muscinale"]  # noqa: E501
                    ),
                    "muscinale_hmoy": (
                        None
                        if feature[join_field_prefix + "Hauteur_muscinale"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Hauteur_muscinale"] / 100  # noqa: E501
                    ),
                    "sol_nu_recouvrement": (
                        None
                        if feature[join_field_prefix + "Recouvrement_sol_nu"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Recouvrement_sol_nu"]
                    ),
                    "litiere_recouvrement": (
                        None
                        if feature[join_field_prefix + "Recouvrement_litiere"] == NULL  # noqa: E501
                        else feature[join_field_prefix + "Recouvrement_litiere"]  # noqa: E501
                    ),
                },
            },
        }
        document = QJsonDocument(json_data)
        reply = self.network_manager.post(request, document.toJson())
        reply.finished.connect(lambda: self.add_observation(reply, feature))

    def add_observation(self, reply, feature):
        """POST Request to create an observatuion in the OCCTAX Module.
        It will be apart of the survey created previously.
        """
        data_request = reply.readAll().data().decode()
        data = json.loads(data_request)
        url = QUrl(
            "https://" + geonature_domain + "/api/occtax/OCCTAX/releve/"  # noqa: E501
            + str(data["id"])
            + "/occurrence"
        )
        request = QNetworkRequest(url)
        request.setHeader(
            QNetworkRequest.ContentTypeHeader, "application/json"
        )
        json_data = {
            "id_nomenclature_obs_technique": 41,
            "id_nomenclature_bio_condition": 157,
            "id_nomenclature_bio_status": 29,
            "id_nomenclature_naturalness": 160,
            "id_nomenclature_exist_proof": 81,
            "id_nomenclature_behaviour": 552,
            "id_nomenclature_observation_status": 88,
            "id_nomenclature_blurring": 175,
            "id_nomenclature_source_status": 75,
            "determiner": self.user_name,
            "id_nomenclature_determination_method": 445,
            "nom_cite": (
                None
                if feature["Nom"] == NULL
                else feature["Nom"]
            ),
            "cd_nom": (
                None
                if feature["CD_REF"] == NULL
                else feature["CD_REF"]
            ),
            "meta_v_taxref": None,
            "sample_number_proof": None,
            "digital_proof": None,
            "non_digital_proof": None,
            "comment": None,
            "additional_fields": {},
            "cor_counting_occtax": [
                {
                    "id_counting_occtax": None,
                    "id_nomenclature_life_stage": 1,
                    "id_nomenclature_sex": 171,
                    "id_nomenclature_obj_count": 146,
                    "id_nomenclature_type_count": (
                        92 if feature["Denombrement"] == "Précis" else 93 if feature["Denombrement"] == "Estimé" else 94  # noqa: E501
                    ),
                    "count_min": 1 if feature["Nombre"] == NULL else feature["Nombre"],  # noqa: E501
                    "count_max": 1 if feature["Nombre"] == NULL else feature["Nombre"],  # noqa: E501
                    "medias": [],
                    "additional_fields": {
                        "strate": (
                            None
                            if feature["Strate"] == NULL
                            else feature["Strate"]
                        ),
                        "abondance": (
                            None
                            if feature["Releve_Recouvrement"] == NULL
                            else feature["Releve_Recouvrement"]
                        ),
                    },
                }
            ],
        }
        document = QJsonDocument(json_data)
        reply = self.network_manager.post(request, document.toJson())
        reply.finished.connect(lambda: self.handle_finished(reply))
        self._pending_downloads += 1

    def handle_finished(self, reply):
        """The End of the feature import.
        The process for the next feature is launched.
        """
        self._pending_downloads -= 1
        self._pending_features -= 1
        if reply.error() != QNetworkReply.NoError:
            print(f"code: {reply.error()} message: {reply.errorString()}")

        if self.pending_downloads == 0:
            print("finish feature")
            if self.pending_features != 0:
                self.geo_download(self.list_id[self.pending_features - 1])
            else:
                print("FINISH")
        reply.deleteLater()


# START ALGORITHM
if QgsProject.instance().mapLayersByName(
    layer_name_releve
) and QgsProject.instance().mapLayersByName(layer_name_flore):
    join_attributes(
        flore_layer,
        releve_phyto_layer,
        "Nom",
        "Releve",
        join_field_prefix,
    )
    properties = GetProperties(network_manager)
    properties.finished_dl.connect(
        lambda: launch_dlg(
            network_manager,
            properties,
            iface,
            flore_layer,
        )
    )
else:
    msg = QMessageBox()
    msg.warning(
        None,
        "Ce n'est pas un projet QBiome",
        "Les couches '{layer_name_flore}' et/ou '{layer_name_releve}' sont manquantes".format(  # noqa: E501
            layer_name_flore=layer_name_flore,
            layer_name_releve=layer_name_releve,
        ),
    )
