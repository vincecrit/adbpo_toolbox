from pathlib import Path

import yaml
from PyQt5.QtCore import QVariant
from qgis.core import (QgsFeature,  # type:ignore
                       QgsField,
                       QgsFields,
                       QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterCrs,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField)

import processing

from ..utils import get_crs_transformer

risk_matrices_path = Path(__file__).parent / "matrici_rischio.yaml"
RISK_MATRICES = yaml.safe_load(risk_matrices_path.read_text())


class CalcRisk(QgsProcessingAlgorithm):

    HLAYER = "HAZARD"
    HFIELD = "HFIELD"
    DLAYER = "DAMAGE"
    DFIELD = "DFIELD"
    RMAT = "MATRICI"
    CRS = "CRS"
    OUTPUT = "Rischio"

    def name(self):
        return "flood_risk"

    def displayName(self):
        return "Determina rischio massimo"

    def group(self):
        return "Rischio aree allagabili"

    def groupId(self):
        return "flood_risk"

    def shortHelpString(self):
        return "Associa una classe di rischio per ogni origine di rischio "

    def createInstance(self): return CalcRisk()

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.HLAYER,
                "Layer pericolosità",
                [QgsProcessing.TypeVector]
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.HFIELD,
                "Campo pericolosità",
                parentLayerParameterName=self.HLAYER,
                type=QgsProcessingParameterField.Numeric
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.DLAYER,
                "Layer danno",
                [QgsProcessing.TypeVector]
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.DFIELD,
                "Campo danno",
                parentLayerParameterName=self.DLAYER,
                type=QgsProcessingParameterField.Numeric
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.RMAT,
                "Matrici di rischio",
                options=list(RISK_MATRICES.keys()),
                allowMultiple=True
            )
        )

        self.addParameter(
            QgsProcessingParameterCrs(
                self.CRS,
                defaultValue="EPSG:3035"
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Output rischio"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        
        hlayer = self.parameterAsVectorLayer(parameters, self.HLAYER, context)
        dlayer = self.parameterAsVectorLayer(parameters, self.DLAYER, context)
        hfield = self.parameterAsString(parameters, self.HFIELD, context)
        dfield = self.parameterAsString(parameters, self.DFIELD, context)
        matrici_idx = self.parameterAsEnums(parameters, self.RMAT, context)
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        crs_changed = False
        
        matrici_scelte = [list(RISK_MATRICES.keys())[i] for i in matrici_idx]

        fields = QgsFields()
        fields.append(QgsField(hfield, QVariant.Int))
        fields.append(QgsField(dfield, QVariant.Int))

        for m in matrici_scelte:
            fields.append(QgsField(f"R_{m}", QVariant.Int))

        fields.append(QgsField("R_MAX", QVariant.Int))

        hd_layer = processing.run( #type:ignore
            "native:intersection",
            {
                'INPUT': hlayer,
                'OVERLAY': dlayer,
                'INPUT_FIELDS': [hfield],
                'OVERLAY_FIELDS': [dfield],
                'OVERLAY_FIELDS_PREFIX': '',
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                'GRID_SIZE': None
            },
            context=context,
            feedback=feedback)['OUTPUT']

        hd_layer_crs = hd_layer.sourceCrs()
        transform = get_crs_transformer(hd_layer_crs, crs, context)

        sink, sink_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            hd_layer.wkbType(),
            crs
        )

        for feat in hd_layer.getFeatures():
            p = feat[hfield]
            d = feat[dfield]

            new_feat = QgsFeature(fields)
            geom = feat.geometry()

            if crs != hd_layer_crs:
                crs_changed = True
                if geom and not geom.isEmpty():
                    geom.transform(transform)
            else:
                pass

            new_feat.setGeometry(geom)

            rischi = list()
            for m in matrici_scelte:
                valore = RISK_MATRICES[m].get(p, dict()).get(d, None)
                rischi.append(valore)
                new_feat[f"R_{m}"] = valore

            if any([e is not None for e in rischi]):
                rmax = int(max([r for r in rischi if r is not None]))
            else:
                rmax = None

            new_feat.setAttribute(hfield, p)
            new_feat.setAttribute(dfield, d)
            new_feat.setAttribute("R_MAX", rmax)

            sink.addFeature(new_feat)
        
        if crs_changed:
            feedback.pushInfo(f"CRS cambiato da {hd_layer_crs.authid()} a {crs.authid()}")

        return {self.OUTPUT: sink_id}
