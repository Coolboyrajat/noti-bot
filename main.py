import asyncio
from bot.imports import Bot, Dispatcher, TELEGRAM_BOT_TOKEN, DefaultBotProperties, WebsiteMonitor, storage, load_website_configs, ENABLE_REPEAT_NOTIFICATION, DEFAULT_REPEAT_INTERVAL, SINGLE_MODE, register_handlers, send_startup_message, monitor_websites, send_notification, DEV_MODE, debug_print
from bot.special_site import SpecialSiteMonitor

async def main():
    # Initialize bot with minimal memory footprint
    bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    # Register handlers
    register_handlers(dp)

    # Initialize website monitors
    website_configs = load_website_configs()
    for site_id, config in website_configs.items():
        if config["enabled"] and config["url"]:
            if site_id == "special_site":
                storage["websites"][site_id] = SpecialSiteMonitor(site_id, config)
            else:
                storage["websites"][site_id] = WebsiteMonitor(site_id, config)

    # Initialize repeat interval if enabled
    if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is None:
        storage["repeat_interval"] = DEFAULT_REPEAT_INTERVAL

    print(f"✅ Bot is live in {'development' if DEV_MODE else 'production'} mode! I am now online 🌐")
    if DEV_MODE:
        debug_print("DEBUG logging is enabled - detailed logs will be displayed")

    # Start the bot
    dp_task = asyncio.create_task(dp.start_polling(bot, allowed_updates=["message", "callback_query"]))

    # Send startup message
    await send_startup_message(bot)

    # Start monitoring for new numbers across all websites
    # The monitor_websites function will handle first run detection and initialization
    monitor_task = asyncio.create_task(monitor_websites(bot, lambda data: send_notification(bot, data)))

    # Log status
    enabled_sites = [f"{site_id} ({website.url})" for site_id, website in storage["websites"].items() if website.enabled]
    print(f"Monitoring {len(enabled_sites)} websites:")
    for site in enabled_sites:
        print(f"  - {site}")
    print(f"Repeat notification status: {'Enabled' if ENABLE_REPEAT_NOTIFICATION else 'Disabled'}")
    print(f"Single mode status: {'Enabled' if SINGLE_MODE else 'Disabled'}")

    # Wait for both tasks to complete (they should run indefinitely)
    await asyncio.gather(dp_task, monitor_task)

if __name__ == "__main__":
    asyncio.run(main())
