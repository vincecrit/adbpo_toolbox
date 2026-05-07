from PyQt5.QtCore import QVariant  # type: ignore
from qgis.core import (  # type: ignore
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterCrs,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsWkbTypes,
    QgsProcessingParameterBoolean,
    NULL,
)

import processing

from ..utils import (
    check_geometry,
    _ftransformCRS,
    native_dissolve,
    native_merge,
    native_polygonize,
    native_polygonstolines,
    native_reprojectlayer,
)


class ResolvePolygonOverlay(QgsProcessingAlgorithm):

    INPUT = "INPUT"
    FIELD = "CAMPO"
    CRS = "CRS"
    AREA_THRESHOLD = "AREA_THRESHOLD"
    OUTPUT = "RisolviSovrapposizioni"
    CLEAN = "Scarta record senza attributo"

    def name(self):
        return "risolvi_overlay_poligonali"

    def displayName(self):
        return "Risolvi sovrapposizioni poligonali"

    def group(self):
        return "Rischio aree allagabili"

    def groupId(self):
        return "flood_risk"

    def shortHelpString(self):
        return (
            "Genera una partizione poligonale senza sovrapposizioni a"
            "partire da più layer e assegna gli attributi per massima"
            "sovrapposizione."
        )

    def createInstance(self):
        return ResolvePolygonOverlay()

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT, self.INPUT, layerType=QgsProcessing.TypeVectorPolygon
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.FIELD, self.FIELD, defaultValue="p", optional=False
            )
        )

        self.addParameter(QgsProcessingParameterCrs(self.CRS, defaultValue="EPSG:3035"))

        self.addParameter(
            QgsProcessingParameterNumber(
                self.AREA_THRESHOLD,
                "Soglia areale di sovrapposizione (unità mappa)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=1.0,
                minValue=0.0,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorDestination(self.OUTPUT, self.OUTPUT)
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CLEAN, self.CLEAN, defaultValue=True, optional=False
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        poly_layers = self.parameterAsLayerList(parameters, self.INPUT, context)
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        area_threshold = self.parameterAsDouble(
            parameters, self.AREA_THRESHOLD, context
        )
        field = self.parameterAsString(parameters, self.FIELD, context)
        clean = self.parameterAsBool(parameters, self.CLEAN, context)

        # DEBUG: Verifica layer e CRS
        feedback.pushInfo("=== VERIFICA PRE-PROCESSAMENTO ===")
        feedback.pushInfo(f"CRS target: {crs.authid()}")
        feedback.pushInfo(f"Soglia areale: {area_threshold}")
        feedback.pushInfo(f"Campo pericolosità: {field}")

        verified = list()
        for layer in poly_layers:
            feedback.pushInfo(
                f"Layer: {layer.name()} | CRS: {layer.sourceCrs().authid()} | Features: {layer.featureCount()}"
            )
            # Verifica presenza di P nulli
            null_p_count = sum([f[field] is None for f in layer.getFeatures()])
            feedback.pushInfo(f"  └─ {field}=null: {null_p_count}")

            if layer.sourceCrs() != crs:
                layer = native_reprojectlayer(layer, crs)
                verified.append(layer)
            else:
                verified.append(layer)

        feedback.pushInfo(f"=== ESECUZIONE ===")

        # DISSOLVI
        dissolved_layers = list()
        for layer in verified:
            dissolved = native_dissolve(layer, field, False, context=context, feedback=feedback)
            dissolved_layers.append(dissolved)

        # FONDI VETTORI
        merged = native_merge(dissolved_layers, crs, context=context, feedback=feedback)

        # DA POLIGONI A LINEE
        lines = native_polygonstolines(merged, context=context, feedback=feedback)

        # POLIGONIZZA
        polygonized = native_polygonize(lines, context=context, feedback=feedback)

        # PRE-CACHE INPUT FEATURES
        layers_feature_list = list()
        for layer in verified:
            layers_feature_list.append(list(layer.getFeatures()))

        # OUTPUT SETUP
        out_fields = QgsFields()
        out_fields.append(QgsField(field, QVariant.Int))

        sink, sink_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            out_fields,
            QgsWkbTypes.Polygon,
            crs,
        )

        if sink is None:
            raise QgsProcessingException("Impossibile creare output")

        # ATTRIBUZIONE P (massimo valore tra sovrapposizioni)
        # DEBUG: Contatori per analisi
        total_partitions = 0
        assigned_partitions = 0
        orphan_partitions = 0  # Senza intersezioni sopra soglia
        invalid = 0  # geometrie non valide
        empty = 0  # geometrie vuote
        with_intersections_no_p = 0  # Con intersezioni MA P=None (il vero problema)

        for feat in polygonized.getFeatures():
            geometry = feat.geometry()

            if not check_geometry(geometry):
                continue

            total_partitions += 1

            max_p = None
            matching_none = list()
            all_matches = list()

            for features, layer in zip(layers_feature_list, poly_layers):
                for f in features:
                    input_geometry = f.geometry()
                    attr_value = f[field]

                    # controllo se esiste un'intersezione
                    if not geometry.intersects(input_geometry):
                        continue

                    _intx = geometry.intersection(input_geometry)

                    # controllo se geometria intersezione è valida
                    if not check_geometry(_intx):
                        continue

                    # Verifica la soglia areale
                    intersection_area = _intx.area()
                    if intersection_area < area_threshold:
                        continue

                    all_matches.append(
                        {
                            "layer": layer.name(),
                            "area": intersection_area,
                            "attr_value": attr_value,
                        }
                    )

                    if attr_value is None:
                        matching_none.append(
                            {
                                "layer": layer.name(),
                                "area": intersection_area,
                            }
                        )

                    else:
                        if max_p is None or attr_value > max_p:
                            max_p = attr_value

            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(geometry)
            out_feat[field] = max_p

            if max_p is None and clean:
                continue
            else:
                sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

            # DEBUG: Categorizzazione
            if max_p is not None:
                assigned_partitions += 1
            else:
                if len(matching_none) > 0:  # Ha intersezioni sopra soglia, ma P=None
                    with_intersections_no_p += 1
                elif len(all_matches) == 0:  # Ha intersezioni, ma tutte sotto soglia
                    orphan_partitions += 1
                else:  # Nessuna intersezione
                    orphan_partitions += 1

        # Report debug
        feedback.pushInfo(f"=== REPORT DEBUG ===")
        feedback.pushInfo(f"Partizioni senza geometria: {empty}")
        feedback.pushInfo(f"Partizioni non valide: {invalid}")
        feedback.pushInfo(f"Partizioni con geometrie valide totali: {total_partitions}")
        feedback.pushInfo(f"    di cui assegnate: {assigned_partitions}")
        feedback.pushInfo(f"    di cui senza intersezioni valide: {orphan_partitions}")
        feedback.pushInfo(
            f"    di cui con intersezioni ma {field}=None: {with_intersections_no_p}"
        )

        return {self.OUTPUT: sink_id}
