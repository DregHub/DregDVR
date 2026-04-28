import json
import datetime
import os
import traceback
import asyncio
from dlp.helpers import DLPHelpers

# optional emoji library used to convert colon-style names to unicode
try:
    import emoji  # type: ignore

    _emoji_lib_available = True
except ImportError:
    _emoji_lib_available = False

from config.config_settings import DVR_Config
from utils.logging_utils import LogManager, LogLevels
from utils.template_manager import TemplateManager


class LiveCommentsDownloader:
    Live_Comments_Dir = None
    TXT_Comments_Dir = None
    JSON_Comments_Dir = None
    _download_lock = asyncio.Lock()
    _publish_lock = asyncio.Lock()
    templates_dir = None
    comments_templates_dir = None
    HTML_Template_File = None
    comments_youtube_placeholder_template = None
    comments_embed_script_template = None
    comments_item_template = None
    comments_user_banned_banner_template = None
    comments_removed_post_banner_template = None

    @classmethod
    async def _ensure_initialized(cls):
        """Initialize class variables from config on first use."""
        if cls.Live_Comments_Dir is not None:
            return  # Already initialized
        cls.Live_Comments_Dir = DVR_Config.get_live_comments_dir()
        cls.TXT_Comments_Dir = os.path.join(cls.Live_Comments_Dir, "_TXT")
        cls.JSON_Comments_Dir = os.path.join(cls.Live_Comments_Dir, "_JSON")
        cls.templates_dir = DVR_Config.get_templates_dir()
        cls.comments_templates_dir = os.path.join(cls.templates_dir, "comments")
        cls.HTML_Template_File = os.path.join(
            cls.comments_templates_dir, "comments_page.html"
        )
        cls.comments_youtube_placeholder_template = os.path.join(
            cls.comments_templates_dir, "comments_youtube_placeholder.html"
        )
        cls.comments_embed_script_template = os.path.join(
            cls.comments_templates_dir, "comments_embed_script.html"
        )
        cls.comments_item_template = os.path.join(
            cls.comments_templates_dir, "comments_item.html"
        )
        cls.comments_user_banned_banner_template = os.path.join(
            cls.comments_templates_dir, "comments_user_banned_banner.html"
        )
        cls.comments_removed_post_banner_template = os.path.join(
            cls.comments_templates_dir, "comments_removed_post_banner.html"
        )

    # Class variables to cache loaded templates
    _comments_youtube_placeholder_content = None
    _comments_embed_script_content = None
    _comments_item_content = None
    _comments_user_banned_banner_content = None
    _comments_removed_post_banner_content = None

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
                    "_comments_user_banned_banner_content": cls.comments_user_banned_banner_template,
                    "_comments_removed_post_banner_content": cls.comments_removed_post_banner_template,
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
        cls._comments_user_banned_banner_content = templates.get(
            "_comments_user_banned_banner_content", ""
        )
        cls._comments_removed_post_banner_content = templates.get(
            "_comments_removed_post_banner_content", ""
        )

    @classmethod
    async def download_comments(cls, yturl, name_template, name_prefix):
        await cls._ensure_initialized()
        await cls._load_templates()
        async with cls._download_lock:
            try:
                LogManager.log_download_comments(
                    f"Starting Live Comment Monitor for {yturl}"
                )
                cls._ensure_chat_directories_exist()

                # Get instance context
                from utils.playlist_manager import PlaylistManager
                from config.config_settings import DVR_Config

                instance_name = await PlaylistManager._get_instance_name()
                channel_source = await PlaylistManager._get_channel_source()

                if not instance_name or not channel_source:
                    LogManager.log_download_comments(
                        "Cannot get instance context: instance_name or channel_source is not set",
                        LogLevels.Warning,
                    )
                else:
                    # Get download table name for current instance
                    db = await PlaylistManager._get_db()
                    download_table_name = db.get_playlist_download_table_name(
                        channel_source
                    )

                    # Get current download playlist
                    current_download_playlist = await db.get_current_download_playlist(
                        instance_name
                    )

                    if not current_download_playlist:
                        LogManager.log_download_comments(
                            "Cannot get current download playlist: current_download_playlist is not set",
                            LogLevels.Warning,
                        )
                    else:
                        LogManager.log_download_comments(
                            f"Scanning download table: {download_table_name} for playlist: {current_download_playlist} for instance: {instance_name}",
                            LogLevels.Info,
                        )

                options = cls._get_download_options(name_template)
                try:
                    await DLPHelpers.download_with_retry(
                        ydl_opts=options,
                        url_or_list=yturl,
                        timeout_enabled=True,
                        log_table_name=LogManager.table_download_comments,
                        log_warnings_and_above_only=False,
                        thread_number=1,
                    )
                except Exception as e:
                    LogManager.log_download_comments(
                        f"Error downloading live comments: {e}\n{traceback.format_exc()}",
                        LogLevels.Error,
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
                                f"Found existing JSON file: {file_path}", LogLevels.Info
                            )
                            json_path = file_path

                if json_path is not None:
                    await cls.publish_comments(json_path)
                else:
                    LogManager.log_download_comments(
                        f"No valid JSON file found for {name_template} in {cls.JSON_Comments_Dir}",
                        LogLevels.Warning,
                    )
                    LogManager.log_download_comments(
                        "Leaving as unpublished, This will be fixed on the next republish",
                        LogLevels.Warning,
                    )

            except Exception as e:
                LogManager.log_download_comments(
                    f"Exception in download_comments:  {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
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
            LogManager.log_download_comments(
                f"Failed reading JSON {file_path}: {e}", LogLevels.Error
            )
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
                    f"Failed parsing JSON {file_path}: {e}", LogLevels.Error
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
            LogManager.log_download_comments(
                f"Source JSON not found: {sourcejson}", LogLevels.Error
            )
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
                f"Combined {len(matches)} JSON files into {combined_path}",
                LogLevels.Info,
            )
            return combined_path
        except Exception as e:
            LogManager.log_download_comments(
                f"Failed creating combined JSON {combined_path}: {e}", LogLevels.Error
            )
            return None

    @classmethod
    def check_user_banned(cls, author_id, mod_items):
        if not author_id:
            LogManager.log_download_comments(
                "Empty author_id, skipping ban check"
            ), LogLevels.Warning
            return False
        return author_id in mod_items

    @classmethod
    def check_post_removed(cls, offset_time, mod_items):
        if not offset_time:
            LogManager.log_download_comments(
                "Empty offset_time, skipping removal check", LogLevels.Info
            )
            return False
        return offset_time in mod_items

    @classmethod
    async def _publish_from_json_path(cls, sourcejson_path):
        await cls._load_templates()
        try:
            # Helper function
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
            chat_items = cls._parse_json_file(sourcejson_path)
            # Filter out engagement messages to avoid errors
            chat_items = [
                item
                for item in chat_items
                if not _contains_key(item, "liveChatViewerEngagementMessageRenderer")
            ]
            # Filter out specific chat items based on actions and add them to removed_posts and banned_users
            removed_post_items = []
            banned_user_items = []
            filtered_items = []
            for item in chat_items:
                if isinstance(item, dict):
                    # Check for "removeChatItemAction" or "removeChatItemByAuthorAction"
                    if "replayChatItemAction" in item and isinstance(
                        item["replayChatItemAction"], dict
                    ):
                        actions = item["replayChatItemAction"].get("actions", [])
                        if any("removeChatItemAction" in action for action in actions):
                            removed_post_items.append(item)
                        if any(
                            "removeChatItemByAuthorAction" in action
                            for action in actions
                        ):
                            banned_user_items.append(item)
                        if any(
                            "removeChatItemAction" in action
                            or "removeChatItemByAuthorAction" in action
                            for action in actions
                        ):
                            continue
                filtered_items.append(item)
            chat_items = filtered_items

            removed_posts = []
            banned_users = []
            html_parts = []
            txt_lines = []

            # Create de-duplicated lists
            removed_offsets = list(
                set(
                    str(item.get("videoOffsetTimeMsec"))
                    for item in removed_post_items
                    if item.get("videoOffsetTimeMsec") is not None
                )
            )
            removed_posts = "\n".join(removed_offsets)
            banned_ids = set()
            for item in banned_user_items:
                rca = item.get("replayChatItemAction")
                if isinstance(rca, dict):
                    for a in rca.get("actions", []):
                        ban = a.get("removeChatItemByAuthorAction")
                        if isinstance(ban, dict):
                            id_ = ban.get("externalChannelId")
                            if id_:
                                banned_ids.add(id_)
            banned_users = "\n".join(banned_ids)

            for it in chat_items:
                time_str = ""
                author = ""
                text = ""
                channel_url = ""
                mod_action = ""
                post_id = ""
                author_id = ""
                offset_time = ""
                author_banned = False
                post_removed = False

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
                                return _unwrap(a)
                        return _unwrap(rc)
                    if "actions" in obj and isinstance(obj["actions"], list):
                        for a in obj["actions"]:
                            if (
                                isinstance(a, dict)
                                and "addChatItemAction" in a
                                and isinstance(a["addChatItemAction"], dict)
                            ):
                                return _unwrap(a["addChatItemAction"])
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
                    if "removeChatItemByAuthorAction" in obj and isinstance(
                        obj["removeChatItemByAuthorAction"], dict
                    ):
                        return obj["removeChatItemByAuthorAction"]
                    if "removeChatItemAction" in obj and isinstance(
                        obj["removeChatItemAction"], dict
                    ):
                        return obj["removeChatItemAction"]
                    return obj

                # preserve offset_time present on the raw item (before unwrapping)
                if isinstance(it, dict):
                    ot_val = it.get("videoOffsetTimeMsec")
                    if ot_val is not None:
                        offset_time = str(ot_val)

                it = _unwrap(it)

                # Extract post_id and author_id
                post_id = it.get("id", "")
                author_id = it.get(
                    "authorExternalChannelId", it.get("externalChannelId", "")
                )

                if not author_id:
                    LogManager.log_download_comments(
                        f"Warning: No author ID found for item {it}"
                    )

                # also check unwrapped object for a more specific offset_time
                if isinstance(it, dict) and not offset_time:
                    offset_time_val = it.get("videoOffsetTimeMsec")
                    if offset_time_val is not None:
                        offset_time = str(offset_time_val)

                # Check if author is banned or post is removed based on moderation data
                author_banned = cls.check_user_banned(author_id, banned_users)
                post_removed = cls.check_post_removed(offset_time, removed_posts)

                # Filter out moderation/remove events and engagement messages
                if _contains_key(it, "removeChatItemByAuthorAction"):
                    continue
                if _contains_key(it, "removeChatItemAction"):
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
                                time_str = datetime.datetime.fromtimestamp(
                                    secs_val / 1_000_000
                                ).strftime("%Y-%m-%d %H:%M:%S")
                            elif secs_val > 1_000_000_000:
                                time_str = datetime.datetime.fromtimestamp(
                                    secs_val
                                ).strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                time_str = str(secs_val)
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
                    def _extract_run_text(run):
                        # When processing `runs` from YouTube chat items, extract a
                        # human-readable representation. We try to return an
                        # actual emoji character for standard emojis (via the
                        # `emoji` package) and fall back to a shortcut/search term
                        # or accessibility label. Custom emojis usually have no
                        # unicode equivalent so we don't emit the internal ID.
                        #
                        # Returns a plain string; higher-level code will escape
                        # HTML characters, so this should not contain markup.
                        if isinstance(run, dict):
                            if "text" in run:
                                return run["text"]
                            elif "emoji" in run and isinstance(run["emoji"], dict):
                                e = run["emoji"]
                                # gather candidate label
                                label = ""
                                if "shortcuts" in e and e["shortcuts"]:
                                    label = e["shortcuts"][0]
                                if (
                                    not label
                                    and "searchTerms" in e
                                    and e["searchTerms"]
                                ):
                                    label = e["searchTerms"][0]
                                if not label:
                                    img = e.get("image", {})
                                    label = (
                                        img.get("accessibility", {})
                                        .get("accessibilityData", {})
                                        .get("label", "")
                                    )
                                # convert colon-style name to unicode if possible
                                if label:
                                    # ensure it is surrounded by colons for emoji lib
                                    if not label.startswith(":"):
                                        label = f":{label}:"
                                    if _emoji_lib_available:
                                        try:
                                            uni = emoji.emojize(label, language="alias")
                                            # if emojize didn't know this alias it'll
                                            # return the input verbatim; we detect that
                                            if uni != label:
                                                return uni
                                        except Exception:
                                            pass
                                    # fall back to image representation for custom
                                    thumbs = e.get("image", {}).get("thumbnails", [])
                                    if thumbs:
                                        # choose the largest thumbnail available
                                        url = thumbs[-1].get("url")
                                        if url:
                                            # produce inline HTML with styling so the
                                            # emoji is the same size as surrounding text
                                            # and aligns vertically. `display:inline-block`
                                            # prevents stacking.
                                            style = (
                                                "display:inline-block;"
                                                "width:1em;"
                                                "height:1em;"
                                                "vertical-align:middle;"
                                            )
                                            return (
                                                f'<img src="{url}" alt="{label}" '
                                                f'class="emoji" style="{style}">'
                                            )
                                    # no image, just return label text
                                    return label
                        return str(run)

                    msg_val = (
                        it.get("message") or it.get("text") or it.get("message_text")
                    )
                    if (
                        isinstance(msg_val, dict)
                        and "runs" in msg_val
                        and isinstance(msg_val["runs"], list)
                    ):
                        text = "".join(_extract_run_text(r) for r in msg_val["runs"])
                    elif isinstance(msg_val, str):
                        text = msg_val
                    else:
                        text = ""

                    if not text:
                        if "runs" in it and isinstance(it["runs"], list):
                            text = "".join(_extract_run_text(r) for r in it["runs"])
                        elif "snippet" in it and isinstance(it["snippet"], dict):
                            text = it["snippet"].get("text", "")
                else:
                    text = str(it)

                if not text:
                    try:
                        text = json.dumps(it, ensure_ascii=False)
                    except Exception:
                        text = str(it)

                # keep `<img>` tags intact so custom emojis render as images
                if "<img" in text:
                    safe_text = text
                else:
                    safe_text = (
                        text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
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
                            media_html += f'<div class="media video"><a href="{video_url}">Video</a></div>'
                        else:
                            media_html += f'<div class="media video"><a href="{video_url}">Video</a></div>'
                    except Exception:
                        media_html += f'<div class="media video"><a href="{video_url}">Video</a></div>'

                if images_val:
                    try:
                        if isinstance(images_val, str):
                            media_html += f'<div class="media image"><img src="{images_val}" alt="Image"></div>'
                        elif isinstance(images_val, list):
                            for img in images_val:
                                media_html += f'<div class="media image"><img src="{img}" alt="Image"></div>'
                    except Exception:
                        pass

                # determine CSS/value classes for banned/removed flags
                user_banned_banner = (
                    cls._comments_user_banned_banner_content if author_banned else ""
                )
                removed_post_banner = (
                    cls._comments_removed_post_banner_content if post_removed else ""
                )

                comment_html = (
                    cls._comments_item_content.replace("{{AUTHOR_NAME}}", author)
                    .replace("{{TIME_STR}}", time_str)
                    .replace("{{SAFE_TEXT}}", safe_text)
                    .replace("{{MEDIA_HTML}}", media_html)
                    .replace("{{MOD_ACTION}}", mod_action)
                    .replace("{{POST_ID}}", post_id)
                    .replace("{{AUTHOR_ID}}", author_id)
                    .replace("{{USER_BANNED_BANNER}}", user_banned_banner)
                    .replace("{{REMOVED_POST_BANNER}}", removed_post_banner)
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
