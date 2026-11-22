import pytest

from odei_api.mac_worker import _load_factory, run_worker


def test_mac_worker_factory_requires_explicit_module_callable():
    with pytest.raises(RuntimeError, match="trusted module:callable"):
        _load_factory("os;import:system", setting_name="TEST_FACTORY")
    with pytest.raises(RuntimeError, match="allowlist"):
        _load_factory(
            "odei_api.mac_worker:main", setting_name="TEST_FACTORY",
            allowed_factories=[],
        )
    with pytest.raises(TypeError, match="callable"):
        _load_factory("os:path", setting_name="TEST_FACTORY", allowed_factories=["os:path"])
    assert callable(_load_factory(
        "odei_api.mac_worker:main", setting_name="TEST_FACTORY",
        allowed_factories=["odei_api.mac_worker:main"],
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", [True, 0, 0.1, 30.1, "2"])
async def test_mac_worker_rejects_invalid_poll_intervals_before_loading_adapters(interval):
    with pytest.raises(ValueError, match="Poll interval"):
        await run_worker(poll_interval=interval)


def test_mac_worker_factory_allowlists_are_validated_in_settings():
    from odei_api.config import Settings

    assert Settings(
        mac_provider_factory_allowlist_json='["odei_api.integrations.aws:build_provider"]',
        mac_secret_resolver_factory_allowlist_json='["odei_api.integrations.vault:build_resolver"]',
    ).mac_provider_factory_allowlist_json
    with pytest.raises(ValueError, match="MAC_PROVIDER_FACTORY_ALLOWLIST_JSON"):
        Settings(mac_provider_factory_allowlist_json='["os;import:system"]')
    with pytest.raises(ValueError, match="MAC_SECRET_RESOLVER_FACTORY_ALLOWLIST_JSON"):
        Settings(mac_secret_resolver_factory_allowlist_json='["module:callable", "module:callable"]')
