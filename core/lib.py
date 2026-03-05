from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsProcessingUtils,
    QgsWkbTypes,
    QgsFields,
    QgsField
)
from PyQt5.QtCore import QVariant
import processing


def resolve_overlay(self, parameters, context, feedback):

    # -----------------------------
    # INPUT
    # -----------------------------
    poly_layers = self.parameterAsSource(parameters, "INPUT", context)

    # -----------------------------
    # POLYGON → LINE
    # -----------------------------
    line_layers = []

    for i, layer in enumerate(poly_layers):
        feedback.pushInfo(f'Converto layer {i+1} in linee')

        res = processing.run(
            'native:polygonstolines',
            {
                'INPUT': layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            },
            context=context,
            feedback=feedback
        )

        line_layers.append(res['OUTPUT'])

    # -----------------------------
    # MERGE LINEE
    # -----------------------------
    feedback.pushInfo('Merge dei layer lineari')

    merged_lines = processing.run(
        'native:mergevectorlayers',
        {
            'LAYERS': line_layers,
            'CRS': poly_layers[0].sourceCrs(),
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        },
        context=context,
        feedback=feedback
    )['OUTPUT']

    # -----------------------------
    # POLYGONIZE
    # -----------------------------
    feedback.pushInfo('Polygonize')

    poly_no_overlap = processing.run(
        'native:polygonize',
        {
            'INPUT': merged_lines,
            'KEEP_FIELDS': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        },
        context=context,
        feedback=feedback
    )['OUTPUT']

    # -----------------------------
    # OUTPUT SETUP
    # -----------------------------
    out_fields = QgsFields()
    out_fields.append(QgsField('P', QVariant.Double))

    (sink, sink_id) = self.parameterAsSink(
        parameters,
        'OUTPUT',
        context,
        out_fields,
        QgsWkbTypes.Polygon,
        poly_no_overlap.sourceCrs()
    )

    if sink is None:
        raise QgsProcessingException('Impossibile creare output')

    # -----------------------------
    # PRE-CACHE INPUT FEATURES
    # -----------------------------
    input_feats = []
    for layer in poly_layers:
        input_feats.append(list(layer.getFeatures()))

    # -----------------------------
    # ATTRIBUZIONE P
    # -----------------------------
    for feat in poly_no_overlap.getFeatures():
        geom = feat.geometry()

        best_area = 0.0
        best_p = None

        for feats, layer in zip(input_feats, poly_layers):
            for f in feats:
                if not geom.intersects(f.geometry()):
                    continue

                inter = geom.intersection(f.geometry())
                if inter.isEmpty():
                    continue

                area = inter.area()
                if area > best_area:
                    best_area = area
                    best_p = f['P']

        out_feat = QgsFeature(out_fields)
        out_feat.setGeometry(geom)
        out_feat['P'] = best_p

        sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

    return {'OUTPUT': sink_id}
