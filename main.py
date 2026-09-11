from qgis.core import QgsApplication # type:ignore
from .processing.provider import ProcessingProvider

class AdBPoRisk:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initGui(self):
        self.provider = ProcessingProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
