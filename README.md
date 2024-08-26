<p align="center">
  <img src="docs/assets/logo.png" alt="xtream2m3u logo" width="200"
  style = "border-radius: 30%;"/>
</p>

<h1 align="center">xtream2m3u</h1>

[![Discord][discord-shield]][discord-url]
[![Language][language-shield]][language-url]
[![License][license-shield]][license-url]

<p align="center">
  <strong>Convert Xtream IPTV APIs into customizable M3U playlists with ease</strong>
</p>

<p align="center">
  <a href="#about">About</a> •
  <a href="#prerequisites">Prerequisites</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#license">License</a> •
  <a href="#disclaimer">Disclaimer</a>
</p>

## About

xtream2m3u is a powerful and flexible tool designed to bridge the gap between Xtream API-based IPTV services and M3U playlist-compatible media players. It provides a simple API that fetches live streams from Xtream IPTV services, filters out unwanted channel groups, and generates a customized M3U playlist file.

### Why xtream2m3u?

Many IPTV providers use the Xtream API, which isn't directly compatible with media players that accept M3U playlists. xtream2m3u solves this problem by:

1. Connecting to Xtream API-based IPTV services
2. Fetching the list of available live streams
3. Allowing users to filter out unwanted channel groups
4. Generating a standard M3U playlist that's compatible with a wide range of media players

## Prerequisites

To use xtream2m3u, you'll need:

- An active subscription to an IPTV service that uses the Xtream API

For deployment, you'll need one of the following:

- Docker and Docker Compose
- Python 3.9 or higher

## Installation

### Using Docker (Recommended)

1. Install Docker and Docker Compose
2. Clone the repository:
   ```
   git clone https://github.com/ovosimpatico/xtream2m3u.git
   cd xtream2m3u
   ```
3. Run the application:
   ```
   docker-compose up -d
   ```

### Native Python Installation

1. Install Python (3.9 or higher)
2. Clone the repository:
   ```
   git clone https://github.com/ovosimpatico/xtream2m3u.git
   cd xtream2m3u
   ```
3. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```
4. Install the required packages:
   ```
   pip install -r requirements.txt
   ```
5. Run the application:
   ```
   python run.py
   ```

## Usage

### API Endpoint

The endpoint for generating M3U playlists is:

```
GET /m3u
```

#### Query Parameters

- `url` (required): The base URL of your IPTV service
- `username` (required): Your IPTV service username
- `password` (required): Your IPTV service password
- `unwanted_groups` (optional): A comma-separated list of group names to exclude

#### Example Request

```
http://localhost:5000/m3u?url=http://your-iptv-service.com&username=your_username&password=your_password&unwanted_groups=news,sports
```

#### Response

The API will return an M3U playlist file that you can use with compatible media players.

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPLv3). This license requires that any modifications to the code must also be made available under the same license, even when the software is run as a service (e.g., over a network). See the [LICENSE](LICENSE) file for details.

## Disclaimer

xtream2m3u is a tool for generating M3U playlists from Xtream API-based IPTV services but does not provide IPTV services itself. A valid subscription to an IPTV service using the Xtream API is required to use this tool.

xtream2m3u does not endorse piracy and requires users to ensure they have the necessary rights and permissions. The developers are not responsible for any misuse of the software or violations of IPTV providers' terms of service.

[language-shield]: https://img.shields.io/github/languages/top/ovosimpatico/xtream2m3u?logo=python&logoColor=yellow&style=for-the-badge
[language-url]: https://www.python.org/

[license-shield]: https://img.shields.io/github/license/ovosimpatico/xtream2m3u?style=for-the-badge
[license-url]: https://github.com/ovosimpatico/xtream2m3u/blob/main/LICENSE

[discord-shield]: https://img.shields.io/discord/1068543728274382868?color=7289da&label=Support&logo=discord&logoColor=7289da&style=for-the-badge
[discord-url]: https://discord.gg/7qK8sfEq2q
[discord-banner]: https://discordapp.com/api/guilds/1068543728274382868/widget.png?style=banner2