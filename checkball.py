from flask import Flask, render_template, request, jsonify, make_response
import requests
import json
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

class SportsAPI:
    def __init__(self):
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports"
    
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
                    response = requests.get(url, timeout=3)  # Back to 3 seconds
                    data = response.json()
                    
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
                                        print(f"Original date: {game_date_str}")
                                        print(f"Parsed UTC: {game_date}")
                                        print(f"Eastern Time: {game_date_eastern}")
                                        print(f"Current Eastern: {now}")
                                    else:
                                        continue
                                except Exception as e:
                                    print(f"Date parsing error: {e}")
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
                except:
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
    
    def _select_game_by_priority(self, games, current_time):
        """Select game based on priority: today's game, upcoming within 24h, most recent"""
        today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        next_24h = current_time + timedelta(hours=24)
        
        # Priority 1: Today's games (completed or in progress)
        todays_games = [g for g in games if today_start <= g['game_date'] < today_end]
        if todays_games:
            # Prefer completed games first, then in-progress, then scheduled
            completed = [g for g in todays_games if g['status_type'] in ['STATUS_FINAL', 'STATUS_FINAL_OT']]
            in_progress = [g for g in todays_games if g['status_type'] in ['STATUS_IN_PROGRESS', 'STATUS_HALFTIME']]
            scheduled_today = [g for g in todays_games if g['status_type'] == 'STATUS_SCHEDULED']
            
            if completed:
                return completed[0]  # Most recent completed game today
            elif in_progress:
                return in_progress[0]  # Current game in progress
            elif scheduled_today:
                return scheduled_today[0]  # Game scheduled for today
        
        # Priority 2: Upcoming games within next 24 hours
        upcoming_games = [g for g in games if current_time <= g['game_date'] <= next_24h]
        if upcoming_games:
            # Sort by date, closest first
            upcoming_games.sort(key=lambda x: x['game_date'])
            return upcoming_games[0]
        
        # Priority 3: Most recent completed game
        past_games = [g for g in games if g['game_date'] < current_time and g['status_type'] in ['STATUS_FINAL', 'STATUS_FINAL_OT']]
        if past_games:
            # Sort by date, most recent first
            past_games.sort(key=lambda x: x['game_date'], reverse=True)
            return past_games[0]
        
        # Fallback: return the first game found
        games.sort(key=lambda x: x['game_date'], reverse=True)
        return games[0]
    
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

# Initialize sports API
sports_api = SportsAPI()

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/teams/<path:sport>')
def get_teams(sport):
    """Get teams for a specific sport"""
    # URL decode the sport parameter to handle spaces and special characters
    import urllib.parse
    sport = urllib.parse.unquote(sport)
    
    print(f"Getting teams for sport: '{sport}'")  # Debug log
    teams = sports_api.get_teams_by_sport(sport)
    print(f"Found {len(teams)} teams")  # Debug log
    return jsonify(teams)

@app.route('/api/scores/<path:sport>/<path:team>')
def get_scores(sport, team):
    """Get scores for a specific team"""
    # URL decode the parameters to handle spaces and special characters
    import urllib.parse
    sport = urllib.parse.unquote(sport)
    team = urllib.parse.unquote(team)
    
    print(f"Getting scores for {team} in {sport}")  # Debug log
    scores = sports_api.get_scores(sport, team)
    return jsonify(scores)

@app.route('/save_config', methods=['POST'])
def save_config():
    """Save user's widget configuration"""
    config = request.json
    response = make_response(jsonify({'status': 'saved'}))
    # Store config in cookie for 1 year
    response.set_cookie('sports_config', json.dumps(config), max_age=365*24*60*60)
    return response

@app.route('/load_config')
def load_config():
    """Load user's widget configuration"""
    config = request.cookies.get('sports_config')
    if config:
        return jsonify(json.loads(config))
    return jsonify({})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)