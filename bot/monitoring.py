import asyncio
from typing import Dict, Any, List, Optional, Union, Tuple
from bot.storage import storage, save_website_data, load_website_data
from bot.utils import parse_website_content, fetch_url_content
from bot.config import CHECK_INTERVAL, debug_print, DEV_MODE
from bot.special_site import SpecialSiteMonitor

class WebsiteMonitor:
    def __init__(self, site_id: str, config: Dict[str, Any]):
        self.site_id = site_id
        self.url = config["url"]
        self.type = config.get("type")
        self.enabled = config["enabled"]
        self.is_initial_run = True
        self.position = config.get("position", 1)  # Position determines UI layout
        self.latest_numbers = []
        self.last_number = None
        self.flag_url = None

    async def fetch_content(self) -> Optional[str]:
        """Fetch content from the website"""
        return await fetch_url_content(self.url)

    async def check_for_updates(self) -> Tuple[Optional[Union[int, List[str]]], Optional[str]]:
        """Check for updates based on website type"""
        if not self.enabled or not self.url:
            return None, None

        # Use the unified parsing function
        return await parse_website_content(self.url, self.type)

    async def process_update(self, new_data: Union[int, List[str]], flag_url: Optional[str]) -> bool:
        """Process updates and return True if notification should be sent"""
        if not new_data:
            # Website temporarily unavailable, don't disrupt monitoring
            debug_print(f"[DEBUG] No data from {self.site_id}, skipping this check")
            return False

        # Dynamic type detection
        if self.type is None:
            if isinstance(new_data, list) and len(new_data) > 1:
                self.type = "multiple"
            elif (isinstance(new_data, list) and len(new_data) == 1) or isinstance(new_data, str):
                self.type = "single"
            else:
                self.type = "single"  # Fallback for empty or unknown
            # print(f"[DEBUG] WebsiteMonitor - dynamically set type for {self.site_id}: {self.type}")

        if self.type == "single":
            new_number = new_data
            # Remove leading + if present
            if isinstance(new_number, str) and new_number.startswith('+'):
                new_number = new_number[1:]
            # Convert to int if possible
            try:
                new_number_int = int(new_number)
                new_number = new_number_int
            except (ValueError, TypeError):
                pass
            # First time initialization or number has changed
            if self.last_number is None:
                # First run - save number and notify
                self.last_number = new_number
                self.flag_url = flag_url
                await save_website_data(self.site_id)
                return True  # Send notification on first run
            elif new_number != self.last_number:
                # Number has changed - update and notify
                self.last_number = new_number
                self.flag_url = flag_url
                await save_website_data(self.site_id)
                return True
            return False
        else:
            # For multiple numbers website
            if not self.latest_numbers:
                # First run - 1. Get all numbers from website
                if new_data:
                    # 2. Pick the first (0th index) element to be the last_number for comparison
                    first_num = new_data[0]
                    if isinstance(first_num, str) and first_num.startswith("+"):
                        first_num = first_num[1:]
                    try:
                        self.last_number = int(first_num)
                        self.flag_url = flag_url
                        # Save all numbers but mark as initial notification
                        self.latest_numbers = new_data.copy()
                        await save_website_data(self.site_id)
                        # 3. Return True to send initial notification with last_number
                        return True
                    except (ValueError, TypeError):
                        self.last_number = None
                        return False

            elif new_data and new_data != self.latest_numbers:
                # Numbers have changed - check if last_number has moved from 0th position
                if new_data and self.last_number is not None:
                    # Current last_number (as string with + prefix for comparison)
                    last_number_str = f"+{self.last_number}"
                    # 4. Find the position of the last_number in the new array
                    last_number_position = -1
                    for i, num in enumerate(new_data):
                        if num == last_number_str:
                            last_number_position = i
                            break

                    # 5. If last_number found and moved from position 0
                    if last_number_position > 0:
                        # Create array of numbers that come before last_number
                        new_numbers = new_data[:last_number_position]
                        # Pick the newest number (0th index) as the new last_number
                        first_num = new_data[0]
                        if isinstance(first_num, str) and first_num.startswith("+"):
                            first_num = first_num[1:]
                        try:
                            self.last_number = int(first_num)
                        except (ValueError, TypeError):
                            pass
                    # If last_number not found or already at position 0
                    else:
                        # Update last_number to the new first element
                        first_num = new_data[0]
                        if isinstance(first_num, str) and first_num.startswith("+"):
                            first_num = first_num[1:]
                        try:
                            self.last_number = int(first_num)
                        except (ValueError, TypeError):
                            pass

                    # 6. Update latest_numbers with full array
                    self.latest_numbers = new_data
                    self.flag_url = flag_url
                    await save_website_data(self.site_id)
                    # 7. Send notification with latest_numbers array
                    return True

        return False

    def get_notification_data(self) -> Dict[str, Any]:
        """Get data needed for notification"""
        if self.type == "single":
            return {
                "is_initial_run": self.is_initial_run,
                "number": self.last_number,
                "flag_url": self.flag_url,
                "site_id": self.site_id,
                "url": self.url
            }
        else:
            return {
                "is_initial_run": self.is_initial_run,
                "numbers": self.latest_numbers,
                "flag_url": self.flag_url,
                "site_id": self.site_id,
                "url": self.url
            }

async def monitor_websites(bot, send_notification_func):
    """Monitor all configured websites for updates"""
    # Load saved data for all websites
    await load_website_data()

    consecutive_failures = {site_id: 0 for site_id in storage["websites"]}
    max_consecutive_failures = 5

    # First run check - if any website has no saved data, initialize it
    initial_run_needed = False
    for site_id, website in storage["websites"].items():
        # Only set is_initial_run to True if the website hasn't been initialized yet
        if website.enabled and website.type == "single" and website.last_number is None:
            website.is_initial_run = True
            initial_run_needed = True
        elif website.enabled and website.type == "multiple" and not website.latest_numbers:
            website.is_initial_run = True
            initial_run_needed = True

    # For first run, initialize all websites
    if initial_run_needed:
        for site_id, website in storage["websites"].items():
            if not website.enabled:
                continue

            try:
                # Get initial data
                new_data, flag_url = await website.check_for_updates()
                if new_data:
                    # Save data and send notification for all websites on first run
                    await website.process_update(new_data, flag_url)
                    # Send notification for all websites
                    await send_notification_func(website.get_notification_data())
                    # Reset consecutive failures on success
                    consecutive_failures[site_id] = 0
            except Exception as e:
                print(f"Error initializing {site_id}: {e}")
                # Don't increase failure count on first run

    # For normal operation, start monitoring loop
    while True:
        try:
            for site_id, website in storage["websites"].items():
                if not website.enabled:
                    # Skip disabled websites
                    continue

                try:
                    # Check for updates
                    new_data, flag_url = await website.check_for_updates()

                    if new_data:
                        # Process update and send notification
                        notify = await website.process_update(new_data, flag_url)

                        if notify:
                            notification_data = website.get_notification_data()
                            await send_notification_func(notification_data)
                        
                        # Reset consecutive failures on any successful response
                        consecutive_failures[site_id] = 0
                    else:
                        consecutive_failures[site_id] += 1                        
                        # Only log errors at specific thresholds to avoid spam
                        # if consecutive_failures[site_id] == 1 or consecutive_failures[site_id] % 5 == 0:
                        #     debug_print(f"⚠️ No data from {site_id} (attempt {consecutive_failures[site_id]}/{max_consecutive_failures})")
                except Exception as e:
                    consecutive_failures[site_id] += 1
                    print(f"Error monitoring {site_id} (attempt {consecutive_failures[site_id]}): {e}")
                    
                # Short pause between websites to prevent overwhelming the network
                await asyncio.sleep(1)

            # Wait for CHECK_INTERVAL seconds before checking again
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"[ERROR] Error in monitor_websites main loop: {e}")
            # Continue monitoring even if there's an error in the main loop
            await asyncio.sleep(5)
