import json
import datetime
import os
import yt_dlp
import traceback
import asyncio
from utils.dlp_utils import download_with_retry
from config.config_settings import DVR_Config
from utils.logging_utils import LogManager


class LiveCommentsDownloader:
    Live_Comments_Dir = DVR_Config.get_live_comments_dir()
    TXT_Comments_Dir = os.path.join(Live_Comments_Dir, "_TXT")
    JSON_Comments_Dir = os.path.join(Live_Comments_Dir, "_JSON")
    _download_lock = asyncio.Lock()
    _publish_lock = asyncio.Lock()
    templates_dir = DVR_Config.get_templates_dir()
    HTML_Template_File = os.path.join(templates_dir, "comments.html")

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

                try:
                    await download_with_retry(livechat_dl_opts, [yturl], filename)
                except Exception as e:
                    # download_with_retry logs details; still catch here to
                    # ensure publish_comments runs and errors are recorded.
                    LogManager.log_download_comments(
                        f"Error downloading live comments: {e}\n{traceback.format_exc()}"
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
                                thumb = (
                                    f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                                )
                                placeholder = (
                                    f'<div class="media video"><div class="yt-placeholder" data-vid="{vid}" '
                                    f'style="position:relative;max-width:560px;margin-top:10px;">'
                                    f'<img src="{thumb}" alt="YouTube thumbnail" '
                                    f'style="width:100%;height:auto;display:block;" />'
                                    f'<div class="yt-play" '
                                    f'style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);'
                                    f"width:72px;height:72px;border-radius:50%;background:rgba(0,0,0,0.6);"
                                    f'display:flex;align-items:center;justify-content:center;">'
                                    f'<svg width="36" height="36" viewBox="0 0 24 24" fill="white">'
                                    f'<path d="M8 5v14l11-7z"/></svg></div>'
                                    f'<div class="yt-spinner" '
                                    f'style="display:none;width:48px;height:48px;border:4px solid rgba(255,255,255,0.2);'
                                    f"border-top-color:#fff;border-radius:50%;animation:spin 1s linear infinite;"
                                    f'position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);"></div>'
                                    f'<div style="text-align:center;margin-top:6px;">'
                                    f'<a href="https://www.youtube.com/watch?v={vid}" target="_blank" '
                                    f'style="color:#90caf9;">Watch on YouTube</a></div>'
                                    f"</div></div>"
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

                    html_parts.append(
                        f'<div class="comment"><span class="time">{time_str}</span> <strong class="author">{safe_author}</strong>: <span class="text">{safe_text}</span>'
                        + media_html
                        + "</div>"
                    )

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

                                # Add small JS/CSS to enable click-to-load YouTube placeholders
                                embed_script = """
<style>@keyframes spin{to{transform:rotate(360deg);}}</style>
<script>
document.addEventListener('click', function(e){
    var p = e.target.closest && e.target.closest('.yt-placeholder');
    if(!p) return;
    if(p.dataset.loaded) return;
    var vid = p.dataset.vid;
    var spinner = p.querySelector('.yt-spinner');
    var img = p.querySelector('img');
    var play = p.querySelector('.yt-play');
    if(spinner) spinner.style.display='block';
    if(play) play.style.display='none';
    var iframe = document.createElement('iframe');
    iframe.width='560'; iframe.height='315';
    iframe.src='https://www.youtube-nocookie.com/embed/'+vid+'?rel=0&autoplay=1';
    iframe.allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
    iframe.allowFullscreen=true; iframe.loading='lazy'; iframe.style.border='0';
    iframe.addEventListener('load', function(){ if(spinner) spinner.style.display='none'; });
    p.insertBefore(iframe, img);
    if(img) img.style.display='none';
    p.dataset.loaded=1;
});
</script>
"""

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
