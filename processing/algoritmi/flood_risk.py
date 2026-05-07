from pathlib import Path

import yaml
from PyQt5.QtCore import QVariant
from qgis.core import ( # type:ignore
    QgsFeature,  # type:ignore
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
)

import processing

from ..utils import get_crs_transformer

risk_matrices_path = Path(__file__).parent / "matrici_rischio.yaml"
RISK_MATRICES = yaml.safe_load(risk_matrices_path.read_text())
OPTSUFFX = " (opzionale)"
REQSUFFX = " (obbligatorio)"
HFIELD = "P"
DFIELD = "D"


def _qgis_nativeintersection(
    input, overlay, input_fields, overlay_fileds, context, feedback
):
    intx = processing.run(  # type:ignore
        "native:intersection",
        {
            "INPUT": input,
            "OVERLAY": overlay,
            "INPUT_FIELDS": [input_fields],
            "OVERLAY_FIELDS": [overlay_fileds],
            "OVERLAY_FIELDS_PREFIX": "",
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            "GRID_SIZE": None,
        },
        context=context,
        feedback=feedback,
    )["OUTPUT"]
    return intx


class CalcRisk(QgsProcessingAlgorithm):
    
    input_layers = dict(
        RP = "Reticolo principale",
        RSCM = "Reticolo secondario collinare-montano",
        RSP = "Reticolo secondario di pianura",
        ACM = "Ambito costiero-marino",
        ACL = "Ambito costiero-lacuale",
        DANNO = "Danno"
    )

    RP =    "Reticolo principale"
    RSCM =  "Reticolo secondario collinare-montano"
    RSP =   "Reticolo secondario di pianura"
    ACM =   "Ambito costiero-marino"
    ACL =   "Ambito costiero-lacuale"
    DANNO = "Danno"
    CRS =   "CRS"

    CREATE_OUT_RP = "CREATE_OUT_RP"
    CREATE_OUT_RSCM = "CREATE_OUT_RSCM"
    CREATE_OUT_RSP = "CREATE_OUT_RSP"
    CREATE_OUT_ACM = "CREATE_OUT_ACM"
    CREATE_OUT_ACL = "CREATE_OUT_ACL"

    OUTPUT_MAIN = "Rischio massimo"
    OUTPUT_RP = "Rischio RP"
    OUTPUT_RSCM = "Rischio RSCM"
    OUTPUT_RSP = "Rischio RSP"
    OUTPUT_ACM = "Rischio ACM"
    OUTPUT_ACL = "Rischio ACL"

    def name(self):
        return "flood_risk"

    def displayName(self):
        return "Determina rischio massimo"

    def group(self):
        return "Rischio aree allagabili"

    def groupId(self):
        return "flood_risk"

    def shortHelpString(self):
        return ""

    def createInstance(self):
        return CalcRisk()

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.RP, self.RP + OPTSUFFX, [QgsProcessing.TypeVector],
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.RSCM,
                self.RSCM + OPTSUFFX,
                [QgsProcessing.TypeVector],
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.RSP, self.RSP + OPTSUFFX, [QgsProcessing.TypeVector],
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.ACM, self.ACM + OPTSUFFX, [QgsProcessing.TypeVector],
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.ACL, self.ACL + OPTSUFFX, [QgsProcessing.TypeVector],
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.DANNO,
                self.DANNO + REQSUFFX,
                [QgsProcessing.TypeVector],
                optional=False,
            )
        )

        self.addParameter(QgsProcessingParameterCrs(self.CRS, defaultValue="EPSG:3035"))

        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT_MAIN, "Output rischio")
        )

        ### CHECKBOX
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_OUT_RP, self.CREATE_OUT_RP, defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_OUT_RSCM, self.CREATE_OUT_RSCM, defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_OUT_RSP, self.CREATE_OUT_RSP, defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_OUT_ACM, self.CREATE_OUT_ACM, defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_OUT_ACL, self.CREATE_OUT_ACL, defaultValue=False
            )
        )

        ### OUTPUT OPZIONALI
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_RP, self.OUTPUT_RP, optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_RSCM, self.OUTPUT_RSCM, optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_RSP, self.OUTPUT_RSP, optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ACM, self.OUTPUT_ACM, optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ACL, self.OUTPUT_ACL, optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        rp = self.parameterAsVectorLayer(parameters, self.RP, context)
        rscm = self.parameterAsVectorLayer(parameters, self.RSCM, context)
        rsp = self.parameterAsVectorLayer(parameters, self.RSP, context)
        acm = self.parameterAsVectorLayer(parameters, self.ACM, context)
        acl = self.parameterAsVectorLayer(parameters, self.ACL, context)
        danno = self.parameterAsVectorLayer(parameters, self.DANNO, context)

        crs = self.parameterAsCrs(parameters, self.CRS, context)
        crs_changed = False

        ambiti_territoriali = [rp, rscm, rsp, acm, acl]
        matrici_rischio = [
            RISK_MATRICES["mat1"],
            RISK_MATRICES["mat1"],
            RISK_MATRICES["mat2"],
            RISK_MATRICES["mat2"],
            RISK_MATRICES["mat3"],
        ]

        # sink, sink_id = self.parameterAsSink(
        #     parameters,
        #     self.OUTPUT_MAIN,
        #     context,
        #     fields,
        #     intx.wkbType(),
        #     crs
        # )

        # fields = QgsFields()
        # fields.append(QgsField(HFIELD, QVariant.Int))
        # fields.append(QgsField(DFIELD, QVariant.Int))

        # for m in matrici_scelte:
        #     fields.append(QgsField(f"R_{m}", QVariant.Int))

        # fields.append(QgsField("R_MAX", QVariant.Int))

        # intersects = list()
        sinked_ids = list()
        for layer, mat in zip(ambiti_territoriali, matrici_rischio):
            fields = QgsFields()
            fields.append(QgsField(HFIELD, QVariant.Int))
            fields.append(QgsField(DFIELD, QVariant.Int))

            intx = _qgis_nativeintersection(
                layer, danno, HFIELD, DFIELD, context=context, feedback=feedback
            )

            intx_crs = intx.sourceCrs()
            transform = get_crs_transformer(intx_crs, crs, context)

            for feat in intx.getFeatures():
                p = feat[HFIELD]
                d = feat[DFIELD]

                new_feat = QgsFeature(fields)
                geom = feat.geometry()

                if crs != intx_crs:
                    crs_changed = True
                    if geom and not geom.isEmpty():
                        geom.transform(transform)
                else:
                    pass

                new_feat.setGeometry(geom)

                valore = mat.get(p, dict()).get(d, None)
                new_feat[f"R"] = valore

                new_feat.setAttribute(HFIELD, p)
                new_feat.setAttribute(DFIELD, d)

                sink.addFeature(new_feat)

            if crs_changed:
                feedback.pushInfo(
                    f"CRS cambiato da {intx_crs.authid()} a {crs.authid()}"
                )

        return
