import json

import requests
from flask import Flask, Response, request
from requests.exceptions import SSLError

app = Flask(__name__)

def curl_request(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except SSLError:
        return None
    except requests.RequestException:
        return None

@app.route('/m3u', methods=['GET'])
def generate_m3u():
    # Get parameters from the URL
    url = request.args.get('url')
    username = request.args.get('username')
    password = request.args.get('password')
    unwanted_groups = request.args.get('unwanted_groups', '')  # This is a comma-separated list

    if not url or not username or not password:
        return "Missing url, username, or password", 400

    # Convert unwanted groups into a list
    unwanted_groups = [group.strip() for group in unwanted_groups.split(',')] if unwanted_groups else []

    # Verify the credentials and the provided URL
    mainurl_json = curl_request(f'{url}/player_api.php?username={username}&password={password}')
    if mainurl_json is None:
        return "Unable to connect to the server. There might be an SSL certificate issue. Please check your URL and try again.", 503

    try:
        mainurlraw = json.loads(mainurl_json)
    except json.JSONDecodeError:
        return "Invalid response data from the server", 500

    if 'user_info' not in mainurlraw or 'server_info' not in mainurlraw:
        return "Invalid response data", 400

    # Fetch live streams
    livechannel_json = curl_request(f'{url}/player_api.php?username={username}&password={password}&action=get_live_streams')
    if livechannel_json is None:
        return "Failed to retrieve live streams. There might be a connection issue.", 503

    try:
        livechannelraw = json.loads(livechannel_json)
    except json.JSONDecodeError:
        return "Invalid live streams data from the server", 500

    if not isinstance(livechannelraw, list):
        return "Invalid live streams data", 500

    # Fetch live categories
    category_json = curl_request(f'{url}/player_api.php?username={username}&password={password}&action=get_live_categories')
    if category_json is None:
        return "Failed to retrieve live categories. There might be a connection issue.", 503

    try:
        categoryraw = json.loads(category_json)
    except json.JSONDecodeError:
        return "Invalid live categories data from the server", 500

    if not isinstance(categoryraw, list):
        return "Invalid live categories data", 500

    username = mainurlraw['user_info']['username']
    password = mainurlraw['user_info']['password']

    server_url = f"http://{mainurlraw['server_info']['url']}:{mainurlraw['server_info']['port']}"
    fullurl = f"{server_url}/live/{username}/{password}/"

    categoryname = {cat['category_id']: cat['category_name'] for cat in categoryraw}

    # Generate M3U playlist
    m3u_playlist = "#EXTM3U\n"
    for channel in livechannelraw:
        if channel['stream_type'] == 'live':
            group_title = categoryname[channel["category_id"]]
            # Skip this channel if its group is in the unwanted list
            if not any(unwanted_group.lower() in group_title.lower() for unwanted_group in unwanted_groups):
                m3u_playlist += f'#EXTINF:0 tvg-name="{channel["name"]}" group-title="{group_title}",{channel["name"]}\n'
                m3u_playlist += f'{fullurl}{channel["stream_id"]}.ts\n'

    # Return the M3U playlist as a downloadable file
    return Response(m3u_playlist, mimetype='audio/x-scpls', headers={"Content-Disposition": "attachment; filename=LiveStream.m3u"})

if __name__ == '__main__':
    app.run(debug=True)