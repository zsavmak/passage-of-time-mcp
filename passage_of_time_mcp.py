from fastmcp import FastMCP
import datetime
import pytz
import os
from typing import Dict, Union, Optional, Literal
from datetime import datetime, timedelta
from fastapi import Request, Response

API_KEY = os.environ.get("MCP_API_KEY")

class AuthenticatedFastMCP(FastMCP):
    """A wrapper around FastMCP to add API key authentication middleware."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        @self.app.middleware("http")
        async def check_api_key(request: Request, call_next):
            # If no API_KEY is configured on the server, we allow traffic.
            if not API_KEY:
                return await call_next(request)

            client_api_key = request.headers.get("X-API-Key")

            if not client_api_key or client_api_key != API_KEY:
                return Response(
                    content="Invalid or missing API Key",
                    status_code=401,
                    media_type="text/plain"
                )
            
            return await call_next(request)

mcp = AuthenticatedFastMCP(
    name="Perception of Passage of Time",
    instructions="""You now have access to current_datetime() and can pass along an optional timezone parameter (defaults to NYC). You should call this at the start of every response, so you can get an appreciation for the user's passage of time.

To help you make computations about time, you have multiple other tools:
- time_difference(): Calculate difference between two timestamps
- time_since(): Calculate time elapsed since a timestamp
- parse_timestamp(): Convert timestamp to multiple formats
- add_time(): Add/subtract duration from a timestamp
- timestamp_context(): Get contextual info about a timestamp
- format_duration(): Format seconds into readable text

IMPORTANT: All timestamps must use format "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD" for dates only. 
Examples: "2024-01-15 14:30:00" or "2024-01-15". This ensures no ambiguity in parsing."""
)


def parse_standard_timestamp(timestamp_str: str, timezone: str = "America/New_York") -> datetime:
    tz = pytz.timezone(timezone)
    timestamp_str = timestamp_str.strip()
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        return tz.localize(dt)
    except ValueError:
        pass
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d")
        return tz.localize(dt)
    except ValueError:
        pass
    try:
        parts = timestamp_str.rsplit(' ', 2)
        if len(parts) == 3 and len(parts[2]) <= 4:
            dt_str = f"{parts[0]} {parts[1]}"
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            return tz.localize(dt)
    except ValueError:
        pass
    raise ValueError(
        f"Invalid timestamp format: '{timestamp_str}'. "
        f"Expected format: 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD'."
    )

@mcp.tool()
def current_datetime(timezone: str = "America/New_York") -> str:
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        return now.strftime("%Y-%m-%d %H:%M:%S %Z")
    except pytz.exceptions.UnknownTimeZoneError:
        return f"Error: Unknown timezone '{timezone}'."

@mcp.tool()
def time_difference(
    timestamp1: str, 
    timestamp2: str, 
    unit: Literal["auto", "seconds", "minutes", "hours", "days"] = "auto",
    timezone: str = "America/New_York"
) -> Dict[str, Union[int, float, str, bool]]:
    try:
        dt1 = parse_standard_timestamp(timestamp1, timezone)
        dt2 = parse_standard_timestamp(timestamp2, timezone)
        delta = dt2 - dt1
        total_seconds = delta.total_seconds()
        is_negative = total_seconds < 0
        abs_seconds = abs(total_seconds)
        
        def format_timedelta(seconds):
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            parts = []
            if days > 0: parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours > 0: parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0: parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if secs > 0 or not parts: parts.append(f"{secs} second{'s' if secs != 1 else ''}")
            return ", ".join(parts)
        
        formatted = format_timedelta(abs_seconds)
        if is_negative: formatted = f"-{formatted}"
        
        result = {"seconds": total_seconds, "formatted": formatted, "is_negative": is_negative}
        
        if unit != "auto":
            unit_conversions = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
            result["requested_unit"] = total_seconds / unit_conversions[unit]
        
        return result
    except Exception as e:
        return {"error": str(e), "seconds": 0, "formatted": "Error", "is_negative": False}

@mcp.tool()
def time_since(
    timestamp: str,
    timezone: str = "America/New_York"
) -> Dict[str, Union[int, float, str]]:
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        diff = time_difference(timestamp, now_str, unit="auto", timezone=timezone)
        if "error" in diff: return {"error": diff.get("error", "Error"), "seconds": 0, "formatted": "Error", "context": "unknown"}
        seconds = diff["seconds"]
        abs_seconds = abs(seconds)
        dt = parse_standard_timestamp(timestamp, timezone)
        context = ""
        if seconds < 0: context = "in the future"
        elif abs_seconds < 60: context = "just now"
        elif abs_seconds < 3600: context = "earlier"
        elif abs_seconds < 86400: context = "earlier today" if dt.date() == now.date() else "yesterday"
        elif abs_seconds < 172800: context = "yesterday"
        elif abs_seconds < 604800: context = "this week"
        else: context = "a while ago"
        formatted = diff["formatted"] + (" ago" if seconds >= 0 else " from now")
        return {"seconds": seconds, "formatted": formatted, "context": context}
    except Exception as e:
        return {"error": str(e), "seconds": 0, "formatted": "Error", "context": "unknown"}

@mcp.tool()
def parse_timestamp(
    timestamp: str,
    source_timezone: Optional[str] = None,
    target_timezone: str = "America/New_York"
) -> Dict[str, str]:
    try:
        parse_tz = source_timezone or target_timezone
        dt = parse_standard_timestamp(timestamp, parse_tz)
        if source_timezone and source_timezone != target_timezone:
            dt = dt.astimezone(pytz.timezone(target_timezone))
        return {
            "iso": dt.isoformat(),
            "unix": str(int(dt.timestamp())),
            "human": dt.strftime("%B %d, %Y at %I:%M %p %Z"),
            "timezone": target_timezone,
            "day_of_week": dt.strftime("%A"),
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M:%S")
        }
    except Exception as e:
        return {"error": str(e), "iso": "", "unix": "", "human": "Error"}

@mcp.tool()
def add_time(
    timestamp: str,
    duration: Union[int, float],
    unit: Literal["seconds", "minutes", "hours", "days", "weeks"],
    timezone: str = "America/New_York"
) -> Dict[str, str]:
    try:
        dt = parse_standard_timestamp(timestamp, timezone)
        is_date_only = ":" not in timestamp
        delta = timedelta(**{unit: duration})
        result_dt = dt + delta
        now = datetime.now(pytz.timezone(timezone))
        days_diff = (result_dt.date() - now.date()).days
        if days_diff == 0: day_desc = "today"
        elif days_diff == 1: day_desc = "tomorrow"
        elif days_diff == -1: day_desc = "yesterday"
        else: day_desc = result_dt.strftime("%B %d, %Y")
        time_desc = result_dt.strftime("%I:%M %p").lstrip("0")
        description = f"{day_desc} at {time_desc}" if not is_date_only else day_desc
        result_str = result_dt.strftime("%Y-%m-%d" if is_date_only else "%Y-%m-%d %H:%M:%S")
        return {"result": result_str, "iso": result_dt.isoformat(), "description": description}
    except Exception as e:
        return {"error": str(e), "result": "Error"}

@mcp.tool()
def timestamp_context(
    timestamp: str,
    timezone: str = "America/New_York"
) -> Dict[str, Union[str, bool, int]]:
    try:
        dt = parse_standard_timestamp(timestamp, timezone)
        hour = dt.hour
        if 5 <= hour < 12: time_of_day = "morning"
        elif 12 <= hour < 17: time_of_day = "afternoon"
        elif 17 <= hour < 21: time_of_day = "evening"
        else: time_of_day = "night"
        is_weekend = dt.weekday() >= 5
        is_business_hours = not is_weekend and 9 <= hour < 17
        return {
            "time_of_day": time_of_day,
            "day_of_week": dt.strftime("%A"),
            "is_weekend": is_weekend,
            "is_business_hours": is_business_hours
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def format_duration(
    seconds: Union[int, float],
    style: Literal["full", "compact", "minimal"] = "full"
) -> str:
    try:
        seconds = float(seconds)
        is_negative = seconds < 0
        abs_seconds = abs(seconds)
        days, rem = divmod(abs_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        result = ""
        if style == "full":
            parts = []
            if days > 0: parts.append(f"{int(days)} day{'s' if days != 1 else ''}")
            if hours > 0: parts.append(f"{int(hours)} hour{'s' if hours != 1 else ''}")
            if minutes > 0: parts.append(f"{int(minutes)} minute{'s' if minutes != 1 else ''}")
            if secs > 0 or not parts: parts.append(f"{int(secs)} second{'s' if secs != 1 else ''}")
            result = ", ".join(parts)
        elif style == "compact":
            parts = []
            if days > 0: parts.append(f"{int(days)}d")
            if hours > 0: parts.append(f"{int(hours)}h")
            if minutes > 0: parts.append(f"{int(minutes)}m")
            if secs > 0 or not parts: parts.append(f"{int(secs)}s")
            result = " ".join(parts)
        elif style == "minimal":
            result = f"{int(hours):02}:{int(minutes):02}:{int(secs):02}"
            if days > 0: result = f"{int(days)}:{result}"
        return f"-{result}" if is_negative else result
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    import asyncio
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting MCP server on http://0.0.0.0:{port}")
    if API_KEY:
        print("Authentication is ENABLED. Provide API key in 'X-API-Key' header.")
    else:
        print("WARNING: Authentication is DISABLED. Server is open.")
        
    asyncio.run(
        mcp.run_sse_async(
            host="0.0.0.0",
            port=port,
            log_level="debug"
        )
    )
