import os, asyncio
from aiogram import Dispatcher, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from bot.config import CHAT_ID, ENABLE_REPEAT_NOTIFICATION, DEFAULT_REPEAT_INTERVAL, debug_print, DEV_MODE, SINGLE_MODE
from bot.notifications import update_message_with_countdown, create_keyboard
from bot.storage import storage, save_website_data, save_last_number
from bot.utils import format_time, delete_message_after_delay, get_base_url, extract_website_name, remove_country_code, get_selected_numbers_for_buttons, parse_callback_data, KeyboardData

def register_handlers(dp: Dispatcher):
    """Register all handlers with the dispatcher"""
    # Button callbacks
    dp.callback_query.register(copy_number,
                               lambda c: c.data.startswith("copy_"))
    dp.callback_query.register(
        update_number, lambda c: c.data.startswith("update_") and not c.data.
        startswith("update_multi_"))
    dp.callback_query.register(update_multi_numbers,
                               lambda c: c.data.startswith("update_multi_"))
    dp.callback_query.register(
        handle_settings, lambda c: c.data.startswith("settings_") and not c.
        data.startswith("settings_monitoring_"))
    dp.callback_query.register(
        handle_monitoring_settings,
        lambda c: c.data.startswith("settings_monitoring_"))
    dp.callback_query.register(toggle_site_monitoring,
                               lambda c: c.data.startswith("toggle_monitoring_"))
    dp.callback_query.register(toggle_repeat_notification,
                               lambda c: c.data.startswith("toggle_repeat_"))
    dp.callback_query.register(toggle_single_mode,
                               lambda c: c.data.startswith("toggle_single_mode_"))
    dp.callback_query.register(back_to_main,
                               lambda c: c.data.startswith("back_to_main_"))
    dp.callback_query.register(
        split_number,
        lambda c: c.data.startswith("split_") or c.data.startswith("number_"))

    # Commands
    dp.message.register(send_ping_reply, Command("ping"))
    dp.message.register(set_repeat_interval, Command("set_repeat"))
    dp.message.register(stop_repeat_notification, Command("stop_repeat"))


def is_number_updated(keyboard):
    """Helper function to check if a number is updated in the keyboard"""
    if not keyboard or not keyboard.inline_keyboard:
        return False
        
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.text == "✅ Updated Number":
                return True
    return False


async def copy_number(callback_query: CallbackQuery):
    try:
        debug_print("[INFO] copy_number - function started")
        # Extract data from callback query
        parts, site_id = parse_callback_data(callback_query.data)
        debug_print(f"[DEBUG] copy_number - callback_data: {callback_query.data}, parts: {parts}, site_id: {site_id}")

        if len(parts) != 2 or not site_id:  # copy_number
            debug_print(f"[ERROR] copy_number - invalid format, parts: {parts}, site_id: {site_id}")
            await callback_query.answer("Error copying number: invalid format")
            return

        number = parts[1]
        debug_print(f"[DEBUG] copy_number - extracted number: {number}, site_id: {site_id}")

        # Get website object
        website = storage["websites"].get(site_id)
        if not website:
            await callback_query.answer("Website not found")
            return

        # Check if the number was previously updated for this specific message
        is_updated = is_number_updated(callback_query.message.reply_markup)

        # Animation Step 1 (0-2 seconds)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Copied", callback_data="none")
        ]])
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await asyncio.sleep(2)

        # Animation Step 2 (2-4 seconds)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Copied", callback_data="none"),
             InlineKeyboardButton(text="✅ Updated Number" if is_updated else "🔄 Update Number", 
                                callback_data=f"update_{number}_{site_id}")],
            [InlineKeyboardButton(text="🔢 Split Number", callback_data=f"split_{number}_{site_id}"),
             InlineKeyboardButton(text="⚙️ Settings", callback_data=f"settings_{site_id}")],
            [InlineKeyboardButton(text="🌐 Visit Webpage", url=website.url)]
        ])
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await asyncio.sleep(2)

        # Final State (after 4 seconds)
        keyboard_data = KeyboardData(
            site_id=site_id,
            type=website.type,
            url=website.url,
            updated=is_updated,
            is_initial_run=website.is_initial_run,
            numbers=[number],
            single_mode=SINGLE_MODE
        )

        # Create the final keyboard using the unified function
        final_keyboard = create_keyboard(keyboard_data, website)
        
        # Update the message with the final keyboard
        await callback_query.message.edit_reply_markup(reply_markup=final_keyboard)
        await callback_query.answer("Number copied!")

    except Exception as e:
        debug_print(f"[ERROR] copy_number - error in function: {e}")
        await callback_query.answer("Error copying number")


async def update_number(callback_query: CallbackQuery, bot: Bot):
    """Handle single number update"""
    try:
        # Extract number and site_id from callback data
        parts, site_id = parse_callback_data(callback_query.data)
        debug_print(f"[UPDATE_BUTTON] Callback data: {callback_query.data}")
        debug_print(f"[UPDATE_BUTTON] Parsed parts: {parts}")
        debug_print(f"[UPDATE_BUTTON] Site ID: {site_id}")
        
        if len(parts) != 2 or not site_id:  # update_number
            debug_print(f"[ERROR] update_number - invalid format, parts: {parts}, site_id: {site_id}")
            await callback_query.answer("Invalid format")
            return
            
        number = parts[1]
        debug_print(f"[DEBUG] update_number - number: {number}, site_id: {site_id}")

        # Get website object
        website = storage["websites"].get(site_id)
        if not website:
            debug_print(f"[UPDATE_BUTTON] Website not found for site_id: {site_id}")
            await callback_query.answer("Website not found")
            return

        debug_print(f"[UPDATE_BUTTON] Website type: {website.type}")
        debug_print(f"[UPDATE_BUTTON] Current button state: {callback_query.message.reply_markup}")

        # Animation Step 1 (0-2 seconds)
        debug_print("[UPDATE_BUTTON] Starting animation step 1")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Updating to:", callback_data="none")
        ]])
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await asyncio.sleep(2)

        # Animation Step 2 (2-4 seconds)
        debug_print("[UPDATE_BUTTON] Starting animation step 2")
        if website.type == "multiple":
            # For multiple type, show the last_number from storage
            last_number = website.last_number
            debug_print(f"[UPDATE_BUTTON] Multiple type - showing last_number: {last_number}")
            updated_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=f"+{last_number}", callback_data="none")
            ]])
        else:
            # For single type, show the current number
            debug_print(f"[UPDATE_BUTTON] Single type - showing current number: {number}")
            updated_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=f"+{number}", callback_data="none")
            ]])
        await callback_query.message.edit_reply_markup(reply_markup=updated_keyboard)
        await asyncio.sleep(2)

        # Final State (after 4 seconds)
        debug_print("[UPDATE_BUTTON] Creating final keyboard state")
        # Create data structure for keyboard based on website type
        keyboard_data = {
            "site_id": site_id,
            "type": website.type,
            "updated": True,  # Set to True since we're updating
            "is_initial_run": website.is_initial_run,
            "url": website.url
        }
        debug_print(f"[UPDATE_BUTTON] Keyboard data: {keyboard_data}")

        # Add number-specific data based on website type
        if website.type == "single":
            keyboard_data["number"] = number
            debug_print(f"[UPDATE_BUTTON] Single type - added number to keyboard data: {number}")
        else:
            # For multiple type, use the selected numbers for buttons
            if website.is_initial_run:
                # For initial run, just use the last_number
                keyboard_data["numbers"] = [website.last_number]
                debug_print(f"[UPDATE_BUTTON] Multiple type (initial run) - using last_number: {website.last_number}")
            else:
                # For subsequent runs, use the selected numbers
                selected_numbers = get_selected_numbers_for_buttons(website.latest_numbers, website.last_number)
                keyboard_data["numbers"] = selected_numbers
                debug_print(f"[UPDATE_BUTTON] Multiple type (subsequent run) - selected numbers: {selected_numbers}")
            keyboard_data["is_initial_run"] = website.is_initial_run

        # Create the final keyboard using the unified function
        final_keyboard = create_keyboard(keyboard_data, website)
        debug_print(f"[UPDATE_BUTTON] Final keyboard created: {final_keyboard}")
        
        # Update the message with the final keyboard
        await callback_query.message.edit_reply_markup(reply_markup=final_keyboard)
        debug_print("[UPDATE_BUTTON] Message updated with final keyboard")

        # Get the latest notification data
        latest = storage.get("latest_notification", {})
        debug_print(f"[UPDATE_BUTTON] Latest notification data: {latest}")
        
        if latest and site_id:
            if website and SINGLE_MODE and website.type == "multiple":
                debug_print("[UPDATE_BUTTON] Processing in SINGLE_MODE for multiple type website")
                # In SINGLE_MODE, stop repeat notifications for all messages from this site
                numbers = latest.get("numbers", [])
                debug_print(f"[UPDATE_BUTTON] Numbers from latest notification: {numbers}")
                
                if numbers:
                    # Only cancel countdown task for this specific site
                    if site_id in storage["active_countdown_tasks"]:
                        debug_print(f"[UPDATE_BUTTON] Cancelling countdown task for site_id: {site_id}")
                        storage["active_countdown_tasks"][site_id].cancel()
                        del storage["active_countdown_tasks"][site_id]

                    # Remove countdown from all messages but keep their original button states
                    for num in numbers:
                        try:
                            message_text = callback_query.message.caption
                            debug_print(f"[UPDATE_BUTTON] Processing message for number: {num}")
                            debug_print(f"[UPDATE_BUTTON] Current message text: {message_text}")
                            
                            if message_text and "⏱ Next notification in:" in message_text:
                                new_message = message_text.split("\n\n⏱")[0]
                                debug_print(f"[UPDATE_BUTTON] New message after removing countdown: {new_message}")
                                
                                # Only update the clicked message's button state
                                if num == number:
                                    debug_print("[UPDATE_BUTTON] Updating clicked message's button state")
                                    await callback_query.message.edit_caption(
                                        caption=new_message,
                                        parse_mode="Markdown",
                                        reply_markup=final_keyboard
                                    )
                                else:
                                    # Create keyboard data for other numbers
                                    debug_print(f"[UPDATE_BUTTON] Creating keyboard for other number: {num}")
                                    other_keyboard_data = {
                                        "site_id": site_id,
                                        "type": website.type,
                                        "updated": False,  # Keep original state
                                        "is_initial_run": website.is_initial_run,
                                        "url": website.url,
                                        "numbers": [num]
                                    }
                                    other_keyboard = create_keyboard(other_keyboard_data, website)
                                    await callback_query.message.edit_caption(
                                        caption=new_message,
                                        parse_mode="Markdown",
                                        reply_markup=other_keyboard
                                    )
                        except Exception as e:
                            debug_print(f"[ERROR] Error removing countdown for number {num}: {e}")
            else:
                # For single notification or non-SINGLE_MODE
                debug_print("[UPDATE_BUTTON] Processing single notification or non-SINGLE_MODE")
                if site_id in storage["active_countdown_tasks"]:
                    debug_print(f"[UPDATE_BUTTON] Cancelling countdown task for site_id: {site_id}")
                    storage["active_countdown_tasks"][site_id].cancel()
                    del storage["active_countdown_tasks"][site_id]

                # Remove countdown from message if present
                try:
                    message_text = callback_query.message.caption
                    debug_print(f"[UPDATE_BUTTON] Current message text: {message_text}")
                    
                    if message_text and "⏱ Next notification in:" in message_text:
                        new_message = message_text.split("\n\n⏱")[0]
                        debug_print(f"[UPDATE_BUTTON] New message after removing countdown: {new_message}")
                        await callback_query.message.edit_caption(
                            caption=new_message,
                            parse_mode="Markdown",
                            reply_markup=final_keyboard
                        )
                except Exception as e:
                    debug_print(f"[ERROR] Error removing countdown: {e}")

        await callback_query.answer("Number updated successfully!")
        debug_print("[UPDATE_BUTTON] Update process completed successfully")

    except Exception as e:
        debug_print(f"[ERROR] update_number - {e}")
        await callback_query.answer("Failed to update number")


async def update_multi_numbers(callback_query: CallbackQuery):
    """Handle multiple numbers update"""
    try:
        # Extract site_id from callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return

        # Get website object
        website = storage["websites"].get(site_id)
        if not website:
            await callback_query.answer("Website not found.")
            return

        # Show updating animation similar to single type
        try:
            has_countdown = False
            message_text = callback_query.message.caption
            if message_text and "⏱ Next notification in:" in message_text:
                has_countdown = True
                new_message = message_text.split("\n\n⏱")[0]

            # Show updating animation
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Updating to:", callback_data="none")
            ]])
            await callback_query.message.edit_reply_markup(reply_markup=keyboard)
            await asyncio.sleep(2)

            # If we have numbers to display in the animation, show the first one
            display_number = ""
            if website and hasattr(website, 'latest_numbers') and website.latest_numbers:
                display_number = website.latest_numbers[0]
            elif website and hasattr(website, 'last_number') and website.last_number:
                display_number = f"+{website.last_number}"

            if display_number:
                updated_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=f"{display_number}", callback_data="none")
                ]])
                await callback_query.message.edit_reply_markup(reply_markup=updated_keyboard)
                await asyncio.sleep(2)
        except Exception as e:
            debug_print(f"[ERROR] Error during animation: {e}")
            # Continue with the update even if animation fails

        # Create a unified data structure for the keyboard
        keyboard_data = {
            "site_id": site_id,
            "updated": True,  # Always set to True since we're updating
            "type": getattr(website, 'type', 'multiple'),
            "is_initial_run": website.is_initial_run,  # Maintain the current is_initial_run state
            "url": getattr(website, 'url', get_base_url() or "")
        }

        # Add numbers to keyboard data based on website state
        if website.is_initial_run:
            keyboard_data["numbers"] = [website.last_number]
        else:
            selected_numbers = get_selected_numbers_for_buttons(website.latest_numbers, website.last_number)
            keyboard_data["numbers"] = selected_numbers

        # Get the keyboard using the unified function
        keyboard = create_keyboard(keyboard_data, website)

        # Update the message with the new keyboard
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)

        # Update the button_updated state
        website.button_updated = True
        await save_website_data(site_id)

    except Exception as e:
        debug_print(f"[ERROR] Error in update_multi_numbers: {e}")
        # Show error message to user
        await callback_query.answer("Error updating numbers. Please try again.", show_alert=True)


async def handle_settings(callback_query: CallbackQuery):
    try:
        # Extract site_id from callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return

        debug_print(f"[DEBUG] Settings - extracted site_id: {site_id}")

        # Get website configuration
        website = storage["websites"].get(site_id)
        debug_print(f"[INFO] handle_settings - website found: {website is not None}")

        if not website:
            await callback_query.answer("Website not found.")
            return

        # Determine if repeat notification is enabled
        repeat_status = "Disable" if ENABLE_REPEAT_NOTIFICATION else "Enable"
        single_mode_status = "Disable" if SINGLE_MODE else "Enable"

        # Define base buttons that are common for all types
        base_buttons = [
            [InlineKeyboardButton(
                text=f"{repeat_status} Repeat Notification",
                callback_data=f"toggle_repeat_{site_id}")
            ],
            [InlineKeyboardButton(
                text="Stop Monitoring",
                callback_data=f"settings_monitoring_{site_id}")
            ],
            [InlineKeyboardButton(
                text="« Back",
                callback_data=f"back_to_main_{site_id}")
            ]
        ]

        # Add single mode button only for multiple type websites
        if website.type == "multiple":
            base_buttons.insert(1, [InlineKeyboardButton(
                text=f"Single Mode : {single_mode_status}",
                callback_data=f"toggle_single_mode_{site_id}")
            ])

        # Create settings keyboard
        settings_keyboard = InlineKeyboardMarkup(inline_keyboard=base_buttons)

        # Update message with settings menu
        await callback_query.message.edit_reply_markup(
            reply_markup=settings_keyboard)

    except Exception as e:
        debug_print(f"[ERROR] Error in handle_settings: {e}")


async def create_monitoring_keyboard(current_page: int, total_sites: int, all_sites: list, original_site_id: str = None) -> InlineKeyboardMarkup:
    """Create monitoring settings keyboard with pagination and site toggles"""
    # Constants for pagination
    SITES_PER_PAGE = 12
    SITES_PER_ROW = 2

    # Only use pagination if we have more than 14 sites
    use_pagination = total_sites > 14

    # Calculate total pages
    total_pages = (total_sites + SITES_PER_PAGE - 1) // SITES_PER_PAGE if use_pagination else 1

    # Calculate start and end indices for current page
    start_idx = current_page * SITES_PER_PAGE
    end_idx = min(start_idx + SITES_PER_PAGE, total_sites)

    # Get sites for current page
    current_page_sites = all_sites[start_idx:end_idx]

    debug_print(f"[DEBUG] create_monitoring_keyboard - displaying page {current_page+1}/{total_pages}, sites {start_idx+1}-{end_idx} of {total_sites}")

    # Create buttons for each website
    buttons = []
    current_row = []

    for site_id, site in current_page_sites:
        # Extract website name from URL
        site_name = extract_website_name(site.url, site.type)
        debug_print(f"[DEBUG] create_monitoring_keyboard - site_name: {site_name}, enabled: {site.enabled}")
        
        # Show "Disabled" text for disabled sites
        display_name = f"{site_name} : Disabled" if not site.enabled else site_name

        # Create callback data with consistent format
        if use_pagination:
            callback_data = f"toggle_monitoring_page_{current_page}_{site_id}"
        else:
            callback_data = f"toggle_monitoring_{site_id}"

        current_row.append(
            InlineKeyboardButton(
                text=display_name,
                callback_data=callback_data))

        if len(current_row) == SITES_PER_ROW:
            buttons.append(current_row)
            current_row = []

    # Add any remaining buttons if we have an odd number
    if current_row:
        buttons.append(current_row)

    # Add pagination navigation
    if use_pagination:
        nav_row = []

        if current_page > 0:
            nav_row.append(InlineKeyboardButton(
                text="« Back",
                callback_data=f"settings_monitoring_page_{current_page-1}"
            ))

        if current_page < total_pages - 1:
            if len(nav_row) == 0:
                nav_row.append(InlineKeyboardButton(
                    text="⤜ Next Page »",
                    callback_data=f"settings_monitoring_page_{current_page+1}"
                ))
            else:
                nav_row.append(InlineKeyboardButton(
                    text="⤜ Next Page »",
                    callback_data=f"settings_monitoring_page_{current_page+1}"
                ))

        if nav_row:
            buttons.append(nav_row)

    # Add back button
    buttons.append([
        InlineKeyboardButton(
            text="« Back to Settings",
            callback_data=f"settings_{original_site_id or site_id}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def handle_monitoring_settings(callback_query: CallbackQuery):
    try:
        # Extract the site_id from the callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if not site_id:
            await callback_query.answer("Invalid monitoring settings request")
            return

        debug_print(f"[INFO] Monitoring settings - site_id: {site_id}")

        # Get all websites
        all_sites = list(storage["websites"].items())
        total_sites = len(all_sites)

        if total_sites == 0:
            await callback_query.answer("No websites configured for monitoring")
            return

        # Calculate current page
        current_page = 0
        if "page" in callback_query.data:
            page_index = parts.index("page")
            if page_index + 1 < len(parts):
                try:
                    current_page = int(parts[page_index + 1])
                except ValueError:
                    current_page = 0

        # Create monitoring settings keyboard
        monitoring_keyboard = await create_monitoring_keyboard(current_page, total_sites, all_sites, site_id)

        # Update the message with new keyboard
        await callback_query.message.edit_reply_markup(reply_markup=monitoring_keyboard)

    except Exception as e:
        debug_print(f"[ERROR] Error in monitoring settings: {e}")
        print(f"[ERROR] Error in monitoring settings: {e}")


async def toggle_site_monitoring(callback_query: CallbackQuery):
    """Toggle monitoring for a specific site"""
    try:
        # Extract the site_id from the callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if not site_id:
            await callback_query.answer("Invalid toggle request")
            return

        debug_print(f"[INFO] Toggle site monitoring - site_id: {site_id}")

        # Toggle the site's enabled status
        if site_id in storage["websites"]:
            website = storage["websites"][site_id]
            website.enabled = not website.enabled

            # Log the monitoring status change
            status = "started" if website.enabled else "stopped"
            website_name = extract_website_name(website.url, website.type)
            print(f"Monitoring {status} for {website_name} Website")

            # Get all websites
            all_sites = list(storage["websites"].items())
            total_sites = len(all_sites)

            # Calculate current page
            current_page = 0
            if "page" in callback_query.data:
                page_index = parts.index("page")
                if page_index + 1 < len(parts):
                    try:
                        current_page = int(parts[page_index + 1])
                    except ValueError:
                        current_page = 0

            # Create monitoring settings keyboard
            monitoring_keyboard = await create_monitoring_keyboard(current_page, total_sites, all_sites, site_id)

            # Update the keyboard
            await callback_query.message.edit_reply_markup(reply_markup=monitoring_keyboard)

            # Save the updated website data
            await save_website_data(site_id)

            status = "enabled" if website.enabled else "disabled"
            await callback_query.answer(f"Monitoring {status} for {website_name} Website")
        else:
            await callback_query.answer(f"Error: Website {site_id} not found")
    except Exception as e:
        debug_print(f"[ERROR] Error in toggle_site_monitoring: {e}")
        await callback_query.answer("Error toggling site monitoring")


async def toggle_repeat_notification(callback_query: CallbackQuery):
    """Toggle repeat notification for a site"""
    try:
        site_id = parse_callback_data(callback_query.data)
        if site_id is None:
            await callback_query.answer("Invalid site ID")
            return

        global ENABLE_REPEAT_NOTIFICATION
        # Log previous state before toggling
        previous_state = ENABLE_REPEAT_NOTIFICATION

        # Toggle the state
        ENABLE_REPEAT_NOTIFICATION = not ENABLE_REPEAT_NOTIFICATION
        print(
            f"Repeat notification state: {'Enabled' if ENABLE_REPEAT_NOTIFICATION else 'Disabled'}"
        )

        # Update repeat interval if needed
        if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is None:
            storage["repeat_interval"] = DEFAULT_REPEAT_INTERVAL
            print(
                f"Repeat interval set to default: {DEFAULT_REPEAT_INTERVAL} seconds ({format_time(DEFAULT_REPEAT_INTERVAL)})"
            )

        # Log the current interval
        if not DEFAULT_REPEAT_INTERVAL:
            print(
                f"Current repeat interval: {storage['repeat_interval']} seconds"
            )

        # Return to settings menu to show updated state
        await handle_settings(callback_query)
        status = "enabled" if ENABLE_REPEAT_NOTIFICATION else "disabled"
        await callback_query.answer(f"Repeat notification {status}")

    except Exception as e:
        debug_print(f"[ERROR] Error in toggle_repeat_notification: {e}")
        await callback_query.answer("Failed to toggle repeat notification")


async def back_to_main(callback_query: CallbackQuery):
    try:
        # Extract site_id from callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return

        debug_print(f"[DEBUG] back_to_main - site_id: {site_id}")
        
        # Get website data
        website = storage["websites"].get(site_id)
        if not website:
            await callback_query.answer("Website not found.")
            return

        # Get the current notification data from storage
        latest_notification = storage.get("latest_notification", {})
        debug_print(f"[DEBUG] back_to_main - Latest notification data: {latest_notification}")

        # Create keyboard data based on website type and latest notification
        keyboard_data = {
            "site_id": site_id,
            "type": website.type,
            "url": website.url,
            "is_initial_run": website.is_initial_run,
            "single_mode": SINGLE_MODE
        }

        # Get the updated state from the current message's keyboard
        current_keyboard = callback_query.message.reply_markup
        is_updated = is_number_updated(current_keyboard)
        debug_print(f"[DEBUG] back_to_main - Current keyboard updated state: {is_updated}")

        # Set the updated state based on the current keyboard state
        keyboard_data["updated"] = is_updated

        # Add numbers based on website type and latest notification
        if website.type == "multiple":
            if latest_notification.get("site_id") == site_id and latest_notification.get("numbers"):
                keyboard_data["numbers"] = latest_notification.get("numbers", [])
            else:
                keyboard_data["numbers"] = website.latest_numbers if hasattr(website, 'latest_numbers') else []
        else:
            if latest_notification.get("site_id") == site_id and latest_notification.get("number"):
                keyboard_data["number"] = latest_notification.get("number")
            else:
                keyboard_data["number"] = website.last_number if hasattr(website, 'last_number') else None

        debug_print(f"[DEBUG] back_to_main - Creating keyboard with data: {keyboard_data}")
        keyboard = create_keyboard(keyboard_data, website)
        debug_print(f"[DEBUG] back_to_main - Keyboard created: {keyboard}")

        # Update the message with the new keyboard
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await callback_query.answer("Returned to main view.")
    except Exception as e:
        debug_print(f"[ERROR] back_to_main - error: {e}")
        return


async def split_number(callback_query: CallbackQuery):
    try:
        # Extract number and site_id from callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if len(parts) != 2 or not site_id:  # split_number or number_number
            debug_print(f"[ERROR] split_number - invalid format, parts: {parts}, site_id: {site_id}")
            await callback_query.answer("Invalid format")
            return

        number = parts[1]
        debug_print(f"[DEBUG] split_number - extracted number: {number}, site_id: {site_id}")

        # Remove country code from the number
        number_without_country_code = remove_country_code(number)
        split_message = f"`{number_without_country_code}`"

        # Send the split number message
        temp_message = await callback_query.bot.send_message(
            chat_id=callback_query.message.chat.id,
            text=split_message,
            parse_mode="Markdown")

        # Create a task to delete the message after 30 seconds
        asyncio.create_task(
            delete_message_after_delay(callback_query.bot, temp_message, 30))

    except Exception as e:
        debug_print(f"Error in split_number: {e}")
        await callback_query.answer("Error splitting number")


async def send_ping_reply(message: Message):
    await message.bot.send_message(chat_id=message.from_user.id,
                                   text="I am now online 🌐")
    await message.delete()


async def set_repeat_interval(message: Message, command: CommandObject):
    try:
        if command.args:
            args = command.args.lower().strip()

            # Parse the new interval
            new_interval = None

            if args in ["default", "true"]:
                new_interval = DEFAULT_REPEAT_INTERVAL
                global ENABLE_REPEAT_NOTIFICATION
                # Only print the state change if it's actually changing
                if not ENABLE_REPEAT_NOTIFICATION:
                    ENABLE_REPEAT_NOTIFICATION = True
                    print(f"Repeat notification state: Enabled")
                else:
                    ENABLE_REPEAT_NOTIFICATION = True

            # Check for the "x" prefix for minutes
            elif args.startswith("x") and args[1:].isdigit():
                minutes = int(args[1:])
                if minutes <= 0:
                    error_msg = await message.reply(
                        "⚠️ Please provide a positive number of minutes")
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    await message.delete()
                    return

                new_interval = minutes * 60  # Convert minutes to seconds

            elif args.isdigit():
                seconds = int(args)
                if seconds <= 0:
                    error_msg = await message.reply(
                        "⚠️ Please provide a positive number of seconds")
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    await message.delete()
                    return

                new_interval = seconds

            else:
                error_msg = await message.reply(
                    "⚠️ Please provide a valid number, 'default', 'true', or use 'x' prefix for minutes (e.g., 'x10' for 10 minutes). Example: `/set_repeat 300`, `/set_repeat x5`, or `/set_repeat default`"
                )
                await asyncio.sleep(5)
                await error_msg.delete()
                await message.delete()
                return

            # Save the new interval and enable repeat notifications
            storage["repeat_interval"] = new_interval

            # Only print the state change if repeat notification was disabled
            if not ENABLE_REPEAT_NOTIFICATION:
                ENABLE_REPEAT_NOTIFICATION = True
                print("Repeat notification state: Enabled")
            else:
                ENABLE_REPEAT_NOTIFICATION = True

            print(f"Repeat interval set to: {new_interval} seconds ({format_time(new_interval)})")

            # Check if there's an active countdown
            if CHAT_ID in storage["active_countdown_tasks"]:
                # Cancel the existing task
                storage["active_countdown_tasks"][CHAT_ID].cancel()
                storage["active_countdown_tasks"].pop(CHAT_ID, None)

                # Update the current message with the new countdown if there's an active notification
                if storage["latest_notification"]["message_id"]:
                    message_id = storage["latest_notification"]["message_id"]
                    number = storage["latest_notification"]["number"]
                    flag_url = storage["latest_notification"]["flag_url"]
                    site_id = storage["latest_notification"].get(
                        "site_id", "site_1")

                    # Update the message with the new countdown
                    current_message = (
                        f"🎁 *New Number Added* 🎁\n\n"
                        f"`+{number}` check it out! 💖\n\n"
                        f"⏱ Next notification in: *{format_time(new_interval)}*"
                    )

                    try:
                        await message.bot.edit_message_caption(
                            chat_id=CHAT_ID,
                            message_id=message_id,
                            caption=current_message,
                            parse_mode="Markdown",
                            reply_markup=create_keyboard(number, site_id=site_id))

                        # Create a new countdown task with the updated interval
                        countdown_task = asyncio.create_task(
                            update_message_with_countdown(
                                message.bot, message_id, number, flag_url,
                                site_id))
                        storage["active_countdown_tasks"][
                            CHAT_ID] = countdown_task
                    except Exception as e:
                        debug_print(
                            f"Error updating message with new countdown: {e}")

            await message.delete()

        else:
            error_msg = await message.reply(
                "⚠️ Please provide a number of seconds, minutes with 'x' prefix (e.g., 'x10'), or 'default'. Example: `/set_repeat 300`, `/set_repeat x5`, or `/set_repeat default`"
            )
            await asyncio.sleep(5)
            await error_msg.delete()
            await message.delete()
    except Exception as e:
        debug_print(f"Error in set_repeat_interval: {e}")
        error_msg = await message.reply(
            "⚠️ An error occurred. Please try again.")
        await asyncio.sleep(5)
        await error_msg.delete()
        await message.delete()


async def stop_repeat_notification(message: Message):
    global ENABLE_REPEAT_NOTIFICATION
    ENABLE_REPEAT_NOTIFICATION = False

    try:
        # Get the latest notification data
        latest = storage.get("latest_notification", {})
        if not latest:
            return

        site_id = latest.get("site_id")
        if not site_id:
            return

        # Only cancel countdown tasks for this specific site
        if site_id in storage["active_countdown_tasks"]:
            storage["active_countdown_tasks"][site_id].cancel()
            del storage["active_countdown_tasks"][site_id]

        website = storage["websites"].get(site_id)
        if not website:
            return

        # If SINGLE_MODE is enabled and it's a multiple type website
        if SINGLE_MODE and website.type == "multiple":
            # Get all numbers from the latest notification
            numbers = latest.get("numbers", [])
            if not numbers:
                return

            # Update each individual notification message
            for number in numbers:
                basic_message = f"🎁 *New Numbers Added* 🎁\n\n`{number}` check it out! 💖"
                try:
                    # Get the message ID for this number from storage
                    message_id = latest.get("message_id")
                    if message_id:
                        await message.bot.edit_message_caption(
                            chat_id=CHAT_ID,
                            message_id=message_id,
                            caption=basic_message,
                            parse_mode="Markdown",
                            reply_markup=create_keyboard(number))  # Keep original button state
                except Exception as e:
                    debug_print(f"Error updating message for number {number}: {e}")
        else:
            # Handle single notification case
            number = latest.get("number")
            if number:
                basic_message = f"🎁 *New Number Added* 🎁\n\n`{number}` check it out! 💖"
                try:
                    await message.bot.edit_message_caption(
                        chat_id=CHAT_ID,
                        message_id=latest.get("message_id"),
                        caption=basic_message,
                        parse_mode="Markdown",
                        reply_markup=create_keyboard(number))  # Keep original button state
                except Exception as e:
                    debug_print(f"Error updating single notification: {e}")

    except Exception as e:
        debug_print(f"Error removing countdown from notification: {e}")

    await message.delete()


async def send_startup_message(bot):
    if CHAT_ID:
        try:
            await bot.send_message(CHAT_ID, text="At Your Service 🍒🍄")
        except Exception as e:
            debug_print(f"⚠️ Failed to send startup message: {e}")


async def toggle_single_mode(callback_query: CallbackQuery):
    """Toggle SINGLE_MODE setting"""
    try:
        site_id = parse_callback_data(callback_query.data)
        if site_id is None:
            await callback_query.answer("Invalid site ID")
            return

        # Toggle SINGLE_MODE in config
        global SINGLE_MODE
        SINGLE_MODE = not SINGLE_MODE

        # Try to update config file if it exists
        config_file = "config_file.env"
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    lines = f.readlines()

                with open(config_file, "w") as f:
                    for line in lines:
                        if line.startswith("SINGLE_MODE="):
                            f.write(f"SINGLE_MODE={str(SINGLE_MODE).lower()}\n")
                        else:
                            f.write(line)
            except Exception as e:
                debug_print(f"[WARNING] Could not update config file: {e}")
                # Continue execution even if config file update fails
        else:
            debug_print("[INFO] No config file found, using environment variable only")

        # Return to settings menu to show updated state
        await handle_settings(callback_query)
        await callback_query.answer(f"Single Mode {'Enabled' if SINGLE_MODE else 'Disabled'}")

    except Exception as e:
        debug_print(f"[ERROR] Error in toggle_single_mode: {e}")
        await callback_query.answer("Failed to toggle Single Mode")