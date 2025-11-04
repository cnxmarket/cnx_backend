# marketdata/apps.py
from django.apps import AppConfig

class MarketdataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "marketdata"

    def ready(self):
        # Keep existing signals (you already have this module)
        import marketdata.signals  # noqa: F401

        # NEW: register profile-related signals (create UserProfile on user create)
        try:
            import marketdata.signals_profile  # noqa: F401
        except Exception:
            # Don't crash app startup if file is missing during partial deploys
            pass
