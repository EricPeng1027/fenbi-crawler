
import asyncio
from playwright.async_api import async_playwright
import os
import json
import re
import hashlib
from bs4 import BeautifulSoup, Comment
import urllib.parse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("crawler.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


import random

URL = "https://www.fenbi.com/spa/tiku/guide/realTest/xingce/xingce"

async def random_wait(page, min_ms=1000, max_ms=3000):
    """Waits for a random amount of time to simulate human behavior."""
    duration = random.randint(min_ms, max_ms)
    await page.wait_for_timeout(duration)


async def reset_to_list(page, filter_name):
    """Resets the page to the list view and ensures the correct filter is active."""
    current_url = page.url
    if not current_url.startswith(URL):
        print(f"    Navigating back to list URL from {current_url}")
        await page.goto(URL)
        await page.wait_for_load_state("networkidle")
    
    # Check if the correct filter is active
    try:
        await page.wait_for_selector("span.categories-item")
        filters = await page.query_selector_all("span.categories-item")
        target_filter = None
        for f in filters:
            if await f.inner_text() == filter_name:
                target_filter = f
                break
        
        if target_filter:
            # Check if active
            class_attr = await target_filter.get_attribute("class")
            if "active" not in class_attr:
                print(f"    Re-clicking filter: {filter_name}")
                await random_wait(page, 500, 1500)
                await target_filter.click()
                await random_wait(page, 2000, 4000)
        else:
            print(f"    Warning: Could not find filter {filter_name} during reset.")
    except Exception as e:
        print(f"    Error resetting to list: {e}")



def clean_element(element):
    """
    Recursively cleans an HTML element (soup object) to remove useless markup.
    It unwraps almost everything except <p> and <img> (and maybe <br>).
    """
    if element is None:
        return ""
    
    # Remove comments
    for comment in element.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
        
    # Remove unwanted tags completely (input, script, style, button, etc.)
    for tag in element.find_all(['input', 'style', 'script', 'button', 'link', 'meta']):
        tag.decompose()

    # Unwrap tags that we want to flatten into text/parent
    # We unwrap div, span, a, app-format-html, and even p (if we want pure text + img).
    # But usually <p> is good for structure.
    # The user specifically mentioned div, a, app-format-html.
    unwrap_tags = ['app-format-html', 'div', 'span', 'a', 'strong', 'b', 'i', 'em', 'u', 'p']
    
    for tag_name in unwrap_tags:
        for tag in element.find_all(tag_name):
            tag.unwrap()
    
    # Iterate over all remaining tags (should be mostly p, img, br)
    for tag in element.find_all(True):
        if tag.name == 'img':
            src = tag.get('src', '')

            
            # Keep only essential attributes
            attrs = dict(tag.attrs)
            for attr in attrs:
                if attr not in ['src', 'alt', 'width', 'height']:
                    del tag[attr]
        
        else:
             # Unwrap everything else we missed or didn't explicitly handle?
             # For safety, let's just strip attributes of everything else.
             # Or maybe unwrap them too if not img/br.
             if tag.name not in ['img', 'br']:
                 tag.unwrap()
                 
    # Return the inner HTML
    return element.decode_contents().strip()



async def extract_exam_data(page):
    """Extracts question data from the analysis page using Python + BS4."""
    print("    Extracting exam data...")
    
    # Wait for questions to load
    try:
        await page.wait_for_selector(".ti-container", timeout=30000)
    except:
        print("    Timeout waiting for .ti-container")
        return []
        
    # Wait for analysis content to be populated
    # We will grab the main container HTML
    max_retries = 10
    
    for attempt in range(max_retries):
        # Grab the container HTML. Try specific container first, then Body.
        # We need the outer HTML of the list container to preserve structure.
        content_html = await page.evaluate("""() => {
            const container = document.querySelector('.tis-container');
            return container ? container.outerHTML : document.body.outerHTML;
        }""")
        
        soup = BeautifulSoup(content_html, 'html.parser')
        
        # Check if analysis is loaded (simple heuristic: look for '解析' or check if we got questions)
        # However, we are parsing in Python now.
        
        questions_data = []
        
        # Determine root elements
        # If we got .tis-container, the children are .ti
        # If we got body, we search for .ti
        
        root = soup.find(class_='tis-container')
        if root:
            ti_elements = root.find_all(class_='ti', recursive=False)
        else:
            ti_elements = soup.find_all(class_='ti')
            
        if not ti_elements:
             await asyncio.sleep(random.uniform(2, 4))
             continue

        # Prepare global question counter for this exam
        global_question_index = 1

        formatted_items = []
        
        for idx, ti in enumerate(ti_elements):
            # Check if it is a resizable container (Material Group)
            resizable = ti.find(class_='resizable-container')
            
            if resizable:
                # Material Group
                material_data = {
                    "type": "material",
                    "material": {
                        "content": "",
                        "images": []
                    },
                    "questions": []
                }
                
                # Extract Material
                mat_el = resizable.find(class_='materials-container')
                if mat_el:
                    # Extract Images for downloading later
                    for img in mat_el.find_all('img'):
                        src = img.get('src')
                        if src: material_data['material']['images'].append(src)
                        
                    material_data['material']['content'] = clean_element(mat_el)
                
                # Extract Sub-questions
                # In the DOM, they are usually in the right pane or inside the .ti usually
                sub_ti_containers = ti.find_all(class_='ti-container')
                for sub_sq in sub_ti_containers:
                    q_item = parse_single_question(sub_sq)
                    if q_item:
                        q_item['id'] = global_question_index
                        global_question_index += 1
                        material_data['questions'].append(q_item)
                
                formatted_items.append(material_data)
                
            else:
                # Regular Question
                sq = ti.find(class_='ti-container')
                if sq:
                    q_item = parse_single_question(sq)
                    if q_item:
                         q_item['id'] = global_question_index
                         global_question_index += 1
                         formatted_items.append({
                             "type": "regular",
                             "question": q_item
                         })
        
        # Validate extraction (check if we found analysis)
        valid = False
        count = 0
        for item in formatted_items:
            if item['type'] == 'regular':
                count += 1
                if item['question'].get('analysis'): valid = True
            else:
                for q in item['questions']:
                    count += 1
                    if q.get('analysis'): valid = True
                    
        if count > 0 and valid:
            print(f"    Successfully extracted {len(formatted_items)} groups/items (Total {count} questions). Verified analysis present.")
            return formatted_items
        
        print(f"    Attempt {attempt+1}/{max_retries}: Analysis seems incomplete or extraction failed. Waiting...")
        await asyncio.sleep(random.uniform(2, 4))

    return []

def parse_single_question(container):
    """Parses a single .ti-container into a dictionary."""
    if not container: return None
    
    qData = {
        'stem': '',
        'options': [],
        'correct_answer': '',
        'analysis': '',
        'keypoints': [],
        'source': '',
        'images': []
    }
    
    # 1. Stem
    # Try finding simple text container or specific choice container
    stem_el = container.find('app-format-html')
    if not stem_el:
        stem_el = container.find(class_='ti-content')
        
    if stem_el:
        qData['stem'] = clean_element(stem_el)
        for img in stem_el.find_all('img'):
             if img.get('src'): qData['images'].append(img.get('src'))

    # 2. Options
    # Selectors: .choice-radio-label, .choice-checkbox-label
    options = container.find_all(class_=['choice-radio-label', 'choice-checkbox-label'])
    for opt in options:
        qData['options'].append(clean_element(opt))
        for img in opt.find_all('img'):
             if img.get('src'): qData['images'].append(img.get('src'))
             
    # 3. Correct Answer
    # Helper to find correct answer
    correct_el = container.find(class_='correct-answer')
    if correct_el:
        qData['correct_answer'] = correct_el.get_text(strip=True)
    else:
        # Fallback: look for 'correctLost' icon
        correct_icon = container.find(class_='correctLost')
        if correct_icon:
            # Go up to the li
            parent = correct_icon.find_parent(class_='choice-radio')
            if parent:
                # The text is usually the first part
                qData['correct_answer'] = parent.get_text(strip=True).split('\n')[0]
    
    if not qData['correct_answer']:
         # Try overall items
         items = container.find_all(class_='overall-item')
         for item in items:
             title = item.find(class_='overall-item-title')
             if title and '正确答案' in title.get_text():
                 val = item.find(class_='overall-item-value')
                 if val: qData['correct_answer'] = val.get_text(strip=True)

    # 4. Analysis & Source & Keypoints
    # These are usually in .solution-title-container or similar blocks
    # Logic: Find the Title, then the content is the next logical element
    
    # We iterate all solution titles to find headers
    titles = container.find_all(class_='solution-title-container')
    for tc in titles:
        header_text = tc.get_text(strip=True)
        
        # Find content element
        content_el = None
        # Usually checking parent's next sibling or direct structure
        # Structure often: <app-solution-title>...<div class="solution-content">
        
        # Strategy: Go up to app-solution-title (host), then next sibling
        host = tc.find_parent('app-solution-title')
        if host:
            content_el = host.find_next_sibling()
        else:
            # Sometimes direct sibling of parent
            parent = tc.parent
            if parent: content_el = parent.find_next_sibling()
            
        if not content_el: continue
        
        if '解析' in header_text:
            qData['analysis'] = clean_element(content_el)
            for img in content_el.find_all('img'):
                 if img.get('src'): qData['images'].append(img.get('src'))
                 
        elif '来源' in header_text:
            qData['source'] = content_el.get_text(strip=True)
            
        elif '考点' in header_text:
            kps = content_el.find_all(class_='solution-keypoint-item')
            if kps:
                qData['keypoints'] = [k.get_text(strip=True) for k in kps]
            else:
                 qData['keypoints'] = [content_el.get_text(strip=True)]
                 
    return qData

async def download_images_for_questions(questions, save_dir, request_page):
    """Downloads images for questions and updates their paths."""
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
        
    print(f"    Downloading images to {save_dir}...")
    
    # ... (Download logic remains similar, see link_map build) ...
    
    all_unique_urls = set()
    for item in questions:
        # Flatten for processing if nested
        to_process = []
        if item.get('type') == 'material':
            to_process.extend(item['questions'])
            all_unique_urls.update(item['material']['images'])
        else:
            to_process.append(item['question'])
            
        for q in to_process:
            all_unique_urls.update(q.get('images', []))
        
    link_map = {} 

    for url in all_unique_urls:
        if not url: continue
        
        # Handle protocol relative
        if url.startswith('//'):
            url = 'https:' + url
        
        # Normalize original_url to be the https version for the key
        original_url = url
            
        if not url.startswith('http'): 
            continue
            
        try:
            # Generate filename hash
            ext = 'png'
            if '.' in url.split('?')[0]:
                potential_ext = url.split('?')[0].split('.')[-1]
                if len(potential_ext) <= 4 and '/' not in potential_ext:
                    ext = potential_ext
            
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
            filename = f"{url_hash}.{ext}"
            filepath = os.path.join(save_dir, filename)
            
            if not os.path.exists(filepath):
                # Download if not exists
                if request_page:
                    try:
                        response = await request_page.request.get(url)
                        if response.status == 200:
                            data = await response.body()
                            with open(filepath, 'wb') as f:
                                f.write(data)
                        else:
                            print(f"    [Warning] Image download failed (Status {response.status}): {url}")
                            continue # Skip adding to link_map if failed

                        # Add small random delay between image downloads
                        await asyncio.sleep(random.uniform(0.1, 0.4))
                    except Exception as e:
                        print(f"    [Error] Image download exception for {url}: {e}")
                        continue
            
            # Final check: does file exist? (Either previous or just downloaded)
            if os.path.exists(filepath):
                relative_path = f"images/{os.path.basename(save_dir)}/{filename}"
                link_map[original_url] = relative_path
            else:
                print(f"    [Warning] File still missing after download attempt: {filepath}")

        except Exception as e:
            print(f"    Failed to download image {url}: {e}")

    # Replace Links in Content
    print("    Replacing image links...")
    
    def update_links_in_text(text):
        if not text: return text
        for url, local_path in link_map.items():
            # url is https://...
            if url in text:
                text = text.replace(url, local_path)
            
            # Also replace protocol relative version //...
            if url.startswith('https:'):
                 relative_url = url[6:] # remove 'https:' keep '//'
                 if relative_url in text:
                     text = text.replace(relative_url, local_path)
        return text

    # Helper to look up local path
    def get_local_path(img_url):
        if not img_url: return img_url
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        return link_map.get(img_url, img_url)

    for item in questions:
        if item.get('type') == 'material':
            item['material']['content'] = update_links_in_text(item['material']['content'])
            # Update material images list
            item['material']['images'] = [get_local_path(u) for u in item['material'].get('images', [])]

            for q in item['questions']:
                q['stem'] = update_links_in_text(q.get('stem'))
                q['analysis'] = update_links_in_text(q.get('analysis'))
                # Unify images into a list of objects {'source': url, 'path': local_path}
                new_images = []
                for img_url in q.get('images', []):
                    # Ensure we look up the normalized https url
                    lookup_url = 'https:' + img_url if img_url.startswith('//') else img_url
                    local = link_map.get(lookup_url, img_url)
                    new_images.append({'source': lookup_url, 'path': local})
                q['images'] = new_images
                # Remove redundant local_images map if it exists or simply don't add it
                if 'local_images' in q: del q['local_images']
        else:
            q = item['question']
            q['stem'] = update_links_in_text(q.get('stem'))
            q['analysis'] = update_links_in_text(q.get('analysis'))
            # Unify images into a list of objects {'source': url, 'path': local_path}
            new_images = []
            for img_url in q.get('images', []):
                lookup_url = 'https:' + img_url if img_url.startswith('//') else img_url
                local = link_map.get(lookup_url, img_url)
                new_images.append({'source': lookup_url, 'path': local})
            q['images'] = new_images
            if 'local_images' in q: del q['local_images']

async def process_filter_task(context, filter_name, semaphore, nav_lock):
    """
    Worker task to process a single filter category in a separate page.
    """
    async with semaphore:
        print(f"[{filter_name}] Starting processing...")
        page = await context.new_page()
        
        try:
            # Navigate to base URL first
            await page.goto(URL)
            await page.wait_for_load_state("networkidle")
            
            # Reset to list with specific filter
            await reset_to_list(page, filter_name)

            try:
                await page.wait_for_selector("div.paper-item", timeout=10000)
            except:
                print(f"[{filter_name}] No papers found or timeout.")
                return

            # Note: We need to re-query papers in a loop because we navigate away.
            # First, check count.
            papers = await page.query_selector_all("div.paper-item")
            count = len(papers)
            print(f"[{filter_name}] Found {count} papers.")
            
            for j in range(count):
                try:
                    # Reset/Re-verify list state
                    # We might have just come back from an exam, so ensuring we are on list is good.
                    try:
                        await page.wait_for_selector("div.paper-item", timeout=10000)
                    except:
                        # Try resetting if lost
                         await reset_to_list(page, filter_name)
                         await page.wait_for_selector("div.paper-item", timeout=10000)

                    current_papers = await page.query_selector_all("div.paper-item")
                    
                    if j >= len(current_papers):
                        print(f"[{filter_name}] Index {j} out of range (list changed?). Stopping.")
                        break
                    
                    paper_item = current_papers[j]
                    
                    try:
                        title_el = await paper_item.query_selector("div.item-info-title")
                        title = await title_el.inner_text() if title_el else f"Paper_{j}"
                    except:
                        title = f"Paper_{j}"
                    
                    print(f"[{filter_name}] Processing paper {j+1}/{count}: {title}")
                    
                    # ENTER CRITICAL SECTION for Navigation
                    async with nav_lock:
                         # Random wait before entering paper
                        await random_wait(page, 1000, 2500)
                        # Click to enter exam
                        # We re-query the item right before clicking to catch stale handles if possible, 
                        # though logic above tries to keep it fresh.
                        if not await paper_item.is_visible():
                             # fetch again
                             current_papers = await page.query_selector_all("div.paper-item")
                             if j < len(current_papers):
                                 paper_item = current_papers[j]
                        
                        await paper_item.click()
                        
                        # Wait for the navigation to commit
                        try:
                           await page.wait_for_load_state("domcontentloaded", timeout=10000)
                        except:
                           pass # Proceed to check content

                    # Wait a moment for page to stabilize after lock release
                    await random_wait(page, 2000, 4000)
                    
                    is_analysis_page = False
                    
                    # Check for indicators: submit button means we are in exam mode
                    # Use a safely wrapped check
                    try:
                        submit_btn = await page.query_selector("div.submit-btn")
                        
                        if submit_btn:
                            print(f"    [{filter_name}] On exam page. Submitting blank paper...")
                            if await submit_btn.is_visible():
                                await random_wait(page, 500, 1500)
                                await submit_btn.click()
                                confirm_btn = await page.wait_for_selector("button.btn-submit", state="visible")
                                await random_wait(page, 500, 1000)
                                await confirm_btn.click()
                                
                                try:
                                    await page.wait_for_selector(".solution-title", timeout=30000)
                                    print(f"    [{filter_name}] Analysis page loaded.")
                                    is_analysis_page = True
                                except:
                                    print(f"    [{filter_name}] Timed out waiting for analysis elements.")
                                    if "solution" in page.url:
                                        is_analysis_page = True
                                    else:
                                        print(f"    [{filter_name}] Warning: Stuck on exam page.")
                                        is_analysis_page = False
                        else:
                            # Not exam page? Check if already analysis
                            if "solution" in page.url or await page.query_selector(".solution-title"):
                                 print(f"    [{filter_name}] Already on analysis page.")
                                 is_analysis_page = True
                            else:
                                print(f"    [{filter_name}] Unknown page state. Attempting to wait for analysis...")
                                try:
                                    await page.wait_for_selector(".solution-title", timeout=5000)
                                    is_analysis_page = True
                                except:
                                    print(f"    [{filter_name}] Could not confirm analysis page.")

                    except Exception as e:
                        print(f"    [{filter_name}] Error checking page state: {e}")
                        is_analysis_page = False

                    if is_analysis_page:
                        # Extra safety wait for angular to populate text
                        await random_wait(page, 2000, 4000)
                        data = await extract_exam_data(page)
                        
                        # Prepare Save Paths
                        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).strip()
                        json_filename = f"{filter_name}_{safe_title}.json"
                        save_path = os.path.join(os.getcwd(), "downloads", json_filename)
                        img_save_dir = os.path.join(os.getcwd(), "downloads", "images", safe_title)
                        
                        # Download Images & Replace Links - use current page request context
                        await download_images_for_questions(data, img_save_dir, page)

                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        
                        with open(save_path, 'w', encoding='utf-8') as f:
                            json.dump({
                                "title": title,
                                "filter": filter_name,
                                "items": data
                            }, f, ensure_ascii=False, indent=2)
                            
                        print(f"    [{filter_name}] Extracted {len(data)} questions. Saved to {save_path}")
                    else:
                        print(f"    [{filter_name}] Could not reach analysis page.")

                except Exception as e:
                    print(f"    [{filter_name}] Error processing paper {j+1}: {e}")
                
                finally:
                    # Always go back to list
                    # Use a small delay before navigating back to avoid race conditions with other tabs starting
                    await asyncio.sleep(1)
                    await reset_to_list(page, filter_name)
                    await random_wait(page, 2000, 5000)

        except Exception as e:
            logger.error(f"Error in filter task {filter_name}: {e}")
        finally:
            await page.close()
            logger.info(f"[{filter_name}] Task finished.")


async def main():
    user_data_dir = os.path.join(os.getcwd(), "user_data")
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir)

    async with async_playwright() as p:

        try:
            logger.info(f"Launching browser with user data dir: {user_data_dir}")
            # Use launch_persistent_context to keep login session
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                channel="chrome", # Try to use installed chrome if available
                headless=False,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
                no_viewport=True
            )
            
            # Anti-detection script
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Setup initial page to get filters
            if context.pages:
                page = context.pages[0]
            else:
                page = await context.new_page()
            
            # Try to navigate with retry
            for attempt in range(3):
                try:
                    # Use domcontentloaded which is faster and sufficient for SPAs
                    if URL not in page.url:
                        await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
                    else:
                        await page.reload(timeout=60000, wait_until="domcontentloaded")
                    break 
                except Exception as e_nav:
                    print(f"    Attempt {attempt+1}/3 failed to load/reload: {e_nav}")
                    # If we timed out but the URL is correct-ish, maybe we can proceed
                    if "Timeout" in str(e_nav) and "fenbi.com" in page.url:
                        logger.info("    Timeout occurred but URL seems correct. Attempting to proceed...")
                        break
                    
                    if attempt == 2: raise e_nav
                    await asyncio.sleep(2) 

        except Exception as e:
            logger.error(f"Error launching browser: {e}")
            return

        logger.info("Please log in manually if required.")
        input("Press Enter in the terminal after you have logged in and are on the target page...")

        # Add random movement/check to warm up
        await random_wait(page, 1000, 3000)

        try:
            await page.wait_for_selector("span.categories-item", timeout=30000)
        except:
             logger.warning("Could not find filters. Please ensure you are on the correct page.")
             logger.warning(f"Current URL: {page.url}")
             content = await page.evaluate("document.body.innerText")
             logger.warning(f"Page Content Snippet: {content[:200]}")
             return

        filters = await page.query_selector_all("span.categories-item")
        
        filter_names = []
        for f in filters:
            text = await f.inner_text()
            if "推荐" in text:
                logger.info(f"Skipping filter: {text}")
                continue
            filter_names.append(text)
            
        logger.info(f"Found filters: {filter_names}")

        # Limit concurrency to 3
        sem = asyncio.Semaphore(3)
        # Lock for critical navigation sections (entering exams)
        nav_lock = asyncio.Lock()
        
        tasks = []
        
        print("Starting parallel execution...")
        for filter_name in filter_names:
            tasks.append(asyncio.create_task(process_filter_task(context, filter_name, sem, nav_lock)))

        if tasks:
            await asyncio.gather(*tasks)

        print("All done!")
        await context.close()


