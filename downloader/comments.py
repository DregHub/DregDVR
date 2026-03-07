import json
import datetime
import os
import traceback
import asyncio
from utils.dlp_utils import download_with_retry
from config.config_settings import DVR_Config
from utils.logging_utils import LogManager
from utils.template_manager import TemplateManager


class LiveCommentsDownloader:
    Live_Comments_Dir = DVR_Config.get_live_comments_dir()
    TXT_Comments_Dir = os.path.join(Live_Comments_Dir, "_TXT")
    JSON_Comments_Dir = os.path.join(Live_Comments_Dir, "_JSON")
    _download_lock = asyncio.Lock()
    _publish_lock = asyncio.Lock()
    templates_dir = DVR_Config.get_templates_dir()
    HTML_Template_File = os.path.join(templates_dir, "comments_page.html")
    comments_youtube_placeholder_template = os.path.join(
        templates_dir, "comments_youtube_placeholder.html"
    )
    comments_embed_script_template = os.path.join(
        templates_dir, "comments_embed_script.html"
    )
    comments_item_template = os.path.join(templates_dir, "comments_item.html")

    # Class variables to cache loaded templates
    _comments_youtube_placeholder_content = None
    _comments_embed_script_content = None
    _comments_item_content = None

    # Template Manager instance for loading and caching templates
    _template_manager = None

    @classmethod
    def _get_template_manager(cls):
        """Get or create the template manager instance."""
        if cls._template_manager is None:
            cls._template_manager = TemplateManager(
                templates={
                    "_comments_youtube_placeholder_content": cls.comments_youtube_placeholder_template,
                    "_comments_embed_script_content": cls.comments_embed_script_template,
                    "_comments_item_content": cls.comments_item_template,
                },
                log_func=LogManager.log_download_comments,
            )
        return cls._template_manager

    @classmethod
    async def _load_templates(cls):
        """Load HTML templates from files asynchronously."""
        manager = cls._get_template_manager()
        templates = await manager.load_templates()

        # Set class attributes from loaded templates
        cls._comments_youtube_placeholder_content = templates.get(
            "_comments_youtube_placeholder_content", ""
        )
        cls._comments_embed_script_content = templates.get(
            "_comments_embed_script_content", ""
        )
        cls._comments_item_content = templates.get("_comments_item_content", "")

    @classmethod
    async def download_comments(cls, yturl, name_template, name_prefix):
        await cls._load_templates()
        async with cls._download_lock:
            try:
                LogManager.log_download_comments(
                    f"Starting Live Comment Monitor for {yturl}"
                )
                cls._ensure_chat_directories_exist()

                options = cls._get_download_options(name_template)
                try:
                    await download_with_retry(
                        options, yturl, LogManager.DOWNLOAD_COMMENTS_LOG_FILE
                    )
                except Exception as e:
                    LogManager.log_download_comments(
                        f"Error downloading live comments: {e}\n{traceback.format_exc()}"
                    )
                json_path = None
                # Search for files in JSON_Comments_Dir starting with name_prefix
                for file_name in os.listdir(cls.JSON_Comments_Dir):
                    if file_name.startswith(name_prefix):
                        file_path = os.path.join(cls.JSON_Comments_Dir, file_name)
                        if file_name.endswith(".part"):
                            new_file_path = file_path.rsplit(".part", 1)[0] + ".json"
                            os.rename(file_path, new_file_path)
                            LogManager.log_download_comments(
                                f"Renamed {file_path} to {new_file_path}"
                            )
                            json_path = new_file_path
                        else:
                            LogManager.log_download_comments(
                                f"Found existing JSON file: {json_path}"
                            )

                if json_path is not None:
                    await cls.publish_comments(json_path)
                else:
                    LogManager.log_download_comments(
                        f"No valid JSON file found for {name_template} in {cls.JSON_Comments_Dir}"
                    )
                    LogManager.log_download_comments(
                        "Leaving as unpublished, This will be fixed on the next republish"
                    )

            except Exception as e:
                LogManager.log_download_comments(
                    f"Exception in download_comments:  {e}\n{traceback.format_exc()}"
                )

    @classmethod
    def _ensure_chat_directories_exist(cls):
        os.makedirs(cls.Live_Comments_Dir, exist_ok=True)
        os.makedirs(cls.TXT_Comments_Dir, exist_ok=True)
        os.makedirs(cls.JSON_Comments_Dir, exist_ok=True)

    @classmethod
    def _get_download_options(cls, json_name_template):
        return {
            "paths": {
                "home": cls.JSON_Comments_Dir,
            },
            # ignoreerrors: True, Prevents 403 and 404 from crashing the sub downloader
            "ignoreerrors": True,
            "skip_download": True,
            "writesubtitles": True,
            "subtitlesformat": "json",
            "subtitleslangs": ["live_chat"],
            "outtmpl": json_name_template,
        }

    @classmethod
    def _parse_json_file(cls, file_path):
        """Parse a JSON file and return a list of comment items."""
        try:
            with open(file_path, "r", encoding="utf-8") as jf:
                text = jf.read()
        except Exception as e:
            LogManager.log_download_comments(f"Failed reading JSON {file_path}: {e}")
            return []

        try:
            data = json.loads(text)
        except Exception:
            # Fallback: parse as NDJSON or concatenated JSON objects
            decoder = json.JSONDecoder()
            idx = 0
            length = len(text)
            objs = []
            try:
                while idx < length:
                    # skip whitespace
                    while idx < length and text[idx].isspace():
                        idx += 1
                    if idx >= length:
                        break
                    obj, end = decoder.raw_decode(text, idx)
                    objs.append(obj)
                    idx = end
            except Exception as e:
                LogManager.log_download_comments(
                    f"Failed parsing JSON {file_path}: {e}"
                )
                return []
            data = objs

        # Normalize list of items
        items = []
        if isinstance(data, dict):
            if "events" in data and isinstance(data["events"], list):
                items = data["events"]
            elif "entries" in data and isinstance(data["entries"], list):
                items = data["entries"]
            else:
                # attempt to find first list value
                for v in data.values():
                    if isinstance(v, list):
                        items = v
                        break
                if not items:
                    items = [data]
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        return items

    @classmethod
    def _strip_part_extensions(cls, filename):
        """Strip .part extensions and variants (e.g., .part.2, .json.part) for matching purposes."""
        if ".part" in filename:
            filename = filename.split(".part")[0]
        return filename

    @classmethod
    def _resolve_source_json(cls, sourcejson):
        """Resolve the source JSON path, combining multiple files if necessary."""
        # Strip .part extensions from input to normalize the search path
        search_for = cls._strip_part_extensions(sourcejson)

        if os.path.exists(search_for):
            return search_for
        if os.path.exists(sourcejson):
            return sourcejson

        filename = os.path.basename(search_for)
        base, ext = os.path.splitext(filename)

        matches = []
        try:
            for fn in os.listdir(cls.JSON_Comments_Dir):
                fpath = os.path.join(cls.JSON_Comments_Dir, fn)
                if not os.path.isfile(fpath):
                    continue
                # Strip .part extensions for comparison
                fn_for_matching = cls._strip_part_extensions(fn)
                name_no_ext = os.path.splitext(fn_for_matching)[0]
                if name_no_ext == base or fn_for_matching.startswith(base):
                    matches.append(fpath)
        except Exception:
            matches = []

        if not matches:
            LogManager.log_download_comments(f"Source JSON not found: {sourcejson}")
            return None
        if len(matches) == 1:
            return matches[0]
        # Combine multiple matching files into one JSON array file.
        combined_path = os.path.join(cls.JSON_Comments_Dir, f"{base}_combined.json")
        combined_items = []
        for m in matches:
            local_items = cls._parse_json_file(m)
            combined_items.extend(local_items)

        try:
            with open(combined_path, "w", encoding="utf-8") as cf:
                json.dump(combined_items, cf, ensure_ascii=False)
            LogManager.log_download_comments(
                f"Combined {len(matches)} JSON files into {combined_path}"
            )
            return combined_path
        except Exception as e:
            LogManager.log_download_comments(
                f"Failed creating combined JSON {combined_path}: {e}"
            )
            return None

    @classmethod
    async def _publish_from_json_path(cls, sourcejson_path):
        await cls._load_templates()
        try:
            # Determine filenames
            filename = os.path.basename(sourcejson_path)
            base, ext = os.path.splitext(filename)
            # Remove .live_chat suffix if present
            if base.endswith(".live_chat"):
                base = base[: -len(".live_chat")]
            html_filename = f"{base}.html"
            txt_filename = base + ".txt"

            LogManager.log_download_comments(
                f"Publishing Comments from {sourcejson_path}"
            )

            HTML_LiveChat_File = os.path.join(cls.Live_Comments_Dir, html_filename)
            TXT_LiveChat_File = os.path.join(cls.TXT_Comments_Dir, txt_filename)

            # Read the file and try to parse as JSON. Support single JSON value,
            # newline-delimited JSON (NDJSON), or concatenated JSON objects.
            items = cls._parse_json_file(sourcejson_path)

            html_parts = []
            txt_lines = []

            for it in items:
                time_str = ""
                author = ""
                text = ""
                channel_url = ""
                mod_action = ""

                # Unwrap common YouTube replay/live chat wrappers so we can
                # extract `authorName` and `message.runs` when present.
                def _unwrap(obj):
                    if not isinstance(obj, dict):
                        return obj
                    if "replayChatItemAction" in obj and isinstance(
                        obj["replayChatItemAction"], dict
                    ):
                        rc = obj["replayChatItemAction"]
                        if "actions" in rc and isinstance(rc["actions"], list):
                            for a in rc["actions"]:
                                if (
                                    isinstance(a, dict)
                                    and "addChatItemAction" in a
                                    and isinstance(a["addChatItemAction"], dict)
                                ):
                                    inner = a["addChatItemAction"].get(
                                        "item", a["addChatItemAction"]
                                    )
                                    return _unwrap(inner)
                        return _unwrap(rc)
                    if "actions" in obj and isinstance(obj["actions"], list):
                        for a in obj["actions"]:
                            if (
                                isinstance(a, dict)
                                and "addChatItemAction" in a
                                and isinstance(a["addChatItemAction"], dict)
                            ):
                                inner = a["addChatItemAction"].get(
                                    "item", a["addChatItemAction"]
                                )
                                return _unwrap(inner)
                    if "addChatItemAction" in obj and isinstance(
                        obj["addChatItemAction"], dict
                    ):
                        inner = obj["addChatItemAction"].get(
                            "item", obj["addChatItemAction"]
                        )
                        return _unwrap(inner)
                    if "item" in obj and isinstance(obj["item"], dict):
                        return _unwrap(obj["item"])
                    if "liveChatTextMessageRenderer" in obj and isinstance(
                        obj["liveChatTextMessageRenderer"], dict
                    ):
                        return obj["liveChatTextMessageRenderer"]
                    return obj

                it = _unwrap(it)

                # Helper: recursively check if any dict key exists anywhere
                def _contains_key(obj, key_name):
                    if isinstance(obj, dict):
                        if key_name in obj:
                            return True
                        for v in obj.values():
                            if _contains_key(v, key_name):
                                return True
                    elif isinstance(obj, list):
                        for v in obj:
                            if _contains_key(v, key_name):
                                return True
                    return False

                # Helper: detect emoji-only messages
                def _is_emoji_only_message(obj):
                    msg = None
                    if isinstance(obj, dict):
                        msg = (
                            obj.get("message")
                            or obj.get("text")
                            or obj.get("message_text")
                        )
                    if isinstance(msg, dict) and isinstance(msg.get("runs"), list):
                        runs = msg.get("runs")
                        if not runs:
                            return False
                        for r in runs:
                            if not isinstance(r, dict):
                                return False
                            # emoji-only run typically has an 'emoji' key and no 'text'
                            if "emoji" not in r or r.get("text"):
                                return False
                        return True
                    return False

                # Filter out moderation/remove events and engagement messages
                if _contains_key(it, "removeChatItemByAuthorAction"):
                    continue
                if _contains_key(it, "removeChatItemAction"):
                    continue
                if _contains_key(it, "liveChatViewerEngagementMessageRenderer"):
                    continue
                if isinstance(it, dict):
                    # common time keys
                    time_val = (
                        it.get("time")
                        or it.get("timestamp")
                        or it.get("ts")
                        or it.get("offset_ms")
                        or it.get("timestampUsec")
                        or it.get("videoOffsetTimeMsec")
                    )
                    # Try to coerce numeric-like strings to integers as well
                    parsed_number = None
                    if isinstance(time_val, (int, float)):
                        parsed_number = int(time_val)
                    elif isinstance(time_val, str):
                        try:
                            parsed_number = int(time_val)
                        except Exception:
                            parsed_number = None

                    if parsed_number is not None:
                        try:
                            secs_val = parsed_number
                            # Interpret very large values as epoch in microseconds
                            if secs_val > 1_000_000_000_000:
                                dt = datetime.datetime.utcfromtimestamp(
                                    secs_val / 1_000_000
                                )
                                time_str = dt.strftime("%H:%M:%S")
                            # Interpret large values as milliseconds since epoch
                            elif secs_val > 1_000_000_000:
                                dt = datetime.datetime.utcfromtimestamp(secs_val / 1000)
                                time_str = dt.strftime("%H:%M:%S")
                            else:
                                # treat as seconds or offset; format as H:MM:SS
                                total_seconds = int(secs_val)
                                hours, rem = divmod(total_seconds, 3600)
                                minutes, seconds = divmod(rem, 60)
                                time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                        except Exception:
                            time_str = str(time_val)
                    elif isinstance(time_val, str):
                        time_str = time_val

                    # Extract author: support YouTube `authorName.simpleText`
                    author = (
                        it.get("author")
                        or it.get("author_name")
                        or it.get("name")
                        or ""
                    )
                    if not author and isinstance(it.get("authorName"), dict):
                        author = (
                            it["authorName"].get("simpleText")
                            or it["authorName"].get("runs")
                            or ""
                        )
                    channel_url = it.get("authorChannelUrl") or ""
                    if "authorChannelId" in it and not channel_url:
                        channel_id = it["authorChannelId"]
                        channel_url = f"https://www.youtube.com/channel/{channel_id}"
                    # Extract text: support nested `message.runs` used by YouTube
                    msg_val = (
                        it.get("message") or it.get("text") or it.get("message_text")
                    )
                    if (
                        isinstance(msg_val, dict)
                        and "runs" in msg_val
                        and isinstance(msg_val["runs"], list)
                    ):
                        text = "".join(
                            [
                                (r.get("text", "") if isinstance(r, dict) else str(r))
                                for r in msg_val["runs"]
                            ]
                        )
                    elif isinstance(msg_val, str):
                        text = msg_val
                    else:
                        text = ""

                    if not text:
                        if "runs" in it and isinstance(it["runs"], list):
                            text = "".join(
                                [
                                    (
                                        r.get("text", "")
                                        if isinstance(r, dict)
                                        else str(r)
                                    )
                                    for r in it["runs"]
                                ]
                            )
                        elif "snippet" in it and isinstance(it["snippet"], dict):
                            text = (
                                it["snippet"].get("textMessageDetails")
                                or it["snippet"].get("text")
                                or ""
                            )
                            if isinstance(text, dict):
                                text = text.get("messageText") or ""
                else:
                    text = str(it)

                if not text:
                    try:
                        text = json.dumps(it, ensure_ascii=False)
                    except Exception:
                        text = str(it)

                safe_text = (
                    text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                safe_author = (
                    (author or "")
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                author_html = (
                    f'<a href="{channel_url}">{safe_author}</a>'
                    if channel_url
                    else safe_author
                )

                # Embed any media (video/images) if present in the item
                media_html = ""
                video_url = None
                images_val = None
                if isinstance(it, dict):
                    video_url = it.get("video") or it.get("video_url") or None
                    images_val = it.get("images") if "images" in it else None

                if video_url:
                    try:
                        if "watch?v=" in video_url or "youtu.be/" in video_url:
                            if "watch?v=" in video_url:
                                vid = video_url.split("watch?v=")[1].split("&")[0]
                            else:
                                vid = video_url.split("youtu.be/")[1].split("?")[0]
                            thumb = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                            placeholder = (
                                cls._comments_youtube_placeholder_content.replace(
                                    "{{VID}}", vid
                                ).replace("{{THUMB}}", thumb)
                            )
                            media_html += placeholder
                        else:
                            media_html += f'<div class="media video"><a href="{video_url}">Video</a></div>'
                    except Exception:
                        media_html += f'<div class="media video"><a href="{video_url}">Video</a></div>'

                if images_val:
                    try:
                        if isinstance(images_val, str):
                            media_html += (
                                f'<div class="media images"><img src="{images_val}" alt="image" '
                                f'style="max-width:100%;height:auto;"></div>'
                            )
                        elif isinstance(images_val, list):
                            for img in images_val:
                                media_html += (
                                    f'<div class="media images"><img src="{img}" alt="image" '
                                    f'style="max-width:100%;height:auto;"></div>'
                                )
                    except Exception:
                        pass

                comment_html = (
                    cls._comments_item_content.replace("{{AUTHOR_HTML}}", author_html)
                    .replace("{{TIME_STR}}", time_str)
                    .replace("{{SAFE_TEXT}}", safe_text)
                    .replace("{{MEDIA_HTML}}", media_html)
                    .replace("{{MOD_ACTION}}", mod_action)
                )
                html_parts.append(comment_html)

                # Add metadata about media to TXT output as well
                if time_str or author:
                    txt_lines.append(f"[{time_str}] {author}: {text}")
                else:
                    txt_lines.append(text)
                if video_url:
                    txt_lines.append(f"[media] Video: {video_url}")
                if images_val:
                    if isinstance(images_val, str):
                        txt_lines.append(f"[media] Image: {images_val}")
                    elif isinstance(images_val, list):
                        for img in images_val:
                            txt_lines.append(f"[media] Image: {img}")

            html_body = "\n".join(html_parts)

            # Add embed script for click-to-load YouTube placeholders
            embed_script = cls._comments_embed_script_content

            html_body += embed_script

            template = ""
            if os.path.exists(cls.HTML_Template_File):
                with open(cls.HTML_Template_File, "r", encoding="utf-8") as tf:
                    template = tf.read()

            if template:
                # Replace title placeholder if present
                try:
                    out_html = template.replace("{{TITLE}}", base)
                except Exception:
                    out_html = template

                if "{{COMMENTS}}" in out_html:
                    out_html = out_html.replace("{{COMMENTS}}", html_body)
                elif "</body>" in out_html:
                    out_html = out_html.replace("</body>", html_body + "\n</body>")
                else:
                    out_html = out_html + html_body
            else:
                LogManager.log_download_comments(
                    f"HTML Source template not found at {cls.HTML_Template_File} you get ugly light mode html now :( fix it "
                )
                out_html = (
                    "<html><head><meta charset='utf-8'><title>Live Chat</title></head><body>\n"
                    + html_body
                    + "\n</body></html>"
                )

            with open(HTML_LiveChat_File, "w", encoding="utf-8") as hf:
                hf.write(out_html)
            with open(TXT_LiveChat_File, "w", encoding="utf-8") as tf:
                tf.write("\n".join(txt_lines))

            LogManager.log_download_comments(
                f"Published HTML livechat to {HTML_LiveChat_File}"
            )
            LogManager.log_download_comments(
                f"Published TXT livechat to {TXT_LiveChat_File}"
            )

        except Exception as e:
            LogManager.log_download_comments(
                f"Exception in _publish_from_json_path:  {e}\n{traceback.format_exc()}"
            )

    @classmethod
    async def publish_comments(cls, sourcejson):
        await cls._load_templates()
        async with cls._publish_lock:
            try:
                cls._ensure_chat_directories_exist()
                if resolved := cls._resolve_source_json(sourcejson):
                    await cls._publish_from_json_path(resolved)
            except Exception as e:
                LogManager.log_download_comments(
                    f"Exception in publish_comments:  {e}\n{traceback.format_exc()}"
                )

    @classmethod
    async def republish_comments(cls):
        await cls._load_templates()
        async with cls._publish_lock:
            try:
                cls._ensure_chat_directories_exist()
                json_files = []
                try:
                    for fn in os.listdir(cls.JSON_Comments_Dir):
                        fpath = os.path.join(cls.JSON_Comments_Dir, fn)
                        if os.path.isfile(fpath) and fn.endswith(".json"):
                            json_files.append(fpath)
                except Exception as e:
                    LogManager.log_download_comments(f"Error listing JSON files: {e}")
                    return

                LogManager.log_download_comments(
                    f"Republishing {len(json_files)} JSON comment files"
                )
                for json_path in json_files:
                    await cls._publish_from_json_path(json_path)
            except Exception as e:
                LogManager.log_download_comments(
                    f"Exception in republish_comments:  {e}\n{traceback.format_exc()}"
                )
