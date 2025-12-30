import importlib
import os


def _reload_telemetry():
    import sfq.telemetry as telemetry
    importlib.reload(telemetry)
    return telemetry


def test_telemetry_env_parsing_and_enablement():
    old = os.environ.get("SFQ_TELEMETRY")
    try:
        os.environ.pop("SFQ_TELEMETRY", None)
        t = _reload_telemetry()
        assert t.get_config().level == 0
        assert not t.get_config().enabled()

        os.environ["SFQ_TELEMETRY"] = "1"
        t = _reload_telemetry()
        assert t.get_config().level == 1
        assert t.get_config().enabled()

        os.environ["SFQ_TELEMETRY"] = "2"
        t = _reload_telemetry()
        assert t.get_config().level == 2
        assert t.get_config().enabled()

    finally:
        if old is None:
            os.environ.pop("SFQ_TELEMETRY", None)
        else:
            os.environ["SFQ_TELEMETRY"] = old
