from __future__ import annotations

from dataclasses import dataclass
from random import choices
from uuid import uuid4

from src.schemas.enums import DeviceOS, DeviceType, SubscriptionTier


@dataclass(frozen=True)
class UserPersona:
    user_id: str
    subscription_tier: SubscriptionTier
    device_type: DeviceType
    device_os: DeviceOS


_TIER_WEIGHTS = (70, 25, 5)
_DEVICE_WEIGHTS_BY_TIER = {
    SubscriptionTier.FREE: (75, 15, 8, 2),
    SubscriptionTier.PRO: (25, 60, 10, 5),
    SubscriptionTier.ENTERPRISE: (5, 15, 5, 75),
}
_MOBILE_OS_WEIGHTS = (55, 35, 10)
_DESKTOP_OS_WEIGHTS = (45, 25, 20, 10)
_TABLET_OS_WEIGHTS = (60, 25, 15)
_API_OS = DeviceOS.LINUX


def create_user_pool(count: int) -> list[UserPersona]:
    """Generate a pool of personas with realistic product usage patterns."""

    if count < 1:
        raise ValueError("count must be greater than or equal to 1")

    personas: list[UserPersona] = []
    tiers = choices(
        population=[SubscriptionTier.FREE, SubscriptionTier.PRO, SubscriptionTier.ENTERPRISE],
        weights=_TIER_WEIGHTS,
        k=count,
    )

    for tier in tiers:
        device_type = choices(
            population=[DeviceType.MOBILE, DeviceType.DESKTOP, DeviceType.TABLET, DeviceType.API],
            weights=_DEVICE_WEIGHTS_BY_TIER[tier],
            k=1,
        )[0]
        device_os = _pick_device_os(device_type)
        personas.append(
            UserPersona(
                user_id=str(uuid4()),
                subscription_tier=tier,
                device_type=device_type,
                device_os=device_os,
            )
        )

    return personas


def _pick_device_os(device_type: DeviceType) -> DeviceOS:
    if device_type == DeviceType.MOBILE:
        return choices(
            population=[DeviceOS.ANDROID, DeviceOS.IOS, DeviceOS.OTHER],
            weights=_MOBILE_OS_WEIGHTS,
            k=1,
        )[0]
    if device_type == DeviceType.DESKTOP:
        return choices(
            population=[DeviceOS.WINDOWS, DeviceOS.MACOS, DeviceOS.LINUX, DeviceOS.OTHER],
            weights=_DESKTOP_OS_WEIGHTS,
            k=1,
        )[0]
    if device_type == DeviceType.TABLET:
        return choices(
            population=[DeviceOS.ANDROID, DeviceOS.IOS, DeviceOS.OTHER],
            weights=_TABLET_OS_WEIGHTS,
            k=1,
        )[0]
    return _API_OS
