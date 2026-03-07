import asyncio
import traceback
import os
import re
import json
import dateparser
from datetime import datetime
from dateutil.relativedelta import relativedelta
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from utils.file_utils import FileManager
from utils.template_manager import TemplateManager
from yp_dl.yp_dl import YoutubePosts, get_SOCS_cookie


class CommunityDownloader:
    _download_lock = asyncio.Lock()
    json_dir = os.path.join(
        DVR_Config.get_posted_notices_dir(),
        Account_Config.get_youtube_handle_name().lstrip("/"),
    )
    community_archive = os.path.join(
        DVR_Config.get_posted_notices_dir(), "Community_Post_Archive.html"
    )
    json_path = os.path.join(json_dir, "posts_posts.json")
    posts_url = f"{Account_Config.get_youtube_handle()}/posts"
    ythandle = Account_Config.get_youtube_handle_name()
    templates_dir = DVR_Config.get_templates_dir()
    posts_template = os.path.join(templates_dir, "posts_page.html")
    posts_youtube_placeholder_template = os.path.join(
        templates_dir, "posts_youtube_placeholder.html"
    )
    posts_embed_script_template = os.path.join(templates_dir, "posts_embed_script.html")
    posts_item_template = os.path.join(templates_dir, "posts_item.html")

    # Class variables to cache loaded templates
    _posts_youtube_placeholder_content = ""
    _posts_embed_script_content = ""
    _posts_item_content = ""

    # Template Manager instance for loading and caching templates
    _template_manager = None

    @classmethod
    def _get_template_manager(cls):
        """Get or create the template manager instance."""
        if cls._template_manager is None:
            cls._template_manager = TemplateManager(
                templates={
                    "_posts_youtube_placeholder_content": cls.posts_youtube_placeholder_template,
                    "_posts_embed_script_content": cls.posts_embed_script_template,
                    "_posts_item_content": cls.posts_item_template,
                },
                log_func=LogManager.log_download_posted_notices,
            )
        return cls._template_manager

    @classmethod
    async def _load_templates(cls):
        """Load HTML templates from files asynchronously."""
        manager = cls._get_template_manager()
        templates = await manager.load_templates()
        
        # Set class attributes from loaded templates
        cls._posts_youtube_placeholder_content = templates.get(
            "_posts_youtube_placeholder_content", ""
        )
        cls._posts_embed_script_content = templates.get(
            "_posts_embed_script_content", ""
        )
        cls._posts_item_content = templates.get("_posts_item_content", "")

    @classmethod
    async def monitor_channel(cls):
        await cls._load_templates()
        LogManager.log_download_posted_notices(
            f"Monitoring {cls.posts_url} for new Community Posts"
        )
        os.makedirs(cls.json_dir, exist_ok=True)

        while True:
            try:
                await cls.download_community_messages()
            except Exception as e:
                LogManager.log_download_posted_notices(
                    f"Error downloading community messages:{e}\n{traceback.format_exc()}"
                )
            await asyncio.sleep(60)

    @classmethod
    async def export_json_to_html(cls, json_path: str, output_html_path: str):
        await cls._load_templates()
        try:
            # Load posts JSON
            try:
                with open(json_path, "r", encoding="utf-8") as json_file:
                    posts = json.load(json_file)
                    posts = list(reversed(posts))
            except Exception as e:
                LogManager.log_download_posted_notices(f"Error loading JSON: {e}")
                return

            pagetitle = f"Community Posts Archive for {Account_Config.get_youtube_handle_name()}"

            # Load template content
            if not os.path.exists(cls.posts_template):
                LogManager.log_download_posted_notices(
                    f"Community posts template missing: {cls.posts_template}. Aborting export to HTML."
                )
                return
            try:
                with open(cls.posts_template, "r", encoding="utf-8") as tf:
                    template_content = tf.read()
                template_content = template_content.replace("{{PAGETITLE}}", pagetitle)
            except Exception as e:
                LogManager.log_download_posted_notices(
                    f"Error reading community posts template: {e}\n{traceback.format_exc()}"
                )
                return

            # Build posts HTML with lazy video placeholders
            new_posts_html = "\n"
            for post in posts:
                post_link = post.get("post_link", "")
                unique_id = post_link.rsplit("/", 1)[-1] if post_link else ""
                time_since = post.get("time_since", "")
                time_of_download = post.get("time_of_download", "")
                text = post.get("text", "") or ""
                images = post.get("images") or []
                video_url = post.get("video") or post.get("video_url") or None

                image_tags = "".join(
                    f'<img src="{img}" alt="Post image" style="max-width:80%; margin-top:10px;"><br>'
                    for img in images
                )

                # Combine images and video into media_html using a lazy placeholder
                media_html = image_tags
                if video_url:
                    try:
                        if "watch?v=" in video_url or "youtu.be/" in video_url:
                            if "watch?v=" in video_url:
                                vid = video_url.split("watch?v=")[1].split("&")[0]
                            else:
                                vid = video_url.split("youtu.be/")[1].split("?")[0]
                            thumb = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                            placeholder = (
                                cls._posts_youtube_placeholder_content.replace(
                                    "{{VID}}", vid
                                ).replace("{{THUMB}}", thumb)
                            )
                            media_html += placeholder
                        else:
                            media_html += f'<div class="post-video" style="margin-top:10px;"><a href="{video_url}">Video</a></div>'
                    except Exception:
                        media_html += f'<div class="post-video" style="margin-top:10px;"><a href="{video_url}">Video</a></div>'

                normalized_time = cls.parse_friendly_time(time_since)
                post_html = (
                    cls._posts_item_content.replace("{{POST_LINK}}", post_link)
                    .replace("{{YTHANDLE}}", cls.ythandle)
                    .replace("{{NORMALIZED_TIME}}", normalized_time)
                    .replace("{{TIME_OF_DOWNLOAD}}", time_of_download)
                    .replace("{{TEXT}}", text)
                    .replace("{{MEDIA_HTML}}", media_html)
                    .replace("{{UNIQUE_ID}}", unique_id)
                )
                new_posts_html += post_html + "\n"

            # Add embed script for lazy YouTube placeholders
            embed_script = cls._posts_embed_script_content

            # Append embed_script so placeholders will work
            new_posts_html += embed_script
            if "<body" in template_content.lower():
                # find first occurrence of the closing '>' of the <body ...> tag
                body_open_match = re.search(r"(?i)<body\b[^>]*>", template_content)
                if body_open_match:
                    insert_pos = body_open_match.end()
                    final_content = (
                        template_content[:insert_pos]
                        + "\n"
                        + new_posts_html
                        + template_content[insert_pos:]
                    )
                else:
                    final_content = template_content + "\n" + new_posts_html
            else:
                final_content = template_content + "\n" + new_posts_html

            # Write output HTML (overwrite existing)
            try:
                os.makedirs(os.path.dirname(output_html_path) or ".", exist_ok=True)
                with open(output_html_path, "w", encoding="utf-8") as outf:
                    outf.write(final_content)
            except Exception as e:
                LogManager.log_download_posted_notices(
                    f"Error writing community posts HTML to {output_html_path}: {e}\n{traceback.format_exc()}"
                )
                return

        except Exception as e:
            LogManager.log_download_posted_notices(
                f"Unhandled exception in export_json_to_html: {e}\n{traceback.format_exc()}"
            )
        pagetitle = (
            f"Community Posts Archive for {Account_Config.get_youtube_handle_name()}"
        )
        # Ensure HTML file exists with base structure (must come from template)
        if not os.path.exists(output_html_path):
            try:

                if not os.path.exists(cls.posts_template):
                    LogManager.log_download_posted_notices(
                        f"Community posts template missing: {cls.posts_template}. Aborting export to HTML."
                    )
                    return
                with open(cls.posts_template, "r", encoding="utf-8") as tf:
                    content = tf.read().replace("{{PAGETITLE}}", pagetitle)
                with open(output_html_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                LogManager.log_download_posted_notices(
                    f"Error creating community posts HTML from template: {e}\n{traceback.format_exc()}"
                )
                return

        # Read existing HTML content
        if not os.path.exists(output_html_path):
            LogManager.log_download_posted_notices(
                f"Community posts HTML file missing: {output_html_path}"
            )
            return
        with open(output_html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Prepare new post blocks
        new_posts_html = f' <h1 style="text-align:center;">{pagetitle}</h1><br/>'
        for post in posts:
            post_link = post.get("post_link")
            unique_id = post_link.rsplit("/", 1)[-1]
            id_present_inhtml = await FileManager.file_contains_string_mmap_async(
                output_html_path, unique_id
            )

            if id_present_inhtml:
                LogManager.log_download_posted_notices(
                    f"Skipping post with unique id {unique_id} as its present in the html"
                )
                continue

            time_since = post.get("time_since", "")
            time_of_download = post.get("time_of_download", "")
            text = post.get("text", "")
            images = post.get("images") or []
            video_url = post.get("video") or post.get("video_url") or None

            image_tags = "".join(
                f'<img src="{img}" alt="Post image" style="max-width:80%; margin-top:10px;"><br>'
                for img in images
            )

            media_html = image_tags
            if video_url:
                try:
                    if "watch?v=" in video_url or "youtu.be/" in video_url:
                        if "watch?v=" in video_url:
                            vid = video_url.split("watch?v=")[1].split("&")[0]
                        else:
                            vid = video_url.split("youtu.be/")[1].split("?")[0]
                        thumb = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                        placeholder = cls._posts_youtube_placeholder_content.replace(
                            "{{VID}}", vid
                        ).replace("{{THUMB}}", thumb)
                        media_html += placeholder
                    else:
                        media_html += f'<div class="post-video" style="margin-top:10px;"><a href="{video_url}">Video</a></div>'
                except Exception:
                    media_html += f'<div class="post-video" style="margin-top:10px;"><a href="{video_url}">Video</a></div>'

            normalized_time = cls.parse_friendly_time(time_since)
            post_html = (
                cls._posts_item_content.replace("{{POST_LINK}}", post_link)
                .replace("{{YTHANDLE}}", cls.ythandle)
                .replace("{{NORMALIZED_TIME}}", normalized_time)
                .replace("{{TIME_OF_DOWNLOAD}}", time_of_download)
                .replace("{{TEXT}}", text)
                .replace("{{MEDIA_HTML}}", media_html)
                .replace("{{UNIQUE_ID}}", unique_id)
            )
            new_posts_html += post_html

        # Insert new posts right after <body>
        updated_html = html_content.replace("<body>", f"<body>\n{new_posts_html}", 1)

        # Write updated HTML back to file
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(updated_html)

    @classmethod
    async def download_community_messages(cls):
        async with cls._download_lock:
            cookies = {"SOCS": get_SOCS_cookie()}
            yp = YoutubePosts(cls.posts_url, cookies)
            try:
                if not os.path.exists(cls.json_path):
                    LogManager.log_download_posted_notices(
                        f"Creating new Community Posts Archive for {cls.ythandle}"
                    )
                    os.makedirs(cls.json_dir, exist_ok=True)
                    await yp.scrape(pbar=None, limit=None)
                    yp.save(
                        pbar=None,
                        folder=DVR_Config.get_posted_notices_dir(),
                        reverse=False,
                        update=False,
                    )
                    firstrun = True
                else:
                    await yp.scrape(pbar=None, limit=None)
                    yp.save(
                        pbar=None,
                        folder=DVR_Config.get_posted_notices_dir(),
                        reverse=False,
                        update=True,
                    )
                    firstrun = False

                if firstrun:
                    try:
                        await cls.export_json_to_html(
                            cls.json_path, cls.community_archive
                        )
                    except Exception as e:
                        LogManager.log_download_posted_notices(
                            f"Error updating Community Posts HTML archive: {e}\n{traceback.format_exc()}"
                        )
                else:
                    await cls.export_json_to_html(cls.json_path, cls.community_archive)
            except Exception as e:
                LogManager.log_download_posted_notices(
                    f"Error in download_community_messages: {e}\n{traceback.format_exc()}"
                )

    @staticmethod
    def parse_friendly_time(time_str: str) -> str:
        try:
            # Simple parsing using dateparser; fall back to original string if parsing fails
            dt = dateparser.parse(time_str)
            if not dt:
                return time_str
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return time_str
