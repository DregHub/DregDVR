# DregDVR
Dreg's DVR... Am i 4k wecording? Yes im 4k wecording!

# WOT IT DO ?

Automatically downloads all their YouTube....

	Livestreams
	Livestream Comments (even hidden or removed ones) to a .txt file
	Videos
	Shorts
	Community Posts

Automatically uploads....
	Their Livestreams, Videos, Shorts
	To internet archive which is practically unbannable
	To youtube (to seed google search results with links to the internet archive page we dont care if this gets taken down)

Using fuck all resources, no video transcoding, can run on a potato

# I WANT DIS! HOW I GET....

If your on windows run the command here and reboot

https://learn.microsoft.com/en-us/windows/wsl/install

download this and install
 
https://www.docker.com/products/docker-desktop/


Clone the repo into a folder structure like V:\Dregs\SOMEDREG first and fill in your config.cfg with real details

then look at this command and modify it for your system
docker run -v V:\Dregs\SOMEDREG:/dvr python:alpine python /dvr/main.py

command brakedown...

	V:\Dregs\SOMEDREG = The folder on the disk for this instance of the dvr, the repo files should already be in here
	:/dvr = Leave this alone can be the same for multiple dregs
	python:alpine = the os the container will run only alpine is supported
	python /dvr/main.py = the command the container will use to start the dregs dvr script

You need a different folder and container for each dreg you want to record

	eg
	docker run -v V:\Dregs\PJ:/dvr python:alpine python /dvr/main.py
	docker run -v V:\Dregs\Gert:/dvr python:alpine python /dvr/main.py
	docker run -v V:\Dregs\Timmy:/dvr python:alpine python /dvr/main.py
	etc

You need to customise each ini for each Dreg...
	Each DVR needs...
		1 An internet archive account and page (https://archive.org/create/ upload any file to community videos and configure a video archive, put the details page in the ini file)
		2 A youtube account with advanced features https://support.google.com/youtube/answer/9891124

Additionally
	1 google account with API access see: https://developers.google.com/youtube/v3/quickstart/python#step_1_set_up_your_project_and_credentials

	Save the oath json as YT-oauth2.json in \_Auth you can duplicate this file across all your Dreg dvr containers.\

	run ia configure within the containers shell to save your archive.org shared secret.


# OPTIONS , WHAT THEY DO!

Here is a quick breakdown of the config file

	[YT_Sources]
	source = "https://www.youtube.com/@somebody/live"             = The channel you want to clone (if you want more than one make another container)

	[YT_DownloadSettings]
	live_downloadprefix = timmylivestream-                        = This is what the flenames of downloaded livestreams will start with    
	posted_downloadprefix = timmypostedvideo-                     = This is what the flenames of downloaded videos will start with     
	download_timestamp_format = %(timestamp>%d-%m-%Y %I-%M%p)s    = The timestamp refer to yt-dlp documentation for more info this is attached to the end of all video file names
	download_file_extentions = [".mp4", ".webm", ".mkv", ".etc"]  = File extentions for the uploaders to watch the uploadqueue folders for
	dlp_no_progress_filters = [": [download]", "of ~", "iB/s"]    = filters to use when dlp_no_progress_downloads is true greatly reduces log file size (recommended)
	dlp_no_progress_downloads = true                              = dont output 1000s of lines of useless progress messages (recommended)
	dlp_verbose_downloads = true                                  = Run yt-dlp in verbose mode useful for troubleshooting (recommended)
	dlp_keep_fragments_downloads = false                          = Keep the fragments after downloading useful if anything fcuks up the uploader is smart enough to ignore these
	dlp_max_fragment_retries = 10                                 = Mapped to the --retries option for yt-dlp default is 10
	dlp_max_fragment_retries = 10                                 = Mapped to the --fragment-retries option for yt-dlp default is 10
	dlp_truncate_title_after_x_chars = 60                         = Trim the title of the source video when its too large (not the title of the prefixed filename we make)

	[IA_Settings]
	itemid = somename                                             = Your itemid on archive.org

	[IA_Credentials]
	email = 'someuser'                                            = Your archive.org credentials. You will still need to run ia configure on each container before uploading 
	password = '123'                                              = Your archive.org credentials. You will still need to run ia configure on each container before uploading 

	[Log_Filters]
	core_log_filter = []                                          = ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy
	download_live_log_filter = []                                 = ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy
	download_posted_log_filter = []                               = ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy
	download_posted_notices_log_filter = []                       = ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy
	upload_posted_log_filter = []                                 = ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy
	upload_live_log_filter = []                                   = ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy
	upload_ia_log_filter = []                                     = ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy
	upload_yt_log_filter = []                                     = ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy

	[Directories]
	live_uploadqueue_dir = _Live_UploadQueue                      = The name of the directory is customizable for reasons
	live_downloadqueue_dir = _Live_DownloadQueue                  = The name of the directory is customizable for reasons
	live_completeduploads_dir = _Live_CompletedUploads            = The name of the directory is customizable for reasons
	live_comments_dir = _Live_Comments                            = The name of the directory is customizable for reasons
	posted_uploadqueue_dir = _Posted_UploadQueue                  = The name of the directory is customizable for reasons
	posted_downloadqueue_dir = _Posted_DownloadQueue              = The name of the directory is customizable for reasons
	posted_completeduploads_dir = _Posted_CompletedUploads        = The name of the directory is customizable for reasons
	posted_playlists_dir = _Posted_Playlists                      = The name of the directory is customizable for reasons
	posted_notices_dir = _Posted_CommunityMessages                = The name of the directory is customizable for reasons
	metadata_dir = _Meta                                          = The name of the directory is customizable for reasons
	log_dir = _Logs                                               = The name of the directory is customizable for reasons
	auth_dir = _Auth                                              = The name of the directory is customizable for reasons
	bin_dir = /usr/local/bin                                      = the ia binary goes in here, we download it for you how handy
	dirs_to_create =                                              = ["make", "this", "dir"]

	[Maintenance]
	container_maintenance_inf_loop = false                        = boots the contianer and does nothing if true, so you can run commands
	required_dependencies = ["are","installed","automatically"]   = dependencies for us to automatically install using pip
	disable_live_download = false                                 = If true we dont download livestreams as they are streaming
	disable_live_recovery_download = false                        = If true we dont download livestreams again for recovery after they have finished
	disable_comment_download = false                              = If true we dont download comments from livestreams
	disable_posted_download = false                               = if true we dont download shorts or posted videos
	disable_posted_notices_download = false						  = if true we dont archive community posts to \_Posted_CommunityMessages\Community_Post_Archive.html
	disable_live_upload = true                                    = if true we dont upload livestreams
	disable_posted_upload = true                                  = if true we dont upload shorts or posted videos
	disable_log_archiving = true                                  = if true we dont archive logs into folders based on the video filename (useful for troubleshooting)


# CREDITS , WHO TO THANK
https://github.com/yt-dlp/yt-dlp

https://github.com/xenova/chat-downloader

https://github.com/Pyreko/yt-community-post-archiver