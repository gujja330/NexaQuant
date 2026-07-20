"""Model implementations — 11 model types per operator spec.

Every model implements BaseModel.predict() as a deterministic scoring function
over the current feature vector. Sprint 2.7 ships rule-based scoring — Sprint 9's
Learning Engine can swap the internals for trained ML models later without
changing the interface.
"""
from backend.model_factory.models.momentum        import MomentumModel                     # noqa: F401
from backend.model_factory.models.trend           import TrendModel                        # noqa: F401
from backend.model_factory.models.value           import ValueModel                        # noqa: F401
from backend.model_factory.models.growth          import GrowthModel                       # noqa: F401
from backend.model_factory.models.quality         import QualityModel                      # noqa: F401
from backend.model_factory.models.mean_reversion  import MeanReversionModel                # noqa: F401
from backend.model_factory.models.news_model      import NewsModel                         # noqa: F401
from backend.model_factory.models.macro_model     import MacroModel                        # noqa: F401
from backend.model_factory.models.sector_rotation import SectorRotationModel               # noqa: F401
from backend.model_factory.models.event_driven    import EventDrivenModel                  # noqa: F401
from backend.model_factory.models.ai_hybrid       import AIHybridModel                     # noqa: F401


ALL_MODELS = [
    MomentumModel, TrendModel, ValueModel, GrowthModel, QualityModel,
    MeanReversionModel, NewsModel, MacroModel, SectorRotationModel,
    EventDrivenModel, AIHybridModel,
]
