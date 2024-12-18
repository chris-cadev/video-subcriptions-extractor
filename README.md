# Videos from Subscriptions Extractor

This project is a Python-based tool for extracting YouTube subscriptions and
their associated video metadata. It provides functionality to save the extracted
data into either a Solr database or a JSON file. The tool ensures traceability
and robust logging to aid in debugging and monitoring.

## Features

- Authenticate with YouTube API to access subscriptions and video metadata.
- Save extracted data into:
  - **Solr database** for efficient indexing and querying.
  - **JSON file** for local storage and manual analysis.
- Caching to avoid redundant API calls and optimize performance.
- Detailed and traceable logging for every significant step.

## Getting Started

### Quick Start

1. Authenticate with your Google account to access your YouTube subscriptions.
2. Choose your preferred output:
   - Save to a JSON file for offline use.
   - Save to a Solr database for advanced querying and analytics.
3. Run the script with simple commands:
   - To save data to a Solr database:
     `python src/channel_video_extractor/main.py --solr`
   - To save data to a JSON file:
     `python src/channel_video_extractor/main.py --output <json_file_path>`

Enjoy organized and detailed metadata from your YouTube subscriptions.

### Technical Details

#### Prerequisites

1. Python 3.7+
2. Required libraries (install via `requirements.txt`):
   ```bash
   pip install -r requirements.txt
   ```
3. A Solr instance, if using the Solr output option.
4. Google API credentials file for authenticating with YouTube.

#### Environment Variables

Create a `.env` file in the project directory and specify the following:

```env
SOLR_URL=<your_solr_url>
GOOGLE_CREDENTIALS_FILE=<path_to_google_credentials_file>
```

#### Installation

Clone the repository and navigate to the project folder:

```bash
git clone https://github.com/your-repo/video-subcriptions-extractor.git
cd video-subcriptions-extractor
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

or with [pdm](https://pdm-project.org/)

```bash
pdm install
```

### Usage

Run the script using the CLI options:

- Save data to Solr:
  ```bash
  python src/channel_video_extractor/main.py --solr
  ```
- Save data to a JSON file:
  ```bash
  python src/channel_video_extractor/main.py --output <json_file_path>
  ```

### Key Learning: Dealing with Two Types of Outputs

This project was an excellent opportunity to explore handling dual-output
scenarios:

1. **Solr Integration**: Learned how to interact with Solr for data storage and
   querying, including configuring the Solr client and managing connection
   issues.
2. **JSON File Output**: Developed logic for appending data to JSON files,
   ensuring compatibility with existing data structures.

These dual outputs were managed by implementing an abstract repository pattern,
allowing seamless switching between storage backends.

## Project Structure

```plaintext
.
├── docker-compose.yml    # Docker Compose file for setting up Solr instance
├── example.env           # Example environment file for configuration
├── pdm.lock              # PDM lockfile for dependency management
├── pyproject.toml        # Project configuration for PDM and dependencies
├── README.md             # Project documentation
├── src/
│   └── channel_video_extractor/
│       ├── __init__.py   # Module initialization
│       ├── main.py       # Main script for extraction
│       └── __pycache__/  # Compiled Python files
└── tests/                # Unit tests
    ├── __init__.py       # Test module initialization
    └── __pycache__/      # Compiled test files
```

## Logging and Traceability

The project uses Python's logging module to:

- Log detailed messages, including API calls, cache usage, and error details.
- Provide a clear trace of the execution flow for debugging and monitoring.

### Example Logs

- **Authentication**:
  ```plaintext
  2024-12-17 12:34:56 - INFO - Starting YouTube API authentication process.
  2024-12-17 12:34:57 - INFO - Authentication successful.
  ```
- **Video Metadata Extraction**:
  ```plaintext
  2024-12-17 12:35:00 - INFO - Extracted 15 videos for channel: https://www.youtube.com/channel/123456789.
  ```

## Contributing

Feel free to fork this repository and submit pull requests with improvements or
bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for
details.
