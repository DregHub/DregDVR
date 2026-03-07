import asyncio
import os
import traceback
from typing import Callable, Dict, Optional


class TemplateManager:
    """Centralizes template loading for multiple template files with caching and error handling."""

    def __init__(
        self,
        templates: Dict[str, str],
        log_func: Optional[Callable[[str], None]] = None,
        loaded_flag_name: str = "_templates_loaded",
    ):
        """
        Initialize the TemplateManager.

        Args:
            templates: Dictionary mapping attribute names to template file paths.
                       Example: {
                           '_posts_item_content': '/path/to/posts_item.html',
                           '_posts_embed_script_content': '/path/to/posts_embed_script.html'
                       }
            log_func: Optional logging function that accepts a string message.
            loaded_flag_name: Name of the flag attribute to check if templates are already loaded.
        """
        self.templates = templates
        self.log_func = log_func or (lambda msg: None)
        self.loaded_flag_name = loaded_flag_name
        self._cache: Dict[str, str] = {}
        self._is_loaded = False
        self._load_lock = asyncio.Lock()

    async def load_templates(self) -> Dict[str, str]:
        """
        Load all templates asynchronously with caching.

        Returns:
            Dictionary mapping attribute names to their loaded content.
        """
        async with self._load_lock:
            if self._is_loaded:
                return self._cache

            tasks = []
            for attr_name, file_path in self.templates.items():
                tasks.append(self._load_single_template(attr_name, file_path))

            results = await asyncio.gather(*tasks, return_exceptions=False)

            self._cache = {
                attr_name: content
                for attr_name, content in zip(self.templates.keys(), results)
            }
            self._is_loaded = True
            return self._cache

    async def _load_single_template(self, attr_name: str, file_path: str) -> str:
        """
        Load a single template file.

        Args:
            attr_name: The attribute name for this template (used in logging).
            file_path: Path to the template file.

        Returns:
            Template content as string, or empty string if loading fails.
        """
        try:
            await asyncio.to_thread(self._read_file_sync, file_path)
            with open(file_path, "r", encoding="utf-8") as f:
                content = await asyncio.to_thread(f.read)
            return content
        except Exception as e:
            self.log_func(
                f"Exception loading {attr_name} template from {file_path}: {e}\n{traceback.format_exc()}"
            )
            return ""

    @staticmethod
    def _read_file_sync(file_path: str) -> str:
        """Synchronous file read helper for use with asyncio.to_thread."""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def get_template(self, attr_name: str) -> str:
        """
        Get a cached template by attribute name.

        Args:
            attr_name: The attribute name of the template.

        Returns:
            Template content, or empty string if not loaded or not found.
        """
        return self._cache.get(attr_name, "")

    def is_loaded(self) -> bool:
        """Check if all templates have been loaded."""
        return self._is_loaded
