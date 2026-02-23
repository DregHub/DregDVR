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
    Templates_Dir = DVR_Config.get_templates_dir()

    @classmethod
    async def monitor_channel(cls):
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
        try:
            with open(json_path, "r", encoding="utf-8") as json_file:
                posts = json.load(json_file)
                # Reverse as new posts are always added to the bottom of the list
                posts = list(reversed(posts))
        except Exception as e:
            LogManager.log_download_posted_notices(f"Error loading JSON: {e}")
            return
        pagetitle = (
            f"Community Posts Archive for {Account_Config.get_youtube_handle_name()}"
        )
        # Ensure HTML file exists with base structure (must come from template)
        if not os.path.exists(output_html_path):
            try:
                tpl = os.path.join(cls.Templates_Dir, "Posts.html")
                if not os.path.exists(tpl):
                    LogManager.log_download_posted_notices(
                        f"Community posts template missing: {tpl}. Aborting export to HTML."
                    )
                    return
                with open(tpl, "r", encoding="utf-8") as tf:
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
        new_posts_html = f' <h1 style="text-align:center;">{pagetitle}</h1></br></>'
        for post in posts:
            post_link = post.get("post_link")
            unique_id = post_link.rsplit("/", 1)[-1]
            id_present_inhtml = await FileManager.file_contains_string_mmap_async(
                output_html_path, unique_id
            )

            if id_present_inhtml:
                # LogManager.log_download_posted_notices(f'Skipping post with unique id {unique_id} as its present in the html')
                continue

            time_since = post.get("time_since", "")
            time_of_download = post.get("time_of_download", "")
            text = post.get("text", "")
            images = post.get("images") or []

            image_tags = "".join(
                f'<img src="{img}" alt="Post image" style="max-width:80%; margin-top:10px;"><br>'
                for img in images
            )
            normalized_time = cls.parse_friendly_time(time_since)
            post_html = f"""
            <div class="post" id="{post_link}">
                <div class="title"><a href="{post_link}" style="color:#90caf9;">{cls.ythandle} Community Post</a></div>
                <div class="author">Posted: {normalized_time} | Downloaded: {time_of_download}</div>
                <div class="content">{text}<br>{image_tags}</div>
                <div class="unique-id" style="display: none;">{unique_id}</div>
            </div>
            """
            new_posts_html += post_html

        # Insert new posts right after <body>
        updated_html = html_content.replace("<body>", f"<body>\n{new_posts_html}", 1)

        # Write updated HTML back to file
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(updated_html)

    @classmethod
    async def download_community_messages(cls):
        async with cls._download_lock:
            firstrun = False
            if not os.path.exists(cls.json_path):
                LogManager.log_download_posted_notices(
                    f"Creating new Community Posts Archive for {cls.ythandle}"
                )
                args = [
                    "python3",
                    "-m",
                    "yp_dl.yp_dl",
                    "-f",
                    DVR_Config.get_posted_notices_dir(),
                    cls.posts_url,
                ]
                firstrun = True
            else:
                args = [
                    "python3",
                    "-m",
                    "yp_dl.yp_dl",
                    "-f",
                    DVR_Config.get_posted_notices_dir(),
                    "-u",
                    cls.posts_url,
                ]
                firstrun = False

            process = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                if stdout:
                    newposts_match = re.search(r"New posts:\s*(\d+)", stdout.decode())
                    totalposts_match = re.search(r"(?<=\/)\d+(?=\s)", stdout.decode())
                    if newposts_match or totalposts_match:
                        new_posts_count = (
                            int(newposts_match[1]) if newposts_match else 0
                        )
                        total_posts_count = (
                            int(totalposts_match[0]) if totalposts_match else 0
                        )

                        if total_posts_count > 0 and firstrun:
                            LogManager.log_download_posted_notices(
                                f"{total_posts_count} New Community Posts Found for new Community Archive."
                            )
                            try:
                                LogManager.log_download_posted_notices(
                                    "Adding new community posts to html archive."
                                )
                                await cls.export_json_to_html(
                                    cls.json_path, cls.community_archive
                                )
                            except Exception as e:
                                LogManager.log_download_posted_notices(
                                    f"Error updating Community Posts HTML archive: {e}"
                                )

                        elif new_posts_count > 0 and not firstrun:
                            try:
                                LogManager.log_download_posted_notices(
                                    f"Adding {new_posts_count} new community posts to html archive."
                                )
                                await cls.export_json_to_html(
                                    cls.json_path, cls.community_archive
                                )
                            except Exception as e:
                                LogManager.log_download_posted_notices(
                                    f"Error updating Community Posts HTML archive: {e}"
                                )
                    else:
                        LogManager.log_download_posted_notices(
                            "No output from community posts downloader try restarting to update the module."
                        )
            else:
                LogManager.log_download_posted_notices(
                    f"Community Posts Downloader exited with code {process.returncode} Check the channel hasnt been banned or made private."
                )
                if stdout:
                    LogManager.log_download_posted_notices(
                        f"STDOUT:\n{stdout.decode().strip()}"
                    )
                if stderr:
                    LogManager.log_download_posted_notices(
                        f"STDERR:\n{stderr.decode().strip()}"
                    )

    @classmethod
    def parse_friendly_time(cls, time_str):
        if not isinstance(time_str, str):
            return "Invalid input"
        # Try parsing with dateparser first
        dt = dateparser.parse(time_str)
        if dt is not None:
            return dt.strftime("%d/%m/%Y %I:%M %p")

        now = datetime.now()

        # Fallbacks for relative time expressions
        patterns = [
            (r"(\d+)\s+months?\s+ago", lambda n: now - relativedelta(months=n)),
            (r"(\d+)\s+weeks?\s+ago", lambda n: now - relativedelta(weeks=n)),
            (r"(\d+)\s+years?\s+ago", lambda n: now - relativedelta(years=n)),
        ]

        for pattern, adjust_func in patterns:
            if match := re.search(pattern, time_str):
                amount = int(match[1])
                dt = adjust_func(amount)
                return dt.strftime("%d/%m/%Y %I:%M %p")

        return f"Invalid date format {time_str}"
