import asyncio
from typing import Dict, Any, List, Optional, Union, Tuple
from bs4 import BeautifulSoup
import aiohttp
from bot.monitoring import WebsiteMonitor
from bot.utils import parse_website_content, fetch_url_content
from bot.config import debug_print

class SpecialSiteMonitor(WebsiteMonitor):
    def __init__(self, site_id: str, config: Dict[str, Any]):
        super().__init__(site_id, config)
        self.type = "multiple"  # This monitor always returns multiple numbers
        self.countries = {}  # Store country-specific numbers

    def normalize_number(self, raw: str) -> str:
        """Normalize phone number format"""
        # Remove everything except digits
        digits = ''.join(filter(str.isdigit, raw))
        # Ensure starts with '+'
        return f"+{digits}"

    async def fetch_country_numbers(self, base_url: str, country_url: str) -> List[str]:
        """Fetch numbers for a specific country"""
        try:
            full_url = f"{base_url}{country_url}"
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url) as response:
                    if response.status != 200:
                        debug_print(f"[ERROR] Failed to fetch {full_url}: {response.status}")
                        return []
                    
                    text = await response.text()
                    soup = BeautifulSoup(text, 'html.parser')
                    
                    # Find all number elements
                    number_elements = soup.select('.fw-items .scroll a.fw-li:not(.--archive)')
                    numbers = []
                    
                    for element in number_elements:
                        # Get the number from the second div with data-v-93cad54f
                        number_div = element.select('div[data-v-93cad54f]')[1]
                        if number_div:
                            number = number_div.text.strip()
                            if number:
                                numbers.append(self.normalize_number(number))
                    
                    return numbers
        except Exception as e:
            debug_print(f"[ERROR] Error fetching country numbers: {e}")
            return []

    async def check_for_updates(self) -> Tuple[Optional[List[str]], Optional[str]]:
        """Check for updates in country numbers"""
        if not self.enabled or not self.url:
            return None, None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url) as response:
                    if response.status != 200:
                        debug_print(f"[ERROR] Failed to fetch main page: {response.status}")
                        return None, None

                    text = await response.text()
                    soup = BeautifulSoup(text, 'html.parser')
                    
                    # Get base URL
                    base_url = self.url.split('/')[0] + '//' + self.url.split('/')[2]
                    
                    # Find all country links
                    country_links = soup.select('.countries .scroll a.fw-li:not(.--archive)')
                    all_numbers = []
                    
                    for link in country_links:
                        country_name = None
                        country_divs = link.select('div[data-v-93cad54f]')
                        if len(country_divs) > 1:
                            country_name = country_divs[1].text.strip()
                        
                        if country_name:
                            country_url = link.get('href')
                            if country_url:
                                numbers = await self.fetch_country_numbers(base_url, country_url)
                                if numbers:
                                    self.countries[country_name] = numbers
                                    all_numbers.extend(numbers)
                    
                    # Return all numbers found and None for flag_url (handled by notification system)
                    return all_numbers, None

        except Exception as e:
            debug_print(f"[ERROR] Error in check_for_updates: {e}")
            return None, None

    def get_notification_data(self) -> Dict[str, Any]:
        """Get data needed for notification"""
        return {
            "is_initial_run": self.is_initial_run,
            "numbers": self.latest_numbers,
            "flag_url": self.flag_url,
            "site_id": self.site_id,
            "url": self.url,
            "countries": self.countries  # Include country-specific data
        } 