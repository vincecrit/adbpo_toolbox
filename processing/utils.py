from qgis.core import QgsCoordinateTransform #type:ignore


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