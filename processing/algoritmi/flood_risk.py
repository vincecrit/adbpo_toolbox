from pathlib import Path

import yaml
from PyQt5.QtCore import QVariant
from qgis.core import (  # type: ignore
    QgsFeature,
    QgsProject,
    QgsField,
    QgsFields,
    QgsVectorLayer,
    QgsProcessing,
    QgsProcessingUtils,
    QgsSpatialIndex,
    QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
)
import processing

from ..utils import (
    native_reprojectlayer,
    native_intersection,
    solve_overlap,
)

from .clc_damage import DFIELD

risk_matrices_path = Path(__file__).parent / "matrici_rischio.yaml"
RISK_MATRICES = yaml.safe_load(risk_matrices_path.read_text())
HFIELD = 'P'

class CalcRisk(QgsProcessingAlgorithm):

    RP = "Reticolo principale"
    RSCM = "Reticolo secondario collinare-montano"
    RSP = "Reticolo secondario di pianura"
    ACM = "Ambito costiero-marino"
    ACL = "Ambito costiero-lacuale"

    input_layers = [RP, RSCM, RSP, ACM, ACL]
    DANNO = "Danno"
    CRS = "CRS"

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
        self.optional_layers = [
            {
                "input": self.RP,
                "checkbox": self.CREATE_OUT_RP,
                "output": "Rischio RP",
                "label": "Reticolo principale",
                "matrice": RISK_MATRICES['mat1']
            },
            {
                "input": self.RSCM,
                "checkbox": self.CREATE_OUT_RSCM,
                "output": "Rischio RSCM",
                "label": "Reticolo secondario collinare-montano",
                "matrice": RISK_MATRICES['mat1']
            },
            {
                "input": self.RSP,
                "checkbox": self.CREATE_OUT_RSP,
                "output": "Rischio RSP",
                "label": "Reticolo secondario di pianura",
                "matrice": RISK_MATRICES['mat3']
            },
            {
                "input": self.ACM,
                "checkbox": self.CREATE_OUT_ACM,
                "output": "Rischio ACM",
                "label": "Ambito costiero-marino",
                "matrice": RISK_MATRICES['mat2']
            },
            {
                "input": self.ACL,
                "checkbox": self.CREATE_OUT_ACL,
                "output": "Rischio ACL",
                "label": "Ambito costiero-lacuale",
                "matrice": RISK_MATRICES['mat2']
            },
        ]

        # INPUT OBBLIGATORIO
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.DANNO,
                self.DANNO,
                [QgsProcessing.TypeVector],
                optional=False,
            )
        )

        # INPUT OPZIONALI
        for layer in self.optional_layers:

            self.addParameter(
                QgsProcessingParameterFeatureSource(
                    layer["input"],
                    f'{layer["label"]}',
                    [QgsProcessing.TypeVector],
                    optional=True,
                )
            )

        # CRS
        self.addParameter(QgsProcessingParameterCrs(self.CRS, defaultValue="EPSG:3035"))

        # OUTPUT PRINCIPALE
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT_MAIN,
                                              self.OUTPUT_MAIN)
        )

        # CHECKBOX OUTPUT OPZIONALI
        for layer in self.optional_layers:

            self.addParameter(
                QgsProcessingParameterBoolean(
                    layer["checkbox"],
                    f'Restituisci rischio derivato da {layer["label"]}',
                    defaultValue=False,
                )
            )

            # OUTPUT OPZIONALI
            self.addParameter(
                QgsProcessingParameterFeatureSink(
                    layer['output'],
                    layer['output'],
                    optional=True
                )
            )

    def processAlgorithm(self, parameters, context, feedback):

        results = dict()

        matrici_rischio = [
            RISK_MATRICES["mat1"], # matrice per RP
            RISK_MATRICES["mat1"], # matrice per RSCM
            RISK_MATRICES["mat3"], # matrice per RSP
            RISK_MATRICES["mat2"], # matrice per ACM
            RISK_MATRICES["mat2"], # matrice per ACL
        ]

        crs = self.parameterAsCrs(parameters, self.CRS, context)

        danno = self.parameterAsVectorLayer(parameters, self.DANNO, context)

        ambiti_territoriali = list()

        feedback.pushDebugInfo("Itero i layer di input")
        for layer_name, layer, mat in zip(
            self.input_layers, self.optional_layers, matrici_rischio
        ):
            vector = self.parameterAsVectorLayer(parameters, layer_name, context)

            feedback.pushDebugInfo(f"{vector}\n{layer_name}\n{mat}")
            if vector:
                if vector.sourceCrs() != crs:
                    vector = native_reprojectlayer(vector, crs)

                create_output = self.parameterAsBool(
                    parameters, layer["checkbox"], context
                )

                intx = native_intersection(
                    vector, danno, None, None,
                    context=context, feedback=feedback
                )

                fields = QgsFields()
                fields.append(QgsField("R", QVariant.Int))

                intx.dataProvider().addAttributes(fields)
                intx.updateFields()

                intx.startEditing()
                for feat in intx.getFeatures():
                    p = feat[HFIELD]
                    d = feat[DFIELD]
                    rischio = mat.get(p, dict()).get(d, None)
                    intx.changeAttributeValue(feat.id(), intx.fields().indexOf("R"), rischio)
                
                intx.commitChanges()

                ambiti_territoriali.append(intx)

                if create_output:

                    sink, dest_id = self.parameterAsSink(
                        parameters,
                        layer["output"],
                        context,
                        intx.fields(),
                        intx.wkbType(),
                        intx.sourceCrs(),
                    )

                    if sink is not None:
                        for feat in intx.getFeatures():
                            sink.addFeature(feat, QgsFeatureSink.FastInsert)

                        results[layer["output"]] = dest_id

        solved = solve_overlap(inputs = ambiti_territoriali,
                               field = "R",
                               crs = crs.authid(),
                               context = context,
                               feedback = feedback)
        
        main_sink, main_dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT_MAIN,
            context,
            solved.fields(),
            solved.wkbType(),
            solved.sourceCrs(),
        )

        if main_sink is not None:
            for feat in solved.getFeatures():
                main_sink.addFeature(feat, QgsFeatureSink.FastInsert)

            results[self.OUTPUT_MAIN] = main_dest_id

        return results
