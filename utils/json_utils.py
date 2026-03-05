import os
import json
import re
import traceback
from typing import Dict, Tuple
import aiofiles
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config


class JSONUtils:
    @classmethod
    async def read_json(cls, jsonfile):
        # Load existing caption index if available
        try:
            if os.path.exists(jsonfile):
                async with aiofiles.open(jsonfile, "r") as f:
                    contents = await f.read()
                    index_contents = json.loads(contents)
            else:
                index_contents = {}
            return index_contents
        except Exception as e:
            LogManager.log_core(
                f"Failed to read JSON file {jsonfile}: {e}\n{traceback.format_exc()}"
            )
            return {}

    @classmethod
    async def save_json(cls, jsondata: Dict, jsonfile):
        try:
            async with aiofiles.open(jsonfile, "w") as f:
                await f.write(json.dumps(jsondata, indent=2))
        except Exception as e:
            LogManager.log_core(
                f"Failed to save JSON to {jsonfile}: {e}\n{traceback.format_exc()}"
            )
