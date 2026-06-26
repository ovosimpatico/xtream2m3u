"""Utility functions for URL encoding, filtering, and DNS setup"""
import fnmatch
import ipaddress
import logging
import re
import socket
import urllib.parse

import dns.resolver

logger = logging.getLogger(__name__)


def normalize_base_url(url):
    """Normalize a user-supplied Xtream base URL.

    Trims whitespace, prepends http:// when no scheme is given, and strips any
    trailing slashes. Without this, a pasted URL like "http://host/" builds
    endpoints as "http://host//player_api.php" — a double slash that stricter
    Xtream panels reject. Returns the value unchanged if it's empty/None so the
    caller's own required-field validation still fires.
    """
    if not url:
        return url
    url = url.strip()
    if url and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", url):
        url = "http://" + url
    return url.rstrip("/")


def setup_custom_dns():
    """Configure a custom DNS resolver using reliable DNS services"""
    dns_servers = ["1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9"]

    custom_resolver = dns.resolver.Resolver()
    custom_resolver.nameservers = dns_servers

    original_getaddrinfo = socket.getaddrinfo

    def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host:
            try:
                # Skip DNS resolution for IP addresses
                try:
                    ipaddress.ip_address(host)
                    # If we get here, the host is already an IP address
                    logger.debug(f"Host is already an IP address: {host}, skipping DNS resolution")
                except ValueError:
                    # Not an IP address, so try system DNS first
                    try:
                        result = original_getaddrinfo(host, port, family, type, proto, flags)
                        logger.debug(f"System DNS resolved {host}")
                        return result
                    except Exception as system_error:
                        logger.info(f"System DNS resolution failed for {host}: {system_error}, falling back to custom DNS")
                        # Fall back to custom DNS
                        answers = custom_resolver.resolve(host)
                        host = str(answers[0])
                        logger.debug(f"Custom DNS resolved {host}")
            except Exception as e:
                logger.info(f"Custom DNS resolution also failed for {host}: {e}, using original getaddrinfo")
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = new_getaddrinfo
    logger.info("Custom DNS resolver set up")


def encode_url(url):
    """Safely encode a URL for use in proxy endpoints"""
    return urllib.parse.quote(url, safe="") if url else ""


def parse_group_list(group_string):
    """Parse a comma-separated string into a list of trimmed strings"""
    return [group.strip() for group in group_string.split(",")] if group_string else []


def group_matches(group_title, pattern):
    """Check if a group title matches a pattern, supporting wildcards and exact matching"""
    # Convert to lowercase for case-insensitive matching
    group_lower = group_title.lower()
    pattern_lower = pattern.lower()

    # Handle spaces in pattern
    if " " in pattern_lower:
        # For patterns with spaces, split and check each part
        pattern_parts = pattern_lower.split()
        group_parts = group_lower.split()

        # If pattern has more parts than group, can't match
        if len(pattern_parts) > len(group_parts):
            return False

        # Check each part of the pattern against group parts
        for i, part in enumerate(pattern_parts):
            if i >= len(group_parts):
                return False
            if "*" in part or "?" in part:
                if not fnmatch.fnmatch(group_parts[i], part):
                    return False
            else:
                if part not in group_parts[i]:
                    return False
        return True

    # Check for wildcard patterns
    if "*" in pattern_lower or "?" in pattern_lower:
        return fnmatch.fnmatch(group_lower, pattern_lower)
    else:
        # Simple substring match for non-wildcard patterns
        return pattern_lower in group_lower
