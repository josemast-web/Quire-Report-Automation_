import requests
from requests.exceptions import ConnectionError, HTTPError, RequestException, Timeout
import sys
import config
from datetime import datetime, timezone, timedelta
import pandas as pd
import time
import logging
from typing import Dict, List, Optional
import hashlib
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Networking settings ===
# Use separate connect/read timeouts (requests supports passing a tuple).
# You can override these in your environment if Quire is slow or if you need
# tighter limits:
#   QUIRE_CONNECT_TIMEOUT=10
#   QUIRE_READ_TIMEOUT=90
DEFAULT_CONNECT_TIMEOUT = float(os.getenv("QUIRE_CONNECT_TIMEOUT", "10"))
DEFAULT_READ_TIMEOUT = float(os.getenv("QUIRE_READ_TIMEOUT", "90"))


def _timeout():
    """Return (connect_timeout, read_timeout) for requests."""
    return (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)


class RateLimiter:
    """Simple rate limiter to avoid API throttling"""
    
    def __init__(self, calls_per_second: float = 2):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0
    
    def wait_if_needed(self):
        """Wait if necessary to respect rate limit"""
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


class APICache:
    """Simple file-based cache for API responses"""
    
    def __init__(self, cache_dir: str = ".cache", ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_key(self, url: str, params: Optional[Dict] = None) -> str:
        """Generate cache key from URL and params"""
        content = f"{url}|{json.dumps(params, sort_keys=True) if params else ''}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Get cached response if available and not expired"""
        cache_key = self._get_cache_key(url, params)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        if not os.path.exists(cache_file):
            return None
        
        # Check if cache is expired
        file_age = time.time() - os.path.getmtime(cache_file)
        if file_age > self.ttl_seconds:
            logger.info(f"[CACHE EXPIRED] for {url}")
            try:
                os.remove(cache_file)
            except:
                pass
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                logger.info(f"[CACHE HIT] for {url}")
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading cache: {e}")
            return None
    
    def set(self, url: str, data: Dict, params: Optional[Dict] = None):
        """Save response to cache"""
        cache_key = self._get_cache_key(url, params)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            logger.info(f"[CACHED] for {url}")
        except Exception as e:
            logger.error(f"Error writing cache: {e}")
    
    def clear(self):
        """Clear all cache files"""
        try:
            for file in os.listdir(self.cache_dir):
                if file.endswith('.json'):
                    os.remove(os.path.join(self.cache_dir, file))
            logger.info("[CACHE] Cache cleared")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")


def retry_with_backoff(max_retries: int = 3, initial_delay: float = 1.0):
    """
    Decorator for retry logic with exponential backoff
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except RequestException as e:
                    last_exception = e

                    # Decide whether this error is likely transient.
                    retryable = True
                    if isinstance(e, (Timeout, ConnectionError)):
                        retryable = True
                    elif isinstance(e, HTTPError) and getattr(e, "response", None) is not None:
                        status = e.response.status_code
                        # Typical retryable HTTP codes
                        retryable = status in (408, 429) or (500 <= status <= 599)

                    if not retryable:
                        logger.error(f"Non-retryable HTTP error: {e}")
                        raise

                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                    
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                except Exception as e:
                    # Non-network exceptions should not be retried
                    logger.error(f"Non-retryable error: {e}")
                    raise
            
            # All retries failed
            logger.error(f"All {max_retries} attempts failed")
            raise last_exception
        
        return wrapper
    return decorator


class QuireAPI:
    """Optimized Quire API client with retry logic and caching"""
    
    def __init__(self, use_cache: bool = True, cache_ttl: int = 1800):
        self.rate_limiter = RateLimiter(calls_per_second=2)
        self.cache = APICache(ttl_seconds=cache_ttl) if use_cache else None
        self._token = None
        self._token_expires_at = 0
        logger.info(f"QuireAPI initialized (cache={'enabled' if use_cache else 'disabled'})")

    @staticmethod
    def _validate_credentials() -> None:
        """Fail fast with a clear message if required env vars are missing."""
        missing = []
        if not config.CLIENT_ID:
            missing.append("QUIRE_CLIENT_ID")
        if not config.CLIENT_SECRET:
            missing.append("QUIRE_CLIENT_SECRET")
        if not config.REFRESH_TOKEN:
            missing.append("QUIRE_REFRESH_TOKEN")
        if missing:
            raise RuntimeError(
                "Faltan variables de entorno requeridas para Quire: "
                + ", ".join(missing)
            )
    
    def get_access_token(self, force_refresh: bool = False) -> str:
        """Get access token with caching"""
        # Return cached token if still valid
        if not force_refresh and self._token and time.time() < self._token_expires_at:
            logger.debug("Using cached access token")
            return self._token

        # Validate required config early (avoids confusing retries/timeouts later).
        try:
            self._validate_credentials()
        except Exception as e:
            logger.error(str(e))
            sys.exit(1)
        
        url = "https://quire.io/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": config.REFRESH_TOKEN,
            "client_id": config.CLIENT_ID,
            "client_secret": config.CLIENT_SECRET
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        @retry_with_backoff(max_retries=3, initial_delay=1.0)
        def request_token():
            r = requests.post(url, data=payload, headers=headers, timeout=_timeout())
            r.raise_for_status()
            return r.json()
        
        try:
            response = request_token()
            self._token = response['access_token']
            # Prefer the server-provided expiration if present.
            # (Quire often returns a long-lived token when using refresh_token.)
            try:
                expires_in = int(response.get("expires_in", 3600))
            except Exception:
                expires_in = 3600
            # Keep a small safety margin.
            self._token_expires_at = time.time() + max(0, expires_in - 60)
            logger.info("[AUTH] Access token refreshed")
            return self._token
        except Exception as e:
            # Include a more explicit hint when this is a network timeout.
            if isinstance(e, Timeout):
                logger.error(
                    "✗ Error refreshing token: timeout conectando con quire.io. "
                    "Revisa tu red/proxy/firewall o aumenta QUIRE_READ_TIMEOUT. "
                    f"Detalles: {e}"
                )
            else:
                logger.error(f"[ERROR] Error refreshing token: {e}")
            sys.exit(1)
    
    def fetch_projects(self) -> List[Dict]:
        """Fetch all projects with retry and caching"""
        url = "https://quire.io/api/project/list"
        
        # Check cache first
        if self.cache:
            cached = self.cache.get(url)
            if cached:
                return cached
        
        @retry_with_backoff(max_retries=3, initial_delay=1.0)
        def request_projects():
            self.rate_limiter.wait_if_needed()

            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            r = requests.get(url, headers=headers, timeout=_timeout())

            # If token expired earlier than expected, refresh once and retry.
            if r.status_code == 401:
                token = self.get_access_token(force_refresh=True)
                headers = {'Authorization': f'Bearer {token}'}
                r = requests.get(url, headers=headers, timeout=_timeout())

            r.raise_for_status()
            return r.json()
        
        try:
            projects = request_projects()
            logger.info(f"[OK] Fetched {len(projects)} projects from Quire")
            
            # Cache the result
            if self.cache:
                self.cache.set(url, projects)
            
            return projects
        except Exception as e:
            logger.error(f"[ERROR] Error fetching projects: {e}")
            return []
    
    def fetch_tasks_for_project(self, project_oid: str, project_name: str) -> List[Dict]:
        """Fetch tasks for a single project with retry and caching"""
        url = f"https://quire.io/api/task/search/{project_oid}"
        params = {"limit": "no"}
        
        # Check cache
        if self.cache:
            cached = self.cache.get(url, params)
            if cached:
                return cached
        
        @retry_with_backoff(max_retries=3, initial_delay=1.0)
        def request_tasks():
            self.rate_limiter.wait_if_needed()
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            r = requests.get(url, headers=headers, params=params, timeout=_timeout())

            # If token expired earlier than expected, refresh once and retry.
            if r.status_code == 401:
                token = self.get_access_token(force_refresh=True)
                headers = {'Authorization': f'Bearer {token}'}
                r = requests.get(url, headers=headers, params=params, timeout=_timeout())
            
            # 404 means project has no tasks or doesn't exist
            if r.status_code == 404:
                return []
            
            r.raise_for_status()
            return r.json()
        
        try:
            tasks = request_tasks()
            
            if tasks:
                logger.debug(f"  → {project_name}: {len(tasks)} tasks")
            
            # Cache the result
            if self.cache and tasks:
                self.cache.set(url, tasks, params)
            
            return tasks
        except Exception as e:
            logger.warning(f"  Project {project_name}: Error fetching tasks - {e}")
            return []
    
    def process_task_timelogs(self, task: Dict, start_week: datetime, end_week: datetime, start_month: datetime) -> Dict:
        """Process timelogs for a single task"""
        seconds_week = 0
        seconds_month = 0
        total_seconds = 0
        
        timelogs = task.get('timelogs', [])
        
        for tl in timelogs:
            log_start_str = tl.get('start')
            log_end_str = tl.get('end')
            
            if not log_start_str or not log_end_str:
                continue
            
            try:
                log_start_dt = pd.to_datetime(log_start_str)
                log_end_dt = pd.to_datetime(log_end_str)
                duration = (log_end_dt - log_start_dt).total_seconds()
                
                # Skip negative durations (data error)
                if duration < 0:
                    logger.warning(f"Negative duration in task '{task.get('name')}': {duration}s")
                    continue
                
                total_seconds += duration
                
                # Check if timelog falls within the week range
                if start_week <= log_start_dt <= end_week:
                    seconds_week += duration
                
                # Check if timelog falls within the month range
                if log_start_dt >= start_month:
                    seconds_month += duration
                    
            except Exception as e:
                logger.debug(f"Error processing timelog: {e}")
                continue
        
        return {
            'hours_total': round(total_seconds / 3600, 2),
            'hours_week': round(seconds_week / 3600, 2),
            'hours_month': round(seconds_month / 3600, 2)
        }
    
    def fetch_data(self) -> List[Dict]:
        """
        Main method to fetch all data with optimizations
        Returns list of task dictionaries
        """
        logger.info("=" * 70)
        logger.info("Starting data fetch from Quire API")
        logger.info("=" * 70)
        
        start_time = time.time()
        
        # Calculate time ranges
        now = datetime.now(timezone.utc)
        days_to_last_monday = now.weekday() + 7
        start_week = (now - timedelta(days=days_to_last_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_week = start_week + timedelta(days=4, hours=23, minutes=59, seconds=59)
        start_month = now - timedelta(days=30)
        
        logger.info(f"Date ranges:")
        logger.info(f"  Week: {start_week.date()} to {end_week.date()}")
        logger.info(f"  Month: from {start_month.date()}")
        logger.info("-" * 70)
        
        # Fetch projects
        projects = self.fetch_projects()
        if not projects:
            logger.error("No projects found or error fetching projects")
            return []
        
        # Process tasks for each project
        tasks_data = []
        projects_processed = 0
        projects_with_tasks = 0
        
        logger.info(f"Processing {len(projects)} projects...")
        
        for idx, proj in enumerate(projects, 1):
            project_name = proj['name']
            project_oid = proj['oid']
            
            # Fetch tasks for this project
            tasks = self.fetch_tasks_for_project(project_oid, project_name)
            
            if not tasks:
                continue
            
            projects_processed += 1
            projects_with_tasks += 1
            
            # Process each task
            for task in tasks:
                try:
                    # Extract status value
                    status_raw = task.get('status')
                    if isinstance(status_raw, dict):
                        status_value = int(status_raw.get('value', 0))
                    else:
                        status_value = int(status_raw) if status_raw is not None else 0
                    
                    # Process timelogs
                    time_data = self.process_task_timelogs(
                        task, start_week, end_week, start_month
                    )
                    
                    # Extract assignees
                    assignees_list = task.get('assignees', [])
                    assignees_str = ",".join([
                        a.get('name', '') for a in assignees_list
                    ]) if assignees_list else ""
                    
                    # Extract tags
                    tags_list = task.get('tags', [])
                    tags_str = ",".join([
                        t.get('name', '') for t in tags_list
                    ]) if tags_list else ""
                    
                    # Get completion timestamp
                    completed_at = task.get('toggledAt') if status_value >= 100 else None
                    
                    # Build task data dictionary
                    tasks_data.append({
                        "id": task.get('id'),
                        "project_id": project_oid,
                        "name": task.get('name'),
                        "status_value": status_value,
                        "raw_assignees": assignees_str,
                        "raw_tags": tags_str,
                        "project_name": project_name,
                        "completed_at": completed_at,
                        **time_data
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing task in {project_name}: {e}")
                    continue
        
        elapsed_time = time.time() - start_time
        
        # Summary
        logger.info("=" * 70)
        logger.info("[SUMMARY] Data Fetch Summary:")
        logger.info(f"  Total projects in Quire: {len(projects)}")
        logger.info(f"  Projects with tasks: {projects_with_tasks}")
        logger.info(f"  Total tasks collected: {len(tasks_data)}")
        logger.info(f"  Execution time: {elapsed_time:.2f} seconds")
        logger.info("=" * 70)
        
        return tasks_data


# Legacy function for backward compatibility
def get_access_token():
    """Legacy function - creates new API instance"""
    api = QuireAPI(use_cache=False)
    return api.get_access_token()


def fetch_data():
    """
    Legacy function for backward compatibility
    Creates QuireAPI instance with default settings and fetches data
    """
    api = QuireAPI(use_cache=True, cache_ttl=1800)  # 30 minute cache
    return api.fetch_data()
