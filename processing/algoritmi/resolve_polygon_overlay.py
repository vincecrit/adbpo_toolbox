from qgis.core import (  # type: ignore
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureSink,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsSpatialIndex,
    QgsProcessingParameterCrs,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterFeatureSink,
    QgsWkbTypes,
    QgsProcessingParameterBoolean,
    NULL,
)

import processing

from ..utils import (
    check_geometry,
    native_dissolve,
    native_merge,
    native_polygonize,
    native_polygonstolines,
    native_reprojectlayer,
)

class ResolvePolygonOverlay(QgsProcessingAlgorithm):

    INPUT = "INPUT"
    FIELD = "FIELD"
    CRS = "CRS"
    AREA_THRESHOLD = "AREA_THRESHOLD"
    OUTPUT = "OUTPUT"
    CLEAN = "CLEAN"

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
            "Genera una partizione poligonale senza sovrapposizioni a "
            + "partire da più layer e assegna gli attributi per massima "
            + "sovrapposizione."
        )

    def createInstance(self):
        return ResolvePolygonOverlay()

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT, "Layer(s) di input", layerType=QgsProcessing.TypeVectorPolygon
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.FIELD, "Nome campo", defaultValue="p", optional=False
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
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Risolvi sovrapposizioni",
                type=QgsProcessing.TypeVectorPolygon,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CLEAN,
                "Scarta record senza attributo",
                defaultValue=True,
                optional=False,
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
        feedback.pushDebugInfo("=== VERIFICA PRE-PROCESSAMENTO ===")
        feedback.pushDebugInfo(f"CRS target: {crs.authid()}")
        feedback.pushDebugInfo(f"Soglia areale: {area_threshold}")
        feedback.pushDebugInfo(f"Nome campo input: {field}")

        verified_layers = list()
        for layer in poly_layers:
            feedback.pushDebugInfo(
                f"Layer: {layer.name()} | CRS: {layer.sourceCrs().authid()} | Features: {layer.featureCount()}"
            )
            # Verifica presenza di P nulli
            null_p_count = sum([f[field] is None for f in layer.getFeatures()])
            feedback.pushDebugInfo(f"  └─ {field}=null: {null_p_count}")

            if layer.sourceCrs() != crs:
                layer = native_reprojectlayer(layer, crs)
                verified_layers.append(layer)
            else:
                verified_layers.append(layer)

        feedback.pushDebugInfo(f"=== ESECUZIONE ===")

        # DISSOLVI
        dissolved_layers = list()
        for layer in verified_layers:
            dissolved = native_dissolve(
                layer, field, False, context=context, feedback=feedback
            )
            dissolved_layers.append(dissolved)

        # FONDI VETTORI
        merged = native_merge(dissolved_layers, crs, context=context, feedback=feedback)

        # DA POLIGONI A LINEE
        lines = native_polygonstolines(merged, context=context, feedback=feedback)

        # POLIGONIZZA
        polygonized = native_polygonize(lines, keep_fields=True, context=context, feedback=feedback)

        # PRE-CACHE INPUT FEATURES
        verified_feature_dict = list()
        field_indices = list()
        layer_indexes = list()

        for layer in verified_layers:
            idx = QgsSpatialIndex()
            feature_dict = dict()

            for feature in layer.getFeatures():
                feature_dict[feature.id()] = feature
                idx.insertFeature(feature)

            verified_feature_dict.append(feature_dict)

            field_index = layer.fields().lookupField(field)
            field_indices.append(field_index)
            layer_indexes.append(idx)

            # Verifica che il campo esista
            if field_index == -1:
                raise QgsProcessingException(
                    f"Campo '{field}' non trovato in layer '{layer.name()}'"
                )

        # OUTPUT SETUP: unione dei campi originali di tutti i layer di input,
        # cosi' l'output riporta gli attributi originali della feature vincente
        # invece di un singolo campo ricalcolato
        out_fields = QgsFields()
        seen_field_names = set()
        for layer in verified_layers:
            for fld in layer.fields():
                name_key = fld.name().casefold()
                if name_key not in seen_field_names:
                    out_fields.append(fld)
                    seen_field_names.add(name_key)

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
        orphan_partitions = 0  # senza intersezioni sopra soglia
        empty_or_invalid = 0  # geometrie non valide o vuote
        with_intersections_no_p = 0  # Con intersezioni MA field=None

        for feature in polygonized.getFeatures():

            geometry = feature.geometry()

            if not check_geometry(geometry):
                continue

            total_partitions += 1
            max_value = None
            winner_feature = None
            has_valid_intersections = False
            has_null_attr_intersections = False

            for ID_N, (feature_dict, layer, field_index) in enumerate(
                zip(verified_feature_dict, verified_layers, field_indices)
            ):
                candidates = layer_indexes[ID_N].intersects(geometry.boundingBox())

                for feat_id in candidates:
                    cand_feature = feature_dict[feat_id]
                    input_geometry = cand_feature.geometry()
                    attr_value = cand_feature[field_index]

                    if not geometry.intersects(input_geometry):
                        continue

                    _intx = geometry.intersection(input_geometry)

                    # controllo geometria
                    if not check_geometry(_intx):
                        empty_or_invalid += 1
                        continue

                    # Verifica la soglia areale
                    intersection_area = _intx.area()
                    if intersection_area < area_threshold:
                        continue

                    if attr_value is None:
                        has_null_attr_intersections = True
                        # has_valid_intersections = False

                    else:
                        # has_null_attr_intersections = False
                        has_valid_intersections = True

                        if max_value is None or attr_value > max_value:
                            max_value = attr_value
                            winner_feature = cand_feature

            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(geometry)
            out_feat[field.upper()] = max_value

            if winner_feature is not None:
                for src_idx, fld in enumerate(winner_feature.fields()):
                    dst_idx = out_fields.lookupField(fld.name())
                    if dst_idx != -1:
                        out_feat.setAttribute(dst_idx, winner_feature.attribute(src_idx))

            if winner_feature is None and clean:
                continue
            else:
                sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

            # DEBUG: Categorizzazione
            if winner_feature is not None:
                assigned_partitions += 1
            else:
                if has_null_attr_intersections:
                    with_intersections_no_p += 1
                elif not has_valid_intersections:
                    orphan_partitions += 1
                else:  # Nessuna intersezione
                    orphan_partitions += 1

        # Report debug
        feedback.pushDebugInfo(f"=== REPORT DEBUG ===")
        feedback.pushDebugInfo(f"Partizioni vuote o non valide: {empty_or_invalid}")
        feedback.pushDebugInfo(f"Partizioni con geometrie valide totali: {total_partitions}")
        feedback.pushDebugInfo(f"    di cui assegnate: {assigned_partitions}")
        feedback.pushDebugInfo(f"    di cui senza intersezioni valide: {orphan_partitions}")
        feedback.pushDebugInfo(
            f"    di cui con intersezioni ma {field}=None: {with_intersections_no_p}"
        )

        return {self.OUTPUT: sink_id}
