# -*- coding: utf-8 -*-
import os
import json
import time
import logging
import pickle
import click
import pysolr
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
import yt_dlp
import socket

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
SOLR_URL = os.getenv("SOLR_URL")
CACHE_FOLDER = "cache"
CACHE_EXPIRATION_SECONDS = 60 * 60 * 8
DEFAULT_PORT = 8080

# Ensure cache folder exists
os.makedirs(CACHE_FOLDER, exist_ok=True)

# Solr client
solr = pysolr.Solr(SOLR_URL, always_commit=True) if SOLR_URL else None

# Caching functions
def get_cache_file_path(identifier):
    safe_filename = identifier.replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_FOLDER, f"{safe_filename}.pkl")

def load_from_cache(identifier):
    cache_file = get_cache_file_path(identifier)
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            cached_time, data = pickle.load(f)
            if time.time() - cached_time < CACHE_EXPIRATION_SECONDS:
                logger.info("Using cached data for %s", identifier)
                return data
            else:
                logger.info("Cache expired for %s", identifier)
    return None

def save_to_cache(identifier, data):
    cache_file = get_cache_file_path(identifier)
    with open(cache_file, "wb") as f:
        pickle.dump((time.time(), data), f)

# YouTube API authentication
def authenticate_youtube():
    client_secrets_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, SCOPES
    )

    # Try binding to an available port
    port = DEFAULT_PORT
    while True:
        try:
            credentials = flow.run_local_server(port=port)
            break
        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning("Port %d is in use, trying next port", port)
                port += 1
                if port > DEFAULT_PORT + 10:
                    raise RuntimeError("Unable to find an available port")
            else:
                raise

    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials), \
           googleapiclient.discovery.build("oauth2", "v2", credentials=credentials)

# Extract subscriptions
def extract_subscriptions(youtube_api, oauth2_api):
    try:
        logger.info("Extracting subscriptions...")
        user_info = oauth2_api.userinfo().get().execute()
        user_email = user_info["email"]

        subscriptions = []
        next_page_token = None
        while True:
            request = youtube_api.subscriptions().list(
                part="snippet",
                mine=True,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            subscriptions.extend(response.get("items", []))
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info("Found %d subscriptions", len(subscriptions))
        return user_email, subscriptions
    except HttpError as e:
        logger.error("YouTube API error: %s", e)
        return None, []

# Extract video metadata
def extract_videos(channel_url):
    try:
        info_dict = load_from_cache(channel_url)
        if not info_dict:
            with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True}) as ydl:
                info_dict = ydl.extract_info(channel_url, download=False)
                save_to_cache(channel_url, info_dict)

        videos = []
        for entry in info_dict.get('entries', []):
            if entry.get('_type') == 'url':
                videos.append({
                    "id": entry.get("id"),
                    "url": entry.get("url"),
                    "title": entry.get("title"),
                    "description": entry.get("description"),
                    "view_count": entry.get("view_count"),
                    "duration": entry.get("duration"),
                })
        return videos
    except Exception as e:
        logger.error("Error extracting videos for %s: %s", channel_url, e)
        return []

# Save to JSON
def save_to_json(data, filename):
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Data saved to %s", filename)
    except Exception as e:
        logger.error("Failed to save data to JSON: %s", e)

# Save to Solr
def save_to_solr(data):
    if solr:
        try:
            solr.add(data)
            logger.info("Data saved to Solr")
        except Exception as e:
            logger.error("Failed to save data to Solr: %s", e)
    else:
        logger.error("Solr URL not configured")

@click.command()
@click.option("--output", type=click.Path(), help="File path to save the data as JSON.")
@click.option("--solr", is_flag=True, help="Save data to Solr database.")
def cli(output, solr):
    try:
        youtube_api, oauth2_api = authenticate_youtube()
        user_email, subscriptions = extract_subscriptions(youtube_api, oauth2_api)

        if not subscriptions:
            logger.warning("No subscriptions found or failed to fetch data.")
            return

        all_data = []
        for sub in subscriptions:
            channel_id = sub["snippet"]["resourceId"]["channelId"]
            channel_title = sub["snippet"]["title"]
            channel_url = f"https://www.youtube.com/channel/{channel_id}"

            logger.info("Extracting videos for channel: %s", channel_title)
            videos = extract_videos(channel_url)
            for video in videos:
                video.update({
                    "channelId": channel_id,
                    "channelTitle": channel_title,
                    "userEmail": user_email
                })
            all_data.extend(videos)

        if output:
            save_to_json(all_data, output)

        if solr:
            save_to_solr(all_data)

    except Exception as e:
        logger.error("An unexpected error occurred: %s", e)

if __name__ == "__main__":
    cli()
