import json
from pathlib import Path

from PyQt5.QtCore import QVariant
from qgis.core import (QgsFeature,  # type:ignore
                       QgsFeatureSink,
                       QgsField,
                       QgsFields,
                       QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingException,
                       QgsProcessingParameterCrs,
                       QgsProcessingParameterField,
                       QgsProcessingParameterVectorDestination,
                       QgsProcessingParameterVectorLayer,
                       QgsWkbTypes)


from ..utils import _get_crs_transformer

class CLCToDamage(QgsProcessingAlgorithm):

    INPUT = "Corine Land Cover"
    FIELD = "CAMPO"
    CRS = "CRS"
    OUTPUT = "CLC_Danno"

    def name(self):
        return "clc_danno"

    def displayName(self):
        return "Associa classe di danno"

    def group(self):
        return "Rischio aree allagabili"

    def groupId(self):
        return "flood_risk"

    def shortHelpString(self):
        return "Associa una classe di danno alle classi di uso del suolo derivate" \
        "da dati Corine Land Cover"
    
    def createInstance(self): return CLCToDamage()

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                'Layer Corine Land Cover',
                types=[QgsProcessing.TypeVectorPolygon]
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD,
                "Campo",
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.String
            )
        )

        self.addParameter(
            QgsProcessingParameterCrs(
                self.CRS,
                defaultValue="EPSG:3035"
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.OUTPUT,
                "Output danno"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        clc_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        clc_field = self.parameterAsString(parameters, self.FIELD, context)
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        
        json_map = Path(__file__).parent / "clc2damage.json"
        clc_map = json.loads(json_map.read_text())

        transformer = _get_crs_transformer(clc_layer.sourceCrs(), crs, context)
        
        out_fields = QgsFields()

        out_fields.append(QgsField(clc_field, QVariant.String, len=10))
        out_fields.append(QgsField("DANNO", QVariant.Int))

        (sink, sink_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            out_fields,
            QgsWkbTypes.Polygon,
            crs
        )

        if sink is None:
            raise QgsProcessingException('Impossibile creare output')
        
        idx_src = clc_layer.fields().indexFromName(clc_field)

        for feat in clc_layer.getFeatures():

            if feedback.isCanceled():
                break

            clc_val = str(feat[idx_src])

            new_val = clc_map.get(clc_val, 1)

            new_feat = QgsFeature(out_fields)

            geom = feat.geometry()
            if clc_layer.sourceCrs() != crs:
                if geom and not geom.isEmpty():
                    geom.transform(transformer)

            new_feat.setGeometry(geom)
            new_feat[clc_field] = clc_val
            new_feat["DANNO"] = new_val

            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: sink_id}