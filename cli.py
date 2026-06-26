#!/usr/bin/env python3
"""xtream2m3u CLI — generate M3U playlists from an Xtream IPTV provider.

Reuses the same service layer as the Flask app, so it accepts every filter
option exposed by the /m3u endpoint. Credentials can be passed as flags or
read from environment variables (XTREAM_URL / XTREAM_USERNAME / XTREAM_PASSWORD).

Examples:
  # Configure credentials once
  export XTREAM_URL=http://iptv.example.com:8080
  export XTREAM_USERNAME=myuser
  export XTREAM_PASSWORD=mypass

  # Print playlist to stdout
  python cli.py

  # Save to file with a filter
  python cli.py --wanted-groups "Sports*,News" --enable-catchup -o playlist.m3u

  # Combine with cron for periodic refresh:
  # 0 */6 * * * python /path/to/cli.py --wanted-groups "..." -o /var/iptv/list.m3u
"""
import argparse
import logging
import os
import sys

import json as _json

from app.services import (
    fetch_categories_and_channels,
    fetch_series_listing,
    generate_episodes_playlist,
    generate_m3u_playlist,
    validate_xtream_credentials,
)
from app.utils import group_matches, normalize_base_url, parse_group_list, setup_custom_dns


def main():
    parser = argparse.ArgumentParser(
        prog="xtream2m3u",
        description="Generate an M3U playlist from an Xtream IPTV provider.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Credentials (env vars provide defaults; flags override)
    parser.add_argument("--url", default=os.environ.get("XTREAM_URL"),
                        help="Xtream API URL (env: XTREAM_URL)")
    parser.add_argument("--username", default=os.environ.get("XTREAM_USERNAME"),
                        help="Xtream username (env: XTREAM_USERNAME)")
    parser.add_argument("--password", default=os.environ.get("XTREAM_PASSWORD"),
                        help="Xtream password (env: XTREAM_PASSWORD)")

    # Filters
    parser.add_argument("--wanted-groups", default="",
                        help="Comma-separated groups to include (supports * and ? wildcards)")
    parser.add_argument("--unwanted-groups", default="",
                        help="Comma-separated groups to exclude")

    # Content options (per-type, independent flags)
    parser.add_argument("--include-live", action=argparse.BooleanOptionalAction, default=True,
                        help="Include live channels (default: yes; pass --no-include-live to omit)")
    parser.add_argument("--include-vod", action="store_true",
                        help="Include movies (slower, adds 1-2min)")
    parser.add_argument("--include-series", action="store_true",
                        help="Include TV series (slowest, adds episode fetches)")
    parser.add_argument("--series", default="",
                        help="Comma-separated series IDs to restrict to (composes with --include-series)")
    parser.add_argument("--list-series", action="store_true",
                        help="Print available series as JSON (id, name, category) and exit")
    parser.add_argument("--enable-catchup", action="store_true",
                        help="Emit catchup/timeshift tags for archive-enabled channels")
    parser.add_argument("--include-channel-id", action="store_true",
                        help="Include the epg_channel_id tag on each entry")
    parser.add_argument("--channel-id-tag", default="channel-id",
                        help="Custom tag name for channel ID (default: channel-id)")
    parser.add_argument("--no-tvg-id", action="store_true",
                        help="Omit the tvg-id on live channels (some players, e.g. Emby, "
                             "show it as a channel number)")

    # Proxy options
    parser.add_argument("--no-stream-proxy", action="store_true",
                        help="Don't wrap stream URLs through a proxy (URLs stay raw)")
    parser.add_argument("--proxy-url", default=os.environ.get("PROXY_URL", ""),
                        help="Base URL for proxied content (env: PROXY_URL)")

    # Output
    parser.add_argument("-o", "--output", default="-",
                        help="Output file path, or '-' for stdout (default: stdout)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose progress logging to stderr")

    args = parser.parse_args()

    # Normalize the base URL (trim, add scheme, drop trailing slashes) so
    # endpoints never come out as "http://host//player_api.php".
    args.url = normalize_base_url(args.url)

    # All logs go to stderr so stdout stays a clean playlist when piping
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(message)s",
    )

    if not args.url or not args.username or not args.password:
        parser.error(
            "URL, username, and password are required. Provide them via "
            "--url/--username/--password or the XTREAM_URL/XTREAM_USERNAME/"
            "XTREAM_PASSWORD environment variables."
        )

    # Same DNS hardening the server uses
    setup_custom_dns()

    user_data, error_json, error_code = validate_xtream_credentials(
        args.url, args.username, args.password
    )
    if error_json:
        print(f"Authentication failed: {error_json}", file=sys.stderr)
        sys.exit(1)

    server_url = (
        f"http://{user_data['server_info']['url']}:{user_data['server_info']['port']}"
    )
    username_real = user_data["user_info"]["username"]
    password_real = user_data["user_info"]["password"]

    wanted_groups = parse_group_list(args.wanted_groups)
    unwanted_groups = parse_group_list(args.unwanted_groups)

    # --list-series: print JSON catalog of series and exit
    if args.list_series:
        series, category_names, error_json, error_code = fetch_series_listing(
            args.url, args.username, args.password
        )
        if error_json:
            print(f"Failed to fetch series listing: {error_json}", file=sys.stderr)
            sys.exit(1)
        result = []
        for s in series:
            category_id = s.get("category_id")
            category_name = category_names.get(category_id, "Uncategorized")
            if wanted_groups and not any(group_matches(category_name, w) for w in wanted_groups):
                continue
            if unwanted_groups and any(group_matches(category_name, u) for u in unwanted_groups):
                continue
            result.append({
                "series_id": s.get("series_id"),
                "name": s.get("name"),
                "category_id": category_id,
                "category_name": category_name,
            })
        sys.stdout.write(_json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        return

    # --series ID1,ID2: fetch episodes for those specific series only
    series_ids = [s.strip() for s in args.series.split(",") if s.strip()]
    if series_ids:
        listing, category_names, error_json, error_code = fetch_series_listing(
            args.url, args.username, args.password
        )
        if error_json:
            print(f"Failed to fetch series listing: {error_json}", file=sys.stderr)
            sys.exit(1)
        series_meta = {
            str(s.get("series_id")): {"name": s.get("name"), "category_id": s.get("category_id")}
            for s in listing
        }
        m3u = generate_episodes_playlist(
            url=args.url,
            username=username_real,
            password=password_real,
            server_url=server_url,
            series_ids=series_ids,
            series_meta=series_meta,
            category_names=category_names,
            no_stream_proxy=args.no_stream_proxy,
            proxy_url=args.proxy_url,
        )
    else:
        categories, streams, error_json, error_code = fetch_categories_and_channels(
            args.url, args.username, args.password,
            include_live=args.include_live,
            include_vod=args.include_vod,
            include_series=args.include_series,
            for_m3u=True,
        )
        if error_json:
            print(f"Failed to fetch data: {error_json}", file=sys.stderr)
            sys.exit(1)

        m3u = generate_m3u_playlist(
            url=args.url,
            username=username_real,
            password=password_real,
            server_url=server_url,
            categories=categories,
            streams=streams,
            wanted_groups=wanted_groups,
            unwanted_groups=unwanted_groups,
            no_stream_proxy=args.no_stream_proxy,
            include_series=args.include_series,
            include_channel_id=args.include_channel_id,
            channel_id_tag=args.channel_id_tag,
            enable_catchup=args.enable_catchup,
            include_tvg_id=not args.no_tvg_id,
            proxy_url=args.proxy_url,
        )

    # Both generators stream the playlist line-by-line (never held whole in
    # memory), so iterate rather than treating the result as a single string.
    if args.output == "-":
        for chunk in m3u:
            sys.stdout.write(chunk)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            for chunk in m3u:
                f.write(chunk)
        print(f"Wrote playlist to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
