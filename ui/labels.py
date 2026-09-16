"""
Fixed UI strings, centralized to avoid duplication.
"""
from __future__ import annotations

FETCH_TRANSFER = "Fetch && Transfer Achievements"
TRANSFER_ALL = "Transfer All Account Games"
RESUME_BATCH = "Resume interrupted"

MENU_READ_BEFORE_USE = "Read before use"
MENU_SETTINGS = "Settings"

SETTINGS_TITLE = "Settings"
SETTINGS_CACHE_TTL = "Achievements cache TTL"
SETTINGS_CACHE_TTL_DESCRIPTION = (
    "When a game is fetched, its achievements are cached and reused until this "
    "time (in minutes) has passed since the last update. Set 0 to disable the "
    "cache."
)
SETTINGS_MINUTES_SUFFIX = " min"
SETTINGS_RESET_CACHE = "Reset achievements cache"
SETTINGS_TTL_UPDATED = "Achievements cache TTL set to {minutes} min."
SETTINGS_EXPIRED_REMOVED = "{count} expired file(s) removed."
SETTINGS_CACHE_CLEARED = "Achievements cache cleared ({count} file(s) removed)."

FIELD_APPID = "App ID(s)"
FIELD_APPID_LINK = "Find on SteamDB"
FIELD_APPID_PLACEHOLDER = "e.g. 240, 620, 440"
FIELD_APIKEY = "API Key"
FIELD_APIKEY_LINK = "Get your API key"
FIELD_USERID = "SteamID"
FIELD_USERID_LINK = "Find your SteamID"

SAVE_API_CHECKBOX = "Save API Key and SteamID"
CREATE_NAME_CHECKBOX = "Create a game file in each folder"
CREATE_NAME_HELP_TITLE = "Game name file"
CREATE_NAME_HELP = (
    "When enabled, saving achievements also creates a file like "
    "'240.CounterStrike_Source.txt' inside the game's GSE Saves folder. "
    "This makes it easy to tell which game each numbered folder belongs to."
)

IGNORE_UNPLAYED_CHECKBOX = "Ignore unplayed games"
IGNORE_UNPLAYED_HELP_TITLE = "Ignore unplayed games"
IGNORE_UNPLAYED_HELP = (
    "When enabled, 'Fetch all games from account' drops every game with no "
    "playtime, and the saved cache keeps only games you have actually played. "
    "Unplayed games are very unlikely to have achievements. To get them back, "
    "disable this and fetch again."
)

SEARCH_PLACEHOLDER = "Search by name or AppID..."

SORT_BY = "Sort by:"
SORT_NAME = "Name"
SORT_PLAYTIME = "Playtime"
FILTER_INSTALLED_ONLY = "Installed only"
