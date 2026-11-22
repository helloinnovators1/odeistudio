import pytest

from odei_api.mac_worker import _load_factory, run_worker


def test_mac_worker_factory_requires_explicit_module_callable():
    with pytest.raises(RuntimeError, match="trusted module:callable"):
        _load_factory("os;import:system", setting_name="TEST_FACTORY")
    with pytest.raises(RuntimeError, match="callable"):
        _load_factory("os:path", setting_name="TEST_FACTORY")
    assert callable(_load_factory("odei_api.mac_worker:main", setting_name="TEST_FACTORY"))


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", [True, 0, 0.1, 30.1, "2"])
async def test_mac_worker_rejects_invalid_poll_intervals_before_loading_adapters(interval):
    with pytest.raises(ValueError, match="Poll interval"):
        await run_worker(poll_interval=interval)
