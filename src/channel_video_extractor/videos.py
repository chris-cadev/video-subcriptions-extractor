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

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("YouTubeSubscriptionLogger")

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

class SolrRepository:
    def __init__(self, solr_url):
        self.solr = pysolr.Solr(solr_url, always_commit=True) if solr_url else None

    def save(self, data):
        if self.solr:
            try:
                unique_data = self._deduplicate_solr(data)
                if unique_data:
                    self.solr.add(unique_data)
                    logger.info("Data successfully saved to Solr.")
                else:
                    logger.info("No new data to save to Solr.")
            except Exception as e:
                logger.error("Failed to save data to Solr: %s", e, exc_info=True)
        else:
            logger.error("Solr URL is not configured. Cannot save data.")

    def _deduplicate_solr(self, data):
        unique_data = []
        for item in data:
            query = f"id:{item['id']}"
            results = self.solr.search(query)
            if not results.docs:
                unique_data.append(item)
        return unique_data

class JsonRepository:
    def __init__(self, filename):
        self.filename = filename

    def save(self, data):
        try:
            existing_data = []
            if os.path.exists(self.filename):
                with open(self.filename, "r") as f:
                    existing_data = json.load(f)

            existing_ids = {item['id'] for item in existing_data}
            unique_data = [item for item in data if item['id'] not in existing_ids]

            if unique_data:
                existing_data.extend(unique_data)
                with open(self.filename, "w") as f:
                    json.dump(existing_data, f, indent=2)
                logger.info("Data successfully appended to %s.", self.filename)
            else:
                logger.info("No new data to append to %s.", self.filename)

        except Exception as e:
            logger.error("Failed to append data to JSON file: %s", e, exc_info=True)

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
                logger.info("Using cached data for %s.", identifier)
                return data
            else:
                logger.info("Cache expired for %s. Fetching new data.", identifier)
    return None

def save_to_cache(identifier, data):
    cache_file = get_cache_file_path(identifier)
    with open(cache_file, "wb") as f:
        pickle.dump((time.time(), data), f)
    logger.info("Data cached for %s.", identifier)

# YouTube API authentication
def authenticate_youtube():
    client_secrets_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
    if not client_secrets_file:
        logger.critical("Google credentials file is not specified in the environment variables.")
        raise RuntimeError("Missing Google credentials file.")

    logger.info("Starting YouTube API authentication process.")
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, SCOPES
    )

    port = DEFAULT_PORT
    while True:
        try:
            logger.info("Attempting to bind to port %d for authentication.", port)
            credentials = flow.run_local_server(port=port)
            break
        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning("Port %d is in use. Trying next port.", port)
                port += 1
                if port > DEFAULT_PORT + 10:
                    logger.critical("Unable to find an available port for authentication.")
                    raise RuntimeError("Unable to find an available port.")
            else:
                logger.error("Unexpected error during port binding: %s", e, exc_info=True)
                raise

    logger.info("Authentication successful.")
    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials), \
           googleapiclient.discovery.build("oauth2", "v2", credentials=credentials)

def sanitize_solr_query(value):
    # Escape Solr special characters if necessary
    return f'"{value}"' if value.startswith('-') else value

# Extract subscriptions
def extract_subscriptions(youtube_api, oauth2_api, repository):
    try:
        logger.info("Starting subscription extraction.")
        user_info = oauth2_api.userinfo().get().execute()
        user_email = user_info.get("email", "unknown")
        logger.info("Authenticated user email: %s", user_email)

        next_page_token = None
        subscription_count = 0

        while True:
            logger.info("Fetching subscription list with page token: %s", next_page_token)
            request = youtube_api.subscriptions().list(
                part="snippet",
                mine=True,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()

            subscriptions = response.get("items", [])
            logger.info("Fetched %d subscriptions in this batch.", len(subscriptions))

            next_page_token = response.get("nextPageToken")

            for sub in subscriptions:
                channel_id = sub["snippet"]["resourceId"]["channelId"]
                channel_title = sub["snippet"]["title"]
                channel_url = f"https://www.youtube.com/channel/{channel_id}"

                logger.info("Extracting videos for channel: %s (%s)", channel_title, channel_id)
                videos = extract_videos(channel_url)

                for video in videos:
                    video.update({
                        "channelId": channel_id,
                        "channelTitle": channel_title,
                        "userEmail": user_email
                    })
                repository.save(videos)

            subscription_count += len(subscriptions)

            if not next_page_token:
                break

        logger.info("Total subscriptions processed: %d", subscription_count)

    except HttpError as e:
        logger.error("YouTube API error: %s", e, exc_info=True)

def normalize_thumbnails(thumbnails):
    if isinstance(thumbnails, list):
        # Extract only the first thumbnail URL or other required fields
        return [thumb.get('url') for thumb in thumbnails if 'url' in thumb]
    return []

def generate_view_object(entry: dict):
    return {
        "id": sanitize_solr_query(entry.get("id")),
        "url": entry.get("url"),
        "title": entry.get("title"),
        "description": entry.get("description"),
        "view_count": entry.get("view_count"),
        "duration": entry.get("duration"),
        "thumbnails": normalize_thumbnails(entry.get("thumbnails")),
        "release_timestamp": entry.get("release_timestamp"),
        "channel_is_verified": entry.get("channel_is_verified"),
        "live_status": entry.get("live_status"),
    }

# Extract video metadata
def extract_videos(channel_url):
    try:
        logger.info("Checking cache for channel URL: %s", channel_url)
        info_dict = load_from_cache(channel_url)

        if not info_dict:
            logger.info("Fetching video data from YouTube for channel: %s", channel_url)
            with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True}) as ydl:
                info_dict = ydl.extract_info(channel_url, download=False)
                save_to_cache(channel_url, info_dict)

        videos = []
        for entry in info_dict.get('entries', []):
            if entry.get('_type') == 'playlist':
                for playlist_enty in entry.get('entries',[]):
                    videos.append(generate_view_object(playlist_enty))
            if entry.get('_type') == 'url':
                videos.append(generate_view_object(entry))
        logger.info("Extracted %d videos for channel: %s", len(videos), channel_url)
        return videos

    except Exception as e:
        logger.error("Error extracting videos for %s: %s", channel_url, e, exc_info=True)
        return []

@click.command()
@click.option("--output", type=click.Path(), help="File path to save the data as JSON.")
@click.option("--solr", is_flag=True, help="Save data to Solr database.")
def cli(output, solr):
    try:
        logger.info("Starting CLI with parameters: output=%s, solr=%s", output, solr)
        youtube_api, oauth2_api = authenticate_youtube()

        repository = None
        if solr:
            logger.info("Using Solr repository.")
            repository = SolrRepository(SOLR_URL)
        elif output:
            logger.info("Using JSON repository with file path: %s", output)
            repository = JsonRepository(output)
        else:
            logger.error("Either --output or --solr must be specified.")
            return

        extract_subscriptions(youtube_api, oauth2_api, repository)
        logger.info("CLI execution completed successfully.")
    except Exception as e:
        logger.error("An unexpected error occurred: %s", e, exc_info=True)

if __name__ == "__main__":
    cli()
