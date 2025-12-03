"""Script to create an admin user and generate a long-lived access token based on the official onboarding process."""

import asyncio
from datetime import timedelta
import logging
import random
import string
from pathlib import Path
from typing import cast
import json
import os

from homeassistant import (runner, loader)
from homeassistant.helpers.translation import async_get_translations
from homeassistant.auth import auth_manager_from_config
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.auth.models import TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
from homeassistant.auth.providers.homeassistant import HassAuthProvider
from homeassistant.components.onboarding import (
    DOMAIN as ONBOARDING_DOMAIN,
    STEPS,
    STORAGE_KEY,
    STORAGE_VERSION,
    OnboardingData,
    OnboardingStorage,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store, get_internal_store_manager
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.components.person import async_create_person
from homeassistant.setup import async_setup_component
from homeassistant.util.async_ import create_eager_task
from homeassistant.util.unit_system import (METRIC_SYSTEM, UnitSystem)

from homeassistant.helpers import area_registry as ar
from homeassistant.config_entries import ConfigEntries
from homeassistant.helpers.check_config import async_check_ha_config_file

CONFIG_DIR = "/config"
DEFAULT_AREAS = ("living_room", "kitchen", "bedroom")


def _async_get_hass_provider(hass: HomeAssistant) -> HassAuthProvider:
    for provider in hass.auth.auth_providers:
        if provider.type == "homeassistant":
            return cast(HassAuthProvider, provider)
    raise RuntimeError("No Home Assistant auth provider found")


async def _initialize_analytics(hass: HomeAssistant):
    """Initialize analytics and default integrations."""
    onboard_integrations = [
        "google_translate",
        "met",
        "radio_browser",
        "shopping_list",
    ]

    # Start configuration flows for the integrations
    coros = [
        hass.config_entries.flow.async_init(
            domain, context={"source": "onboarding"}
        )
        for domain in onboard_integrations
    ]

    # Ensure analytics component is set up
    if "analytics" not in hass.config.components:
        coros.append(async_setup_component(hass, "analytics", {}))

    # Run all setup coroutines
    await asyncio.gather(*(create_eager_task(coro) for coro in coros))


async def _setup_auth_and_create_user(hass: HomeAssistant):
    """Set up authentication and create admin user."""
    hass.auth = await auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
    provider = _async_get_hass_provider(hass)
    await provider.async_initialize()

    # Get username and password from environment or generate random ones
    username = os.environ.get('USERNAME')
    password = os.environ.get('PASSWORD')

    if not username:
        username = "".join(random.choice(string.ascii_lowercase) for i in range(10))
    if not password:
        password = "".join(random.choice(string.ascii_lowercase) for i in range(15))

    # Create admin user
    user = await hass.auth.async_create_user(
        name=username,
        group_ids=[GROUP_ID_ADMIN]
    )

    # Add credentials and link to user
    await provider.async_add_auth(username, password)
    credentials = await provider.async_get_or_create_credentials(
        {"username": username}
    )
    await hass.auth.async_link_user(user, credentials)

    # Create person associated with the user
    if "person" in hass.config.components:
        await async_create_person(hass, name=username, user_id=user.id)

    # Store the data
    await provider.data.async_save()
    await hass.auth._store._store.async_save(hass.auth._store._data_to_save())

    return user, credentials, username, password


async def _setup_onboarding(hass: HomeAssistant):
    """Set up and save onboarding data."""
    # Mark onboarding steps as done
    onboarding_data = OnboardingData(
        listeners=[],
        onboarded=True,
        steps={"done": STEPS}
    )
    hass.data[ONBOARDING_DOMAIN] = onboarding_data

    # Save onboarding data
    store = OnboardingStorage(hass, STORAGE_VERSION, STORAGE_KEY, private=True)
    if (data := await store.async_load()) is None:
        data = {"done": []}
    data["done"].append(STEPS)

    await store.async_save(onboarding_data.steps)
    # store_manager = get_internal_store_manager(hass)
    # store_manager.async_invalidate(STORAGE_KEY)

# There is a BUG! Areas store is not save data.
async def _create_default_areas(hass: HomeAssistant):
    """Create default areas with translations."""
    translations = await async_get_translations(
        hass, "en", "area", {ONBOARDING_DOMAIN}
    )

    area_registry = ar.async_get(hass)

    for area in DEFAULT_AREAS:
        name = translations[f"component.onboarding.area.{area}"]
        # Guard because area might have been created by an automatically
        # set up integration.
        if not area_registry.async_get_area_by_name(name):
            area_registry.async_create(name)


async def _setup_location_config(hass: HomeAssistant):
    """Set up location configuration."""
    location_config = {
        "latitude": 50.4501,
        "longitude": 30.5234,
        "elevation": 179,
        "unit_system": METRIC_SYSTEM,
        "location_name": "Test home",
        "currency": "UAH",
        "country": "UA",
        "time_zone": "Europe/Kyiv",
    }
    await hass.config.async_update(**location_config)


async def create_and_verify_token(hass: HomeAssistant, user, credentials):
    """Create and verify token persistence."""
    # Create refresh token
    refresh_token = await hass.auth.async_create_refresh_token(
        user,
        token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
        client_name="Home Assistant CLI",
        client_icon="mdi:robot",
        credential=credentials,
        access_token_expiration=timedelta(days=3650)
    )

    # Create access token
    access_token = hass.auth.async_create_access_token(refresh_token)

    # Force save auth data
    await hass.auth._store._store.async_save(hass.auth._store._data_to_save())

    # Verify token exists in storage
    if not any(token.id == refresh_token.id for token in user.refresh_tokens.values()):
        raise Exception("Token not properly stored")

    return access_token


async def create_admin_user_and_token():
    """Create an admin user and generate a long-lived access token."""
    logging.getLogger("homeassistant").setLevel(logging.CRITICAL)

    # Initialize Home Assistant
    hass = HomeAssistant(CONFIG_DIR)
    loader.async_setup(hass)

    # Initialize config entries
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()

    # Load essential registries: area, device, entity, and issue registries
    # These are required for proper Home Assistant initialization
    await asyncio.gather(
        ar.async_load(hass),
        dr.async_load(hass),
        er.async_load(hass),
        ir.async_load(hass, read_only=True)
    )
    components = await async_check_ha_config_file(hass)

    # Create user with credentials
    user, credentials, username, password = await _setup_auth_and_create_user(hass)
    
    # Generate long-lived access token
    access_token = await create_and_verify_token(hass, user, credentials)

    # Complete onboarding
    await _setup_onboarding(hass)

    # Create default areas using translations
    await _create_default_areas(hass)

    # Initialize analytics and integrations
    await _initialize_analytics(hass)

    # Set up location configuration including timezone, coordinates, and unit system
    await _setup_location_config(hass)
 
    # Print result as JSON
    result = {
        "access_token": access_token,
        "username": username,
        "password": password
    }
    print(json.dumps(result))

    await hass.async_stop()

asyncio.set_event_loop_policy(runner.HassEventLoopPolicy(False))
asyncio.run(create_admin_user_and_token())
