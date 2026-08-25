# SPDX-License-Identifier: GPL-3.0-or-later
"""Network-address trust rules for local-only services."""

from __future__ import annotations

import ipaddress

_LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "169.254.0.0/16",
        "::1/128",
        "fe80::/10",
        "fc00::/7",
    )
)


def is_local_address(text: str) -> bool:
    """Return whether a source address belongs to a local network range."""
    try:
        address = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(address in network for network in _LOCAL_NETWORKS)
