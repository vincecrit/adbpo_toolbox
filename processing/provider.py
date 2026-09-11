from qgis.core import QgsProcessingProvider # type:ignore
from .algoritmi.resolve_polygon_overlay import ResolvePolygonOverlay
from .algoritmi.clc_damage import CLCToDamage
from .algoritmi.flood_risk import CalcRisk

class ProcessingProvider(QgsProcessingProvider):

    def id(self):
        return "adbpo"

    def name(self):
        return "AdBPo"

    def loadAlgorithms(self):
        self.addAlgorithm(ResolvePolygonOverlay())
        self.addAlgorithm(CLCToDamage())
        self.addAlgorithm(CalcRisk())
