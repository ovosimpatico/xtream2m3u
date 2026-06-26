"""API routes for Xtream Codes proxy (categories, M3U, XMLTV, series, episodes)"""
import json
import logging
import os
import re

from flask import Blueprint, Response, current_app, jsonify, request

from app.services import (
    fetch_api_data,
    fetch_categories_and_channels,
    fetch_series_listing,
    generate_episodes_playlist,
    generate_m3u_playlist,
    validate_xtream_credentials,
)
from app.utils import encode_url, group_matches, normalize_base_url, parse_group_list

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


def parse_content_flags(data, is_post):
    """Parse include_live / include_vod / include_series flags with soft backward compat.

    Legacy behavior: ?include_vod=true alone (no explicit include_series) used to mean
    'include both movies and series'. We preserve that when the caller hasn't opted in
    to the new granular semantics.
    """
    def _raw(key):
        if is_post:
            return data.get(key)
        return request.args.get(key)

    def _bool(key, default):
        raw = _raw(key)
        if raw is None:
            return default
        return str(raw).lower() == "true"

    include_live = _bool("include_live", True)
    include_vod = _bool("include_vod", False)
    include_series = _bool("include_series", False)

    # Soft compat: legacy include_vod=true with no explicit include_series
    # means 'movies + series' (the old semantics).
    series_explicit = _raw("include_series") is not None
    if include_vod and not series_explicit:
        include_series = True

    return include_live, include_vod, include_series


def get_required_params():
    """Get and validate the required parameters from the request (supports both GET and POST)"""
    # Handle both GET and POST requests
    if request.method == "POST":
        data = request.get_json() or {}
        url = data.get("url")
        username = data.get("username")
        password = data.get("password")
        proxy_url = data.get("proxy_url", current_app.config['DEFAULT_PROXY_URL']) or request.host_url.rstrip("/")
    else:
        url = request.args.get("url")
        username = request.args.get("username")
        password = request.args.get("password")
        proxy_url = request.args.get("proxy_url", current_app.config['DEFAULT_PROXY_URL']) or request.host_url.rstrip("/")

    # Normalize the pasted base URL (trim, add scheme, drop trailing slashes) so
    # endpoints never come out as "http://host//player_api.php".
    url = normalize_base_url(url)

    if not url or not username or not password:
        return (
            None,
            None,
            None,
            None,
            jsonify({"error": "Missing Parameters", "details": "Required parameters: url, username, and password"}),
            400
        )

    return url, username, password, proxy_url, None, None


@api_bp.route("/categories", methods=["GET"])
def get_categories():
    """Get all available categories from the Xtream API"""
    # Get and validate parameters
    url, username, password, proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    # Parse granular content-type flags (with soft backward compat for legacy include_vod)
    include_live, include_vod, include_series = parse_content_flags({}, is_post=False)
    logger.info(f"Categories requested - live: {include_live}, vod: {include_vod}, series: {include_series}")

    # Validate credentials
    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Fetch categories
    categories, channels, error_json, error_code = fetch_categories_and_channels(
        url, username, password,
        include_live=include_live, include_vod=include_vod, include_series=include_series,
    )
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Return categories as JSON
    return json.dumps(categories), 200, {"Content-Type": "application/json"}


@api_bp.route("/xmltv", methods=["GET"])
def generate_xmltv():
    """Generate a filtered XMLTV file from the Xtream API"""
    # Get and validate parameters
    url, username, password, proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    # No filtering supported for XMLTV endpoint

    # Validate credentials
    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Fetch XMLTV data
    base_url = url.rstrip("/")
    xmltv_url = f"{base_url}/xmltv.php?username={username}&password={password}"
    xmltv_data = fetch_api_data(xmltv_url, timeout=20)  # Longer timeout for XMLTV

    if isinstance(xmltv_data, tuple):  # Error response
        return json.dumps(xmltv_data[0]), xmltv_data[1], {"Content-Type": "application/json"}

    # If not proxying, return the original XMLTV
    if not proxy_url:
        return Response(
            xmltv_data, mimetype="application/xml", headers={"Content-Disposition": "attachment; filename=guide.xml"}
        )

    # Replace image URLs in the XMLTV content with proxy URLs
    def replace_icon_url(match):
        original_url = match.group(1)
        proxied_url = f"{proxy_url}/image-proxy/{encode_url(original_url)}"
        return f'<icon src="{proxied_url}"'

    xmltv_data = re.sub(r'<icon src="([^"]+)"', replace_icon_url, xmltv_data)

    # Return the XMLTV data
    return Response(
        xmltv_data, mimetype="application/xml", headers={"Content-Disposition": "attachment; filename=guide.xml"}
    )


@api_bp.route("/m3u", methods=["GET", "POST"])
def generate_m3u():
    """Generate a filtered M3U playlist from the Xtream API"""
    # Get and validate parameters
    url, username, password, proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    # Parse filter parameters (support both GET and POST for large filter lists)
    if request.method == "POST":
        data = request.get_json() or {}
        unwanted_groups = parse_group_list(data.get("unwanted_groups", ""))
        wanted_groups = parse_group_list(data.get("wanted_groups", ""))
        no_stream_proxy = str(data.get("nostreamproxy", "")).lower() == "true"
        include_channel_id = str(data.get("include_channel_id", "false")).lower() == "true"
        channel_id_tag = str(data.get("channel_id_tag", "channel-id"))
        enable_catchup = str(data.get("enable_catchup", "false")).lower() == "true"
        no_tvg_id = str(data.get("no_tvg_id", "false")).lower() == "true"
        logger.info("🔄 Processing POST request for M3U generation")
    else:
        data = {}
        unwanted_groups = parse_group_list(request.args.get("unwanted_groups", ""))
        wanted_groups = parse_group_list(request.args.get("wanted_groups", ""))
        no_stream_proxy = request.args.get("nostreamproxy", "").lower() == "true"
        include_channel_id = request.args.get("include_channel_id", "false") == "true"
        channel_id_tag = request.args.get("channel_id_tag", "channel-id")
        enable_catchup = request.args.get("enable_catchup", "false").lower() == "true"
        no_tvg_id = request.args.get("no_tvg_id", "false").lower() == "true"
        logger.info("🔄 Processing GET request for M3U generation")

    # Parse granular content-type flags
    include_live, include_vod, include_series = parse_content_flags(
        data, is_post=(request.method == "POST")
    )
    logger.info(f"Content types — live: {include_live}, vod: {include_vod}, series: {include_series}")

    if include_vod or include_series:
        logger.warning("⚠️  M3U generation with VOD/Series enabled - expect 2-5 minute generation time!")
    else:
        logger.info("⚡ M3U generation for live content only - should be fast!")

    # Log filter parameters (truncate if too long for readability)
    wanted_display = f"{len(wanted_groups)} groups" if len(wanted_groups) > 10 else str(wanted_groups)
    unwanted_display = f"{len(unwanted_groups)} groups" if len(unwanted_groups) > 10 else str(unwanted_groups)
    logger.info(f"Filter parameters - wanted_groups: {wanted_display}, unwanted_groups: {unwanted_display}, include_vod: {include_vod}")

    # Warn about massive filter lists
    total_filters = len(wanted_groups) + len(unwanted_groups)
    if total_filters > 20:
        logger.warning(f"⚠️  Large filter list detected ({total_filters} categories) - this will be slower!")
    if total_filters > 50:
        logger.warning(f"🐌 MASSIVE filter list ({total_filters} categories) - expect 3-5 minute processing time!")

    # Validate credentials
    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Fetch categories and channels
    categories, streams, error_json, error_code = fetch_categories_and_channels(
        url, username, password,
        include_live=include_live, include_vod=include_vod, include_series=include_series,
        for_m3u=True,
    )
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Extract user info and server URL
    username = user_data["user_info"]["username"]
    password = user_data["user_info"]["password"]

    server_url = f"http://{user_data['server_info']['url']}:{user_data['server_info']['port']}"

    # Generate M3U playlist
    m3u_playlist = generate_m3u_playlist(
        url=url,
        username=username,
        password=password,
        server_url=server_url,
        categories=categories,
        streams=streams,
        wanted_groups=wanted_groups,
        unwanted_groups=unwanted_groups,
        no_stream_proxy=no_stream_proxy,
        include_series=include_series,
        include_channel_id=include_channel_id,
        channel_id_tag=channel_id_tag,
        enable_catchup=enable_catchup,
        include_tvg_id=not no_tvg_id,
        proxy_url=proxy_url
    )

    # Determine filename based on content included
    filename = "FullPlaylist.m3u" if (include_vod or include_series) else "LiveStream.m3u"

    # Return the M3U playlist with proper CORS headers for frontend
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

    return Response(m3u_playlist, mimetype="audio/x-scpls", headers=headers)


@api_bp.route("/series", methods=["GET"])
def list_series():
    """Return a JSON list of available series with their category info.

    Lightweight — does not fetch individual series episodes. Supports the same
    wanted_groups / unwanted_groups filtering as /m3u (matched against the
    series' category name).
    """
    url, username, password, proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    wanted_groups = parse_group_list(request.args.get("wanted_groups", ""))
    unwanted_groups = parse_group_list(request.args.get("unwanted_groups", ""))

    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    series, category_names, error_json, error_code = fetch_series_listing(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    result = []
    for s in series:
        category_id = s.get("category_id")
        category_name = category_names.get(category_id, "Uncategorized")

        if wanted_groups:
            if not any(group_matches(category_name, w) for w in wanted_groups):
                continue
        elif unwanted_groups:
            if any(group_matches(category_name, u) for u in unwanted_groups):
                continue

        result.append({
            "series_id": s.get("series_id"),
            "name": s.get("name"),
            "category_id": category_id,
            "category_name": category_name,
        })

    logger.info(f"Returning {len(result)} series (filtered from {len(series)} total)")
    return jsonify(result)


@api_bp.route("/episodes", methods=["GET", "POST"])
def get_episodes():
    """Return an M3U playlist of episodes for a specific list of series IDs.

    Use ?series=ID1,ID2,ID3 (or POST body) to pick which series. Avoids the
    "fetch episodes for every series" slowness of /m3u with include_series=true.
    """
    url, username, password, proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    if request.method == "POST":
        data = request.get_json() or {}
        series_param = str(data.get("series", ""))
        no_stream_proxy = str(data.get("nostreamproxy", "")).lower() == "true"
    else:
        series_param = request.args.get("series", "")
        no_stream_proxy = request.args.get("nostreamproxy", "").lower() == "true"

    series_ids = [s.strip() for s in series_param.split(",") if s.strip()]
    if not series_ids:
        return (
            jsonify({"error": "Missing Parameter", "details": "series parameter is required (comma-separated IDs)"}),
            400,
        )

    logger.info(f"📺 /episodes requested for {len(series_ids)} series IDs")

    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Fetch series listing to map series_id -> name + category for group-title
    series, category_names, error_json, error_code = fetch_series_listing(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    series_meta = {
        str(s.get("series_id")): {
            "name": s.get("name"),
            "category_id": s.get("category_id"),
            "cover": s.get("cover"),
        }
        for s in series
    }

    username_real = user_data["user_info"]["username"]
    password_real = user_data["user_info"]["password"]
    server_url = f"http://{user_data['server_info']['url']}:{user_data['server_info']['port']}"

    m3u = generate_episodes_playlist(
        url=url,
        username=username_real,
        password=password_real,
        server_url=server_url,
        series_ids=series_ids,
        series_meta=series_meta,
        category_names=category_names,
        no_stream_proxy=no_stream_proxy,
        proxy_url=proxy_url,
    )

    headers = {
        "Content-Disposition": "attachment; filename=Episodes.m3u",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    return Response(m3u, mimetype="audio/x-scpls", headers=headers)
