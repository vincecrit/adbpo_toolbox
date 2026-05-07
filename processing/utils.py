from qgis.core import QgsCoordinateTransform, QgsFeature #type:ignore


def get_crs_transformer(src_crs, out_crs, context):
    return  QgsCoordinateTransform(
        src_crs,
        out_crs,
        context.transformContext()
    )


def check_geometry(geometry) -> bool:
    is_not_empty = not geometry.isEmpty()
    is_valid = geometry.isGeosValid()
    return all([is_not_empty, is_valid])


def _ftransformCRS(layer, target_crs, context, feedback) -> list:
    layer_feats = list()
    if layer.sourceCrs() != target_crs:
        feedback.pushInfo(f"Riproietto layer.\nCRS target: {target_crs}")
        transformer = get_crs_transformer(layer.sourceCrs(),
                                          target_crs, context)
        for feat in layer.getFeatures():
            geometry = feat.geometry()
            geometry.transform(transformer)
            transformed_feat = QgsFeature(feat)
            transformed_feat.setGeometry(geometry)
            layer_feats.append(transformed_feat)
        return layer_feats
    else:
        return [feat for feat in layer.getFeatures()]