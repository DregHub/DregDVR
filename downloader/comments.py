import json
import datetime
import os
import yt_dlp
import traceback
import asyncio
from yt_dlp.utils import DownloadError
from yt_dlp.utils import match_filter_func
from config.config_settings import DVR_Config
from utils.logging_utils import LogManager


class LiveCommentsDownloader:
    Live_Comments_Dir = DVR_Config.get_live_comments_dir()
    TXT_Comments_Dir = os.path.join(Live_Comments_Dir, "_TXT")
    JSON_Comments_Dir = os.path.join(Live_Comments_Dir, "_JSON")
    _download_lock = asyncio.Lock()
    _publish_lock = asyncio.Lock()

    @classmethod
    async def download_comments(cls, yturl, filename):
        async with cls._download_lock:
            try:
                LogManager.log_download_comments(
                    f"Starting Live Comment Monitor for {yturl}"
                )
                os.makedirs(cls.Live_Comments_Dir, exist_ok=True)
                os.makedirs(cls.TXT_Comments_Dir, exist_ok=True)
                os.makedirs(cls.JSON_Comments_Dir, exist_ok=True)

                JSON_LiveChat_File = os.path.join(cls.JSON_Comments_Dir, f"{filename}")
                livechat_dl_opts = {
                    "skip_download": True,
                    "writesubtitles": True,
                    "subtitlesformat": "json",
                    "subtitleslangs": ["live_chat"],
                    "outtmpl": JSON_LiveChat_File,
                }

                with yt_dlp.YoutubeDL(livechat_dl_opts) as ydl:
                    try:
                        ydl.download([yturl])
                    except DownloadError as e:
                        msg = str(e)
                        LogManager.log_download_comments(
                            f"Error downloading live comments: {msg}"
                        )
                        if (
                            "Unable to download video subtitles for 'live_chat'"
                            not in msg
                            and ("HTTP Error 404" not in msg or "live_chat" not in msg)
                            and ("live_chat" not in msg or "404" not in msg)
                        ):
                            raise
                        LogManager.log_download_comments(
                            "Detected the live chat is no longer available, likely because the stream ended. Stopping comment monitor."
                        )
                # Publish comments to TXT and HTML after json download finishes
                await cls.publish_comments(JSON_LiveChat_File)
            except Exception as e:
                LogManager.log_download_comments(
                    f"Exception in download_comments:  {e}\n{traceback.format_exc()}"
                )

    @classmethod
    async def publish_comments(cls, sourcejson):
        async with cls._publish_lock:
            try:

                # Determine filenames
                filename = os.path.basename(sourcejson)
                base, ext = os.path.splitext(filename)
                html_filename = base + ".html"
                txt_filename = base + ".txt"

                LogManager.log_download_comments(
                    f"Publishing Comments from {sourcejson}"
                )
                os.makedirs(cls.Live_Comments_Dir, exist_ok=True)
                os.makedirs(cls.TXT_Comments_Dir, exist_ok=True)
                os.makedirs(cls.JSON_Comments_Dir, exist_ok=True)

                Templates_Dir = DVR_Config.get_templates_dir()
                HTML_Template_File = os.path.join(Templates_Dir, "Comments.html")

                HTML_LiveChat_File = os.path.join(cls.Live_Comments_Dir, html_filename)
                TXT_LiveChat_File = os.path.join(cls.TXT_Comments_Dir, txt_filename)

                # If the provided source path doesn't exist, try to find matching
                # JSON files in the JSON_Comments_Dir by matching the base filename.
                # If multiple matching files are found, combine them into a single
                # JSON file and use that as the source.
                if not os.path.exists(sourcejson):
                    matches = []
                    try:
                        for fn in os.listdir(cls.JSON_Comments_Dir):
                            fpath = os.path.join(cls.JSON_Comments_Dir, fn)
                            if not os.path.isfile(fpath):
                                continue
                            name_no_ext = os.path.splitext(fn)[0]
                            if name_no_ext == base or fn.startswith(base):
                                matches.append(fpath)
                    except Exception:
                        matches = []

                    if not matches:
                        LogManager.log_download_comments(
                            f"Source JSON not found: {sourcejson}"
                        )
                        return
                    if len(matches) == 1:
                        sourcejson = matches[0]
                    else:
                        # Combine multiple matching files into one JSON array file.
                        combined_path = os.path.join(
                            cls.JSON_Comments_Dir, f"{base}_combined.json"
                        )
                        combined_items = []
                        for m in matches:
                            try:
                                with open(m, "r", encoding="utf-8") as mf:
                                    mtext = mf.read()
                            except Exception as e:
                                LogManager.log_download_comments(
                                    f"Failed reading {m} during combine: {e}"
                                )
                                continue

                            # Try to parse each file; support JSON, NDJSON, or concatenated JSON
                            try:
                                parsed = json.loads(mtext)
                            except Exception:
                                decoder = json.JSONDecoder()
                                idx = 0
                                length = len(mtext)
                                objs = []
                                try:
                                    while idx < length:
                                        while idx < length and mtext[idx].isspace():
                                            idx += 1
                                        if idx >= length:
                                            break
                                        obj, end = decoder.raw_decode(mtext, idx)
                                        objs.append(obj)
                                        idx = end
                                except Exception:
                                    LogManager.log_download_comments(
                                        f"Failed parsing {m} during combine"
                                    )
                                    continue
                                parsed = objs

                            # Normalize parsed into a list of items (same logic as below)
                            local_items = []
                            if isinstance(parsed, dict):
                                if "events" in parsed and isinstance(
                                    parsed["events"], list
                                ):
                                    local_items = parsed["events"]
                                elif "entries" in parsed and isinstance(
                                    parsed["entries"], list
                                ):
                                    local_items = parsed["entries"]
                                else:
                                    for v in parsed.values():
                                        if isinstance(v, list):
                                            local_items = v
                                            break
                                    if not local_items:
                                        local_items = [parsed]
                            elif isinstance(parsed, list):
                                local_items = parsed
                            else:
                                local_items = [parsed]

                            combined_items.extend(local_items)

                        try:
                            with open(combined_path, "w", encoding="utf-8") as cf:
                                json.dump(combined_items, cf, ensure_ascii=False)
                            LogManager.log_download_comments(
                                f"Combined {len(matches)} JSON files into {combined_path}"
                            )
                            sourcejson = combined_path
                        except Exception as e:
                            LogManager.log_download_comments(
                                f"Failed creating combined JSON {combined_path}: {e}"
                            )
                            return

                # Read the file and try to parse as JSON. Support single JSON value,
                # newline-delimited JSON (NDJSON), or concatenated JSON objects.
                try:
                    with open(sourcejson, "r", encoding="utf-8") as jf:
                        text = jf.read()
                except Exception as e:
                    LogManager.log_download_comments(
                        f"Failed reading JSON {sourcejson}: {e}"
                    )
                    return

                try:
                    data = json.loads(text)
                except Exception:
                    # Fallback: parse as NDJSON or concatenated JSON objects using raw_decode
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
                            f"Failed parsing JSON {sourcejson}: {e}"
                        )
                        return
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

                html_parts = []
                txt_lines = []

                for it in items:
                    time_str = ""
                    author = ""
                    text = ""

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
                    if _contains_key(it, "liveChatViewerEngagementMessageRenderer"):
                        continue
                    if _is_emoji_only_message(it):
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
                                    dt = datetime.datetime.utcfromtimestamp(
                                        secs_val / 1000
                                    )
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
                        # Extract text: support nested `message.runs` used by YouTube
                        msg_val = (
                            it.get("message")
                            or it.get("text")
                            or it.get("message_text")
                        )
                        if (
                            isinstance(msg_val, dict)
                            and "runs" in msg_val
                            and isinstance(msg_val["runs"], list)
                        ):
                            text = "".join(
                                [
                                    (
                                        r.get("text", "")
                                        if isinstance(r, dict)
                                        else str(r)
                                    )
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
                        text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    safe_author = (
                        (author or "")
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )

                    html_parts.append(
                        f'<div class="comment"><span class="time">{time_str}</span> <strong class="author">{safe_author}</strong>: <span class="text">{safe_text}</span></div>'
                    )
                    if time_str or author:
                        txt_lines.append(f"[{time_str}] {author}: {text}")
                    else:
                        txt_lines.append(text)

                html_body = "\n".join(html_parts)

                template = ""
                if os.path.exists(HTML_Template_File):
                    with open(HTML_Template_File, "r", encoding="utf-8") as tf:
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
                        f"HTML Source template not found at {HTML_LiveChat_File} you get ugly light mode html now :( fix it "
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
                    f"Exception in publish_comments:  {e}\n{traceback.format_exc()}"
                )
