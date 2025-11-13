from flask import Flask, render_template, request, jsonify, make_response
import requests
import json
from datetime import datetime, timedelta
import pytz
import logging
import re
from functools import wraps
from cachetools import TTLCache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.static_folder = 'static'

# Security: Secret key for session management (use environment variable in production)
import os
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32))

# Rate limiting to prevent DDoS attacks
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

# Cache for API responses to reduce external requests
api_cache = TTLCache(maxsize=1000, ttl=300)  # 5 minute TTL

# Security: Input validation patterns
VALID_SPORT_PATTERN = re.compile(r'^[a-zA-Z\s]+$')
VALID_TEAM_PATTERN = re.compile(r'^[a-zA-Z0-9\s\'\.\-&]+$')

# Security headers middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' https://a.espncdn.com data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response

def sanitize_input(value, pattern, max_length=100):
    """Sanitize and validate input strings"""
    if not value:
        return None

    # Remove leading/trailing whitespace
    value = value.strip()

    # Check length
    if len(value) > max_length:
        logger.warning(f"Input too long: {len(value)} characters")
        return None

    # Check pattern
    if not pattern.match(value):
        logger.warning(f"Input failed pattern validation: {value}")
        return None

    return value

def get_cache_key(prefix, *args):
    """Generate cache key from prefix and arguments"""
    return f"{prefix}:{':'.join(str(arg) for arg in args)}"

class SportsAPI:
    def __init__(self):
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports"
        self.request_timeout = 5  # Security: Enforce timeout
        self.max_retries = 2  # Security: Limit retries

    def _make_api_request(self, url, timeout=None):
        """Make API request with caching and security controls"""
        cache_key = get_cache_key('api', url)

        # Check cache first
        if cache_key in api_cache:
            logger.debug(f"Cache hit for {url}")
            return api_cache[cache_key]

        # Make request with timeout and retry logic
        timeout = timeout or self.request_timeout
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url,
                    timeout=timeout,
                    headers={'User-Agent': 'CheckBall/1.0'}  # Identify our requests
                )
                response.raise_for_status()
                data = response.json()

                # Cache successful response
                api_cache[cache_key] = data
                return data

            except requests.Timeout:
                logger.warning(f"Request timeout for {url} (attempt {attempt + 1})")
                if attempt == self.max_retries - 1:
                    raise
            except requests.RequestException as e:
                logger.error(f"Request error for {url}: {e}")
                if attempt == self.max_retries - 1:
                    raise

        return None

    def get_scores(self, sport, team_name):
        """Get scores for a specific sport and team with primary and secondary game info"""
        try:
            # Get base URL for the sport
            if sport.lower() == 'nba':
                base_url = f"{self.base_url}/basketball/nba"
            elif sport.lower() == 'wnba':
                base_url = f"{self.base_url}/basketball/wnba"
            elif sport.lower() == 'nfl':
                base_url = f"{self.base_url}/football/nfl"
            elif sport.lower() == 'mls':
                base_url = f"{self.base_url}/soccer/usa.1"
            elif sport.lower() == 'premier league':
                base_url = f"{self.base_url}/soccer/eng.1"
            elif sport.lower() == 'la liga':
                base_url = f"{self.base_url}/soccer/esp.1"
            elif sport.lower() == 'mlb':
                base_url = f"{self.base_url}/baseball/mlb"
            elif sport.lower() == 'nhl':
                base_url = f"{self.base_url}/hockey/nhl"
            else:
                return {'error': 'Sport not supported'}
            
            # Get current time in EST/EDT
            eastern = pytz.timezone('US/Eastern')
            now = datetime.now(eastern)
            
            team_games = []
            
            # Fetch 5 days of games for better coverage (yesterday, today, next 3 days)
            for days_offset in [-1, 0, 1, 2, 3]:
                date = now + timedelta(days=days_offset)
                date_str = date.strftime('%Y%m%d')
                url = f"{base_url}/scoreboard?dates={date_str}"
                
                try:
                    data = self._make_api_request(url, timeout=3)
                    
                    # Find games involving the specified team
                    for game in data.get('events', []):
                        competitors = game.get('competitions', [{}])[0].get('competitors', [])
                        
                        for team in competitors:
                            team_display_name = team.get('team', {}).get('displayName', '')
                            if self._team_name_matches(team_name, team_display_name):
                                opponent = self._get_opponent(competitors, team)
                                
                                # Parse game date with better timezone handling
                                try:
                                    game_date_str = game.get('date', '')
                                    if game_date_str:
                                        # Handle different date formats from ESPN API
                                        if game_date_str.endswith('Z'):
                                            game_date = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
                                        elif '+' not in game_date_str and 'T' in game_date_str:
                                            # Assume UTC if no timezone info
                                            game_date = datetime.fromisoformat(game_date_str + '+00:00')
                                        else:
                                            game_date = datetime.fromisoformat(game_date_str)
                                        
                                        # Convert to Eastern Time
                                        game_date_eastern = game_date.astimezone(eastern)
                                        
                                        # Debug logging
                                        logger.debug(f"Original date: {game_date_str}")
                                        logger.debug(f"Parsed UTC: {game_date}")
                                        logger.debug(f"Eastern Time: {game_date_eastern}")
                                        logger.debug(f"Current Eastern: {now}")
                                    else:
                                        continue
                                except Exception as e:
                                    logger.warning(f"Date parsing error: {e}")
                                    continue
                                
                                # Get status information
                                status_info = game.get('status', {})
                                status_detail = status_info.get('type', {}).get('detail', 'Scheduled')
                                status_name = status_info.get('type', {}).get('name', 'STATUS_SCHEDULED')
                                
                                # Get venue information
                                venue = game.get('competitions', [{}])[0].get('venue', {}).get('fullName', '')
                                
                                # Handle scores properly - only show for completed/in-progress games
                                if status_name in ['STATUS_FINAL', 'STATUS_FINAL_OT', 'STATUS_IN_PROGRESS', 'STATUS_HALFTIME']:
                                    team_score = team.get('score', '0')
                                    opponent_score = opponent['score']
                                else:
                                    team_score = '-'
                                    opponent_score = '-'
                                
                                game_info = {
                                    'team': team_display_name,
                                    'team_score': team_score,
                                    'opponent': opponent['name'],
                                    'opponent_score': opponent_score,
                                    'status': status_detail,
                                    'status_type': status_name,
                                    'game_date': game_date_eastern,
                                    'game_date_iso': game_date_eastern.isoformat(),
                                    'last_updated': datetime.now().strftime('%H:%M'),
                                    'venue': venue if venue else 'TBD'
                                }
                                team_games.append(game_info)
                                break
                except (requests.RequestException, ValueError, KeyError) as e:
                    logger.warning(f"Error fetching game data for date {date_str}: {e}")
                    continue
            
            if not team_games:
                return {
                    'team': team_name,
                    'team_score': '-',
                    'opponent': 'No games found',
                    'opponent_score': '-',
                    'status': 'No upcoming games',
                    'last_updated': datetime.now().strftime('%H:%M'),
                    'venue': '-',
                    'next_game': None
                }
            
            # Select primary and secondary games
            primary_game, next_game = self._select_primary_and_next_games(team_games, now)
            
            # Add next game info to primary game response
            if next_game:
                primary_game['next_game'] = {
                    'opponent': next_game['opponent'],
                    'game_date': next_game['game_date_iso'],
                    'venue': next_game['venue']
                }
            else:
                primary_game['next_game'] = None
                
            return primary_game
            
        except Exception as e:
            return {'error': f'Failed to fetch data: {str(e)}'}
    
    def _select_primary_and_next_games(self, games, current_time):
        """Select primary game to display and next upcoming game"""
        today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        # Categorize games more precisely
        completed_games = [g for g in games if g['status_type'] in ['STATUS_FINAL', 'STATUS_FINAL_OT']]
        in_progress_games = [g for g in games if g['status_type'] in ['STATUS_IN_PROGRESS', 'STATUS_HALFTIME']]
        upcoming_games = [g for g in games if g['status_type'] == 'STATUS_SCHEDULED']
        
        # Sort games appropriately
        if completed_games:
            completed_games.sort(key=lambda x: x['game_date'], reverse=True)
        if upcoming_games:
            upcoming_games.sort(key=lambda x: x['game_date'])
        
        primary_game = None
        next_game = None
        
        # Priority 1: In-progress games (live games take absolute priority)
        if in_progress_games:
            primary_game = in_progress_games[0]
            if upcoming_games:
                next_game = upcoming_games[0]
        
        # Priority 2: Today's completed games
        elif completed_games:
            todays_completed = [g for g in completed_games if today_start <= g['game_date'] < today_end]
            if todays_completed:
                primary_game = todays_completed[0]
                if upcoming_games:
                    next_game = upcoming_games[0]
            else:
                # Most recent completed game (yesterday or earlier)
                primary_game = completed_games[0]
                if upcoming_games:
                    next_game = upcoming_games[0]
        
        # Priority 3: Only if no completed/in-progress games exist, show upcoming
        elif upcoming_games:
            primary_game = upcoming_games[0]
            if len(upcoming_games) > 1:
                next_game = upcoming_games[1]
        
        # Fallback
        if not primary_game and games:
            games.sort(key=lambda x: x['game_date'], reverse=True)
            primary_game = games[0]
        
        return primary_game, next_game

    def _normalize_team_name(self, team_name):
        """Normalize team names for better matching"""
        # Common team name variations and their standard forms
        team_mappings = {
            # MLB teams
            'athletics': 'oakland athletics',
            'a\'s': 'oakland athletics',
            'oakland a\'s': 'oakland athletics',
            'dodgers': 'los angeles dodgers',
            'angels': 'los angeles angels',
            'yankees': 'new york yankees',
            'mets': 'new york mets',
            'red sox': 'boston red sox',
            'white sox': 'chicago white sox',
            'blue jays': 'toronto blue jays',
            'guardians': 'cleveland guardians',
            'diamondbacks': 'arizona diamondbacks',
            'rays': 'tampa bay rays',
            # WNBA teams
            'liberty': 'new york liberty',
            'aces': 'las vegas aces',
            'sky': 'chicago sky',
            'sun': 'connecticut sun',
            'storm': 'seattle storm',
            'lynx': 'minnesota lynx',
            'sparks': 'los angeles sparks',
            'mercury': 'phoenix mercury',
            'mystics': 'washington mystics',
            'fever': 'indiana fever',
            'wings': 'dallas wings',
            'dream': 'atlanta dream',
            # La Liga teams
            'barcelona': 'barcelona',
            'barca': 'barcelona',
            'real madrid': 'real madrid',
            'madrid': 'real madrid',
            'atletico madrid': 'atlético madrid',
            'atletico': 'atlético madrid',
            'athletic bilbao': 'athletic bilbao',
            'athletic': 'athletic bilbao',
            'real sociedad': 'real sociedad',
            'sociedad': 'real sociedad',
            'valencia': 'valencia',
            'sevilla': 'sevilla',
            'villarreal': 'villarreal',
            'betis': 'real betis',
            'real betis': 'real betis'
        }
        
        normalized = team_name.lower().strip()
        return team_mappings.get(normalized, normalized)
    
    def _team_name_matches(self, search_name, api_name):
        """Check if team names match using flexible matching"""
        search_normalized = self._normalize_team_name(search_name)
        api_normalized = self._normalize_team_name(api_name)
        
        # Direct match
        if search_normalized == api_normalized:
            return True
        
        # Check if search name is contained in API name
        if search_normalized in api_normalized:
            return True
        
        # Check if API name is contained in search name
        if api_normalized in search_normalized:
            return True
        
        # Check individual words (for cases like "Athletics" matching "Oakland Athletics")
        search_words = set(search_normalized.split())
        api_words = set(api_normalized.split())
        
        # If any significant word matches (excluding common words)
        common_words = {'the', 'of', 'and', 'fc', 'united', 'city'}
        search_words_filtered = search_words - common_words
        api_words_filtered = api_words - common_words
        
        if search_words_filtered and api_words_filtered:
            if search_words_filtered.intersection(api_words_filtered):
                return True

        return False

    def _get_opponent(self, competitors, current_team):
        """Get the opponent team info"""
        for team in competitors:
            if team['id'] != current_team['id']:
                return {
                    'name': team['team']['displayName'],
                    'score': team.get('score', '0')
                }
        return {'name': 'Unknown', 'score': '0'}
    
    def get_teams_by_sport(self, sport):
        """Get comprehensive list of teams for each sport"""
        teams = {
            'nba': [
                'Atlanta Hawks', 'Boston Celtics', 'Brooklyn Nets', 'Charlotte Hornets',
                'Chicago Bulls', 'Cleveland Cavaliers', 'Dallas Mavericks', 'Denver Nuggets',
                'Detroit Pistons', 'Golden State Warriors', 'Houston Rockets', 'Indiana Pacers',
                'LA Clippers', 'Los Angeles Lakers', 'Memphis Grizzlies', 'Miami Heat',
                'Milwaukee Bucks', 'Minnesota Timberwolves', 'New Orleans Pelicans', 'New York Knicks',
                'Oklahoma City Thunder', 'Orlando Magic', 'Philadelphia 76ers', 'Phoenix Suns',
                'Portland Trail Blazers', 'Sacramento Kings', 'San Antonio Spurs', 'Toronto Raptors',
                'Utah Jazz', 'Washington Wizards'
            ],
            'wnba': [
                'Atlanta Dream', 'Chicago Sky', 'Connecticut Sun', 'Dallas Wings',
                'Indiana Fever', 'Las Vegas Aces', 'Los Angeles Sparks', 'Minnesota Lynx',
                'New York Liberty', 'Phoenix Mercury', 'Seattle Storm', 'Washington Mystics'
            ],
            'nfl': [
                'Arizona Cardinals', 'Atlanta Falcons', 'Baltimore Ravens', 'Buffalo Bills',
                'Carolina Panthers', 'Chicago Bears', 'Cincinnati Bengals', 'Cleveland Browns',
                'Dallas Cowboys', 'Denver Broncos', 'Detroit Lions', 'Green Bay Packers',
                'Houston Texans', 'Indianapolis Colts', 'Jacksonville Jaguars', 'Kansas City Chiefs',
                'Las Vegas Raiders', 'Los Angeles Chargers', 'Los Angeles Rams', 'Miami Dolphins',
                'Minnesota Vikings', 'New England Patriots', 'New Orleans Saints', 'New York Giants',
                'New York Jets', 'Philadelphia Eagles', 'Pittsburgh Steelers', 'San Francisco 49ers',
                'Seattle Seahawks', 'Tampa Bay Buccaneers', 'Tennessee Titans', 'Washington Commanders'
            ],
            'mls': [
                'Atlanta United FC', 'Austin FC', 'CF Montréal', 'Charlotte FC',
                'Chicago Fire FC', 'Colorado Rapids', 'Columbus Crew', 'D.C. United',
                'FC Cincinnati', 'FC Dallas', 'Houston Dynamo FC', 'Inter Miami CF',
                'LA Galaxy', 'Los Angeles FC', 'Minnesota United FC', 'Nashville SC',
                'New England Revolution', 'New York City FC', 'New York Red Bulls', 'Orlando City SC',
                'Philadelphia Union', 'Portland Timbers', 'Real Salt Lake', 'San Jose Earthquakes',
                'Seattle Sounders FC', 'Sporting Kansas City', 'St. Louis City SC', 'Toronto FC',
                'Vancouver Whitecaps FC'
            ],
            'premier league': [
                'Arsenal', 'Aston Villa', 'Bournemouth', 'Brentford', 'Brighton & Hove Albion',
                'Chelsea', 'Crystal Palace', 'Everton', 'Fulham', 'Ipswich Town',
                'Leicester City', 'Liverpool', 'Manchester City', 'Manchester United',
                'Newcastle United', 'Nottingham Forest', 'Southampton', 'Tottenham Hotspur',
                'West Ham United', 'Wolverhampton Wanderers'
            ],
            'la liga': [
                'Athletic Bilbao', 'Atlético Madrid', 'Barcelona', 'Celta Vigo', 'Deportivo Alavés',
                'Espanyol', 'Getafe', 'Girona', 'Las Palmas', 'Leganés', 'Mallorca', 'Osasuna',
                'Rayo Vallecano', 'Real Betis', 'Real Madrid', 'Real Sociedad', 'Sevilla',
                'Valencia', 'Valladolid', 'Villarreal'
            ],
            'mlb': [
                'Arizona Diamondbacks', 'Atlanta Braves', 'Baltimore Orioles', 'Boston Red Sox',
                'Chicago Cubs', 'Chicago White Sox', 'Cincinnati Reds', 'Cleveland Guardians',
                'Colorado Rockies', 'Detroit Tigers', 'Houston Astros', 'Kansas City Royals',
                'Los Angeles Angels', 'Los Angeles Dodgers', 'Miami Marlins', 'Milwaukee Brewers',
                'Minnesota Twins', 'New York Mets', 'New York Yankees', 'Oakland Athletics',
                'Philadelphia Phillies', 'Pittsburgh Pirates', 'San Diego Padres', 'San Francisco Giants',
                'Seattle Mariners', 'St. Louis Cardinals', 'Tampa Bay Rays', 'Texas Rangers',
                'Toronto Blue Jays', 'Washington Nationals'
            ],
            'nhl': [
                'Anaheim Ducks', 'Arizona Coyotes', 'Boston Bruins', 'Buffalo Sabres',
                'Calgary Flames', 'Carolina Hurricanes', 'Chicago Blackhawks', 'Colorado Avalanche',
                'Columbus Blue Jackets', 'Dallas Stars', 'Detroit Red Wings', 'Edmonton Oilers',
                'Florida Panthers', 'Los Angeles Kings', 'Minnesota Wild', 'Montréal Canadiens',
                'Nashville Predators', 'New Jersey Devils', 'New York Islanders', 'New York Rangers',
                'Ottawa Senators', 'Philadelphia Flyers', 'Pittsburgh Penguins', 'San Jose Sharks',
                'Seattle Kraken', 'St. Louis Blues', 'Tampa Bay Lightning', 'Toronto Maple Leafs',
                'Utah Hockey Club', 'Vancouver Canucks', 'Vegas Golden Knights', 'Washington Capitals',
                'Winnipeg Jets'
            ]
        }
        return teams.get(sport.lower(), [])

    def get_detailed_game_data(self, sport, team_name, game_id=None):
        """Get detailed game data including box scores, player stats, and game details"""
        try:
            # Get base URL for the sport
            if sport.lower() == 'nba':
                base_url = f"{self.base_url}/basketball/nba"
            elif sport.lower() == 'wnba':
                base_url = f"{self.base_url}/basketball/wnba"
            elif sport.lower() == 'nfl':
                base_url = f"{self.base_url}/football/nfl"
            elif sport.lower() == 'mls':
                base_url = f"{self.base_url}/soccer/usa.1"
            elif sport.lower() == 'premier league':
                base_url = f"{self.base_url}/soccer/eng.1"
            elif sport.lower() == 'la liga':
                base_url = f"{self.base_url}/soccer/esp.1"
            elif sport.lower() == 'mlb':
                base_url = f"{self.base_url}/baseball/mlb"
            elif sport.lower() == 'nhl':
                base_url = f"{self.base_url}/hockey/nhl"
            else:
                return {'error': 'Sport not supported'}

            # Find the game first
            game_info = self._find_team_game(sport, team_name, base_url)
            if not game_info or 'error' in game_info:
                return game_info

            # Get detailed game data using the game ID
            detailed_url = f"{base_url}/summary?event={game_info['game_id']}"
        
            try:
                data = self._make_api_request(detailed_url, timeout=5)
                if not data:
                    return {'error': 'Failed to fetch detailed data'}
            
                # Parse the detailed game data
                return self._parse_detailed_game_data(data, sport, game_info)
            
            except requests.exceptions.RequestException as e:
                return {'error': f'Network error: {str(e)}'}
            
        except Exception as e:
            return {'error': f'Failed to fetch detailed data: {str(e)}'}

    def _find_team_game(self, sport, team_name, base_url):
        """Find the most relevant game for a team"""
        try:
            # Get current time in EST/EDT
            eastern = pytz.timezone('US/Eastern')
            now = datetime.now(eastern)
        
            # Search last 3 days and next 3 days for games
            for days_offset in [-2, -1, 0, 1, 2]:
                date = now + timedelta(days=days_offset)
                date_str = date.strftime('%Y%m%d')
                url = f"{base_url}/scoreboard?dates={date_str}"
            
                try:
                    data = self._make_api_request(url, timeout=3)
                
                    # Find the team's game
                    for game in data.get('events', []):
                        competitors = game.get('competitions', [{}])[0].get('competitors', [])
                    
                        for team in competitors:
                            team_display_name = team.get('team', {}).get('displayName', '')
                            if self._team_name_matches(team_name, team_display_name):
                                return {
                                    'game_id': game.get('id'),
                                    'game': game,
                                    'team_data': team,
                                    'competitors': competitors
                                }
                except (requests.RequestException, ValueError, KeyError) as e:
                    logger.warning(f"Error finding game for {team_name} on {date_str}: {e}")
                    continue

            return {'error': 'No recent games found'}
        
        except Exception as e:
            return {'error': f'Error finding game: {str(e)}'}

    def _parse_detailed_game_data(self, data, sport, game_info):
        """Parse ESPN detailed game data into our format"""
        try:
            game_data = {}
        
            # Basic game information
            header = data.get('header', {})
            competition = header.get('competitions', [{}])[0]
        
            # Teams and scores
            competitors = competition.get('competitors', [])
            home_team = next((team for team in competitors if team.get('homeAway') == 'home'), {})
            away_team = next((team for team in competitors if team.get('homeAway') == 'away'), {})
        
            game_data['home_team'] = {
                'name': home_team.get('team', {}).get('displayName', 'Unknown'),
                'short_name': home_team.get('team', {}).get('abbreviation', ''),
                'score': home_team.get('score', '0'),
                'logo': home_team.get('team', {}).get('logo', '')
            }
        
            game_data['away_team'] = {
                'name': away_team.get('team', {}).get('displayName', 'Unknown'),
                'short_name': away_team.get('team', {}).get('abbreviation', ''),
                'score': away_team.get('score', '0'),
                'logo': away_team.get('team', {}).get('logo', '')
            }
        
            # Game status and details
            status = competition.get('status', {})
            game_data['status'] = {
                'display': status.get('type', {}).get('detail', 'Unknown'),
                'state': status.get('type', {}).get('name', 'STATUS_SCHEDULED'),
                'period': status.get('period', 0),
                'clock': status.get('displayClock', ''),
                'completed': status.get('type', {}).get('completed', False)
            }
        
            # Venue and date
            venue = competition.get('venue', {})
            game_data['venue'] = {
                'name': venue.get('fullName', 'TBD'),
                'city': venue.get('address', {}).get('city', ''),
                'state': venue.get('address', {}).get('state', '')
            }
        
            game_data['date'] = header.get('competitions', [{}])[0].get('date', '')
        
            # Box score data
            box_score = data.get('boxscore', {})
            if box_score:
                game_data['box_score'] = self._parse_box_score(box_score, sport)
        
            # Team statistics
            game_data['team_stats'] = self._parse_team_stats(data, sport)
        
            # Leaders/key players
            game_data['leaders'] = self._parse_game_leaders(data, sport)
        
            # Scoring summary (for applicable sports)
            game_data['scoring_summary'] = self._parse_scoring_summary(data, sport)
        
            return game_data
        
        except Exception as e:
            return {'error': f'Error parsing game data: {str(e)}'}

    def _parse_box_score(self, box_score, sport):
        """Parse box score data based on sport"""
        try:
            teams = box_score.get('teams', [])
            parsed_box_score = []
        
            for team_data in teams:
                team_info = {
                    'team_name': team_data.get('team', {}).get('displayName', 'Unknown'),
                    'team_abbr': team_data.get('team', {}).get('abbreviation', ''),
                    'statistics': []
                }
            
                # Parse statistics based on sport
                stats = team_data.get('statistics', [])
                for stat in stats:
                    team_info['statistics'].append({
                        'name': stat.get('name', ''),
                        'display_name': stat.get('displayName', ''),
                        'value': stat.get('displayValue', '0')
                    })
            
                parsed_box_score.append(team_info)
            
            return parsed_box_score
        
        except Exception as e:
            return []

    def _parse_team_stats(self, data, sport):
        """Parse team comparison statistics"""
        try:
            team_stats = {}
        
            # Look for team stats in various locations in ESPN response
            if 'boxscore' in data:
                teams = data['boxscore'].get('teams', [])
                for team in teams:
                    team_name = team.get('team', {}).get('displayName', '')
                    stats = {}
                
                    for stat in team.get('statistics', []):
                        stat_name = stat.get('displayName', stat.get('name', ''))
                        stat_value = stat.get('displayValue', '0')
                        stats[stat_name] = stat_value
                    
                    team_stats[team_name] = stats
        
            return team_stats
        
        except Exception as e:
            return {}
    
    # Also update the main _parse_game_leaders method to ensure MLB gets priority
    def _parse_game_leaders(self, data, sport):
        """Parse game leaders with enhanced debugging and multiple fallback strategies"""
        logger.debug(f"=== PARSING GAME LEADERS FOR SPORT: {sport} ===")
        try:
            leaders = {}

            logger.debug(f"Raw data keys: {list(data.keys())}")
            
            # For MLB, try boxscore strategy FIRST and ONLY
            if sport.lower() == 'mlb':
                logger.debug("MLB detected - trying boxscore strategy only")
                if 'boxscore' in data and 'players' in data['boxscore']:
                    logger.debug("Found boxscore with players data")
                    leaders = self._extract_leaders_from_boxscore(data['boxscore'], sport)
                    if leaders:
                        logger.info(f"SUCCESS: Found {len(leaders)} MLB categories from boxscore")
                        return leaders
                    else:
                        logger.debug("Boxscore extraction returned empty for MLB")
                else:
                    logger.debug("No boxscore/players data found for MLB")

                # If no boxscore data, return empty rather than falling back to basketball stats
                logger.debug("No MLB leaders found - returning empty rather than basketball fallback")
                return {}
            
            # For other sports, use the original strategy fallback system
            # Strategy 1: Parse from main leaders array
            if 'leaders' in data and isinstance(data['leaders'], list) and len(data['leaders']) > 0:
                logger.debug("Strategy 1: Main leaders array")
                leaders = self._parse_leaders_from_main_array(data['leaders'])
                if leaders:
                    logger.info(f"SUCCESS: Found {len(leaders)} categories from main array")
                    return leaders

            # Strategy 2: Parse from boxscore players
            if 'boxscore' in data and 'players' in data['boxscore']:
                logger.debug("Strategy 2: Boxscore players")
                leaders = self._extract_leaders_from_boxscore(data['boxscore'], sport)
                if leaders:
                    logger.info(f"SUCCESS: Found {len(leaders)} categories from boxscore")
                    return leaders

            # Strategy 3: Parse from any nested leaders in boxscore
            if 'boxscore' in data:
                logger.debug("Strategy 3: Boxscore nested leaders")
                leaders = self._extract_leaders_from_boxscore_nested(data['boxscore'])
                if leaders:
                    logger.info(f"SUCCESS: Found {len(leaders)} categories from nested boxscore")
                    return leaders

            # Strategy 4: Create basic team scoring from header
            if 'header' in data:
                logger.debug("Strategy 4: Header fallback")
                leaders = self._extract_leaders_from_header(data['header'])
                if leaders:
                    logger.info(f"SUCCESS: Found {len(leaders)} categories from header")
                    return leaders

            logger.warning("ALL STRATEGIES FAILED for game leaders parsing")
            return {}

        except Exception as e:
            logger.error(f"Error in _parse_game_leaders: {str(e)}", exc_info=True)
            return {}
    def _parse_leaders_from_main_array(self, leaders_data):
        """Parse leaders from the main ESPN leaders array"""
        try:
            leaders = {}
            logger.debug(f"Processing {len(leaders_data)} team entries")
            
            for team_index, team_data in enumerate(leaders_data):
                if not isinstance(team_data, dict):
                    logger.debug(f"  Team {team_index}: Not a dict, skipping")
                    continue
                
                # Get team info
                team_info = team_data.get('team', {})
                team_name = (
                    team_info.get('abbreviation') or 
                    team_info.get('shortDisplayName') or 
                    team_info.get('displayName') or 
                    f'Team {team_index + 1}'
                )
                
                logger.debug(f"  Team {team_index}: {team_name}")
                logger.debug(f"    Team data keys: {list(team_data.keys())}")
                
                # Get the leaders for this team
                team_leaders = team_data.get('leaders', [])
                logger.debug(f"    Found {len(team_leaders)} stat categories")
                
                # Process each stat category for this team
                for stat_index, stat_category in enumerate(team_leaders):
                    if not isinstance(stat_category, dict):
                        continue
                    
                    # Get category name
                    category_name = (
                        stat_category.get('displayName') or 
                        stat_category.get('name') or 
                        f'Category {stat_index}'
                    )
                    
                    logger.debug(f"      Category {stat_index}: {category_name}")
                    logger.debug(f"        Category keys: {list(stat_category.keys())}")
                    
                    # Initialize category if not exists
                    if category_name not in leaders:
                        leaders[category_name] = []
                    
                    # Get the actual player leaders for this category
                    category_leaders = stat_category.get('leaders', [])
                    logger.debug(f"        Found {len(category_leaders)} players")
                    
                    for player_index, player_data in enumerate(category_leaders):
                        if not isinstance(player_data, dict):
                            continue
                        
                        logger.debug(f"          Player {player_index} keys: {list(player_data.keys())}")
                        
                        # Extract player info - be more flexible
                        athlete = player_data.get('athlete', {})
                        
                        # Try multiple fields for player name
                        player_name = (
                            athlete.get('displayName') or 
                            athlete.get('fullName') or
                            athlete.get('name') or
                            athlete.get('lastName') or
                            player_data.get('displayName') or
                            player_data.get('name') or
                            'Unknown Player'
                        )
                        
                        # Try multiple fields for stat value
                        stat_value = (
                            player_data.get('displayValue') or
                            player_data.get('value') or
                            player_data.get('statValue') or
                            '0'
                        )
                        
                        logger.debug(f"          Player: {player_name}, Value: {stat_value}, Team: {team_name}")
                        
                        # More lenient validation - accept any non-zero value
                        if (player_name and player_name not in ['Unknown Player', ''] and 
                            stat_value and str(stat_value) not in ['0', '', 'N/A', '--']):
                            
                            leaders[category_name].append({
                                'name': str(player_name),
                                'value': str(stat_value),
                                'team': str(team_name)
                            })
                            logger.debug(f"            ✓ Added to {category_name}")
                        else:
                            logger.debug(f"            ✗ Skipped - Name: '{player_name}', Value: '{stat_value}'")
            
            # Remove empty categories
            leaders = {k: v for k, v in leaders.items() if v}
            
            logger.debug(f"\n  MAIN ARRAY RESULT: {len(leaders)} categories with data")
            for category, category_leaders in leaders.items():
                logger.debug(f"    {category}: {len(category_leaders)} leaders")
            
            return leaders
            
        except Exception as e:
            logger.error(f"Error in _parse_leaders_from_main_array: {str(e)}")
            return {}
    
    def _extract_leaders_from_boxscore_nested(self, boxscore):
        """Look for leaders data nested within boxscore structure"""
        try:
            logger.debug("Searching for nested leaders in boxscore...")
            leaders = {}
            
            # Check if there are leaders nested in the boxscore
            if 'leaders' in boxscore:
                logger.debug("Found leaders in boxscore root")
                return self._parse_leaders_from_main_array(boxscore['leaders'])
            
            # Check in teams data
            teams = boxscore.get('teams', [])
            for team_data in teams:
                if 'leaders' in team_data:
                    logger.debug("Found leaders in team data")
                    team_leaders = self._parse_leaders_from_main_array([team_data])
                    leaders.update(team_leaders)
            
            return leaders
            
        except Exception as e:
            logger.error(f"Error in _extract_leaders_from_boxscore_nested: {str(e)}")
            return {}
    
    def _extract_leaders_from_boxscore(self, boxscore, sport):
        """Extract game leaders from boxscore player statistics - sport aware"""
        try:
            logger.debug(f"=== EXTRACTING LEADERS FOR SPORT: {sport} ===")
            leaders = {}
            
            # Check for players data in boxscore
            players = boxscore.get('players', [])
            logger.debug(f"Found {len(players)} player groups in boxscore")
            
            if not players:
                logger.debug("No players data found in boxscore")
                return {}
            
            # Log the structure of players data for debugging
            if len(players) > 0:
                logger.debug(f"First team structure: {list(players[0].keys())}")
                if 'statistics' in players[0]:
                    stats = players[0].get('statistics', [])
                    logger.debug(f"Statistics structure: {len(stats)} groups")
                    for i, stat_group in enumerate(stats):
                        group_name = stat_group.get('name', f'Group {i}')
                        logger.debug(f"  Group {i}: '{group_name}' with {len(stat_group.get('athletes', []))} athletes")
            
            # Sport-specific stat processing with enhanced debugging
            logger.debug(f"Processing sport: '{sport.lower()}'")
            
            if sport.lower() == 'mlb':
                logger.debug(">>> Calling _extract_mlb_leaders")
                result = self._extract_mlb_leaders(players)
                logger.debug(f">>> MLB leaders result: {list(result.keys()) if result else 'EMPTY'}")
                return result
            elif sport.lower() in ['nba', 'wnba']:
                logger.debug(">>> Calling _extract_basketball_leaders")
                return self._extract_basketball_leaders(players)
            elif sport.lower() == 'nfl':
                logger.debug(">>> Calling _extract_football_leaders")
                return self._extract_football_leaders(players)
            elif sport.lower() in ['mls', 'premier league', 'la liga']:
                logger.debug(">>> Calling _extract_soccer_leaders")
                return self._extract_soccer_leaders(players)
            elif sport.lower() == 'nhl':
                logger.debug(">>> Calling _extract_hockey_leaders")
                return self._extract_hockey_leaders(players)
            else:
                logger.debug(">>> Calling _extract_generic_leaders (fallback)")
                return self._extract_generic_leaders(players)
                
        except Exception as e:
            logger.error(f"Error extracting leaders from boxscore: {str(e)}", exc_info=True)
            return {}
    
    def _extract_mlb_leaders(self, players):
        """Extract MLB-specific game leaders with enhanced debugging"""
        try:
            logger.debug("=== INSIDE _extract_mlb_leaders ===")
            leaders = {}
            all_players = []
            
            # Collect all players with their stats
            for team_index, team_data in enumerate(players):
                team_name = team_data.get('team', {}).get('abbreviation', 'UNK')
                logger.debug(f"Processing team {team_index}: {team_name}")
                
                statistics = team_data.get('statistics', [])
                if not isinstance(statistics, list):
                    logger.debug(f"  No statistics list found for {team_name}")
                    continue
                
                logger.debug(f"  Found {len(statistics)} stat groups for {team_name}")
                
                for group_index, position_group in enumerate(statistics):
                    if not isinstance(position_group, dict):
                        continue
                    
                    # Get position group label to understand context
                    group_name = position_group.get('name', f'Group {group_index}')
                    athletes = position_group.get('athletes', [])
                    logger.debug(f"    Group {group_index}: '{group_name}' with {len(athletes)} athletes")
                    
                    for athlete_index, athlete in enumerate(athletes):
                        if not isinstance(athlete, dict):
                            continue
                        
                        stats = athlete.get('stats', [])
                        athlete_info = athlete.get('athlete', {})
                        player_name = athlete_info.get('displayName', f'Player {athlete_index}')
                        
                        if not isinstance(stats, list) or len(stats) == 0:
                            logger.debug(f"      {player_name}: No stats")
                            continue
                        
                        logger.debug(f"      {player_name}: {len(stats)} stats - {stats[:5]}...")  # Show first 5 stats
                        
                        player_data = {
                            'name': player_name,
                            'team': team_name,
                            'position_group': group_name,
                            'stats': stats
                        }
                        all_players.append(player_data)
            
            logger.debug(f"Total players collected: {len(all_players)}")
            
            # Define MLB stat mappings with more flexible position group matching
            mlb_categories = {
                'Hits': self._find_mlb_stat_leaders(all_players, ['batting', 'hitters', 'offense'], [0, 1, 2, 3, 4]),
                'RBIs': self._find_mlb_stat_leaders(all_players, ['batting', 'hitters', 'offense'], [1, 2, 3, 4, 5]),
                'Home Runs': self._find_mlb_stat_leaders(all_players, ['batting', 'hitters', 'offense'], [2, 3, 4, 5, 6]),
                'Runs Scored': self._find_mlb_stat_leaders(all_players, ['batting', 'hitters', 'offense'], [3, 4, 5, 6, 7]),
                'Strikeouts (Pitching)': self._find_mlb_stat_leaders(all_players, ['pitching', 'pitchers'], [0, 1, 2, 3, 4]),
                'Innings Pitched': self._find_mlb_stat_leaders(all_players, ['pitching', 'pitchers'], [1, 2, 3, 4, 5]),
            }
            
            # If no position-specific stats found, try without position filtering
            if not any(mlb_categories.values()):
                logger.debug("No position-specific stats found, trying without position filtering...")
                mlb_categories = {
                    'Performance Stat 1': self._find_mlb_stat_leaders(all_players, [], [0, 1, 2]),
                    'Performance Stat 2': self._find_mlb_stat_leaders(all_players, [], [1, 2, 3]),
                    'Performance Stat 3': self._find_mlb_stat_leaders(all_players, [], [2, 3, 4]),
                    'Performance Stat 4': self._find_mlb_stat_leaders(all_players, [], [3, 4, 5]),
                }
            
            # Filter out empty categories
            leaders = {k: v for k, v in mlb_categories.items() if v}
            
            logger.debug(f"MLB Leaders extracted: {list(leaders.keys())}")
            for category, category_leaders in leaders.items():
                logger.debug(f"  {category}: {len(category_leaders)} leaders")
                for leader in category_leaders:
                    logger.debug(f"    {leader['name']} ({leader['team']}): {leader['value']}")
            
            return leaders
            
        except Exception as e:
            logger.error(f"Error in _extract_mlb_leaders: {str(e)}", exc_info=True)
            return {}

    def _find_mlb_stat_leaders(self, all_players, position_groups, stat_indices):
        """Find leaders for specific MLB stats based on position groups and indices"""
        try:
            logger.debug(f"    Finding leaders for position groups: {position_groups}, indices: {stat_indices}")
            category_leaders = []
            
            for player in all_players:
                # Filter by position group if specified (more flexible matching)
                if position_groups:
                    group_match = any(
                        group.lower() in player['position_group'].lower() 
                        for group in position_groups
                    )
                    if not group_match:
                        continue
                
                stats = player['stats']
                
                # Try multiple indices for this stat category
                stat_value = None
                found_index = None
                for index in stat_indices:
                    if len(stats) > index and stats[index] not in ['--', '', '0', None, 0]:
                        try:
                            numeric_value = float(stats[index])
                            if numeric_value > 0:
                                stat_value = stats[index]
                                found_index = index
                                break
                        except (ValueError, TypeError):
                            continue
                
                if stat_value:
                    logger.debug(f"      Found: {player['name']} = {stat_value} (index {found_index})")
                    category_leaders.append({
                        'name': player['name'],
                        'value': str(stat_value),
                        'team': player['team'],
                        'numeric_value': float(stat_value)
                    })
            
            # Sort by numeric value and take top performers
            if category_leaders:
                category_leaders.sort(key=lambda x: x.get('numeric_value', 0), reverse=True)
                # Remove the numeric_value field before returning
                for leader in category_leaders:
                    leader.pop('numeric_value', None)
                result = category_leaders[:3]
                logger.debug(f"    Returning {len(result)} leaders")
                return result
            
            logger.debug(f"    No leaders found for this category")
            return []
            
        except Exception as e:
            logger.error(f"Error in _find_mlb_stat_leaders: {str(e)}")
            return []
        
    def _extract_basketball_leaders(self, players):
        """Extract basketball-specific game leaders"""
        stat_categories = {
            'Points': {'indices': [0, 12, 13], 'names': ['points', 'pts']},
            'Rebounds': {'indices': [1, 7, 8], 'names': ['rebounds', 'reb', 'totalRebounds']},
            'Assists': {'indices': [2, 5, 6], 'names': ['assists', 'ast']},
            'Steals': {'indices': [3, 9, 10], 'names': ['steals', 'stl']},
            'Blocks': {'indices': [4, 11], 'names': ['blocks', 'blk']}
        }
        
        return self._extract_leaders_by_indices(players, stat_categories)
    
    def _extract_football_leaders(self, players):
        """Extract NFL-specific game leaders"""
        stat_categories = {
            'Passing Yards': {'indices': [0, 1, 8, 9], 'names': ['passingYards', 'passYds']},
            'Rushing Yards': {'indices': [2, 3, 10, 11], 'names': ['rushingYards', 'rushYds']},
            'Receiving Yards': {'indices': [4, 5, 12, 13], 'names': ['receivingYards', 'recYds']},
            'Touchdowns': {'indices': [6, 7, 14, 15], 'names': ['touchdowns', 'td']},
            'Tackles': {'indices': [16, 17, 18], 'names': ['tackles', 'tkl']}
        }
        
        return self._extract_leaders_by_indices(players, stat_categories)
    
    def _extract_soccer_leaders(self, players):
        """Extract soccer-specific game leaders"""
        stat_categories = {
            'Goals': {'indices': [0, 1], 'names': ['goals', 'g']},
            'Assists': {'indices': [2, 3], 'names': ['assists', 'a']},
            'Shots': {'indices': [4, 5], 'names': ['shots', 'sh']},
            'Saves': {'indices': [6, 7, 8], 'names': ['saves', 'sv']},
            'Yellow Cards': {'indices': [9, 10], 'names': ['yellowCards', 'yc']}
        }
        
        return self._extract_leaders_by_indices(players, stat_categories)
    
    def _extract_hockey_leaders(self, players):
        """Extract NHL-specific game leaders"""
        stat_categories = {
            'Goals': {'indices': [0, 1], 'names': ['goals', 'g']},
            'Assists': {'indices': [2, 3], 'names': ['assists', 'a']},
            'Points': {'indices': [4, 5], 'names': ['points', 'pts']},
            'Saves': {'indices': [6, 7, 8], 'names': ['saves', 'sv']},
            'Penalty Minutes': {'indices': [9, 10], 'names': ['penaltyMinutes', 'pim']}
        }
        
        return self._extract_leaders_by_indices(players, stat_categories)
    
    def _extract_generic_leaders(self, players):
        """Extract generic game leaders as fallback"""
        stat_categories = {
            'Performance': {'indices': [0, 1, 2], 'names': ['stat1']},
            'Key Stats': {'indices': [3, 4, 5], 'names': ['stat2']},
            'Other Stats': {'indices': [6, 7, 8], 'names': ['stat3']}
        }
        
        return self._extract_leaders_by_indices(players, stat_categories)
    
    def _extract_leaders_by_indices(self, players, stat_categories):
        """Generic helper to extract leaders using index-based approach"""
        leaders = {}
        
        for category_name, config in stat_categories.items():
            category_leaders = []
            
            # Collect all players' stats for this category
            for team_data in players:
                team_name = team_data.get('team', {}).get('abbreviation', 'UNK')
                
                statistics = team_data.get('statistics', [])
                if not isinstance(statistics, list):
                    continue
                
                for position_group in statistics:
                    if not isinstance(position_group, dict):
                        continue
                    
                    athletes = position_group.get('athletes', [])
                    for athlete in athletes:
                        if not isinstance(athlete, dict):
                            continue
                        
                        stats = athlete.get('stats', [])
                        athlete_info = athlete.get('athlete', {})
                        
                        if not isinstance(stats, list) or len(stats) == 0:
                            continue
                        
                        # Try multiple indices for this stat category
                        stat_value = None
                        for index in config['indices']:
                            if len(stats) > index and stats[index] not in ['--', '', '0', None]:
                                stat_value = stats[index]
                                break
                        
                        if stat_value and stat_value != '--' and stat_value != '0':
                            try:
                                numeric_value = float(stat_value)
                                if numeric_value > 0:
                                    category_leaders.append({
                                        'name': athlete_info.get('displayName', 'Unknown'),
                                        'value': str(stat_value),
                                        'team': team_name,
                                        'numeric_value': numeric_value
                                    })
                            except ValueError:
                                pass
            
            # Sort by numeric value and take top performers
            if category_leaders:
                category_leaders.sort(key=lambda x: x.get('numeric_value', 0), reverse=True)
                # Remove the numeric_value field before storing
                for leader in category_leaders:
                    leader.pop('numeric_value', None)
                leaders[category_name] = category_leaders[:3]
        
        return leaders
            
    def _extract_leaders_from_header(self, header):
        """Extract basic game info from header as fallback"""
        try:
            logger.debug("--- Creating basic leaders from header ---")
            leaders = {}
            
            # Get team names and scores as basic "leaders"
            competition = header.get('competitions', [{}])[0]
            competitors = competition.get('competitors', [])
            
            if len(competitors) >= 2:
                home_team = next((team for team in competitors if team.get('homeAway') == 'home'), {})
                away_team = next((team for team in competitors if team.get('homeAway') == 'away'), {})
                
                home_score = home_team.get('score', '0')
                away_score = away_team.get('score', '0')
                home_name = home_team.get('team', {}).get('abbreviation', 'HOME')
                away_name = away_team.get('team', {}).get('abbreviation', 'AWAY')
                
                # Create a simple "scoring" leader category if we have valid scores
                if home_score not in ['0', '', None] or away_score not in ['0', '', None]:
                    scoring_leaders = []
                    
                    try:
                        home_score_int = int(home_score or 0)
                        away_score_int = int(away_score or 0)
                        
                        if home_score_int >= away_score_int:
                            scoring_leaders.append({'name': 'Team Score', 'value': str(home_score), 'team': home_name})
                            scoring_leaders.append({'name': 'Team Score', 'value': str(away_score), 'team': away_name})
                        else:
                            scoring_leaders.append({'name': 'Team Score', 'value': str(away_score), 'team': away_name})
                            scoring_leaders.append({'name': 'Team Score', 'value': str(home_score), 'team': home_name})
                        
                        leaders['Team Scoring'] = scoring_leaders
                        logger.debug(f"Created basic team scoring leaders: {home_name} {home_score}, {away_name} {away_score}")
                    except ValueError:
                        logger.debug("Could not parse team scores as integers")
            
            return leaders
            
        except Exception as e:
            logger.error(f"Error extracting leaders from header: {str(e)}")
            return {}
        
    def _parse_scoring_summary(self, data, sport):
        """Parse scoring plays/summary"""
        try:
            scoring_summary = []
        
            # Look for scoring plays
            if 'scoringPlays' in data:
                for play in data['scoringPlays']:
                    scoring_summary.append({
                        'period': play.get('period', {}).get('displayValue', ''),
                        'clock': play.get('clock', {}).get('displayValue', ''),
                        'team': play.get('team', {}).get('abbreviation', ''),
                        'description': play.get('text', ''),
                        'score_value': play.get('scoreValue', 0)
                    })
        
            return scoring_summary
        
        except Exception as e:
            return []


# Initialize sports API
sports_api = SportsAPI()

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/teams/<path:sport>')
@limiter.limit("30 per minute")  # Rate limit: 30 requests per minute
def get_teams(sport):
    """Get teams for a specific sport"""
    # URL decode the sport parameter to handle spaces and special characters
    import urllib.parse
    sport = urllib.parse.unquote(sport)

    # Security: Sanitize input
    sport = sanitize_input(sport, VALID_SPORT_PATTERN, max_length=50)
    if not sport:
        logger.warning(f"Invalid sport parameter")
        return jsonify({'error': 'Invalid sport parameter'}), 400

    logger.debug(f"Getting teams for sport: '{sport}'")
    teams = sports_api.get_teams_by_sport(sport)
    logger.debug(f"Found {len(teams)} teams")
    return jsonify(teams)

@app.route('/api/scores/<path:sport>/<path:team>')
@limiter.limit("20 per minute")  # Rate limit: 20 requests per minute
def get_scores(sport, team):
    """Get scores for a specific team"""
    # URL decode the parameters to handle spaces and special characters
    import urllib.parse
    sport = urllib.parse.unquote(sport)
    team = urllib.parse.unquote(team)

    # Security: Sanitize inputs
    sport = sanitize_input(sport, VALID_SPORT_PATTERN, max_length=50)
    team = sanitize_input(team, VALID_TEAM_PATTERN, max_length=100)

    if not sport or not team:
        logger.warning(f"Invalid parameters after sanitization")
        return jsonify({'error': 'Invalid parameters'}), 400

    logger.debug(f"Getting scores for {team} in {sport}")
    try:
        scores = sports_api.get_scores(sport, team)
        return jsonify(scores)
    except Exception as e:
        logger.error(f"Error getting scores: {e}")
        return jsonify({'error': 'Service temporarily unavailable'}), 503

@app.route('/api/game-details/<path:sport>/<path:team>')
@limiter.limit("10 per minute")  # Rate limit: 10 requests per minute (more intensive)
def get_game_details(sport, team):
    """Get detailed game information for modal display"""
    import urllib.parse
    sport = urllib.parse.unquote(sport)
    team = urllib.parse.unquote(team)

    # Security: Sanitize inputs
    sport = sanitize_input(sport, VALID_SPORT_PATTERN, max_length=50)
    team = sanitize_input(team, VALID_TEAM_PATTERN, max_length=100)

    if not sport or not team:
        logger.warning(f"Invalid parameters after sanitization")
        return jsonify({'error': 'Invalid parameters'}), 400

    logger.debug(f"Getting detailed game data for {team} in {sport}")
    try:
        detailed_data = sports_api.get_detailed_game_data(sport, team)
        return jsonify(detailed_data)
    except Exception as e:
        logger.error(f"Error getting detailed data: {e}")
        return jsonify({'error': 'Service temporarily unavailable'}), 503

@app.route('/save_config', methods=['POST'])
@limiter.limit("10 per minute")  # Rate limit config saves
def save_config():
    """Save user's widget configuration"""
    try:
        config = request.json

        # Security: Validate config structure
        if not isinstance(config, dict):
            return jsonify({'error': 'Invalid configuration format'}), 400

        # Security: Limit config size to prevent abuse
        if len(json.dumps(config)) > 10000:  # 10KB limit
            return jsonify({'error': 'Configuration too large'}), 400

        response = make_response(jsonify({'status': 'saved'}))

        # Security: Secure cookie settings
        response.set_cookie(
            'sports_config',
            json.dumps(config),
            max_age=365*24*60*60,  # 1 year
            httponly=True,  # Prevent JavaScript access
            secure=True,    # HTTPS only (use False for local development)
            samesite='Lax'  # CSRF protection
        )
        return response
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return jsonify({'error': 'Failed to save configuration'}), 500

@app.route('/load_config')
@limiter.limit("30 per minute")  # Rate limit config loads
def load_config():
    """Load user's widget configuration"""
    try:
        config = request.cookies.get('sports_config')
        if config:
            # Security: Safely parse JSON
            parsed_config = json.loads(config)

            # Security: Validate structure
            if not isinstance(parsed_config, dict):
                logger.warning("Invalid config structure in cookie")
                return jsonify({})

            return jsonify(parsed_config)
        return jsonify({})
    except json.JSONDecodeError:
        logger.warning("Failed to parse config cookie")
        return jsonify({})
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return jsonify({})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)