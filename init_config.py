#!/usr/bin/env python3
"""
DVR Database Initialization Helper
Provides utilities for database setup and configuration management.

Usage:
    python init_config.py list-instances
    python init_config.py create-instance <name>
    python init_config.py delete-instance <name>
    python init_config.py check-status
"""
import sys
import asyncio
import argparse
from utils.logging_utils import LogManager,LogLevels
from db.dvr_db import DVRDB


async def list_instances():
    """List all configured instances."""
    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

    # Register the event loop with lifecycle manager for logging
    loop = asyncio.get_running_loop()
    try:
        AsyncioLifecycleManager.register_loop(loop, loop_name="init_config_list")
    except Exception as e:
        print(f"Failed to register event loop: {e}")

    db = await DVRDB.get_global()
    instances = await db.get_all_instances()

    if not instances:
        LogManager.log_core("No instances configured yet.", LogLevels.Info)
        LogManager.log_core("Use the web UI to create instances: python run_web_ui.py", LogLevels.Info)
        return


async def create_instance(name):
    """Create a new instance."""
    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

    # Register the event loop with lifecycle manager for logging
    loop = asyncio.get_running_loop()
    try:
        AsyncioLifecycleManager.register_loop(loop, loop_name="init_config_create")
    except Exception as e:
        print(f"Failed to register event loop: {e}")

    db = await DVRDB.get_global()

    try:
        # Generate channel_id from name (remove @ prefix if present)
        channel_id = name.replace("@", "")
        # Use name as both instance_name and channel_name for CLI simplicity
        instance_name = name
        channel_name = name if name.startswith("@") else f"@{name}"
        source_platform = "YouTube.com/@"  # Default platform for CLI

        instance_id = await db.add_instance(
            channel_id=channel_id,
            instance_name=instance_name,
            channel_name=channel_name,
            source_platform=source_platform
        )
        LogManager.log_core(f"✅ Instance '{name}' created successfully!", LogLevels.Info)
        LogManager.log_core(f"Channel ID: {instance_id}", LogLevels.Info)
        LogManager.log_core(f"Now configure it using: python run_web_ui.py", LogLevels.Info)
    except Exception as e:
        LogManager.log_core(f"❌ Error creating instance: {e}", LogLevels.Error)
        sys.exit(1)


async def delete_instance(name):
    """Delete an instance."""
    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

    # Register the event loop with lifecycle manager for logging
    loop = asyncio.get_running_loop()
    try:
        AsyncioLifecycleManager.register_loop(loop, loop_name="init_config_delete")
    except Exception as e:
        print(f"Failed to register event loop: {e}")

    db = await DVRDB.get_global()

    instances = await db.get_all_instances()
    for inst in instances:
        # Check by instance_name first (for backward compatibility)
        if inst.get("instance_name") == name:
            channel_id = inst.get("channel_id")
            await db.delete_instance(channel_id)
            LogManager.log_core(f"✅ Instance '{name}' deleted successfully!", LogLevels.Info)
            return
        # Also check by channel_id
        elif inst.get("channel_id") == name:
            channel_id = inst.get("channel_id")
            await db.delete_instance(channel_id)
            LogManager.log_core(f"✅ Instance '{name}' deleted successfully!", LogLevels.Info)
            return

    LogManager.log_core(f"❌ Instance '{name}' not found!", LogLevels.Error)
    sys.exit(1)


async def check_status():
    """Check system configuration status."""
    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

    # Register the event loop with lifecycle manager for logging
    loop = asyncio.get_running_loop()
    try:
        AsyncioLifecycleManager.register_loop(loop, loop_name="init_config_status")
    except Exception as e:
        print(f"Failed to register event loop: {e}")

    db = await DVRDB.get_global()

    LogManager.log_core("DVR Configuration Status", LogLevels.Info)
    LogManager.log_core("-" * 60, LogLevels.Info)
    LogManager.log_core(f"Database Path: {db.db_path}", LogLevels.Info)
    LogManager.log_core(f"Fresh Database: {db.is_fresh}", LogLevels.Info)
    LogManager.log_core(f"Configured: {await db.is_configured()}", LogLevels.Info)

    instances = await db.get_all_instances()
    LogManager.log_core(f"\nInstances: {len(instances)}", LogLevels.Info)

    if instances:
        for inst in instances:
            account = await db.get_account(inst["instance_name"])
            settings = await db.get_instance_settings(inst["instance_name"])
            tasks = await db.get_tasks(inst["instance_name"])
            has_account = bool(account)
            has_settings = bool(settings)
            has_tasks = bool(tasks)

            status = "✓" if (has_account and has_settings and has_tasks) else "✗"
            LogManager.log_core(f"\n  {status} {inst['instance_name']}", LogLevels.Info)
            LogManager.log_core(f"     Account: {'✓' if has_account else '✗'}", LogLevels.Info)
            LogManager.log_core(f"     Settings: {'✓' if has_settings else '✗'}", LogLevels.Info)
            LogManager.log_core(f"     Tasks: {'✓' if has_tasks else '✗'}", LogLevels.Info)

    LogManager.log_core("\nNext Steps:", LogLevels.Info)
    if not instances:
        LogManager.log_core("1. Create an instance: python init_config.py create-instance <name>", LogLevels.Info)
        LogManager.log_core("2. Or use the web UI: python run_web_ui.py", LogLevels.Info)
    elif not db.is_configured():
        LogManager.log_core("1. Configure the system using the web UI: python run_web_ui.py", LogLevels.Info)
        LogManager.log_core("2. Complete all configuration sections", LogLevels.Info)
        LogManager.log_core("3. Click 'Start DVR Service'", LogLevels.Info)
    else:
        LogManager.log_core("✅ System is fully configured!", LogLevels.Info)
        LogManager.log_core("Run: python main.py", LogLevels.Info)


def main():
    parser = argparse.ArgumentParser(
        description="DVR Configuration Initialization Helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python init_config.py list-instances
  python init_config.py create-instance Production
  python init_config.py delete-instance TestMain
  python init_config.py check-status
        """,
    )

    parser.add_argument(
        "command",
        choices=[
            "list-instances",
            "create-instance",
            "delete-instance",
            "check-status",
        ],
        help="Command to execute",
    )

    parser.add_argument(
        "instance_name",
        nargs="?",
        help="Instance name (required for create-instance and delete-instance)",
    )

    args = parser.parse_args()

    if args.command == "list-instances":
        asyncio.run(list_instances())
    elif args.command == "create-instance":
        if not args.instance_name:
            LogManager.log_core("Error: instance_name required for create-instance", LogLevels.Error)
            sys.exit(1)
        asyncio.run(create_instance(args.instance_name))
    elif args.command == "delete-instance":
        if not args.instance_name:
            LogManager.log_core("Error: instance_name required for delete-instance", LogLevels.Error)
            sys.exit(1)
        asyncio.run(delete_instance(args.instance_name))
    elif args.command == "check-status":
        asyncio.run(check_status())


if __name__ == "__main__":
    main()
