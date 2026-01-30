# Fenbi Crawler

A powerful and robust crawler designed to extract structured exam data from the Fenbi website. It automates the process of navigating, submitting exams, and downloading detailed question data including analysis and images.

## Features

- **Structured Data Extraction**: Extracts comprehensive exam data (Stems, Options, Analysis, Material, Sources) into JSON format.
- **Image Handling**: Automatically downloads images locally and updates content links to point to local files, ensuring offline access.
- **Material Question Support**: Correctly groups sub-questions under their shared material for accurate representation.
- **Smart Navigation**:
    - **Persistence**: Maintains login session via `user_data` directory.
    - **Parallel Processing**: Processes multiple filter categories concurrently for faster execution.
    - **Robustness**: Handles network timeouts, retries, and page reloads automatically.
    - **Anti-Detection**: Uses stealth techniques to bypass basic anti-crawler measures.

## Prerequisites

- **Python 3.13+**
- **Package Manager**: `uv` (recommended) or `pip`

## Installation

1. **Install Dependencies**
   
   Using `uv`:
   ```bash
   uv sync
   ```
   
   Using `pip` (manual install):
   ```bash
   pip install playwright beautifulsoup4
   ```

2. **Install Playwright Browsers**
   ```bash
   uv run playwright install chromium
   # OR
   playwright install chromium
   ```

## Usage

1. **Run the Crawler**
   Execute the main script:
   ```bash
   uv run python main.py
   # OR
   python main.py
   ```

2. **Login Process**
   - A Chromium browser window will open.
   - **Log in manually** to your Fenbi account in this window.
   - Once logged in and on the target page (Question Bank / Past Papers), return to your terminal.
   - Press **Enter** to start the automation.

3. **Automation Flow**
   The script will:
   - Identify available exam filters (excluding "推荐").
   - Launch parallel workers for each filter.
   - Navigate to each exam paper.
   - If the exam hasn't been taken, it will **submit a blank paper**.
   - Wait for the analysis page to load.
   - Extract all data and download images.
   - Save the results in `downloads/`.

## Output Structure

- **Data**: `downloads/{filter_name}_{paper_title}.json`
- **Images**: `downloads/images/{paper_title}/{image_name}.png`

### JSON Format Example
```json
[
  {
    "id": "question_id",
    "type": "single/material",
    "stem": "<p>Question text...</p>",
    "options": ["A. ...", "B. ..."],
    "analysis": "<p>Explanation...</p>",
    "material": "<p>Shared content...</p>", // Only for material questions
    "local_images": {
      "original_url": "local_path"
    }
  }
]
```

## Troubleshooting

- **Login Issues**: If the automation fails to detect login, restart the script. The `user_data` folder preserves your session, so you shouldn't need to log in every time.
- **Timeout**: Network issues may cause timeouts. The script has built-in retries, but persistent failures may require checking your internet connection.
- **Missing Elements**: If the script logs "Could not find filters", ensure the browser works and the page is fully loaded before pressing Enter.
