from qgis.core import (  # type: ignore
    QgsCoordinateTransform,
    QgsFeature,
    QgsProcessing,
    QgsCoordinateReferenceSystem,
)

import processing


def _get_crs_transformer(src_crs, out_crs, context):
    return QgsCoordinateTransform(src_crs, out_crs, context.transformContext())


def _ftransformCRS(layer, target_crs, context, feedback) -> list:
    layer_feats = list()
    if layer.sourceCrs() != target_crs:
        feedback.pushInfo(f"Riproietto layer.\nCRS target: {target_crs}")
        transformer = _get_crs_transformer(layer.sourceCrs(), target_crs, context)
        for feat in layer.getFeatures():
            geometry = feat.geometry()
            geometry.transform(transformer)
            transformed_feat = QgsFeature(feat)
            transformed_feat.setGeometry(geometry)
            layer_feats.append(transformed_feat)
        return layer_feats
    else:
        return [feat for feat in layer.getFeatures()]


def check_geometry(geometry) -> bool:
    is_not_empty = not geometry.isEmpty()
    is_valid = geometry.isGeosValid()
    return all([is_not_empty, is_valid])


def native_reprojectlayer(
    layer,
    target_crs,
    output=QgsProcessing.TEMPORARY_OUTPUT,
    context=None,
    feedback=None,
):
    params = {
        "INPUT": layer,
        "TARGET_CRS": target_crs,  # Esempio: UTM Zone 32N
        "OUTPUT": output,
    }

    if feedback is not None:
        feedback.pushInfo(f"Riproietto layer.\nCRS target: {target_crs}")

    result = processing.run(  # type: ignore
        "native:reprojectlayer", params, context, feedback
    )["OUTPUT"]

    return result


def native_intersection(
    input, overlay, input_fields, overlay_fields, context, feedback
):
    intx = processing.run(  # type: ignore
        "native:intersection",
        {
            "INPUT": input,
            "OVERLAY": overlay,
            "INPUT_FIELDS": [input_fields],
            "OVERLAY_FIELDS": [overlay_fields],
            "OVERLAY_FIELDS_PREFIX": "",
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            "GRID_SIZE": None,
        },
        context=context,
        feedback=feedback
    )["OUTPUT"]
    return intx


def solve_overlap(
    inputs: list, field="R", crs="EPSG:3035", context=None, feedback=None
):
    solved = processing.run(  # type: ignore
        "adbpo:risolvi_overlay_poligonali",
        {
            "INPUT": inputs,
            "CAMPO": field,
            "CRS": QgsCoordinateReferenceSystem(crs),
            "AREA_THRESHOLD": 1,
            "RisolviSovrapposizioni": "TEMPORARY_OUTPUT",
            "Scarta record senza attributo": True,
        },
        context=context,
        feedback=feedback
    )["RisolviSovrapposizioni"]
    return solved


def native_dissolve(
    layer,
    field,
    sep_dis=False,
    output="TEMPORARY_OUTPUT",
    context=None,
    feedback=None,
):
    if feedback is not None:
        feedback.pushInfo(f"Dissolvo layer: {layer.name()} ({field})")

    dissolved = processing.run(  # type: ignore
        "native:dissolve",
        {
            "INPUT": layer,
            "FIELD": [field],
            "SEPARATE_DISJOINT": sep_dis,
            "OUTPUT": output,
        },
        context=context,
        feedback=feedback
    )["OUTPUT"]

    return dissolved


def native_merge(
    layers,
    crs,
    output="TEMPORARY_OUTPUT",
    context=None,
    feedback=None
):
    if feedback is not None:
        feedback.pushInfo("Fondi vettori")

    merged = processing.run(  # type: ignore
        "native:mergevectorlayers",
        {
            "LAYERS": layers,
            "CRS": crs,
            "OUTPUT": output,
        },
        context=context,
        feedback=feedback
    )["OUTPUT"]
    return merged


def native_polygonize(
    lines,
    keep_fields=False,
    output="TEMPORARY_OUTPUT",
    context=None,
    feedback=None
):
    if feedback is not None:
        feedback.pushInfo("Poligonizza")

    polygonized = processing.run(  # type: ignore
        "native:polygonize",
        {
            "INPUT": lines,
            "KEEP_FIELDS": keep_fields,
            "OUTPUT": output,
        },
        context=context,
        feedback=feedback
    )["OUTPUT"]
    return polygonized


def native_polygonstolines(
    layer,
    output="TEMPORARY_OUTPUT",
    context=None,
    feedback=None
):
    if feedback is not None:
        feedback.pushInfo("Da poligoni a linee")

    lines = processing.run(  # type: ignore
        "native:polygonstolines", {
            "INPUT": layer,
            "OUTPUT": output
        },
        context=context,
        feedback=feedback
    )["OUTPUT"]

    return lines
    

