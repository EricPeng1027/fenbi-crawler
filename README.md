
# Fenbi Crawler

This project contains a crawler for the Fenbi website to extract structured exam data, including questions, options, correct answers, analysis, and images.

## Features

- **Structured Data Extraction**: Extracts exam data into JSON format.
- **Image Downloading**: Downloads images locally and updates content links to point to local files.
- **Material Question Support**: Correctly handles material analysis questions, grouping them with their shared material.
- **Robust Navigation**: automated retry, filter iteration, and state management.

## Prerequisites

- Python 3.13+
- `uv` package manager (recommended) or `pip`

## Installation

1. Install dependencies:
   ```bash
   uv sync
   # OR
   pip install playwright
   ```

2. Install Playwright browsers:
   ```bash
   uv run playwright install (or playwright install)
   ```

## Usage

1. Run the crawler script:
   ```bash
   uv run python fenbi_crawler.py
   ```

2. A browser window will open.
3. Log in to your Fenbi account manually in that window.
4. Once logged in and on the target page, return to your terminal and press **Enter**.
5. The script will automatically:
    - Iterate through all filters (excluding "推荐", "行测").
    - Open each exam paper.
    - Submit a blank paper.
    - Wait for analysis to load.
    - Extract detailed data (Stem, Options, Analysis, Source, Keypoints).
    - Download images and normalize links.
    - Save the result as a JSON file in the `downloads` folder.

## Output

- **JSON Files**: Saved in `downloads/{filter_name}_{paper_title}.json`.
- **Images**: Saved in `downloads/images/{paper_title}/`.

Each JSON file contains a list of questions with fields like `stem`, `options`, `analysis`, `material` (for shared text), and `local_images` map. Image tags in the content are updated to point to the local `images/` directory.
